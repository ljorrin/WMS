"""
WMS Panamá — Schemas Pydantic: Labor Management — FR-090…093
=============================================================
Contratos de entrada/salida para estándares de labor, tareas y KPIs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

_ACTIVITY = r"^(pick|putaway|receive|pack|cycle_count|replenish|loading|unloading|transfer)$"


# ── Estándares de labor ────────────────────────────────────────────────────────
class LaborStandardCreate(BaseModel):
    activity_type: str = Field(..., pattern=_ACTIVITY)
    warehouse_id: Optional[uuid.UUID] = Field(
        None, description="NULL = aplica a todas las bodegas del tenant."
    )
    uom: str = Field("unit", max_length=20)
    fixed_minutes: Decimal = Field(0, ge=0, description="Minutos fijos por tarea.")
    std_minutes_per_unit: Decimal = Field(0, ge=0, description="Minutos por unidad.")
    description: Optional[str] = Field(None, max_length=255)


class LaborStandardUpdate(BaseModel):
    uom: Optional[str] = Field(None, max_length=20)
    fixed_minutes: Optional[Decimal] = Field(None, ge=0)
    std_minutes_per_unit: Optional[Decimal] = Field(None, ge=0)
    description: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None


class LaborStandardResponse(BaseModel):
    id: uuid.UUID
    warehouse_id: Optional[uuid.UUID] = None
    activity_type: str
    uom: str
    fixed_minutes: Decimal
    std_minutes_per_unit: Decimal
    description: Optional[str] = None
    is_active: bool
    model_config = {"from_attributes": True}


# ── Tareas de labor ────────────────────────────────────────────────────────────
class LaborTaskCreate(BaseModel):
    warehouse_id: uuid.UUID
    activity_type: str = Field(..., pattern=_ACTIVITY)
    quantity: Decimal = Field(1, gt=0)
    uom: str = Field("unit", max_length=20)
    user_id: Optional[uuid.UUID] = Field(None, description="Si se omite, queda en cola.")
    reference_type: Optional[str] = Field(None, max_length=30)
    reference_id: Optional[uuid.UUID] = None
    reference_number: Optional[str] = Field(None, max_length=50)
    location_id: Optional[uuid.UUID] = None
    zone: Optional[str] = Field(None, max_length=50)
    priority: int = Field(5, ge=1, le=9)
    notes: Optional[str] = None


class LaborTaskResponse(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    activity_type: str
    reference_type: Optional[str] = None
    reference_id: Optional[uuid.UUID] = None
    reference_number: Optional[str] = None
    location_id: Optional[uuid.UUID] = None
    zone: Optional[str] = None
    priority: int
    quantity: Decimal
    uom: str
    status: str
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    actual_minutes: Optional[Decimal] = None
    standard_minutes: Optional[Decimal] = None
    performance_pct: Optional[Decimal] = None
    is_interleaved: bool = False
    model_config = {"from_attributes": True}


# ── KPIs / Dashboard ───────────────────────────────────────────────────────────
class LaborActivityKPI(BaseModel):
    activity_type: str
    tasks_completed: int
    avg_performance_pct: Optional[float] = None
    total_standard_hours: float
    total_actual_hours: float


class LaborOperatorKPI(BaseModel):
    user_id: uuid.UUID
    tasks_completed: int
    avg_performance_pct: Optional[float] = None
    total_actual_hours: float


class LaborDashboardMetrics(BaseModel):
    window_days: int
    tasks_completed: int
    tasks_pending: int
    tasks_in_progress: int
    avg_performance_pct: Optional[float] = None
    total_standard_hours: float
    total_actual_hours: float
    labor_efficiency_pct: Optional[float] = Field(
        None, description="Horas estándar / horas reales * 100 (global)."
    )
    by_activity: list[LaborActivityKPI] = []
    top_operators: list[LaborOperatorKPI] = []
    bottom_operators: list[LaborOperatorKPI] = []
