"""
WMS Panamá — YMS (Yard Management System) — FR-060
===================================================
Gestión de patio: muelles (docks), citas de transporte, cola de espera y
estadías. Usa columnas String para tipo/estado (sin enums nativos) para
simplificar el versionado del esquema.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import WMSTenantBase


class Dock(WMSTenantBase):
    """Muelle de carga/descarga de una bodega."""
    __tablename__ = "docks"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(200))
    dock_type: Mapped[str] = mapped_column(
        String(20), default="both", comment="receiving | shipping | both"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="available", comment="available | occupied | maintenance | blocked"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("warehouse_id", "code", name="uq_docks_warehouse_code"),
        Index("ix_docks_tenant_warehouse", "tenant_id", "warehouse_id"),
    )


class YardAppointment(WMSTenantBase):
    """Cita de transporte en el patio (YMS)."""
    __tablename__ = "yard_appointments"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    dock_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("docks.id", ondelete="SET NULL"), nullable=True,
    )
    appointment_number: Mapped[str] = mapped_column(String(50), nullable=False)
    appointment_type: Mapped[str] = mapped_column(
        String(20), default="inbound", comment="inbound | outbound"
    )
    carrier_name: Mapped[Optional[str]] = mapped_column(String(200))
    vehicle_plate: Mapped[Optional[str]] = mapped_column(String(20))
    driver_name: Mapped[Optional[str]] = mapped_column(String(200))
    reference: Mapped[Optional[str]] = mapped_column(
        String(100), comment="Número de ASN/SO asociado"
    )

    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    arrived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    at_dock_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    departed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(
        String(20), default="scheduled",
        comment="scheduled | arrived | at_dock | departed | cancelled | no_show",
    )
    queue_position: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("warehouse_id", "appointment_number", name="uq_yard_appt_warehouse_number"),
        Index("ix_yard_appt_tenant_status", "tenant_id", "status"),
        Index("ix_yard_appt_dock", "dock_id"),
    )
