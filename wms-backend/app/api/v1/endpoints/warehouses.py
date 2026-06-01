"""
WMS Panama — Warehouse Endpoints
===================================
CRUD de bodegas dentro de un tenant.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from app.core.dependencies import DBDep, CurrentUserDep, SuperAdminDep, PaginationDep
from app.models.core import Warehouse, WarehouseStatus, WarehouseType

router = APIRouter()


class WarehouseCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=20)
    name: str = Field(..., min_length=2, max_length=200)
    company_id: uuid.UUID
    type: WarehouseType = WarehouseType.DISTRIBUTION_CENTER
    address: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    country: str = "PA"
    total_area_m2: Optional[float] = None
    picking_strategy: str = "FEFO"
    has_cold_storage: bool = False
    has_hazmat_zone: bool = False
    has_dock_management: bool = False
    model_config = {"from_attributes": True}


class WarehouseResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    type: WarehouseType
    status: WarehouseStatus
    address: Optional[str]
    city: Optional[str]
    province: Optional[str]
    country: str
    total_area_m2: Optional[float]
    picking_strategy: str
    has_cold_storage: bool
    has_hazmat_zone: bool
    has_dock_management: bool
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    gln: Optional[str]
    model_config = {"from_attributes": True}


class WarehouseListResponse(BaseModel):
    items: list[WarehouseResponse]
    total: int
    page: int
    page_size: int


@router.get("", response_model=WarehouseListResponse)
async def list_warehouses(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    search: Optional[str] = Query(None),
    type_filter: Optional[WarehouseType] = Query(None, alias="type"),
    status_filter: Optional[WarehouseStatus] = Query(None, alias="status"),
) -> WarehouseListResponse:
    """Lista las bodegas del tenant actual."""
    stmt = select(Warehouse).where(Warehouse.tenant_id == current_user.tenant_id)

    if search:
        stmt = stmt.where(
            Warehouse.name.ilike(f"%{search}%") | Warehouse.code.ilike(f"%{search}%")
        )
    if type_filter:
        stmt = stmt.where(Warehouse.type == type_filter)
    if status_filter:
        stmt = stmt.where(Warehouse.status == status_filter)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.offset(pagination.offset).limit(pagination.limit).order_by(Warehouse.code)
    items = (await db.execute(stmt)).scalars().all()

    return WarehouseListResponse(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("", response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    body: WarehouseCreate,
    db: DBDep,
    superadmin: SuperAdminDep,
) -> WarehouseResponse:
    """Crea una nueva bodega en el tenant."""
    # Verificar límite del plan
    from app.models.core import Tenant
    tenant = await db.get(Tenant, superadmin.tenant_id)
    count_stmt = select(func.count()).where(Warehouse.tenant_id == superadmin.tenant_id)
    current_count = (await db.execute(count_stmt)).scalar_one()

    if current_count >= tenant.max_warehouses:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Plan '{tenant.plan.value}' permite máximo {tenant.max_warehouses} bodegas. Actualiza tu plan.",
        )

    # Código único por tenant
    existing = (await db.execute(
        select(Warehouse).where(
            Warehouse.tenant_id == superadmin.tenant_id,
            Warehouse.code == body.code.upper(),
        )
    )).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una bodega con el código '{body.code}'.",
        )

    warehouse = Warehouse(
        tenant_id=superadmin.tenant_id,
        code=body.code.upper(),
        **body.model_dump(exclude={"code"}),
    )
    db.add(warehouse)
    await db.commit()
    await db.refresh(warehouse)
    return warehouse


@router.get("/{warehouse_id}", response_model=WarehouseResponse)
async def get_warehouse(
    warehouse_id: uuid.UUID,
    db: DBDep,
    current_user: CurrentUserDep,
) -> WarehouseResponse:
    """Obtiene una bodega por ID."""
    wh = await db.get(Warehouse, warehouse_id)
    if not wh or wh.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bodega no encontrada.")
    return wh
