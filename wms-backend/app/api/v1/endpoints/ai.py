"""
WMS Panama — Endpoints AI/ML API v1
=====================================
  /ai/forecast          — Demand forecasting (Prophet)
  /ai/alerts            — Replenishment alerts
  /ai/optimize          — Picking route optimization (OR-Tools)
  /ai/anomalies         — Anomaly detection
  /ai/assistant         — WMS RAG Chatbot (LangChain)
"""
from __future__ import annotations
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import CurrentUserDep, DBDep, PaginationDep, require_permission
from app.schemas.ai import (
    AnomalyResolveRequest, AnomalyScanRequest, AnomalyScanResponse,
    AlertResolveRequest, ChatRequest, ChatResponse,
    ConversationListResponse, ConversationResponse,
    ForecastListResponse, ForecastRequest, ForecastResponse,
    RouteOptimizeRequest, RouteOptimizationResponse,
)
from app.services.ai.forecasting import ForecastingService
from app.services.ai.optimizer import PickingRouteOptimizer
from app.services.ai.anomaly import AnomalyDetector
from app.services.ai.assistant import WMSAssistant

router = APIRouter()

def _forecast_svc(db: DBDep, u: CurrentUserDep) -> ForecastingService:
    return ForecastingService(db, u.tenant_id, u.id)

def _opt_svc(db: DBDep, u: CurrentUserDep) -> PickingRouteOptimizer:
    return PickingRouteOptimizer(db, u.tenant_id, u.id)

def _anomaly_svc(db: DBDep, u: CurrentUserDep) -> AnomalyDetector:
    return AnomalyDetector(db, u.tenant_id, u.id)

def _assistant_svc(db: DBDep, u: CurrentUserDep) -> WMSAssistant:
    return WMSAssistant(db, u.tenant_id, u.id)


# ══════════════════════════════════════════════════════════════════════════════
# FORECASTING
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/forecast",
    response_model=ForecastResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generar pronóstico de demanda (Prophet)",
    dependencies=[Depends(require_permission("ai:forecast:create"))],
)
async def generate_forecast(
    payload: ForecastRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _forecast_svc(db, current_user)
    try:
        result = await svc.generate_forecast(
            product_id=payload.product_id,
            warehouse_id=payload.warehouse_id,
            horizon=payload.horizon,
            retrain=payload.retrain,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get(
    "/forecast",
    response_model=ForecastListResponse,
    summary="Listar pronósticos generados",
    dependencies=[Depends(require_permission("ai:forecast:create"))],
)
async def list_forecasts(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    warehouse_id: Optional[UUID] = Query(None),
    product_id: Optional[UUID] = Query(None),
):
    svc = _forecast_svc(db, current_user)
    result = await svc.get_forecasts(
        warehouse_id=warehouse_id,
        product_id=product_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return ForecastListResponse(**result)


# ══════════════════════════════════════════════════════════════════════════════
# REPLENISHMENT ALERTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/alerts",
    summary="Listar alertas de reposición",
    dependencies=[Depends(require_permission("ai:forecast:create"))],
)
async def list_alerts(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    is_resolved: bool = Query(False),
    product_id: Optional[UUID] = Query(None),
):
    from sqlalchemy import select, func, and_
    from app.models.ai import ReplenishmentAlert

    filters = [
        ReplenishmentAlert.tenant_id == current_user.tenant_id,
        ReplenishmentAlert.is_resolved == is_resolved,
    ]
    if product_id:
        filters.append(ReplenishmentAlert.product_id == product_id)

    total = (await db.execute(
        select(func.count(ReplenishmentAlert.id)).where(and_(*filters))
    )).scalar_one()

    rows = (await db.execute(
        select(ReplenishmentAlert)
        .where(and_(*filters))
        .order_by(ReplenishmentAlert.created_at.desc())
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    )).scalars().all()

    return {
        "items": rows, "total": total,
        "page": pagination.page, "page_size": pagination.page_size,
    }


@router.post(
    "/alerts/{alert_id}/resolve",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Marcar alerta como resuelta",
    dependencies=[Depends(require_permission("ai:forecast:create"))],
)
async def resolve_alert(
    alert_id: UUID,
    payload: AlertResolveRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    from sqlalchemy import update
    from app.models.ai import ReplenishmentAlert
    from datetime import datetime, timezone

    await db.execute(
        update(ReplenishmentAlert)
        .where(and_(
            ReplenishmentAlert.id == alert_id,
            ReplenishmentAlert.tenant_id == current_user.tenant_id,
        ))
        .values(
            is_resolved=True,
            resolved_at=datetime.now(timezone.utc),
            resolved_by_id=current_user.id,
            action_taken=payload.action_taken,
        )
    )
    await db.commit()

from sqlalchemy import and_  # noqa: E402 import necesario para la closure

# ══════════════════════════════════════════════════════════════════════════════
# ROUTE OPTIMIZATION
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/optimize/routes",
    response_model=RouteOptimizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Optimizar rutas de picking con OR-Tools",
    dependencies=[Depends(require_permission("ai:optimize:create"))],
)
async def optimize_picking_routes(
    payload: RouteOptimizeRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _opt_svc(db, current_user)
    try:
        result = await svc.optimize_wave(
            wave_id=payload.wave_id,
            num_operators=payload.num_operators,
            algorithm=payload.algorithm,
            time_limit_seconds=payload.time_limit_seconds,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get(
    "/optimize/routes",
    summary="Historial de optimizaciones",
    dependencies=[Depends(require_permission("ai:optimize:create"))],
)
async def list_optimizations(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
):
    from sqlalchemy import select, func
    from app.models.ai import PickingRouteOptimization

    total = (await db.execute(
        select(func.count(PickingRouteOptimization.id)).where(
            PickingRouteOptimization.tenant_id == current_user.tenant_id
        )
    )).scalar_one()

    rows = (await db.execute(
        select(PickingRouteOptimization)
        .where(PickingRouteOptimization.tenant_id == current_user.tenant_id)
        .order_by(PickingRouteOptimization.computed_at.desc())
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    )).scalars().all()

    return {"items": rows, "total": total,
            "page": pagination.page, "page_size": pagination.page_size}


# ══════════════════════════════════════════════════════════════════════════════
# ANOMALY DETECTION
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/anomalies/scan",
    response_model=AnomalyScanResponse,
    summary="Ejecutar escaneo de anomalías",
    dependencies=[Depends(require_permission("ai:anomaly:manage"))],
)
async def scan_anomalies(
    payload: AnomalyScanRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _anomaly_svc(db, current_user)
    result = await svc.run_full_scan(
        warehouse_id=payload.warehouse_id,
        days_back=payload.days_back,
    )
    await db.commit()
    return result


@router.get(
    "/anomalies",
    summary="Listar anomalías detectadas",
    dependencies=[Depends(require_permission("ai:anomaly:manage"))],
)
async def list_anomalies(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    is_resolved: bool = Query(False),
    product_id: Optional[UUID] = Query(None),
):
    svc = _anomaly_svc(db, current_user)
    result = await svc.get_anomalies(
        is_resolved=is_resolved,
        product_id=product_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return result


@router.post(
    "/anomalies/{anomaly_id}/resolve",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Resolver anomalía",
    dependencies=[Depends(require_permission("ai:anomaly:manage"))],
)
async def resolve_anomaly(
    anomaly_id: UUID,
    payload: AnomalyResolveRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _anomaly_svc(db, current_user)
    await svc.resolve_anomaly(
        anomaly_id=anomaly_id,
        is_false_positive=payload.is_false_positive,
        resolution_notes=payload.resolution_notes,
    )
    await db.commit()


# ══════════════════════════════════════════════════════════════════════════════
# WMS ASSISTANT (RAG Chatbot)
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/assistant/chat",
    response_model=ChatResponse,
    summary="Enviar mensaje al asistente WMS",
    dependencies=[Depends(require_permission("ai:assistant:use"))],
)
async def chat(
    payload: ChatRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _assistant_svc(db, current_user)
    result = await svc.chat(
        message=payload.message,
        conversation_id=payload.conversation_id,
        context_type=payload.context_type,
        context_id=payload.context_id,
    )
    await db.commit()
    return result


@router.get(
    "/assistant/conversations",
    response_model=ConversationListResponse,
    summary="Listar conversaciones del usuario",
    dependencies=[Depends(require_permission("ai:assistant:use"))],
)
async def list_conversations(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
):
    svc = _assistant_svc(db, current_user)
    result = await svc.list_conversations(
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return ConversationListResponse(**result)


@router.get(
    "/assistant/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="Detalle de conversación con mensajes",
    dependencies=[Depends(require_permission("ai:assistant:use"))],
)
async def get_conversation(
    conversation_id: UUID,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _assistant_svc(db, current_user)
    conv = await svc.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada.")
    return conv
