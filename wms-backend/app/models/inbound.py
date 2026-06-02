"""
WMS Panama — Inbound Models
=============================
Modelos del proceso de entrada de mercancia:
- PurchaseOrder (Orden de Compra)
- PurchaseOrderLine (Linea de OC)
- ASN / AdvanceShippingNotice (Aviso de Despacho)
- ASNLine
- GoodsReceipt / GRN (Nota de Recepcion)
- GoodsReceiptLine
- QualityInspection (Inspeccion de Calidad)
- QualityInspectionLine
- TemperatureLog (Registro de cadena de frio)
- PutawayTask (Tarea de ubicacion post-recepcion)
- ReturnToVendor / RTV (Devolucion a proveedor)
"""

from __future__ import annotations

import uuid
from datetime import datetime, date
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional, List

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, ForeignKey, Index,
    Integer, Numeric, String, Text, UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import WMSTenantBase


# ─── ENUMS ────────────────────────────────────────────────────────────────────

class POStatus(str, PyEnum):
    DRAFT      = "draft"
    CONFIRMED  = "confirmed"
    SENT       = "sent"          # Enviada al proveedor
    PARTIAL    = "partial"       # Recibida parcialmente
    RECEIVED   = "received"      # Recibida completamente
    CLOSED     = "closed"        # Cerrada (puede quedar pendiente)
    CANCELLED  = "cancelled"


class ASNStatus(str, PyEnum):
    EXPECTED   = "expected"      # ASN recibido, mercancia en camino
    ARRIVED    = "arrived"       # Camion llego al patio
    RECEIVING  = "receiving"     # En proceso de descarga/recepcion
    RECEIVED   = "received"      # Recepcion completada
    DISCREPANCY = "discrepancy"  # Con discrepancias pendientes
    CLOSED     = "closed"


class GRNStatus(str, PyEnum):
    DRAFT      = "draft"
    PENDING_QC = "pending_qc"    # Esperando inspeccion de calidad
    QC_PASSED  = "qc_passed"     # Calidad aprobada
    QC_FAILED  = "qc_failed"     # Calidad rechazada (va a cuarentena/RTV)
    PUTAWAY    = "putaway"       # En proceso de putaway
    COMPLETED  = "completed"     # GRN completo, inventario actualizado
    CANCELLED  = "cancelled"


class QCStatus(str, PyEnum):
    PENDING    = "pending"
    IN_PROGRESS = "in_progress"
    PASSED     = "passed"
    FAILED     = "failed"
    PARTIAL    = "partial"       # Parte aprobada, parte rechazada
    CONDITIONALLY_RELEASED = "conditionally_released"


class PutawayStatus(str, PyEnum):
    PENDING    = "pending"
    ASSIGNED   = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED  = "completed"
    CANCELLED  = "cancelled"


class RTVStatus(str, PyEnum):
    DRAFT      = "draft"
    APPROVED   = "approved"
    PICKING    = "picking"
    READY      = "ready"         # Listo para recoger por proveedor
    SHIPPED    = "shipped"
    CONFIRMED  = "confirmed"     # Proveedor confirmo recepcion
    CLOSED     = "closed"


class ReceivingMode(str, PyEnum):
    STANDARD   = "standard"      # Recepcion normal por item
    CONTAINER  = "container"     # Descarga de contenedor completo
    CROSS_DOCK = "cross_dock"    # Cross-docking (sin putaway)
    BLIND      = "blind"         # Recepcion ciega (sin PO previa)


# ─── PURCHASE ORDER ───────────────────────────────────────────────────────────

class PurchaseOrder(WMSTenantBase):
    """
    PurchaseOrder (PO) = Orden de Compra.
    Puede ser generada internamente o recibida del ERP.
    Una PO puede recibirse en multiples GRNs (entregas parciales).
    """
    __tablename__ = "purchase_orders"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )

    # Numeros de documento
    po_number: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Numero de OC (generado por WMS o heredado del ERP)"
    )
    erp_reference: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True,
        comment="Numero de OC en el ERP (SAP, Oracle, Dynamics)"
    )
    supplier_po_reference: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Referencia de OC del proveedor"
    )

    status: Mapped[POStatus] = mapped_column(
        Enum(POStatus), nullable=False, default=POStatus.DRAFT
    )

    # Fechas
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_delivery_date: Mapped[Optional[date]] = mapped_column(
        Date, comment="Fecha esperada de entrega"
    )
    confirmed_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="Fecha confirmada por el proveedor"
    )
    closed_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="Fecha de cierre/cancelacion"
    )

    # Valores
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    subtotal: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))

    # Condiciones
    payment_terms: Mapped[Optional[str]] = mapped_column(String(100))
    incoterms: Mapped[Optional[str]] = mapped_column(
        String(10), comment="Incoterms: FOB, CIF, DDP, EXW, etc."
    )
    delivery_address: Mapped[Optional[str]] = mapped_column(Text)

    # Aduanas Panama (para importaciones)
    is_import: Mapped[bool] = mapped_column(Boolean, default=False)
    country_of_origin: Mapped[Optional[str]] = mapped_column(String(2))
    customs_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        comment="Referencia a DAM / documento aduanero vinculado"
    )

    # Sincronizacion ERP
    erp_synced: Mapped[bool] = mapped_column(Boolean, default=False)
    erp_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    notes: Mapped[Optional[str]] = mapped_column(Text)
    custom_attributes: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # Relaciones
    lines: Mapped[List["PurchaseOrderLine"]] = relationship(
        back_populates="purchase_order", order_by="PurchaseOrderLine.line_number"
    )
    asns: Mapped[List["ASN"]] = relationship(back_populates="purchase_order")
    status_history: Mapped[List["POStatusHistory"]] = relationship(
        back_populates="purchase_order",
        order_by="POStatusHistory.created_at",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("warehouse_id", "po_number",
                         name="uq_po_warehouse_number"),
        Index("ix_po_tenant_warehouse", "tenant_id", "warehouse_id"),
        Index("ix_po_supplier_status", "supplier_id", "status"),
        Index("ix_po_erp_number", "erp_reference"),
        Index("ix_po_expected_date", "expected_delivery_date", "status"),
    )

    def __repr__(self) -> str:
        return f"<PurchaseOrder {self.po_number} [{self.status}]>"


class PurchaseOrderLine(WMSTenantBase):
    """Linea de Orden de Compra — un SKU con su cantidad y precio."""
    __tablename__ = "purchase_order_lines"

    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False
    )

    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    erp_line_number: Mapped[Optional[str]] = mapped_column(String(20))

    # Cantidades
    quantity_ordered: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False
    )
    quantity_received: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=0,
        comment="Cantidad ya recibida en GRNs"
    )
    quantity_pending: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=0,
        comment="Cantidad aun pendiente de recibir"
    )
    quantity_rejected: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=0,
        comment="Cantidad rechazada en control de calidad"
    )
    uom: Mapped[str] = mapped_column(String(20), default="UN")

    # Precios
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    discount_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), default=0)
    tax_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), default=7.0)
    line_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))

    # Atributos de recepcion esperada
    expected_batch: Mapped[Optional[str]] = mapped_column(String(100))
    expected_expiry_date: Mapped[Optional[date]] = mapped_column(Date)

    status: Mapped[str] = mapped_column(
        String(20), default="open",
        comment="open | partial | received | closed | cancelled"
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="lines")

    __table_args__ = (
        UniqueConstraint("purchase_order_id", "line_number",
                         name="uq_po_lines_order_line"),
        Index("ix_po_lines_order", "purchase_order_id"),
        Index("ix_po_lines_product", "product_id"),
    )


class POStatusHistory(WMSTenantBase):
    """
    Historial de cambios de estado de una Orden de Compra.
    Registra cada transicion (quien, cuando, de->a, motivo) para auditoria.
    """
    __tablename__ = "po_status_history"

    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    from_status: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="Estado anterior (NULL al crear la OC)"
    )
    to_status: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="Estado al que transiciona la OC"
    )
    changed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        comment="Usuario que ejecuto la transicion"
    )
    reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Motivo o comentario de la transicion"
    )

    purchase_order: Mapped["PurchaseOrder"] = relationship(
        back_populates="status_history"
    )

    __table_args__ = (
        Index("ix_po_status_hist_order", "purchase_order_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<POStatusHistory {self.purchase_order_id} {self.from_status}->{self.to_status}>"


# ─── ASN ──────────────────────────────────────────────────────────────────────

class ASN(WMSTenantBase):
    """
    ASN = Advance Shipping Notice (Aviso de Despacho del Proveedor).
    El proveedor notifica que el envio esta en camino con detalle de contenido.
    Puede venir via EDI, portal web o integracion directa con ERP del proveedor.
    """
    __tablename__ = "asns"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False
    )
    purchase_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=True,
        comment="NULL si el ASN no tiene PO asociada (recepcion ciega)"
    )

    asn_number: Mapped[str] = mapped_column(String(50), nullable=False)
    supplier_reference: Mapped[Optional[str]] = mapped_column(
        String(100), comment="Numero de referencia del proveedor"
    )
    status: Mapped[ASNStatus] = mapped_column(
        Enum(ASNStatus), default=ASNStatus.EXPECTED
    )

    # Logistica del envio
    carrier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carriers.id", ondelete="SET NULL"),
        nullable=True
    )
    tracking_number: Mapped[Optional[str]] = mapped_column(String(100))
    plate_number: Mapped[Optional[str]] = mapped_column(
        String(20), comment="Placa del camion para YMS"
    )
    container_number: Mapped[Optional[str]] = mapped_column(
        String(20), comment="Numero de contenedor maritimo"
    )
    seal_number: Mapped[Optional[str]] = mapped_column(String(30))

    # Fechas
    ship_date: Mapped[Optional[date]] = mapped_column(Date)
    expected_arrival: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), index=True,
        comment="Fecha/hora esperada de llegada al patio"
    )
    actual_arrival: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dock_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        comment="Dock asignado por YMS"
    )

    # Totales esperados
    total_pallets: Mapped[Optional[int]] = mapped_column(Integer)
    total_boxes: Mapped[Optional[int]] = mapped_column(Integer)
    total_weight_kg: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    total_volume_m3: Mapped[Optional[float]] = mapped_column(Numeric(8, 3))

    # Aduanas
    customs_reference: Mapped[Optional[str]] = mapped_column(
        String(50), comment="Numero de DAM o documento aduanero vinculado"
    )
    is_customs_cleared: Mapped[bool] = mapped_column(Boolean, default=False)

    receiving_mode: Mapped[ReceivingMode] = mapped_column(
        Enum(ReceivingMode), default=ReceivingMode.STANDARD
    )

    notes: Mapped[Optional[str]] = mapped_column(Text)
    custom_attributes: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # Relaciones
    purchase_order: Mapped[Optional["PurchaseOrder"]] = relationship(
        back_populates="asns"
    )
    lines: Mapped[List["ASNLine"]] = relationship(
        back_populates="asn", order_by="ASNLine.line_number"
    )
    goods_receipts: Mapped[List["GoodsReceipt"]] = relationship(back_populates="asn")

    __table_args__ = (
        UniqueConstraint("warehouse_id", "asn_number",
                         name="uq_asn_warehouse_number"),
        Index("ix_asn_warehouse_status", "warehouse_id", "status"),
        Index("ix_asn_expected_arrival", "expected_arrival", "status"),
        Index("ix_asn_supplier", "supplier_id"),
    )

    def __repr__(self) -> str:
        return f"<ASN {self.asn_number} [{self.status}]>"


class ASNLine(WMSTenantBase):
    """Linea de ASN — producto esperado con su cantidad y empaque."""
    __tablename__ = "asn_lines"

    asn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asns.id", ondelete="CASCADE"),
        nullable=False
    )
    po_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"),
        nullable=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False
    )

    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_expected: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=0)
    uom: Mapped[str] = mapped_column(String(20), default="UN")

    # Datos del lote esperado
    batch_number: Mapped[Optional[str]] = mapped_column(String(100))
    expiry_date: Mapped[Optional[date]] = mapped_column(Date)
    manufacture_date: Mapped[Optional[date]] = mapped_column(Date)

    # GS1
    sscc: Mapped[Optional[str]] = mapped_column(
        String(18), comment="SSCC del palet esperado"
    )

    status: Mapped[str] = mapped_column(String(20), default="pending")

    asn: Mapped["ASN"] = relationship(back_populates="lines")

    __table_args__ = (
        UniqueConstraint("asn_id", "line_number", name="uq_asn_lines_number"),
        Index("ix_asn_lines_asn", "asn_id"),
        Index("ix_asn_lines_product", "product_id"),
    )


# ─── GOODS RECEIPT (GRN) ─────────────────────────────────────────────────────

class GoodsReceipt(WMSTenantBase):
    """
    GoodsReceipt (GRN) = Nota de Recepcion de Mercancias.
    Registra la mercancia efectivamente recibida en la bodega.
    Un GRN puede ser parcial respecto a un ASN o PO.
    Al completarse, actualiza el InventoryLevel y genera InventoryMovements.
    """
    __tablename__ = "goods_receipts"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    asn_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asns.id", ondelete="RESTRICT"),
        nullable=True
    )
    purchase_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False
    )

    grn_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[GRNStatus] = mapped_column(
        Enum(GRNStatus), default=GRNStatus.DRAFT
    )
    receiving_mode: Mapped[ReceivingMode] = mapped_column(
        Enum(ReceivingMode), default=ReceivingMode.STANDARD
    )

    # Operario receptor
    received_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # Fechas
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Dock y vehiculo
    dock_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    plate_number: Mapped[Optional[str]] = mapped_column(String(20))
    seal_number: Mapped[Optional[str]] = mapped_column(String(30))
    container_number: Mapped[Optional[str]] = mapped_column(String(20))

    # Totales reales recibidos
    total_lines: Mapped[int] = mapped_column(Integer, default=0)
    total_units_expected: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    total_units_received: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=0
    )
    total_units_rejected: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=0
    )

    # Discrepancias
    has_discrepancies: Mapped[bool] = mapped_column(Boolean, default=False)
    discrepancy_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Temperatura al recibir (cadena de frio)
    ambient_temp_celsius: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    product_temp_celsius: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    temp_within_range: Mapped[Optional[bool]] = mapped_column(Boolean)

    notes: Mapped[Optional[str]] = mapped_column(Text)
    custom_attributes: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # Firma digital del receptor (para auditoria)
    signature_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Sincronizacion ERP
    erp_synced: Mapped[bool] = mapped_column(Boolean, default=False)
    erp_document_id: Mapped[Optional[str]] = mapped_column(String(100))

    # Relaciones
    asn: Mapped[Optional["ASN"]] = relationship(back_populates="goods_receipts")
    lines: Mapped[List["GoodsReceiptLine"]] = relationship(
        back_populates="goods_receipt", order_by="GoodsReceiptLine.line_number"
    )
    quality_inspections: Mapped[List["QualityInspection"]] = relationship(
        back_populates="goods_receipt"
    )
    putaway_tasks: Mapped[List["PutawayTask"]] = relationship(
        back_populates="goods_receipt"
    )

    __table_args__ = (
        UniqueConstraint("warehouse_id", "grn_number",
                         name="uq_grn_warehouse_number"),
        Index("ix_grn_warehouse_status", "warehouse_id", "status"),
        Index("ix_grn_tenant_date", "tenant_id", "received_date"),
        Index("ix_grn_supplier", "supplier_id"),
    )

    def __repr__(self) -> str:
        return f"<GoodsReceipt {self.grn_number} [{self.status}]>"


class GoodsReceiptLine(WMSTenantBase):
    """Linea de GRN — item recibido con cantidades reales."""
    __tablename__ = "goods_receipt_lines"

    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("goods_receipts.id", ondelete="CASCADE"),
        nullable=False
    )
    asn_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asn_lines.id", ondelete="RESTRICT"),
        nullable=True
    )
    po_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"),
        nullable=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True
    )

    line_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Cantidades
    quantity_expected: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    quantity_accepted: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=0,
        comment="Cantidad aprobada por QC"
    )
    quantity_rejected: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=0)
    uom: Mapped[str] = mapped_column(String(20), default="UN")

    # GS1
    sscc: Mapped[Optional[str]] = mapped_column(
        String(18), comment="SSCC del palet recibido"
    )
    gtin_scanned: Mapped[Optional[str]] = mapped_column(
        String(14), comment="GTIN escaneado durante la recepcion"
    )

    # Temperatura especifica del item
    item_temp_celsius: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    temp_ok: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Ubicacion donde se coloco temporalmente
    receiving_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL")
    )

    status: Mapped[str] = mapped_column(
        String(20), default="received",
        comment="received | pending_qc | accepted | rejected | quarantine"
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(200))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    goods_receipt: Mapped["GoodsReceipt"] = relationship(back_populates="lines")

    __table_args__ = (
        UniqueConstraint("goods_receipt_id", "line_number",
                         name="uq_grn_lines_number"),
        Index("ix_grn_lines_grn", "goods_receipt_id"),
        Index("ix_grn_lines_product", "product_id"),
        Index("ix_grn_lines_batch", "batch_id"),
    )


# ─── QUALITY INSPECTION ───────────────────────────────────────────────────────

class QualityInspection(WMSTenantBase):
    """
    Inspeccion de calidad post-recepcion.
    Puede ser: inspeccion 100%, muestreo AQL, inspeccion aleatoria.
    """
    __tablename__ = "quality_inspections"

    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("goods_receipts.id", ondelete="RESTRICT"),
        nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False
    )

    inspection_number: Mapped[str] = mapped_column(String(50), nullable=False)
    inspection_type: Mapped[str] = mapped_column(
        String(30), default="sampling",
        comment="full_100 | sampling_aql | random | visual_only"
    )
    status: Mapped[QCStatus] = mapped_column(
        Enum(QCStatus), default=QCStatus.PENDING
    )

    # Parametros de muestreo
    sample_size: Mapped[Optional[int]] = mapped_column(Integer)
    aql_level: Mapped[Optional[str]] = mapped_column(
        String(10), comment="Nivel AQL: 0.065, 0.1, 0.25, 0.65, 1.0, 1.5, 2.5, 4.0"
    )
    acceptance_number: Mapped[Optional[int]] = mapped_column(Integer)
    rejection_number: Mapped[Optional[int]] = mapped_column(Integer)

    # Inspector
    inspector_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Resultado
    defects_found: Mapped[int] = mapped_column(Integer, default=0)
    defect_rate_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    overall_result: Mapped[Optional[str]] = mapped_column(
        String(20), comment="pass | fail | conditional"
    )
    disposition: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="use_as_is | rework | return_to_vendor | scrap | quarantine"
    )

    # Evidencia
    photos: Mapped[Optional[list]] = mapped_column(
        JSONB, comment="Lista de URLs de fotos tomadas durante la inspeccion"
    )
    report_url: Mapped[Optional[str]] = mapped_column(String(500))

    notes: Mapped[Optional[str]] = mapped_column(Text)

    goods_receipt: Mapped["GoodsReceipt"] = relationship(
        back_populates="quality_inspections"
    )
    lines: Mapped[List["QualityInspectionLine"]] = relationship(
        back_populates="inspection"
    )

    __table_args__ = (
        UniqueConstraint("warehouse_id", "inspection_number",
                         name="uq_qc_warehouse_number"),
        Index("ix_qc_grn", "goods_receipt_id"),
        Index("ix_qc_warehouse_status", "warehouse_id", "status"),
    )


class QualityInspectionLine(WMSTenantBase):
    """Resultado de inspeccion por producto/defecto."""
    __tablename__ = "quality_inspection_lines"

    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quality_inspections.id", ondelete="CASCADE"),
        nullable=False
    )
    grn_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("goods_receipt_lines.id", ondelete="RESTRICT"),
        nullable=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False
    )

    defect_code: Mapped[Optional[str]] = mapped_column(String(30))
    defect_description: Mapped[Optional[str]] = mapped_column(Text)
    defect_category: Mapped[Optional[str]] = mapped_column(
        String(30), comment="critical | major | minor | cosmetic"
    )
    quantity_inspected: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    quantity_defective: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=0)
    result: Mapped[str] = mapped_column(String(10), default="pass")

    inspection: Mapped["QualityInspection"] = relationship(back_populates="lines")

    __table_args__ = (
        Index("ix_qc_lines_inspection", "inspection_id"),
    )


# ─── PUTAWAY TASK ─────────────────────────────────────────────────────────────

class PutawayTask(WMSTenantBase):
    """
    Tarea de Putaway = ubicar mercancia recibida en su lugar en la bodega.
    Generada automaticamente al completar la recepcion (GRN aprobado).
    El sistema propone la ubicacion optima segun reglas de slotting.
    """
    __tablename__ = "putaway_tasks"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("goods_receipts.id", ondelete="RESTRICT"),
        nullable=False
    )
    grn_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("goods_receipt_lines.id", ondelete="RESTRICT"),
        nullable=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True
    )

    # Asignacion
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL")
    )

    status: Mapped[PutawayStatus] = mapped_column(
        Enum(PutawayStatus), default=PutawayStatus.PENDING
    )

    # Ubicaciones
    from_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Ubicacion de origen (zona de recepcion)"
    )
    suggested_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=True,
        comment="Ubicacion sugerida por el motor de slotting"
    )
    actual_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=True,
        comment="Ubicacion donde realmente se coloco la mercancia"
    )
    override_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="Razon por la que el operario no uso la ubicacion sugerida"
    )

    # Cantidades
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    quantity_putaway: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=0)
    uom: Mapped[str] = mapped_column(String(20), default="UN")

    # Tiempos (para LMS)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cycle_time_seconds: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Tiempo de ciclo en segundos para calculo de LMS"
    )

    priority: Mapped[int] = mapped_column(Integer, default=5)
    sscc: Mapped[Optional[str]] = mapped_column(String(18))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    goods_receipt: Mapped["GoodsReceipt"] = relationship(back_populates="putaway_tasks")

    __table_args__ = (
        Index("ix_putaway_warehouse_status", "warehouse_id", "status"),
        Index("ix_putaway_assigned", "assigned_to", "status"),
        Index("ix_putaway_grn", "goods_receipt_id"),
    )


# ─── RETURN TO VENDOR ─────────────────────────────────────────────────────────

class ReturnToVendor(WMSTenantBase):
    """
    RTV = Return To Vendor (Devolucion a Proveedor).
    Se genera cuando hay rechazo de calidad o mercancia defectuosa.
    Genera movimientos de inventario y documentacion de despacho.
    """
    __tablename__ = "return_to_vendors"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False
    )
    goods_receipt_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("goods_receipts.id", ondelete="RESTRICT"),
        nullable=True
    )

    rtv_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[RTVStatus] = mapped_column(
        Enum(RTVStatus), default=RTVStatus.DRAFT
    )
    reason: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="quality_defect | wrong_product | damaged | overage | expired | other"
    )
    reason_detail: Mapped[Optional[str]] = mapped_column(Text)

    carrier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carriers.id", ondelete="SET NULL")
    )
    tracking_number: Mapped[Optional[str]] = mapped_column(String(100))
    shipped_date: Mapped[Optional[date]] = mapped_column(Date)

    total_units: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    total_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    credit_memo_number: Mapped[Optional[str]] = mapped_column(
        String(50), comment="Numero de nota de credito del proveedor"
    )

    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("warehouse_id", "rtv_number",
                         name="uq_rtv_warehouse_number"),
        Index("ix_rtv_warehouse_status", "warehouse_id", "status"),
        Index("ix_rtv_supplier", "supplier_id"),
    )
