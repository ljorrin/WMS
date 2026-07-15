"""
WMS Panamá — Order Streaming / Waveless Endpoints — FR-055
===========================================================
Liberación continua de picking sin olas. Reutiliza los permisos de outbound.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select

from app.core.dependencies import CurrentUserDep, DBDep, require_permission
from app.core.exceptions import OutboundServiceError, PickingStateError
from app.schemas.streaming import (
    EnqueueOrderRequest, EnqueueOrderResult, PickingTaskLite,
    StreamingMetrics, StreamNextRequest,
)
from app.services.streaming_service import StreamingService

router = APIRouter()


def _svc(db) -> StreamingService:
    return StreamingService(db)


@router.post(
    "/enqueue", response_model=EnqueueOrderResult,
    summary="Encolar una orden como picking waveless",
    dependencies=[Depends(require_permission("outbound:picking:execute"))],
)
async def enqueue_order(
    payload: EnqueueOrderRequest, db: DBDep, current_user: CurrentUserDep,
) -> EnqueueOrderResult:
    try:
        result = await _svc(db).enqueue_order(current_user.tenant_id, payload.so_id, current_user.id)
    except PickingStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except OutboundServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return EnqueueOrderResult(
        so_id=result["so_id"], tasks_created=result["tasks_created"],
        tasks=[PickingTaskLite.model_validate(t) for t in result["tasks"]],
    )


@router.post(
    "/next", response_model=Optional[PickingTaskLite],
    summary="Despachar la siguiente mejor tarea al operario (streaming)",
    dependencies=[Depends(require_permission("outbound:picking:execute"))],
)
async def stream_next(
    payload: StreamNextRequest, db: DBDep, current_user: CurrentUserDep,
) -> Optional[PickingTaskLite]:
    operator = payload.operator_id or current_user.id
    task = await _svc(db).stream_next(
        current_user.tenant_id, payload.warehouse_id, operator,
        current_pick_sequence=payload.current_pick_sequence, max_wip=payload.max_wip,
    )
    return PickingTaskLite.model_validate(task) if task else None


@router.get(
    "/queue", summary="Listar la cola waveless pendiente",
    dependencies=[Depends(require_permission("outbound:order:read"))],
)
async def list_queue(
    db: DBDep, current_user: CurrentUserDep,
    warehouse_id: Optional[uuid.UUID] = Query(None), limit: int = Query(50, ge=1, le=200),
) -> dict:
    from app.models.outbound import PickingStatus, PickingTask, SalesOrder
    stmt = (
        select(PickingTask)
        .where(and_(
            PickingTask.tenant_id == current_user.tenant_id,
            PickingTask.wave_id.is_(None),
            PickingTask.assigned_to_id.is_(None),
            PickingTask.status == PickingStatus.PENDING,
            PickingTask.deleted_at.is_(None),
        ))
    )
    if warehouse_id:
        stmt = stmt.join(SalesOrder, SalesOrder.id == PickingTask.so_id).where(
            SalesOrder.warehouse_id == warehouse_id
        )
    rows = (await db.execute(stmt.order_by(PickingTask.priority).limit(limit))).scalars().all()
    return {"items": [PickingTaskLite.model_validate(t) for t in rows], "count": len(rows)}


@router.get(
    "/metrics", response_model=StreamingMetrics, summary="KPIs de streaming/waveless",
    dependencies=[Depends(require_permission("outbound:order:read"))],
)
async def metrics(
    db: DBDep, current_user: CurrentUserDep,
    warehouse_id: Optional[uuid.UUID] = Query(None),
) -> StreamingMetrics:
    m = await _svc(db).get_metrics(current_user.tenant_id, warehouse_id)
    return StreamingMetrics(**m)
