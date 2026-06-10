"""
WMS Panama — Repositorio de Inventario
========================================
Capa de acceso a datos para el módulo de inventario.
Patrón Repository: toda la lógica SQL aquí, sin lógica de negocio.
La lógica de negocio va en el Service (inventory_service.py).

Principios:
- Todas las queries son async (asyncpg)
- Multi-tenant: todos los filtros incluyen tenant_id
- FEFO/FIFO implementado en las queries de selección de lotes
- Locks optimistas para operaciones concurrentes de stock
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional, List, Sequence

from sqlalchemy import (
    select, update, func, and_, or_, case, text
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.models.inventory import (
    InventoryLevel, InventoryMovement, InventoryReservation,
    InventoryAdjustment, AdjustmentLine, CycleCount, CycleCountLine,
    Batch, SerialNumber, StockAlert,
    MovementType, InventoryStatus, ReservationType, AdjustmentStatus,
)
from app.models.master_data import Product, Location
from app.core.logging import get_logger

logger = get_logger(__name__)


class InventoryLevelRepository:
    """Repositorio de niveles de stock (InventoryLevel)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, level_id: uuid.UUID, tenant_id: uuid.UUID) -> Optional[InventoryLevel]:
        result = await self.db.execute(
            select(InventoryLevel)
            .where(InventoryLevel.id == level_id, InventoryLevel.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        tenant_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
        location_id: uuid.UUID,
        batch_id: Optional[uuid.UUID] = None,
    ) -> InventoryLevel:
        """
        Obtiene el nivel de stock existente o crea uno nuevo.
        La combinación (warehouse, product, location, batch) es única.
        """
        stmt = select(InventoryLevel).where(
            InventoryLevel.tenant_id == tenant_id,
            InventoryLevel.warehouse_id == warehouse_id,
            InventoryLevel.product_id == product_id,
            InventoryLevel.location_id == location_id,
            InventoryLevel.batch_id == batch_id,
        )
        result = await self.db.execute(stmt)
        level = result.scalar_one_or_none()

        if not level:
            level = InventoryLevel(
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                product_id=product_id,
                location_id=location_id,
                batch_id=batch_id,
                quantity_on_hand=Decimal("0"),
                quantity_available=Decimal("0"),
                quantity_reserved=Decimal("0"),
                quantity_in_picking=Decimal("0"),
                quantity_damaged=Decimal("0"),
                status=InventoryStatus.AVAILABLE,
            )
            self.db.add(level)
            await self.db.flush()

        return level

    async def list_by_warehouse(
        self,
        tenant_id: uuid.UUID,
        warehouse_id: Optional[uuid.UUID] = None,
        product_id: Optional[uuid.UUID] = None,
        location_id: Optional[uuid.UUID] = None,
        status: Optional[InventoryStatus] = None,
        include_zero: bool = False,
        near_expiry_days: Optional[int] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[InventoryLevel], int]:
        """Lista stock con filtros. Retorna (items, total)."""
        stmt = (
            select(
                InventoryLevel,
                Product.sku.label("product_code"),
                Product.name.label("product_name"),
                Location.code.label("location_code"),
                Batch.batch_number.label("lot_number"),
                Batch.expiry_date.label("expiry_date")
            )
            .join(Product, InventoryLevel.product_id == Product.id)
            .join(Location, InventoryLevel.location_id == Location.id)
            .outerjoin(Batch, InventoryLevel.batch_id == Batch.id)
            .where(InventoryLevel.tenant_id == tenant_id)
        )
        
        if warehouse_id:
            stmt = stmt.where(InventoryLevel.warehouse_id == warehouse_id)

        if product_id:
            stmt = stmt.where(InventoryLevel.product_id == product_id)
        if location_id:
            stmt = stmt.where(InventoryLevel.location_id == location_id)
        if status:
            stmt = stmt.where(InventoryLevel.status == status)
        if not include_zero:
            stmt = stmt.where(InventoryLevel.quantity_on_hand > 0)

        if near_expiry_days:
            from datetime import timedelta
            cutoff_date = datetime.now(timezone.utc).date() + timedelta(days=near_expiry_days)
            stmt = stmt.where(
                or_(
                    Batch.expiry_date <= cutoff_date,
                    Batch.expiry_date.is_(None),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(offset).limit(limit).order_by(InventoryLevel.updated_at.desc())
        results = (await self.db.execute(stmt)).all()

        items = []
        for row in results:
            level = row.InventoryLevel
            level.product_code = row.product_code
            level.product_name = row.product_name
            level.location_code = row.location_code
            level.lot_number = row.lot_number
            level.expiry_date = row.expiry_date
            items.append(level)

        return items, total

    async def get_available_batches_fefo(
        self,
        tenant_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
        quantity_needed: Decimal,
        location_id: Optional[uuid.UUID] = None,
        strategy: str = "FEFO",
    ) -> List[dict]:
        """
        Selecciona lotes según la estrategia de rotación (FR-043):
          - FEFO: vencimiento más próximo primero (default; NULL al final).
          - FIFO: el más antiguo recibido primero.
          - LIFO: el más reciente recibido primero.
        Retorna lista de {level, batch, quantity_to_use} hasta cubrir quantity_needed.
        Este es el algoritmo crítico del WMS.
        """
        stmt = (
            select(InventoryLevel, Batch)
            .join(Batch, InventoryLevel.batch_id == Batch.id, isouter=True)
            .where(
                InventoryLevel.tenant_id == tenant_id,
                InventoryLevel.warehouse_id == warehouse_id,
                InventoryLevel.product_id == product_id,
                InventoryLevel.quantity_available > 0,
                InventoryLevel.status == InventoryStatus.AVAILABLE,
            )
        )

        if location_id:
            stmt = stmt.where(InventoryLevel.location_id == location_id)

        strat = (strategy or "FEFO").upper()
        if strat == "LIFO":
            # Último en entrar, primero en salir: lote recibido más recientemente.
            stmt = stmt.order_by(
                Batch.received_date.desc().nullslast(),
                InventoryLevel.created_at.desc(),
            )
        elif strat == "FIFO":
            # Primero en entrar, primero en salir.
            stmt = stmt.order_by(
                Batch.received_date.asc().nullslast(),
                InventoryLevel.created_at.asc(),
            )
        else:
            # FEFO (default): los que vencen primero primero. NULL expiry va al final.
            stmt = stmt.order_by(
                case(
                    (Batch.expiry_date.is_(None), 1),
                    else_=0,
                ),
                Batch.expiry_date.asc().nullslast(),
                InventoryLevel.updated_at.asc(),  # FIFO como desempate
            )

        results = (await self.db.execute(stmt)).all()

        allocation = []
        remaining = quantity_needed

        for level, batch in results:
            if remaining <= 0:
                break
            use = min(level.quantity_available, remaining)
            allocation.append({
                "level": level,
                "batch": batch,
                "quantity_to_use": use,
            })
            remaining -= use

        return allocation

    async def get_stock_summary(
        self,
        tenant_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> dict:
        """
        Resumen consolidado de stock para un SKU en la bodega.
        Agrega quantities de todas las ubicaciones/lotes.
        """
        stmt = select(
            func.sum(InventoryLevel.quantity_on_hand).label("total_on_hand"),
            func.sum(InventoryLevel.quantity_available).label("total_available"),
            func.sum(InventoryLevel.quantity_reserved).label("total_reserved"),
            func.sum(InventoryLevel.quantity_in_transit).label("total_in_transit"),
            func.sum(
                case((InventoryLevel.status == InventoryStatus.QUARANTINE,
                      InventoryLevel.quantity_on_hand), else_=0)
            ).label("total_quarantine"),
        ).where(
            InventoryLevel.tenant_id == tenant_id,
            InventoryLevel.warehouse_id == warehouse_id,
            InventoryLevel.product_id == product_id,
        )

        result = (await self.db.execute(stmt)).one()

        return {
            "total_on_hand":    result.total_on_hand    or Decimal("0"),
            "total_available":  result.total_available  or Decimal("0"),
            "total_reserved":   result.total_reserved   or Decimal("0"),
            "total_in_transit": result.total_in_transit or Decimal("0"),
            "total_quarantine": result.total_quarantine or Decimal("0"),
        }

    async def update_quantities(
        self,
        level_id: uuid.UUID,
        delta_on_hand: Decimal = Decimal("0"),
        delta_available: Decimal = Decimal("0"),
        delta_reserved: Decimal = Decimal("0"),
        delta_in_transit: Decimal = Decimal("0"),
    ) -> InventoryLevel:
        """
        Actualiza cantidades de forma atómica usando UPDATE con delta.
        Más seguro que read-modify-write en concurrencia.
        """
        await self.db.execute(
            update(InventoryLevel)
            .where(InventoryLevel.id == level_id)
            .values(
                quantity_on_hand=InventoryLevel.quantity_on_hand + delta_on_hand,
                quantity_available=InventoryLevel.quantity_available + delta_available,
                quantity_reserved=InventoryLevel.quantity_reserved + delta_reserved,
                quantity_in_transit=InventoryLevel.quantity_in_transit + delta_in_transit,
                updated_at=func.now(),
            )
        )

        # Recargar para obtener los valores actualizados
        result = await self.db.execute(
            select(InventoryLevel).where(InventoryLevel.id == level_id)
        )
        return result.scalar_one()


class InventoryMovementRepository:
    """Repositorio de movimientos de inventario."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        tenant_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
        movement_type: MovementType,
        quantity: Decimal,
        user_id: Optional[uuid.UUID] = None,
        **kwargs,
    ) -> InventoryMovement:
        """Crea un evento de movimiento inmutable."""
        movement = InventoryMovement(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            movement_type=movement_type,
            quantity=quantity,
            user_id=user_id,
            occurred_at=datetime.now(timezone.utc),
            **kwargs,
        )
        self.db.add(movement)
        await self.db.flush()
        return movement

    async def list(
        self,
        tenant_id: uuid.UUID,
        warehouse_id: Optional[uuid.UUID] = None,
        product_id: Optional[uuid.UUID] = None,
        movement_type: Optional[MovementType] = None,
        reference_type: Optional[str] = None,
        reference_id: Optional[uuid.UUID] = None,
        location_id: Optional[uuid.UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[InventoryMovement], int]:
        from sqlalchemy.orm import aliased
        FromLocation = aliased(Location)
        ToLocation = aliased(Location)

        stmt = (
            select(
                InventoryMovement,
                Product.sku.label("product_code"),
                Product.name.label("product_name"),
                FromLocation.code.label("from_location_code"),
                ToLocation.code.label("to_location_code"),
                Batch.batch_number.label("lot_number")
            )
            .join(Product, InventoryMovement.product_id == Product.id)
            .outerjoin(FromLocation, InventoryMovement.from_location_id == FromLocation.id)
            .outerjoin(ToLocation, InventoryMovement.to_location_id == ToLocation.id)
            .outerjoin(Batch, InventoryMovement.batch_id == Batch.id)
            .where(InventoryMovement.tenant_id == tenant_id)
        )

        if warehouse_id:
            stmt = stmt.where(InventoryMovement.warehouse_id == warehouse_id)
        if product_id:
            stmt = stmt.where(InventoryMovement.product_id == product_id)
        if movement_type:
            stmt = stmt.where(InventoryMovement.movement_type == movement_type)
        if reference_type:
            stmt = stmt.where(InventoryMovement.reference_type == reference_type)
        if reference_id:
            stmt = stmt.where(InventoryMovement.reference_id == reference_id)
        if location_id:
            stmt = stmt.where(
                or_(
                    InventoryMovement.from_location_id == location_id,
                    InventoryMovement.to_location_id == location_id,
                )
            )
        if date_from:
            stmt = stmt.where(InventoryMovement.occurred_at >= date_from)
        if date_to:
            stmt = stmt.where(InventoryMovement.occurred_at <= date_to)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(offset).limit(limit).order_by(InventoryMovement.occurred_at.desc())
        results = (await self.db.execute(stmt)).all()

        items = []
        for row in results:
            mov = row.InventoryMovement
            mov.product_code = row.product_code
            mov.product_name = row.product_name
            mov.from_location_code = row.from_location_code
            mov.to_location_code = row.to_location_code
            mov.lot_number = row.lot_number
            # Compatibilidad con frontend
            mov.location_id = mov.to_location_id or mov.from_location_id
            mov.location_code = row.to_location_code or row.from_location_code
            mov.batch_number = row.lot_number
            items.append(mov)

        return items, total

    async def get_product_stock_card(
        self,
        tenant_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[InventoryMovement]:
        """
        Tarjeta de stock (kárdex) de un producto — todos sus movimientos.
        Ordenados cronológicamente para reconstruir el saldo.
        """
        stmt = select(InventoryMovement).where(
            InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.warehouse_id == warehouse_id,
            InventoryMovement.product_id == product_id,
        ).order_by(InventoryMovement.occurred_at.asc())

        if date_from:
            stmt = stmt.where(InventoryMovement.occurred_at >= date_from)
        if date_to:
            stmt = stmt.where(InventoryMovement.occurred_at <= date_to)

        return (await self.db.execute(stmt)).scalars().all()


class BatchRepository:
    """Repositorio de lotes (Batch)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, tenant_id: uuid.UUID, **kwargs) -> Batch:
        batch = Batch(tenant_id=tenant_id, **kwargs)
        self.db.add(batch)
        await self.db.flush()
        return batch

    async def get_by_lot_number(
        self,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        lot_number: str,
    ) -> Optional[Batch]:
        result = await self.db.execute(
            select(Batch).where(
                Batch.tenant_id == tenant_id,
                Batch.product_id == product_id,
                Batch.warehouse_id == warehouse_id,
                Batch.lot_number == lot_number,
            )
        )
        return result.scalar_one_or_none()

    async def get_near_expiry(
        self,
        tenant_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        days_ahead: int = 30,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[List[Batch], int]:
        """Lotes que vencen en los próximos N días."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc).date() + timedelta(days=days_ahead)

        stmt = (
            select(
                Batch,
                Product.sku.label("product_code"),
                Product.name.label("product_name"),
                func.sum(InventoryLevel.quantity_available).label("qty_avail"),
                func.sum(InventoryLevel.quantity_reserved).label("qty_hold"),
            )
            .join(Product, Batch.product_id == Product.id)
            .join(InventoryLevel, InventoryLevel.batch_id == Batch.id)
            .where(
                Batch.tenant_id == tenant_id,
                Batch.warehouse_id == warehouse_id,
                Batch.expiry_date.is_not(None),
                Batch.expiry_date <= cutoff,
                InventoryLevel.quantity_available > 0,
            )
            .group_by(Batch.id, Product.sku, Product.name)
        )
        
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(Batch.expiry_date.asc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        
        items = []
        today_date = datetime.now(timezone.utc).date()
        for row in result.all():
            batch = row.Batch
            batch.product_code = row.product_code
            batch.product_name = row.product_name
            batch.quantity_available = row.qty_avail or 0
            batch.quantity_on_hold = row.qty_hold or 0
            if batch.expiry_date:
                batch.days_to_expiry = (batch.expiry_date - today_date).days
                batch.is_expired = batch.days_to_expiry < 0
                batch.is_near_expiry = 0 <= batch.days_to_expiry <= 30
            items.append(batch)
        return items, total

    async def get_expired(
        self,
        tenant_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[List[Batch], int]:
        """Lotes ya vencidos con stock disponible."""
        today = datetime.now(timezone.utc).date()
        stmt = (
            select(
                Batch,
                Product.sku.label("product_code"),
                Product.name.label("product_name"),
                func.sum(InventoryLevel.quantity_available).label("qty_avail"),
                func.sum(InventoryLevel.quantity_reserved).label("qty_hold"),
            )
            .join(Product, Batch.product_id == Product.id)
            .join(InventoryLevel, InventoryLevel.batch_id == Batch.id)
            .where(
                Batch.tenant_id == tenant_id,
                Batch.warehouse_id == warehouse_id,
                Batch.expiry_date < today,
                InventoryLevel.quantity_available > 0,
            )
            .group_by(Batch.id, Product.sku, Product.name)
        )
        
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(Batch.expiry_date.asc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        
        items = []
        for row in result.all():
            batch = row.Batch
            batch.product_code = row.product_code
            batch.product_name = row.product_name
            batch.quantity_available = row.qty_avail or 0
            batch.quantity_on_hold = row.qty_hold or 0
            if batch.expiry_date:
                batch.days_to_expiry = (batch.expiry_date - today).days
                batch.is_expired = True
                batch.is_near_expiry = False
            items.append(batch)
        return items, total


class ReservationRepository:
    """Repositorio de reservas de inventario."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, tenant_id: uuid.UUID, **kwargs) -> InventoryReservation:
        reservation = InventoryReservation(tenant_id=tenant_id, **kwargs)
        self.db.add(reservation)
        await self.db.flush()
        return reservation

    async def get_active_by_reference(
        self,
        tenant_id: uuid.UUID,
        reference_type: str,
        reference_id: uuid.UUID,
    ) -> List[InventoryReservation]:
        result = await self.db.execute(
            select(InventoryReservation).where(
                InventoryReservation.tenant_id == tenant_id,
                InventoryReservation.reference_type == reference_type,
                InventoryReservation.reference_id == reference_id,
                InventoryReservation.status == "active",
            )
        )
        return result.scalars().all()

    async def get_reserved_quantity(
        self,
        tenant_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> Decimal:
        """Total reservado para un producto en la bodega."""
        result = await self.db.execute(
            select(func.sum(InventoryReservation.quantity))
            .where(
                InventoryReservation.tenant_id == tenant_id,
                InventoryReservation.warehouse_id == warehouse_id,
                InventoryReservation.product_id == product_id,
                InventoryReservation.status == "active",
            )
        )
        return result.scalar_one() or Decimal("0")


class AdjustmentRepository:
    """Repositorio de ajustes de inventario."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        tenant_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        created_by: uuid.UUID,
        reason: str,
        reason_code: str,
        notes: Optional[str] = None,
        reference_number: Optional[str] = None,
    ) -> InventoryAdjustment:
        """Crea el encabezado del ajuste y genera el número correlativo."""
        # Número correlativo por tenant
        count_result = await self.db.execute(
            select(func.count(InventoryAdjustment.id))
            .where(InventoryAdjustment.tenant_id == tenant_id)
        )
        count = (count_result.scalar_one() or 0) + 1
        adjustment_number = f"ADJ-{count:06d}"

        adj = InventoryAdjustment(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            adjustment_number=adjustment_number,
            reason=reason,
            reason_code=reason_code,
            notes=notes,
            reference_number=reference_number,
            status=AdjustmentStatus.DRAFT,
            requested_by=created_by,
            created_by_id=created_by,
        )
        self.db.add(adj)
        await self.db.flush()
        return adj

    async def add_line(
        self,
        adjustment_id: uuid.UUID,
        tenant_id: uuid.UUID,
        **kwargs,
    ) -> AdjustmentLine:
        line = AdjustmentLine(
            adjustment_id=adjustment_id,
            tenant_id=tenant_id,
            **kwargs,
        )
        self.db.add(line)
        await self.db.flush()
        return line

    async def get_by_id(
        self,
        adjustment_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Optional[InventoryAdjustment]:
        result = await self.db.execute(
            select(InventoryAdjustment)
            .where(
                InventoryAdjustment.id == adjustment_id,
                InventoryAdjustment.tenant_id == tenant_id,
            )
            .options(selectinload(InventoryAdjustment.lines))
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        tenant_id: uuid.UUID,
        warehouse_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[InventoryAdjustment], int]:
        stmt = select(InventoryAdjustment).where(
            InventoryAdjustment.tenant_id == tenant_id
        )
        if warehouse_id:
            stmt = stmt.where(InventoryAdjustment.warehouse_id == warehouse_id)
        if status:
            stmt = stmt.where(InventoryAdjustment.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar_one()

        stmt = (
            stmt.options(selectinload(InventoryAdjustment.lines))
            .offset(offset)
            .limit(limit)
            .order_by(InventoryAdjustment.created_at.desc())
        )
        items = (await self.db.execute(stmt)).scalars().all()
        return items, total


class CycleCountRepository:
    """Repositorio de conteos cíclicos."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        tenant_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        name: str,
        count_type: str,
        created_by: uuid.UUID,
        scheduled_date: Optional[date] = None,
        notes: Optional[str] = None,
    ) -> CycleCount:
        count_result = await self.db.execute(
            select(func.count(CycleCount.id))
            .where(CycleCount.tenant_id == tenant_id)
        )
        seq = (count_result.scalar_one() or 0) + 1
        count_number = f"CC-{seq:06d}"

        cc = CycleCount(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            count_number=count_number,
            name=name,
            count_type=count_type,
            status="draft",
            scheduled_date=scheduled_date,
            notes=notes,
            created_by_id=created_by,
        )
        self.db.add(cc)
        await self.db.flush()
        return cc

    async def add_line(self, cycle_count_id: uuid.UUID, tenant_id: uuid.UUID, **kwargs) -> CycleCountLine:
        line = CycleCountLine(
            cycle_count_id=cycle_count_id,
            tenant_id=tenant_id,
            status="pending",
            **kwargs,
        )
        self.db.add(line)
        await self.db.flush()
        return line

    async def get_by_id(self, cc_id: uuid.UUID, tenant_id: uuid.UUID) -> Optional[CycleCount]:
        result = await self.db.execute(
            select(CycleCount)
            .where(CycleCount.id == cc_id, CycleCount.tenant_id == tenant_id)
            .options(selectinload(CycleCount.lines))
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        tenant_id: uuid.UUID,
        warehouse_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[CycleCount], int]:
        stmt = select(CycleCount).where(CycleCount.tenant_id == tenant_id)
        if warehouse_id:
            stmt = stmt.where(CycleCount.warehouse_id == warehouse_id)
        if status:
            stmt = stmt.where(CycleCount.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(offset).limit(limit).order_by(CycleCount.created_at.desc())
        items = (await self.db.execute(stmt)).scalars().all()
        return items, total
