"""
WMS Panamá — Slotting Dinámico Endpoints — FR-094…097
======================================================
Política de slotting, ejecución del análisis ABC, recomendaciones de re-slot
(aplicar/rechazar) y dashboard. Cierra la brecha de slotting dinámico frente a
los WMS líderes.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select

from app.core.dependencies import CurrentUserDep, DBDep, PaginationDep, require_permission
from app.core.exceptions import SlottingServiceError, SlottingStateError
from app.models.slotting import SlottingPolicy, SlottingRecommendation
from app.schemas.slotting import (
    SlottingAnalyzeRequest, SlottingAnalyzeResult, SlottingDashboardMetrics,
    SlottingPolicyResponse, SlottingPolicyUpsert, SlottingRecommendationResponse,
)
from app.services.slotting_service import SlottingService

router = APIRouter()


def _svc(db) -> SlottingService:
    return SlottingService(db)


# ── Política ───────────────────────────────────────────────────────────────────
@router.put(
    "/policy", response_model=SlottingPolicyResponse, summary="Crear/actualizar política de slotting",
    dependencies=[Depends(require_permission("slotting:manage"))],
)
async def upsert_policy(
    payload: SlottingPolicyUpsert, db: DBDep, current_user: CurrentUserDep,
) -> SlottingPolicyResponse:
    policy = await _svc(db).upsert_policy(
        current_user.tenant_id, payload.model_dump(), current_user.id
    )
    return policy


@router.get(
    "/policy", summary="Listar políticas de slotting",
    dependencies=[Depends(require_permission("slotting:read"))],
)
async def list_policies(db: DBDep, current_user: CurrentUserDep) -> dict:
    rows = (await db.execute(select(SlottingPolicy).where(and_(
        SlottingPolicy.tenant_id == current_user.tenant_id,
        SlottingPolicy.deleted_at.is_(None),
    )))).scalars().all()
    return {"items": [SlottingPolicyResponse.model_validate(r) for r in rows]}


# ── Análisis ───────────────────────────────────────────────────────────────────
@router.post(
    "/analyze", response_model=SlottingAnalyzeResult,
    summary="Ejecutar análisis ABC y generar recomendaciones",
    dependencies=[Depends(require_permission("slotting:run"))],
)
async def analyze(
    payload: SlottingAnalyzeRequest, db: DBDep, current_user: CurrentUserDep,
) -> SlottingAnalyzeResult:
    result = await _svc(db).analyze_and_generate(
        current_user.tenant_id, payload.warehouse_id,
        window_days=payload.window_days, persist=payload.persist,
    )
    return SlottingAnalyzeResult(**result)


# ── Recomendaciones ────────────────────────────────────────────────────────────
@router.get(
    "/recommendations", summary="Listar recomendaciones de slotting",
    dependencies=[Depends(require_permission("slotting:read"))],
)
async def list_recommendations(
    db: DBDep, current_user: CurrentUserDep, pagination: PaginationDep,
    warehouse_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    abc_class: Optional[str] = Query(None),
) -> dict:
    filters = [
        SlottingRecommendation.tenant_id == current_user.tenant_id,
        SlottingRecommendation.deleted_at.is_(None),
    ]
    if warehouse_id:
        filters.append(SlottingRecommendation.warehouse_id == warehouse_id)
    if status_filter:
        filters.append(SlottingRecommendation.status == status_filter)
    if abc_class:
        filters.append(SlottingRecommendation.abc_class == abc_class)
    total = (await db.execute(
        select(func.count(SlottingRecommendation.id)).where(and_(*filters))
    )).scalar_one()
    rows = (await db.execute(
        select(SlottingRecommendation).where(and_(*filters))
        .order_by(SlottingRecommendation.velocity_score.desc().nullslast())
        .offset(pagination.offset).limit(pagination.limit)
    )).scalars().all()
    return {
        "items": [SlottingRecommendationResponse.model_validate(r) for r in rows],
        "total": total, "page": pagination.page, "page_size": pagination.page_size,
    }


async def _rec_action(db, tenant_id, rec_id, action, user_id):
    try:
        return await getattr(_svc(db), action)(tenant_id, rec_id, user_id)
    except SlottingStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except SlottingServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/recommendations/{rec_id}/apply", response_model=SlottingRecommendationResponse,
    summary="Aplicar recomendación",
    dependencies=[Depends(require_permission("slotting:manage"))],
)
async def apply_recommendation(
    rec_id: uuid.UUID, db: DBDep, current_user: CurrentUserDep,
) -> SlottingRecommendationResponse:
    return await _rec_action(db, current_user.tenant_id, rec_id, "apply_recommendation", current_user.id)


@router.post(
    "/recommendations/{rec_id}/reject", response_model=SlottingRecommendationResponse,
    summary="Rechazar recomendación",
    dependencies=[Depends(require_permission("slotting:manage"))],
)
async def reject_recommendation(
    rec_id: uuid.UUID, db: DBDep, current_user: CurrentUserDep,
) -> SlottingRecommendationResponse:
    return await _rec_action(db, current_user.tenant_id, rec_id, "reject_recommendation", current_user.id)


# ── Dashboard ──────────────────────────────────────────────────────────────────
@router.get(
    "/dashboard", response_model=SlottingDashboardMetrics,
    summary="KPIs de slotting", dependencies=[Depends(require_permission("slotting:read"))],
)
async def dashboard(
    db: DBDep, current_user: CurrentUserDep,
    warehouse_id: Optional[uuid.UUID] = Query(None),
) -> SlottingDashboardMetrics:
    metrics = await _svc(db).get_dashboard_metrics(current_user.tenant_id, warehouse_id)
    return SlottingDashboardMetrics(**metrics)
