"""
WMS Panama — Base Model
========================
Clase base para todos los modelos SQLAlchemy 2.0.
Incluye campos comunes: UUID, timestamps, soft delete, tenant y auditoria.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarativa para todos los modelos del WMS."""
    pass


class TimestampMixin:
    """
    Mixin de timestamps automaticos.
    created_at: se establece al crear el registro (server_default).
    updated_at: se actualiza automaticamente en cada UPDATE (onupdate).
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Fecha y hora de creacion del registro (UTC)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Fecha y hora de ultima modificacion (UTC)"
    )


class SoftDeleteMixin:
    """
    Mixin para eliminacion logica (soft delete).
    Los registros no se borran fisicamente — se marcan con deleted_at.
    Todos los queries deben filtrar WHERE deleted_at IS NULL.
    """
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Fecha de eliminacion logica. NULL = activo."
    )
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Usuario que elimino logicamente el registro"
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class AuditMixin:
    """
    Mixin de auditoria de creacion y modificacion.
    Registra quien creo y quien modifico cada registro.
    """
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="UUID del usuario que creo el registro"
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="UUID del usuario que hizo la ultima modificacion"
    )


class TenantMixin:
    """
    Mixin de multitenancy.
    CRITICO: tenant_id debe incluirse en TODOS los indices de busqueda.
    Garantiza aislamiento total entre empresas.
    """
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="ID del tenant (empresa). Aislamiento de datos."
    )


class WMSBase(Base, TimestampMixin, SoftDeleteMixin, AuditMixin):
    """
    Clase base completa para modelos WMS.
    Incluye: UUID PK, timestamps, soft delete, auditoria.
    NO incluye tenant_id (algunos modelos como Tenant no lo necesitan).
    """
    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        comment="Identificador unico universal del registro"
    )


class WMSTenantBase(WMSBase, TenantMixin):
    """
    Clase base para modelos que pertenecen a un tenant especifico.
    La MAYORIA de los modelos del WMS heredan de esta clase.
    """
    __abstract__ = True
