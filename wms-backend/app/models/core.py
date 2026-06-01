"""
WMS Panama — Core Models
=========================
Modelos fundacionales del sistema:
- Tenant (empresa/cliente del WMS)
- Company (empresa operacional)
- Warehouse (bodega fisica)
- User (usuario del sistema)
- Role (rol de acceso)
- Permission (permiso granular)
- UserRole (asignacion de rol por bodega)
- AuditLog (log inmutable de operaciones)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional, List

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import WMSBase, WMSTenantBase


# ─── ENUMS ────────────────────────────────────────────────────────────────────

class TenantPlan(str, PyEnum):
    STARTER    = "starter"     # 1 bodega, hasta 10 usuarios
    PROFESSIONAL = "professional"  # 5 bodegas, hasta 50 usuarios
    ENTERPRISE = "enterprise"  # Sin limite, multiempresa


class TenantStatus(str, PyEnum):
    ACTIVE    = "active"
    SUSPENDED = "suspended"
    TRIAL     = "trial"
    CANCELLED = "cancelled"


class WarehouseType(str, PyEnum):
    DISTRIBUTION_CENTER = "distribution_center"
    FACTORY_WAREHOUSE   = "factory_warehouse"    # Bodega de fabrica (MP, PT)
    TRANSIT_WAREHOUSE   = "transit_warehouse"    # Bodega de transito
    RETURN_CENTER       = "return_center"        # Centro de devoluciones
    COLD_STORAGE        = "cold_storage"         # Almacenamiento frio
    BONDED_WAREHOUSE    = "bonded_warehouse"     # Bodega aduanera
    THIRD_PARTY         = "third_party"          # 3PL
    RETAIL_BACKROOM     = "retail_backroom"      # Trastienda retail
    VIRTUAL             = "virtual"              # Bodega virtual/logica


class WarehouseStatus(str, PyEnum):
    ACTIVE      = "active"
    INACTIVE    = "inactive"
    MAINTENANCE = "maintenance"


class UserStatus(str, PyEnum):
    ACTIVE   = "active"
    INACTIVE = "inactive"
    LOCKED   = "locked"      # Bloqueado por intentos fallidos
    PENDING  = "pending"     # Esperando activacion


class AuditAction(str, PyEnum):
    CREATE  = "create"
    READ    = "read"
    UPDATE  = "update"
    DELETE  = "delete"
    LOGIN   = "login"
    LOGOUT  = "logout"
    EXPORT  = "export"
    APPROVE = "approve"
    REJECT  = "reject"


class IndustryType(str, PyEnum):
    """Industrias soportadas por el WMS (multi-industria)."""
    CONSUMER_GOODS  = "consumer_goods"    # Consumo masivo
    AUTOMOTIVE      = "automotive"        # Automotriz
    PHARMACEUTICAL  = "pharmaceutical"    # Farmaceutico
    HARDWARE        = "hardware"          # Ferreteria
    ELECTRONICS     = "electronics"       # Electronica
    FASHION         = "fashion"           # Moda / textil
    AGRO_FOOD       = "agro_food"         # Agro-alimentario
    CHEMICAL        = "chemical"          # Quimica / peligrosos
    ECOMMERCE       = "ecommerce"         # eCommerce puro
    GENERAL         = "general"           # General / sin clasificar


# ─── TENANT ───────────────────────────────────────────────────────────────────

class Tenant(WMSBase):
    """
    Tenant = Cliente del WMS (empresa que contrata la plataforma).
    Nivel mas alto de la jerarquia. Aislamiento total de datos por tenant.
    Un Tenant puede tener multiples Companies y Warehouses.
    """
    __tablename__ = "tenants"

    # Identificacion
    name: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="Nombre legal o comercial del tenant"
    )
    slug: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True,
        comment="Identificador URL-friendly unico (ej: empresa-sa)"
    )
    legal_name: Mapped[Optional[str]] = mapped_column(
        String(300), nullable=True,
        comment="Razon social completa para documentos fiscales"
    )
    ruc: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, index=True,
        comment="RUC (Registro Unico de Contribuyente) en Panama"
    )
    dv: Mapped[Optional[str]] = mapped_column(
        String(2), nullable=True,
        comment="Digito verificador del RUC panamenio"
    )

    # Plan y estado
    plan: Mapped[TenantPlan] = mapped_column(
        Enum(TenantPlan), nullable=False, default=TenantPlan.STARTER,
        comment="Plan de suscripcion del tenant"
    )
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus), nullable=False, default=TenantStatus.TRIAL
    )

    # Configuracion
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, default="America/Panama",
        comment="Zona horaria por defecto (Panama UTC-5)"
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD",
        comment="Moneda principal (USD = Dolar / Balboa panamenio)"
    )
    locale: Mapped[str] = mapped_column(
        String(10), nullable=False, default="es-PA",
        comment="Locale para formatos de fecha/numero"
    )
    industries: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True,
        comment="Lista de industrias activas para este tenant"
    )

    # Contacto
    contact_email: Mapped[Optional[str]] = mapped_column(String(200))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(30))
    address: Mapped[Optional[str]] = mapped_column(Text)
    country: Mapped[str] = mapped_column(
        String(2), nullable=False, default="PA",
        comment="Codigo ISO 3166-1 alpha-2 del pais principal"
    )

    # Limites del plan
    max_warehouses: Mapped[int] = mapped_column(Integer, default=1)
    max_users: Mapped[int] = mapped_column(Integer, default=10)
    max_skus: Mapped[int] = mapped_column(Integer, default=10000)

    # Suscripcion
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    subscribed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Configuracion avanzada (extensible)
    settings: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="Configuracion JSON extensible del tenant"
    )

    # Relaciones
    companies: Mapped[List["Company"]] = relationship(back_populates="tenant", lazy="select")
    warehouses: Mapped[List["Warehouse"]] = relationship(back_populates="tenant", lazy="select")
    users: Mapped[List["User"]] = relationship(back_populates="tenant", lazy="select")

    __table_args__ = (
        Index("ix_tenants_slug", "slug"),
        Index("ix_tenants_ruc", "ruc"),
        Index("ix_tenants_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Tenant {self.slug} [{self.status}]>"


# ─── COMPANY ──────────────────────────────────────────────────────────────────

class Company(WMSTenantBase):
    """
    Company = Empresa operacional dentro del Tenant.
    Un Tenant puede tener multiples Companies (grupo empresarial).
    Cada Company tiene sus propias bodegas, clientes y proveedores.
    """
    __tablename__ = "companies"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )

    # Identificacion
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name: Mapped[Optional[str]] = mapped_column(String(300))
    ruc: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    dv: Mapped[Optional[str]] = mapped_column(String(2))
    industry: Mapped[IndustryType] = mapped_column(
        Enum(IndustryType), nullable=False, default=IndustryType.GENERAL
    )

    # Contacto
    email: Mapped[Optional[str]] = mapped_column(String(200))
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(2), default="PA")

    # GS1
    gs1_company_prefix: Mapped[Optional[str]] = mapped_column(
        String(13), nullable=True,
        comment="Prefijo GS1 de la empresa para generacion de GTINs/SSCCs"
    )
    gln: Mapped[Optional[str]] = mapped_column(
        String(13), nullable=True,
        comment="GLN (Global Location Number) de la empresa"
    )

    # Panama especifico
    dgi_authorized: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="Autorizado para facturacion electronica DGI"
    )
    dgi_environment: Mapped[str] = mapped_column(
        String(20), default="sandbox",
        comment="Ambiente DGI: sandbox | production"
    )
    free_trade_zone: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Zona franca si aplica: ZLC | PANAMA_PACIFICO | CIUDAD_SABER"
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # Relaciones
    tenant: Mapped["Tenant"] = relationship(back_populates="companies")
    warehouses: Mapped[List["Warehouse"]] = relationship(back_populates="company")

    __table_args__ = (
        Index("ix_companies_tenant", "tenant_id"),
        Index("ix_companies_tenant_ruc", "tenant_id", "ruc"),
        UniqueConstraint("tenant_id", "ruc", name="uq_companies_tenant_ruc"),
    )

    def __repr__(self) -> str:
        return f"<Company {self.name} [tenant={self.tenant_id}]>"


# ─── WAREHOUSE ────────────────────────────────────────────────────────────────

class Warehouse(WMSTenantBase):
    """
    Warehouse = Bodega fisica gestionada por el WMS.
    Una Company puede tener multiples Warehouses.
    Cada Warehouse tiene su propia configuracion operacional.
    """
    __tablename__ = "warehouses"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )

    # Identificacion
    code: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="Codigo corto de la bodega (ej: BOG-01, PTY-CD)"
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[WarehouseType] = mapped_column(
        Enum(WarehouseType), nullable=False,
        default=WarehouseType.DISTRIBUTION_CENTER
    )
    status: Mapped[WarehouseStatus] = mapped_column(
        Enum(WarehouseStatus), nullable=False, default=WarehouseStatus.ACTIVE
    )

    # Ubicacion fisica
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    province: Mapped[Optional[str]] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(2), default="PA")
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 8))
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(11, 8))

    # GS1 / Aduanas
    gln: Mapped[Optional[str]] = mapped_column(
        String(13),
        comment="GLN (Global Location Number) de la bodega — identificador GS1"
    )
    customs_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Codigo de instalacion aduanera ANA (si aplica)"
    )
    free_trade_zone: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Zona franca especial si la bodega esta en ZLC o similar"
    )
    bonded: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="True si es bodega aduanera (bonded warehouse)"
    )

    # Capacidad
    total_area_m2: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2),
        comment="Area total en metros cuadrados"
    )
    storage_area_m2: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    max_weight_kg: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    max_volume_m3: Mapped[Optional[float]] = mapped_column(Numeric(10, 3))
    total_locations: Mapped[Optional[int]] = mapped_column(Integer)

    # Configuracion operacional
    picking_strategy: Mapped[str] = mapped_column(
        String(20), default="FEFO",
        comment="Estrategia de picking: FEFO | FIFO | LIFO"
    )
    has_cold_storage: Mapped[bool] = mapped_column(Boolean, default=False)
    has_hazmat_zone: Mapped[bool] = mapped_column(Boolean, default=False)
    has_dock_management: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="True si tiene YMS (Yard Management System)"
    )
    offline_capable: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="True si soporta operacion offline con sincronizacion"
    )

    # Configuracion LMS
    shift_hours: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        comment="Configuracion de turnos: {morning: {start: 06:00, end: 14:00}}"
    )
    engineered_standards: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        comment="Estandares de ingenieria LMS por operacion (picks/hora, etc)"
    )

    settings: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # Relaciones
    tenant: Mapped["Tenant"] = relationship(back_populates="warehouses")
    company: Mapped["Company"] = relationship(back_populates="warehouses")

    __table_args__ = (
        Index("ix_warehouses_tenant_company", "tenant_id", "company_id"),
        UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),
        Index("ix_warehouses_gln", "gln"),
    )

    def __repr__(self) -> str:
        return f"<Warehouse {self.code} - {self.name}>"


# ─── ROLE & PERMISSION ────────────────────────────────────────────────────────

class Permission(WMSBase):
    """
    Permission = permiso atomico del sistema.
    Formato: modulo:recurso:accion (ej: inventory:adjustment:approve)
    """
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True,
        comment="Codigo del permiso: modulo:recurso:accion"
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    module: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="Modulo al que pertenece: inventory, inbound, outbound, etc."
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relaciones
    roles: Mapped[List["RolePermission"]] = relationship(back_populates="permission")

    def __repr__(self) -> str:
        return f"<Permission {self.code}>"


class Role(WMSTenantBase):
    """
    Role = conjunto de permisos asignables a usuarios.
    Los roles son por tenant (cada empresa puede tener sus propios roles).
    Roles del sistema (is_system=True) no pueden modificarse.
    """
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="True para roles del sistema que no pueden modificarse"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relaciones
    permissions: Mapped[List["RolePermission"]] = relationship(back_populates="role")
    user_roles: Mapped[List["UserRole"]] = relationship(back_populates="role")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
        Index("ix_roles_tenant", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<Role {self.name} [tenant={self.tenant_id}]>"


class RolePermission(WMSBase):
    """Tabla de union entre Role y Permission (M:N)."""
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False
    )

    role: Mapped["Role"] = relationship(back_populates="permissions")
    permission: Mapped["Permission"] = relationship(back_populates="roles")

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions"),
        Index("ix_role_permissions_role", "role_id"),
        Index("ix_role_permissions_permission", "permission_id"),
    )


# ─── USER ─────────────────────────────────────────────────────────────────────

class User(WMSTenantBase):
    """
    User = Usuario del sistema WMS.
    Un usuario pertenece a un Tenant.
    Sus permisos se definen mediante UserRole (rol por bodega).
    """
    __tablename__ = "users"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )

    # Identificacion
    email: Mapped[str] = mapped_column(
        String(254), nullable=False,
        comment="Email del usuario — usado como login"
    )
    username: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Nombre de usuario alternativo para login"
    )
    employee_id: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="ID de empleado en sistema HR del tenant"
    )

    # Autenticacion
    hashed_password: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        comment="Hash bcrypt de la contrasena. NULL si usa SSO/Keycloak."
    )
    keycloak_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True,
        comment="ID de usuario en Keycloak (SSO)"
    )
    mfa_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="True si el usuario tiene MFA activado"
    )
    mfa_secret: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Secreto TOTP cifrado para MFA. Almacenado cifrado con Vault."
    )

    # Perfil
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(5), default="es")

    # Estado
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus), nullable=False, default=UserStatus.PENDING
    )
    is_superadmin: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="Superadmin del tenant (acceso total sin restriccion de bodega)"
    )

    # Seguridad
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45))
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # RF device
    rf_pin: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True,
        comment="PIN de 4-6 digitos para login rapido en dispositivos RF"
    )
    default_warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relaciones
    tenant: Mapped["Tenant"] = relationship(back_populates="users")
    user_roles: Mapped[List["UserRole"]] = relationship(back_populates="user")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        Index("ix_users_tenant_email", "tenant_id", "email"),
        Index("ix_users_tenant_status", "tenant_id", "status"),
        Index("ix_users_keycloak", "keycloak_id"),
    )

    def __repr__(self) -> str:
        return f"<User {self.email} [{self.status}]>"


class UserRole(WMSBase):
    """
    Asignacion de Rol a Usuario por Bodega.
    Un usuario puede tener roles distintos en bodegas distintas.
    warehouse_id=NULL significa que el rol aplica a todas las bodegas del tenant.
    """
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False
    )
    warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=True,
        comment="NULL = rol aplica a todas las bodegas del tenant"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        comment="Fecha de expiracion del rol (NULL = permanente)"
    )

    # Relaciones
    user: Mapped["User"] = relationship(back_populates="user_roles")
    role: Mapped["Role"] = relationship(back_populates="user_roles")

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "warehouse_id", name="uq_user_roles"),
        Index("ix_user_roles_user", "user_id"),
        Index("ix_user_roles_warehouse", "warehouse_id"),
    )


# ─── AUDIT LOG ────────────────────────────────────────────────────────────────

class AuditLog(WMSTenantBase):
    """
    Log de auditoria inmutable.
    Registra TODA operacion realizada en el sistema.
    CRITICO: Requerimiento ANA — retener minimo 5 anos.
    Esta tabla NUNCA tiene soft delete — los registros son permanentes.
    """
    __tablename__ = "audit_logs"

    # No usamos SoftDeleteMixin aqui — audit logs son inmutables
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="SET NULL"),
        nullable=True
    )

    # Que ocurrio
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), nullable=False)
    entity_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment="Nombre del modelo afectado (ej: InventoryMovement)"
    )
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        comment="UUID del registro afectado"
    )

    # Datos del cambio
    before_data: Mapped[Optional[dict]] = mapped_column(
        JSONB, comment="Estado del registro ANTES del cambio"
    )
    after_data: Mapped[Optional[dict]] = mapped_column(
        JSONB, comment="Estado del registro DESPUES del cambio"
    )
    metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB, comment="Informacion adicional del evento"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, comment="Descripcion legible del evento para auditores"
    )

    # Contexto de red
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    request_id: Mapped[Optional[str]] = mapped_column(
        String(100), comment="ID de trazabilidad de la peticion HTTP"
    )

    # Timestamp (override — audit log usa server_default rigido)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Momento exacto del evento (inmutable)"
    )

    __table_args__ = (
        Index("ix_audit_tenant_entity", "tenant_id", "entity_type", "entity_id"),
        Index("ix_audit_tenant_user", "tenant_id", "user_id"),
        Index("ix_audit_tenant_occurred", "tenant_id", "occurred_at"),
        Index("ix_audit_warehouse", "warehouse_id"),
        # Particionamiento por occurred_at (definir en migracion)
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} on {self.entity_type} [{self.occurred_at}]>"
