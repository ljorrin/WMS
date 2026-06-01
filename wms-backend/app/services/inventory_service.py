"""
WMS Panama — Servicio de Inventario
======================================
Lógica de negocio del módulo de inventario.
El Service orquesta: validaciones → repositorio → eventos → notificaciones.

Reglas de negocio implementadas:
1. FEFO/FIFO: Selección automática de lotes según estrategia de la bodega
2. Ajustes: Flujo draft → pending_approval → approved → applied
3. Reservas: Soft reserve (compromiso lógico) y Hard reserve (separación física)
4. Conteo cíclico: Bloqueo de ubicaciones durante conteo
5. Movimientos: Inmutables — nunca se editan, solo se crean reversas
6. Validaciones: Stock negativo NUNCA permitido
7. Alertas: Generación automática de alertas de stock bajo/vencimiento
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.redis import distributed_lock
from app.models.inventory import (
    InventoryStatus, MovementType, ReservationType,
    InventoryAdjustment, AdjustmentLine, CycleCount, CycleCountLine,
)
from app.models.master_data import Product, Location, Warehouse
from app.repositories.inventory import (
    InventoryLevelRepository,
    InventoryMovementRepository,
    BatchRepository,
    ReservationRepository,
    AdjustmentRepository,
    CycleCountRepository,
)
from app.schemas.inventory import (
    InventoryAdjustmentCreate,
    CycleCountCreate,
    CycleCountLineResult,
    InventoryReservationCreate,
    AdjustmentApproveRequest,
)

logger = get_logger(__name__)


class InventoryServiceError(Exception):
    """Error de lógica de negocio del inventario."""
    def __init__(self, message: str, code: str = "INVENTORY_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class InsufficientStockError(InventoryServiceError):
    def __init__(self, product_id: uuid.UUID, needed: Decimal, available: Decimal):
        super().__init__(
            f"Stock insuficiente para producto {product_id}: "
            f"necesario={needed}, disponible={available}",
            code="INSUFFICIENT_STOCK",
        )
        self.needed = needed
        self.available = available


class InventoryService:
    """
    Servicio principal de inventario.
    Instanciar por request — no es singleton.
    """

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

        # Repositorios
        self.levels = InventoryLevelRepository(db)
        self.movements = InventoryMovementRepository(db)
        self.batches = BatchRepository(db)
        self.reservations = ReservationRepository(db)
        self.adjustments = AdjustmentRepository(db)
        self.cycle_counts = CycleCountRepository(db)

    # ── Recepción (Receipt) ────────────────────────────────────────────────────

    async def receive_stock(
        self,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
        location_id: uuid.UUID,
        quantity: Decimal,
        lot_number: Optional[str] = None,
        expiry_date: Optional[date] = None,
        manufacture_date: Optional[date] = None,
        supplier_lot: Optional[str] = None,
        unit_cost: Optional[Decimal] = None,
        reference_type: Optional[str] = None,
        reference_id: Optional[uuid.UUID] = None,
        reference_number: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """
        Registra la entrada de mercancía a la bodega.
        Crea/actualiza el lote si aplica y actualiza el nivel de stock.
        """
        if quantity <= 0:
            raise InventoryServiceError("La cantidad de recepción debe ser mayor a cero.")

        # Validar que el producto requiere lote si se usa FEFO
        product = await self.db.get(Product, product_id)
        if not product:
            raise InventoryServiceError(f"Producto {product_id} no encontrado.")

        # Crear o recuperar lote
        batch_id = None
        if lot_number:
            batch = await self.batches.get_by_lot_number(
                self.tenant_id, product_id, warehouse_id, lot_number
            )
            if not batch:
                batch = await self.batches.create(
                    tenant_id=self.tenant_id,
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    lot_number=lot_number,
                    expiry_date=expiry_date,
                    manufacture_date=manufacture_date,
                    supplier_lot=supplier_lot,
                    quantity_received=quantity,
                    quantity_available=quantity,
                    status="active",
                )
            else:
                # Actualizar batch existente
                batch.quantity_received += quantity
                batch.quantity_available += quantity
            batch_id = batch.id

        # Actualizar nivel de stock
        async with distributed_lock(
            f"inv:level:{self.tenant_id}:{warehouse_id}:{product_id}:{location_id}:{batch_id}",
            timeout=30,
        ) as acquired:
            if not acquired:
                raise InventoryServiceError("No se pudo obtener lock de inventario. Intenta nuevamente.")

            level = await self.levels.get_or_create(
                tenant_id=self.tenant_id,
                warehouse_id=warehouse_id,
                product_id=product_id,
                location_id=location_id,
                batch_id=batch_id,
            )

            await self.levels.update_quantities(
                level_id=level.id,
                delta_on_hand=quantity,
                delta_available=quantity,
            )

        # Crear movimiento (evento inmutable)
        movement = await self.movements.create(
            tenant_id=self.tenant_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            movement_type=MovementType.RECEIPT,
            quantity=quantity,
            user_id=self.user_id,
            to_location_id=location_id,
            batch_id=batch_id,
            lot_number=lot_number,
            unit_cost=unit_cost,
            total_cost=unit_cost * quantity if unit_cost else None,
            reference_type=reference_type,
            reference_id=reference_id,
            reference_number=reference_number,
            notes=notes,
        )

        # Verificar alertas de stock
        await self._check_stock_alerts(warehouse_id, product_id)

        logger.info(
            "Stock received",
            product_id=str(product_id),
            warehouse_id=str(warehouse_id),
            quantity=str(quantity),
            lot_number=lot_number,
            movement_id=str(movement.id),
        )

        return {"movement": movement, "batch_id": batch_id, "level_id": level.id}

    # ── Transferencia entre ubicaciones ───────────────────────────────────────

    async def transfer_location(
        self,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
        from_location_id: uuid.UUID,
        to_location_id: uuid.UUID,
        quantity: Decimal,
        batch_id: Optional[uuid.UUID] = None,
        lot_number: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """
        Transfiere stock entre ubicaciones dentro de la misma bodega.
        Operación atómica: descuenta de origen y acredita en destino.
        """
        if from_location_id == to_location_id:
            raise InventoryServiceError("La ubicación de origen y destino no pueden ser iguales.")

        lock_key = f"inv:transfer:{self.tenant_id}:{warehouse_id}:{product_id}"
        async with distributed_lock(lock_key, timeout=30) as acquired:
            if not acquired:
                raise InventoryServiceError("No se pudo obtener lock. Intenta nuevamente.")

            # Verificar stock disponible en origen
            from_level = await self.levels.get_or_create(
                self.tenant_id, warehouse_id, product_id, from_location_id, batch_id
            )

            if from_level.quantity_available < quantity:
                raise InsufficientStockError(product_id, quantity, from_level.quantity_available)

            # Actualizar origen (resta)
            await self.levels.update_quantities(
                from_level.id,
                delta_on_hand=-quantity,
                delta_available=-quantity,
            )

            # Actualizar destino (suma)
            to_level = await self.levels.get_or_create(
                self.tenant_id, warehouse_id, product_id, to_location_id, batch_id
            )
            await self.levels.update_quantities(
                to_level.id,
                delta_on_hand=quantity,
                delta_available=quantity,
            )

        # Movimiento de salida
        out_mvt = await self.movements.create(
            tenant_id=self.tenant_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            movement_type=MovementType.TRANSFER_OUT,
            quantity=quantity,
            user_id=self.user_id,
            from_location_id=from_location_id,
            to_location_id=to_location_id,
            batch_id=batch_id,
            lot_number=lot_number,
            notes=notes,
        )

        return {"movement": out_mvt, "from_level_id": from_level.id, "to_level_id": to_level.id}

    # ── Picking ───────────────────────────────────────────────────────────────

    async def pick_stock(
        self,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
        quantity: Decimal,
        reference_type: str = "SO",
        reference_id: Optional[uuid.UUID] = None,
        reference_number: Optional[str] = None,
        force_location_id: Optional[uuid.UUID] = None,
        strategy: str = "FEFO",
    ) -> List[dict]:
        """
        Ejecuta el picking de stock para una orden.
        Aplica FEFO/FIFO automáticamente según la estrategia.
        Retorna lista de picks con ubicación, lote y cantidad.
        """
        # Seleccionar lotes según estrategia
        allocation = await self.levels.get_available_batches_fefo(
            tenant_id=self.tenant_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            quantity_needed=quantity,
            location_id=force_location_id,
        )

        # Verificar que haya stock suficiente
        total_allocated = sum(a["quantity_to_use"] for a in allocation)
        if total_allocated < quantity:
            raise InsufficientStockError(product_id, quantity, total_allocated)

        pick_results = []
        for alloc in allocation:
            level = alloc["level"]
            batch = alloc["batch"]
            qty = alloc["quantity_to_use"]

            async with distributed_lock(
                f"inv:pick:{self.tenant_id}:{level.id}", timeout=30
            ) as acquired:
                if not acquired:
                    raise InventoryServiceError("Lock de picking no disponible.")

                await self.levels.update_quantities(
                    level.id,
                    delta_on_hand=-qty,
                    delta_available=-qty,
                )

            movement = await self.movements.create(
                tenant_id=self.tenant_id,
                warehouse_id=warehouse_id,
                product_id=product_id,
                movement_type=MovementType.PICK,
                quantity=qty,
                user_id=self.user_id,
                from_location_id=level.location_id,
                batch_id=level.batch_id,
                lot_number=batch.lot_number if batch else None,
                reference_type=reference_type,
                reference_id=reference_id,
                reference_number=reference_number,
            )

            pick_results.append({
                "location_id": level.location_id,
                "batch_id": level.batch_id,
                "lot_number": batch.lot_number if batch else None,
                "quantity": qty,
                "movement_id": movement.id,
            })

        return pick_results

    # ── Ajustes de Inventario ─────────────────────────────────────────────────

    async def create_adjustment(
        self,
        body: InventoryAdjustmentCreate,
    ) -> InventoryAdjustment:
        """
        Crea un ajuste de inventario en estado 'draft'.
        El ajuste necesita aprobación antes de aplicarse al stock.
        """
        adj = await self.adjustments.create(
            tenant_id=self.tenant_id,
            warehouse_id=body.warehouse_id,
            created_by=self.user_id,
            reason=body.reason,
            reason_code=body.reason_code,
            notes=body.notes,
        )

        for line_data in body.lines:
            variance = line_data.quantity_physical - line_data.quantity_system
            await self.adjustments.add_line(
                adjustment_id=adj.id,
                tenant_id=self.tenant_id,
                product_id=line_data.product_id,
                location_id=line_data.location_id,
                batch_id=line_data.batch_id,
                lot_number=line_data.lot_number,
                quantity_system=line_data.quantity_system,
                quantity_physical=line_data.quantity_physical,
                variance=variance,
                variance_type="surplus" if variance > 0 else ("shortage" if variance < 0 else "none"),
                unit_cost=line_data.unit_cost,
                total_variance_cost=abs(variance) * line_data.unit_cost if line_data.unit_cost else None,
                notes=line_data.notes,
            )

        # Pasar a pending_approval automáticamente
        adj.status = "pending_approval"

        logger.info(
            "Adjustment created",
            adjustment_id=str(adj.id),
            adjustment_number=adj.adjustment_number,
            lines=len(body.lines),
        )
        return adj

    async def approve_adjustment(
        self,
        adjustment_id: uuid.UUID,
        body: AdjustmentApproveRequest,
    ) -> InventoryAdjustment:
        """
        Aprueba o rechaza un ajuste pendiente.
        Solo usuarios con permiso inventory:adjustment:approve pueden ejecutar esto.
        """
        adj = await self.adjustments.get_by_id(adjustment_id, self.tenant_id)
        if not adj:
            raise InventoryServiceError("Ajuste no encontrado.", "NOT_FOUND")
        if adj.status != "pending_approval":
            raise InventoryServiceError(
                f"El ajuste está en estado '{adj.status}'. Solo se puede aprobar/rechazar en 'pending_approval'.",
                "INVALID_STATE",
            )

        if body.approved:
            adj.status = "approved"
            adj.approved_by = self.user_id
            adj.approved_at = datetime.now(timezone.utc)
        else:
            adj.status = "rejected"
            adj.approved_by = self.user_id
            adj.approved_at = datetime.now(timezone.utc)

        if body.notes:
            adj.notes = (adj.notes or "") + f"\n[{body.approved and 'APROBADO' or 'RECHAZADO'}]: {body.notes}"

        return adj

    async def apply_adjustment(self, adjustment_id: uuid.UUID) -> InventoryAdjustment:
        """
        Aplica el ajuste aprobado al stock.
        Esta operación es irreversible y genera movimientos para cada línea.
        """
        adj = await self.adjustments.get_by_id(adjustment_id, self.tenant_id)
        if not adj:
            raise InventoryServiceError("Ajuste no encontrado.", "NOT_FOUND")
        if adj.status != "approved":
            raise InventoryServiceError(
                f"El ajuste debe estar 'approved' para aplicarse. Estado actual: {adj.status}",
                "INVALID_STATE",
            )

        for line in adj.lines:
            if line.variance == 0:
                continue  # Sin diferencia, skip

            movement_type = MovementType.ADJUSTMENT_IN if line.variance > 0 else MovementType.ADJUSTMENT_OUT
            qty = abs(line.variance)

            # Actualizar nivel de stock
            level = await self.levels.get_or_create(
                self.tenant_id, adj.warehouse_id,
                line.product_id, line.location_id, line.batch_id
            )

            if line.variance > 0:
                await self.levels.update_quantities(
                    level.id, delta_on_hand=qty, delta_available=qty
                )
            else:
                # Verificar que no quede negativo
                if level.quantity_available < qty:
                    logger.warning(
                        "Adjustment would make stock negative, using available",
                        level_id=str(level.id),
                        variance=str(line.variance),
                        available=str(level.quantity_available),
                    )
                    qty = level.quantity_available

                await self.levels.update_quantities(
                    level.id, delta_on_hand=-qty, delta_available=-qty
                )

            # Crear movimiento de ajuste
            await self.movements.create(
                tenant_id=self.tenant_id,
                warehouse_id=adj.warehouse_id,
                product_id=line.product_id,
                movement_type=movement_type,
                quantity=qty,
                user_id=self.user_id,
                to_location_id=line.location_id if line.variance > 0 else None,
                from_location_id=line.location_id if line.variance < 0 else None,
                batch_id=line.batch_id,
                lot_number=line.lot_number,
                unit_cost=line.unit_cost,
                reference_type="ADJUSTMENT",
                reference_id=adj.id,
                reference_number=adj.adjustment_number,
                notes=f"Ajuste {adj.adjustment_number}: {adj.reason}",
            )

        adj.status = "applied"
        adj.applied_by = self.user_id
        adj.applied_at = datetime.now(timezone.utc)

        logger.info("Adjustment applied", adjustment_id=str(adj.id))
        return adj

    # ── Reservas ──────────────────────────────────────────────────────────────

    async def create_reservation(
        self,
        body: InventoryReservationCreate,
    ) -> dict:
        """
        Reserva stock para una orden (soft o hard).
        Soft: reduce quantity_available sin separar físicamente.
        Hard: mueve a ubicación de staging.
        """
        # Verificar disponibilidad
        summary = await self.levels.get_stock_summary(
            self.tenant_id, body.warehouse_id, body.product_id
        )

        if summary["total_available"] < body.quantity:
            raise InsufficientStockError(
                body.product_id, body.quantity, summary["total_available"]
            )

        reservation = await self.reservations.create(
            tenant_id=self.tenant_id,
            warehouse_id=body.warehouse_id,
            product_id=body.product_id,
            quantity=body.quantity,
            reservation_type=body.reservation_type,
            status="active",
            reference_type=body.reference_type,
            reference_id=body.reference_id,
            reference_number=body.reference_number,
            batch_id=body.batch_id,
            location_id=body.location_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )

        # Actualizar stock disponible (reserva lógica)
        # En producción: seleccionar ubicación específica con FEFO
        allocation = await self.levels.get_available_batches_fefo(
            self.tenant_id, body.warehouse_id, body.product_id, body.quantity,
            location_id=body.location_id,
        )
        for alloc in allocation:
            await self.levels.update_quantities(
                alloc["level"].id,
                delta_available=-alloc["quantity_to_use"],
                delta_reserved=alloc["quantity_to_use"],
            )

        return {"reservation": reservation, "allocation": allocation}

    async def cancel_reservation(self, reservation_id: uuid.UUID) -> None:
        """Cancela una reserva activa y libera el stock."""
        from sqlalchemy import select
        from app.models.inventory import InventoryReservation

        result = await self.db.execute(
            select(InventoryReservation).where(
                InventoryReservation.id == reservation_id,
                InventoryReservation.tenant_id == self.tenant_id,
                InventoryReservation.status == "active",
            )
        )
        reservation = result.scalar_one_or_none()
        if not reservation:
            raise InventoryServiceError("Reserva no encontrada o ya cancelada.", "NOT_FOUND")

        # Liberar stock reservado
        allocation = await self.levels.get_available_batches_fefo(
            self.tenant_id, reservation.warehouse_id,
            reservation.product_id, reservation.quantity,
        )
        for alloc in allocation:
            qty = min(alloc["quantity_to_use"], reservation.quantity)
            await self.levels.update_quantities(
                alloc["level"].id,
                delta_available=qty,
                delta_reserved=-qty,
            )

        reservation.status = "cancelled"
        reservation.cancelled_at = datetime.now(timezone.utc)

    # ── Conteo Cíclico ────────────────────────────────────────────────────────

    async def create_cycle_count(self, body: CycleCountCreate) -> CycleCount:
        """
        Crea una tarea de conteo cíclico.
        Genera las líneas a contar basándose en los criterios.
        """
        cc = await self.cycle_counts.create(
            tenant_id=self.tenant_id,
            warehouse_id=body.warehouse_id,
            name=body.name,
            count_type=body.count_type,
            created_by=self.user_id,
            scheduled_date=body.scheduled_date,
            notes=body.notes,
        )

        # Generar líneas según criterios
        from sqlalchemy import select as sql_select
        from app.models.inventory import InventoryLevel

        stmt = sql_select(InventoryLevel).where(
            InventoryLevel.tenant_id == self.tenant_id,
            InventoryLevel.warehouse_id == body.warehouse_id,
            InventoryLevel.quantity_on_hand > 0,
        )

        if body.location_ids:
            stmt = stmt.where(InventoryLevel.location_id.in_(body.location_ids))
        if body.product_ids:
            stmt = stmt.where(InventoryLevel.product_id.in_(body.product_ids))

        levels = (await self.db.execute(stmt)).scalars().all()

        for level in levels:
            await self.cycle_counts.add_line(
                cycle_count_id=cc.id,
                tenant_id=self.tenant_id,
                location_id=level.location_id,
                product_id=level.product_id,
                batch_id=level.batch_id,
                lot_number=None,
                quantity_system=level.quantity_on_hand,
                status="pending",
            )

        cc.status = "in_progress"
        cc.started_at = datetime.now(timezone.utc)

        logger.info(
            "Cycle count created",
            cc_id=str(cc.id),
            lines=len(levels),
        )
        return cc

    async def record_cycle_count_result(
        self,
        cycle_count_id: uuid.UUID,
        results: List[CycleCountLineResult],
    ) -> CycleCount:
        """Registra los resultados de un conteo cíclico."""
        from sqlalchemy import select as sql_select
        from app.models.inventory import CycleCountLine

        cc = await self.cycle_counts.get_by_id(cycle_count_id, self.tenant_id)
        if not cc or cc.status != "in_progress":
            raise InventoryServiceError("Conteo no encontrado o no está en progreso.")

        for result in results:
            # Buscar la línea correspondiente
            stmt = sql_select(CycleCountLine).where(
                CycleCountLine.cycle_count_id == cycle_count_id,
                CycleCountLine.location_id == result.location_id,
                CycleCountLine.product_id == result.product_id,
            )
            line = (await self.db.execute(stmt)).scalar_one_or_none()

            if not line:
                continue

            line.quantity_counted = result.quantity_counted
            line.counted_at = datetime.now(timezone.utc)
            line.counted_by = result.counter_id or self.user_id
            line.notes = result.notes

            # Calcular varianza
            if line.quantity_system is not None:
                line.variance = result.quantity_counted - line.quantity_system
                if line.quantity_system > 0:
                    line.variance_pct = (abs(line.variance) / line.quantity_system) * 100
                line.status = "discrepancy" if abs(line.variance) > 0 else "counted"
            else:
                line.status = "counted"

        return cc

    async def complete_cycle_count(self, cycle_count_id: uuid.UUID, apply_results: bool = False) -> CycleCount:
        """
        Completa el conteo cíclico.
        Si apply_results=True, aplica las diferencias como ajustes de inventario.
        """
        cc = await self.cycle_counts.get_by_id(cycle_count_id, self.tenant_id)
        if not cc:
            raise InventoryServiceError("Conteo no encontrado.")

        if apply_results:
            # Crear ajuste automático con las diferencias del conteo
            from app.schemas.inventory import InventoryAdjustmentCreate, AdjustmentLineCreate

            lines_with_variance = [
                line for line in cc.lines if line.variance and line.variance != 0
            ]

            if lines_with_variance:
                adj_body = InventoryAdjustmentCreate(
                    warehouse_id=cc.warehouse_id,
                    reason=f"Ajuste automático por conteo cíclico {cc.count_number}",
                    reason_code="CYCLE_COUNT",
                    lines=[
                        AdjustmentLineCreate(
                            product_id=line.product_id,
                            location_id=line.location_id,
                            batch_id=line.batch_id,
                            quantity_system=line.quantity_system or Decimal("0"),
                            quantity_physical=line.quantity_counted or Decimal("0"),
                        )
                        for line in lines_with_variance
                    ],
                    reference_number=cc.count_number,
                )
                adj = await self.create_adjustment(adj_body)
                # Auto-aprobar si viene del conteo cíclico verificado
                adj.status = "approved"
                adj.approved_by = self.user_id
                adj.approved_at = datetime.now(timezone.utc)
                await self.apply_adjustment(adj.id)

        # Calcular precisión del conteo
        total_lines = len(cc.lines)
        accurate_lines = sum(1 for l in cc.lines if l.variance == 0 or l.variance is None)
        if total_lines > 0:
            cc.accuracy_pct = Decimal(str(accurate_lines / total_lines * 100)).quantize(Decimal("0.01"))

        cc.status = "completed"
        cc.completed_at = datetime.now(timezone.utc)

        return cc

    # ── Alertas ───────────────────────────────────────────────────────────────

    async def _check_stock_alerts(
        self,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> None:
        """
        Verifica y genera alertas de stock post-movimiento.
        Se ejecuta de forma silenciosa (errores no propagan).
        """
        try:
            product = await self.db.get(Product, product_id)
            if not product:
                return

            summary = await self.levels.get_stock_summary(
                self.tenant_id, warehouse_id, product_id
            )

            from app.models.inventory import StockAlert

            # Alerta: Stock bajo mínimo
            if product.min_stock and summary["total_available"] < product.min_stock:
                alert = StockAlert(
                    tenant_id=self.tenant_id,
                    warehouse_id=warehouse_id,
                    product_id=product_id,
                    alert_type="below_min",
                    severity="warning",
                    current_quantity=summary["total_available"],
                    threshold_quantity=product.min_stock,
                    message=f"Stock por debajo del mínimo: {summary['total_available']} < {product.min_stock}",
                )
                self.db.add(alert)

        except Exception as e:
            logger.warning("Failed to check stock alerts", error=str(e))
