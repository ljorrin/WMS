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
    lot_number: str = Field(alias="batch_number")
    expiry_date: Optional[date] = None
    manufacture_date: Optional[date] = None
    supplier_lot: Optional[str] = None
    quantity_received: Decimal = Decimal("0")
    quantity_available: Decimal = Decimal("0")
    quantity_on_hold: Decimal = Decimal("0")
    days_to_expiry: Optional[int] = None
    is_expired: bool = False
    is_near_expiry: bool = False
    status: str = "active"
    created_at: datetime
    product_code: Optional[str] = None
    product_name: Optional[str] = None


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
    location_id: Optional[uuid.UUID] = None
    batch_id: Optional[uuid.UUID] = None
    received_at: datetime
    shipped_at: Optional[datetime] = None


# ── Inventory Level (Stock por ubicación) ─────────────────────────────────────

class InventoryLevelResponse(WMSSchema):
    """Stock de un SKU en una ubicación específica."""
    id: uuid.UUID
    tenant_id: uuid.UUID
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    location_id: uuid.UUID
    batch_id: Optional[uuid.UUID] = None
    serial_id: Optional[uuid.UUID] = None

    # Cantidades
    quantity_on_hand: Decimal       # Físico total en la ubicación
    quantity_available: Decimal     # Disponible para picking
    quantity_reserved: Decimal      # Reservado para órdenes
    quantity_in_transit: Decimal = Decimal("0")    # En movimiento
    quantity_in_picking: Decimal = Decimal("0")
    quantity_damaged: Decimal = Decimal("0")

    status: str
    tracking_type: str = "DEFAULT"

    # Datos derivados (calculados)
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    location_code: Optional[str] = None
    lot_number: Optional[str] = None
    expiry_date: Optional[date] = None
    days_to_expiry: Optional[int] = None

    last_movement_at: Optional[datetime] = None
    last_count_at: Optional[datetime] = None
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
    unit_cost: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None

    from_location_id: Optional[uuid.UUID] = None
    to_location_id: Optional[uuid.UUID] = None
    batch_id: Optional[uuid.UUID] = None
    serial_id: Optional[uuid.UUID] = Field(None, alias="serial_number_id")
    lot_number: Optional[str] = None

    reference_type: Optional[str] = Field(None, alias="source_document_type")
    reference_id: Optional[uuid.UUID] = Field(None, alias="source_document_id")
    reference_number: Optional[str] = Field(None, alias="source_document_number")

    notes: Optional[str] = None
    user_id: Optional[uuid.UUID] = Field(None, alias="operator_id")
    occurred_at: datetime

    # Datos enriquecidos
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    from_location_code: Optional[str] = None
    to_location_code: Optional[str] = None
    location_id: Optional[uuid.UUID] = None
    location_code: Optional[str] = None
    batch_number: Optional[str] = None


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
    quantity_system: Decimal = Decimal("0")
    quantity_physical: Decimal = Decimal("0")
    variance: Decimal = Decimal("0")
    variance_type: str = "none"
    unit_cost: Optional[Decimal] = None
    total_variance_cost: Optional[Decimal] = None
    notes: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    location_code: Optional[str] = None


class InventoryAdjustmentResponse(WMSSchema):
    id: uuid.UUID
    tenant_id: uuid.UUID
    warehouse_id: uuid.UUID
    adjustment_number: str
    reason: str
    reason_code: Optional[str] = None
    status: str    # draft | pending_approval | approved | rejected | applied
    notes: Optional[str] = None
    reference_number: Optional[str] = None
    lines: List[AdjustmentLineResponse] = []
    total_lines: int = 0
    total_variance_value: Optional[Decimal] = None
    created_by_id: Optional[uuid.UUID] = None
    approved_by: Optional[uuid.UUID] = None
    applied_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    approved_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None


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
    batch_id: Optional[uuid.UUID] = None
    lot_number: Optional[str] = None
    quantity_system: Optional[Decimal] = None
    quantity_counted: Optional[Decimal] = None
    variance: Optional[Decimal] = None
    variance_pct: Optional[Decimal] = None
    status: str = "pending"   # pending | counted | verified | discrepancy
    counted_at: Optional[datetime] = None
    counted_by: Optional[uuid.UUID] = None
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
    scheduled_date: Optional[date] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None
    lines: List[CycleCountLineResponse] = []
    total_lines: int
    counted_lines: int
    discrepancy_lines: int
    accuracy_pct: Optional[Decimal] = None
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
    batch_id: Optional[uuid.UUID] = None
    location_id: Optional[uuid.UUID] = None
    expires_at: Optional[datetime] = None
    created_at: datetime


# ── Stock Alert ───────────────────────────────────────────────────────────────

class StockAlertResponse(WMSSchema):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    alert_type: str    # below_min | above_max | near_expiry | expired | blocked
    severity: str      # info | warning | critical
    current_quantity: Decimal
    threshold_quantity: Optional[Decimal] = None
    expiry_date: Optional[date] = None
    days_to_expiry: Optional[int] = None
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


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD / KPIs INVENTARIO
# ══════════════════════════════════════════════════════════════════════════════

class InventoryDashboardMetrics(WMSSchema):
    """KPIs del módulo de inventario para el dashboard inicial."""
    # Stock
    distinct_skus: int
    stock_positions: int
    total_stock_value: Optional[Decimal] = None
    # Calidad / vencimientos
    near_expiry_batches: int
    expired_batches: int
    active_alerts: int
    # Operación
    pending_adjustments: int
    movements_today: int
