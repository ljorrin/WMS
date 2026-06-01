"""
WMS Panama — Tenant Endpoints
================================
Gestión de tenants (empresas clientes del WMS).
Solo superadmins del sistema pueden crear/modificar tenants.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import DBDep, SuperAdminDep, PaginationDep
from app.models.core import Tenant, TenantPlan, TenantStatus

router = APIRouter()


# ── Schemas locales ────────────────────────────────────────────────────────────

class TenantCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r'^[a-z0-9\-]+$')
    legal_name: Optional[str] = None
    ruc: Optional[str] = None
    plan: TenantPlan = TenantPlan.STARTER
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    timezone: str = "America/Panama"
    currency: str = "USD"
    model_config = {"from_attributes": True}


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    legal_name: Optional[str]
    ruc: Optional[str]
    plan: TenantPlan
    status: TenantStatus
    timezone: str
    currency: str
    max_warehouses: int
    max_users: int
    max_skus: int
    model_config = {"from_attributes": True}


class TenantListResponse(BaseModel):
    items: list[TenantResponse]
    total: int
    page: int
    page_size: int


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=TenantListResponse, summary="Listar tenants")
async def list_tenants(
    db: DBDep,
    pagination: PaginationDep,
    superadmin: SuperAdminDep,
    search: Optional[str] = Query(None, description="Buscar por nombre o slug"),
    plan: Optional[TenantPlan] = Query(None),
    status_filter: Optional[TenantStatus] = Query(None, alias="status"),
) -> TenantListResponse:
    """Lista todos los tenants. Solo accesible por superadmins del sistema."""
    stmt = select(Tenant)

    if search:
        stmt = stmt.where(
            Tenant.name.ilike(f"%{search}%") | Tenant.slug.ilike(f"%{search}%")
        )
    if plan:
        stmt = stmt.where(Tenant.plan == plan)
    if status_filter:
        stmt = stmt.where(Tenant.status == status_filter)

    # Total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Paginación
    stmt = stmt.offset(pagination.offset).limit(pagination.limit).order_by(Tenant.name)
    items = (await db.execute(stmt)).scalars().all()

    return TenantListResponse(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    db: DBDep,
    superadmin: SuperAdminDep,
) -> TenantResponse:
    """Crea un nuevo tenant."""
    # Verificar slug único
    existing = (await db.execute(select(Tenant).where(Tenant.slug == body.slug))).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un tenant con el slug '{body.slug}'.",
        )

    # Límites por plan
    plan_limits = {
        TenantPlan.STARTER:      {"max_warehouses": 1,  "max_users": 10,  "max_skus": 10_000},
        TenantPlan.PROFESSIONAL: {"max_warehouses": 5,  "max_users": 50,  "max_skus": 100_000},
        TenantPlan.ENTERPRISE:   {"max_warehouses": 999, "max_users": 9999, "max_skus": 9_999_999},
    }
    limits = plan_limits[body.plan]

    tenant = Tenant(
        **body.model_dump(exclude={"plan"}),
        plan=body.plan,
        status=TenantStatus.TRIAL,
        **limits,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: uuid.UUID,
    db: DBDep,
    superadmin: SuperAdminDep,
) -> TenantResponse:
    """Obtiene un tenant por ID."""
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado.")
    return tenant
