"""
WMS Panamá — Labor Management Endpoints — FR-090…093
=====================================================
Estándares de labor, cola de tareas, ejecución, interleaving y dashboard de
productividad. Cierra la brecha de "labor management" frente a los WMS líderes.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select

from app.core.dependencies import CurrentUserDep, DBDep, PaginationDep, require_permission
from app.core.exceptions import LaborServiceError, LaborStandardError, LaborTaskStateError
from app.models.labor import LaborStandard, LaborTask
from app.schemas.labor import (
    LaborDashboardMetrics, LaborStandardCreate, LaborStandardResponse,
    LaborStandardUpdate, LaborTaskCreate, LaborTaskResponse,
)
from app.services.labor_service import LaborService

router = APIRouter()


def _svc(db) -> LaborService:
    return LaborService(db)


# ── Estándares de labor ────────────────────────────────────────────────────────
@router.post(
    "/standards", response_model=LaborStandardResponse,
    status_code=status.HTTP_201_CREATED, summary="Crear estándar de labor",
    dependencies=[Depends(require_permission("labor:standard:manage"))],
)
async def create_standard(
    payload: LaborStandardCreate, db: DBDep, current_user: CurrentUserDep,
) -> LaborStandardResponse:
    try:
        std = await _svc(db).create_standard(
            current_user.tenant_id, payload.model_dump(), current_user.id
        )
    except LaborStandardError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return std


@router.get(
    "/standards", summary="Listar estándares de labor",
    dependencies=[Depends(require_permission("labor:read"))],
)
async def list_standards(
    db: DBDep, current_user: CurrentUserDep, pagination: PaginationDep,
    activity_type: Optional[str] = Query(None),
) -> dict:
    filters = [
        LaborStandard.tenant_id == current_user.tenant_id,
        LaborStandard.deleted_at.is_(None),
    ]
    if activity_type:
        filters.append(LaborStandard.activity_type == activity_type)
    total = (await db.execute(
        select(func.count(LaborStandard.id)).where(and_(*filters))
    )).scalar_one()
    rows = (await db.execute(
        select(LaborStandard).where(and_(*filters))
        .order_by(LaborStandard.activity_type)
        .offset(pagination.offset).limit(pagination.limit)
    )).scalars().all()
    return {
        "items": [LaborStandardResponse.model_validate(r) for r in rows],
        "total": total, "page": pagination.page, "page_size": pagination.page_size,
    }


@router.put(
    "/standards/{standard_id}", response_model=LaborStandardResponse,
    summary="Editar estándar de labor",
    dependencies=[Depends(require_permission("labor:standard:manage"))],
)
async def update_standard(
    standard_id: uuid.UUID, payload: LaborStandardUpdate,
    db: DBDep, current_user: CurrentUserDep,
) -> LaborStandardResponse:
    std = (await db.execute(select(LaborStandard).where(and_(
        LaborStandard.id == standard_id,
        LaborStandard.tenant_id == current_user.tenant_id,
        LaborStandard.deleted_at.is_(None),
    )))).scalar_one_or_none()
    if not std:
        raise HTTPException(status_code=404, detail="Estándar no encontrado.")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(std, field, value)
    std.updated_by_id = current_user.id
    await db.commit(); await db.refresh(std)
    return std


# ── Tareas de labor ────────────────────────────────────────────────────────────
@router.post(
    "/tasks", response_model=LaborTaskResponse,
    status_code=status.HTTP_201_CREATED, summary="Crear/encolar tarea de labor",
    dependencies=[Depends(require_permission("labor:task:manage"))],
)
async def create_task(
    payload: LaborTaskCreate, db: DBDep, current_user: CurrentUserDep,
) -> LaborTaskResponse:
    task = await _svc(db).create_task(
        current_user.tenant_id, payload.model_dump(exclude_none=True), current_user.id
    )
    return task


@router.get(
    "/tasks", summary="Listar tareas de labor",
    dependencies=[Depends(require_permission("labor:read"))],
)
async def list_tasks(
    db: DBDep, current_user: CurrentUserDep, pagination: PaginationDep,
    warehouse_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    user_id: Optional[uuid.UUID] = Query(None),
) -> dict:
    filters = [
        LaborTask.tenant_id == current_user.tenant_id,
        LaborTask.deleted_at.is_(None),
    ]
    if warehouse_id:
        filters.append(LaborTask.warehouse_id == warehouse_id)
    if status_filter:
        filters.append(LaborTask.status == status_filter)
    if user_id:
        filters.append(LaborTask.user_id == user_id)
    total = (await db.execute(
        select(func.count(LaborTask.id)).where(and_(*filters))
    )).scalar_one()
    rows = (await db.execute(
        select(LaborTask).where(and_(*filters))
        .order_by(LaborTask.priority, LaborTask.created_at)
        .offset(pagination.offset).limit(pagination.limit)
    )).scalars().all()
    return {
        "items": [LaborTaskResponse.model_validate(r) for r in rows],
        "total": total, "page": pagination.page, "page_size": pagination.page_size,
    }


async def _task_action(db, tenant_id, task_id, action, current_user, **kwargs):
    svc = _svc(db)
    try:
        method = getattr(svc, action)
        return await method(tenant_id, task_id, **kwargs)
    except LaborTaskStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except LaborServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/tasks/{task_id}/assign", response_model=LaborTaskResponse, summary="Asignar operario",
    dependencies=[Depends(require_permission("labor:task:manage"))],
)
async def assign_task(
    task_id: uuid.UUID, operator_id: uuid.UUID, db: DBDep, current_user: CurrentUserDep,
) -> LaborTaskResponse:
    return await _task_action(
        db, current_user.tenant_id, task_id, "assign_task", current_user,
        operator_id=operator_id,
    )


@router.post(
    "/tasks/{task_id}/start", response_model=LaborTaskResponse, summary="Iniciar tarea",
    dependencies=[Depends(require_permission("labor:task:execute"))],
)
async def start_task(
    task_id: uuid.UUID, db: DBDep, current_user: CurrentUserDep,
) -> LaborTaskResponse:
    return await _task_action(db, current_user.tenant_id, task_id, "start_task", current_user)


@router.post(
    "/tasks/{task_id}/complete", response_model=LaborTaskResponse,
    summary="Completar tarea (calcula desempeño)",
    dependencies=[Depends(require_permission("labor:task:execute"))],
)
async def complete_task(
    task_id: uuid.UUID, db: DBDep, current_user: CurrentUserDep,
) -> LaborTaskResponse:
    return await _task_action(db, current_user.tenant_id, task_id, "complete_task", current_user)


# ── Interleaving ───────────────────────────────────────────────────────────────
@router.get(
    "/next-task", summary="Sugerir siguiente tarea por proximidad (interleaving)",
    dependencies=[Depends(require_permission("labor:read"))],
)
async def next_task(
    db: DBDep, current_user: CurrentUserDep,
    warehouse_id: uuid.UUID = Query(...),
    zone: Optional[str] = Query(None, description="Zona actual del operario."),
) -> Optional[LaborTaskResponse]:
    task = await _svc(db).suggest_next_task(current_user.tenant_id, warehouse_id, zone)
    return LaborTaskResponse.model_validate(task) if task else None


@router.post(
    "/next-task/assign", response_model=Optional[LaborTaskResponse],
    summary="Asignar la siguiente mejor tarea al operario (interleaving)",
    dependencies=[Depends(require_permission("labor:task:execute"))],
)
async def assign_next_task(
    db: DBDep, current_user: CurrentUserDep,
    warehouse_id: uuid.UUID = Query(...),
    operator_id: Optional[uuid.UUID] = Query(None, description="Por defecto: el usuario actual."),
    zone: Optional[str] = Query(None),
) -> Optional[LaborTaskResponse]:
    op = operator_id or current_user.id
    task = await _svc(db).assign_next_task(current_user.tenant_id, warehouse_id, op, zone)
    return LaborTaskResponse.model_validate(task) if task else None


# ── Dashboard de productividad ─────────────────────────────────────────────────
@router.get(
    "/dashboard", response_model=LaborDashboardMetrics,
    summary="KPIs de productividad de mano de obra",
    dependencies=[Depends(require_permission("labor:read"))],
)
async def dashboard(
    db: DBDep, current_user: CurrentUserDep,
    warehouse_id: Optional[uuid.UUID] = Query(None),
    window_days: int = Query(7, ge=1, le=90),
) -> LaborDashboardMetrics:
    metrics = await _svc(db).get_dashboard_metrics(
        current_user.tenant_id, warehouse_id, window_days
    )
    return LaborDashboardMetrics(**metrics)
