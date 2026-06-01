"""
WMS Panama — Seguridad y JWT
==============================
- Hashing de contraseñas con bcrypt
- Generación y verificación de JWT (access + refresh)
- Tokens de reset de contraseña
- Utilidades de seguridad generales
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Hashing ────────────────────────────────────────────────────────────────────

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,   # 12 rondas = balance seguridad/velocidad
)


def hash_password(password: str) -> str:
    """Genera el hash bcrypt de una contraseña."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña contra su hash bcrypt."""
    return pwd_context.verify(plain_password, hashed_password)


def needs_rehash(hashed_password: str) -> bool:
    """True si el hash fue generado con parámetros obsoletos."""
    return pwd_context.needs_update(hashed_password)


# ── JWT ────────────────────────────────────────────────────────────────────────

class TokenType:
    ACCESS  = "access"
    REFRESH = "refresh"
    RESET   = "reset"
    INVITE  = "invite"


def create_access_token(
    subject: str | uuid.UUID,
    tenant_id: str | uuid.UUID,
    extra_claims: Optional[dict] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Genera un JWT de acceso.

    Claims:
    - sub: user_id (UUID)
    - tid: tenant_id (UUID)
    - typ: "access"
    - jti: ID único del token (para revocación)
    - exp: expiración
    - iat: emitido en
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    payload: dict[str, Any] = {
        "sub": str(subject),
        "tid": str(tenant_id),
        "typ": TokenType.ACCESS,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire,
    }

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    subject: str | uuid.UUID,
    tenant_id: str | uuid.UUID,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Genera un JWT de refresh.
    Tiene mayor duración y solo sirve para obtener nuevos access tokens.
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))

    payload: dict[str, Any] = {
        "sub": str(subject),
        "tid": str(tenant_id),
        "typ": TokenType.REFRESH,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_reset_token(email: str) -> str:
    """Token para reset de contraseña (1 uso, expira en 24h)."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.RESET_PASSWORD_TOKEN_EXPIRE_HOURS)

    payload: dict[str, Any] = {
        "sub": email,
        "typ": TokenType.RESET,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decodifica y valida un JWT.

    Raises:
        JWTError: si el token es inválido o expirado.
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"verify_exp": True},
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decodifica un access token, verificando que sea del tipo correcto."""
    payload = decode_token(token)
    if payload.get("typ") != TokenType.ACCESS:
        raise JWTError("Token type mismatch: expected 'access'")
    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decodifica un refresh token, verificando tipo."""
    payload = decode_token(token)
    if payload.get("typ") != TokenType.REFRESH:
        raise JWTError("Token type mismatch: expected 'refresh'")
    return payload


def generate_api_key(prefix: str = "wms") -> str:
    """
    Genera una API key segura para integraciones.
    Formato: wms_<32 bytes hex>
    """
    token = secrets.token_hex(32)
    return f"{prefix}_{token}"


def generate_rf_pin(length: int = 4) -> str:
    """Genera un PIN numérico para dispositivos RF."""
    return "".join([str(secrets.randbelow(10)) for _ in range(length)])


def mask_sensitive(value: str, visible_chars: int = 4) -> str:
    """Enmascara datos sensibles para logs: 'mypassword123' → '****123'."""
    if len(value) <= visible_chars:
        return "****"
    return f"{'*' * (len(value) - visible_chars)}{value[-visible_chars:]}"
