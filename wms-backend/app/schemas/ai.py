"""
WMS Panama — Schemas AI/ML (Pydantic v2)
"""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

# ── Forecasting ───────────────────────────────────────
class ForecastRequest(BaseModel):
    product_id: UUID
    warehouse_id: UUID
    horizon: str = Field("4w", pattern="^(1w|4w|12w|26w)$")
    retrain: bool = False

class ForecastPoint(BaseModel):
    ds: str
    yhat: float
    yhat_lower: float
    yhat_upper: float

class ForecastMetrics(BaseModel):
    mae: Optional[float]
    mape: Optional[float]
    rmse: Optional[float]

class ForecastResponse(BaseModel):
    forecast_id: str
    product_id: str
    warehouse_id: str
    horizon: str
    forecast: List[ForecastPoint]
    metrics: ForecastMetrics
    alerts_generated: int

class ForecastListItem(BaseModel):
    id: UUID
    product_id: UUID
    warehouse_id: UUID
    horizon: str
    status: str
    mae: Optional[float]
    mape: Optional[float]
    total_predicted_units: Optional[Decimal]
    avg_weekly_units: Optional[Decimal]
    generated_at: Optional[datetime]
    model_config = {"from_attributes": True}

class ForecastListResponse(BaseModel):
    items: List[ForecastListItem]
    total: int; page: int; page_size: int

# ── Replenishment Alerts ───────────────────────────────
class ReplenishmentAlertResponse(BaseModel):
    id: UUID
    product_id: UUID
    warehouse_id: UUID
    alert_type: str
    severity: str
    title: str
    description: Optional[str]
    recommendation: Optional[str]
    current_stock: Optional[Decimal]
    days_of_stock: Optional[float]
    recommended_qty: Optional[Decimal]
    recommended_order_date: Optional[datetime]
    is_resolved: bool
    created_at: datetime
    model_config = {"from_attributes": True}

class AlertResolveRequest(BaseModel):
    action_taken: str = Field(..., max_length=200)

# ── Route Optimization ────────────────────────────────
class RouteOptimizeRequest(BaseModel):
    wave_id: UUID
    num_operators: int = Field(1, ge=1, le=20)
    algorithm: str = Field("PATH_CHEAPEST_ARC",
        pattern="^(PATH_CHEAPEST_ARC|SAVINGS|GUIDED_LOCAL_SEARCH)$")
    time_limit_seconds: int = Field(30, ge=5, le=120)

class RouteStop(BaseModel):
    location_id: str
    location_code: str
    task_id: Optional[str]

class OperatorRoute(BaseModel):
    operator_id: int
    route: List[RouteStop]
    distance_m: float
    est_minutes: int

class RouteOptimizationResponse(BaseModel):
    optimization_id: str
    wave_id: str
    routes: List[OperatorRoute]
    total_distance_m: float
    estimated_minutes: int
    savings_pct: float
    solver_status: str
    algorithm: str

# ── Anomaly Detection ─────────────────────────────────
class AnomalyScanRequest(BaseModel):
    warehouse_id: Optional[UUID] = None
    days_back: int = Field(7, ge=1, le=90)

class AnomalyResponse(BaseModel):
    id: UUID
    anomaly_type: str
    severity: str
    description: str
    detected_value: Optional[float]
    expected_value: Optional[float]
    z_score: Optional[float]
    confidence: Optional[float]
    is_resolved: bool
    is_false_positive: bool
    detected_at: Optional[datetime]
    product_id: Optional[UUID]
    model_config = {"from_attributes": True}

class AnomalyResolveRequest(BaseModel):
    is_false_positive: bool
    resolution_notes: str = Field(..., max_length=1000)

class AnomalyScanResponse(BaseModel):
    scanned_days: int
    total_anomalies: int
    breakdown: dict[str, int]
    anomalies: List[dict]

# ── Assistant ─────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[UUID] = None
    context_type: Optional[str] = Field(None, max_length=50)
    context_id: Optional[UUID] = None

class ChatResponse(BaseModel):
    conversation_id: str
    response: str
    sources: List[Any] = []
    latency_ms: int
    tokens_used: int

class ConversationResponse(BaseModel):
    id: UUID
    title: Optional[str]
    context_type: Optional[str]
    message_count: int
    total_tokens: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class ConversationListResponse(BaseModel):
    items: List[ConversationResponse]
    total: int; page: int; page_size: int
