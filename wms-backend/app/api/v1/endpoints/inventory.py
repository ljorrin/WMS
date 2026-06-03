"""
WMS Panama — Inventory Endpoints
===================================
API REST para el módulo de inventario.

GET  /inventory/stock              — Consulta de stock (con filtros)
GET  /inventory/stock/{product_id}/summary — Resumen de un SKU
POST /inventory/receive            — Recibir mercancía
POST /inventory/transfer           — Transferir entre ubicaciones
POST /inventory/pick               — Picking de stock

GET  /inventory/movements          — Historial de movimientos
GET  /inventory/movements/kardex   — Kárdex por producto

POST /inventory/adjustments        — Crear ajuste (draft → pending_approval)
GET  /inventory/adjustments        — Listar ajustes
GET  /inventory/adjustments/{id}   — Detalle de ajuste
POST /inventory/adjustments/{id}/approve — Aprobar/rechazar ajuste
POST /inventory/adjustments/{id}/apply   — Aplicar ajuste aprobado

POST /inventory/cycle-counts       — Crear conteo cíclico
GET  /inventory/cycle-counts       — Listar conteos
GET  /inventory/cycle-counts/{id}  — Detalle de conteo
POST /inventory/cycle-counts/{id}/results  — Registrar resultados
POST /inventory/cycle-counts/{id}/complete — Completar conteo

GET  /inventory/batches            — Listar lotes
GET  /inventory/batches/near-expiry — Lotes próximos a vencer
GET  /inventory/batches/expired    — Lotes vencidos

POST /inventory/reservations       — Crear reserva
DELETE /inventory/reservations/{id} — Cancelar reserva

GET  /inventory/alerts             — Alertas de stock activas
"""

from __future__ import annotations

import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    DBDep, CurrentUserDep, PaginationDep,
    require_permission,
)
from app.core.logging import get_logger
from app.services.inventory_service import InventoryService, InventoryServiceError, InsufficientStockError
from app.schemas.inventory import (
    InventoryLevelResponse, StockSummaryResponse,
    InventoryMovementCreate, InventoryMovementResponse, MovementListResponse,
    InventoryAdjustmentCreate, InventoryAdjustmentResponse, AdjustmentApproveRequest,
    CycleCountCreate, CycleCountResponse, CycleCountLineResult,
    InventoryReservationCreate, InventoryReservationResponse,
    BatchResponse, StockAlertResponse,
    StockQueryParams, MovementQueryParams,
    InventoryDashboardMetrics,
)

router = APIRouter()
logger = get_logger(__name__)


def get_inventory_service(current_user: CurrentUserDep, db: DBDep) -> InventoryService:
    """Dependency: instancia el servicio de inventario con el contexto del usuario."""
    return InventoryService(db=db, tenant_id=current_user.tenant_id, user_id=current_user.id)


# ── Consulta de Stock ─────────────────────────────────────────────────────────

@router.get(
    "/stock",
    summary="Consultar stock",
    description="Lista el stock disponible con filtros por bodega, producto, ubicación, lote, etc.",
)
async def query_stock(
    current_user: CurrentUserDep,
    db: DBDep,
    pagination: PaginationDep,
    warehouse_id: Optional[uuid.UUID] = Query(None, description="Filtrar por bodega"),
    product_id: Optional[uuid.UUID] = Query(None),
    location_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None, description="available|reserved|quarantine|blocked|damaged|expired"),
    near_expiry_days: Optional[int] = Query(None, ge=1, le=365, description="Alertar si vence en N días"),
    include_zero: bool = Query(False, description="Incluir ubicaciones con stock en cero"),
    search: Optional[str] = Query(None, description="Buscar por código de producto o lote"),
) -> dict:
    """Consulta el stock con filtros múltiples."""
    svc = get_inventory_service(current_user, db)
    from app.models.inventory import InventoryStatus

    status_enum = None
    if status:
        try:
            status_enum = InventoryStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Estado inválido: {status}")

    items, total = await svc.levels.list_by_warehouse(
        tenant_id=current_user.tenant_id,
        warehouse_id=warehouse_id,
        product_id=product_id,
        location_id=location_id,
        status=status_enum,
        include_zero=include_zero,
        near_expiry_days=near_expiry_days,
        offset=pagination.offset,
        limit=pagination.limit,
    )

    return {
        "items": [InventoryLevelResponse.model_validate(i) for i in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get(
    "/stock/{product_id}/summary",
    response_model=dict,
    summary="Resumen de stock de un SKU",
)
async def get_stock_summary(
    product_id: uuid.UUID,
    warehouse_id: uuid.UUID = Query(..., description="ID de la bodega"),
    current_user: CurrentUserDep = None,
    db: DBDep = None,
) -> dict:
    """Resumen consolidado de un SKU: totales por estado, lotes disponibles."""
    svc = get_inventory_service(current_user, db)
    summary = await svc.levels.get_stock_summary(
        current_user.tenant_id, warehouse_id, product_id
    )
    return summary


# ── Recepción ─────────────────────────────────────────────────────────────────

class ReceiveStockRequest(BaseModel):
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    location_id: uuid.UUID
    quantity: Decimal = Field(..., gt=0)
    lot_number: Optional[str] = None
    expiry_date: Optional[date] = None
    manufacture_date: Optional[date] = None
    supplier_lot: Optional[str] = None
    unit_cost: Optional[Decimal] = Field(None, ge=0)
    reference_type: Optional[str] = None
    reference_id: Optional[uuid.UUID] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None


@router.post(
    "/receive",
    status_code=status.HTTP_201_CREATED,
    summary="Recibir mercancía",
    description="Registra la entrada de stock a una ubicación de la bodega.",
    dependencies=[Depends(require_permission("inbound:grn:create"))],
)
async def receive_stock(
    body: ReceiveStockRequest,
    current_user: CurrentUserDep,
    db: DBDep,
) -> dict:
    """Recibe mercancía en la bodega. Crea lote si se especifica número de lote."""
    svc = get_inventory_service(current_user, db)
    try:
        result = await svc.receive_stock(**body.model_dump())
        return {
            "success": True,
            "movement_id": str(result["movement"].id),
            "batch_id": str(result["batch_id"]) if result["batch_id"] else None,
            "level_id": str(result["level_id"]),
            "message": f"Recibidas {body.quantity} unidades correctamente.",
        }
    except InventoryServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)


# ── Transferencia ─────────────────────────────────────────────────────────────

class TransferRequest(BaseModel):
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    quantity: Decimal = Field(..., gt=0)
    batch_id: Optional[uuid.UUID] = None
    lot_number: Optional[str] = None
    notes: Optional[str] = None


@router.post(
    "/transfer",
    status_code=status.HTTP_201_CREATED,
    summary="Transferir entre ubicaciones",
)
async def transfer_location(
    body: TransferRequest,
    current_user: CurrentUserDep,
    db: DBDep,
) -> dict:
    """Mueve stock de una ubicación a otra dentro de la misma bodega."""
    svc = get_inventory_service(current_user, db)
    try:
        result = await svc.transfer_location(**body.model_dump())
        return {
            "success": True,
            "movement_id": str(result["movement"].id),
            "message": f"Transferidas {body.quantity} unidades correctamente.",
        }
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": e.code, "message": e.message, "needed": str(e.needed), "available": str(e.available)},
        )
    except InventoryServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)


# ── Movimientos ───────────────────────────────────────────────────────────────

@router.get(
    "/movements",
    summary="Historial de movimientos",
)
async def list_movements(
    current_user: CurrentUserDep,
    db: DBDep,
    pagination: PaginationDep,
    warehouse_id: Optional[uuid.UUID] = Query(None),
    product_id: Optional[uuid.UUID] = Query(None),
    movement_type: Optional[str] = Query(None),
    reference_type: Optional[str] = Query(None),
    reference_id: Optional[uuid.UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
) -> dict:
    """Lista el historial de movimientos de inventario con filtros."""
    svc = get_inventory_service(current_user, db)
    from app.models.inventory import MovementType

    mt = None
    if movement_type:
        try:
            mt = MovementType(movement_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Tipo de movimiento inválido: {movement_type}")

    items, total = await svc.movements.list(
        tenant_id=current_user.tenant_id,
        warehouse_id=warehouse_id,
        product_id=product_id,
        movement_type=mt,
        reference_type=reference_type,
        reference_id=reference_id,
        date_from=date_from,
        date_to=date_to,
        offset=pagination.offset,
        limit=pagination.limit,
    )

    return {
        "items": [InventoryMovementResponse.model_validate(m) for m in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get(
    "/movements/kardex",
    summary="Kárdex de un producto",
    description="Tarjeta de stock con todos los movimientos cronológicos de un SKU.",
)
async def get_kardex(
    product_id: uuid.UUID = Query(...),
    warehouse_id: uuid.UUID = Query(...),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: CurrentUserDep = None,
    db: DBDep = None,
) -> dict:
    """Kárdex del producto: entrada → salida → saldo acumulado."""
    svc = get_inventory_service(current_user, db)
    movements = await svc.movements.get_product_stock_card(
        current_user.tenant_id, warehouse_id, product_id, date_from, date_to
    )

    # Calcular saldo acumulado
    INBOUND_TYPES = {"receipt", "return_from_customer", "transfer_in", "adjustment_in", "found", "production_in"}
    saldo = Decimal("0")
    kardex = []
    for m in movements:
        if m.movement_type.value in INBOUND_TYPES:
            saldo += m.quantity
            entradas = m.quantity
            salidas = Decimal("0")
        else:
            saldo -= m.quantity
            entradas = Decimal("0")
            salidas = m.quantity

        kardex.append({
            "date": m.occurred_at.isoformat(),
            "movement_type": m.movement_type.value,
            "reference": m.reference_number,
            "entradas": str(entradas),
            "salidas": str(salidas),
            "saldo": str(saldo),
            "unit_cost": str(m.unit_cost) if m.unit_cost else None,
        })

    return {
        "product_id": str(product_id),
        "warehouse_id": str(warehouse_id),
        "movements": kardex,
        "total_movements": len(kardex),
        "current_balance": str(saldo),
    }


# ── Ajustes de Inventario ─────────────────────────────────────────────────────

@router.post(
    "/adjustments",
    status_code=status.HTTP_201_CREATED,
    summary="Crear ajuste de inventario",
    dependencies=[Depends(require_permission("inventory:adjustment:create"))],
)
async def create_adjustment(
    body: InventoryAdjustmentCreate,
    current_user: CurrentUserDep,
    db: DBDep,
) -> dict:
    """Crea un ajuste de inventario que pasa por flujo de aprobación."""
    svc = get_inventory_service(current_user, db)
    try:
        adj = await svc.create_adjustment(body)
        return {
            "id": str(adj.id),
            "adjustment_number": adj.adjustment_number,
            "status": adj.status,
            "lines": len(body.lines),
            "message": f"Ajuste {adj.adjustment_number} creado. Pendiente de aprobación.",
        }
    except InventoryServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)


@router.get(
    "/adjustments",
    summary="Listar ajustes de inventario",
)
async def list_adjustments(
    current_user: CurrentUserDep,
    db: DBDep,
    pagination: PaginationDep,
    warehouse_id: Optional[uuid.UUID] = Query(None),
    adj_status: Optional[str] = Query(None, alias="status"),
) -> dict:
    svc = get_inventory_service(current_user, db)
    items, total = await svc.adjustments.list(
        current_user.tenant_id, warehouse_id=warehouse_id,
        status=adj_status, offset=pagination.offset, limit=pagination.limit,
    )
    return {
        "items": [InventoryAdjustmentResponse.model_validate(a) for a in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get("/adjustments/{adjustment_id}", summary="Detalle de ajuste")
async def get_adjustment(
    adjustment_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBDep,
) -> InventoryAdjustmentResponse:
    svc = get_inventory_service(current_user, db)
    adj = await svc.adjustments.get_by_id(adjustment_id, current_user.tenant_id)
    if not adj:
        raise HTTPException(status_code=404, detail="Ajuste no encontrado.")
    return InventoryAdjustmentResponse.model_validate(adj)


@router.post(
    "/adjustments/{adjustment_id}/approve",
    summary="Aprobar o rechazar ajuste",
    dependencies=[Depends(require_permission("inventory:adjustment:approve"))],
)
async def approve_adjustment(
    adjustment_id: uuid.UUID,
    body: AdjustmentApproveRequest,
    current_user: CurrentUserDep,
    db: DBDep,
) -> dict:
    svc = get_inventory_service(current_user, db)
    try:
        adj = await svc.approve_adjustment(adjustment_id, body)
        action = "aprobado" if body.approved else "rechazado"
        return {
            "id": str(adj.id),
            "adjustment_number": adj.adjustment_number,
            "status": adj.status,
            "message": f"Ajuste {adj.adjustment_number} {action}.",
        }
    except InventoryServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST if e.code != "NOT_FOUND" else 404,
            detail=e.message
        )


@router.post(
    "/adjustments/{adjustment_id}/apply",
    summary="Aplicar ajuste aprobado",
    dependencies=[Depends(require_permission("inventory:adjustment:approve"))],
)
async def apply_adjustment(
    adjustment_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBDep,
) -> dict:
    """Aplica el ajuste al stock. Operación irreversible."""
    svc = get_inventory_service(current_user, db)
    try:
        adj = await svc.apply_adjustment(adjustment_id)
        return {
            "id": str(adj.id),
            "adjustment_number": adj.adjustment_number,
            "status": adj.status,
            "message": f"Ajuste {adj.adjustment_number} aplicado exitosamente.",
        }
    except InventoryServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST if e.code != "NOT_FOUND" else 404,
            detail=e.message
        )


# ── Conteo Cíclico ────────────────────────────────────────────────────────────

@router.post(
    "/cycle-counts",
    status_code=status.HTTP_201_CREATED,
    summary="Crear conteo cíclico",
    dependencies=[Depends(require_permission("inventory:cycle_count:manage"))],
)
async def create_cycle_count(
    body: CycleCountCreate,
    current_user: CurrentUserDep,
    db: DBDep,
) -> dict:
    svc = get_inventory_service(current_user, db)
    cc = await svc.create_cycle_count(body)
    return {
        "id": str(cc.id),
        "count_number": cc.count_number,
        "status": cc.status,
        "total_lines": len(cc.lines),
        "message": f"Conteo {cc.count_number} iniciado con {len(cc.lines)} líneas.",
    }


@router.get(
    "/cycle-counts",
    summary="Listar conteos cíclicos",
)
async def list_cycle_counts(
    current_user: CurrentUserDep,
    db: DBDep,
    pagination: PaginationDep,
    warehouse_id: Optional[uuid.UUID] = Query(None),
    cc_status: Optional[str] = Query(None, alias="status"),
) -> dict:
    svc = get_inventory_service(current_user, db)
    items, total = await svc.cycle_counts.list(
        current_user.tenant_id, warehouse_id=warehouse_id,
        status=cc_status, offset=pagination.offset, limit=pagination.limit,
    )
    return {
        "items": [CycleCountResponse.model_validate(cc) for cc in items],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.get("/cycle-counts/{cycle_count_id}", summary="Detalle de conteo")
async def get_cycle_count(
    cycle_count_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBDep,
) -> CycleCountResponse:
    svc = get_inventory_service(current_user, db)
    cc = await svc.cycle_counts.get_by_id(cycle_count_id, current_user.tenant_id)
    if not cc:
        raise HTTPException(status_code=404, detail="Conteo no encontrado.")
    return CycleCountResponse.model_validate(cc)


class CycleCountResultsRequest(BaseModel):
    results: List[CycleCountLineResult]


@router.post(
    "/cycle-counts/{cycle_count_id}/results",
    summary="Registrar resultados de conteo",
)
async def record_count_results(
    cycle_count_id: uuid.UUID,
    body: CycleCountResultsRequest,
    current_user: CurrentUserDep,
    db: DBDep,
) -> dict:
    svc = get_inventory_service(current_user, db)
    try:
        await svc.record_cycle_count_result(cycle_count_id, body.results)
        return {"success": True, "message": f"{len(body.results)} resultados registrados."}
    except InventoryServiceError as e:
        raise HTTPException(status_code=400, detail=e.message)


class CompleteCycleCountRequest(BaseModel):
    apply_results: bool = Field(
        default=False,
        description="Si True, aplica automáticamente las diferencias como ajuste de inventario.",
    )


@router.post(
    "/cycle-counts/{cycle_count_id}/complete",
    summary="Completar conteo cíclico",
)
async def complete_cycle_count(
    cycle_count_id: uuid.UUID,
    body: CompleteCycleCountRequest,
    current_user: CurrentUserDep,
    db: DBDep,
) -> dict:
    svc = get_inventory_service(current_user, db)
    try:
        cc = await svc.complete_cycle_count(cycle_count_id, apply_results=body.apply_results)
        return {
            "id": str(cc.id),
            "count_number": cc.count_number,
            "status": cc.status,
            "accuracy_pct": str(cc.accuracy_pct) if cc.accuracy_pct else None,
            "message": f"Conteo {cc.count_number} completado. Precisión: {cc.accuracy_pct}%",
        }
    except InventoryServiceError as e:
        raise HTTPException(status_code=400, detail=e.message)


# ── Lotes ─────────────────────────────────────────────────────────────────────

@router.get(
    "/batches/near-expiry",
    summary="Lotes próximos a vencer",
)
async def get_near_expiry_batches(
    warehouse_id: uuid.UUID = Query(...),
    days_ahead: int = Query(default=30, ge=1, le=365),
    current_user: CurrentUserDep = None,
    db: DBDep = None,
) -> dict:
    """Lotes que vencen en los próximos N días — crítico para FEFO."""
    svc = get_inventory_service(current_user, db)
    batches = await svc.batches.get_near_expiry(
        current_user.tenant_id, warehouse_id, days_ahead=days_ahead
    )
    return {
        "items": [BatchResponse.model_validate(b) for b in batches],
        "total": len(batches),
        "days_ahead": days_ahead,
    }


@router.get(
    "/batches/expired",
    summary="Lotes vencidos con stock",
)
async def get_expired_batches(
    warehouse_id: uuid.UUID = Query(...),
    current_user: CurrentUserDep = None,
    db: DBDep = None,
) -> dict:
    """Lotes ya vencidos que aún tienen stock — requieren acción inmediata."""
    svc = get_inventory_service(current_user, db)
    batches = await svc.batches.get_expired(current_user.tenant_id, warehouse_id)
    return {
        "items": [BatchResponse.model_validate(b) for b in batches],
        "total": len(batches),
        "warning": "Estos lotes están vencidos y deben ser procesados inmediatamente.",
    }


# ── Reservas ──────────────────────────────────────────────────────────────────

@router.post(
    "/reservations",
    status_code=status.HTTP_201_CREATED,
    summary="Crear reserva de stock",
)
async def create_reservation(
    body: InventoryReservationCreate,
    current_user: CurrentUserDep,
    db: DBDep,
) -> dict:
    svc = get_inventory_service(current_user, db)
    try:
        result = await svc.create_reservation(body)
        return {
            "reservation_id": str(result["reservation"].id),
            "quantity": str(body.quantity),
            "status": "active",
            "message": f"Reserva creada para {body.quantity} unidades.",
        }
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": e.code, "message": e.message},
        )


@router.delete(
    "/reservations/{reservation_id}",
    status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None,
    summary="Cancelar reserva",
)
async def cancel_reservation(
    reservation_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DBDep,
) -> None:
    svc = get_inventory_service(current_user, db)
    try:
        await svc.cancel_reservation(reservation_id)
    except InventoryServiceError as e:
        raise HTTPException(status_code=404, detail=e.message)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get(
    "/dashboard",
    response_model=InventoryDashboardMetrics,
    summary="KPIs del módulo de Inventario",
    dependencies=[Depends(require_permission("inventory:read"))],
)
async def inventory_dashboard(
    current_user: CurrentUserDep,
    db: DBDep,
    warehouse_id: Optional[uuid.UUID] = Query(None),
) -> InventoryDashboardMetrics:
    svc = get_inventory_service(current_user, db)
    return await svc.get_dashboard_metrics(warehouse_id=warehouse_id)
