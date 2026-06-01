"""
WMS Panama — Dependencies de FastAPI
=======================================
Dependencias reutilizables para inyección en endpoints:
- Autenticación JWT (current_user, require_superadmin)
- Paginación estándar
- Tenant context
- Rate limiting
"""

from __future__ import annotations

import uuid
from typing import Optional, Annotated

from fastapi import Depends, HTTPException, Security, status, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import decode_access_token
from app.db.session import get_db
from app.db.redis import is_token_revoked, get_redis, check_rate_limit

logger = get_logger(__name__)
security = HTTPBearer(auto_error=True)


# ── Tipos anotados ─────────────────────────────────────────────────────────────

DBDep = Annotated[AsyncSession, Depends(get_db)]


# ── Paginación ─────────────────────────────────────────────────────────────────

class PaginationParams:
    """Parámetros de paginación estándar para todos los listados."""

    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="Número de página (inicia en 1)"),
        page_size: int = Query(
            default=settings.DEFAULT_PAGE_SIZE,
            ge=1,
            le=settings.MAX_PAGE_SIZE,
            description=f"Elementos por página (máx {settings.MAX_PAGE_SIZE})",
        ),
    ):
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size
        self.limit = page_size


PaginationDep = Annotated[PaginationParams, Depends(PaginationParams)]


# ── Contexto del Token JWT ─────────────────────────────────────────────────────

class TokenData:
    """Datos extraídos del JWT decodificado."""

    def __init__(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        jti: str,
        roles: list[str] = None,
        permissions: list[str] = None,
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.jti = jti
        self.roles = roles or []
        self.permissions = permissions or []


async def get_token_data(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> TokenData:
    """
    Extrae y valida el token JWT de la cabecera Authorization.
    Verifica que no esté en la blacklist de Redis.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(credentials.credentials)
        user_id_str: str = payload.get("sub")
        tenant_id_str: str = payload.get("tid")
        jti: str = payload.get("jti")

        if not user_id_str or not tenant_id_str or not jti:
            raise credentials_exception

        # Verificar blacklist
        if await is_token_revoked(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token revocado. Por favor inicia sesión nuevamente.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return TokenData(
            user_id=uuid.UUID(user_id_str),
            tenant_id=uuid.UUID(tenant_id_str),
            jti=jti,
            roles=payload.get("roles", []),
            permissions=payload.get("permissions", []),
        )

    except JWTError as e:
        logger.warning("JWT validation failed", error=str(e))
        raise credentials_exception
    except ValueError as e:
        logger.warning("Invalid UUID in token", error=str(e))
        raise credentials_exception


TokenDep = Annotated[TokenData, Depends(get_token_data)]


# ── Usuario actual ─────────────────────────────────────────────────────────────

async def get_current_user(
    token_data: TokenDep,
    db: DBDep,
) -> "User":  # type: ignore  # evitar import circular
    """
    Obtiene el usuario activo desde la BD.
    Verifica que exista y no esté bloqueado/inactivo.
    """
    from app.models.core import User, UserStatus

    user = await db.get(User, token_data.user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado.",
        )

    if user.status == UserStatus.INACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo.",
        )

    if user.status == UserStatus.LOCKED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta bloqueada. Contacta al administrador.",
        )

    # Verificar que el tenant_id del token coincida
    if str(user.tenant_id) != str(token_data.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token inválido para este tenant.",
        )

    return user


CurrentUserDep = Annotated["User", Depends(get_current_user)]


# ── Permisos ───────────────────────────────────────────────────────────────────

def require_permission(permission_code: str):
    """
    Factory de dependency para verificar un permiso específico.

    Uso:
        @router.post("/", dependencies=[Depends(require_permission("inventory:adjustment:approve"))])
    """
    async def _check_permission(
        token_data: TokenDep,
        current_user: CurrentUserDep,
    ) -> None:
        # Superadmin siempre tiene acceso
        if current_user.is_superadmin:
            return

        if permission_code not in token_data.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso requerido: {permission_code}",
            )

    return _check_permission


def require_superadmin(current_user: CurrentUserDep) -> "User":
    """Verifica que el usuario sea superadmin del tenant."""
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de superadministrador.",
        )
    return current_user


SuperAdminDep = Annotated["User", Depends(require_superadmin)]


# ── Rate Limiting ─────────────────────────────────────────────────────────────

def rate_limit(limit: int, window: int = 60, key_prefix: str = "api"):
    """
    Middleware de rate limiting por IP + endpoint.
    limit: máximo de requests en la ventana
    window: ventana en segundos
    """
    async def _rate_limit(
        request,  # Request de Starlette
        redis=Depends(lambda: get_redis()),
    ) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"rate:{key_prefix}:{client_ip}"

        allowed, remaining = await check_rate_limit(key, limit=limit, window=window)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiadas solicitudes. Intenta nuevamente en {window} segundos.",
                headers={"Retry-After": str(window), "X-RateLimit-Remaining": "0"},
            )

    return _rate_limit
