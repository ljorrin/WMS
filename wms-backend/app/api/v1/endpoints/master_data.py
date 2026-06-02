"""
WMS Panama — Master Data Endpoints (solo lectura)
==================================================
Listados de datos maestros usados por los formularios del frontend
(selectores de producto, proveedor y ubicacion en Inbound/Outbound).

Son endpoints de SOLO LECTURA: el alta/edicion de maestros se gestiona
por procesos dedicados. Aqui solo exponemos catalogos paginados y
buscables, siempre acotados al tenant del usuario autenticado.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select, func

from app.core.dependencies import DBDep, CurrentUserDep, PaginationDep
from app.models.master_data import (
    Product, ProductStatus,
    Supplier, SupplierStatus,
    Location, LocationType, LocationStatus,
)

router = APIRouter()


# ─────────────────────────────────────────────────────────────
# Schemas de respuesta (ligeros, pensados para selectores)
# ─────────────────────────────────────────────────────────────
class ProductLite(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    uom: str
    status: ProductStatus
    gtin_13: Optional[str] = None
    model_config = {"from_attributes": True}


class SupplierLite(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    status: SupplierStatus
    supplier_type: str
    lead_time_days: Optional[int] = None
    model_config = {"from_attributes": True}


class LocationLite(BaseModel):
    id: uuid.UUID
    code: str
    warehouse_id: uuid.UUID
    location_type: LocationType
    status: LocationStatus
    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    items: list[ProductLite]
    total: int
    page: int
    page_size: int


class SupplierListResponse(BaseModel):
    items: list[SupplierLite]
    total: int
    page: int
    page_size: int


class LocationListResponse(BaseModel):
    items: list[LocationLite]
    total: int
    page: int
    page_size: int


# ─────────────────────────────────────────────────────────────
# Productos
# ─────────────────────────────────────────────────────────────
@router.get("/products", response_model=ProductListResponse)
async def list_products(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    search: Optional[str] = Query(None, description="Busca por SKU o nombre"),
    status_filter: Optional[ProductStatus] = Query(None, alias="status"),
) -> ProductListResponse:
    """Catalogo de productos del tenant (para selectores de SKU)."""
    stmt = select(Product).where(Product.tenant_id == current_user.tenant_id)

    if search:
        stmt = stmt.where(
            Product.sku.ilike(f"%{search}%") | Product.name.ilike(f"%{search}%")
        )
    if status_filter:
        stmt = stmt.where(Product.status == status_filter)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(Product.sku).offset(pagination.offset).limit(pagination.limit)
    items = (await db.execute(stmt)).scalars().all()

    return ProductListResponse(
        items=items, total=total, page=pagination.page, page_size=pagination.page_size
    )


# ─────────────────────────────────────────────────────────────
# Proveedores
# ─────────────────────────────────────────────────────────────
@router.get("/suppliers", response_model=SupplierListResponse)
async def list_suppliers(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    search: Optional[str] = Query(None, description="Busca por codigo o nombre"),
    status_filter: Optional[SupplierStatus] = Query(None, alias="status"),
) -> SupplierListResponse:
    """Catalogo de proveedores del tenant (para selectores de proveedor)."""
    stmt = select(Supplier).where(Supplier.tenant_id == current_user.tenant_id)

    if search:
        stmt = stmt.where(
            Supplier.code.ilike(f"%{search}%") | Supplier.name.ilike(f"%{search}%")
        )
    if status_filter:
        stmt = stmt.where(Supplier.status == status_filter)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(Supplier.name).offset(pagination.offset).limit(pagination.limit)
    items = (await db.execute(stmt)).scalars().all()

    return SupplierListResponse(
        items=items, total=total, page=pagination.page, page_size=pagination.page_size
    )


# ─────────────────────────────────────────────────────────────
# Ubicaciones
# ─────────────────────────────────────────────────────────────
@router.get("/locations", response_model=LocationListResponse)
async def list_locations(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    warehouse_id: Optional[uuid.UUID] = Query(None, description="Filtra por bodega"),
    search: Optional[str] = Query(None, description="Busca por codigo de ubicacion"),
    type_filter: Optional[LocationType] = Query(None, alias="type"),
    status_filter: Optional[LocationStatus] = Query(None, alias="status"),
) -> LocationListResponse:
    """Catalogo de ubicaciones del tenant (para selectores de ubicacion/staging)."""
    stmt = select(Location).where(Location.tenant_id == current_user.tenant_id)

    if warehouse_id:
        stmt = stmt.where(Location.warehouse_id == warehouse_id)
    if search:
        stmt = stmt.where(Location.code.ilike(f"%{search}%"))
    if type_filter:
        stmt = stmt.where(Location.location_type == type_filter)
    if status_filter:
        stmt = stmt.where(Location.status == status_filter)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(Location.code).offset(pagination.offset).limit(pagination.limit)
    items = (await db.execute(stmt)).scalars().all()

    return LocationListResponse(
        items=items, total=total, page=pagination.page, page_size=pagination.page_size
    )
