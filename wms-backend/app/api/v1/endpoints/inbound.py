"""
WMS Panama — Endpoints Inbound API v1
========================================
Cubre el flujo: PO → ASN → GRN → QC → Putaway → RTV

Permisos requeridos:
  inbound:po:create / read / confirm / cancel
  inbound:asn:create / read
  inbound:grn:create / read / confirm
  inbound:qc:create / resolve
  inbound:putaway:manage
  inbound:rtv:create / manage
"""

from __future__ import annotations
from fastapi import Response

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
from app.models.inbound import (
    ASNStatus,
    GRNStatus,
    POStatus,
    PutawayStatus,
    RTVStatus,
)
from app.schemas.inbound import (
    ASNCreate,
    ASNListResponse,
    ASNResponse,
    ASNScheduleDockRequest,
    GRNCreate,
    GRNListResponse,
    GRNQueryParams,
    GRNResponse,
    InboundDashboardMetrics,
    InboundThroughputResponse,
    POListResponse,
    POQueryParams,
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    PurchaseOrderUpdate,
    PutawayCompleteRequest,
    PutawayListResponse,
    PutawayTaskResponse,
    QualityInspectionApprove,
    QualityInspectionCreate,
    QualityInspectionResponse,
    RTVCreate,
    RTVResponse,
)
from app.services.inbound_service import InboundService, InboundServiceError, POStateError

router = APIRouter()


# ── Helper para instanciar el servicio ────────────────────────────────────────

def _svc(db: DBDep, current_user: CurrentUserDep) -> InboundService:
    return InboundService(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )


# ══════════════════════════════════════════════════════════════════════════════
# PURCHASE ORDERS
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/purchase-orders",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear Orden de Compra",
    dependencies=[Depends(require_permission("inbound:po:create"))],
)
async def create_purchase_order(
    payload: PurchaseOrderCreate,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    lines_data = [line.model_dump() for line in payload.lines]
    data = payload.model_dump(exclude={"lines"})
    po = await svc.create_purchase_order(
        warehouse_id=data.pop("warehouse_id"),
        supplier_id=data.pop("supplier_id"),
        order_date=data.pop("order_date"),
        lines_data=lines_data,
        **data,
    )
    await db.commit()
    return await svc.po_repo.get_by_id(po.id)


@router.get(
    "/purchase-orders",
    response_model=POListResponse,
    summary="Listar Órdenes de Compra",
    dependencies=[Depends(require_permission("inbound:po:read"))],
)
async def list_purchase_orders(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    warehouse_id: Optional[UUID] = Query(None),
    supplier_id: Optional[UUID] = Query(None),
    status_filter: Optional[POStatus] = Query(None, alias="status"),
    date_from=Query(None),
    date_to=Query(None),
    search: Optional[str] = Query(None),
):
    svc = _svc(db, current_user)
    items, total = await svc.po_repo.list(
        warehouse_id=warehouse_id,
        supplier_id=supplier_id,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
        search=search,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return POListResponse(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/purchase-orders/{po_id}",
    response_model=PurchaseOrderResponse,
    summary="Detalle de OC",
    dependencies=[Depends(require_permission("inbound:po:read"))],
)
async def get_purchase_order(
    po_id: UUID,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    po = await svc.po_repo.get_by_id(po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Orden de Compra no encontrada.")
    return po


@router.post(
    "/purchase-orders/{po_id}/confirm",
    status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None,
    summary="Confirmar OC",
    dependencies=[Depends(require_permission("inbound:po:confirm"))],
)
async def confirm_purchase_order(
    po_id: UUID,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    try:
        await svc.confirm_purchase_order(po_id)
        await db.commit()
    except (InboundServiceError, POStateError) as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put(
    "/purchase-orders/{po_id}",
    response_model=PurchaseOrderResponse,
    summary="Editar OC (solo en DRAFT)",
    dependencies=[Depends(require_permission("inbound:po:update"))],
)
async def update_purchase_order(
    po_id: UUID,
    payload: PurchaseOrderUpdate,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    try:
        po = await svc.update_purchase_order(po_id, payload.model_dump(exclude_unset=True))
        await db.commit()
        return await svc.po_repo.get_by_id(po.id)
    except POStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except InboundServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/purchase-orders/{po_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None,
    summary="Cancelar OC",
    dependencies=[Depends(require_permission("inbound:po:cancel"))],
)
async def cancel_purchase_order(
    po_id: UUID,
    reason: str = Query("", max_length=500),
    db: DBDep = None,
    current_user: CurrentUserDep = None,
):
    svc = _svc(db, current_user)
    try:
        await svc.cancel_purchase_order(po_id, reason=reason)
        await db.commit()
    except (InboundServiceError, POStateError) as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete(
    "/purchase-orders/{po_id}",
    status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None,
    summary="Eliminar OC (borrado lógico, solo DRAFT/CANCELLED)",
    dependencies=[Depends(require_permission("inbound:po:delete"))],
)
async def delete_purchase_order(
    po_id: UUID,
    reason: str = Query("", max_length=500),
    db: DBDep = None,
    current_user: CurrentUserDep = None,
):
    svc = _svc(db, current_user)
    try:
        await svc.delete_purchase_order(po_id, reason=reason)
        await db.commit()
    except POStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except InboundServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# ASN
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/asn",
    response_model=ASNResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear ASN",
    dependencies=[Depends(require_permission("inbound:asn:create"))],
)
async def create_asn(
    payload: ASNCreate,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    lines_data = [line.model_dump() for line in payload.lines]
    data = payload.model_dump(exclude={"lines"})
    try:
        asn = await svc.create_asn(
            warehouse_id=data.pop("warehouse_id"),
            supplier_id=data.pop("supplier_id"),
            lines_data=lines_data,
            po_id=data.pop("po_id", None),
            **data,
        )
        await db.commit()
        return await svc.asn_repo.get_by_id(asn.id)
    except InboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/asn",
    response_model=ASNListResponse,
    summary="Listar ASNs",
    dependencies=[Depends(require_permission("inbound:asn:read"))],
)
async def list_asn(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    warehouse_id: Optional[UUID] = Query(None),
    status_filter: Optional[ASNStatus] = Query(None, alias="status"),
):
    svc = _svc(db, current_user)
    items, total = await svc.asn_repo.list(
        warehouse_id=warehouse_id,
        status=status_filter,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return ASNListResponse(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/asn/{asn_id}",
    response_model=ASNResponse,
    summary="Detalle de ASN",
    dependencies=[Depends(require_permission("inbound:asn:read"))],
)
async def get_asn(asn_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    asn = await svc.asn_repo.get_by_id(asn_id)
    if not asn:
        raise HTTPException(status_code=404, detail="ASN no encontrado.")
    return asn


@router.post(
    "/asn/{asn_id}/dispatch",
    status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None,
    summary="Despachar ASN (IN_TRANSIT)",
    dependencies=[Depends(require_permission("inbound:asn:create"))],
)
async def dispatch_asn(asn_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    try:
        await svc.dispatch_asn(asn_id)
        await db.commit()
    except InboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post(
    "/asn/{asn_id}/arrive",
    status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None,
    summary="Registrar llegada de ASN al almacén",
    dependencies=[Depends(require_permission("inbound:grn:create"))],
)
async def arrive_asn(
    asn_id: UUID,
    payload: ASNScheduleDockRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    try:
        await svc.arrive_asn(asn_id, dock_number=payload.dock_number)
        await db.commit()
    except InboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# GRN
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/grn",
    response_model=GRNResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear GRN (Recibo de Mercancía)",
    dependencies=[Depends(require_permission("inbound:grn:create"))],
)
async def create_grn(
    payload: GRNCreate,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    lines_data = [line.model_dump() for line in payload.lines]
    data = payload.model_dump(exclude={"lines"})
    try:
        grn = await svc.create_grn(
            warehouse_id=data.pop("warehouse_id"),
            lines_data=lines_data,
            asn_id=data.pop("asn_id", None),
            po_id=data.pop("po_id", None),
            **data,
        )
        await db.commit()
        return await svc.grn_repo.get_by_id(grn.id)
    except InboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/grn",
    response_model=GRNListResponse,
    summary="Listar GRNs",
    dependencies=[Depends(require_permission("inbound:grn:read"))],
)
async def list_grn(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    warehouse_id: Optional[UUID] = Query(None),
    status_filter: Optional[GRNStatus] = Query(None, alias="status"),
    requires_qc: Optional[bool] = Query(None),
    date_from=Query(None),
    date_to=Query(None),
):
    svc = _svc(db, current_user)
    items, total = await svc.grn_repo.list(
        warehouse_id=warehouse_id,
        status=status_filter,
        requires_qc=requires_qc,
        date_from=date_from,
        date_to=date_to,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return GRNListResponse(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/grn/{grn_id}",
    response_model=GRNResponse,
    summary="Detalle de GRN",
    dependencies=[Depends(require_permission("inbound:grn:read"))],
)
async def get_grn(grn_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    grn = await svc.grn_repo.get_by_id(grn_id)
    if not grn:
        raise HTTPException(status_code=404, detail="GRN no encontrado.")
    return grn


@router.post(
    "/grn/{grn_id}/confirm",
    status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None,
    summary="Confirmar GRN",
    dependencies=[Depends(require_permission("inbound:grn:confirm"))],
)
async def confirm_grn(grn_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    try:
        await svc.confirm_grn(grn_id)
        await db.commit()
    except InboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# QUALITY INSPECTION
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/grn/{grn_id}/quality-inspection",
    response_model=QualityInspectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear Inspección de Calidad para un GRN",
    dependencies=[Depends(require_permission("inbound:qc:create"))],
)
async def create_quality_inspection(
    grn_id: UUID,
    payload: QualityInspectionCreate,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    lines_data = [line.model_dump() for line in payload.lines]
    data = payload.model_dump(exclude={"lines", "grn_id"})
    try:
        qi = await svc.create_quality_inspection(
            grn_id=grn_id,
            lines_data=lines_data,
            **data,
        )
        await db.commit()
        return await svc.qi_repo.get_by_id(qi.id)
    except InboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/quality-inspections",
    summary="Listar QIs pendientes",
    dependencies=[Depends(require_permission("inbound:qc:create"))],
)
async def list_quality_inspections(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
):
    svc = _svc(db, current_user)
    items, total = await svc.qi_repo.list(
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size}


@router.get(
    "/quality-inspections/{qi_id}",
    response_model=QualityInspectionResponse,
    summary="Detalle de QI",
    dependencies=[Depends(require_permission("inbound:qc:create"))],
)
async def get_quality_inspection(qi_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    qi = await svc.qi_repo.get_by_id(qi_id)
    if not qi:
        raise HTTPException(status_code=404, detail="Inspección de Calidad no encontrada.")
    return qi


@router.post(
    "/quality-inspections/{qi_id}/resolve",
    summary="Aprobar / Rechazar QI",
    dependencies=[Depends(require_permission("inbound:qc:resolve"))],
)
async def resolve_quality_inspection(
    qi_id: UUID,
    payload: QualityInspectionApprove,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    try:
        result = await svc.resolve_quality_inspection(
            qi_id=qi_id,
            approved=payload.approved,
            disposition=payload.disposition,
            disposition_notes=payload.disposition_notes,
            return_to_vendor=payload.return_to_vendor,
        )
        await db.commit()
        return result
    except InboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# PUTAWAY
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/putaway",
    response_model=PutawayListResponse,
    summary="Listar tareas de Putaway",
    dependencies=[Depends(require_permission("inbound:putaway:manage"))],
)
async def list_putaway_tasks(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    status_filter: Optional[PutawayStatus] = Query(None, alias="status"),
    assigned_to_id: Optional[UUID] = Query(None),
    my_tasks: bool = Query(False, description="Solo mis tareas asignadas"),
):
    svc = _svc(db, current_user)
    operator_filter = current_user.id if my_tasks else assigned_to_id
    items, total = await svc.putaway_repo.list(
        status=status_filter,
        assigned_to_id=operator_filter,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PutawayListResponse(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/putaway/{task_id}",
    response_model=PutawayTaskResponse,
    summary="Detalle de tarea Putaway",
    dependencies=[Depends(require_permission("inbound:putaway:manage"))],
)
async def get_putaway_task(task_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    task = await svc.putaway_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarea de Putaway no encontrada.")
    return task


@router.post(
    "/putaway/{task_id}/start",
    status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None,
    summary="Iniciar tarea Putaway (RF)",
    dependencies=[Depends(require_permission("inbound:putaway:manage"))],
)
async def start_putaway_task(task_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    try:
        await svc.start_putaway_task(task_id)
        await db.commit()
    except InboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post(
    "/putaway/{task_id}/complete",
    status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None,
    summary="Completar tarea Putaway (RF) — actualiza inventario",
    dependencies=[Depends(require_permission("inbound:putaway:manage"))],
)
async def complete_putaway_task(
    task_id: UUID,
    payload: PutawayCompleteRequest,
    db: DBDep,
    current_user: CurrentUserDep,
):
    svc = _svc(db, current_user)
    try:
        await svc.complete_putaway_task(
            task_id=task_id,
            actual_location=payload.actual_location,
            override_reason=payload.override_reason,
        )
        await db.commit()
    except InboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# RTV
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/rtv",
    response_model=RTVResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear Devolución a Proveedor (RTV)",
    dependencies=[Depends(require_permission("inbound:rtv:create"))],
)
async def create_rtv(payload: RTVCreate, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    data = payload.model_dump()
    rtv = await svc.create_rtv(
        supplier_id=data.pop("supplier_id"),
        warehouse_id=data.pop("warehouse_id"),
        reason=data.pop("reason"),
        **data,
    )
    await db.commit()
    return await svc.rtv_repo.get_by_id(rtv.id)


@router.get(
    "/rtv",
    summary="Listar RTVs",
    dependencies=[Depends(require_permission("inbound:rtv:create"))],
)
async def list_rtv(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    supplier_id: Optional[UUID] = Query(None),
    status_filter: Optional[RTVStatus] = Query(None, alias="status"),
):
    svc = _svc(db, current_user)
    items, total = await svc.rtv_repo.list(
        supplier_id=supplier_id,
        status=status_filter,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size}


@router.get(
    "/rtv/{rtv_id}",
    response_model=RTVResponse,
    summary="Detalle de RTV",
    dependencies=[Depends(require_permission("inbound:rtv:create"))],
)
async def get_rtv(rtv_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    rtv = await svc.rtv_repo.get_by_id(rtv_id)
    if not rtv:
        raise HTTPException(status_code=404, detail="RTV no encontrado.")
    return rtv


@router.post(
    "/rtv/{rtv_id}/ship",
    status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None,
    summary="Registrar despacho de RTV",
    dependencies=[Depends(require_permission("inbound:rtv:manage"))],
)
async def ship_rtv(rtv_id: UUID, db: DBDep, current_user: CurrentUserDep):
    svc = _svc(db, current_user)
    try:
        await svc.ship_rtv(rtv_id)
        await db.commit()
    except InboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post(
    "/rtv/{rtv_id}/credit",
    status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None,
    summary="Confirmar Nota de Crédito RTV",
    dependencies=[Depends(require_permission("inbound:rtv:manage"))],
)
async def confirm_rtv_credit(
    rtv_id: UUID,
    credit_memo_number: str = Query(..., max_length=50),
    credit_received: Decimal = Query(..., ge=0),
    db: DBDep = None,
    current_user: CurrentUserDep = None,
):
    svc = _svc(db, current_user)
    try:
        await svc.confirm_rtv_credit(rtv_id, credit_memo_number, credit_received)
        await db.commit()
    except InboundServiceError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/dashboard",
    response_model=InboundDashboardMetrics,
    summary="KPIs del módulo Inbound",
    dependencies=[Depends(require_permission("inbound:po:read"))],
)
async def inbound_dashboard(
    db: DBDep,
    current_user: CurrentUserDep,
    warehouse_id: Optional[UUID] = Query(None),
):
    svc = _svc(db, current_user)
    return await svc.get_dashboard_metrics(warehouse_id=warehouse_id)


@router.get(
    "/dashboard/throughput",
    response_model=InboundThroughputResponse,
    summary="Serie diaria de recepciones y putaway",
    dependencies=[Depends(require_permission("inbound:po:read"))],
)
async def inbound_throughput(
    db: DBDep,
    current_user: CurrentUserDep,
    days: int = Query(7, ge=1, le=31),
    warehouse_id: Optional[UUID] = Query(None),
):
    svc = _svc(db, current_user)
    return await svc.get_throughput_series(days=days, warehouse_id=warehouse_id)
