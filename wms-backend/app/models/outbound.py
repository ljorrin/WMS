"""
WMS Panama — Modelos Outbound
================================
Cubre el flujo completo de salida:
  SalesOrder → PickingWave → PickingTask → PackTask → Shipment → DeliveryNote

Entidades:
  SalesOrder / SalesOrderLine
  PickingWave            — agrupa tareas de picking (wave picking)
  PickingTask            — tarea individual de picking por operador RF
  PackStation / PackTask — estación de empaque y tarea de empaque
  Shipment               — envío consolidado
  DeliveryNote           — albarán de entrega (DUA para exportación Panamá)
  ReturnOrder            — devolución de cliente (RMA)
"""

from __future__ import annotations

import enum
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.db.session import WMSBase


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class SOStatus(str, enum.Enum):
    DRAFT           = "draft"
    CONFIRMED       = "confirmed"
    ALLOCATED       = "allocated"       # stock reservado
    PICKING         = "picking"         # en proceso de picking
    PACKED          = "packed"          # empacado, pendiente despacho
    SHIPPED         = "shipped"         # en tránsito
    DELIVERED       = "delivered"       # entregado al cliente
    CANCELLED       = "cancelled"
    PARTIALLY_SHIPPED = "partially_shipped"


class SOLineStatus(str, enum.Enum):
    PENDING         = "pending"
    ALLOCATED       = "allocated"
    PICKED          = "picked"
    PACKED          = "packed"
    SHIPPED         = "shipped"
    CANCELLED       = "cancelled"
    BACKORDERED     = "backordered"


class WaveStatus(str, enum.Enum):
    OPEN            = "open"
    RELEASED        = "released"       # liberada a operadores
    IN_PROGRESS     = "in_progress"
    COMPLETED       = "completed"
    CANCELLED       = "cancelled"


class PickingStatus(str, enum.Enum):
    PENDING         = "pending"
    IN_PROGRESS     = "in_progress"
    COMPLETED       = "completed"
    SHORT_PICKED    = "short_picked"   # menos de lo solicitado
    CANCELLED       = "cancelled"


class PackStatus(str, enum.Enum):
    PENDING         = "pending"
    IN_PROGRESS     = "in_progress"
    COMPLETED       = "completed"
    CANCELLED       = "cancelled"


class ShipmentStatus(str, enum.Enum):
    PENDING         = "pending"
    READY           = "ready"          # documentos listos
    IN_TRANSIT      = "in_transit"
    DELIVERED       = "delivered"
    FAILED          = "failed"
    RETURNED        = "returned"


class ReturnOrderStatus(str, enum.Enum):
    REQUESTED       = "requested"
    APPROVED        = "approved"
    IN_TRANSIT      = "in_transit"
    RECEIVED        = "received"
    INSPECTED       = "inspected"
    CLOSED          = "closed"
    REJECTED        = "rejected"


class PickingMethod(str, enum.Enum):
    DISCRETE        = "discrete"       # 1 orden 1 operador
    BATCH           = "batch"          # N órdenes 1 operador
    ZONE            = "zone"           # por zonas del almacén
    CLUSTER         = "cluster"        # carros de picking múltiples


class ShippingCarrierType(str, enum.Enum):
    OWN_FLEET       = "own_fleet"
    THIRD_PARTY     = "third_party"
    CUSTOMER_PICKUP = "customer_pickup"
    COURIER         = "courier"


# ══════════════════════════════════════════════════════════════════════════════
# SALES ORDER
# ══════════════════════════════════════════════════════════════════════════════

class SalesOrder(WMSBase):
    __tablename__ = "sales_orders"
    __table_args__ = (
        Index("ix_so_tenant_status", "tenant_id", "status"),
        Index("ix_so_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_so_number", "tenant_id", "so_number", unique=True),
    )

    # Identificación
    tenant_id       = Column(PG_UUID(as_uuid=True), nullable=False)
    warehouse_id    = Column(PG_UUID(as_uuid=True), nullable=False)
    customer_id     = Column(PG_UUID(as_uuid=True), nullable=False)
    so_number       = Column(String(50), nullable=False, comment="Número interno SO-000001")
    customer_po_reference = Column(String(100), comment="# de PO del cliente")
    erp_reference   = Column(String(100), comment="Referencia en ERP externo")

    # Estado y fechas
    status          = Column(Enum(SOStatus), nullable=False, default=SOStatus.DRAFT)
    order_date      = Column(DateTime(timezone=True), nullable=False)
    requested_delivery_date = Column(DateTime(timezone=True))
    confirmed_date  = Column(DateTime(timezone=True))
    shipped_date    = Column(DateTime(timezone=True))
    delivered_date  = Column(DateTime(timezone=True))
    cancelled_date  = Column(DateTime(timezone=True))

    # Prioridad y picking
    priority        = Column(Integer, default=5, comment="1=urgente, 10=normal")
    picking_method  = Column(Enum(PickingMethod), default=PickingMethod.DISCRETE)
    wave_id         = Column(PG_UUID(as_uuid=True), ForeignKey("picking_waves.id"), nullable=True)

    # Financiero
    currency        = Column(String(3), default="USD")
    subtotal        = Column(Numeric(18, 2), default=Decimal("0"))
    tax_amount      = Column(Numeric(18, 2), default=Decimal("0"))
    discount_amount = Column(Numeric(18, 2), default=Decimal("0"))
    total_amount    = Column(Numeric(18, 2), default=Decimal("0"))
    payment_terms   = Column(String(100))

    # Dirección de entrega
    ship_to_name    = Column(String(200))
    ship_to_address = Column(Text)
    ship_to_city    = Column(String(100))
    ship_to_country = Column(String(2))
    ship_to_phone   = Column(String(30))

    # Transporte
    carrier_type    = Column(Enum(ShippingCarrierType), default=ShippingCarrierType.THIRD_PARTY)
    carrier_name    = Column(String(200))
    service_level   = Column(String(50), comment="express, standard, economy")
    incoterms       = Column(String(11))

    # Panama específico
    is_export       = Column(Boolean, default=False)
    dua_number      = Column(String(50), comment="Declaración Única Aduanera")
    ruc_cliente     = Column(String(20), comment="RUC del cliente en Panamá")

    # Notas
    internal_notes  = Column(Text)
    delivery_instructions = Column(Text)
    cancel_reason   = Column(String(500))

    # Auditoría
    created_by_id   = Column(PG_UUID(as_uuid=True), nullable=False)
    erp_synced_at   = Column(DateTime(timezone=True))

    # Relaciones
    lines           = relationship("SalesOrderLine", back_populates="sales_order",
                                   cascade="all, delete-orphan")
    wave            = relationship("PickingWave", back_populates="sales_orders", foreign_keys=[wave_id])
    shipments       = relationship("Shipment", back_populates="sales_order")


class SalesOrderLine(WMSBase):
    __tablename__ = "sales_order_lines"
    __table_args__ = (
        Index("ix_sol_so_id", "so_id"),
        Index("ix_sol_product", "tenant_id", "product_id"),
    )

    tenant_id           = Column(PG_UUID(as_uuid=True), nullable=False)
    so_id               = Column(PG_UUID(as_uuid=True), ForeignKey("sales_orders.id"), nullable=False)
    line_number         = Column(Integer, nullable=False)
    product_id          = Column(PG_UUID(as_uuid=True), nullable=False)
    uom_id              = Column(PG_UUID(as_uuid=True), nullable=False)
    description         = Column(String(500))

    # Cantidades
    quantity_ordered    = Column(Numeric(18, 4), nullable=False)
    quantity_allocated  = Column(Numeric(18, 4), default=Decimal("0"))
    quantity_picked     = Column(Numeric(18, 4), default=Decimal("0"))
    quantity_packed     = Column(Numeric(18, 4), default=Decimal("0"))
    quantity_shipped    = Column(Numeric(18, 4), default=Decimal("0"))
    quantity_backordered = Column(Numeric(18, 4), default=Decimal("0"))

    # Precio
    unit_price          = Column(Numeric(18, 4), default=Decimal("0"))
    discount_pct        = Column(Numeric(5, 4), default=Decimal("0"))
    tax_rate            = Column(Numeric(5, 4), default=Decimal("0"))
    line_total          = Column(Numeric(18, 2), default=Decimal("0"))

    # Estado y picking
    status              = Column(Enum(SOLineStatus), default=SOLineStatus.PENDING)
    batch_id            = Column(PG_UUID(as_uuid=True), nullable=True, comment="Batch asignado por FEFO")
    location_id         = Column(PG_UUID(as_uuid=True), nullable=True, comment="Ubicación de picking")

    # GS1
    gtin                = Column(String(14))

    # Relaciones
    sales_order         = relationship("SalesOrder", back_populates="lines")
    picking_tasks       = relationship("PickingTask", back_populates="so_line")


# ══════════════════════════════════════════════════════════════════════════════
# PICKING WAVE
# ══════════════════════════════════════════════════════════════════════════════

class PickingWave(WMSBase):
    __tablename__ = "picking_waves"
    __table_args__ = (
        Index("ix_wave_tenant_status", "tenant_id", "status"),
    )

    tenant_id           = Column(PG_UUID(as_uuid=True), nullable=False)
    warehouse_id        = Column(PG_UUID(as_uuid=True), nullable=False)
    wave_number         = Column(String(50), nullable=False)
    status              = Column(Enum(WaveStatus), default=WaveStatus.OPEN)
    picking_method      = Column(Enum(PickingMethod), default=PickingMethod.DISCRETE)
    priority            = Column(Integer, default=5)

    # Contadores
    total_orders        = Column(Integer, default=0)
    total_lines         = Column(Integer, default=0)
    total_units         = Column(Numeric(18, 4), default=Decimal("0"))

    # Fechas
    released_at         = Column(DateTime(timezone=True))
    completed_at        = Column(DateTime(timezone=True))

    # LMS
    estimated_minutes   = Column(Integer)
    actual_minutes      = Column(Integer)

    notes               = Column(Text)
    created_by_id       = Column(PG_UUID(as_uuid=True), nullable=False)

    # Relaciones
    sales_orders        = relationship("SalesOrder", back_populates="wave",
                                       foreign_keys="SalesOrder.wave_id")
    picking_tasks       = relationship("PickingTask", back_populates="wave")


# ══════════════════════════════════════════════════════════════════════════════
# PICKING TASK
# ══════════════════════════════════════════════════════════════════════════════

class PickingTask(WMSBase):
    __tablename__ = "picking_tasks"
    __table_args__ = (
        Index("ix_pick_tenant_status", "tenant_id", "status"),
        Index("ix_pick_wave", "wave_id"),
        Index("ix_pick_operator", "assigned_to_id", "status"),
    )

    tenant_id           = Column(PG_UUID(as_uuid=True), nullable=False)
    wave_id             = Column(PG_UUID(as_uuid=True), ForeignKey("picking_waves.id"), nullable=True)
    so_id               = Column(PG_UUID(as_uuid=True), ForeignKey("sales_orders.id"), nullable=False)
    so_line_id          = Column(PG_UUID(as_uuid=True), ForeignKey("sales_order_lines.id"), nullable=False)

    # Producto y cantidades
    product_id          = Column(PG_UUID(as_uuid=True), nullable=False)
    uom_id              = Column(PG_UUID(as_uuid=True), nullable=False)
    batch_id            = Column(PG_UUID(as_uuid=True), nullable=True)
    quantity_requested  = Column(Numeric(18, 4), nullable=False)
    quantity_picked     = Column(Numeric(18, 4), default=Decimal("0"))
    quantity_short      = Column(Numeric(18, 4), default=Decimal("0"),
                                 comment="Diferencia no encontrada en ubicación")

    # Ubicación
    from_location_id    = Column(PG_UUID(as_uuid=True), nullable=False)
    to_location_id      = Column(PG_UUID(as_uuid=True), comment="Staging/packing area")

    # Estado y asignación
    status              = Column(Enum(PickingStatus), default=PickingStatus.PENDING)
    priority            = Column(Integer, default=5)
    assigned_to_id      = Column(PG_UUID(as_uuid=True), nullable=True)

    # GS1 — scan verification
    sscc_scanned        = Column(String(18))
    gtin_scanned        = Column(String(14))

    # Fechas / LMS
    started_at          = Column(DateTime(timezone=True))
    completed_at        = Column(DateTime(timezone=True))
    cycle_time_seconds  = Column(Integer)

    short_reason        = Column(String(500))
    notes               = Column(String(500))

    # Relaciones
    wave                = relationship("PickingWave", back_populates="picking_tasks")
    so_line             = relationship("SalesOrderLine", back_populates="picking_tasks")


# ══════════════════════════════════════════════════════════════════════════════
# PACK STATION / PACK TASK
# ══════════════════════════════════════════════════════════════════════════════

class PackTask(WMSBase):
    """
    Tarea de empaque: agrupa los items pickeados de una SO
    y los empaca en cajas/pallets.
    """
    __tablename__ = "pack_tasks"
    __table_args__ = (
        Index("ix_pack_tenant_status", "tenant_id", "status"),
        Index("ix_pack_so", "so_id"),
    )

    tenant_id           = Column(PG_UUID(as_uuid=True), nullable=False)
    so_id               = Column(PG_UUID(as_uuid=True), ForeignKey("sales_orders.id"), nullable=False)
    pack_task_number    = Column(String(50), nullable=False)
    status              = Column(Enum(PackStatus), default=PackStatus.PENDING)

    # Empaque
    box_type            = Column(String(50), comment="small, medium, large, pallet")
    box_count           = Column(Integer, default=0)
    total_weight_kg     = Column(Numeric(10, 3))
    total_volume_m3     = Column(Numeric(10, 4))

    # GS1 — SSCC del pallet/caja
    sscc                = Column(String(18), comment="SSCC del contenedor de empaque")

    # Estación y operador
    pack_station_id     = Column(PG_UUID(as_uuid=True))
    assigned_to_id      = Column(PG_UUID(as_uuid=True))

    # LMS
    started_at          = Column(DateTime(timezone=True))
    completed_at        = Column(DateTime(timezone=True))
    cycle_time_seconds  = Column(Integer)

    # Documentos
    label_printed       = Column(Boolean, default=False)
    packing_list_printed = Column(Boolean, default=False)

    notes               = Column(Text)
    created_by_id       = Column(PG_UUID(as_uuid=True), nullable=False)


# ══════════════════════════════════════════════════════════════════════════════
# SHIPMENT
# ══════════════════════════════════════════════════════════════════════════════

class Shipment(WMSBase):
    __tablename__ = "shipments"
    __table_args__ = (
        Index("ix_ship_tenant_status", "tenant_id", "status"),
        Index("ix_ship_so", "so_id"),
    )

    tenant_id           = Column(PG_UUID(as_uuid=True), nullable=False)
    so_id               = Column(PG_UUID(as_uuid=True), ForeignKey("sales_orders.id"), nullable=False)
    warehouse_id        = Column(PG_UUID(as_uuid=True), nullable=False)
    shipment_number     = Column(String(50), nullable=False)
    status              = Column(Enum(ShipmentStatus), default=ShipmentStatus.PENDING)

    # Transporte
    carrier_type        = Column(Enum(ShippingCarrierType))
    carrier_name        = Column(String(200))
    tracking_number     = Column(String(100))
    vehicle_plate       = Column(String(20))
    driver_name         = Column(String(200))
    driver_id_number    = Column(String(30))

    # Fechas
    scheduled_pickup    = Column(DateTime(timezone=True))
    actual_pickup       = Column(DateTime(timezone=True))
    estimated_delivery  = Column(DateTime(timezone=True))
    actual_delivery     = Column(DateTime(timezone=True))

    # Carga
    total_boxes         = Column(Integer, default=0)
    total_weight_kg     = Column(Numeric(10, 3))
    total_volume_m3     = Column(Numeric(10, 4))

    # Documentos Panamá
    delivery_note_number = Column(String(50))
    dua_number          = Column(String(50), comment="DUA para exportaciones")
    bl_number           = Column(String(50), comment="Bill of Lading")
    is_export           = Column(Boolean, default=False)

    # Firma digital / confirmación de entrega
    delivered_to_name   = Column(String(200))
    delivered_signature = Column(Text, comment="Base64 firma digital")
    delivery_photo_url  = Column(String(500))

    # ERP sync
    erp_synced_at       = Column(DateTime(timezone=True))
    notes               = Column(Text)
    created_by_id       = Column(PG_UUID(as_uuid=True), nullable=False)

    # Relaciones
    sales_order         = relationship("SalesOrder", back_populates="shipments")


# ══════════════════════════════════════════════════════════════════════════════
# RETURN ORDER (RMA)
# ══════════════════════════════════════════════════════════════════════════════

class ReturnOrder(WMSBase):
    """Devolución de cliente — Return Merchandise Authorization."""
    __tablename__ = "return_orders"
    __table_args__ = (
        Index("ix_rma_tenant_status", "tenant_id", "status"),
    )

    tenant_id           = Column(PG_UUID(as_uuid=True), nullable=False)
    warehouse_id        = Column(PG_UUID(as_uuid=True), nullable=False)
    so_id               = Column(PG_UUID(as_uuid=True), ForeignKey("sales_orders.id"), nullable=True)
    customer_id         = Column(PG_UUID(as_uuid=True), nullable=False)
    rma_number          = Column(String(50), nullable=False)
    status              = Column(Enum(ReturnOrderStatus), default=ReturnOrderStatus.REQUESTED)

    reason              = Column(String(500), nullable=False)
    return_type         = Column(String(50), comment="refund, exchange, credit")

    # Recepción
    received_at         = Column(DateTime(timezone=True))
    received_by_id      = Column(PG_UUID(as_uuid=True))
    inspection_notes    = Column(Text)
    restocking_eligible = Column(Boolean, default=False,
                                  comment="Puede volver al inventario vendible")
    restocking_location_id = Column(PG_UUID(as_uuid=True))

    # Financiero
    refund_amount       = Column(Numeric(18, 2), default=Decimal("0"))
    refund_issued_at    = Column(DateTime(timezone=True))
    credit_memo_number  = Column(String(50))

    notes               = Column(Text)
    created_by_id       = Column(PG_UUID(as_uuid=True), nullable=False)
