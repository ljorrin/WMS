"""
WMS Panama — User Endpoints
==============================
CRUD de usuarios dentro de un tenant.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status, Response
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


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
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


@router.post("/{user_id}/anonymize", status_code=status.HTTP_200_OK)
async def anonymize_user(
    user_id: uuid.UUID,
    db: DBDep,
    superadmin: SuperAdminDep,
) -> dict:
    """Anonimiza los datos personales de un usuario conforme a la Ley 81 de 2019
    (derecho al olvido). Reemplaza PII por valores no identificables y desactiva
    la cuenta; conserva el id para integridad referencial de la auditoría."""
    user = await db.get(User, user_id)
    if not user or user.tenant_id != superadmin.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    if user.id == superadmin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No puedes anonimizar tu propia cuenta.")

    token = uuid.uuid4().hex[:12]
    user.first_name = "ANONIMIZADO"
    user.last_name = "ANONIMIZADO"
    user.email = f"anon-{token}@anonimizado.local"
    user.username = f"anon-{token}"
    user.phone = None
    user.avatar_url = None
    user.hashed_password = None
    user.mfa_enabled = False
    user.mfa_secret = None
    user.rf_pin = None
    user.status = UserStatus.INACTIVE
    await db.commit()
    return {"user_id": str(user_id), "anonymized": True,
            "message": "Datos personales anonimizados (Ley 81 de 2019)."}


# ── Ley 81 de 2019 — Derecho al olvido / anonimización (REG-006) ─────────────
@router.post("/{user_id}/anonymize", summary="Anonimizar datos personales (Ley 81)")
async def anonymize_user(
    user_id: uuid.UUID,
    superadmin: SuperAdminDep,
    db: DBDep,
) -> dict:
    """Anonimiza de forma irreversible los datos personales del usuario conforme
    a la Ley 81 de 2019 (derecho al olvido). Conserva id/tenant para integridad
    referencial e historial, pero elimina toda PII y deshabilita el acceso."""
    from datetime import datetime, timezone

    user = (await db.execute(select(User).where(
        User.id == user_id, User.tenant_id == superadmin.tenant_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    anon = uuid.uuid4().hex[:12]
    user.email = f"anon+{anon}@anonimizado.local"
    user.username = f"anon_{anon}"
    user.first_name = "ANONIMIZADO"
    user.last_name = "ANONIMIZADO"
    for attr in ("phone", "avatar_url", "rf_pin", "employee_id", "hashed_password",
                 "mfa_secret", "last_login_ip", "keycloak_id"):
        if hasattr(user, attr):
            setattr(user, attr, None)
    if hasattr(user, "mfa_enabled"):
        user.mfa_enabled = False
    user.status = UserStatus.INACTIVE
    user.deleted_at = datetime.now(timezone.utc)
    user.deleted_by = superadmin.id
    await db.commit()
    return {"anonymized": True, "user_id": str(user_id),
            "message": "Datos personales anonimizados conforme a la Ley 81 de 2019."}
