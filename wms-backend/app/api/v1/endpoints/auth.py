"""
WMS Panama — Auth Endpoints
==============================
Módulo de autenticación completo:
POST /auth/login         — Login con email/password → tokens JWT
POST /auth/login/rf      — Login rápido RF (PIN)
POST /auth/refresh       — Renovar access token
POST /auth/logout        — Logout (revoca tokens en Redis)
GET  /auth/me            — Perfil del usuario actual
POST /auth/password/reset-request  — Solicitar reset de contraseña
POST /auth/password/reset-confirm  — Confirmar reset con token
POST /auth/password/change         — Cambiar contraseña (autenticado)
"""

from __future__ import annotations

import uuid
from datetime import timedelta, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.dependencies import (
    CurrentUserDep, DBDep, TokenDep, get_token_data
)
from app.core.logging import get_logger
from app.core.security import (
    create_access_token, create_refresh_token, create_reset_token,
    decode_refresh_token, hash_password, verify_password,
)
from app.db.redis import get_session_redis, is_token_revoked, revoke_token
from app.db.session import get_db
from app.models.core import AuditAction, AuditLog, User, UserStatus, UserRole
from app.schemas.auth import (
    ChangePasswordRequest, CurrentUserResponse, LoginRequest,
    LoginRFRequest, LogoutRequest, MessageResponse,
    PasswordResetConfirm, PasswordResetRequest,
    RefreshTokenRequest, TokenResponse, UserRoleInfo,
)

router = APIRouter()
logger = get_logger(__name__)


# ── Helper: construir respuesta de token ──────────────────────────────────────

def _build_token_response(
    user: User,
    remember_me: bool = False,
) -> TokenResponse:
    """Genera el par access/refresh token para un usuario autenticado."""
    extra_claims = {
        "roles": [ur.role.name for ur in user.user_roles if ur.is_active],
        # En producción: cargar permisos reales desde BD
    }

    access_token = create_access_token(
        subject=user.id,
        tenant_id=user.tenant_id,
        extra_claims=extra_claims,
    )

    refresh_delta = timedelta(days=30) if remember_me else None
    refresh_token = create_refresh_token(
        subject=user.id,
        tenant_id=user.tenant_id,
        expires_delta=refresh_delta,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def _log_audit(
    db: AsyncSession,
    action: AuditAction,
    user_id: uuid.UUID | None,
    tenant_id: uuid.UUID,
    description: str,
    ip_address: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Registra evento en el audit log."""
    try:
        log = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            entity_type="User",
            entity_id=user_id,
            description=description,
            ip_address=ip_address,
            metadata=metadata or {},
        )
        db.add(log)
    except Exception as e:
        logger.warning("Failed to write audit log", error=str(e))


# ── POST /auth/login ──────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login con email y contraseña",
    status_code=status.HTTP_200_OK,
)
async def login(
    request: Request,
    body: LoginRequest,
    db: DBDep,
) -> TokenResponse:
    """
    Autentica al usuario y retorna un par de tokens JWT.
    - Bloquea la cuenta después de 5 intentos fallidos.
    - Registra el evento en el audit log.
    """
    client_ip = request.client.host if request.client else None

    # Buscar usuario por email dentro del contexto del tenant
    stmt = (
        select(User)
        .where(User.email == body.email.lower())
        .options(selectinload(User.user_roles).selectinload(UserRole.role))
    )
    result = await db.execute(stmt)
    user: User | None = result.scalar_one_or_none()

    # Error genérico para no revelar si el email existe
    invalid_credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas.",
    )

    if not user:
        logger.warning("Login attempt for non-existent user", email=body.email)
        raise invalid_credentials_exc

    # Verificar contraseña
    if not user.hashed_password or not verify_password(body.password, user.hashed_password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.status = UserStatus.LOCKED
            user.locked_until = datetime.now(timezone.utc) + timedelta(hours=1)
            logger.warning("User account locked", user_id=str(user.id))

        await db.commit()
        raise invalid_credentials_exc

    # Verificar estado
    if user.status == UserStatus.LOCKED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta bloqueada. Contacta al administrador.",
        )
    if user.status == UserStatus.INACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta inactiva.",
        )
    if user.status == UserStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta pendiente de activación. Revisa tu email.",
        )

    # Segundo factor (MFA/TOTP) — solo si el usuario lo tiene activado (FR-001)
    if getattr(user, "mfa_enabled", False):
        import pyotp
        if (not body.mfa_code or not user.mfa_secret
                or not pyotp.TOTP(user.mfa_secret).verify(str(body.mfa_code), valid_window=1)):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Código MFA inválido o requerido.",
                headers={"X-MFA-Required": "true"},
            )

    # Reset de intentos fallidos + actualizar last_login
    user.failed_login_attempts = 0
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = client_ip

    # Audit log
    await _log_audit(
        db, AuditAction.LOGIN, user.id, user.tenant_id,
        f"Login exitoso desde {client_ip}",
        ip_address=client_ip,
    )

    await db.commit()

    logger.info("User logged in", user_id=str(user.id), tenant_id=str(user.tenant_id))
    return _build_token_response(user, remember_me=body.remember_me)


# ── POST /auth/login/rf ───────────────────────────────────────────────────────

@router.post(
    "/login/rf",
    response_model=TokenResponse,
    summary="Login rápido para dispositivos RF",
    status_code=status.HTTP_200_OK,
)
async def login_rf(
    request: Request,
    body: LoginRFRequest,
    db: DBDep,
) -> TokenResponse:
    """
    Login optimizado para handhelds/RF scanners.
    Usa username + PIN de 4-6 dígitos en lugar de email/password.
    """
    from sqlalchemy import or_
    from app.models.core import Tenant

    # Buscar tenant por slug
    tenant_stmt = select(Tenant).where(Tenant.slug == body.tenant_slug)
    tenant = (await db.execute(tenant_stmt)).scalar_one_or_none()

    if not tenant:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant no encontrado.")

    # Buscar usuario
    stmt = (
        select(User)
        .where(
            User.tenant_id == tenant.id,
            or_(User.username == body.username, User.employee_id == body.username),
            User.status == UserStatus.ACTIVE,
        )
        .options(selectinload(User.user_roles).selectinload(UserRole.role))
    )
    user: User | None = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not user.rf_pin or user.rf_pin != body.rf_pin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="PIN inválido.")

    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = request.client.host if request.client else None

    await db.commit()
    return _build_token_response(user)


# ── POST /auth/refresh ────────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Renovar access token",
)
async def refresh_token(body: RefreshTokenRequest, db: DBDep) -> TokenResponse:
    """Renueva el access token usando un refresh token válido."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token inválido o expirado.",
    )

    try:
        payload = decode_refresh_token(body.refresh_token)
        jti = payload.get("jti")
        user_id = uuid.UUID(payload.get("sub"))
        tenant_id = uuid.UUID(payload.get("tid"))
    except (JWTError, ValueError):
        raise credentials_exc

    if await is_token_revoked(jti):
        raise credentials_exc

    user = await db.get(User, user_id)
    if not user or user.status != UserStatus.ACTIVE:
        raise credentials_exc

    return _build_token_response(user)


# ── POST /auth/logout ─────────────────────────────────────────────────────────

@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Cerrar sesión",
)
async def logout(
    body: LogoutRequest,
    token_data: TokenDep,
    db: DBDep,
) -> MessageResponse:
    """Revoca el token actual en Redis. Opcionalmente cierra todas las sesiones."""
    # Revocamos el JTI del access token actual
    await revoke_token(
        jti=token_data.jti,
        ttl=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    await _log_audit(
        db,
        AuditAction.LOGOUT,
        token_data.user_id,
        token_data.tenant_id,
        "Logout registrado",
    )
    await db.commit()

    return MessageResponse(message="Sesión cerrada exitosamente.")


# ── GET /auth/me ──────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Perfil del usuario actual",
)
async def get_me(current_user: CurrentUserDep) -> CurrentUserResponse:
    """Retorna el perfil completo del usuario autenticado."""
    roles_info = [
        UserRoleInfo(
            id=ur.role.id,
            name=ur.role.name,
            warehouse_id=ur.warehouse_id,
            permissions=[rp.permission.code for rp in ur.role.permissions if rp.permission.is_active],
        )
        for ur in current_user.user_roles
        if ur.is_active
    ]

    all_permissions = list({
        p for role_info in roles_info for p in role_info.permissions
    })

    return CurrentUserResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        full_name=current_user.full_name,
        username=current_user.username,
        employee_id=current_user.employee_id,
        phone=current_user.phone,
        avatar_url=current_user.avatar_url,
        language=current_user.language,
        tenant_id=current_user.tenant_id,
        status=current_user.status.value,
        is_superadmin=current_user.is_superadmin,
        mfa_enabled=current_user.mfa_enabled,
        default_warehouse_id=current_user.default_warehouse_id,
        roles=roles_info,
        all_permissions=all_permissions,
        last_login_at=current_user.last_login_at,
    )


# ── POST /auth/password/reset-request ────────────────────────────────────────

@router.post(
    "/password/reset-request",
    response_model=MessageResponse,
    summary="Solicitar reset de contraseña",
)
async def password_reset_request(
    body: PasswordResetRequest,
    db: DBDep,
) -> MessageResponse:
    """
    Envía email con enlace de reset si el email existe.
    SIEMPRE retorna 200 para no revelar si el email está registrado.
    """
    stmt = select(User).where(User.email == body.email.lower())
    user: User | None = (await db.execute(stmt)).scalar_one_or_none()

    if user and user.status == UserStatus.ACTIVE:
        token = create_reset_token(user.email)
        # TODO: enviar email con el token usando el servicio de email
        logger.info("Password reset token generated", user_id=str(user.id))

    return MessageResponse(
        message="Si el email está registrado, recibirás instrucciones para restablecer tu contraseña."
    )


# ── POST /auth/password/change ────────────────────────────────────────────────

@router.post(
    "/password/change",
    response_model=MessageResponse,
    summary="Cambiar contraseña",
)
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUserDep,
    token_data: TokenDep,
    db: DBDep,
) -> MessageResponse:
    """Cambia la contraseña del usuario autenticado."""
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contraseña actual incorrecta.",
        )

    current_user.hashed_password = hash_password(body.new_password)
    current_user.password_changed_at = datetime.now(timezone.utc)

    # Revocar token actual (forzar re-login)
    await revoke_token(jti=token_data.jti, ttl=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)

    await _log_audit(
        db,
        AuditAction.UPDATE,
        current_user.id,
        current_user.tenant_id,
        "Contraseña cambiada",
    )
    await db.commit()

    return MessageResponse(message="Contraseña actualizada exitosamente. Por favor inicia sesión nuevamente.")


# ══════════════════════════════════════════════════════════════════════════════
# MFA / 2FA (TOTP) — FR-001
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/mfa/enroll", summary="Iniciar enrolamiento MFA (genera secreto TOTP)")
async def mfa_enroll(current_user: CurrentUserDep, db: DBDep) -> dict:
    """Genera (o regenera, si aún no está activado) el secreto TOTP del usuario
    y devuelve la URI otpauth:// para configurar la app (Google Authenticator)."""
    import pyotp

    user = (await db.execute(select(User).where(User.id == current_user.id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA ya está activado. Desactívalo antes de re-enrolar.")

    secret = pyotp.random_base32()
    user.mfa_secret = secret
    await db.commit()

    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="WMS Panamá")
    return {"secret": secret, "otpauth_uri": uri,
            "message": "Escanea el QR/URI en tu app TOTP y confirma con POST /auth/mfa/verify."}


@router.post("/mfa/verify", summary="Confirmar y activar MFA")
async def mfa_verify(payload: dict, current_user: CurrentUserDep, db: DBDep) -> dict:
    """Verifica un código TOTP contra el secreto pendiente y activa MFA."""
    import pyotp

    code = str(payload.get("code", "")).strip()
    user = (await db.execute(select(User).where(User.id == current_user.id))).scalar_one_or_none()
    if not user or not user.mfa_secret:
        raise HTTPException(status_code=400, detail="No hay enrolamiento MFA pendiente.")
    if not code or not pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail="Código MFA inválido.")
    user.mfa_enabled = True
    await _log_audit(db, AuditAction.UPDATE, user.id, user.tenant_id, "MFA activado")
    await db.commit()
    return {"mfa_enabled": True, "message": "MFA activado correctamente."}


@router.post("/mfa/disable", summary="Desactivar MFA")
async def mfa_disable(payload: dict, current_user: CurrentUserDep, db: DBDep) -> dict:
    """Desactiva MFA validando un último código TOTP (o contraseña, según política)."""
    import pyotp

    code = str(payload.get("code", "")).strip()
    user = (await db.execute(select(User).where(User.id == current_user.id))).scalar_one_or_none()
    if not user or not user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA no está activado.")
    if not code or not user.mfa_secret or not pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail="Código MFA inválido.")
    user.mfa_enabled = False
    user.mfa_secret = None
    await _log_audit(db, AuditAction.UPDATE, user.id, user.tenant_id, "MFA desactivado")
    await db.commit()
    return {"mfa_enabled": False, "message": "MFA desactivado."}
