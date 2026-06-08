"""
WMS Panama — Schemas Outbound (Pydantic v2)
============================================
Cubre el flujo: SalesOrder → Wave → Picking → Packing → Shipment → RMA
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.outbound import (
    PickingMethod,
    PickingStatus,
    PackStatus,
    ReturnOrderStatus,
    SOLineStatus,
    SOStatus,
    ShipmentStatus,
    ShippingCarrierType,
    WaveStatus,
)


# ══════════════════════════════════════════════════════════════════════════════
# SALES ORDER
# ══════════════════════════════════════════════════════════════════════════════

class SalesOrderLineCreate(BaseModel):
    product_id: UUID
    uom_id: UUID
    description: Optional[str] = Field(None, max_length=500)
    quantity_ordered: Decimal = Field(..., gt=0, decimal_places=4)
    unit_price: Decimal = Field(Decimal("0"), ge=0, decimal_places=4)
    discount_pct: Decimal = Field(Decimal("0"), ge=0, le=1, decimal_places=4)
    tax_rate: Decimal = Field(Decimal("0"), ge=0, le=1, decimal_places=4)
    gtin: Optional[str] = Field(None, max_length=14)


class SalesOrderLineResponse(SalesOrderLineCreate):
    id: UUID
    so_id: UUID
    line_number: int
    quantity_allocated: Decimal
    quantity_picked: Decimal
    quantity_packed: Decimal
    quantity_shipped: Decimal
    quantity_backordered: Decimal
    line_total: Decimal
    status: SOLineStatus
    batch_id: Optional[UUID]
    location_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SalesOrderCreate(BaseModel):
    warehouse_id: UUID
    customer_id: UUID
    so_number: Optional[str] = Field(None, max_length=50)
    customer_po_reference: Optional[str] = Field(None, max_length=100)
    erp_reference: Optional[str] = Field(None, max_length=100)
    order_date: datetime
    requested_delivery_date: Optional[datetime] = None
    priority: int = Field(5, ge=1, le=10, description="1=urgente, 10=normal")
    picking_method: PickingMethod = PickingMethod.DISCRETE
    currency: str = Field("USD", max_length=3)
    payment_terms: Optional[str] = Field(None, max_length=100)
    # Envío
    carrier_type: ShippingCarrierType = ShippingCarrierType.THIRD_PARTY
    carrier_name: Optional[str] = Field(None, max_length=200)
    service_level: Optional[str] = Field(None, max_length=50)
    incoterms: Optional[str] = Field(None, max_length=11)
    # Dirección
    ship_to_name: Optional[str] = Field(None, max_length=200)
    ship_to_address: Optional[str] = None
    ship_to_city: Optional[str] = Field(None, max_length=100)
    ship_to_country: Optional[str] = Field(None, max_length=2)
    ship_to_phone: Optional[str] = Field(None, max_length=30)
    # Panamá
    is_export: bool = False
    ruc_cliente: Optional[str] = Field(None, max_length=20)
    # Notas
    internal_notes: Optional[str] = None
    delivery_instructions: Optional[str] = None
    lines: List[SalesOrderLineCreate] = Field(..., min_length=1)


class SalesOrderUpdate(BaseModel):
    requested_delivery_date: Optional[datetime] = None
    priority: Optional[int] = Field(None, ge=1, le=10)
    internal_notes: Optional[str] = None
    delivery_instructions: Optional[str] = None
    carrier_name: Optional[str] = Field(None, max_length=200)
    ship_to_address: Optional[str] = None


class SalesOrderResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    warehouse_id: UUID
    customer_id: UUID
    so_number: str
    customer_po_reference: Optional[str]
    erp_reference: Optional[str]
    status: SOStatus
    order_date: datetime
    requested_delivery_date: Optional[datetime]
    confirmed_date: Optional[datetime]
    shipped_date: Optional[datetime]
    delivered_date: Optional[datetime]
    priority: int
    picking_method: PickingMethod
    wave_id: Optional[UUID]
    currency: str
    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    payment_terms: Optional[str]
    ship_to_name: Optional[str]
    ship_to_address: Optional[str]
    ship_to_city: Optional[str]
    ship_to_country: Optional[str]
    carrier_type: ShippingCarrierType
    carrier_name: Optional[str]
    service_level: Optional[str]
    incoterms: Optional[str]
    is_export: bool
    ruc_cliente: Optional[str]
    dua_number: Optional[str]
    internal_notes: Optional[str]
    delivery_instructions: Optional[str]
    cancel_reason: Optional[str]
    lines: List[SalesOrderLineResponse] = []
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SOListResponse(BaseModel):
    items: List[SalesOrderResponse]
    total: int
    page: int
    page_size: int


class SOCancelRequest(BaseModel):
    reason: str = Field(..., max_length=500)


# ══════════════════════════════════════════════════════════════════════════════
# PICKING WAVE
# ══════════════════════════════════════════════════════════════════════════════

class WaveCreateRequest(BaseModel):
    warehouse_id: UUID
    so_ids: List[UUID] = Field(..., min_length=1, description="Órdenes a incluir en la wave")
    picking_method: PickingMethod = PickingMethod.DISCRETE
    priority: int = Field(5, ge=1, le=10)
    notes: Optional[str] = None


class WaveResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    warehouse_id: UUID
    wave_number: str
    status: WaveStatus
    picking_method: PickingMethod
    priority: int
    total_orders: int
    total_lines: int
    total_units: Decimal
    released_at: Optional[datetime]
    completed_at: Optional[datetime]
    estimated_minutes: Optional[int]
    actual_minutes: Optional[int]
    notes: Optional[str]
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WaveListResponse(BaseModel):
    items: List[WaveResponse]
    total: int
    page: int
    page_size: int


# ══════════════════════════════════════════════════════════════════════════════
# PICKING TASK
# ══════════════════════════════════════════════════════════════════════════════

class PickingTaskResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    wave_id: Optional[UUID]
    so_id: UUID
    so_line_id: UUID
    product_id: UUID
    uom_id: UUID
    batch_id: Optional[UUID]
    quantity_requested: Decimal
    quantity_picked: Decimal
    quantity_short: Decimal
    from_location_id: UUID
    to_location_id: Optional[UUID]
    status: PickingStatus
    priority: int
    assigned_to_id: Optional[UUID]
    sscc_scanned: Optional[str]
    gtin_scanned: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    cycle_time_seconds: Optional[int]
    short_reason: Optional[str]
    notes: Optional[str]
    product_name: Optional[str] = None
    from_location_code: Optional[str] = None
    to_location_code: Optional[str] = None
    assigned_to_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PickingTaskListResponse(BaseModel):
    items: List[PickingTaskResponse]
    total: int
    page: int
    page_size: int


class PickingCompleteRequest(BaseModel):
    """Operador RF completa una tarea de picking."""
    quantity_picked: Decimal = Field(..., ge=0, decimal_places=4)
    sscc_scanned: Optional[str] = Field(None, max_length=18)
    gtin_scanned: Optional[str] = Field(None, max_length=14)
    short_reason: Optional[str] = Field(None, max_length=500,
        description="Obligatorio si quantity_picked < quantity_requested")
    notes: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def short_reason_required_on_short(self) -> "PickingCompleteRequest":
        # La validación completa se hace en el servicio (necesita quantity_requested)
        return self


# ══════════════════════════════════════════════════════════════════════════════
# PACK TASK
# ══════════════════════════════════════════════════════════════════════════════

class PackTaskResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    so_id: UUID
    pack_task_number: str
    status: PackStatus
    box_type: Optional[str]
    box_count: int
    total_weight_kg: Optional[Decimal]
    total_volume_m3: Optional[Decimal]
    sscc: Optional[str]
    pack_station_id: Optional[UUID]
    assigned_to_id: Optional[UUID]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    cycle_time_seconds: Optional[int]
    label_printed: bool
    packing_list_printed: bool
    notes: Optional[str]
    so_number: Optional[str] = None
    assigned_to_name: Optional[str] = None
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PackTaskListResponse(BaseModel):
    items: List[PackTaskResponse]
    total: int
    page: int
    page_size: int


class PackCompleteRequest(BaseModel):
    box_type: str = Field(..., max_length=50)
    box_count: int = Field(..., ge=1)
    total_weight_kg: Optional[Decimal] = Field(None, ge=0, decimal_places=3)
    total_volume_m3: Optional[Decimal] = Field(None, ge=0, decimal_places=4)
    sscc: Optional[str] = Field(None, max_length=18)
    notes: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# SHIPMENT
# ══════════════════════════════════════════════════════════════════════════════

class ShipmentCreate(BaseModel):
    so_id: UUID
    warehouse_id: UUID
    carrier_type: ShippingCarrierType = ShippingCarrierType.THIRD_PARTY
    carrier_name: Optional[str] = Field(None, max_length=200)
    tracking_number: Optional[str] = Field(None, max_length=100)
    vehicle_plate: Optional[str] = Field(None, max_length=20)
    driver_name: Optional[str] = Field(None, max_length=200)
    driver_id_number: Optional[str] = Field(None, max_length=30)
    scheduled_pickup: Optional[datetime] = None
    estimated_delivery: Optional[datetime] = None
    dua_number: Optional[str] = Field(None, max_length=50)
    bl_number: Optional[str] = Field(None, max_length=50)
    is_export: bool = False
    notes: Optional[str] = None


class ShipmentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    so_id: UUID
    warehouse_id: UUID
    shipment_number: str
    status: ShipmentStatus
    carrier_type: Optional[ShippingCarrierType]
    carrier_name: Optional[str]
    tracking_number: Optional[str]
    vehicle_plate: Optional[str]
    driver_name: Optional[str]
    driver_id_number: Optional[str]
    scheduled_pickup: Optional[datetime]
    actual_pickup: Optional[datetime]
    estimated_delivery: Optional[datetime]
    actual_delivery: Optional[datetime]
    total_boxes: int
    total_weight_kg: Optional[Decimal]
    total_volume_m3: Optional[Decimal]
    delivery_note_number: Optional[str]
    dua_number: Optional[str]
    bl_number: Optional[str]
    is_export: bool
    delivered_to_name: Optional[str]
    erp_synced_at: Optional[datetime]
    notes: Optional[str]
    so_number: Optional[str] = None
    customer_name: Optional[str] = None
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShipmentListResponse(BaseModel):
    items: List[ShipmentResponse]
    total: int
    page: int
    page_size: int


class ShipmentDispatchRequest(BaseModel):
    actual_pickup: datetime
    tracking_number: Optional[str] = Field(None, max_length=100)
    vehicle_plate: Optional[str] = Field(None, max_length=20)
    driver_name: Optional[str] = Field(None, max_length=200)


class ShipmentDeliverRequest(BaseModel):
    actual_delivery: datetime
    delivered_to_name: str = Field(..., max_length=200)
    delivery_signature: Optional[str] = None  # base64
    delivery_photo_url: Optional[str] = Field(None, max_length=500)


# ══════════════════════════════════════════════════════════════════════════════
# RETURN ORDER (RMA)
# ══════════════════════════════════════════════════════════════════════════════

class ReturnOrderCreate(BaseModel):
    warehouse_id: UUID
    customer_id: UUID
    so_id: Optional[UUID] = None
    reason: str = Field(..., max_length=500)
    return_type: str = Field("refund", max_length=50,
                             description="refund | exchange | credit")
    notes: Optional[str] = None


class ReturnOrderResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    warehouse_id: UUID
    so_id: Optional[UUID]
    customer_id: UUID
    rma_number: str
    status: ReturnOrderStatus
    reason: str
    return_type: str
    received_at: Optional[datetime]
    received_by_id: Optional[UUID]
    inspection_notes: Optional[str]
    restocking_eligible: bool
    restocking_location_id: Optional[UUID]
    refund_amount: Decimal
    refund_issued_at: Optional[datetime]
    credit_memo_number: Optional[str]
    notes: Optional[str]
    so_number: Optional[str] = None
    customer_name: Optional[str] = None
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReturnReceiveRequest(BaseModel):
    inspection_notes: str = Field(..., max_length=2000)
    restocking_eligible: bool = False
    restocking_location_id: Optional[UUID] = None
    refund_amount: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD / KPIs OUTBOUND
# ══════════════════════════════════════════════════════════════════════════════

class OutboundDashboardMetrics(BaseModel):
    # Órdenes
    orders_open: int
    orders_pending_pick: int
    orders_pending_pack: int
    orders_pending_ship: int
    orders_overdue: int
    # Productividad
    picks_today: int
    avg_pick_cycle_time_seconds: Optional[int]
    waves_open: int
    # Envíos
    shipments_today: int
    shipments_in_transit: int
    on_time_delivery_pct: Optional[Decimal]
    # Calidad
    short_pick_rate_pct: Optional[Decimal]
    rma_open: int
    # Fill Rate
    order_fill_rate_pct: Optional[Decimal]


# ══════════════════════════════════════════════════════════════════════════════
# THROUGHPUT (series temporales para gráficas)
# ══════════════════════════════════════════════════════════════════════════════

class OutboundThroughputPoint(BaseModel):
    """Volumen diario de picking y envíos para gráficas del dashboard."""
    day: date
    picks: int
    shorts: int
    shipments: int


class OutboundThroughputResponse(BaseModel):
    series: List[OutboundThroughputPoint]
