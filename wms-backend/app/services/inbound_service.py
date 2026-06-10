"""
WMS Panama — Servicio de Inbound
==================================
Orquesta el flujo completo:
  PurchaseOrder → ASN → GRN → QualityInspection → PutawayTask → RTV

Reglas de negocio críticas:
  1. La OC debe estar en estado CONFIRMED o OPEN para recibir mercancía.
  2. Un GRN puede crearse sin ASN (recepción ciega) o vinculado a uno.
  3. Si el GRN tiene líneas con temperatura fuera de rango, requires_qc=True automático.
  4. La QI aprobada dispara la creación de PutawayTasks.
  5. La QI rechazada dispara un RTV automático.
  6. El putaway completado actualiza el inventario via InventoryService.receive_stock().
  7. Todo actualiza quantities_received en la PO Line correspondiente.
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound import (
    ASNStatus,
    GRNStatus,
    POStatus,
    PutawayStatus,
    QCStatus,
)
from app.repositories.inbound import (
    ASNRepository,
    GRNRepository,
    PurchaseOrderRepository,
    PutawayTaskRepository,
    QualityInspectionRepository,
    RTVRepository,
)
from app.services.inventory_service import InventoryService
from app.core.exceptions import (
    InboundServiceError,
    POStateError,
    GRNStateError,
    QCStateError,
    PutawayStateError,
)

log = structlog.get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# INBOUND SERVICE
# ══════════════════════════════════════════════════════════════════════════════

class InboundService:
    """
    Servicio de Inbound — instanciar por request.
    Recibe la sesión de BD y el contexto del usuario actual.
    """

    # Temperatura máxima aceptable en cadena de frío (configurable)
    COLD_CHAIN_MAX_CELSIUS: Decimal = Decimal("8.0")
    COLD_CHAIN_MIN_CELSIUS: Decimal = Decimal("-25.0")

    def __init__(self, db: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

        # Repositorios
        self.po_repo = PurchaseOrderRepository(db, tenant_id)
        self.asn_repo = ASNRepository(db, tenant_id)
        self.grn_repo = GRNRepository(db, tenant_id)
        self.qi_repo = QualityInspectionRepository(db, tenant_id)
        self.putaway_repo = PutawayTaskRepository(db, tenant_id)
        self.rtv_repo = RTVRepository(db, tenant_id)

        # Servicio de inventario para movimientos finales
        self.inv_service = InventoryService(db, tenant_id, user_id)

    # ══════════════════════════════════════════════════════════════════════════
    # PURCHASE ORDER
    # ══════════════════════════════════════════════════════════════════════════

    async def create_purchase_order(
        self,
        warehouse_id: UUID,
        supplier_id: UUID,
        order_date,
        lines_data: List[dict],
        **kwargs,
    ):
        """Crear una OC nueva en estado DRAFT."""
        log.info("po.create", tenant=str(self.tenant_id), supplier=str(supplier_id))
        data = dict(
            warehouse_id=warehouse_id,
            supplier_id=supplier_id,
            order_date=order_date,
            status=POStatus.DRAFT,
            **kwargs,
        )
        po = await self.po_repo.create(
            data=data,
            lines_data=lines_data,
            created_by_id=self.user_id,
        )
        await self.po_repo.add_status_history(
            po_id=po.id,
            from_status=None,
            to_status=POStatus.DRAFT.value,
            changed_by_id=self.user_id,
            reason="Creación de la orden de compra",
        )
        return po

    # Estados de OC que admiten edición/eliminación
    _PO_EDITABLE_STATES = (POStatus.DRAFT,)
    _PO_DELETABLE_STATES = (POStatus.DRAFT, POStatus.CANCELLED)

    async def update_purchase_order(self, po_id: UUID, fields: dict):
        """Editar cabecera de una OC. Solo permitido en estado DRAFT."""
        po = await self.po_repo.get_by_id(po_id)
        if not po:
            raise InboundServiceError(f"PO {po_id} no encontrada.")
        if po.status not in self._PO_EDITABLE_STATES:
            raise POStateError(
                f"Solo se puede editar una OC en DRAFT. Estado actual: {po.status}"
            )
        clean = {k: v for k, v in fields.items() if v is not None}
        await self.po_repo.update_fields(po_id, clean)
        log.info("po.updated", po_id=str(po_id), fields=list(clean.keys()))
        return await self.po_repo.get_by_id(po_id)

    async def delete_purchase_order(self, po_id: UUID, reason: str = ""):
        """Eliminación lógica de una OC. Solo en DRAFT o CANCELLED."""
        po = await self.po_repo.get_by_id(po_id)
        if not po:
            raise InboundServiceError(f"PO {po_id} no encontrada.")
        if po.status not in self._PO_DELETABLE_STATES:
            raise POStateError(
                f"Solo se puede eliminar una OC en DRAFT o CANCELLED. Estado actual: {po.status}"
            )
        await self.po_repo.soft_delete(po_id, deleted_by=self.user_id)
        log.info("po.deleted", po_id=str(po_id), reason=reason)

    async def confirm_purchase_order(self, po_id: UUID):
        """Confirmar OC: DRAFT → CONFIRMED."""
        po = await self.po_repo.get_by_id(po_id)
        if not po:
            raise InboundServiceError(f"PO {po_id} no encontrada.")
        if po.status != POStatus.DRAFT:
            raise POStateError(
                f"Solo se puede confirmar una OC en DRAFT. Estado actual: {po.status}"
            )
        await self.po_repo.update_status(po_id, POStatus.CONFIRMED)
        await self.po_repo.add_status_history(
            po_id=po_id,
            from_status=POStatus.DRAFT.value,
            to_status=POStatus.CONFIRMED.value,
            changed_by_id=self.user_id,
            reason="Confirmación de la orden de compra",
        )
        log.info("po.confirmed", po_id=str(po_id))

    async def cancel_purchase_order(self, po_id: UUID, reason: str = ""):
        """Cancelar OC — solo si no tiene GRNs procesados."""
        po = await self.po_repo.get_by_id(po_id)
        if not po:
            raise InboundServiceError(f"PO {po_id} no encontrada.")
        if po.status in (POStatus.CLOSED, POStatus.CANCELLED):
            raise POStateError(f"No se puede cancelar. Estado actual: {po.status}")
        prev_status = po.status.value if hasattr(po.status, "value") else str(po.status)
        await self.po_repo.update_status(po_id, POStatus.CANCELLED)
        await self.po_repo.add_status_history(
            po_id=po_id,
            from_status=prev_status,
            to_status=POStatus.CANCELLED.value,
            changed_by_id=self.user_id,
            reason=reason or "Cancelación de la orden de compra",
        )
        log.info("po.cancelled", po_id=str(po_id), reason=reason)

    # ══════════════════════════════════════════════════════════════════════════
    # ASN
    # ══════════════════════════════════════════════════════════════════════════

    async def create_asn(
        self,
        warehouse_id: UUID,
        supplier_id: UUID,
        lines_data: List[dict],
        po_id: Optional[UUID] = None,
        **kwargs,
    ):
        """Crear un ASN. Puede vincularse a una OC o ser independiente."""
        if po_id:
            po = await self.po_repo.get_by_id(po_id)
            if not po:
                raise InboundServiceError(f"PO {po_id} no encontrada.")
            if po.status not in (POStatus.CONFIRMED, POStatus.PARTIALLY_RECEIVED):
                raise POStateError(
                    f"La OC debe estar CONFIRMED o PARTIALLY_RECEIVED. Estado: {po.status}"
                )

        data = dict(
            warehouse_id=warehouse_id,
            supplier_id=supplier_id,
            po_id=po_id,
            status=ASNStatus.CREATED,
            **kwargs,
        )
        asn = await self.asn_repo.create(
            data=data,
            lines_data=lines_data,
            created_by_id=self.user_id,
        )
        log.info("asn.created", asn_id=str(asn.id))
        return asn

    async def dispatch_asn(self, asn_id: UUID) -> None:
        """Marcar ASN como IN_TRANSIT (proveedor lo despachó)."""
        asn = await self.asn_repo.get_by_id(asn_id)
        if not asn:
            raise InboundServiceError(f"ASN {asn_id} no encontrado.")
        if asn.status != ASNStatus.CREATED:
            raise InboundServiceError(
                f"El ASN debe estar en CREATED para despacharse. Estado: {asn.status}"
            )
        await self.asn_repo.update_status(asn_id, ASNStatus.IN_TRANSIT)

    async def arrive_asn(self, asn_id: UUID, dock_number: Optional[str] = None) -> None:
        """ASN llega al almacén — IN_TRANSIT → ARRIVED."""
        asn = await self.asn_repo.get_by_id(asn_id)
        if not asn:
            raise InboundServiceError(f"ASN {asn_id} no encontrado.")
        await self.asn_repo.update_status(asn_id, ASNStatus.ARRIVED, dock_number=dock_number)
        log.info("asn.arrived", asn_id=str(asn_id), dock=dock_number)

    # ══════════════════════════════════════════════════════════════════════════
    # GRN — GOODS RECEIPT
    # ══════════════════════════════════════════════════════════════════════════

    async def create_grn(
        self,
        warehouse_id: UUID,
        lines_data: List[dict],
        asn_id: Optional[UUID] = None,
        po_id: Optional[UUID] = None,
        **kwargs,
    ):
        """
        Crear GRN (recibo de mercancía).

        Reglas:
          - Si hay ASN, debe estar en ARRIVED.
          - Si hay temperatura de producto fuera de rango, requires_qc = True.
          - Actualiza quantities_received en cada PO Line referenciada.
        """
        # Validar ASN si fue provisto
        if asn_id:
            asn = await self.asn_repo.get_by_id(asn_id)
            if not asn or asn.status != ASNStatus.ARRIVED:
                raise InboundServiceError(
                    "El ASN debe estar en estado ARRIVED para procesar un GRN."
                )

        # Detectar si requiere QC (cadena de frío rota u otra condición)
        requires_qc = kwargs.pop("requires_qc", False)
        ambient_temp = kwargs.get("ambient_temp_celsius")
        product_temp = kwargs.get("product_temp_celsius")
        if product_temp is not None:
            if (
                product_temp > self.COLD_CHAIN_MAX_CELSIUS
                or product_temp < self.COLD_CHAIN_MIN_CELSIUS
            ):
                requires_qc = True
                log.warning(
                    "grn.cold_chain_breach",
                    product_temp=str(product_temp),
                )

        # Añadir campos calculados al header
        grn_data = dict(
            warehouse_id=warehouse_id,
            asn_id=asn_id,
            po_id=po_id,
            status=GRNStatus.IN_PROGRESS,
            requires_qc=requires_qc,
            **kwargs,
        )

        grn = await self.grn_repo.create(
            data=grn_data,
            lines_data=lines_data,
            received_by_id=self.user_id,
        )

        # Actualizar PO Lines con cantidades recibidas
        for ld in lines_data:
            if ld.get("po_line_id"):
                await self.po_repo.update_line_received(
                    line_id=ld["po_line_id"],
                    qty_received_delta=ld["quantity_received"],
                    qty_rejected_delta=ld.get("quantity_rejected", Decimal("0")),
                )

        # Marcar ASN como RECEIVING
        if asn_id:
            await self.asn_repo.update_status(asn_id, ASNStatus.RECEIVING)

        log.info(
            "grn.created",
            grn_id=str(grn.id),
            requires_qc=requires_qc,
        )
        return grn

    async def confirm_grn(self, grn_id: UUID) -> None:
        """
        Confirmar GRN: IN_PROGRESS → CONFIRMED.

        Si requires_qc=True → estado CONFIRMED (pendiente QI).
        Si requires_qc=False → genera PutawayTasks directamente.
        """
        grn = await self.grn_repo.get_by_id(grn_id)
        if not grn:
            raise InboundServiceError(f"GRN {grn_id} no encontrado.")
        if grn.status != GRNStatus.IN_PROGRESS:
            raise GRNStateError(
                f"El GRN debe estar IN_PROGRESS para confirmar. Estado: {grn.status}"
            )

        await self.grn_repo.update_status(grn_id, GRNStatus.CONFIRMED)

        if not grn.requires_qc:
            # Sin QC: ir directo a putaway
            await self._generate_putaway_tasks(grn)
            await self.grn_repo.update_status(grn_id, GRNStatus.PUTAWAY_IN_PROGRESS)

        # Notificar la recepción al ERP (best-effort; no rompe el flujo si no está configurado)
        try:
            from app.integrations import erp
            await erp.push_goods_receipt({
                "grn_number": getattr(grn, "grn_number", None),
                "grn_id": str(grn_id),
                "warehouse_id": str(grn.warehouse_id),
                "purchase_order_id": str(getattr(grn, "purchase_order_id", "") or ""),
                "received_at": getattr(grn, "received_at", None).isoformat() if getattr(grn, "received_at", None) else None,
            })
        except Exception as e:  # nunca bloquear la confirmación por la integración
            log.warning("erp.push_grn_failed", grn_id=str(grn_id), error=str(e))

        log.info("grn.confirmed", grn_id=str(grn_id), requires_qc=grn.requires_qc)

    # ══════════════════════════════════════════════════════════════════════════
    # QUALITY INSPECTION
    # ══════════════════════════════════════════════════════════════════════════

    async def create_quality_inspection(
        self,
        grn_id: UUID,
        lines_data: List[dict],
        **kwargs,
    ):
        """Crear inspección de calidad para un GRN."""
        grn = await self.grn_repo.get_by_id(grn_id)
        if not grn:
            raise InboundServiceError(f"GRN {grn_id} no encontrado.")
        if grn.status != GRNStatus.CONFIRMED:
            raise GRNStateError(
                f"El GRN debe estar CONFIRMED para crear una QI. Estado: {grn.status}"
            )

        # Verificar que no ya exista una QI
        existing = await self.qi_repo.get_by_grn(grn_id)
        if existing and existing.status not in (QCStatus.REJECTED,):
            raise InboundServiceError(f"Ya existe una QI activa para el GRN {grn_id}.")

        qi = await self.qi_repo.create(
            grn_id=grn_id,
            data=kwargs,
            lines_data=lines_data,
            created_by_id=self.user_id,
        )
        log.info("qi.created", qi_id=str(qi.id), grn_id=str(grn_id))
        return qi

    async def resolve_quality_inspection(
        self,
        qi_id: UUID,
        approved: bool,
        disposition: str,
        disposition_notes: Optional[str] = None,
        return_to_vendor: bool = False,
    ) -> dict:
        """
        Aprobar o rechazar QI.

        Si aprobada → genera PutawayTasks.
        Si rechazada y return_to_vendor=True → genera RTV automático.
        """
        qi = await self.qi_repo.get_by_id(qi_id)
        if not qi:
            raise InboundServiceError(f"QI {qi_id} no encontrada.")
        if qi.status not in (QCStatus.PENDING, QCStatus.IN_PROGRESS):
            raise QCStateError(
                f"La QI debe estar PENDING o IN_PROGRESS. Estado: {qi.status}"
            )

        await self.qi_repo.resolve(
            qi_id=qi_id,
            approved=approved,
            disposition=disposition,
            disposition_notes=disposition_notes,
            inspector_id=self.user_id,
        )

        grn = await self.grn_repo.get_by_id(qi.grn_id)
        result: dict = {"qi_id": str(qi_id), "approved": approved}

        if approved:
            # QI aprobada → putaway
            if grn:
                await self._generate_putaway_tasks(grn)
                await self.grn_repo.update_status(
                    qi.grn_id, GRNStatus.PUTAWAY_IN_PROGRESS
                )
            log.info("qi.approved", qi_id=str(qi_id))

        else:
            # QI rechazada
            await self.grn_repo.update_status(qi.grn_id, GRNStatus.REJECTED)

            if return_to_vendor and grn:
                rtv = await self.rtv_repo.create(
                    data=dict(
                        grn_id=qi.grn_id,
                        supplier_id=getattr(grn, "supplier_id", None),
                        warehouse_id=grn.warehouse_id,
                        reason=disposition_notes or "Rechazado por control de calidad.",
                        credit_expected=Decimal("0"),
                        currency="USD",
                    ),
                    created_by_id=self.user_id,
                )
                result["rtv_id"] = str(rtv.id)
                log.info("rtv.auto_created", rtv_id=str(rtv.id), qi_id=str(qi_id))

        return result

    # ══════════════════════════════════════════════════════════════════════════
    # PUTAWAY
    # ══════════════════════════════════════════════════════════════════════════

    async def _suggest_location(self, warehouse_id: UUID, quarantine: bool = False):
        """Regla de slotting simple (FR-030/032): primera ubicación ACTIVA del tipo
        adecuado en la bodega, por secuencia de picking. Cuarentena para rechazos."""
        from sqlalchemy import select, and_
        from app.models.master_data import Location, LocationType, LocationStatus

        types = [LocationType.QUARANTINE] if quarantine else [LocationType.STANDARD, LocationType.BULK]
        stmt = (
            select(Location.id)
            .where(and_(
                Location.tenant_id == self.tenant_id,
                Location.warehouse_id == warehouse_id,
                Location.status == LocationStatus.ACTIVE,
                Location.location_type.in_(types),
            ))
            .order_by(Location.pick_sequence.asc().nullslast(), Location.code.asc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _generate_putaway_tasks(self, grn) -> List:
        """
        Genera PutawayTasks para cada línea aprobada del GRN.

        Regla de ubicación sugerida (simplificada):
          En el futuro, usar Putaway Rules (zona, clase de almacenamiento, etc.).
          Por ahora: ubicación de staging (from_location) = location_id de la línea.
          suggested_location_id = None (operador elige en RF).
        """
        tasks_data = []
        for line in grn.lines:
            status = getattr(line, "status", "approved")
            received = line.quantity_received or Decimal("0")
            rejected = line.quantity_rejected or Decimal("0")
            base = dict(
                warehouse_id=grn.warehouse_id, grn_id=grn.id, grn_line_id=line.id,
                product_id=line.product_id, uom=getattr(line, "uom", "UN"),
                from_location_id=line.location_id,
            )
            if status == "rejected":
                # Línea rechazada completa → cuarentena (FR-032)
                if received > 0:
                    qloc = await self._suggest_location(grn.warehouse_id, quarantine=True)
                    tasks_data.append(dict(base, quantity=received, suggested_location_id=qloc,
                                           priority=8, notes="Rechazado en QC → cuarentena"))
                continue
            net = received - rejected
            if net > 0:
                # Ubicación sugerida por reglas de slotting (FR-030)
                suggested = await self._suggest_location(grn.warehouse_id)
                tasks_data.append(dict(base, quantity=net, suggested_location_id=suggested, priority=5))
            if rejected > 0:
                qloc = await self._suggest_location(grn.warehouse_id, quarantine=True)
                tasks_data.append(dict(base, quantity=rejected, suggested_location_id=qloc,
                                       priority=8, notes="Cantidad rechazada → cuarentena"))

        tasks = await self.putaway_repo.create_bulk(tasks_data)
        log.info("putaway.tasks_created", count=len(tasks), grn_id=str(grn.id))
        return tasks

    async def start_putaway_task(self, task_id: UUID) -> None:
        """Operador inicia tarea de putaway en dispositivo RF."""
        task = await self.putaway_repo.get_by_id(task_id)
        if not task:
            raise InboundServiceError(f"Tarea de putaway {task_id} no encontrada.")
        if task.status != PutawayStatus.PENDING:
            raise PutawayStateError(
                f"La tarea debe estar PENDING. Estado: {task.status}"
            )
        await self.putaway_repo.start_task(task_id, self.user_id)

    async def complete_putaway_task(
        self,
        task_id: UUID,
        actual_location: str,
        override_reason: Optional[str] = None,
    ) -> None:
        """
        Completar putaway → actualiza inventario (receive_stock) y
        marca la tarea como COMPLETED.

        Si la ubicación elegida ≠ sugerida, override_reason es obligatorio.
        """
        task = await self.putaway_repo.get_by_id(task_id)
        if not task:
            raise InboundServiceError(f"Tarea de putaway {task_id} no encontrada.")
        if task.status != PutawayStatus.IN_PROGRESS:
            raise PutawayStateError(
                f"La tarea debe estar IN_PROGRESS. Estado: {task.status}"
            )

        # Resolver actual_location a UUID
        try:
            actual_location_id = UUID(actual_location)
        except ValueError:
            from sqlalchemy import select
            from app.models.master_data import Location
            stmt = select(Location.id).where(
                Location.tenant_id == self.tenant_id,
                Location.code == actual_location
            )
            actual_location_id = (await self.db.execute(stmt)).scalar_one_or_none()
            if not actual_location_id:
                raise InboundServiceError(f"Ubicación con código {actual_location} no encontrada.")

        # Validar override_reason si la ubicación difiere de la sugerida
        if (
            task.suggested_location_id
            and task.suggested_location_id != actual_location_id
            and not override_reason
        ):
            raise InboundServiceError(
                "Se requiere override_reason cuando la ubicación real difiere de la sugerida."
            )

        # Ingresar stock al inventario
        await self.inv_service.receive_stock(
            warehouse_id=task.warehouse_id,
            product_id=task.product_id,
            location_id=actual_location_id,
            quantity=task.quantity,
            reference_type="putaway",
            reference_id=task_id,
            reference_number=f"PUTAWAY-{task_id}",
        )

        # Marcar tarea completada
        await self.putaway_repo.complete_task(task_id, actual_location_id, override_reason)

        # Verificar si todos los putaway del GRN están completos
        if task.grn_id:
            await self._check_grn_putaway_completion(task.grn_id)

        log.info(
            "putaway.completed",
            task_id=str(task_id),
            location=str(actual_location_id),
        )

    async def _check_grn_putaway_completion(self, grn_id: UUID) -> None:
        """Si todos los putaway tasks del GRN están COMPLETED → GRN = COMPLETED."""
        from sqlalchemy import and_, select
        from app.models.inbound import PutawayTask as PT, PutawayStatus as PS

        result = await self.db.execute(
            select(PT).where(
                and_(
                    PT.grn_id == grn_id,
                    PT.tenant_id == self.tenant_id,
                    PT.status != PS.COMPLETED,
                )
            )
        )
        pending = result.scalars().first()
        if pending is None:
            await self.grn_repo.update_status(grn_id, GRNStatus.COMPLETED)
            log.info("grn.completed_all_putaway", grn_id=str(grn_id))

    # ══════════════════════════════════════════════════════════════════════════
    # RETURN TO VENDOR
    # ══════════════════════════════════════════════════════════════════════════

    async def create_rtv(
        self,
        supplier_id: UUID,
        warehouse_id: UUID,
        reason: str,
        **kwargs,
    ):
        """Crear devolución manual a proveedor."""
        data = dict(
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            reason=reason,
            **kwargs,
        )
        rtv = await self.rtv_repo.create(data=data, created_by_id=self.user_id)
        log.info("rtv.created", rtv_id=str(rtv.id))
        return rtv

    async def ship_rtv(self, rtv_id: UUID) -> None:
        """Marcar RTV como despachado al proveedor."""
        from app.models.inbound import RTVStatus
        rtv = await self.rtv_repo.get_by_id(rtv_id)
        if not rtv:
            raise InboundServiceError(f"RTV {rtv_id} no encontrado.")
        await self.rtv_repo.update_status(rtv_id, RTVStatus.SHIPPED)

    async def confirm_rtv_credit(
        self,
        rtv_id: UUID,
        credit_memo_number: str,
        credit_received: Decimal,
    ) -> None:
        """Registrar nota de crédito recibida del proveedor."""
        from app.models.inbound import RTVStatus
        await self.rtv_repo.update_status(
            rtv_id,
            RTVStatus.CREDIT_RECEIVED,
            credit_memo_number=credit_memo_number,
            credit_received=credit_received,
        )
        log.info(
            "rtv.credit_confirmed",
            rtv_id=str(rtv_id),
            credit=str(credit_received),
        )

    # ══════════════════════════════════════════════════════════════════════════
    # DASHBOARD
    # ══════════════════════════════════════════════════════════════════════════

    async def get_dashboard_metrics(self, warehouse_id: Optional[UUID] = None) -> dict:
        """KPIs del módulo inbound para el dashboard."""
        from sqlalchemy import and_, func, select

        from app.models.inbound import (
            GoodsReceipt,
            PurchaseOrder,
            QualityInspection,
            ReturnToVendor,
        )
        from datetime import date

        today = date.today()

        # POs abiertas
        pos_open = (
            await self.db.execute(
                select(func.count(PurchaseOrder.id)).where(
                    and_(
                        PurchaseOrder.tenant_id == self.tenant_id,
                        PurchaseOrder.status.in_(
                            [POStatus.DRAFT, POStatus.CONFIRMED, POStatus.PARTIALLY_RECEIVED]
                        ),
                    )
                )
            )
        ).scalar_one()

        # POs pendientes de recibo (con expected_delivery_date pasada)
        pos_overdue = (
            await self.db.execute(
                select(func.count(PurchaseOrder.id)).where(
                    and_(
                        PurchaseOrder.tenant_id == self.tenant_id,
                        PurchaseOrder.status.in_(
                            [POStatus.CONFIRMED, POStatus.PARTIALLY_RECEIVED]
                        ),
                        PurchaseOrder.expected_delivery_date < today,
                    )
                )
            )
        ).scalar_one()

        # GRNs de hoy
        grns_today = (
            await self.db.execute(
                select(func.count(GoodsReceipt.id)).where(
                    and_(
                        GoodsReceipt.tenant_id == self.tenant_id,
                        func.date(GoodsReceipt.received_at) == today,
                    )
                )
            )
        ).scalar_one()

        # GRNs pendientes QC
        grns_pending_qc = (
            await self.db.execute(
                select(func.count(GoodsReceipt.id)).where(
                    and_(
                        GoodsReceipt.tenant_id == self.tenant_id,
                        GoodsReceipt.status == GRNStatus.CONFIRMED,
                        GoodsReceipt.requires_qc == True,
                    )
                )
            )
        ).scalar_one()

        # GRNs pendientes putaway
        grns_pending_putaway = (
            await self.db.execute(
                select(func.count(GoodsReceipt.id)).where(
                    and_(
                        GoodsReceipt.tenant_id == self.tenant_id,
                        GoodsReceipt.status == GRNStatus.PUTAWAY_IN_PROGRESS,
                    )
                )
            )
        ).scalar_one()

        # RTV pendientes
        from app.models.inbound import RTVStatus
        rtv_pending = (
            await self.db.execute(
                select(func.count(ReturnToVendor.id)).where(
                    and_(
                        ReturnToVendor.tenant_id == self.tenant_id,
                        ReturnToVendor.status.in_(
                            [RTVStatus.PENDING, RTVStatus.APPROVED, RTVStatus.SHIPPED]
                        ),
                    )
                )
            )
        ).scalar_one()

        # Tasa de defectos promedio
        avg_defect = (
            await self.db.execute(
                select(func.avg(QualityInspection.defect_rate)).where(
                    QualityInspection.tenant_id == self.tenant_id
                )
            )
        ).scalar_one_or_none()

        putaway_open = await self.putaway_repo.get_open_count()
        avg_cycle_time = await self.putaway_repo.get_avg_cycle_time()

        # Precisión de recepción = recibido / ordenado sobre líneas de OC (FR-072)
        from app.models.inbound import PurchaseOrderLine
        racc = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(PurchaseOrderLine.quantity_ordered), 0),
                    func.coalesce(func.sum(PurchaseOrderLine.quantity_received), 0),
                ).where(PurchaseOrderLine.tenant_id == self.tenant_id)
            )
        ).one()
        ord_qty, rec_qty = racc[0] or Decimal("0"), racc[1] or Decimal("0")
        receipt_accuracy = round(Decimal(rec_qty) / Decimal(ord_qty) * 100, 2) if ord_qty else None

        return {
            "pos_open": pos_open,
            "pos_pending_receipt": pos_open,
            "pos_overdue": pos_overdue,
            "grns_today": grns_today,
            "grns_pending_qc": grns_pending_qc,
            "grns_pending_putaway": grns_pending_putaway,
            "avg_defect_rate_pct": round((avg_defect or Decimal("0")) * 100, 2),
            "rtv_pending": rtv_pending,
            "avg_putaway_cycle_time_seconds": avg_cycle_time,
            "putaway_tasks_open": putaway_open,
            "receipt_accuracy_pct": receipt_accuracy,
        }

    async def get_throughput_series(
        self, days: int = 7, warehouse_id: Optional[UUID] = None
    ) -> dict:
        """Serie temporal diaria (GRNs recibidos y putaway completados).

        Alimenta las gráficas del dashboard con datos reales agregados por día.
        Rellena con ceros los días sin actividad para mantener el eje continuo.
        """
        from datetime import date, timedelta

        from sqlalchemy import and_, func, select

        from app.models.inbound import GoodsReceipt, PutawayTask

        today = date.today()
        start = today - timedelta(days=days - 1)

        # GRNs recibidos por día
        grn_filters = [
            GoodsReceipt.tenant_id == self.tenant_id,
            func.date(GoodsReceipt.received_at) >= start,
        ]
        if warehouse_id is not None:
            grn_filters.append(GoodsReceipt.warehouse_id == warehouse_id)
        grn_rows = (
            await self.db.execute(
                select(
                    func.date(GoodsReceipt.received_at).label("day"),
                    func.count(GoodsReceipt.id).label("n"),
                )
                .where(and_(*grn_filters))
                .group_by(func.date(GoodsReceipt.received_at))
            )
        ).all()
        grn_by_day = {str(r.day): int(r.n) for r in grn_rows}

        # Putaway completados por día
        pt_filters = [
            PutawayTask.tenant_id == self.tenant_id,
            PutawayTask.status == PutawayStatus.COMPLETED,
            func.date(PutawayTask.completed_at) >= start,
        ]
        pt_rows = (
            await self.db.execute(
                select(
                    func.date(PutawayTask.completed_at).label("day"),
                    func.count(PutawayTask.id).label("n"),
                )
                .where(and_(*pt_filters))
                .group_by(func.date(PutawayTask.completed_at))
            )
        ).all()
        putaway_by_day = {str(r.day): int(r.n) for r in pt_rows}

        series = []
        for i in range(days):
            d = start + timedelta(days=i)
            key = d.isoformat()
            series.append(
                {
                    "day": d,
                    "grns": grn_by_day.get(key, 0),
                    "putaway_completed": putaway_by_day.get(key, 0),
                }
            )
        return {"series": series}
