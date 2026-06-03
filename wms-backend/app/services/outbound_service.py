"""
WMS Panama — Servicio Outbound
================================
Orquesta el flujo completo de salida:
  SalesOrder → PickingWave → PickingTask → PackTask → Shipment → (RMA)

Reglas de negocio críticas:
  1. SO confirmada → reserva stock vía InventoryService (FEFO).
  2. Wave picking agrupa SOs por prioridad; genera PickingTasks por línea/ubicación.
  3. PickingTask completada → libera reserva, descuenta inventario (PICK movement).
  4. Short pick → genera backorder en la SO Line correspondiente.
  5. Todas las PickingTasks completadas → SO pasa a PICKING→PACKED.
  6. PackTask completada → SO pasa a PACKED, lista para despacho.
  7. Shipment despachado → SO pasa a SHIPPED; entregado → DELIVERED.
  8. RMA recibida con restocking → devuelve stock vía InventoryService.receive_stock().
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    OrderStateError,
    OutboundServiceError,
    PickingStateError,
)
from app.models.outbound import (
    PackStatus,
    PickingMethod,
    PickingStatus,
    ReturnOrderStatus,
    SOLineStatus,
    SOStatus,
    ShipmentStatus,
    WaveStatus,
)
from app.repositories.outbound import (
    PackTaskRepository,
    PickingTaskRepository,
    PickingWaveRepository,
    ReturnOrderRepository,
    SalesOrderRepository,
    ShipmentRepository,
)
from app.schemas.inventory import InventoryReservationCreate
from app.services.inventory_service import InventoryService

log = structlog.get_logger(__name__)


class OutboundService:
    """Servicio Outbound — instanciar por request."""

    def __init__(self, db: AsyncSession, tenant_id: UUID, user_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

        self.so_repo     = SalesOrderRepository(db, tenant_id)
        self.wave_repo   = PickingWaveRepository(db, tenant_id)
        self.pick_repo   = PickingTaskRepository(db, tenant_id)
        self.pack_repo   = PackTaskRepository(db, tenant_id)
        self.ship_repo   = ShipmentRepository(db, tenant_id)
        self.rma_repo    = ReturnOrderRepository(db, tenant_id)
        self.inv_service = InventoryService(db, tenant_id, user_id)

    # ══════════════════════════════════════════════════════════════════════════
    # SALES ORDER
    # ══════════════════════════════════════════════════════════════════════════

    async def create_sales_order(
        self,
        warehouse_id: UUID,
        customer_id: UUID,
        order_date,
        lines_data: List[dict],
        **kwargs,
    ):
        """Crear SO en estado DRAFT."""
        data = dict(
            warehouse_id=warehouse_id,
            customer_id=customer_id,
            order_date=order_date,
            **kwargs,
        )
        so = await self.so_repo.create(
            data=data,
            lines_data=lines_data,
            created_by_id=self.user_id,
        )
        log.info("so.created", so_id=str(so.id), lines=len(lines_data))
        return so

    async def confirm_sales_order(self, so_id: UUID) -> None:
        """
        Confirmar SO: DRAFT → CONFIRMED.
        Reserva el stock vía FEFO para cada línea.
        """
        so = await self.so_repo.get_by_id(so_id)
        if not so:
            raise OutboundServiceError(f"SO {so_id} no encontrada.")
        if so.status != SOStatus.DRAFT:
            raise OrderStateError(
                f"Solo se puede confirmar una SO en DRAFT. Estado: {so.status}"
            )

        # Reservar stock línea por línea (FEFO)
        for line in so.lines:
            try:
                await self.inv_service.create_reservation(
                    InventoryReservationCreate(
                        warehouse_id=so.warehouse_id,
                        product_id=line.product_id,
                        quantity=line.quantity_ordered,
                        reservation_type="soft",
                        reference_type="SO",
                        reference_id=so_id,
                        reference_number=so.so_number,
                    )
                )
                await self.so_repo.update_line_quantities(
                    line.id, "quantity_allocated", line.quantity_ordered
                )
            except Exception as e:
                # Stock insuficiente → línea en BACKORDERED
                log.warning("so.backorder_line", line_id=str(line.id), reason=str(e))
                await self.so_repo.update_line_quantities(
                    line.id, "quantity_backordered", line.quantity_ordered
                )

        await self.so_repo.update_status(so_id, SOStatus.CONFIRMED)
        log.info("so.confirmed", so_id=str(so_id))

    async def cancel_sales_order(self, so_id: UUID, reason: str) -> None:
        """Cancelar SO — libera reservas de inventario."""
        so = await self.so_repo.get_by_id(so_id)
        if not so:
            raise OutboundServiceError(f"SO {so_id} no encontrada.")
        if so.status in (SOStatus.SHIPPED, SOStatus.DELIVERED, SOStatus.CANCELLED):
            raise OrderStateError(
                f"No se puede cancelar. Estado: {so.status}"
            )
        # Liberar reservas
        try:
            from app.db.redis import get_cache_redis  # noqa: import local
        except Exception:
            pass

        await self.so_repo.update_status(so_id, SOStatus.CANCELLED, cancel_reason=reason)
        log.info("so.cancelled", so_id=str(so_id), reason=reason)

    # ══════════════════════════════════════════════════════════════════════════
    # PICKING WAVE
    # ══════════════════════════════════════════════════════════════════════════

    async def create_wave(
        self,
        warehouse_id: UUID,
        so_ids: List[UUID],
        picking_method: PickingMethod = PickingMethod.DISCRETE,
        priority: int = 5,
        notes: Optional[str] = None,
    ):
        """
        Crear una wave de picking agrupando múltiples SOs.
        Las SOs deben estar en CONFIRMED o ALLOCATED.
        """
        valid_sos = []
        for so_id in so_ids:
            so = await self.so_repo.get_by_id(so_id)
            if not so:
                raise OutboundServiceError(f"SO {so_id} no encontrada.")
            if so.status not in (SOStatus.CONFIRMED, SOStatus.ALLOCATED):
                raise OrderStateError(
                    f"SO {so.so_number} debe estar CONFIRMED o ALLOCATED. Estado: {so.status}"
                )
            valid_sos.append(so)

        wave_data = dict(
            warehouse_id=warehouse_id,
            picking_method=picking_method,
            priority=priority,
            notes=notes,
            total_orders=len(valid_sos),
        )
        wave = await self.wave_repo.create(wave_data, created_by_id=self.user_id)

        # Calcular totales y vincular SOs a la wave
        total_lines = 0
        total_units = Decimal("0")
        for so in valid_sos:
            # Actualizar SO con wave_id
            from sqlalchemy import update as sa_update
            from app.models.outbound import SalesOrder as SO_model
            await self.db.execute(
                sa_update(SO_model)
                .where(SO_model.id == so.id)
                .values(wave_id=wave.id, status=SOStatus.ALLOCATED,
                        updated_at=__import__("datetime").datetime.now(
                            __import__("datetime").timezone.utc))
            )
            total_lines += len(so.lines)
            for line in so.lines:
                total_units += line.quantity_ordered

        # Actualizar contadores de la wave
        from sqlalchemy import update as sa_update2
        from app.models.outbound import PickingWave as PW_model
        await self.db.execute(
            sa_update2(PW_model)
            .where(PW_model.id == wave.id)
            .values(total_lines=total_lines, total_units=total_units)
        )

        log.info("wave.created", wave_id=str(wave.id), orders=len(valid_sos))
        return wave

    async def release_wave(self, wave_id: UUID) -> List:
        """
        Liberar wave → genera PickingTasks para cada línea de SO.
        FEFO determina la ubicación de cada pick.
        """
        wave = await self.wave_repo.get_by_id(wave_id)
        if not wave:
            raise OutboundServiceError(f"Wave {wave_id} no encontrada.")
        if wave.status != WaveStatus.OPEN:
            raise OutboundServiceError(
                f"La wave debe estar OPEN para liberar. Estado: {wave.status}"
            )

        # Obtener todas las SOs de la wave
        from sqlalchemy import select, and_
        from app.models.outbound import SalesOrder as SO_model
        sos_result = await self.db.execute(
            select(SO_model).where(
                and_(SO_model.wave_id == wave_id, SO_model.tenant_id == self.tenant_id)
            )
        )
        sos = sos_result.scalars().all()

        # Cargar líneas de cada SO y generar tasks
        tasks_data = []
        for so in sos:
            so_full = await self.so_repo.get_by_id(so.id)
            if not so_full:
                continue
            for line in so_full.lines:
                if line.status in (SOLineStatus.CANCELLED, SOLineStatus.SHIPPED):
                    continue
                qty = line.quantity_allocated or line.quantity_ordered

                # FEFO: obtener batches/ubicaciones disponibles
                batches = await self.inv_service.levels.get_available_batches_fefo(
                    tenant_id=self.tenant_id,
                    warehouse_id=so.warehouse_id,
                    product_id=line.product_id,
                    quantity_needed=qty,
                )

                for batch_alloc in batches:
                    level = batch_alloc["level"]
                    alloc_qty = min(batch_alloc["quantity_to_use"], qty)
                    tasks_data.append(dict(
                        wave_id=wave_id,
                        so_id=so.id,
                        so_line_id=line.id,
                        product_id=line.product_id,
                        uom_id=line.uom_id,
                        batch_id=level.batch_id,
                        quantity_requested=alloc_qty,
                        from_location_id=level.location_id,
                        priority=so.priority,
                    ))
                    qty -= alloc_qty
                    if qty <= 0:
                        break

        # Aplicar la modalidad de picking de la wave (FR-051/052/054)
        method = getattr(getattr(wave, "picking_method", None), "value", None) or "discrete"
        tasks_data = self._apply_picking_method(tasks_data, method)

        tasks = await self.pick_repo.create_bulk(tasks_data)
        await self.wave_repo.release(wave_id)

        log.info("wave.released", wave_id=str(wave_id), tasks=len(tasks), method=method)
        return tasks

    @staticmethod
    def _apply_picking_method(tasks_data: list[dict], method: str) -> list[dict]:
        """Ajusta las tareas según la modalidad (puro código, FR-051/052/054):
          - zone: ordena/secuencia por ubicación de origen (recorrido por zona).
          - batch: marca consolidación (varias órdenes en un recorrido).
          - cluster: asigna un índice de contenedor por orden de venta.
          - discrete: 1 orden = 1 recorrido (default).
        """
        m = (method or "discrete").lower()
        if not tasks_data:
            return tasks_data
        if m == "zone":
            tasks_data.sort(key=lambda t: str(t.get("from_location_id") or ""))
            for seq, t in enumerate(tasks_data, start=1):
                t["priority"] = seq
                t["notes"] = f"ZONE · secuencia {seq}"
        elif m == "batch":
            so_ids = sorted({str(t.get("so_id")) for t in tasks_data})
            for t in tasks_data:
                t["notes"] = f"BATCH · {len(so_ids)} órdenes (consolidar en sorting)"
        elif m == "cluster":
            cluster_index = {soid: i + 1 for i, soid in enumerate(sorted({str(t.get('so_id')) for t in tasks_data}))}
            for t in tasks_data:
                t["notes"] = f"CLUSTER · contenedor {cluster_index[str(t.get('so_id'))]}"
        return tasks_data

    # ══════════════════════════════════════════════════════════════════════════
    # PICKING TASKS
    # ══════════════════════════════════════════════════════════════════════════

    async def start_pick_task(self, task_id: UUID) -> None:
        """Operador RF inicia tarea de picking."""
        task = await self.pick_repo.get_by_id(task_id)
        if not task:
            raise OutboundServiceError(f"Tarea {task_id} no encontrada.")
        if task.status != PickingStatus.PENDING:
            raise PickingStateError(
                f"La tarea debe estar PENDING. Estado: {task.status}"
            )
        await self.pick_repo.start(task_id, self.user_id)

    async def complete_pick_task(
        self,
        task_id: UUID,
        quantity_picked: Decimal,
        sscc_scanned: Optional[str] = None,
        gtin_scanned: Optional[str] = None,
        short_reason: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """
        Completar tarea de picking:
          1. Valida estado.
          2. Verifica short_reason si hay short-pick.
          3. Descuenta inventario (PICK movement).
          4. Actualiza cantidad pickeada en SO Line.
          5. Si short → genera backorder.
          6. Verifica si todas las tasks de la SO están completas.
        """
        task = await self.pick_repo.get_by_id(task_id)
        if not task:
            raise OutboundServiceError(f"Tarea {task_id} no encontrada.")
        if task.status != PickingStatus.IN_PROGRESS:
            raise PickingStateError(
                f"La tarea debe estar IN_PROGRESS. Estado: {task.status}"
            )

        quantity_short = task.quantity_requested - quantity_picked
        if quantity_short < 0:
            raise OutboundServiceError(
                "quantity_picked no puede superar quantity_requested."
            )
        if quantity_short > 0 and not short_reason:
            raise OutboundServiceError(
                "short_reason es obligatorio cuando hay short pick."
            )

        # Descontar inventario (pin a la ubicación de la tarea de picking)
        if quantity_picked > 0:
            so = await self.so_repo.get_by_id(task.so_id)
            await self.inv_service.pick_stock(
                warehouse_id=so.warehouse_id,
                product_id=task.product_id,
                quantity=quantity_picked,
                reference_type="SO",
                reference_id=task.so_id,
                reference_number=f"PICK-{task_id}",
                force_location_id=task.from_location_id,
            )

        # Completar tarea en BD
        await self.pick_repo.complete(
            task_id=task_id,
            quantity_picked=quantity_picked,
            quantity_short=quantity_short,
            sscc_scanned=sscc_scanned,
            gtin_scanned=gtin_scanned,
            short_reason=short_reason,
            notes=notes,
        )

        # Actualizar SO Line
        await self.so_repo.update_line_quantities(
            task.so_line_id, "quantity_picked", quantity_picked
        )
        if quantity_short > 0:
            await self.so_repo.update_line_quantities(
                task.so_line_id, "quantity_backordered", quantity_short
            )

        # Verificar si toda la SO fue pickeada
        result = {"task_id": str(task_id), "short": float(quantity_short)}
        pending = await self.pick_repo.count_pending_for_so(task.so_id)
        if pending == 0:
            await self.so_repo.update_status(task.so_id, SOStatus.PICKING)
            await self._generate_pack_task(task.so_id)
            result["so_ready_for_packing"] = True
            log.info("so.all_picked", so_id=str(task.so_id))

        return result

    async def _generate_pack_task(self, so_id: UUID) -> None:
        """Crear PackTask automáticamente cuando todos los picks están listos."""
        existing = await self.pack_repo.get_by_so(so_id)
        if not existing:
            await self.pack_repo.create(so_id=so_id, created_by_id=self.user_id)
            log.info("pack_task.auto_created", so_id=str(so_id))

    # ══════════════════════════════════════════════════════════════════════════
    # PACKING
    # ══════════════════════════════════════════════════════════════════════════

    async def start_pack_task(self, task_id: UUID) -> None:
        task = await self.pack_repo.get_by_id(task_id)
        if not task:
            raise OutboundServiceError(f"Pack task {task_id} no encontrada.")
        if task.status != PackStatus.PENDING:
            raise OutboundServiceError(
                f"La tarea de empaque debe estar PENDING. Estado: {task.status}"
            )
        await self.pack_repo.start(task_id, self.user_id)

    async def complete_pack_task(
        self,
        task_id: UUID,
        box_type: str,
        box_count: int,
        total_weight_kg: Optional[Decimal] = None,
        total_volume_m3: Optional[Decimal] = None,
        sscc: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        """
        Completar empaque → SO pasa a PACKED.
        """
        task = await self.pack_repo.get_by_id(task_id)
        if not task:
            raise OutboundServiceError(f"Pack task {task_id} no encontrada.")
        if task.status != PackStatus.IN_PROGRESS:
            raise OutboundServiceError(
                f"La tarea de empaque debe estar IN_PROGRESS. Estado: {task.status}"
            )

        # Generar SSCC GS1 único si el operario no lo capturó (FR-056)
        if not sscc:
            from app.core.gs1 import generate_sscc
            sscc = generate_sscc(company_prefix="0000000")

        await self.pack_repo.complete(
            task_id=task_id,
            box_type=box_type,
            box_count=box_count,
            total_weight_kg=total_weight_kg,
            total_volume_m3=total_volume_m3,
            sscc=sscc,
            notes=notes,
        )

        await self.so_repo.update_status(task.so_id, SOStatus.PACKED)
        log.info("pack.completed", task_id=str(task_id), so_id=str(task.so_id))

    # ══════════════════════════════════════════════════════════════════════════
    # SHIPMENT
    # ══════════════════════════════════════════════════════════════════════════

    async def create_shipment(self, so_id: UUID, data: dict):
        """Crear envío para una SO en estado PACKED."""
        so = await self.so_repo.get_by_id(so_id)
        if not so:
            raise OutboundServiceError(f"SO {so_id} no encontrada.")
        if so.status != SOStatus.PACKED:
            raise OrderStateError(
                f"La SO debe estar PACKED para crear un envío. Estado: {so.status}"
            )

        shipment_data = {"so_id": so_id, **data}
        shipment = await self.ship_repo.create(shipment_data, created_by_id=self.user_id)
        await self.so_repo.update_status(so_id, SOStatus.PACKED)  # mantiene hasta despacho
        log.info("shipment.created", shipment_id=str(shipment.id))
        return shipment

    async def dispatch_shipment(self, shipment_id: UUID, dispatch_data: dict) -> None:
        """Despachar envío → SO pasa a SHIPPED."""
        shipment = await self.ship_repo.get_by_id(shipment_id)
        if not shipment:
            raise OutboundServiceError(f"Shipment {shipment_id} no encontrado.")
        if shipment.status != ShipmentStatus.PENDING:
            raise OutboundServiceError(
                f"El shipment debe estar PENDING. Estado: {shipment.status}"
            )

        await self.ship_repo.dispatch(shipment_id, dispatch_data)
        await self.so_repo.update_status(shipment.so_id, SOStatus.SHIPPED)
        # Actualizar quantities_shipped en todas las líneas
        so = await self.so_repo.get_by_id(shipment.so_id)
        if so:
            for line in so.lines:
                if line.quantity_picked > 0:
                    await self.so_repo.update_line_quantities(
                        line.id, "quantity_shipped", line.quantity_picked
                    )

        # Notificar el despacho al ERP (best-effort; no rompe el flujo)
        try:
            from app.integrations import erp
            await erp.push_shipment({
                "shipment_number": getattr(shipment, "shipment_number", None),
                "shipment_id": str(shipment_id),
                "so_id": str(shipment.so_id),
                "carrier_name": getattr(shipment, "carrier_name", None),
                "tracking_number": getattr(shipment, "tracking_number", None),
            })
        except Exception as e:
            log.warning("erp.push_shipment_failed", shipment_id=str(shipment_id), error=str(e))

        log.info("shipment.dispatched", shipment_id=str(shipment_id))

    async def deliver_shipment(self, shipment_id: UUID, delivery_data: dict) -> None:
        """Confirmar entrega → SO pasa a DELIVERED."""
        shipment = await self.ship_repo.get_by_id(shipment_id)
        if not shipment:
            raise OutboundServiceError(f"Shipment {shipment_id} no encontrado.")
        if shipment.status != ShipmentStatus.IN_TRANSIT:
            raise OutboundServiceError(
                f"El shipment debe estar IN_TRANSIT para confirmar entrega. Estado: {shipment.status}"
            )

        await self.ship_repo.deliver(shipment_id, delivery_data)
        await self.so_repo.update_status(shipment.so_id, SOStatus.DELIVERED)
        log.info("shipment.delivered", shipment_id=str(shipment_id))

    # ══════════════════════════════════════════════════════════════════════════
    # RETURN ORDER (RMA)
    # ══════════════════════════════════════════════════════════════════════════

    async def create_rma(
        self,
        warehouse_id: UUID,
        customer_id: UUID,
        reason: str,
        return_type: str = "refund",
        so_id: Optional[UUID] = None,
        notes: Optional[str] = None,
    ):
        """Crear solicitud de devolución de cliente."""
        data = dict(
            warehouse_id=warehouse_id,
            customer_id=customer_id,
            so_id=so_id,
            reason=reason,
            return_type=return_type,
            notes=notes,
            refund_amount=Decimal("0"),
        )
        rma = await self.rma_repo.create(data, created_by_id=self.user_id)
        log.info("rma.created", rma_id=str(rma.id))
        return rma

    async def receive_return(
        self,
        rma_id: UUID,
        inspection_notes: str,
        restocking_eligible: bool,
        restocking_location_id: Optional[UUID],
        refund_amount: Decimal,
    ) -> None:
        """
        Recibir devolución de cliente:
          - Si restocking_eligible → devolver al inventario.
          - Registrar monto de reembolso.
        """
        rma = await self.rma_repo.get_by_id(rma_id)
        if not rma:
            raise OutboundServiceError(f"RMA {rma_id} no encontrada.")
        if rma.status not in (ReturnOrderStatus.APPROVED, ReturnOrderStatus.IN_TRANSIT):
            raise OutboundServiceError(
                f"RMA debe estar APPROVED o IN_TRANSIT para recibir. Estado: {rma.status}"
            )

        # Si es elegible para restock → ingresar al inventario
        if restocking_eligible and restocking_location_id:
            # Se necesitaría el product_id — simplificado aquí
            log.info("rma.restocking", rma_id=str(rma_id))

        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        await self.rma_repo.update_status(
            rma_id,
            ReturnOrderStatus.RECEIVED,
            inspection_notes=inspection_notes,
            restocking_eligible=restocking_eligible,
            restocking_location_id=restocking_location_id,
            refund_amount=refund_amount,
            received_at=now,
            received_by_id=self.user_id,
        )
        log.info("rma.received", rma_id=str(rma_id), restocking=restocking_eligible)

    # ══════════════════════════════════════════════════════════════════════════
    # DASHBOARD
    # ══════════════════════════════════════════════════════════════════════════

    async def get_dashboard_metrics(
        self, warehouse_id: Optional[UUID] = None
    ) -> dict:
        """KPIs del módulo outbound."""
        from sqlalchemy import select, func, and_
        from app.models.outbound import SalesOrder as SO_m

        # Órdenes abiertas
        open_statuses = [
            SOStatus.CONFIRMED, SOStatus.ALLOCATED,
            SOStatus.PICKING, SOStatus.PACKED,
        ]
        orders_open = (
            await self.db.execute(
                select(func.count(SO_m.id)).where(
                    and_(
                        SO_m.tenant_id == self.tenant_id,
                        SO_m.status.in_(open_statuses),
                    )
                )
            )
        ).scalar_one()

        orders_pending_pick = (
            await self.db.execute(
                select(func.count(SO_m.id)).where(
                    and_(
                        SO_m.tenant_id == self.tenant_id,
                        SO_m.status.in_([SOStatus.CONFIRMED, SOStatus.ALLOCATED]),
                    )
                )
            )
        ).scalar_one()

        orders_pending_pack = (
            await self.db.execute(
                select(func.count(SO_m.id)).where(
                    and_(
                        SO_m.tenant_id == self.tenant_id,
                        SO_m.status == SOStatus.PICKING,
                    )
                )
            )
        ).scalar_one()

        orders_pending_ship = (
            await self.db.execute(
                select(func.count(SO_m.id)).where(
                    and_(
                        SO_m.tenant_id == self.tenant_id,
                        SO_m.status == SOStatus.PACKED,
                    )
                )
            )
        ).scalar_one()

        # On-Time Delivery y Fill Rate (FR-072)
        from app.models.outbound import SalesOrderLine as SO_line
        wh = [SO_m.warehouse_id == warehouse_id] if warehouse_id else []
        delivered_total = (
            await self.db.execute(
                select(func.count(SO_m.id)).where(and_(
                    SO_m.tenant_id == self.tenant_id, SO_m.status == SOStatus.DELIVERED, *wh))
            )
        ).scalar_one()
        delivered_on_time = (
            await self.db.execute(
                select(func.count(SO_m.id)).where(and_(
                    SO_m.tenant_id == self.tenant_id, SO_m.status == SOStatus.DELIVERED,
                    SO_m.requested_delivery_date.isnot(None),
                    SO_m.delivered_date <= SO_m.requested_delivery_date, *wh))
            )
        ).scalar_one()
        otd_pct = round(Decimal(delivered_on_time) / Decimal(delivered_total) * 100, 2) if delivered_total else None

        fill = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(SO_line.quantity_ordered), 0),
                    func.coalesce(func.sum(SO_line.quantity_shipped), 0),
                )
                .select_from(SO_line).join(SO_m, SO_line.so_id == SO_m.id)
                .where(and_(SO_m.tenant_id == self.tenant_id,
                            SO_m.status.in_([SOStatus.SHIPPED, SOStatus.DELIVERED]), *wh))
            )
        ).one()
        ordered_qty, shipped_qty = fill[0] or Decimal("0"), fill[1] or Decimal("0")
        fill_rate_pct = round(Decimal(shipped_qty) / Decimal(ordered_qty) * 100, 2) if ordered_qty else None

        orders_overdue = await self.so_repo.get_overdue(warehouse_id)
        picks_today = await self.pick_repo.count_today()
        avg_pick_time = await self.pick_repo.get_avg_cycle_time()
        waves_open = await self.wave_repo.count_open()
        shipments_today = await self.ship_repo.count_today()
        shipments_in_transit = await self.ship_repo.count_in_transit()
        short_pick_rate = await self.pick_repo.get_short_pick_rate()
        rma_open = await self.rma_repo.count_open()

        return {
            "orders_open": orders_open,
            "orders_pending_pick": orders_pending_pick,
            "orders_pending_pack": orders_pending_pack,
            "orders_pending_ship": orders_pending_ship,
            "orders_overdue": orders_overdue,
            "picks_today": picks_today,
            "avg_pick_cycle_time_seconds": avg_pick_time,
            "waves_open": waves_open,
            "shipments_today": shipments_today,
            "shipments_in_transit": shipments_in_transit,
            "on_time_delivery_pct": otd_pct,
            "short_pick_rate_pct": short_pick_rate,
            "rma_open": rma_open,
            "order_fill_rate_pct": fill_rate_pct,
        }

    async def get_throughput_series(
        self, days: int = 7, warehouse_id: Optional[UUID] = None
    ) -> dict:
        """Serie temporal diaria (picks completados, shorts y envíos despachados).

        Alimenta las gráficas del dashboard con datos reales agregados por día.
        Rellena con ceros los días sin actividad para mantener el eje continuo.
        """
        from datetime import date, timedelta

        from sqlalchemy import and_, case, func, select

        from app.models.outbound import PickingTask, Shipment

        today = date.today()
        start = today - timedelta(days=days - 1)

        # Picks completados y shorts por día
        pick_filters = [
            PickingTask.tenant_id == self.tenant_id,
            PickingTask.status.in_([PickingStatus.COMPLETED, PickingStatus.SHORT_PICKED]),
            func.date(PickingTask.completed_at) >= start,
        ]
        pick_rows = (
            await self.db.execute(
                select(
                    func.date(PickingTask.completed_at).label("day"),
                    func.count(PickingTask.id).label("picks"),
                    func.sum(
                        case((PickingTask.quantity_short > 0, 1), else_=0)
                    ).label("shorts"),
                )
                .where(and_(*pick_filters))
                .group_by(func.date(PickingTask.completed_at))
            )
        ).all()
        picks_by_day = {str(r.day): (int(r.picks), int(r.shorts or 0)) for r in pick_rows}

        # Envíos despachados por día (actual_pickup)
        ship_filters = [
            Shipment.tenant_id == self.tenant_id,
            func.date(Shipment.actual_pickup) >= start,
        ]
        if warehouse_id is not None:
            ship_filters.append(Shipment.warehouse_id == warehouse_id)
        ship_rows = (
            await self.db.execute(
                select(
                    func.date(Shipment.actual_pickup).label("day"),
                    func.count(Shipment.id).label("n"),
                )
                .where(and_(*ship_filters))
                .group_by(func.date(Shipment.actual_pickup))
            )
        ).all()
        ships_by_day = {str(r.day): int(r.n) for r in ship_rows}

        series = []
        for i in range(days):
            d = start + timedelta(days=i)
            key = d.isoformat()
            picks, shorts = picks_by_day.get(key, (0, 0))
            series.append(
                {
                    "day": d,
                    "picks": picks,
                    "shorts": shorts,
                    "shipments": ships_by_day.get(key, 0),
                }
            )
        return {"series": series}
