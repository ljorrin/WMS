"""
WMS Panama — Schemas de Autenticación (Pydantic v2)
=====================================================
Request/Response models para el módulo de auth:
- Login / Logout
- Token pair (access + refresh)
- Refresh token
- Reset de contraseña
- Cambio de contraseña
- Perfil de usuario actual
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ── Config base ────────────────────────────────────────────────────────────────

class WMSBaseSchema(BaseModel):
    """Schema base con configuración estándar para todos los schemas del WMS."""
    model_config = {
        "from_attributes": True,    # Permite crear desde objetos SQLAlchemy
        "populate_by_name": True,   # Acepta alias y nombre real
        "str_strip_whitespace": True,
    }


# ── Login ──────────────────────────────────────────────────────────────────────

class LoginRequest(WMSBaseSchema):
    """Request para login con email y contraseña."""
    email: EmailStr = Field(..., description="Email del usuario")
    password: str = Field(..., min_length=1, description="Contraseña")
    remember_me: bool = Field(default=False, description="Extender duración del refresh token")

    @field_validator("email")
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.lower().strip()


class LoginRFRequest(WMSBaseSchema):
    """Login rápido desde dispositivos RF/handheld con PIN."""
    username: str = Field(..., description="Nombre de usuario o employee_id")
    rf_pin: str = Field(..., min_length=4, max_length=6, description="PIN de 4-6 dígitos")
    warehouse_id: uuid.UUID = Field(..., description="Bodega donde opera el usuario")
    tenant_slug: str = Field(..., description="Slug del tenant (empresa)")


# ── Token Response ─────────────────────────────────────────────────────────────

class TokenResponse(WMSBaseSchema):
    """Respuesta con par de tokens JWT."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Segundos hasta expiración del access token")


class RefreshTokenRequest(WMSBaseSchema):
    """Request para renovar el access token usando el refresh token."""
    refresh_token: str = Field(..., description="Refresh token válido")


class TokenVerifyRequest(WMSBaseSchema):
    """Verificar si un token es válido (sin renovar)."""
    token: str


class TokenVerifyResponse(WMSBaseSchema):
    """Resultado de verificación de token."""
    valid: bool
    user_id: Optional[uuid.UUID] = None
    tenant_id: Optional[uuid.UUID] = None
    expires_at: Optional[datetime] = None


# ── Password ───────────────────────────────────────────────────────────────────

class PasswordResetRequest(WMSBaseSchema):
    """Solicitar reset de contraseña por email."""
    email: EmailStr

    @field_validator("email")
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.lower().strip()


class PasswordResetConfirm(WMSBaseSchema):
    """Confirmar reset de contraseña con token y nueva contraseña."""
    token: str
    new_password: str = Field(..., min_length=8, description="Nueva contraseña (mín 8 caracteres)")
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "PasswordResetConfirm":
        if self.new_password != self.confirm_password:
            raise ValueError("Las contraseñas no coinciden.")
        return self

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Valida fortaleza mínima de contraseña."""
        errors = []
        if len(v) < 8:
            errors.append("mínimo 8 caracteres")
        if not any(c.isupper() for c in v):
            errors.append("al menos una mayúscula")
        if not any(c.isdigit() for c in v):
            errors.append("al menos un número")
        if errors:
            raise ValueError(f"Contraseña débil. Requiere: {', '.join(errors)}.")
        return v


class ChangePasswordRequest(WMSBaseSchema):
    """Cambiar contraseña (usuario autenticado)."""
    current_password: str
    new_password: str = Field(..., min_length=8)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "ChangePasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Las contraseñas no coinciden.")
        if self.new_password == self.current_password:
            raise ValueError("La nueva contraseña debe ser diferente a la actual.")
        return self


# ── Perfil del usuario ─────────────────────────────────────────────────────────

class UserPermissionInfo(WMSBaseSchema):
    code: str
    name: str
    module: str


class UserRoleInfo(WMSBaseSchema):
    id: uuid.UUID
    name: str
    warehouse_id: Optional[uuid.UUID] = None
    permissions: List[str] = []


class CurrentUserResponse(WMSBaseSchema):
    """Información del usuario autenticado (para /auth/me)."""
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    full_name: str
    username: Optional[str] = None
    employee_id: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    language: str = "es"
    tenant_id: uuid.UUID
    status: str
    is_superadmin: bool
    mfa_enabled: bool
    default_warehouse_id: Optional[uuid.UUID] = None
    roles: List[UserRoleInfo] = []
    all_permissions: List[str] = []
    last_login_at: Optional[datetime] = None


# ── MFA ────────────────────────────────────────────────────────────────────────

class MFASetupResponse(WMSBaseSchema):
    """Respuesta con configuración de MFA para el usuario."""
    secret: str = Field(description="Secreto TOTP para configurar en app de autenticación")
    qr_code_url: str = Field(description="URL del QR code para escanear")
    backup_codes: List[str] = Field(description="Códigos de respaldo (guardar en lugar seguro)")


class MFAVerifyRequest(WMSBaseSchema):
    """Verificar código TOTP de MFA."""
    code: str = Field(..., min_length=6, max_length=6, description="Código TOTP de 6 dígitos")


# ── Logout ─────────────────────────────────────────────────────────────────────

class LogoutRequest(WMSBaseSchema):
    """Logout — opcionalmente en todos los dispositivos."""
    all_devices: bool = Field(default=False, description="Cerrar sesión en todos los dispositivos")


class MessageResponse(WMSBaseSchema):
    """Respuesta genérica con mensaje."""
    message: str
    success: bool = True
