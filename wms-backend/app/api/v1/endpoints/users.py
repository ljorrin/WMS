"""
WMS Panama — User Endpoints
==============================
CRUD de usuarios dentro de un tenant.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import DBDep, CurrentUserDep, SuperAdminDep, PaginationDep
from app.core.security import hash_password
from app.models.core import User, UserStatus

router = APIRouter()


class UserCreate(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8)
    username: Optional[str] = None
    employee_id: Optional[str] = None
    phone: Optional[str] = None
    language: str = "es"
    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    language: Optional[str] = None
    username: Optional[str] = None
    employee_id: Optional[str] = None
    default_warehouse_id: Optional[uuid.UUID] = None
    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    full_name: str
    username: Optional[str]
    employee_id: Optional[str]
    phone: Optional[str]
    language: str
    status: UserStatus
    is_superadmin: bool
    tenant_id: uuid.UUID
    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int


@router.get("", response_model=UserListResponse)
async def list_users(
    db: DBDep,
    current_user: CurrentUserDep,
    pagination: PaginationDep,
    search: Optional[str] = Query(None),
    status_filter: Optional[UserStatus] = Query(None, alias="status"),
) -> UserListResponse:
    """Lista usuarios del tenant actual."""
    stmt = select(User).where(User.tenant_id == current_user.tenant_id)

    if search:
        stmt = stmt.where(
            User.email.ilike(f"%{search}%")
            | User.first_name.ilike(f"%{search}%")
            | User.last_name.ilike(f"%{search}%")
        )
    if status_filter:
        stmt = stmt.where(User.status == status_filter)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.offset(pagination.offset).limit(pagination.limit).order_by(User.last_name, User.first_name)
    items = (await db.execute(stmt)).scalars().all()

    return UserListResponse(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: DBDep,
    superadmin: SuperAdminDep,
) -> UserResponse:
    """Crea un nuevo usuario en el tenant (solo superadmin)."""
    # Verificar email único en el tenant
    existing = (await db.execute(
        select(User).where(
            User.tenant_id == superadmin.tenant_id,
            User.email == body.email.lower(),
        )
    )).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un usuario con el email '{body.email}' en este tenant.",
        )

    user = User(
        tenant_id=superadmin.tenant_id,
        email=body.email.lower(),
        first_name=body.first_name,
        last_name=body.last_name,
        hashed_password=hash_password(body.password),
        username=body.username,
        employee_id=body.employee_id,
        phone=body.phone,
        language=body.language,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: DBDep,
    current_user: CurrentUserDep,
) -> UserResponse:
    """Obtiene un usuario por ID (mismo tenant)."""
    user = await db.get(User, user_id)
    if not user or user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: DBDep,
    superadmin: SuperAdminDep,
) -> UserResponse:
    """Actualiza un usuario (solo superadmin)."""
    user = await db.get(User, user_id)
    if not user or user.tenant_id != superadmin.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: uuid.UUID,
    db: DBDep,
    superadmin: SuperAdminDep,
) -> None:
    """Desactiva un usuario (soft delete — no elimina de BD)."""
    user = await db.get(User, user_id)
    if not user or user.tenant_id != superadmin.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    if user.id == superadmin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta.",
        )

    user.status = UserStatus.INACTIVE
    await db.commit()
