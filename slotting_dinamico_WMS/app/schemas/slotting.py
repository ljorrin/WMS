"""
WMS Panamá — Schemas Pydantic: Slotting Dinámico — FR-094…097
==============================================================
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ── Política ───────────────────────────────────────────────────────────────────
class SlottingPolicyUpsert(BaseModel):
    warehouse_id: Optional[uuid.UUID] = Field(None, description="NULL = política global.")
    strategy: str = Field("velocity_abc", pattern="^(velocity_abc|manual)$")
    velocity_window_days: int = Field(90, ge=7, le=730)
    abc_a_threshold: Decimal = Field(Decimal("0.80"), gt=0, lt=1)
    abc_b_threshold: Decimal = Field(Decimal("0.95"), gt=0, le=1)
    golden_zone_code: Optional[str] = Field(None, max_length=10)
    bulk_zone_code: Optional[str] = Field(None, max_length=10)
    is_active: bool = True


class SlottingPolicyResponse(BaseModel):
    id: uuid.UUID
    warehouse_id: Optional[uuid.UUID] = None
    strategy: str
    velocity_window_days: int
    abc_a_threshold: Decimal
    abc_b_threshold: Decimal
    golden_zone_code: Optional[str] = None
    bulk_zone_code: Optional[str] = None
    is_active: bool
    model_config = {"from_attributes": True}


# ── Análisis ───────────────────────────────────────────────────────────────────
class SlottingAnalyzeRequest(BaseModel):
    warehouse_id: uuid.UUID
    window_days: Optional[int] = Field(None, ge=7, le=730)
    persist: bool = Field(True, description="Si False, solo calcula sin crear recomendaciones.")


class SlottingAnalyzeResult(BaseModel):
    window_days: int
    products_analyzed: int
    abc_counts: dict
    recommendations_created: int
    golden_zone: Optional[str] = None
    bulk_zone: Optional[str] = None


# ── Recomendaciones ────────────────────────────────────────────────────────────
class SlottingRecommendationResponse(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    abc_class: Optional[str] = None
    velocity_score: Optional[Decimal] = None
    pick_count: Optional[int] = None
    current_location_id: Optional[uuid.UUID] = None
    current_zone_code: Optional[str] = None
    recommended_location_id: Optional[uuid.UUID] = None
    recommended_zone_code: Optional[str] = None
    reason: Optional[str] = None
    score_delta: Optional[Decimal] = None
    status: str
    applied_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class SlottingDashboardMetrics(BaseModel):
    pending: int
    applied: int
    rejected: int
    pending_by_class: dict
