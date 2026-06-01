"""
WMS Panama — Schemas de Inventario (Pydantic v2)
=================================================
Request/Response models para el módulo de inventario:
- Stock queries (por producto, ubicación, lote, serie)
- Movimientos de inventario (Event Sourcing)
- Ajustes con flujo de aprobación
- Conteo cíclico
- Reservas
- Alertas de stock
"""

from __future__ import annotations

import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator, model_validator


class WMSSchema(BaseModel):
    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
        "str_strip_whitespace": True,
    }


# ── Batch / Lote ──────────────────────────────────────────────────────────────

class BatchCreate(WMSSchema):
    """Creación de un número de lote."""
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    lot_number: str = Field(..., min_length=1, max_length=100)
    expiry_date: Optional[date] = None
    manufacture_date: Optional[date] = None
    supplier_lot: Optional[str] = None
    quantity_received: Decimal = Field(..., gt=0)


class BatchResponse(WMSSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    lot_number: str
    expiry_date: Optional[date]
    manufacture_date: Optional[date]
    supplier_lot: Optional[str]
    quantity_received: Decimal
    quantity_available: Decimal
    quantity_on_hold: Decimal
    days_to_expiry: Optional[int] = None
    is_expired: bool = False
    is_near_expiry: bool = False
    status: str
    created_at: datetime


# ── Serial Number ─────────────────────────────────────────────────────────────

class SerialNumberCreate(WMSSchema):
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    serial_number: str = Field(..., min_length=1, max_length=100)
    batch_id: Optional[uuid.UUID] = None
    lot_number: Optional[str] = None


class SerialNumberResponse(WMSSchema):
    id: uuid.UUID
    product_id: uuid.UUID
    serial_number: str
    status: str
    location_id: Optional[uuid.UUID]
    batch_id: Optional[uuid.UUID]
    received_at: datetime
    shipped_at: Optional[datetime]


# ── Inventory Level (Stock por ubicación) ─────────────────────────────────────

class InventoryLevelResponse(WMSSchema):
    """Stock de un SKU en una ubicación específica."""
    id: uuid.UUID
    tenant_id: uuid.UUID
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    location_id: uuid.UUID
    batch_id: Optional[uuid.UUID]
    serial_id: Optional[uuid.UUID]

    # Cantidades
    quantity_on_hand: Decimal       # Físico total en la ubicación
    quantity_available: Decimal     # Disponible para picking
    quantity_reserved: Decimal      # Reservado para órdenes
    quantity_in_transit: Decimal    # En movimiento

    status: str
    tracking_type: str

    # Datos derivados (calculados)
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    location_code: Optional[str] = None
    lot_number: Optional[str] = None
    expiry_date: Optional[date] = None
    days_to_expiry: Optional[int] = None

    last_movement_at: Optional[datetime]
    last_count_at: Optional[datetime]
    updated_at: datetime


class StockSummaryResponse(WMSSchema):
    """Resumen de stock de un SKU en toda la bodega."""
    product_id: uuid.UUID
    warehouse_id: uuid.UUID
    product_code: str
    product_name: str
    unit_of_measure: str

    # Totales consolidados
    total_on_hand: Decimal
    total_available: Decimal
    total_reserved: Decimal
    total_in_transit: Decimal
    total_quarantine: Decimal

    # Por lote (si aplica)
    batches: List[BatchStockDetail] = []

    # Alertas
    is_below_min_stock: bool = False
    is_above_max_stock: bool = False
    min_stock: Optional[Decimal] = None
    max_stock: Optional[Decimal] = None
    reorder_point: Optional[Decimal] = None


class BatchStockDetail(WMSSchema):
    """Detalle de stock por lote dentro de un SKU."""
    batch_id: uuid.UUID
    lot_number: str
    expiry_date: Optional[date]
    days_to_expiry: Optional[int]
    quantity_available: Decimal
    locations: List[str] = []  # Códigos de ubicación


# Fix forward references
StockSummaryResponse.model_rebuild()


# ── Movimientos de Inventario (Event Sourcing) ────────────────────────────────

class InventoryMovementCreate(WMSSchema):
    """
    Registra un movimiento de inventario.
    REGLA: Un movimiento es inmutable — nunca se edita, solo se crea otro de reversa.
    """
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    movement_type: str
    quantity: Decimal = Field(..., description="Siempre positivo. El tipo define la dirección.")

    # Origen y destino
    from_location_id: Optional[uuid.UUID] = None
    to_location_id: Optional[uuid.UUID] = None

    # Trazabilidad
    batch_id: Optional[uuid.UUID] = None
    serial_id: Optional[uuid.UUID] = None
    lot_number: Optional[str] = None

    # Referencia al documento origen
    reference_type: Optional[str] = None   # "PO", "SO", "TRANSFER", "ADJUSTMENT"
    reference_id: Optional[uuid.UUID] = None
    reference_number: Optional[str] = None

    # Costo
    unit_cost: Optional[Decimal] = Field(None, ge=0)

    notes: Optional[str] = None

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("La cantidad debe ser mayor a cero.")
        return v


class InventoryMovementResponse(WMSSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    movement_type: str
    quantity: Decimal
    unit_cost: Optional[Decimal]
    total_cost: Optional[Decimal]

    from_location_id: Optional[uuid.UUID]
    to_location_id: Optional[uuid.UUID]
    batch_id: Optional[uuid.UUID]
    serial_id: Optional[uuid.UUID]
    lot_number: Optional[str]

    reference_type: Optional[str]
    reference_id: Optional[uuid.UUID]
    reference_number: Optional[str]

    notes: Optional[str]
    user_id: Optional[uuid.UUID]
    occurred_at: datetime

    # Datos enriquecidos
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    from_location_code: Optional[str] = None
    to_location_code: Optional[str] = None


class MovementListResponse(WMSSchema):
    items: List[InventoryMovementResponse]
    total: int
    page: int
    page_size: int


# ── Ajustes de Inventario ─────────────────────────────────────────────────────

class AdjustmentLineCreate(WMSSchema):
    """Línea de un ajuste de inventario."""
    product_id: uuid.UUID
    location_id: uuid.UUID
    batch_id: Optional[uuid.UUID] = None
    lot_number: Optional[str] = None
    quantity_system: Decimal = Field(..., description="Cantidad según sistema")
    quantity_physical: Decimal = Field(..., description="Cantidad contada físicamente", ge=0)
    unit_cost: Optional[Decimal] = Field(None, ge=0)
    notes: Optional[str] = None

    @property
    def variance(self) -> Decimal:
        return self.quantity_physical - self.quantity_system

    @property
    def variance_type(self) -> str:
        v = self.variance
        if v > 0:
            return "surplus"     # Sobrante
        elif v < 0:
            return "shortage"    # Faltante
        return "none"


class InventoryAdjustmentCreate(WMSSchema):
    """Creación de un ajuste de inventario (requiere aprobación)."""
    warehouse_id: uuid.UUID
    reason: str = Field(..., min_length=5, description="Motivo del ajuste")
    reason_code: str = Field(..., description="Código de razón: DAMAGE, EXPIRED, COUNT_ERROR, THEFT, etc.")
    lines: List[AdjustmentLineCreate] = Field(..., min_length=1, max_length=500)
    notes: Optional[str] = None
    reference_number: Optional[str] = None


class AdjustmentLineResponse(WMSSchema):
    id: uuid.UUID
    product_id: uuid.UUID
    location_id: uuid.UUID
    batch_id: Optional[uuid.UUID]
    lot_number: Optional[str]
    quantity_system: Decimal
    quantity_physical: Decimal
    variance: Decimal
    variance_type: str
    unit_cost: Optional[Decimal]
    total_variance_cost: Optional[Decimal]
    notes: Optional[str]
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    location_code: Optional[str] = None


class InventoryAdjustmentResponse(WMSSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    warehouse_id: uuid.UUID
    adjustment_number: str
    reason: str
    reason_code: str
    status: str    # draft | pending_approval | approved | rejected | applied
    notes: Optional[str]
    reference_number: Optional[str]
    lines: List[AdjustmentLineResponse] = []
    total_lines: int
    total_variance_value: Optional[Decimal]
    created_by: uuid.UUID
    approved_by: Optional[uuid.UUID]
    applied_by: Optional[uuid.UUID]
    created_at: datetime
    approved_at: Optional[datetime]
    applied_at: Optional[datetime]


class AdjustmentApproveRequest(WMSSchema):
    approved: bool = True
    notes: Optional[str] = None


# ── Conteo Cíclico ────────────────────────────────────────────────────────────

class CycleCountCreate(WMSSchema):
    """Crear una tarea de conteo cíclico."""
    warehouse_id: uuid.UUID
    count_type: str = Field(
        default="location",
        description="location | product | zone | random | full"
    )
    name: str = Field(..., min_length=3, max_length=200)

    # Criterios de selección
    zone_ids: Optional[List[uuid.UUID]] = None
    location_ids: Optional[List[uuid.UUID]] = None
    product_ids: Optional[List[uuid.UUID]] = None
    category_ids: Optional[List[uuid.UUID]] = None

    scheduled_date: Optional[date] = None
    notes: Optional[str] = None


class CycleCountLineResult(WMSSchema):
    """Resultado de contar una línea del ciclo."""
    location_id: uuid.UUID
    product_id: uuid.UUID
    batch_id: Optional[uuid.UUID] = None
    lot_number: Optional[str] = None
    quantity_counted: Decimal = Field(..., ge=0)
    notes: Optional[str] = None
    counter_id: Optional[uuid.UUID] = None  # Usuario que contó


class CycleCountLineResponse(WMSSchema):
    id: uuid.UUID
    location_id: uuid.UUID
    product_id: uuid.UUID
    batch_id: Optional[uuid.UUID]
    lot_number: Optional[str]
    quantity_system: Optional[Decimal]
    quantity_counted: Optional[Decimal]
    variance: Optional[Decimal]
    variance_pct: Optional[Decimal]
    status: str    # pending | counted | verified | discrepancy
    counted_at: Optional[datetime]
    counted_by: Optional[uuid.UUID]
    location_code: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None


class CycleCountResponse(WMSSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    warehouse_id: uuid.UUID
    count_number: str
    name: str
    count_type: str
    status: str     # draft | in_progress | completed | cancelled
    scheduled_date: Optional[date]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    notes: Optional[str]
    lines: List[CycleCountLineResponse] = []
    total_lines: int
    counted_lines: int
    discrepancy_lines: int
    accuracy_pct: Optional[Decimal]
    created_at: datetime


# ── Reservas ──────────────────────────────────────────────────────────────────

class InventoryReservationCreate(WMSSchema):
    """Reserva stock para una orden (soft o hard)."""
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    quantity: Decimal = Field(..., gt=0)
    reservation_type: str = "soft"    # soft | hard
    reference_type: str               # "SO" | "TRANSFER" | etc.
    reference_id: uuid.UUID
    reference_number: str
    batch_id: Optional[uuid.UUID] = None
    location_id: Optional[uuid.UUID] = None
    lot_number: Optional[str] = None
    expiry_date_after: Optional[date] = None  # Para selección FEFO


class InventoryReservationResponse(WMSSchema):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    quantity: Decimal
    reservation_type: str
    status: str    # active | fulfilled | cancelled | expired
    reference_type: str
    reference_id: uuid.UUID
    reference_number: str
    batch_id: Optional[uuid.UUID]
    location_id: Optional[uuid.UUID]
    expires_at: Optional[datetime]
    created_at: datetime


# ── Stock Alert ───────────────────────────────────────────────────────────────

class StockAlertResponse(WMSSchema):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    alert_type: str    # below_min | above_max | near_expiry | expired | blocked
    severity: str      # info | warning | critical
    current_quantity: Decimal
    threshold_quantity: Optional[Decimal]
    expiry_date: Optional[date]
    days_to_expiry: Optional[int]
    message: str
    is_resolved: bool
    created_at: datetime
    resolved_at: Optional[datetime]
    product_code: Optional[str] = None
    product_name: Optional[str] = None


# ── Filtros y Queries ─────────────────────────────────────────────────────────

class StockQueryParams(WMSSchema):
    """Parámetros para consultar stock."""
    warehouse_id: Optional[uuid.UUID] = None
    product_id: Optional[uuid.UUID] = None
    location_id: Optional[uuid.UUID] = None
    zone_id: Optional[uuid.UUID] = None
    batch_id: Optional[uuid.UUID] = None
    lot_number: Optional[str] = None
    status: Optional[str] = None
    tracking_type: Optional[str] = None
    near_expiry_days: Optional[int] = Field(None, ge=1, le=365)
    include_zero_stock: bool = False
    search: Optional[str] = None


class MovementQueryParams(WMSSchema):
    """Filtros para consultar movimientos de inventario."""
    warehouse_id: Optional[uuid.UUID] = None
    product_id: Optional[uuid.UUID] = None
    movement_type: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[uuid.UUID] = None
    location_id: Optional[uuid.UUID] = None
    batch_id: Optional[uuid.UUID] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    user_id: Optional[uuid.UUID] = None
