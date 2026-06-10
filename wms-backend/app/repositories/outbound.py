"""
WMS Panama — Repositorios Outbound
=====================================
Acceso a datos para: SalesOrder, PickingWave, PickingTask,
PackTask, Shipment, ReturnOrder.

Patrón: sin lógica de negocio, queries async SQLAlchemy 2.0,
siempre filtra por tenant_id.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.outbound import (
    PackStatus,
    PackTask,
    PickingStatus,
    PickingTask,
    PickingWave,
    ReturnOrder,
    ReturnOrderStatus,
    SOLineStatus,
    SOStatus,
    SalesOrder,
    SalesOrderLine,
    ShipmentStatus,
    Shipment,
    WaveStatus,
)


# ══════════════════════════════════════════════════════════════════════════════
# SALES ORDER
# ══════════════════════════════════════════════════════════════════════════════

class SalesOrderRepository:

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def _next_so_number(self) -> str:
        result = await self.db.execute(
            select(func.count(SalesOrder.id)).where(
                SalesOrder.tenant_id == self.tenant_id
            )
        )
        return f"SO-{result.scalar_one() + 1:06d}"

    async def create(
        self,
        data: dict,
        lines_data: List[dict],
        created_by_id: UUID,
    ) -> SalesOrder:
        so_number = data.pop("so_number", None) or await self._next_so_number()
        so = SalesOrder(
            id=uuid4(),
            tenant_id=self.tenant_id,
            so_number=so_number,
            created_by_id=created_by_id,
            status=SOStatus.DRAFT,
            **data,
        )
        self.db.add(so)
        await self.db.flush()

        subtotal = Decimal("0")
        for i, ld in enumerate(lines_data, start=1):
            qty = ld["quantity_ordered"]
            price = ld.get("unit_price", Decimal("0"))
            disc = ld.get("discount_pct", Decimal("0"))
            line_total = qty * price * (1 - disc)
            line = SalesOrderLine(
                id=uuid4(),
                tenant_id=self.tenant_id,
                so_id=so.id,
                line_number=i,
                line_total=line_total,
                **ld,
            )
            self.db.add(line)
            subtotal += line_total

        so.subtotal = subtotal
        so.total_amount = subtotal  # tax se puede calcular después
        await self.db.flush()
        return so

    async def get_by_id(self, so_id: UUID) -> Optional[SalesOrder]:
        result = await self.db.execute(
            select(SalesOrder)
            .options(selectinload(SalesOrder.lines))
            .where(
                and_(
                    SalesOrder.id == so_id,
                    SalesOrder.tenant_id == self.tenant_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        warehouse_id: Optional[UUID] = None,
        customer_id: Optional[UUID] = None,
        status: Optional[SOStatus] = None,
        priority: Optional[int] = None,
        search: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List[SalesOrder], int]:
        filters = [SalesOrder.tenant_id == self.tenant_id]
        if warehouse_id:
            filters.append(SalesOrder.warehouse_id == warehouse_id)
        if customer_id:
            filters.append(SalesOrder.customer_id == customer_id)
        if status:
            filters.append(SalesOrder.status == status)
        if priority is not None:
            filters.append(SalesOrder.priority <= priority)
        if search:
            t = f"%{search}%"
            filters.append(
                or_(
                    SalesOrder.so_number.ilike(t),
                    SalesOrder.customer_po_reference.ilike(t),
                )
            )
        if date_from:
            filters.append(func.date(SalesOrder.order_date) >= date_from)
        if date_to:
            filters.append(func.date(SalesOrder.order_date) <= date_to)

        total = (
            await self.db.execute(
                select(func.count(SalesOrder.id)).where(and_(*filters))
            )
        ).scalar_one()

        rows = (
            await self.db.execute(
                select(SalesOrder)
                .options(selectinload(SalesOrder.lines))
                .where(and_(*filters))
                .order_by(SalesOrder.priority.asc(), SalesOrder.order_date.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

        return list(rows), total

    async def update_status(self, so_id: UUID, status: SOStatus, **extra) -> None:
        now = datetime.now(timezone.utc)
        values = {"status": status, "updated_at": now, **extra}
        if status == SOStatus.CONFIRMED:
            values.setdefault("confirmed_date", now)
        if status == SOStatus.SHIPPED:
            values.setdefault("shipped_date", now)
        if status == SOStatus.DELIVERED:
            values.setdefault("delivered_date", now)
        if status == SOStatus.CANCELLED:
            values.setdefault("cancelled_date", now)

        await self.db.execute(
            update(SalesOrder)
            .where(and_(SalesOrder.id == so_id, SalesOrder.tenant_id == self.tenant_id))
            .values(**values)
        )

    async def update_line_quantities(
        self,
        line_id: UUID,
        field: str,
        delta: Decimal,
    ) -> None:
        """Actualiza atómicamente un campo de cantidad en la línea."""
        col = getattr(SalesOrderLine, field)
        await self.db.execute(
            update(SalesOrderLine)
            .where(
                and_(
                    SalesOrderLine.id == line_id,
                    SalesOrderLine.tenant_id == self.tenant_id,
                )
            )
            .values(**{field: col + delta, "updated_at": datetime.now(timezone.utc)})
        )

    async def get_overdue(self, warehouse_id: Optional[UUID] = None) -> int:
        filters = [
            SalesOrder.tenant_id == self.tenant_id,
            SalesOrder.status.in_([SOStatus.CONFIRMED, SOStatus.ALLOCATED,
                                    SOStatus.PICKING, SOStatus.PACKED]),
            SalesOrder.requested_delivery_date < datetime.now(timezone.utc),
        ]
        if warehouse_id:
            filters.append(SalesOrder.warehouse_id == warehouse_id)
        return (
            await self.db.execute(
                select(func.count(SalesOrder.id)).where(and_(*filters))
            )
        ).scalar_one()


# ══════════════════════════════════════════════════════════════════════════════
# PICKING WAVE
# ══════════════════════════════════════════════════════════════════════════════

class PickingWaveRepository:

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def _next_wave_number(self) -> str:
        result = await self.db.execute(
            select(func.count(PickingWave.id)).where(
                PickingWave.tenant_id == self.tenant_id
            )
        )
        return f"WAVE-{result.scalar_one() + 1:05d}"

    async def create(self, data: dict, created_by_id: UUID) -> PickingWave:
        wave_number = await self._next_wave_number()
        wave = PickingWave(
            id=uuid4(),
            tenant_id=self.tenant_id,
            wave_number=wave_number,
            created_by_id=created_by_id,
            **data,
        )
        self.db.add(wave)
        await self.db.flush()
        return wave

    async def get_by_id(self, wave_id: UUID) -> Optional[PickingWave]:
        result = await self.db.execute(
            select(PickingWave).where(
                and_(
                    PickingWave.id == wave_id,
                    PickingWave.tenant_id == self.tenant_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        status: Optional[WaveStatus] = None,
        warehouse_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List[PickingWave], int]:
        filters = [PickingWave.tenant_id == self.tenant_id]
        if status:
            filters.append(PickingWave.status == status)
        if warehouse_id:
            filters.append(PickingWave.warehouse_id == warehouse_id)

        total = (
            await self.db.execute(
                select(func.count(PickingWave.id)).where(and_(*filters))
            )
        ).scalar_one()
        rows = (
            await self.db.execute(
                select(PickingWave)
                .where(and_(*filters))
                .order_by(PickingWave.priority.asc(), PickingWave.created_at.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return list(rows), total

    async def release(self, wave_id: UUID) -> None:
        await self.db.execute(
            update(PickingWave)
            .where(and_(PickingWave.id == wave_id, PickingWave.tenant_id == self.tenant_id))
            .values(
                status=WaveStatus.RELEASED,
                released_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def update_status(self, wave_id: UUID, status: WaveStatus) -> None:
        values = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if status == WaveStatus.COMPLETED:
            values["completed_at"] = datetime.now(timezone.utc)
        await self.db.execute(
            update(PickingWave)
            .where(and_(PickingWave.id == wave_id, PickingWave.tenant_id == self.tenant_id))
            .values(**values)
        )

    async def count_open(self) -> int:
        result = await self.db.execute(
            select(func.count(PickingWave.id)).where(
                and_(
                    PickingWave.tenant_id == self.tenant_id,
                    PickingWave.status.in_([WaveStatus.OPEN, WaveStatus.RELEASED,
                                            WaveStatus.IN_PROGRESS]),
                )
            )
        )
        return result.scalar_one()


# ══════════════════════════════════════════════════════════════════════════════
# PICKING TASK
# ══════════════════════════════════════════════════════════════════════════════

class PickingTaskRepository:

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def create_bulk(self, tasks_data: List[dict]) -> List[PickingTask]:
        tasks = []
        for td in tasks_data:
            task = PickingTask(
                id=uuid4(),
                tenant_id=self.tenant_id,
                status=PickingStatus.PENDING,
                **td,
            )
            self.db.add(task)
            tasks.append(task)
        await self.db.flush()
        return tasks

    async def get_by_id(self, task_id: UUID) -> Optional[PickingTask]:
        result = await self.db.execute(
            select(PickingTask).where(
                and_(
                    PickingTask.id == task_id,
                    PickingTask.tenant_id == self.tenant_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        wave_id: Optional[UUID] = None,
        so_id: Optional[UUID] = None,
        status: Optional[PickingStatus] = None,
        assigned_to_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[List[PickingTask], int]:
        filters = [PickingTask.tenant_id == self.tenant_id]
        if wave_id:
            filters.append(PickingTask.wave_id == wave_id)
        if so_id:
            filters.append(PickingTask.so_id == so_id)
        if status:
            filters.append(PickingTask.status == status)
        if assigned_to_id:
            filters.append(PickingTask.assigned_to_id == assigned_to_id)

        from app.models.master_data import Product, Location
        from app.models.core import User
        from sqlalchemy.orm import aliased
        
        LocFrom = aliased(Location)
        LocTo = aliased(Location)

        total = (
            await self.db.execute(
                select(func.count(PickingTask.id)).where(and_(*filters))
            )
        ).scalar_one()
        
        result = (
            await self.db.execute(
                select(
                    PickingTask,
                    Product.name.label("product_name"),
                    LocFrom.code.label("from_location_code"),
                    LocTo.code.label("to_location_code"),
                    User.full_name.label("assigned_to_name")
                )
                .join(Product, PickingTask.product_id == Product.id)
                .outerjoin(LocFrom, PickingTask.from_location_id == LocFrom.id)
                .outerjoin(LocTo, PickingTask.to_location_id == LocTo.id)
                .outerjoin(User, PickingTask.assigned_to_id == User.id)
                .where(and_(*filters))
                .order_by(PickingTask.priority.asc(), PickingTask.created_at.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        
        tasks = []
        for row in result:
            task = row.PickingTask
            task.product_name = row.product_name
            task.from_location_code = row.from_location_code
            task.to_location_code = row.to_location_code
            task.assigned_to_name = row.assigned_to_name
            tasks.append(task)
            
        return tasks, total

    async def start(self, task_id: UUID, operator_id: UUID) -> None:
        await self.db.execute(
            update(PickingTask)
            .where(and_(PickingTask.id == task_id, PickingTask.tenant_id == self.tenant_id))
            .values(
                status=PickingStatus.IN_PROGRESS,
                assigned_to_id=operator_id,
                started_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def complete(
        self,
        task_id: UUID,
        quantity_picked: Decimal,
        quantity_short: Decimal,
        sscc_scanned: Optional[str] = None,
        gtin_scanned: Optional[str] = None,
        short_reason: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        task = await self.get_by_id(task_id)
        cycle_time = int((now - task.started_at).total_seconds()) if task and task.started_at else None
        status = PickingStatus.SHORT_PICKED if quantity_short > 0 else PickingStatus.COMPLETED

        await self.db.execute(
            update(PickingTask)
            .where(and_(PickingTask.id == task_id, PickingTask.tenant_id == self.tenant_id))
            .values(
                status=status,
                quantity_picked=quantity_picked,
                quantity_short=quantity_short,
                sscc_scanned=sscc_scanned,
                gtin_scanned=gtin_scanned,
                short_reason=short_reason,
                notes=notes,
                completed_at=now,
                cycle_time_seconds=cycle_time,
                updated_at=now,
            )
        )

    async def count_pending_for_so(self, so_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(PickingTask.id)).where(
                and_(
                    PickingTask.so_id == so_id,
                    PickingTask.tenant_id == self.tenant_id,
                    PickingTask.status.in_([PickingStatus.PENDING, PickingStatus.IN_PROGRESS]),
                )
            )
        )
        return result.scalar_one()

    async def get_avg_cycle_time(self) -> Optional[int]:
        result = await self.db.execute(
            select(func.avg(PickingTask.cycle_time_seconds)).where(
                and_(
                    PickingTask.tenant_id == self.tenant_id,
                    PickingTask.status.in_([PickingStatus.COMPLETED, PickingStatus.SHORT_PICKED]),
                    PickingTask.cycle_time_seconds.isnot(None),
                )
            )
        )
        val = result.scalar_one_or_none()
        return int(val) if val is not None else None

    async def count_today(self) -> int:
        today = date.today()
        result = await self.db.execute(
            select(func.count(PickingTask.id)).where(
                and_(
                    PickingTask.tenant_id == self.tenant_id,
                    PickingTask.status.in_([PickingStatus.COMPLETED, PickingStatus.SHORT_PICKED]),
                    func.date(PickingTask.completed_at) == today,
                )
            )
        )
        return result.scalar_one()

    async def get_short_pick_rate(self) -> Optional[Decimal]:
        """Tasa de short picks = short_picks / total_completed."""
        total = (
            await self.db.execute(
                select(func.count(PickingTask.id)).where(
                    and_(
                        PickingTask.tenant_id == self.tenant_id,
                        PickingTask.status.in_([PickingStatus.COMPLETED,
                                                PickingStatus.SHORT_PICKED]),
                    )
                )
            )
        ).scalar_one()

        if total == 0:
            return None

        shorts = (
            await self.db.execute(
                select(func.count(PickingTask.id)).where(
                    and_(
                        PickingTask.tenant_id == self.tenant_id,
                        PickingTask.status == PickingStatus.SHORT_PICKED,
                    )
                )
            )
        ).scalar_one()

        return round(Decimal(shorts) / Decimal(total) * 100, 2)


# ══════════════════════════════════════════════════════════════════════════════
# PACK TASK
# ══════════════════════════════════════════════════════════════════════════════

class PackTaskRepository:

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def _next_number(self) -> str:
        result = await self.db.execute(
            select(func.count(PackTask.id)).where(PackTask.tenant_id == self.tenant_id)
        )
        return f"PACK-{result.scalar_one() + 1:06d}"

    async def create(self, so_id: UUID, created_by_id: UUID) -> PackTask:
        task = PackTask(
            id=uuid4(),
            tenant_id=self.tenant_id,
            so_id=so_id,
            pack_task_number=await self._next_number(),
            status=PackStatus.PENDING,
            created_by_id=created_by_id,
        )
        self.db.add(task)
        await self.db.flush()
        return task

    async def get_by_id(self, task_id: UUID) -> Optional[PackTask]:
        result = await self.db.execute(
            select(PackTask).where(
                and_(PackTask.id == task_id, PackTask.tenant_id == self.tenant_id)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_so(self, so_id: UUID) -> Optional[PackTask]:
        result = await self.db.execute(
            select(PackTask).where(
                and_(PackTask.so_id == so_id, PackTask.tenant_id == self.tenant_id)
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        status: Optional[PackStatus] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List[PackTask], int]:
        filters = [PackTask.tenant_id == self.tenant_id]
        if status:
            filters.append(PackTask.status == status)

        from app.models.core import User
        
        total = (
            await self.db.execute(
                select(func.count(PackTask.id)).where(and_(*filters))
            )
        ).scalar_one()
        
        result = (
            await self.db.execute(
                select(
                    PackTask,
                    SalesOrder.so_number.label("so_number"),
                    User.full_name.label("assigned_to_name")
                )
                .join(SalesOrder, PackTask.so_id == SalesOrder.id)
                .outerjoin(User, PackTask.assigned_to_id == User.id)
                .where(and_(*filters))
                .order_by(PackTask.created_at.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        
        tasks = []
        for row in result:
            task = row.PackTask
            task.so_number = row.so_number
            task.assigned_to_name = row.assigned_to_name
            tasks.append(task)
            
        return tasks, total

    async def start(self, task_id: UUID, operator_id: UUID) -> None:
        await self.db.execute(
            update(PackTask)
            .where(and_(PackTask.id == task_id, PackTask.tenant_id == self.tenant_id))
            .values(
                status=PackStatus.IN_PROGRESS,
                assigned_to_id=operator_id,
                started_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def complete(
        self,
        task_id: UUID,
        box_type: str,
        box_count: int,
        total_weight_kg: Optional[Decimal],
        total_volume_m3: Optional[Decimal],
        sscc: Optional[str],
        notes: Optional[str],
    ) -> None:
        now = datetime.now(timezone.utc)
        task = await self.get_by_id(task_id)
        cycle_time = int((now - task.started_at).total_seconds()) if task and task.started_at else None

        await self.db.execute(
            update(PackTask)
            .where(and_(PackTask.id == task_id, PackTask.tenant_id == self.tenant_id))
            .values(
                status=PackStatus.COMPLETED,
                box_type=box_type,
                box_count=box_count,
                total_weight_kg=total_weight_kg,
                total_volume_m3=total_volume_m3,
                sscc=sscc,
                notes=notes,
                completed_at=now,
                cycle_time_seconds=cycle_time,
                updated_at=now,
            )
        )


# ══════════════════════════════════════════════════════════════════════════════
# SHIPMENT
# ══════════════════════════════════════════════════════════════════════════════

class ShipmentRepository:

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def _next_number(self) -> str:
        result = await self.db.execute(
            select(func.count(Shipment.id)).where(Shipment.tenant_id == self.tenant_id)
        )
        return f"SHIP-{result.scalar_one() + 1:06d}"

    async def create(self, data: dict, created_by_id: UUID) -> Shipment:
        shipment = Shipment(
            id=uuid4(),
            tenant_id=self.tenant_id,
            shipment_number=await self._next_number(),
            status=ShipmentStatus.PENDING,
            created_by_id=created_by_id,
            **data,
        )
        self.db.add(shipment)
        await self.db.flush()
        return shipment

    async def get_by_id(self, shipment_id: UUID) -> Optional[Shipment]:
        result = await self.db.execute(
            select(Shipment).where(
                and_(Shipment.id == shipment_id, Shipment.tenant_id == self.tenant_id)
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        status: Optional[ShipmentStatus] = None,
        warehouse_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List[Shipment], int]:
        filters = [Shipment.tenant_id == self.tenant_id]
        if status:
            filters.append(Shipment.status == status)
        if warehouse_id:
            filters.append(Shipment.warehouse_id == warehouse_id)

        from app.models.master_data import Customer
        
        total = (
            await self.db.execute(
                select(func.count(Shipment.id)).where(and_(*filters))
            )
        ).scalar_one()
        
        result = (
            await self.db.execute(
                select(
                    Shipment,
                    SalesOrder.so_number.label("so_number"),
                    Customer.name.label("customer_name")
                )
                .join(SalesOrder, Shipment.so_id == SalesOrder.id)
                .join(Customer, SalesOrder.customer_id == Customer.id)
                .where(and_(*filters))
                .order_by(Shipment.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        
        shipments = []
        for row in result:
            shipment = row.Shipment
            shipment.so_number = row.so_number
            shipment.customer_name = row.customer_name
            shipments.append(shipment)
            
        return shipments, total

    async def dispatch(self, shipment_id: UUID, data: dict) -> None:
        await self.db.execute(
            update(Shipment)
            .where(and_(Shipment.id == shipment_id, Shipment.tenant_id == self.tenant_id))
            .values(
                status=ShipmentStatus.IN_TRANSIT,
                updated_at=datetime.now(timezone.utc),
                **data,
            )
        )

    async def deliver(self, shipment_id: UUID, data: dict) -> None:
        await self.db.execute(
            update(Shipment)
            .where(and_(Shipment.id == shipment_id, Shipment.tenant_id == self.tenant_id))
            .values(
                status=ShipmentStatus.DELIVERED,
                updated_at=datetime.now(timezone.utc),
                **data,
            )
        )

    async def count_today(self) -> int:
        result = await self.db.execute(
            select(func.count(Shipment.id)).where(
                and_(
                    Shipment.tenant_id == self.tenant_id,
                    func.date(Shipment.actual_pickup) == date.today(),
                )
            )
        )
        return result.scalar_one()

    async def count_in_transit(self) -> int:
        result = await self.db.execute(
            select(func.count(Shipment.id)).where(
                and_(
                    Shipment.tenant_id == self.tenant_id,
                    Shipment.status == ShipmentStatus.IN_TRANSIT,
                )
            )
        )
        return result.scalar_one()


# ══════════════════════════════════════════════════════════════════════════════
# RETURN ORDER
# ══════════════════════════════════════════════════════════════════════════════

class ReturnOrderRepository:

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def _next_rma_number(self) -> str:
        result = await self.db.execute(
            select(func.count(ReturnOrder.id)).where(
                ReturnOrder.tenant_id == self.tenant_id
            )
        )
        return f"RMA-{result.scalar_one() + 1:06d}"

    async def create(self, data: dict, created_by_id: UUID) -> ReturnOrder:
        rma = ReturnOrder(
            id=uuid4(),
            tenant_id=self.tenant_id,
            rma_number=await self._next_rma_number(),
            status=ReturnOrderStatus.REQUESTED,
            created_by_id=created_by_id,
            **data,
        )
        self.db.add(rma)
        await self.db.flush()
        return rma

    async def get_by_id(self, rma_id: UUID) -> Optional[ReturnOrder]:
        result = await self.db.execute(
            select(ReturnOrder).where(
                and_(ReturnOrder.id == rma_id, ReturnOrder.tenant_id == self.tenant_id)
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        status: Optional[ReturnOrderStatus] = None,
        customer_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List[ReturnOrder], int]:
        filters = [ReturnOrder.tenant_id == self.tenant_id]
        if status:
            filters.append(ReturnOrder.status == status)
        if customer_id:
            filters.append(ReturnOrder.customer_id == customer_id)

        from app.models.master_data import Customer
        from app.models.outbound import SalesOrder
        
        total = (
            await self.db.execute(
                select(func.count(ReturnOrder.id)).where(and_(*filters))
            )
        ).scalar_one()
        
        result = (
            await self.db.execute(
                select(
                    ReturnOrder,
                    SalesOrder.so_number.label("so_number"),
                    Customer.name.label("customer_name")
                )
                .join(Customer, ReturnOrder.customer_id == Customer.id)
                .outerjoin(SalesOrder, ReturnOrder.so_id == SalesOrder.id)
                .where(and_(*filters))
                .order_by(ReturnOrder.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        
        rmas = []
        for row in result:
            rma = row.ReturnOrder
            rma.so_number = row.so_number
            rma.customer_name = row.customer_name
            rmas.append(rma)
            
        return rmas, total

    async def update_status(self, rma_id: UUID, status: ReturnOrderStatus, **extra) -> None:
        await self.db.execute(
            update(ReturnOrder)
            .where(and_(ReturnOrder.id == rma_id, ReturnOrder.tenant_id == self.tenant_id))
            .values(status=status, updated_at=datetime.now(timezone.utc), **extra)
        )

    async def count_open(self) -> int:
        result = await self.db.execute(
            select(func.count(ReturnOrder.id)).where(
                and_(
                    ReturnOrder.tenant_id == self.tenant_id,
                    ReturnOrder.status.in_([
                        ReturnOrderStatus.REQUESTED,
                        ReturnOrderStatus.APPROVED,
                        ReturnOrderStatus.IN_TRANSIT,
                        ReturnOrderStatus.RECEIVED,
                    ]),
                )
            )
        )
        return result.scalar_one()
