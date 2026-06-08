"""
WMS Panama — Repositorios Inbound
===================================
Acceso a datos para: PurchaseOrder, ASN, GRN, QualityInspection,
PutawayTask, ReturnToVendor.

Patrón:
  - Sin lógica de negocio.
  - Queries async con SQLAlchemy 2.0.
  - Siempre filtran por tenant_id.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound import (
    ASN,
    ASNLine,
    ASNStatus,
    GoodsReceipt,
    GoodsReceiptLine,
    GRNStatus,
    POStatus,
    POStatusHistory,
    PurchaseOrder,
    PurchaseOrderLine,
    PutawayStatus,
    PutawayTask,
    QCStatus,
    QualityInspection,
    QualityInspectionLine,
    RTVStatus,
    ReturnToVendor,
    ReceivingMode,
)


# ══════════════════════════════════════════════════════════════════════════════
# PURCHASE ORDER
# ══════════════════════════════════════════════════════════════════════════════

class PurchaseOrderRepository:

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    # ── Auto-numeración ────────────────────────────────────────────────────────

    async def _next_po_number(self) -> str:
        result = await self.db.execute(
            select(func.count(PurchaseOrder.id)).where(
                PurchaseOrder.tenant_id == self.tenant_id
            )
        )
        count = result.scalar_one()
        return f"PO-{count + 1:06d}"

    # ── CRUD ──────────────────────────────────────────────────────────────────

    # Mapeo de campos del schema de línea → columnas del modelo
    _LINE_FIELD_MAP = {"unit_cost": "unit_price", "line_note": "notes"}

    def _map_line(self, ld: dict) -> dict:
        mapped: dict = {}
        for key, value in ld.items():
            mapped[self._LINE_FIELD_MAP.get(key, key)] = value
        return mapped

    async def create(
        self,
        data: dict,
        lines_data: List[dict],
        created_by_id: UUID,
    ) -> PurchaseOrder:
        po_number = data.get("po_number") or await self._next_po_number()
        po = PurchaseOrder(
            id=uuid4(),
            tenant_id=self.tenant_id,
            po_number=po_number,
            created_by_id=created_by_id,
            **{k: v for k, v in data.items() if k != "po_number" and v is not None},
        )
        self.db.add(po)
        await self.db.flush()  # obtener ID sin commit

        total = Decimal("0")
        for i, ld in enumerate(lines_data, start=1):
            mapped = self._map_line(ld)
            qty = mapped.get("quantity_ordered") or Decimal("0")
            unit_price = mapped.get("unit_price")
            line_total = (qty * unit_price) if unit_price is not None else None
            line = PurchaseOrderLine(
                id=uuid4(),
                tenant_id=self.tenant_id,
                purchase_order_id=po.id,
                line_number=i,
                quantity_pending=qty,
                line_total=line_total,
                **{k: v for k, v in mapped.items() if v is not None},
            )
            self.db.add(line)
            if line_total is not None:
                total += line_total

        po.total_amount = total
        await self.db.flush()
        return po

    async def get_by_id(self, po_id: UUID) -> Optional[PurchaseOrder]:
        from app.models.master_data import Supplier
        result = await self.db.execute(
            select(PurchaseOrder, Supplier.name.label("supplier_name"))
            .join(Supplier, PurchaseOrder.supplier_id == Supplier.id)
            .options(
                selectinload(PurchaseOrder.lines),
                selectinload(PurchaseOrder.status_history),
            )
            .where(
                and_(
                    PurchaseOrder.id == po_id,
                    PurchaseOrder.tenant_id == self.tenant_id,
                    PurchaseOrder.deleted_at.is_(None),
                )
            )
        )
        row = result.first()
        if not row:
            return None
            
        po = row.PurchaseOrder
        po.supplier_name = row.supplier_name
        return po

    async def list(
        self,
        warehouse_id: Optional[UUID] = None,
        supplier_id: Optional[UUID] = None,
        status: Optional[POStatus] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List[PurchaseOrder], int]:
        filters = [
            PurchaseOrder.tenant_id == self.tenant_id,
            PurchaseOrder.deleted_at.is_(None),
        ]

        if warehouse_id:
            filters.append(PurchaseOrder.warehouse_id == warehouse_id)
        if supplier_id:
            filters.append(PurchaseOrder.supplier_id == supplier_id)
        if status:
            filters.append(PurchaseOrder.status == status)
        if date_from:
            filters.append(PurchaseOrder.order_date >= date_from)
        if date_to:
            filters.append(PurchaseOrder.order_date <= date_to)
        if search:
            term = f"%{search}%"
            filters.append(
                or_(
                    PurchaseOrder.po_number.ilike(term),
                    PurchaseOrder.supplier_po_reference.ilike(term),
                )
            )

        count_q = select(func.count(PurchaseOrder.id)).where(and_(*filters))
        total = (await self.db.execute(count_q)).scalar_one()

        from app.models.master_data import Supplier
        q = (
            select(
                PurchaseOrder,
                Supplier.name.label("supplier_name")
            )
            .join(Supplier, PurchaseOrder.supplier_id == Supplier.id)
            .options(
                selectinload(PurchaseOrder.lines),
                selectinload(PurchaseOrder.status_history),
            )
            .where(and_(*filters))
            .order_by(PurchaseOrder.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.db.execute(q)).all()
        
        items = []
        for row in rows:
            po = row.PurchaseOrder
            po.supplier_name = row.supplier_name
            items.append(po)
            
        return items, total

    async def update_fields(self, po_id: UUID, fields: dict) -> None:
        """Actualiza campos de cabecera de una OC (edición)."""
        if not fields:
            return
        await self.db.execute(
            update(PurchaseOrder)
            .where(
                and_(
                    PurchaseOrder.id == po_id,
                    PurchaseOrder.tenant_id == self.tenant_id,
                    PurchaseOrder.deleted_at.is_(None),
                )
            )
            .values(updated_at=datetime.now(timezone.utc), **fields)
        )

    async def soft_delete(self, po_id: UUID, deleted_by: UUID) -> None:
        """Eliminación lógica: marca deleted_at sin borrar físicamente."""
        await self.db.execute(
            update(PurchaseOrder)
            .where(
                and_(
                    PurchaseOrder.id == po_id,
                    PurchaseOrder.tenant_id == self.tenant_id,
                )
            )
            .values(
                deleted_at=datetime.now(timezone.utc),
                deleted_by=deleted_by,
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def add_status_history(
        self,
        po_id: UUID,
        from_status: Optional[str],
        to_status: str,
        changed_by_id: Optional[UUID],
        reason: Optional[str] = None,
    ) -> None:
        """Registra una transición de estado en el historial de la OC."""
        self.db.add(
            POStatusHistory(
                id=uuid4(),
                tenant_id=self.tenant_id,
                purchase_order_id=po_id,
                from_status=from_status,
                to_status=to_status,
                changed_by_id=changed_by_id,
                reason=reason,
            )
        )
        await self.db.flush()

    async def update_status(self, po_id: UUID, status: POStatus) -> None:
        extra: dict = {}
        if status == POStatus.CONFIRMED:
            extra["confirmed_date"] = datetime.now(timezone.utc)
        if status in (POStatus.CLOSED, POStatus.CANCELLED):
            extra["closed_date"] = datetime.now(timezone.utc)

        await self.db.execute(
            update(PurchaseOrder)
            .where(
                and_(
                    PurchaseOrder.id == po_id,
                    PurchaseOrder.tenant_id == self.tenant_id,
                )
            )
            .values(status=status, updated_at=datetime.now(timezone.utc), **extra)
        )

    async def update_line_received(
        self,
        line_id: UUID,
        qty_received_delta: Decimal,
        qty_rejected_delta: Decimal,
    ) -> None:
        """Actualiza cantidades recibidas/rechazadas de forma atómica."""
        await self.db.execute(
            update(PurchaseOrderLine)
            .where(
                and_(
                    PurchaseOrderLine.id == line_id,
                    PurchaseOrderLine.tenant_id == self.tenant_id,
                )
            )
            .values(
                quantity_received=PurchaseOrderLine.quantity_received + qty_received_delta,
                quantity_rejected=PurchaseOrderLine.quantity_rejected + qty_rejected_delta,
                quantity_pending=PurchaseOrderLine.quantity_pending
                - qty_received_delta
                - qty_rejected_delta,
                updated_at=datetime.now(timezone.utc),
            )
        )


# ══════════════════════════════════════════════════════════════════════════════
# ASN
# ══════════════════════════════════════════════════════════════════════════════

class ASNRepository:

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def _next_asn_number(self) -> str:
        result = await self.db.execute(
            select(func.count(ASN.id)).where(ASN.tenant_id == self.tenant_id)
        )
        count = result.scalar_one()
        return f"ASN-{count + 1:06d}"

    async def create(
        self,
        data: dict,
        lines_data: List[dict],
        created_by_id: UUID,
    ) -> ASN:
        asn_number = data.get("asn_number") or await self._next_asn_number()
        asn = ASN(
            id=uuid4(),
            tenant_id=self.tenant_id,
            asn_number=asn_number,
            created_by_id=created_by_id,
            **{k: v for k, v in data.items() if k != "asn_number"},
        )
        self.db.add(asn)
        await self.db.flush()

        for i, ld in enumerate(lines_data, start=1):
            line = ASNLine(
                id=uuid4(),
                tenant_id=self.tenant_id,
                asn_id=asn.id,
                line_number=i,
                **ld,
            )
            self.db.add(line)

        await self.db.flush()
        return asn

    async def get_by_id(self, asn_id: UUID) -> Optional[ASN]:
        result = await self.db.execute(
            select(ASN)
            .options(selectinload(ASN.lines))
            .where(
                and_(
                    ASN.id == asn_id,
                    ASN.tenant_id == self.tenant_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        warehouse_id: Optional[UUID] = None,
        status: Optional[ASNStatus] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List[ASN], int]:
        filters = [ASN.tenant_id == self.tenant_id]
        if warehouse_id:
            filters.append(ASN.warehouse_id == warehouse_id)
        if status:
            filters.append(ASN.status == status)

        total = (
            await self.db.execute(
                select(func.count(ASN.id)).where(and_(*filters))
            )
        ).scalar_one()

        rows = (
            await self.db.execute(
                select(ASN)
                .options(selectinload(ASN.lines))
                .where(and_(*filters))
                .order_by(ASN.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

        return list(rows), total

    async def update_status(
        self,
        asn_id: UUID,
        status: ASNStatus,
        dock_number: Optional[str] = None,
    ) -> None:
        values: dict = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if status == ASNStatus.IN_TRANSIT:
            values["actual_arrival_date"] = None
        if status == ASNStatus.ARRIVED:
            values["actual_arrival_date"] = datetime.now(timezone.utc)
        if dock_number:
            values["dock_number"] = dock_number

        await self.db.execute(
            update(ASN)
            .where(and_(ASN.id == asn_id, ASN.tenant_id == self.tenant_id))
            .values(**values)
        )


# ══════════════════════════════════════════════════════════════════════════════
# GRN
# ══════════════════════════════════════════════════════════════════════════════

class GRNRepository:

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def _next_grn_number(self) -> str:
        result = await self.db.execute(
            select(func.count(GoodsReceipt.id)).where(
                GoodsReceipt.tenant_id == self.tenant_id
            )
        )
        count = result.scalar_one()
        return f"GRN-{count + 1:06d}"

    # Mapeo de campos del schema/servicio → columnas del modelo
    _HEADER_FIELD_MAP = {"po_id": "purchase_order_id"}

    async def create(
        self,
        data: dict,
        lines_data: List[dict],
        received_by_id: UUID,
    ) -> GoodsReceipt:
        grn_number = await self._next_grn_number()
        header = {
            self._HEADER_FIELD_MAP.get(k, k): v
            for k, v in data.items()
            if v is not None
        }
        grn = GoodsReceipt(
            id=uuid4(),
            tenant_id=self.tenant_id,
            grn_number=grn_number,
            received_by=received_by_id,
            received_at=datetime.now(timezone.utc),
            **header,
        )
        self.db.add(grn)
        await self.db.flush()

        for i, ld in enumerate(lines_data, start=1):
            line = GoodsReceiptLine(
                id=uuid4(),
                tenant_id=self.tenant_id,
                grn_id=grn.id,
                line_number=i,
                **{k: v for k, v in ld.items() if v is not None},
            )
            self.db.add(line)

        await self.db.flush()
        return grn

    async def get_by_id(self, grn_id: UUID) -> Optional[GoodsReceipt]:
        result = await self.db.execute(
            select(GoodsReceipt)
            .options(selectinload(GoodsReceipt.lines))
            .where(
                and_(
                    GoodsReceipt.id == grn_id,
                    GoodsReceipt.tenant_id == self.tenant_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        warehouse_id: Optional[UUID] = None,
        status: Optional[GRNStatus] = None,
        requires_qc: Optional[bool] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List[GoodsReceipt], int]:
        filters = [GoodsReceipt.tenant_id == self.tenant_id]
        if warehouse_id:
            filters.append(GoodsReceipt.warehouse_id == warehouse_id)
        if status:
            filters.append(GoodsReceipt.status == status)
        if requires_qc is not None:
            filters.append(GoodsReceipt.requires_qc == requires_qc)
        if date_from:
            filters.append(func.date(GoodsReceipt.received_at) >= date_from)
        if date_to:
            filters.append(func.date(GoodsReceipt.received_at) <= date_to)

        total = (
            await self.db.execute(
                select(func.count(GoodsReceipt.id)).where(and_(*filters))
            )
        ).scalar_one()

        rows = (
            await self.db.execute(
                select(GoodsReceipt)
                .options(selectinload(GoodsReceipt.lines))
                .where(and_(*filters))
                .order_by(GoodsReceipt.received_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

        return list(rows), total

    async def update_status(self, grn_id: UUID, status: GRNStatus) -> None:
        values: dict = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if status == GRNStatus.CONFIRMED:
            values["confirmed_at"] = datetime.now(timezone.utc)
        await self.db.execute(
            update(GoodsReceipt)
            .where(
                and_(
                    GoodsReceipt.id == grn_id,
                    GoodsReceipt.tenant_id == self.tenant_id,
                )
            )
            .values(**values)
        )

    async def get_lines_pending_putaway(
        self, grn_id: UUID
    ) -> List[GoodsReceiptLine]:
        result = await self.db.execute(
            select(GoodsReceiptLine).where(
                and_(
                    GoodsReceiptLine.grn_id == grn_id,
                    GoodsReceiptLine.tenant_id == self.tenant_id,
                    GoodsReceiptLine.status == "approved",
                )
            )
        )
        return list(result.scalars().all())


# ══════════════════════════════════════════════════════════════════════════════
# QUALITY INSPECTION
# ══════════════════════════════════════════════════════════════════════════════

class QualityInspectionRepository:

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def _next_qi_number(self) -> str:
        result = await self.db.execute(
            select(func.count(QualityInspection.id)).where(
                QualityInspection.tenant_id == self.tenant_id
            )
        )
        count = result.scalar_one()
        return f"QI-{count + 1:06d}"

    async def create(
        self,
        grn_id: UUID,
        data: dict,
        lines_data: List[dict],
        created_by_id: UUID,
    ) -> QualityInspection:
        qi_number = await self._next_qi_number()
        qi = QualityInspection(
            id=uuid4(),
            tenant_id=self.tenant_id,
            grn_id=grn_id,
            qi_number=qi_number,
            created_by_id=created_by_id,
            status=QCStatus.PENDING,
            **data,
        )
        self.db.add(qi)
        await self.db.flush()

        total_inspected = Decimal("0")
        total_approved = Decimal("0")
        total_rejected = Decimal("0")

        for i, ld in enumerate(lines_data, start=1):
            line = QualityInspectionLine(
                id=uuid4(),
                tenant_id=self.tenant_id,
                qi_id=qi.id,
                line_number=i,
                **ld,
            )
            self.db.add(line)
            total_inspected += ld["quantity_inspected"]
            total_approved += ld["quantity_approved"]
            total_rejected += ld["quantity_rejected"]

        qi.total_inspected = total_inspected
        qi.total_approved = total_approved
        qi.total_rejected = total_rejected
        qi.defect_rate = (
            total_rejected / total_inspected if total_inspected > 0 else Decimal("0")
        )
        await self.db.flush()
        return qi

    async def get_by_id(self, qi_id: UUID) -> Optional[QualityInspection]:
        result = await self.db.execute(
            select(QualityInspection)
            .options(selectinload(QualityInspection.lines))
            .where(
                and_(
                    QualityInspection.id == qi_id,
                    QualityInspection.tenant_id == self.tenant_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_grn(self, grn_id: UUID) -> Optional[QualityInspection]:
        result = await self.db.execute(
            select(QualityInspection)
            .options(selectinload(QualityInspection.lines))
            .where(
                and_(
                    QualityInspection.grn_id == grn_id,
                    QualityInspection.tenant_id == self.tenant_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def resolve(
        self,
        qi_id: UUID,
        approved: bool,
        disposition: str,
        disposition_notes: Optional[str],
        inspector_id: UUID,
    ) -> None:
        status = QCStatus.APPROVED if approved else QCStatus.REJECTED
        await self.db.execute(
            update(QualityInspection)
            .where(
                and_(
                    QualityInspection.id == qi_id,
                    QualityInspection.tenant_id == self.tenant_id,
                )
            )
            .values(
                status=status,
                disposition=disposition,
                disposition_notes=disposition_notes,
                inspector_id=inspector_id,
                completed_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def list(
        self, warehouse_id: Optional[UUID] = None, status: Optional[str] = None, page: int = 1, page_size: int = 50
    ) -> tuple[List[QualityInspection], int]:
        filters = [QualityInspection.tenant_id == self.tenant_id]
        if warehouse_id:
            filters.append(QualityInspection.warehouse_id == warehouse_id)
        if status:
            filters.append(QualityInspection.status == status)

        total = (
            await self.db.execute(
                select(func.count(QualityInspection.id)).where(and_(*filters))
            )
        ).scalar_one()
        rows = (
            await self.db.execute(
                select(QualityInspection)
                .where(and_(*filters))
                .order_by(QualityInspection.created_at.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return list(rows), total


# ══════════════════════════════════════════════════════════════════════════════
# PUTAWAY TASK
# ══════════════════════════════════════════════════════════════════════════════

class PutawayTaskRepository:

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def create(self, data: dict) -> PutawayTask:
        task = PutawayTask(
            id=uuid4(),
            tenant_id=self.tenant_id,
            status=PutawayStatus.PENDING,
            **data,
        )
        self.db.add(task)
        await self.db.flush()
        return task

    async def create_bulk(self, tasks_data: List[dict]) -> List[PutawayTask]:
        tasks = []
        for td in tasks_data:
            task = PutawayTask(
                id=uuid4(),
                tenant_id=self.tenant_id,
                status=PutawayStatus.PENDING,
                **td,
            )
            self.db.add(task)
            tasks.append(task)
        await self.db.flush()
        return tasks

    async def get_by_id(self, task_id: UUID) -> Optional[PutawayTask]:
        result = await self.db.execute(
            select(PutawayTask).where(
                and_(
                    PutawayTask.id == task_id,
                    PutawayTask.tenant_id == self.tenant_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        status: Optional[PutawayStatus] = None,
        assigned_to_id: Optional[UUID] = None,
        warehouse_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List[PutawayTask], int]:
        filters = [PutawayTask.tenant_id == self.tenant_id]
        if status:
            filters.append(PutawayTask.status == status)
        if assigned_to_id:
            filters.append(PutawayTask.assigned_to_id == assigned_to_id)

        from app.models.master_data import Product, Location
        from sqlalchemy.orm import aliased
        
        LocFrom = aliased(Location)
        LocSug = aliased(Location)
        LocAct = aliased(Location)

        total = (
            await self.db.execute(
                select(func.count(PutawayTask.id)).where(and_(*filters))
            )
        ).scalar_one()
        result = (
            await self.db.execute(
                select(
                    PutawayTask,
                    Product.name.label("product_name"),
                    LocFrom.code.label("from_location_code"),
                    LocSug.code.label("suggested_location_code"),
                    LocAct.code.label("actual_location_code"),
                )
                .join(Product, PutawayTask.product_id == Product.id)
                .outerjoin(LocFrom, PutawayTask.from_location_id == LocFrom.id)
                .outerjoin(LocSug, PutawayTask.suggested_location_id == LocSug.id)
                .outerjoin(LocAct, PutawayTask.actual_location_id == LocAct.id)
                .where(and_(*filters))
                .order_by(PutawayTask.priority.desc(), PutawayTask.created_at.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        
        tasks = []
        for row in result:
            task = row.PutawayTask
            task.product_name = row.product_name
            task.from_location_code = row.from_location_code
            task.suggested_location_code = row.suggested_location_code
            task.actual_location_code = row.actual_location_code
            tasks.append(task)
            
        return tasks, total

    async def start_task(self, task_id: UUID, operator_id: UUID) -> None:
        await self.db.execute(
            update(PutawayTask)
            .where(
                and_(
                    PutawayTask.id == task_id,
                    PutawayTask.tenant_id == self.tenant_id,
                )
            )
            .values(
                status=PutawayStatus.IN_PROGRESS,
                assigned_to_id=operator_id,
                started_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def complete_task(
        self,
        task_id: UUID,
        actual_location_id: UUID,
        override_reason: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        task = await self.get_by_id(task_id)
        cycle_time = None
        if task and task.started_at:
            cycle_time = int((now - task.started_at).total_seconds())

        await self.db.execute(
            update(PutawayTask)
            .where(
                and_(
                    PutawayTask.id == task_id,
                    PutawayTask.tenant_id == self.tenant_id,
                )
            )
            .values(
                status=PutawayStatus.COMPLETED,
                actual_location_id=actual_location_id,
                override_reason=override_reason,
                completed_at=now,
                cycle_time_seconds=cycle_time,
                updated_at=now,
            )
        )

    async def get_open_count(self) -> int:
        result = await self.db.execute(
            select(func.count(PutawayTask.id)).where(
                and_(
                    PutawayTask.tenant_id == self.tenant_id,
                    PutawayTask.status.in_([PutawayStatus.PENDING, PutawayStatus.IN_PROGRESS]),
                )
            )
        )
        return result.scalar_one()

    async def get_avg_cycle_time(self) -> Optional[int]:
        result = await self.db.execute(
            select(func.avg(PutawayTask.cycle_time_seconds)).where(
                and_(
                    PutawayTask.tenant_id == self.tenant_id,
                    PutawayTask.status == PutawayStatus.COMPLETED,
                    PutawayTask.cycle_time_seconds.isnot(None),
                )
            )
        )
        val = result.scalar_one_or_none()
        return int(val) if val is not None else None


# ══════════════════════════════════════════════════════════════════════════════
# RETURN TO VENDOR
# ══════════════════════════════════════════════════════════════════════════════

class RTVRepository:

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def _next_rtv_number(self) -> str:
        result = await self.db.execute(
            select(func.count(ReturnToVendor.id)).where(
                ReturnToVendor.tenant_id == self.tenant_id
            )
        )
        count = result.scalar_one()
        return f"RTV-{count + 1:06d}"

    async def create(self, data: dict, created_by_id: UUID) -> ReturnToVendor:
        rtv_number = await self._next_rtv_number()
        rtv = ReturnToVendor(
            id=uuid4(),
            tenant_id=self.tenant_id,
            rtv_number=rtv_number,
            created_by_id=created_by_id,
            status=RTVStatus.PENDING,
            credit_received=Decimal("0"),
            **data,
        )
        self.db.add(rtv)
        await self.db.flush()
        return rtv

    async def get_by_id(self, rtv_id: UUID) -> Optional[ReturnToVendor]:
        result = await self.db.execute(
            select(ReturnToVendor).where(
                and_(
                    ReturnToVendor.id == rtv_id,
                    ReturnToVendor.tenant_id == self.tenant_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        supplier_id: Optional[UUID] = None,
        status: Optional[RTVStatus] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List[ReturnToVendor], int]:
        filters = [ReturnToVendor.tenant_id == self.tenant_id]
        if supplier_id:
            filters.append(ReturnToVendor.supplier_id == supplier_id)
        if status:
            filters.append(ReturnToVendor.status == status)

        total = (
            await self.db.execute(
                select(func.count(ReturnToVendor.id)).where(and_(*filters))
            )
        ).scalar_one()
        rows = (
            await self.db.execute(
                select(ReturnToVendor)
                .where(and_(*filters))
                .order_by(ReturnToVendor.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return list(rows), total

    async def update_status(
        self,
        rtv_id: UUID,
        status: RTVStatus,
        credit_memo_number: Optional[str] = None,
        credit_received: Optional[Decimal] = None,
    ) -> None:
        values: dict = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if status == RTVStatus.SHIPPED:
            values["shipped_at"] = datetime.now(timezone.utc)
        if status == RTVStatus.CREDIT_RECEIVED:
            values["confirmed_at"] = datetime.now(timezone.utc)
        if credit_memo_number:
            values["credit_memo_number"] = credit_memo_number
        if credit_received is not None:
            values["credit_received"] = credit_received

        await self.db.execute(
            update(ReturnToVendor)
            .where(
                and_(
                    ReturnToVendor.id == rtv_id,
                    ReturnToVendor.tenant_id == self.tenant_id,
                )
            )
            .values(**values)
        )
