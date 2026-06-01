"""
WMS Panama — Schemas Inbound (Pydantic v2)
==========================================
Cubre el flujo completo:
  PurchaseOrder → ASN → GoodsReceipt → QualityInspection → PutawayTask → RTV
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.inbound import (
    ASNStatus,
    GRNStatus,
    POStatus,
    PutawayStatus,
    QCStatus,
    RTVStatus,
    ReceivingMode,
)


# ══════════════════════════════════════════════════════════════════════════════
# PURCHASE ORDER
# ══════════════════════════════════════════════════════════════════════════════

class PurchaseOrderLineCreate(BaseModel):
    product_id: UUID
    uom_id: UUID
    description: Optional[str] = None
    quantity_ordered: Decimal = Field(..., gt=0, decimal_places=4)
    unit_cost: Optional[Decimal] = Field(None, ge=0, decimal_places=4)
    currency: str = Field("USD", max_length=3)
    tax_rate: Decimal = Field(Decimal("0"), ge=0, le=1, decimal_places=4)
    line_note: Optional[str] = Field(None, max_length=500)
    requested_delivery_date: Optional[date] = None
    # GS1
    gtin: Optional[str] = Field(None, max_length=14)
    country_of_origin: Optional[str] = Field(None, max_length=2)
    hs_code: Optional[str] = Field(None, max_length=10)


class PurchaseOrderLineResponse(PurchaseOrderLineCreate):
    id: UUID
    po_id: UUID
    line_number: int
    quantity_received: Decimal
    quantity_pending: Decimal
    quantity_rejected: Decimal
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PurchaseOrderCreate(BaseModel):
    warehouse_id: UUID
    supplier_id: UUID
    po_number: Optional[str] = Field(None, max_length=50, description="Si vacío, se auto-genera")
    supplier_po_reference: Optional[str] = Field(None, max_length=100)
    order_date: date
    expected_delivery_date: Optional[date] = None
    payment_terms: Optional[str] = Field(None, max_length=100)
    incoterms: Optional[str] = Field(None, max_length=11)
    currency: str = Field("USD", max_length=3)
    notes: Optional[str] = Field(None, max_length=2000)
    # Panama Aduanas
    customs_document_id: Optional[str] = Field(None, max_length=50)
    is_import: bool = False
    country_of_origin: Optional[str] = Field(None, max_length=2)
    # ERP
    erp_reference: Optional[str] = Field(None, max_length=100)
    # Líneas
    lines: List[PurchaseOrderLineCreate] = Field(..., min_length=1)

    @field_validator("lines")
    @classmethod
    def lines_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("La orden debe tener al menos una línea.")
        return v


class PurchaseOrderUpdate(BaseModel):
    expected_delivery_date: Optional[date] = None
    payment_terms: Optional[str] = Field(None, max_length=100)
    incoterms: Optional[str] = Field(None, max_length=11)
    notes: Optional[str] = Field(None, max_length=2000)
    erp_reference: Optional[str] = Field(None, max_length=100)
    customs_document_id: Optional[str] = Field(None, max_length=50)


class PurchaseOrderResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    warehouse_id: UUID
    supplier_id: UUID
    po_number: str
    supplier_po_reference: Optional[str]
    status: POStatus
    order_date: date
    expected_delivery_date: Optional[date]
    confirmed_date: Optional[datetime]
    closed_date: Optional[datetime]
    payment_terms: Optional[str]
    incoterms: Optional[str]
    currency: str
    total_amount: Decimal
    notes: Optional[str]
    customs_document_id: Optional[str]
    is_import: bool
    country_of_origin: Optional[str]
    erp_reference: Optional[str]
    erp_synced_at: Optional[datetime]
    lines: List[PurchaseOrderLineResponse] = []
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class POListResponse(BaseModel):
    items: List[PurchaseOrderResponse]
    total: int
    page: int
    page_size: int


class POQueryParams(BaseModel):
    warehouse_id: Optional[UUID] = None
    supplier_id: Optional[UUID] = None
    status: Optional[POStatus] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    search: Optional[str] = None  # po_number o supplier_po_reference


# ══════════════════════════════════════════════════════════════════════════════
# ASN — ADVANCE SHIPPING NOTICE
# ══════════════════════════════════════════════════════════════════════════════

class ASNLineCreate(BaseModel):
    po_line_id: Optional[UUID] = None
    product_id: UUID
    uom_id: UUID
    quantity_expected: Decimal = Field(..., gt=0, decimal_places=4)
    batch_number: Optional[str] = Field(None, max_length=50)
    expiry_date: Optional[date] = None
    manufacture_date: Optional[date] = None
    # GS1
    sscc: Optional[str] = Field(None, max_length=18, description="Serial Shipping Container Code")
    gtin: Optional[str] = Field(None, max_length=14)
    country_of_origin: Optional[str] = Field(None, max_length=2)


class ASNLineResponse(ASNLineCreate):
    id: UUID
    asn_id: UUID
    line_number: int
    quantity_received: Decimal
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ASNCreate(BaseModel):
    po_id: Optional[UUID] = None
    warehouse_id: UUID
    supplier_id: UUID
    asn_number: Optional[str] = Field(None, max_length=50)
    supplier_asn_reference: Optional[str] = Field(None, max_length=100)
    expected_arrival_date: Optional[datetime] = None
    # Transporte
    carrier_name: Optional[str] = Field(None, max_length=200)
    tracking_number: Optional[str] = Field(None, max_length=100)
    vehicle_plate: Optional[str] = Field(None, max_length=20)
    container_number: Optional[str] = Field(None, max_length=20)
    seal_number: Optional[str] = Field(None, max_length=50)
    # Aduanas Panamá
    customs_document_id: Optional[str] = Field(None, max_length=50)
    customs_reference: Optional[str] = Field(None, max_length=100)
    is_customs_cleared: bool = False
    notes: Optional[str] = Field(None, max_length=2000)
    lines: List[ASNLineCreate] = Field(..., min_length=1)


class ASNResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    po_id: Optional[UUID]
    warehouse_id: UUID
    supplier_id: UUID
    asn_number: str
    supplier_asn_reference: Optional[str]
    status: ASNStatus
    expected_arrival_date: Optional[datetime]
    actual_arrival_date: Optional[datetime]
    carrier_name: Optional[str]
    tracking_number: Optional[str]
    vehicle_plate: Optional[str]
    container_number: Optional[str]
    seal_number: Optional[str]
    dock_number: Optional[str]
    customs_document_id: Optional[str]
    customs_reference: Optional[str]
    is_customs_cleared: bool
    notes: Optional[str]
    lines: List[ASNLineResponse] = []
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ASNListResponse(BaseModel):
    items: List[ASNResponse]
    total: int
    page: int
    page_size: int


class ASNScheduleDockRequest(BaseModel):
    dock_number: str = Field(..., max_length=20)
    expected_arrival_date: datetime


# ══════════════════════════════════════════════════════════════════════════════
# GRN — GOODS RECEIPT NOTE
# ══════════════════════════════════════════════════════════════════════════════

class GRNLineCreate(BaseModel):
    asn_line_id: Optional[UUID] = None
    po_line_id: Optional[UUID] = None
    product_id: UUID
    uom_id: UUID
    location_id: UUID   # Ubicación temporal de recepción (staging area)
    quantity_received: Decimal = Field(..., gt=0, decimal_places=4)
    quantity_rejected: Decimal = Field(Decimal("0"), ge=0, decimal_places=4)
    batch_number: Optional[str] = Field(None, max_length=50)
    expiry_date: Optional[date] = None
    manufacture_date: Optional[date] = None
    unit_cost: Optional[Decimal] = Field(None, ge=0, decimal_places=4)
    currency: str = Field("USD", max_length=3)
    # GS1
    sscc: Optional[str] = Field(None, max_length=18)
    gtin_scanned: Optional[str] = Field(None, max_length=14)
    # Cadena de frío
    item_temp_celsius: Optional[Decimal] = Field(None, decimal_places=2)
    notes: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def rejected_le_received(self) -> "GRNLineCreate":
        if self.quantity_rejected > self.quantity_received:
            raise ValueError("quantity_rejected no puede superar quantity_received.")
        return self


class GRNLineResponse(GRNLineCreate):
    id: UUID
    grn_id: UUID
    line_number: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class GRNCreate(BaseModel):
    warehouse_id: UUID
    asn_id: Optional[UUID] = None
    po_id: Optional[UUID] = None
    receiving_mode: ReceivingMode = ReceivingMode.STANDARD
    dock_number: Optional[str] = Field(None, max_length=20)
    # Cadena de frío a nivel de recibo
    ambient_temp_celsius: Optional[Decimal] = Field(None, decimal_places=2)
    product_temp_celsius: Optional[Decimal] = Field(None, decimal_places=2)
    notes: Optional[str] = Field(None, max_length=2000)
    lines: List[GRNLineCreate] = Field(..., min_length=1)


class GRNResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    warehouse_id: UUID
    asn_id: Optional[UUID]
    po_id: Optional[UUID]
    grn_number: str
    status: GRNStatus
    receiving_mode: ReceivingMode
    dock_number: Optional[str]
    received_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    ambient_temp_celsius: Optional[Decimal]
    product_temp_celsius: Optional[Decimal]
    requires_qc: bool
    notes: Optional[str]
    erp_synced_at: Optional[datetime]
    lines: List[GRNLineResponse] = []
    received_by_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GRNListResponse(BaseModel):
    items: List[GRNResponse]
    total: int
    page: int
    page_size: int


class GRNQueryParams(BaseModel):
    warehouse_id: Optional[UUID] = None
    status: Optional[GRNStatus] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    requires_qc: Optional[bool] = None


# ══════════════════════════════════════════════════════════════════════════════
# QUALITY INSPECTION
# ══════════════════════════════════════════════════════════════════════════════

class QCLineCreate(BaseModel):
    grn_line_id: UUID
    product_id: UUID
    quantity_inspected: Decimal = Field(..., gt=0, decimal_places=4)
    quantity_approved: Decimal = Field(..., ge=0, decimal_places=4)
    quantity_rejected: Decimal = Field(..., ge=0, decimal_places=4)
    defect_codes: Optional[List[str]] = Field(default_factory=list)
    defect_description: Optional[str] = Field(None, max_length=1000)
    notes: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def totals_match(self) -> "QCLineCreate":
        if self.quantity_approved + self.quantity_rejected != self.quantity_inspected:
            raise ValueError(
                "quantity_approved + quantity_rejected debe ser igual a quantity_inspected."
            )
        return self


class QCLineResponse(QCLineCreate):
    id: UUID
    qi_id: UUID
    line_number: int
    created_at: datetime

    model_config = {"from_attributes": True}


class QualityInspectionCreate(BaseModel):
    grn_id: UUID
    # AQL Sampling
    aql_level: Optional[str] = Field(None, max_length=10, description="Ej: II, S-2")
    sample_size: Optional[int] = Field(None, ge=1)
    acceptance_number: Optional[int] = Field(None, ge=0)
    rejection_number: Optional[int] = Field(None, ge=0)
    inspection_type: Optional[str] = Field(None, max_length=50, description="visual, dimensional, funcional")
    notes: Optional[str] = Field(None, max_length=2000)
    lines: List[QCLineCreate] = Field(..., min_length=1)


class QualityInspectionApprove(BaseModel):
    """Aprobar o rechazar una inspección."""
    approved: bool
    disposition: str = Field(..., max_length=50, description="accept | reject | conditional_accept | rework")
    disposition_notes: Optional[str] = Field(None, max_length=2000)
    rework_location_id: Optional[UUID] = None    # Para disposición "rework"
    return_to_vendor: bool = False               # Si True, crear RTV automáticamente


class QualityInspectionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    grn_id: UUID
    qi_number: str
    status: QCStatus
    aql_level: Optional[str]
    sample_size: Optional[int]
    acceptance_number: Optional[int]
    rejection_number: Optional[int]
    inspection_type: Optional[str]
    total_inspected: Optional[Decimal]
    total_approved: Optional[Decimal]
    total_rejected: Optional[Decimal]
    defect_rate: Optional[Decimal]
    disposition: Optional[str]
    disposition_notes: Optional[str]
    inspection_date: Optional[datetime]
    completed_at: Optional[datetime]
    photo_urls: Optional[List[str]] = []
    notes: Optional[str]
    lines: List[QCLineResponse] = []
    inspector_id: Optional[UUID]
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════════════════
# PUTAWAY TASK
# ══════════════════════════════════════════════════════════════════════════════

class PutawayTaskResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    grn_id: Optional[UUID]
    grn_line_id: Optional[UUID]
    product_id: UUID
    batch_id: Optional[UUID]
    quantity: Decimal
    uom_id: UUID
    from_location_id: Optional[UUID]
    suggested_location_id: Optional[UUID]
    actual_location_id: Optional[UUID]
    status: PutawayStatus
    priority: int
    putaway_rule_id: Optional[UUID]
    assigned_to_id: Optional[UUID]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    cycle_time_seconds: Optional[int]
    override_reason: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PutawayCompleteRequest(BaseModel):
    actual_location_id: UUID
    override_reason: Optional[str] = Field(None, max_length=500,
        description="Obligatorio si la ubicación real difiere de la sugerida")


class PutawayListResponse(BaseModel):
    items: List[PutawayTaskResponse]
    total: int
    page: int
    page_size: int


# ══════════════════════════════════════════════════════════════════════════════
# RETURN TO VENDOR (RTV)
# ══════════════════════════════════════════════════════════════════════════════

class RTVCreate(BaseModel):
    grn_id: Optional[UUID] = None
    supplier_id: UUID
    warehouse_id: UUID
    reason: str = Field(..., max_length=500)
    notes: Optional[str] = Field(None, max_length=2000)
    # Logística de devolución
    return_carrier: Optional[str] = Field(None, max_length=200)
    return_tracking: Optional[str] = Field(None, max_length=100)
    # Financiero
    credit_expected: Decimal = Field(Decimal("0"), ge=0, decimal_places=2)
    currency: str = Field("USD", max_length=3)


class RTVResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    grn_id: Optional[UUID]
    supplier_id: UUID
    warehouse_id: UUID
    rtv_number: str
    status: RTVStatus
    reason: str
    notes: Optional[str]
    return_carrier: Optional[str]
    return_tracking: Optional[str]
    shipped_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    credit_expected: Decimal
    credit_received: Decimal
    currency: str
    credit_memo_number: Optional[str]
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD / MÉTRICAS INBOUND
# ══════════════════════════════════════════════════════════════════════════════

class InboundDashboardMetrics(BaseModel):
    """KPIs del módulo de recepción para el período seleccionado."""
    # Órdenes
    pos_open: int
    pos_pending_receipt: int
    pos_overdue: int
    # Recepciones
    grns_today: int
    grns_pending_qc: int
    grns_pending_putaway: int
    # Calidad
    avg_defect_rate_pct: Decimal
    rtv_pending: int
    # Productividad (LMS)
    avg_putaway_cycle_time_seconds: Optional[int]
    putaway_tasks_open: int
    # Precisión
    receipt_accuracy_pct: Optional[Decimal]


class InboundThroughputPoint(BaseModel):
    """Volumen diario de recepciones y putaway para gráficas del dashboard."""
    day: date
    grns: int
    putaway_completed: int


class InboundThroughputResponse(BaseModel):
    series: List[InboundThroughputPoint]
