"""
WMS Panamá — Slotting Dinámico (Dynamic Slotting) — FR-094…097
===============================================================
Ubicación óptima de productos según rotación (ABC por velocidad) y
re-slotting continuo. Cierra otra brecha frente a los WMS líderes:
no solo dónde cabe el producto, sino dónde DEBERÍA estar para minimizar
el recorrido de picking.

Modelo:
  • SlottingPolicy         — parámetros del análisis (ventana, umbrales ABC,
                             zona dorada de picking, zona de bulk).
  • SlottingRecommendation — propuestas de reubicación generadas por el motor,
                             con clase ABC, score de velocidad y motivo.

Convención del proyecto: columnas String para enums; multitenancy vía tenant_id.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import WMSTenantBase


SLOTTING_STRATEGIES = ("velocity_abc", "manual")
RECOMMENDATION_STATUSES = ("pending", "applied", "rejected", "expired")


class SlottingPolicy(WMSTenantBase):
    """Parámetros de la estrategia de slotting para una bodega (o global)."""
    __tablename__ = "slotting_policies"

    warehouse_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=True, index=True,
        comment="Bodega a la que aplica. NULL = política global del tenant.",
    )
    strategy: Mapped[str] = mapped_column(
        String(20), default="velocity_abc",
        comment="velocity_abc | manual",
    )
    velocity_window_days: Mapped[int] = mapped_column(
        Integer, default=90,
        comment="Ventana (días) de movimientos usada para medir rotación.",
    )
    abc_a_threshold: Mapped[float] = mapped_column(
        Numeric(5, 4), default=0.8,
        comment="Cuota acumulada de velocidad que define la clase A (p. ej. 0.80).",
    )
    abc_b_threshold: Mapped[float] = mapped_column(
        Numeric(5, 4), default=0.95,
        comment="Cuota acumulada que define hasta la clase B (p. ej. 0.95).",
    )
    golden_zone_code: Mapped[Optional[str]] = mapped_column(
        String(10), comment="Código de zona dorada (frente de picking más cercano)."
    )
    bulk_zone_code: Mapped[Optional[str]] = mapped_column(
        String(10), comment="Código de zona de bulk/reserva para baja rotación (C)."
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "warehouse_id", name="uq_slotting_policy_scope"),
    )


class SlottingRecommendation(WMSTenantBase):
    """Propuesta de reubicación generada por el motor de slotting."""
    __tablename__ = "slotting_recommendations"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    abc_class: Mapped[Optional[str]] = mapped_column(String(1), comment="A | B | C")
    velocity_score: Mapped[Optional[float]] = mapped_column(Numeric(14, 4))
    pick_count: Mapped[Optional[int]] = mapped_column(Integer)

    current_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True,
    )
    current_zone_code: Mapped[Optional[str]] = mapped_column(String(10))
    recommended_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True,
    )
    recommended_zone_code: Mapped[Optional[str]] = mapped_column(String(10))

    reason: Mapped[Optional[str]] = mapped_column(String(255))
    score_delta: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2), comment="Mejora estimada (proxy de ahorro de recorrido)."
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True,
        comment="pending | applied | rejected | expired",
    )
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    applied_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        Index("ix_slotting_recs_tenant_status", "tenant_id", "status"),
        Index("ix_slotting_recs_wh_status", "warehouse_id", "status"),
    )
