"""
WMS Panama — Endpoints Outbound API v1
=========================================
Flujo: SalesOrder → Wave → Picking → Packing → Shipment → RMA

Permisos:
  outbound:so:create / read / confirm / cancel
  outbound:wave:create / manage
  outbound:picking:manage
  outbound:packing:manage
  outbound:shipping:manage
  outbound:rma:create / manage
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import (
    CurrentUserDep,
    DBDep,
    PaginationDep,
    require_permission,
)
from app.core.exceptions import OrderStateError, OutboundServiceError, PickingStateError
from app.models.outbound import (
    PackStatus,
    PickingStatus,
    ReturnOrderStatus,
    SOStatus,
    ShipmentStatus,
    WaveStatus,
)
from app.schemas.outbound import (
    OutboundDashboardMetrics,
    OutboundThroughputResponse,
    PackCompleteRequest,
    PackTaskListResponse,
    PackTaskResponse,
    PickingCompleteRequest,
    PickingTaskListResponse,
    PickingTaskResponse,
    ReturnOrderCreate,
    ReturnOrderResponse,
    ReturnReceiveRequest,
    SOCancelRequest,
    SOListResponse,
    SalesOrderCreate,
    SalesOrderResponse,
    SalesOrderUpdate,
    ShipmentCreate,
    ShipmentDeliverRequest,
    ShipmentDispatchRequest,
    ShipmentListResponse,
    ShipmentResponse,
    WaveCreateRequest,
    WaveListResponse,
    WaveResponse,
)
from app.services.outbound_service import OutboundService

router = APIRouter()


def _svc(db: DBDep, current_user: CurrentUserDep) -> OutboundService:
    return OutboundService(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )


# ══════════════════════════════════════════════════════════════════════════════
# SALES ORDERS
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/orders",
    response_model=SalesOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear Orden de Venta",
    dependencies=[Depends(require_permission("outbound:so:create"))],
)
async def create_sales_order(
    payload: SalesOrderCreate,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    lines_data = [line.model_dump() for line in payload.lines]
    data = payload.model_dump(exclude={"lines"})
    so = await svc.create_sales_order(
        warehouse_id=data.pop("warehouse_id"),
        customer_id=data.pop("customer_id"),
        order_date=data.pop("order_date"),
        lines_data=lines_data,
        **data,
    )
    await db.commit()
    await db.refresh(so)
    return so


@router.get(
    "/orders",
    response_model=SOListResponse,
    summary="Listar Órdenes de Venta",
    dependencies=[Depends(require_permission("outbound:so:read"))],
)
async def list_sales_orders(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    warehouse_id: Optional[UUID] = Query(None),
    customer_id: Optional[UUID] = Query(None),
    status_filter: Optional[SOStatus] = Query(None, alias="status"),
    priority: Optional[int] = Query(None, ge=1, le=10),
    search: Optional[str] = Query(None),
):
    svc = _svc(db, current_user)
    items, total = await svc.so_repo.list(
        warehouse_id=warehouse_id,
        customer_id=customer_id,
        status=status_filter,
        priority=priority,
        search=search,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return SOListResponse(
        items=items, total=total,
        page=pagination.page, page_size=pagination.page_size,
    )


@router.get(
    "/orders/{so_id}",
    response_model=SalesOrderResponse,
    summary="Detalle de SO",
    dependencies=[Depends(require_permission("outbound:so:read"))],
)
async def get_sales_order(so_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    so = await svc.so_repo.get_by_id(so_id)
    if not so:
        raise HTTPException(status_code=404, detail="Orden de Venta no encontrada.")
    return so


@router.post(
    "/orders/{so_id}/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Confirmar SO — reserva stock FEFO",
    dependencies=[Depends(require_permission("outbound:so:confirm"))],
)
async def confirm_sales_order(so_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    try:
        await svc.confirm_sales_order(so_id)
        await db.commit()
    except (OutboundServiceError, OrderStateError) as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post(
    "/orders/{so_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancelar SO",
    dependencies=[Depends(require_permission("outbound:so:cancel"))],
)
async def cancel_sales_order(
    so_id: UUID,
    payload: SOCancelRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    try:
        await svc.cancel_sales_order(so_id, reason=payload.reason)
        await db.commit()
    except (OutboundServiceError, OrderStateError) as e:
        raise HTTPException(status_code=409, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# PICKING WAVES
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/waves",
    response_model=WaveResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear Wave de Picking",
    dependencies=[Depends(require_permission("outbound:wave:create"))],
)
async def create_wave(
    payload: WaveCreateRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    try:
        wave = await svc.create_wave(
            warehouse_id=payload.warehouse_id,
            so_ids=payload.so_ids,
            picking_method=payload.picking_method,
            priority=payload.priority,
            notes=payload.notes,
        )
        await db.commit()
        await db.refresh(wave)
        return wave
    except (OutboundServiceError, OrderStateError) as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/waves",
    response_model=WaveListResponse,
    summary="Listar Waves",
    dependencies=[Depends(require_permission("outbound:wave:create"))],
)
async def list_waves(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    status_filter: Optional[WaveStatus] = Query(None, alias="status"),
    warehouse_id: Optional[UUID] = Query(None),
):
    svc = _svc(db, current_user)
    items, total = await svc.wave_repo.list(
        status=status_filter,
        warehouse_id=warehouse_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return WaveListResponse(
        items=items, total=total,
        page=pagination.page, page_size=pagination.page_size,
    )


@router.get(
    "/waves/{wave_id}",
    response_model=WaveResponse,
    summary="Detalle de Wave",
    dependencies=[Depends(require_permission("outbound:wave:create"))],
)
async def get_wave(wave_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    wave = await svc.wave_repo.get_by_id(wave_id)
    if not wave:
        raise HTTPException(status_code=404, detail="Wave no encontrada.")
    return wave


@router.post(
    "/waves/{wave_id}/release",
    summary="Liberar Wave — genera PickingTasks FEFO",
    dependencies=[Depends(require_permission("outbound:wave:manage"))],
)
async def release_wave(wave_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    try:
        tasks = await svc.release_wave(wave_id)
        await db.commit()
        return {"wave_id": str(wave_id), "tasks_created": len(tasks)}
    except OutboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# PICKING TASKS
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/picking",
    response_model=PickingTaskListResponse,
    summary="Listar Tareas de Picking",
    dependencies=[Depends(require_permission("outbound:picking:manage"))],
)
async def list_picking_tasks(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    wave_id: Optional[UUID] = Query(None),
    so_id: Optional[UUID] = Query(None),
    status_filter: Optional[PickingStatus] = Query(None, alias="status"),
    my_tasks: bool = Query(False),
):
    svc = _svc(db, current_user)
    operator = current_user.id if my_tasks else None
    items, total = await svc.pick_repo.list(
        wave_id=wave_id,
        so_id=so_id,
        status=status_filter,
        assigned_to_id=operator,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PickingTaskListResponse(
        items=items, total=total,
        page=pagination.page, page_size=pagination.page_size,
    )


@router.get(
    "/picking/{task_id}",
    response_model=PickingTaskResponse,
    summary="Detalle de Tarea de Picking",
    dependencies=[Depends(require_permission("outbound:picking:manage"))],
)
async def get_pick_task(task_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    task = await svc.pick_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarea de picking no encontrada.")
    return task


@router.post(
    "/picking/{task_id}/start",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Iniciar Picking (RF)",
    dependencies=[Depends(require_permission("outbound:picking:manage"))],
)
async def start_pick_task(task_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    try:
        await svc.start_pick_task(task_id)
        await db.commit()
    except (OutboundServiceError, PickingStateError) as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post(
    "/picking/{task_id}/complete",
    summary="Completar Picking (RF) — descuenta inventario",
    dependencies=[Depends(require_permission("outbound:picking:manage"))],
)
async def complete_pick_task(
    task_id: UUID,
    payload: PickingCompleteRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    try:
        result = await svc.complete_pick_task(
            task_id=task_id,
            quantity_picked=payload.quantity_picked,
            sscc_scanned=payload.sscc_scanned,
            gtin_scanned=payload.gtin_scanned,
            short_reason=payload.short_reason,
            notes=payload.notes,
        )
        await db.commit()
        return result
    except (OutboundServiceError, PickingStateError) as e:
        raise HTTPException(status_code=409, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# PACKING
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/packing",
    response_model=PackTaskListResponse,
    summary="Listar Tareas de Empaque",
    dependencies=[Depends(require_permission("outbound:packing:manage"))],
)
async def list_pack_tasks(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    status_filter: Optional[PackStatus] = Query(None, alias="status"),
):
    svc = _svc(db, current_user)
    items, total = await svc.pack_repo.list(
        status=status_filter,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PackTaskListResponse(
        items=items, total=total,
        page=pagination.page, page_size=pagination.page_size,
    )


@router.get(
    "/packing/{task_id}",
    response_model=PackTaskResponse,
    summary="Detalle de Tarea de Empaque",
    dependencies=[Depends(require_permission("outbound:packing:manage"))],
)
async def get_pack_task(task_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    task = await svc.pack_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarea de empaque no encontrada.")
    return task


@router.post(
    "/packing/{task_id}/start",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Iniciar Empaque",
    dependencies=[Depends(require_permission("outbound:packing:manage"))],
)
async def start_pack_task(task_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    try:
        await svc.start_pack_task(task_id)
        await db.commit()
    except OutboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post(
    "/packing/{task_id}/complete",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Completar Empaque — SO pasa a PACKED",
    dependencies=[Depends(require_permission("outbound:packing:manage"))],
)
async def complete_pack_task(
    task_id: UUID,
    payload: PackCompleteRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    try:
        await svc.complete_pack_task(
            task_id=task_id,
            box_type=payload.box_type,
            box_count=payload.box_count,
            total_weight_kg=payload.total_weight_kg,
            total_volume_m3=payload.total_volume_m3,
            sscc=payload.sscc,
            notes=payload.notes,
        )
        await db.commit()
    except OutboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# SHIPMENTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/shipments",
    response_model=ShipmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear Envío",
    dependencies=[Depends(require_permission("outbound:shipping:manage"))],
)
async def create_shipment(
    payload: ShipmentCreate,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    so_id = payload.so_id
    data = payload.model_dump(exclude={"so_id"})
    try:
        shipment = await svc.create_shipment(so_id=so_id, data=data)
        await db.commit()
        await db.refresh(shipment)
        return shipment
    except (OutboundServiceError, OrderStateError) as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/shipments",
    response_model=ShipmentListResponse,
    summary="Listar Envíos",
    dependencies=[Depends(require_permission("outbound:shipping:manage"))],
)
async def list_shipments(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    status_filter: Optional[ShipmentStatus] = Query(None, alias="status"),
    warehouse_id: Optional[UUID] = Query(None),
):
    svc = _svc(db, current_user)
    items, total = await svc.ship_repo.list(
        status=status_filter,
        warehouse_id=warehouse_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return ShipmentListResponse(
        items=items, total=total,
        page=pagination.page, page_size=pagination.page_size,
    )


@router.get(
    "/shipments/{shipment_id}",
    response_model=ShipmentResponse,
    summary="Detalle de Envío",
    dependencies=[Depends(require_permission("outbound:shipping:manage"))],
)
async def get_shipment(shipment_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    s = await svc.ship_repo.get_by_id(shipment_id)
    if not s:
        raise HTTPException(status_code=404, detail="Envío no encontrado.")
    return s


@router.post(
    "/shipments/{shipment_id}/dispatch",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Despachar Envío — SO pasa a SHIPPED",
    dependencies=[Depends(require_permission("outbound:shipping:manage"))],
)
async def dispatch_shipment(
    shipment_id: UUID,
    payload: ShipmentDispatchRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    try:
        await svc.dispatch_shipment(shipment_id, payload.model_dump(exclude_none=True))
        await db.commit()
    except OutboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post(
    "/shipments/{shipment_id}/deliver",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Confirmar Entrega — SO pasa a DELIVERED",
    dependencies=[Depends(require_permission("outbound:shipping:manage"))],
)
async def deliver_shipment(
    shipment_id: UUID,
    payload: ShipmentDeliverRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    try:
        await svc.deliver_shipment(
            shipment_id,
            {
                "actual_delivery": payload.actual_delivery,
                "delivered_to_name": payload.delivered_to_name,
                "delivered_signature": payload.delivery_signature,
                "delivery_photo_url": payload.delivery_photo_url,
            },
        )
        await db.commit()
    except OutboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# RMA
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/returns",
    response_model=ReturnOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear Devolución de Cliente (RMA)",
    dependencies=[Depends(require_permission("outbound:rma:create"))],
)
async def create_rma(
    payload: ReturnOrderCreate,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    rma = await svc.create_rma(
        warehouse_id=payload.warehouse_id,
        customer_id=payload.customer_id,
        reason=payload.reason,
        return_type=payload.return_type,
        so_id=payload.so_id,
        notes=payload.notes,
    )
    await db.commit()
    await db.refresh(rma)
    return rma


@router.get(
    "/returns",
    summary="Listar RMAs",
    dependencies=[Depends(require_permission("outbound:rma:create"))],
)
async def list_rma(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    status_filter: Optional[ReturnOrderStatus] = Query(None, alias="status"),
    customer_id: Optional[UUID] = Query(None),
):
    svc = _svc(db, current_user)
    items, total = await svc.rma_repo.list(
        status=status_filter,
        customer_id=customer_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return {"items": items, "total": total,
            "page": pagination.page, "page_size": pagination.page_size}


@router.get(
    "/returns/{rma_id}",
    response_model=ReturnOrderResponse,
    summary="Detalle de RMA",
    dependencies=[Depends(require_permission("outbound:rma:create"))],
)
async def get_rma(rma_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    rma = await svc.rma_repo.get_by_id(rma_id)
    if not rma:
        raise HTTPException(status_code=404, detail="RMA no encontrada.")
    return rma


@router.post(
    "/returns/{rma_id}/receive",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Recibir Devolución — puede restockear inventario",
    dependencies=[Depends(require_permission("outbound:rma:manage"))],
)
async def receive_return(
    rma_id: UUID,
    payload: ReturnReceiveRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    try:
        await svc.receive_return(
            rma_id=rma_id,
            inspection_notes=payload.inspection_notes,
            restocking_eligible=payload.restocking_eligible,
            restocking_location_id=payload.restocking_location_id,
            refund_amount=payload.refund_amount,
        )
        await db.commit()
    except OutboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/dashboard",
    response_model=OutboundDashboardMetrics,
    summary="KPIs del módulo Outbound",
    dependencies=[Depends(require_permission("outbound:so:read"))],
)
async def outbound_dashboard(
    db: DBDep,
    current_user: CurrentUserDep,
    warehouse_id: Optional[UUID] = Query(None),
):
    svc = _svc(db, current_user)
    return await svc.get_dashboard_metrics(warehouse_id=warehouse_id)


@router.get(
    "/dashboard/throughput",
    response_model=OutboundThroughputResponse,
    summary="Serie diaria de picking y envíos",
    dependencies=[Depends(require_permission("outbound:so:read"))],
)
async def outbound_throughput(
    db: DBDep,
    current_user: CurrentUserDep,
    days: int = Query(7, ge=1, le=31),
    warehouse_id: Optional[UUID] = Query(None),
):
    svc = _svc(db, current_user)
    return await svc.get_throughput_series(days=days, warehouse_id=warehouse_id)
