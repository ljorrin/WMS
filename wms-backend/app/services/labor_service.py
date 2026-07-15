"""
WMS Panamá — Labor Management Service — FR-090…093
===================================================
Lógica de negocio de gestión de mano de obra:

  • Estándares de labor de ingeniería (crear/editar).
  • Ciclo de vida de tareas: crear → asignar → iniciar → completar.
  • Cálculo de desempeño real vs. estándar al completar.
  • Task interleaving: sugerir/asignar la siguiente mejor tarea por proximidad
    (misma zona primero) para minimizar viajes vacíos.
  • KPIs del dashboard de productividad (por operario y por actividad).

La lógica de cálculo se expone en métodos estáticos puros para poder
probarse sin base de datos (tests unitarios con --noconftest).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import LaborServiceError, LaborStandardError, LaborTaskStateError
from app.models.labor import LaborStandard, LaborTask


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LaborService:
    """Servicio de gestión de mano de obra."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ══════════════════════════════════════════════════════════════════════════
    # LÓGICA PURA (testeable sin BD)
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def compute_standard_minutes(
        fixed_minutes: Decimal | float,
        std_minutes_per_unit: Decimal | float,
        quantity: Decimal | float,
    ) -> Decimal:
        """Tiempo esperado = fijo + (por_unidad × cantidad)."""
        fixed = Decimal(str(fixed_minutes or 0))
        per_unit = Decimal(str(std_minutes_per_unit or 0))
        qty = Decimal(str(quantity or 0))
        return (fixed + per_unit * qty).quantize(Decimal("0.0001"))

    @staticmethod
    def compute_actual_minutes(started_at: datetime, completed_at: datetime) -> Decimal:
        """Minutos reales transcurridos entre inicio y fin (mínimo 0)."""
        if not started_at or not completed_at:
            raise LaborTaskStateError("La tarea requiere started_at y completed_at.")
        seconds = (completed_at - started_at).total_seconds()
        if seconds < 0:
            seconds = 0
        return (Decimal(str(seconds)) / Decimal("60")).quantize(Decimal("0.0001"))

    @staticmethod
    def compute_performance_pct(
        standard_minutes: Decimal | float,
        actual_minutes: Decimal | float,
    ) -> Optional[Decimal]:
        """
        % de desempeño = estándar / real × 100.
        100 = cumple el estándar; >100 más rápido (mejor); <100 más lento.
        Devuelve None si no hay tiempo real medible (evita división por cero).
        """
        actual = Decimal(str(actual_minutes or 0))
        std = Decimal(str(standard_minutes or 0))
        if actual <= 0:
            return None
        return (std / actual * Decimal("100")).quantize(Decimal("0.01"))

    @staticmethod
    def choose_next_task(
        pending: list["LaborTask"],
        current_zone: Optional[str] = None,
    ) -> Optional["LaborTask"]:
        """
        Motor de interleaving: elige la mejor tarea pendiente para un operario.

        Regla: primero las de la MISMA zona que el operario (minimiza viaje),
        luego el resto; dentro de cada grupo, por prioridad (1 antes que 9) y
        por antigüedad (created_at). Devuelve None si no hay tareas.
        """
        if not pending:
            return None

        def sort_key(t: "LaborTask"):
            same_zone = 0 if (current_zone and t.zone == current_zone) else 1
            priority = int(t.priority) if t.priority is not None else 5
            created = getattr(t, "created_at", None) or _now()
            return (same_zone, priority, created)

        return sorted(pending, key=sort_key)[0]

    # ══════════════════════════════════════════════════════════════════════════
    # ESTÁNDARES DE LABOR
    # ══════════════════════════════════════════════════════════════════════════

    async def create_standard(
        self, tenant_id: uuid.UUID, data: dict, user_id: Optional[uuid.UUID] = None
    ) -> LaborStandard:
        dup = (await self.db.execute(
            select(func.count()).select_from(LaborStandard).where(and_(
                LaborStandard.tenant_id == tenant_id,
                LaborStandard.warehouse_id == data.get("warehouse_id"),
                LaborStandard.activity_type == data["activity_type"],
                LaborStandard.uom == data.get("uom", "unit"),
                LaborStandard.deleted_at.is_(None),
            ))
        )).scalar_one()
        if dup:
            raise LaborStandardError(
                f"Ya existe un estándar para '{data['activity_type']}' "
                f"({data.get('uom', 'unit')}) en ese alcance."
            )
        std = LaborStandard(
            id=uuid.uuid4(), tenant_id=tenant_id, created_by_id=user_id, **data
        )
        self.db.add(std)
        await self.db.commit()
        await self.db.refresh(std)
        return std

    async def _find_standard(
        self, tenant_id: uuid.UUID, warehouse_id: Optional[uuid.UUID],
        activity_type: str, uom: str,
    ) -> Optional[LaborStandard]:
        """Busca el estándar más específico: por bodega primero, luego global."""
        rows = (await self.db.execute(
            select(LaborStandard).where(and_(
                LaborStandard.tenant_id == tenant_id,
                LaborStandard.activity_type == activity_type,
                LaborStandard.uom == uom,
                LaborStandard.is_active.is_(True),
                LaborStandard.deleted_at.is_(None),
                or_(LaborStandard.warehouse_id == warehouse_id, LaborStandard.warehouse_id.is_(None)),
            ))
        )).scalars().all()
        if not rows:
            return None
        # Prioriza el estándar específico de la bodega sobre el global (NULL).
        rows.sort(key=lambda s: 0 if s.warehouse_id == warehouse_id else 1)
        return rows[0]

    # ══════════════════════════════════════════════════════════════════════════
    # CICLO DE VIDA DE TAREAS
    # ══════════════════════════════════════════════════════════════════════════

    async def create_task(
        self, tenant_id: uuid.UUID, data: dict, user_id: Optional[uuid.UUID] = None
    ) -> LaborTask:
        assigned_user = data.get("user_id")
        task = LaborTask(
            id=uuid.uuid4(), tenant_id=tenant_id, created_by_id=user_id,
            status="assigned" if assigned_user else "pending",
            assigned_at=_now() if assigned_user else None,
            **data,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def _get_task(self, tenant_id: uuid.UUID, task_id: uuid.UUID) -> LaborTask:
        task = (await self.db.execute(
            select(LaborTask).where(and_(
                LaborTask.id == task_id,
                LaborTask.tenant_id == tenant_id,
                LaborTask.deleted_at.is_(None),
            ))
        )).scalar_one_or_none()
        if not task:
            raise LaborServiceError("Tarea de labor no encontrada.")
        return task

    async def assign_task(
        self, tenant_id: uuid.UUID, task_id: uuid.UUID, operator_id: uuid.UUID,
        interleaved: bool = False,
    ) -> LaborTask:
        task = await self._get_task(tenant_id, task_id)
        if task.status not in ("pending", "assigned"):
            raise LaborTaskStateError(
                f"No se puede asignar una tarea en estado '{task.status}'."
            )
        task.user_id = operator_id
        task.status = "assigned"
        task.assigned_at = _now()
        task.is_interleaved = interleaved
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def start_task(
        self, tenant_id: uuid.UUID, task_id: uuid.UUID
    ) -> LaborTask:
        task = await self._get_task(tenant_id, task_id)
        if task.status not in ("assigned", "pending"):
            raise LaborTaskStateError(
                f"No se puede iniciar una tarea en estado '{task.status}'."
            )
        task.status = "in_progress"
        task.started_at = _now()
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def complete_task(
        self, tenant_id: uuid.UUID, task_id: uuid.UUID
    ) -> LaborTask:
        """Cierra la tarea y calcula tiempo real, estándar y desempeño."""
        task = await self._get_task(tenant_id, task_id)
        if task.status != "in_progress":
            raise LaborTaskStateError(
                f"Solo se completa una tarea 'in_progress' (actual: '{task.status}')."
            )
        completed = _now()
        task.completed_at = completed
        task.actual_minutes = self.compute_actual_minutes(task.started_at, completed)

        std = await self._find_standard(
            tenant_id, task.warehouse_id, task.activity_type, task.uom
        )
        if std is not None:
            task.standard_minutes = self.compute_standard_minutes(
                std.fixed_minutes, std.std_minutes_per_unit, task.quantity
            )
            task.performance_pct = self.compute_performance_pct(
                task.standard_minutes, task.actual_minutes
            )
        task.status = "completed"
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def suggest_next_task(
        self, tenant_id: uuid.UUID, warehouse_id: uuid.UUID,
        current_zone: Optional[str] = None,
    ) -> Optional[LaborTask]:
        """Devuelve la mejor tarea pendiente por proximidad (sin asignarla)."""
        pending = (await self.db.execute(
            select(LaborTask).where(and_(
                LaborTask.tenant_id == tenant_id,
                LaborTask.warehouse_id == warehouse_id,
                LaborTask.status == "pending",
                LaborTask.deleted_at.is_(None),
            ))
        )).scalars().all()
        return self.choose_next_task(list(pending), current_zone)

    async def assign_next_task(
        self, tenant_id: uuid.UUID, warehouse_id: uuid.UUID,
        operator_id: uuid.UUID, current_zone: Optional[str] = None,
    ) -> Optional[LaborTask]:
        """Interleaving: elige y asigna la siguiente mejor tarea al operario."""
        nxt = await self.suggest_next_task(tenant_id, warehouse_id, current_zone)
        if nxt is None:
            return None
        return await self.assign_task(
            tenant_id, nxt.id, operator_id, interleaved=True
        )

    # ══════════════════════════════════════════════════════════════════════════
    # KPIs / DASHBOARD
    # ══════════════════════════════════════════════════════════════════════════

    async def get_dashboard_metrics(
        self, tenant_id: uuid.UUID, warehouse_id: Optional[uuid.UUID] = None,
        window_days: int = 7,
    ) -> dict:
        since = _now() - timedelta(days=window_days)
        base = [LaborTask.tenant_id == tenant_id, LaborTask.deleted_at.is_(None)]
        if warehouse_id:
            base.append(LaborTask.warehouse_id == warehouse_id)

        async def _count(status: str) -> int:
            return (await self.db.execute(
                select(func.count(LaborTask.id)).where(and_(*base, LaborTask.status == status))
            )).scalar_one()

        tasks_pending = await _count("pending")
        tasks_in_progress = await _count("in_progress")

        done = [*base, LaborTask.status == "completed", LaborTask.completed_at >= since]
        agg = (await self.db.execute(
            select(
                func.count(LaborTask.id),
                func.avg(LaborTask.performance_pct),
                func.coalesce(func.sum(LaborTask.standard_minutes), 0),
                func.coalesce(func.sum(LaborTask.actual_minutes), 0),
            ).where(and_(*done))
        )).one()
        completed_n, avg_perf, sum_std_min, sum_act_min = agg
        std_hours = float(sum_std_min or 0) / 60.0
        act_hours = float(sum_act_min or 0) / 60.0
        efficiency = round(std_hours / act_hours * 100, 2) if act_hours > 0 else None

        # Por actividad
        by_activity = []
        for row in (await self.db.execute(
            select(
                LaborTask.activity_type,
                func.count(LaborTask.id),
                func.avg(LaborTask.performance_pct),
                func.coalesce(func.sum(LaborTask.standard_minutes), 0),
                func.coalesce(func.sum(LaborTask.actual_minutes), 0),
            ).where(and_(*done)).group_by(LaborTask.activity_type)
        )).all():
            by_activity.append({
                "activity_type": row[0],
                "tasks_completed": row[1],
                "avg_performance_pct": round(float(row[2]), 2) if row[2] is not None else None,
                "total_standard_hours": round(float(row[3] or 0) / 60.0, 2),
                "total_actual_hours": round(float(row[4] or 0) / 60.0, 2),
            })

        # Por operario (ranking)
        operators = []
        for row in (await self.db.execute(
            select(
                LaborTask.user_id,
                func.count(LaborTask.id),
                func.avg(LaborTask.performance_pct),
                func.coalesce(func.sum(LaborTask.actual_minutes), 0),
            ).where(and_(*done, LaborTask.user_id.isnot(None))).group_by(LaborTask.user_id)
        )).all():
            operators.append({
                "user_id": row[0],
                "tasks_completed": row[1],
                "avg_performance_pct": round(float(row[2]), 2) if row[2] is not None else None,
                "total_actual_hours": round(float(row[3] or 0) / 60.0, 2),
            })
        ranked = sorted(
            [o for o in operators if o["avg_performance_pct"] is not None],
            key=lambda o: o["avg_performance_pct"], reverse=True,
        )

        return {
            "window_days": window_days,
            "tasks_completed": completed_n or 0,
            "tasks_pending": tasks_pending or 0,
            "tasks_in_progress": tasks_in_progress or 0,
            "avg_performance_pct": round(float(avg_perf), 2) if avg_perf is not None else None,
            "total_standard_hours": round(std_hours, 2),
            "total_actual_hours": round(act_hours, 2),
            "labor_efficiency_pct": efficiency,
            "by_activity": by_activity,
            "top_operators": ranked[:5],
            "bottom_operators": list(reversed(ranked))[:5],
        }
