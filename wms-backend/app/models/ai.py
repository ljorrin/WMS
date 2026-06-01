"""
WMS Panama — Modelos AI/ML
============================
Persiste los artefactos generados por los módulos de inteligencia:

  DemandForecast      — predicciones de demanda (Prophet)
  ReplenishmentAlert  — alertas de reposición generadas por AI
  PickingRouteOptimization — rutas de picking optimizadas (OR-Tools)
  AnomalyEvent        — anomalías detectadas en inventario / movimientos
  AIConversation      — historial de conversaciones con el asistente RAG
  AIConversationMessage — mensajes individuales de la conversación
"""

from __future__ import annotations

import enum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float,
    Integer, JSON, Numeric, String, Text,
    ForeignKey, Index,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.db.session import WMSBase


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class ForecastStatus(str, enum.Enum):
    PENDING    = "pending"
    RUNNING    = "running"
    COMPLETED  = "completed"
    FAILED     = "failed"


class ForecastHorizon(str, enum.Enum):
    WEEK_1  = "1w"
    WEEK_4  = "4w"
    WEEK_12 = "12w"
    WEEK_26 = "26w"


class AlertSeverity(str, enum.Enum):
    INFO     = "info"
    WARNING  = "warning"
    CRITICAL = "critical"


class AlertType(str, enum.Enum):
    STOCKOUT_RISK      = "stockout_risk"
    OVERSTOCK          = "overstock"
    SLOW_MOVER         = "slow_mover"
    NEAR_EXPIRY        = "near_expiry"
    DEMAND_SPIKE       = "demand_spike"
    ANOMALY_MOVEMENT   = "anomaly_movement"
    REPLENISHMENT      = "replenishment"


class AnomalyType(str, enum.Enum):
    UNUSUAL_QUANTITY   = "unusual_quantity"
    DUPLICATE_MOVEMENT = "duplicate_movement"
    NEGATIVE_STOCK     = "negative_stock"
    VELOCITY_CHANGE    = "velocity_change"
    PRICE_OUTLIER      = "price_outlier"


class RouteOptStatus(str, enum.Enum):
    PENDING   = "pending"
    OPTIMIZED = "optimized"
    APPLIED   = "applied"
    REJECTED  = "rejected"


class MessageRole(str, enum.Enum):
    USER      = "user"
    ASSISTANT = "assistant"
    SYSTEM    = "system"


# ══════════════════════════════════════════════════════════════════════════════
# DEMAND FORECAST
# ══════════════════════════════════════════════════════════════════════════════

class DemandForecast(WMSBase):
    """
    Predicción de demanda generada por Prophet para un producto/almacén.
    Guarda los valores predichos y los intervalos de confianza (yhat_lower/upper).
    """
    __tablename__ = "demand_forecasts"
    __table_args__ = (
        Index("ix_forecast_tenant_product", "tenant_id", "product_id"),
        Index("ix_forecast_tenant_status", "tenant_id", "status"),
    )

    tenant_id       = Column(PG_UUID(as_uuid=True), nullable=False)
    warehouse_id    = Column(PG_UUID(as_uuid=True), nullable=False)
    product_id      = Column(PG_UUID(as_uuid=True), nullable=False)

    # Configuración del modelo
    horizon         = Column(Enum(ForecastHorizon), nullable=False, default=ForecastHorizon.WEEK_4)
    status          = Column(Enum(ForecastStatus), default=ForecastStatus.PENDING)
    trained_on_days = Column(Integer, default=365, comment="Días de historial usados")

    # Resultado serializado como JSON: [{ds, yhat, yhat_lower, yhat_upper}]
    forecast_data   = Column(JSON, comment="Series de tiempo predicha")

    # Métricas del modelo
    mae             = Column(Float, comment="Mean Absolute Error")
    mape            = Column(Float, comment="Mean Absolute Percentage Error")
    rmse            = Column(Float, comment="Root Mean Square Error")
    model_params    = Column(JSON, comment="Parámetros Prophet usados")

    # Totales de la predicción
    total_predicted_units = Column(Numeric(18, 4))
    peak_week_units       = Column(Numeric(18, 4))
    avg_weekly_units      = Column(Numeric(18, 4))

    # Fechas
    period_start    = Column(DateTime(timezone=True))
    period_end      = Column(DateTime(timezone=True))
    generated_at    = Column(DateTime(timezone=True))
    error_message   = Column(Text)

    created_by_id   = Column(PG_UUID(as_uuid=True))


# ══════════════════════════════════════════════════════════════════════════════
# REPLENISHMENT ALERT
# ══════════════════════════════════════════════════════════════════════════════

class ReplenishmentAlert(WMSBase):
    """
    Alerta de reposición generada automáticamente por el motor AI.
    Puede derivar de forecasting (stockout_risk) o de reglas de negocio.
    """
    __tablename__ = "replenishment_alerts"
    __table_args__ = (
        Index("ix_alert_tenant_product", "tenant_id", "product_id"),
        Index("ix_alert_tenant_status", "tenant_id", "is_resolved"),
    )

    tenant_id            = Column(PG_UUID(as_uuid=True), nullable=False)
    warehouse_id         = Column(PG_UUID(as_uuid=True), nullable=False)
    product_id           = Column(PG_UUID(as_uuid=True), nullable=False)
    forecast_id          = Column(PG_UUID(as_uuid=True), ForeignKey("demand_forecasts.id"), nullable=True)

    alert_type           = Column(Enum(AlertType), nullable=False)
    severity             = Column(Enum(AlertSeverity), nullable=False)

    # Datos de la alerta
    current_stock        = Column(Numeric(18, 4))
    days_of_stock        = Column(Float, comment="Días de stock actual según demanda prevista")
    recommended_qty      = Column(Numeric(18, 4), comment="Cantidad de reposición recomendada")
    recommended_order_date = Column(DateTime(timezone=True))
    lead_time_days       = Column(Integer, comment="Lead time del proveedor en días")

    # Financiero
    stockout_cost_est    = Column(Numeric(18, 2), comment="Costo estimado de quiebre de stock")
    overstock_cost_est   = Column(Numeric(18, 2), comment="Costo estimado de sobrestock")

    title                = Column(String(200), nullable=False)
    description          = Column(Text)
    recommendation       = Column(Text)

    is_resolved          = Column(Boolean, default=False)
    resolved_at          = Column(DateTime(timezone=True))
    resolved_by_id       = Column(PG_UUID(as_uuid=True))
    action_taken         = Column(String(200))

    # Relaciones
    forecast             = relationship("DemandForecast")


# ══════════════════════════════════════════════════════════════════════════════
# PICKING ROUTE OPTIMIZATION (OR-Tools)
# ══════════════════════════════════════════════════════════════════════════════

class PickingRouteOptimization(WMSBase):
    """
    Resultado de la optimización de rutas de picking calculada por OR-Tools.
    Guarda la secuencia óptima de ubicaciones para minimizar distancia recorrida.
    """
    __tablename__ = "picking_route_optimizations"
    __table_args__ = (
        Index("ix_route_opt_wave", "wave_id"),
        Index("ix_route_opt_tenant", "tenant_id", "status"),
    )

    tenant_id            = Column(PG_UUID(as_uuid=True), nullable=False)
    warehouse_id         = Column(PG_UUID(as_uuid=True), nullable=False)
    wave_id              = Column(PG_UUID(as_uuid=True), nullable=True, comment="Wave de picking relacionada")

    status               = Column(Enum(RouteOptStatus), default=RouteOptStatus.PENDING)

    # Parámetros de la optimización
    num_operators        = Column(Integer, default=1)
    num_locations        = Column(Integer)
    algorithm            = Column(String(50), default="PATH_CHEAPEST_ARC")
    time_limit_seconds   = Column(Integer, default=30)

    # Resultado: lista ordenada de ubicaciones por operador
    # Formato: [{operator_id, route: [location_id, ...], distance_m, est_minutes}]
    routes               = Column(JSON)

    # Métricas
    total_distance_m     = Column(Float, comment="Distancia total optimizada en metros")
    estimated_minutes    = Column(Integer)
    savings_pct          = Column(Float, comment="% ahorro vs ruta no optimizada")
    solver_status        = Column(String(50), comment="OPTIMAL, FEASIBLE, INFEASIBLE")

    computed_at          = Column(DateTime(timezone=True))
    applied_at           = Column(DateTime(timezone=True))
    created_by_id        = Column(PG_UUID(as_uuid=True))


# ══════════════════════════════════════════════════════════════════════════════
# ANOMALY EVENT
# ══════════════════════════════════════════════════════════════════════════════

class AnomalyEvent(WMSBase):
    """
    Anomalía detectada en los datos de inventario o movimientos.
    Usa Z-Score, IQR o modelos de isolation forest (configurable).
    """
    __tablename__ = "anomaly_events"
    __table_args__ = (
        Index("ix_anomaly_tenant_product", "tenant_id", "product_id"),
        Index("ix_anomaly_tenant_resolved", "tenant_id", "is_resolved"),
    )

    tenant_id            = Column(PG_UUID(as_uuid=True), nullable=False)
    warehouse_id         = Column(PG_UUID(as_uuid=True), nullable=False)
    product_id           = Column(PG_UUID(as_uuid=True), nullable=True)

    anomaly_type         = Column(Enum(AnomalyType), nullable=False)
    severity             = Column(Enum(AlertSeverity), nullable=False)

    # Referencia al movimiento/ajuste anómalo
    reference_type       = Column(String(50), comment="movement, adjustment, grn_line")
    reference_id         = Column(PG_UUID(as_uuid=True))

    # Datos de la anomalía
    detected_value       = Column(Float, comment="Valor detectado como anómalo")
    expected_value       = Column(Float, comment="Valor esperado según el modelo")
    z_score              = Column(Float, comment="Z-Score de la anomalía")
    confidence           = Column(Float, comment="Confianza del modelo 0-1")

    description          = Column(Text, nullable=False)
    context_data         = Column(JSON, comment="Datos adicionales del contexto")

    is_resolved          = Column(Boolean, default=False)
    is_false_positive    = Column(Boolean, default=False)
    resolved_at          = Column(DateTime(timezone=True))
    resolved_by_id       = Column(PG_UUID(as_uuid=True))
    resolution_notes     = Column(Text)

    detected_at          = Column(DateTime(timezone=True))


# ══════════════════════════════════════════════════════════════════════════════
# AI CONVERSATION (RAG Assistant)
# ══════════════════════════════════════════════════════════════════════════════

class AIConversation(WMSBase):
    """Sesión de conversación con el asistente WMS basado en LangChain RAG."""
    __tablename__ = "ai_conversations"
    __table_args__ = (
        Index("ix_conv_tenant_user", "tenant_id", "user_id"),
    )

    tenant_id       = Column(PG_UUID(as_uuid=True), nullable=False)
    user_id         = Column(PG_UUID(as_uuid=True), nullable=False)
    title           = Column(String(200))
    context_type    = Column(String(50), comment="general, inventory, inbound, outbound")
    context_id      = Column(PG_UUID(as_uuid=True), comment="ID del objeto en contexto (SO, PO, etc.)")
    is_active       = Column(Boolean, default=True)
    message_count   = Column(Integer, default=0)
    total_tokens    = Column(Integer, default=0)

    messages        = relationship("AIConversationMessage", back_populates="conversation",
                                   cascade="all, delete-orphan",
                                   order_by="AIConversationMessage.created_at")


class AIConversationMessage(WMSBase):
    """Mensaje individual dentro de una conversación AI."""
    __tablename__ = "ai_conversation_messages"
    __table_args__ = (
        Index("ix_msg_conversation", "conversation_id"),
    )

    tenant_id       = Column(PG_UUID(as_uuid=True), nullable=False)
    conversation_id = Column(PG_UUID(as_uuid=True),
                             ForeignKey("ai_conversations.id"), nullable=False)
    role            = Column(Enum(MessageRole), nullable=False)
    content         = Column(Text, nullable=False)
    tokens_used     = Column(Integer, default=0)

    # Fuentes usadas por el RAG (chunks de documentos)
    sources         = Column(JSON, comment="[{doc_id, chunk, score}]")
    model_used      = Column(String(50))
    latency_ms      = Column(Integer)

    conversation    = relationship("AIConversation", back_populates="messages")
