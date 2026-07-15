"""
WMS Panamá — Order Streaming / Waveless Service — FR-055
=========================================================
Evolución del picking por olas (PickingWave) hacia liberación CONTINUA:

  • enqueue_order  — convierte una orden de venta asignada en tareas de picking
                     "waveless" (wave_id = NULL), listas para despacharse.
  • stream_next    — entrega al operario la SIGUIENTE mejor tarea pendiente por
                     prioridad y proximidad, con control de WIP (trabajo en curso),
                     en vez de planificar una ola completa por adelantado.
  • metrics        — cola pendiente, en curso y WIP por operario.

Ventaja vs. olas: menor latencia (una orden puede empezar a pickearse apenas
entra, sin esperar a llenar una ola) y flujo balanceado (WIP acotado por operario).

La lógica de selección es pura (testeable sin BD); los modelos pesados se importan
dentro de los métodos async. Reutiliza el modelo PickingTask existente y las
excepciones OutboundServiceError/PickingStateError (no crea tablas nuevas).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import OutboundServiceError, PickingStateError


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StreamingService:
    """Servicio de order streaming / picking waveless."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ══════════════════════════════════════════════════════════════════════════
    # LÓGICA PURA (testeable sin BD)
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def should_release(wip_count: int, max_wip: int) -> bool:
        """Control de flujo: solo liberar si el operario está por debajo del WIP máximo."""
        return wip_count < max_wip

    @staticmethod
    def select_next_pick(candidates: list, current_pick_sequence: Optional[int] = None):
        """
        Elige la siguiente mejor tarea de picking (order streaming).

        `candidates`: objetos con .priority (1=urgente), .pick_sequence (ubicación) y
        .created_at. Orden: prioridad → proximidad → antigüedad. Si se da la
        secuencia actual, la proximidad es |seq - actual| (minimiza recorrido);
        si no, se prefiere la secuencia más baja. Devuelve el mejor o None.
        """
        if not candidates:
            return None

        def key(t):
            priority = getattr(t, "priority", None)
            priority = 5 if priority is None else int(priority)
            seq = getattr(t, "pick_sequence", None)
            if current_pick_sequence is not None and seq is not None:
                distance = abs(int(seq) - int(current_pick_sequence))
            elif seq is not None:
                distance = int(seq)
            else:
                distance = 10 ** 9
            created = getattr(t, "created_at", None) or _now()
            return (priority, distance, created)

        return sorted(candidates, key=key)[0]

    # ══════════════════════════════════════════════════════════════════════════
    # ENCOLAR ORDEN (waveless)
    # ══════════════════════════════════════════════════════════════════════════

    async def enqueue_order(
        self, tenant_id: uuid.UUID, so_id: uuid.UUID, user_id: Optional[uuid.UUID] = None
    ) -> dict:
        """
        Crea tareas de picking waveless (wave_id = NULL) para las líneas
        asignadas de una orden. Requiere ubicación de picking en la línea.
        """
        from app.models.outbound import (
            PickingStatus, PickingTask, SalesOrder, SalesOrderLine, SOStatus,
        )

        so = (await self.db.execute(
            select(SalesOrder).where(and_(
                SalesOrder.id == so_id, SalesOrder.tenant_id == tenant_id
            ))
        )).scalar_one_or_none()
        if so is None:
            raise OutboundServiceError("Orden de venta no encontrada.")
        if so.status not in (SOStatus.CONFIRMED, SOStatus.ALLOCATED, SOStatus.PICKING):
            raise PickingStateError(
                f"La orden debe estar confirmada/asignada para encolar picking "
                f"(estado actual: '{so.status.value if hasattr(so.status, 'value') else so.status}')."
            )

        lines = (await self.db.execute(
            select(SalesOrderLine).where(SalesOrderLine.so_id == so_id)
        )).scalars().all()

        created = []
        for line in lines:
            if line.location_id is None:
                continue  # sin ubicación asignada aún → no se puede pickear
            allocated = Decimal(str(line.quantity_allocated or 0))
            picked = Decimal(str(line.quantity_picked or 0))
            to_pick = (allocated if allocated > 0 else Decimal(str(line.quantity_ordered or 0))) - picked
            if to_pick <= 0:
                continue
            task = PickingTask(
                id=uuid.uuid4(), tenant_id=tenant_id, created_by_id=user_id,
                wave_id=None,  # ← waveless
                so_id=so_id, so_line_id=line.id,
                product_id=line.product_id, uom_id=line.uom_id, batch_id=line.batch_id,
                quantity_requested=to_pick,
                from_location_id=line.location_id,
                status=PickingStatus.PENDING, priority=so.priority or 5,
            )
            self.db.add(task)
            created.append(task)

        if created and so.status in (SOStatus.CONFIRMED, SOStatus.ALLOCATED):
            so.status = SOStatus.PICKING

        await self.db.commit()
        for t in created:
            await self.db.refresh(t)
        return {"so_id": so_id, "tasks_created": len(created), "tasks": created}

    # ══════════════════════════════════════════════════════════════════════════
    # STREAM NEXT (despacho continuo)
    # ══════════════════════════════════════════════════════════════════════════

    async def _operator_wip(self, tenant_id, operator_id) -> int:
        from app.models.outbound import PickingStatus, PickingTask
        return (await self.db.execute(
            select(func.count(PickingTask.id)).where(and_(
                PickingTask.tenant_id == tenant_id,
                PickingTask.assigned_to_id == operator_id,
                PickingTask.status.in_([PickingStatus.PENDING, PickingStatus.IN_PROGRESS]),
                PickingTask.deleted_at.is_(None),
            ))
        )).scalar_one()

    async def stream_next(
        self, tenant_id: uuid.UUID, warehouse_id: uuid.UUID, operator_id: uuid.UUID,
        current_pick_sequence: Optional[int] = None, max_wip: int = 1,
    ):
        """
        Asigna al operario la siguiente mejor tarea waveless pendiente, respetando
        el WIP máximo. Devuelve la tarea asignada o None (cola vacía o WIP lleno).
        """
        from app.models.master_data import Location
        from app.models.outbound import PickingStatus, PickingTask, SalesOrder

        wip = await self._operator_wip(tenant_id, operator_id)
        if not self.should_release(wip, max_wip):
            return None

        # Cola waveless: tareas PENDING, sin ola y sin asignar, de la bodega.
        rows = (await self.db.execute(
            select(PickingTask, Location.pick_sequence)
            .join(SalesOrder, SalesOrder.id == PickingTask.so_id)
            .join(Location, Location.id == PickingTask.from_location_id, isouter=True)
            .where(and_(
                PickingTask.tenant_id == tenant_id,
                PickingTask.wave_id.is_(None),
                PickingTask.assigned_to_id.is_(None),
                PickingTask.status == PickingStatus.PENDING,
                PickingTask.deleted_at.is_(None),
                SalesOrder.warehouse_id == warehouse_id,
            ))
        )).all()
        if not rows:
            return None

        # Adjuntar pick_sequence a cada tarea para la selección pura.
        candidates = []
        for task, seq in rows:
            task.pick_sequence = seq  # atributo transitorio para el heurístico
            candidates.append(task)

        chosen = self.select_next_pick(candidates, current_pick_sequence)
        if chosen is None:
            return None
        chosen.assigned_to_id = operator_id
        await self.db.commit()
        await self.db.refresh(chosen)
        return chosen

    async def get_metrics(
        self, tenant_id: uuid.UUID, warehouse_id: Optional[uuid.UUID] = None,
    ) -> dict:
        from app.models.outbound import PickingStatus, PickingTask, SalesOrder

        base = [PickingTask.tenant_id == tenant_id, PickingTask.deleted_at.is_(None)]
        join_wh = warehouse_id is not None

        def _stmt(select_cols, extra):
            s = select(*select_cols)
            if join_wh:
                s = s.join(SalesOrder, SalesOrder.id == PickingTask.so_id)
            return s.where(and_(*base, *extra))

        wh = [SalesOrder.warehouse_id == warehouse_id] if join_wh else []

        queue_pending = (await self.db.execute(_stmt(
            [func.count(PickingTask.id)],
            [PickingTask.wave_id.is_(None), PickingTask.assigned_to_id.is_(None),
             PickingTask.status == PickingStatus.PENDING, *wh],
        ))).scalar_one()
        in_progress = (await self.db.execute(_stmt(
            [func.count(PickingTask.id)],
            [PickingTask.status == PickingStatus.IN_PROGRESS, *wh],
        ))).scalar_one()

        wip_rows = (await self.db.execute(_stmt(
            [PickingTask.assigned_to_id, func.count(PickingTask.id)],
            [PickingTask.assigned_to_id.isnot(None),
             PickingTask.status.in_([PickingStatus.PENDING, PickingStatus.IN_PROGRESS]), *wh],
        ).group_by(PickingTask.assigned_to_id))).all()
        wip_by_operator = {str(r[0]): r[1] for r in wip_rows}

        return {
            "queue_pending": queue_pending or 0,
            "in_progress": in_progress or 0,
            "operators_active": len(wip_by_operator),
            "wip_by_operator": wip_by_operator,
        }
