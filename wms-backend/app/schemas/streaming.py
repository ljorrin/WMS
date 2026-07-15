"""
WMS Panamá — Schemas Pydantic: Order Streaming / Waveless — FR-055
===================================================================
Liberación continua de picking (sin olas): las órdenes se encolan como tareas
waveless y se despachan de a una al operario según prioridad y proximidad.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class EnqueueOrderRequest(BaseModel):
    so_id: uuid.UUID = Field(..., description="Orden de venta a encolar como waveless.")


class StreamNextRequest(BaseModel):
    warehouse_id: uuid.UUID
    operator_id: Optional[uuid.UUID] = Field(None, description="Por defecto: el usuario actual.")
    current_pick_sequence: Optional[int] = Field(
        None, description="Secuencia de picking de la ubicación actual del operario."
    )
    max_wip: int = Field(1, ge=1, le=20, description="Tareas simultáneas máximas por operario (WIP).")


class PickingTaskLite(BaseModel):
    id: uuid.UUID
    so_id: uuid.UUID
    so_line_id: uuid.UUID
    product_id: uuid.UUID
    quantity_requested: Decimal
    from_location_id: Optional[uuid.UUID] = None
    status: str
    priority: int
    assigned_to_id: Optional[uuid.UUID] = None
    wave_id: Optional[uuid.UUID] = None
    started_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class EnqueueOrderResult(BaseModel):
    so_id: uuid.UUID
    tasks_created: int
    tasks: list[PickingTaskLite] = []


class StreamingMetrics(BaseModel):
    queue_pending: int = Field(..., description="Tareas waveless pendientes sin asignar.")
    in_progress: int
    operators_active: int
    wip_by_operator: dict = {}
