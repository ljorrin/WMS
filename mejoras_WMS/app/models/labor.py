"""
WMS Panamá — Labor Management (Gestión de Mano de Obra) — FR-090…093
=====================================================================
Estándares de labor de ingeniería (engineered labor standards), registro
de tareas ejecutadas por operario con cálculo de desempeño real vs. estándar,
y soporte para task interleaving (intercalado de tareas por proximidad).

Cierra una de las brechas frente a los WMS líderes (Manhattan, Blue Yonder,
SAP EWM): medir y optimizar el trabajo de las personas, no solo ejecutarlo.

Convenciones del proyecto:
- Columnas String para tipo/estado (sin enums nativos), igual que YMS.
- Multitenancy vía tenant_id (heredado de WMSTenantBase).
- Auditoría/soft-delete heredados de la base.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import WMSTenantBase


# Tipos de actividad medibles en bodega (usados por estándares y tareas).
ACTIVITY_TYPES = (
    "pick", "putaway", "receive", "pack", "cycle_count",
    "replenish", "loading", "unloading", "transfer",
)

# Estados del ciclo de vida de una tarea de labor.
LABOR_TASK_STATUSES = (
    "pending", "assigned", "in_progress", "completed", "cancelled",
)


class LaborStandard(WMSTenantBase):
    """
    Estándar de labor de ingeniería para un tipo de actividad.

    El tiempo esperado de una tarea = fixed_minutes + std_minutes_per_unit * cantidad.
    fixed_minutes modela el tiempo de preparación/desplazamiento fijo; el término
    por unidad modela el trabajo variable (p. ej. minutos por línea o por caja).

    Si warehouse_id es NULL, el estándar aplica a todas las bodegas del tenant.
    """
    __tablename__ = "labor_standards"

    warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=True, index=True,
        comment="Bodega a la que aplica. NULL = aplica a todo el tenant.",
    )
    activity_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="pick | putaway | receive | pack | cycle_count | replenish | loading | unloading | transfer",
    )
    uom: Mapped[str] = mapped_column(
        String(20), default="unit",
        comment="Unidad de medida del estándar: unit | line | case | pallet",
    )
    fixed_minutes: Mapped[float] = mapped_column(
        Numeric(10, 4), default=0,
        comment="Tiempo fijo de preparación/desplazamiento por tarea (minutos).",
    )
    std_minutes_per_unit: Mapped[float] = mapped_column(
        Numeric(10, 4), default=0,
        comment="Tiempo estándar por unidad de trabajo (minutos).",
    )
    description: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "warehouse_id", "activity_type", "uom",
            name="uq_labor_standard_scope",
        ),
        Index("ix_labor_standards_tenant_activity", "tenant_id", "activity_type"),
    )


class LaborTask(WMSTenantBase):
    """
    Unidad de trabajo ejecutable/medible por un operario.

    Puede crearse ya asignada o quedar 'pending' en la cola para que el motor de
    interleaving la asigne según proximidad. Al completarse se calcula el tiempo
    real, el tiempo estándar y el % de desempeño (performance_pct).
    """
    __tablename__ = "labor_tasks"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
        comment="Operario asignado. NULL mientras la tarea está en cola.",
    )
    activity_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Referencia polimórfica al objeto de trabajo (tarea de picking, putaway, etc.)
    reference_type: Mapped[Optional[str]] = mapped_column(
        String(30), comment="picking_task | putaway_task | grn | cycle_count | ..."
    )
    reference_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    reference_number: Mapped[Optional[str]] = mapped_column(String(50))

    # Ubicación/zona para el motor de interleaving (proximidad).
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True,
    )
    zone: Mapped[Optional[str]] = mapped_column(
        String(50), index=True, comment="Código de zona para agrupar por proximidad."
    )
    priority: Mapped[int] = mapped_column(
        Numeric(4, 0), default=5, comment="1 = más urgente … 9 = menos urgente."
    )
    quantity: Mapped[float] = mapped_column(
        Numeric(14, 4), default=1, comment="Unidades de trabajo (según uom del estándar).",
    )
    uom: Mapped[str] = mapped_column(String(20), default="unit")

    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True,
        comment="pending | assigned | in_progress | completed | cancelled",
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Resultados de medición (se calculan al completar).
    actual_minutes: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 4), comment="Tiempo real trabajado (completed_at - started_at)."
    )
    standard_minutes: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 4), comment="Tiempo esperado según el estándar de ingeniería."
    )
    performance_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(7, 2),
        comment="standard/actual*100. 100 = cumple; >100 más rápido; <100 más lento.",
    )
    is_interleaved: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="True si la tarea fue asignada por el motor de interleaving.",
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index("ix_labor_tasks_tenant_status", "tenant_id", "status"),
        Index("ix_labor_tasks_user_status", "user_id", "status"),
        Index("ix_labor_tasks_queue", "tenant_id", "warehouse_id", "status", "priority"),
    )
