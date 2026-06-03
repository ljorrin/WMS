"""
WMS Panama — Inventory Models
================================
Modelos de inventario en tiempo real:
- InventoryLevel (stock por ubicacion/lote/serie)
- InventoryMovement (evento de movimiento — Event Sourcing)
- Batch (numero de lote con fecha de vencimiento)
- SerialNumber (numero de serie — trazabilidad 1:1)
- InventoryReservation (reservas de stock)
- CycleCount (conteo de inventario)
- CycleCountLine (linea de conteo)
- InventoryAdjustment (ajuste con flujo de aprobacion)
- StockAlert (alertas de nivel de stock)
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

class MovementType(str, PyEnum):
    """Tipos de movimiento de inventario — Event Sourcing."""
    # Entradas
    RECEIPT         = "receipt"          # Recepcion de proveedor (GRN)
    RETURN_FROM_CUSTOMER = "return_from_customer"  # Devolucion de cliente
    TRANSFER_IN     = "transfer_in"      # Entrada por transferencia
    PRODUCTION_IN   = "production_in"    # Entrada de produccion (PT)
    ADJUSTMENT_IN   = "adjustment_in"    # Ajuste positivo
    FOUND           = "found"            # Faltante encontrado en conteo

    # Salidas
    SHIPMENT        = "shipment"         # Despacho a cliente
    RETURN_TO_SUPPLIER = "return_to_supplier"  # Devolucion a proveedor
    TRANSFER_OUT    = "transfer_out"     # Salida por transferencia
    PRODUCTION_OUT  = "production_out"   # Salida a produccion (MP/insumos)
    ADJUSTMENT_OUT  = "adjustment_out"   # Ajuste negativo
    DAMAGE          = "damage"           # Producto danado
    EXPIRED         = "expired"          # Producto vencido
    SAMPLE          = "sample"           # Muestra para QC/marketing
    SCRAP           = "scrap"            # Merma

    # Internos
    PUTAWAY         = "putaway"          # Ubicacion inicial post-recepcion
    REPLENISHMENT   = "replenishment"    # Reposicion de frente de picking
    RELOCATION      = "relocation"       # Relocation interna (slotting)
    PICK            = "pick"             # Picking de una orden
    PACK            = "pack"             # Packing (consolidacion)
    CYCLE_COUNT     = "cycle_count"      # Ajuste por conteo ciclico


class InventoryStatus(str, PyEnum):
    """Estado del inventario en una ubicacion."""
    AVAILABLE    = "available"     # Disponible para picking
    RESERVED     = "reserved"      # Reservado para una orden
    QUARANTINE   = "quarantine"    # En cuarentena (QC pendiente)
    BLOCKED      = "blocked"       # Bloqueado (recall, danado, etc.)
    IN_TRANSIT   = "in_transit"    # En transito entre bodegas
    DAMAGED      = "damaged"       # Danado, no se puede usar
    EXPIRED      = "expired"       # Vencido
    COUNTING     = "counting"      # En proceso de conteo ciclico


class ReservationType(str, PyEnum):
    HARD       = "hard"       # Reserva fisica (separado)
    SOFT       = "soft"       # Reserva logica (comprometido)
    PROJECT    = "project"    # Para proyecto especifico
    VIP        = "vip"        # Para cliente VIP
    PROMOTION  = "promotion"  # Para campana/promocion
    PRODUCTION = "production" # Para orden de produccion


class AdjustmentStatus(str, PyEnum):
    DRAFT             = "draft"              # Borrador (recien creado)
    PENDING_APPROVAL  = "pending_approval"  # Esperando aprobacion
    APPROVED          = "approved"          # Aprobado
    REJECTED          = "rejected"          # Rechazado
    APPLIED           = "applied"           # Aplicado al inventario


class CycleCountStatus(str, PyEnum):
    DRAFT      = "draft"      # En preparacion
    IN_PROGRESS = "in_progress"
    COMPLETED  = "completed"
    CANCELLED  = "cancelled"


class SerialStatus(str, PyEnum):
    IN_STOCK    = "in_stock"
    RESERVED    = "reserved"
    SHIPPED     = "shipped"
    RETURNED    = "returned"
    DAMAGED     = "damaged"
    LOST        = "lost"


# ─── BATCH (NUMERO DE LOTE) ───────────────────────────────────────────────────

class Batch(WMSTenantBase):
    """
    Batch = Numero de lote de un producto.
    Critico para farmaceuticos, alimentos y cualquier producto con FEFO.
    Un lote tiene fecha de fabricacion, fecha de vencimiento y origen.
    """
    __tablename__ = "batches"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False
    )

    batch_number: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Numero de lote del proveedor o fabricante"
    )
    internal_batch: Mapped[Optional[str]] = mapped_column(
        String(100), comment="Numero de lote interno asignado por el WMS"
    )

    # Fechas criticas
    manufacture_date: Mapped[Optional[date]] = mapped_column(
        Date, comment="Fecha de fabricacion"
    )
    expiry_date: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, index=True,
        comment="Fecha de vencimiento — CRITICO para FEFO"
    )
    best_before_date: Mapped[Optional[date]] = mapped_column(
        Date, comment="Fecha de consumo preferente (puede diferir del vencimiento legal)"
    )
    received_date: Mapped[date] = mapped_column(
        Date, nullable=False,
        comment="Fecha en que se recibio este lote en la bodega"
    )

    # Origen
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True
    )
    country_of_origin: Mapped[Optional[str]] = mapped_column(String(2))

    # Certificados y calidad
    certificate_of_analysis: Mapped[Optional[str]] = mapped_column(
        String(500), comment="URL del certificado de analisis del lote"
    )
    sanitary_lot_number: Mapped[Optional[str]] = mapped_column(
        String(100), comment="Numero de lote sanitario MINSA"
    )
    qc_status: Mapped[str] = mapped_column(
        String(20), default="pending",
        comment="Estado QC: pending | approved | rejected | released"
    )
    qc_approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    qc_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Temperatura (cadena de frio)
    received_temp_celsius: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), comment="Temperatura al momento de recepcion"
    )
    temp_excursion: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="True si hubo excursion de temperatura en este lote"
    )

    # Estado del lote
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text)
    blocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_recalled: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="True si hay una alerta de retiro (recall) para este lote"
    )

    custom_attributes: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "product_id", "warehouse_id", "batch_number",
            name="uq_batches_tenant_product_warehouse_number"
        ),
        Index("ix_batches_product_expiry", "product_id", "expiry_date"),
        Index("ix_batches_warehouse_expiry", "warehouse_id", "expiry_date"),
        Index("ix_batches_tenant_product", "tenant_id", "product_id"),
        # Indice para alertas de vencimiento proximo
        Index("ix_batches_expiry_active", "expiry_date", "is_blocked", "is_recalled"),
    )

    def __repr__(self) -> str:
        return f"<Batch {self.batch_number} expires={self.expiry_date}>"


# ─── SERIAL NUMBER ────────────────────────────────────────────────────────────

class SerialNumber(WMSTenantBase):
    """
    SerialNumber = Numero de serie para productos con trazabilidad 1:1.
    Usado en electronica, automotriz, equipos medicos.
    Cada unidad tiene su propio numero de serie y ciclo de vida trazado.
    """
    __tablename__ = "serial_numbers"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="SET NULL"),
        nullable=True
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True
    )

    serial_number: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Numero de serie del fabricante"
    )
    internal_serial: Mapped[Optional[str]] = mapped_column(
        String(100), comment="Numero de serie interno asignado por WMS"
    )

    status: Mapped[SerialStatus] = mapped_column(
        Enum(SerialStatus), nullable=False, default=SerialStatus.IN_STOCK
    )

    # Trazabilidad
    received_date: Mapped[Optional[date]] = mapped_column(Date)
    shipped_date: Mapped[Optional[date]] = mapped_column(Date)
    last_movement_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Garantia
    warranty_months: Mapped[Optional[int]] = mapped_column(Integer)
    warranty_expires_at: Mapped[Optional[date]] = mapped_column(Date)

    custom_attributes: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "product_id", "serial_number",
                         name="uq_serials_tenant_product_serial"),
        Index("ix_serials_product_status", "product_id", "status"),
        Index("ix_serials_location", "location_id"),
        Index("ix_serials_serial_number", "serial_number"),
    )


# ─── INVENTORY LEVEL ──────────────────────────────────────────────────────────

class InventoryLevel(WMSTenantBase):
    """
    InventoryLevel = Stock actual por combinacion de:
    (warehouse + location + product + batch + status)

    Esta tabla es el ESTADO ACTUAL del inventario.
    Cada movimiento (InventoryMovement) actualiza estos contadores.

    CRITICO: Los locks de Redis garantizan que operaciones concurrentes
    no generen inconsistencias en esta tabla.

    Patron: CQRS — esta tabla es el READ MODEL.
    InventoryMovement es el WRITE MODEL (Event Sourcing).
    """
    __tablename__ = "inventory_levels"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True
    )

    # Cantidades
    quantity_on_hand: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, default=0,
        comment="Cantidad fisica total en la ubicacion"
    )
    quantity_available: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, default=0,
        comment="Cantidad disponible = on_hand - reserved - picking"
    )
    quantity_reserved: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, default=0,
        comment="Cantidad reservada para ordenes"
    )
    quantity_in_picking: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, default=0,
        comment="Cantidad actualmente en proceso de picking"
    )
    quantity_damaged: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False, default=0
    )

    # Estado del stock en esta ubicacion
    status: Mapped[InventoryStatus] = mapped_column(
        Enum(InventoryStatus), nullable=False, default=InventoryStatus.AVAILABLE
    )

    # Valor (referencial)
    unit_cost: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 4), comment="Costo unitario al momento de recepcion"
    )
    total_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 2),
        comment="Valor total = quantity_on_hand * unit_cost"
    )

    # Trazabilidad de ultimo movimiento
    last_movement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        comment="Referencia al ultimo InventoryMovement que afecto este nivel"
    )
    last_movement_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        comment="Timestamp del ultimo movimiento"
    )
    last_movement_type: Mapped[Optional[MovementType]] = mapped_column(
        Enum(MovementType)
    )

    __table_args__ = (
        # Constraint de unicidad: solo puede haber 1 registro por combinacion
        UniqueConstraint(
            "warehouse_id", "location_id", "product_id", "batch_id", "status",
            name="uq_inventory_levels_location_product_batch_status"
        ),
        # Indice principal de consulta de inventario disponible
        Index("ix_inv_levels_tenant_warehouse_product",
              "tenant_id", "warehouse_id", "product_id"),
        Index("ix_inv_levels_location_product", "location_id", "product_id"),
        Index("ix_inv_levels_warehouse_status",
              "warehouse_id", "status"),
        Index("ix_inv_levels_product_available",
              "product_id", "quantity_available"),
        # Indice para alertas de stock bajo
        Index("ix_inv_levels_tenant_available",
              "tenant_id", "quantity_available"),
    )

    def __repr__(self) -> str:
        return (f"<InventoryLevel product={self.product_id} "
                f"loc={self.location_id} qty={self.quantity_on_hand}>")


# ─── INVENTORY MOVEMENT ───────────────────────────────────────────────────────

class InventoryMovement(WMSTenantBase):
    """
    InventoryMovement = Registro inmutable de cada evento de inventario.

    Implementa EVENT SOURCING: cada cambio de inventario genera un evento
    que NO puede modificarse. El estado actual (InventoryLevel) se deriva
    de la secuencia de movimientos.

    CRITICO para auditoria: ANA requiere trazabilidad completa de movimientos.
    Esta tabla se particiona por fecha para mantener performance con millones de registros.
    """
    __tablename__ = "inventory_movements"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True
    )
    serial_number_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("serial_numbers.id", ondelete="RESTRICT"),
        nullable=True
    )

    # Ubicaciones origen y destino
    from_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=True,
        comment="Ubicacion de origen (NULL para recepciones)"
    )
    to_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=True,
        comment="Ubicacion de destino (NULL para despachos)"
    )

    # Tipo y cantidad
    movement_type: Mapped[MovementType] = mapped_column(
        Enum(MovementType), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False,
        comment="Cantidad movida (siempre positiva, la direccion la da movement_type)"
    )
    uom: Mapped[str] = mapped_column(String(20), default="UN")

    # Valoracion al momento del movimiento
    unit_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    total_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Referencias a documentos originadores
    source_document_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Tipo de documento origen: purchase_order | sales_order | transfer | adjustment"
    )
    source_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        comment="UUID del documento origen (PO, SO, Transfer, etc.)"
    )
    source_document_number: Mapped[Optional[str]] = mapped_column(
        String(50), comment="Numero legible del documento origen"
    )
    source_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), comment="UUID de la linea del documento origen"
    )

    # Operario que ejecuto
    operator_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Contexto del movimiento
    notes: Mapped[Optional[str]] = mapped_column(Text)
    reference: Mapped[Optional[str]] = mapped_column(
        String(100), comment="Referencia externa (numero de guia, DAM, etc.)"
    )

    # Timestamp del evento (diferente de created_at que es cuando se registro)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False, index=True,
        comment="Momento en que ocurrio fisicamente el movimiento"
    )

    # Estado de registro en sistemas externos
    erp_synced: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="True si ya se sincronizo con el ERP"
    )
    erp_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    erp_document_id: Mapped[Optional[str]] = mapped_column(
        String(100), comment="ID del documento creado en el ERP"
    )

    movement_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_inv_movements_tenant_warehouse", "tenant_id", "warehouse_id"),
        Index("ix_inv_movements_product_occurred",
              "product_id", "occurred_at"),
        Index("ix_inv_movements_warehouse_type",
              "warehouse_id", "movement_type", "occurred_at"),
        Index("ix_inv_movements_source_doc",
              "source_document_type", "source_document_id"),
        Index("ix_inv_movements_operator", "operator_id"),
        Index("ix_inv_movements_occurred", "occurred_at"),
        # NOTA: Particionamiento por occurred_at se define en migracion Alembic
        # PostgreSQL PARTITION BY RANGE (occurred_at) mensual
    )

    def __repr__(self) -> str:
        return (f"<InventoryMovement {self.movement_type} "
                f"qty={self.quantity} product={self.product_id}>")


# ─── INVENTORY RESERVATION ────────────────────────────────────────────────────

class InventoryReservation(WMSTenantBase):
    """
    Reserva de inventario para una orden o proyecto especifico.
    Las reservas se crean antes del picking para garantizar disponibilidad.
    Una reserva HARD separa fisicamente el stock; SOFT solo lo compromete.
    """
    __tablename__ = "inventory_reservations"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=True,
        comment="NULL = reserva a nivel de almacen (sin ubicacion especifica)"
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True
    )

    # Tipo y cantidad
    reservation_type: Mapped[ReservationType] = mapped_column(
        Enum(ReservationType), nullable=False, default=ReservationType.SOFT
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    quantity_picked: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), default=0,
        comment="Cantidad ya pickeada de esta reserva"
    )

    # Referencia
    source_document_type: Mapped[str] = mapped_column(String(50))
    source_document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    source_document_number: Mapped[Optional[str]] = mapped_column(String(50))

    # Control de vigencia
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        comment="Expiracion automatica de la reserva (NULL = permanente)"
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("ix_reservations_warehouse_product",
              "warehouse_id", "product_id", "is_active"),
        Index("ix_reservations_source_doc",
              "source_document_type", "source_document_id"),
        Index("ix_reservations_expires", "expires_at", "is_active"),
    )


# ─── CYCLE COUNT ──────────────────────────────────────────────────────────────

class CycleCount(WMSTenantBase):
    """
    CycleCount = Sesion de conteo de inventario.
    Tipos: ciclico (por zona/ABC), fisico total, ciego, por discrepancia.
    """
    __tablename__ = "cycle_counts"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False
    )

    count_number: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="Numero de conteo (ej: CC-2026-001)"
    )
    count_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="cyclic",
        comment="cyclic | full_physical | blind | discrepancy | abc_rotation"
    )
    status: Mapped[CycleCountStatus] = mapped_column(
        Enum(CycleCountStatus), default=CycleCountStatus.DRAFT
    )

    # Scope del conteo
    zone_ids: Mapped[Optional[list]] = mapped_column(
        JSONB, comment="Lista de zone_ids a contar (NULL = toda la bodega)"
    )
    abc_classes: Mapped[Optional[list]] = mapped_column(
        JSONB, comment="Clases ABC a contar: ['A'], ['A','B'], etc."
    )
    is_blind: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="True = operario no ve la cantidad teorica (conteo ciego)"
    )

    # Tolerancias
    variance_tolerance_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), default=0.5,
        comment="% de variacion aceptable antes de requerir segundo conteo"
    )
    value_threshold_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        comment="Valor en USD por encima del cual cualquier discrepancia requiere aprobacion"
    )

    # Fechas
    planned_date: Mapped[Optional[date]] = mapped_column(Date)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Responsables
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Resumen (calculado al cerrar)
    total_locations_counted: Mapped[Optional[int]] = mapped_column(Integer)
    total_skus_counted: Mapped[Optional[int]] = mapped_column(Integer)
    total_discrepancies: Mapped[Optional[int]] = mapped_column(Integer)
    accuracy_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    total_variance_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))

    notes: Mapped[Optional[str]] = mapped_column(Text)

    lines: Mapped[List["CycleCountLine"]] = relationship(
        back_populates="cycle_count"
    )

    __table_args__ = (
        UniqueConstraint("warehouse_id", "count_number",
                         name="uq_cycle_counts_warehouse_number"),
        Index("ix_cycle_counts_warehouse_status", "warehouse_id", "status"),
        Index("ix_cycle_counts_tenant", "tenant_id"),
    )


class CycleCountLine(WMSTenantBase):
    """Linea de conteo de inventario — una ubicacion/SKU contada."""
    __tablename__ = "cycle_count_lines"

    cycle_count_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cycle_counts.id", ondelete="CASCADE"),
        nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False
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

    # Cantidades
    system_quantity: Mapped[Decimal] = mapped_column(
        Numeric(15, 4), nullable=False,
        comment="Cantidad segun sistema antes del conteo"
    )
    counted_quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 4), nullable=True,
        comment="Cantidad contada por el operario"
    )
    recount_quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 4), nullable=True,
        comment="Cantidad del segundo conteo si hubo discrepancia"
    )
    variance: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 4), comment="counted - system (puede ser negativo)"
    )
    variance_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))

    # Estado de la linea
    status: Mapped[str] = mapped_column(
        String(20), default="pending",
        comment="pending | counted | recount_needed | approved | adjusted"
    )
    needs_recount: Mapped[bool] = mapped_column(Boolean, default=False)

    # Quien y cuando
    counted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    counted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    notes: Mapped[Optional[str]] = mapped_column(Text)
    cycle_count: Mapped["CycleCount"] = relationship(back_populates="lines")

    __table_args__ = (
        Index("ix_cycle_count_lines_count", "cycle_count_id"),
        Index("ix_cycle_count_lines_location_product",
              "location_id", "product_id"),
    )


# ─── INVENTORY ADJUSTMENT ─────────────────────────────────────────────────────

class InventoryAdjustment(WMSTenantBase):
    """
    Ajuste de inventario con flujo de aprobacion.
    El ajuste no se aplica hasta ser aprobado por el nivel requerido.
    Nivel de aprobacion se determina por el valor del ajuste.
    """
    __tablename__ = "inventory_adjustments"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False
    )
    # Nota: el ajuste es cabecera + lineas (ver AdjustmentLine). Estas columnas
    # de un solo SKU se conservan como opcionales para compatibilidad/atajos,
    # pero el detalle real vive en las lineas.
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=True
    )
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=True
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True
    )

    adjustment_number: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Razon del ajuste: cycle_count | damage | expiry | found | error | other"
    )
    reason_code: Mapped[Optional[str]] = mapped_column(
        String(50), comment="Codigo de razon: DAMAGE | EXPIRED | COUNT_ERROR | THEFT | etc."
    )
    reason_detail: Mapped[Optional[str]] = mapped_column(Text)
    reference_number: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Cantidades (a nivel cabecera, opcionales — el detalle vive en lineas)
    quantity_before: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    quantity_after: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    quantity_delta: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 4),
        comment="quantity_after - quantity_before (puede ser negativo)"
    )

    # Valor del ajuste (para determinar nivel de aprobacion)
    unit_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    adjustment_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2),
        comment="Valor economico del ajuste en USD (|delta| * unit_cost)"
    )

    # Flujo de aprobacion
    status: Mapped[AdjustmentStatus] = mapped_column(
        Enum(AdjustmentStatus), default=AdjustmentStatus.DRAFT
    )
    required_approval_level: Mapped[str] = mapped_column(
        String(30), default="auto",
        comment="auto | supervisor | manager | director"
    )
    requested_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejected_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    applied_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Referencia a conteo ciclico si aplica
    cycle_count_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cycle_counts.id", ondelete="SET NULL"),
        nullable=True
    )
    cycle_count_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cycle_count_lines.id", ondelete="SET NULL"),
        nullable=True
    )

    lines: Mapped[List["AdjustmentLine"]] = relationship(
        back_populates="adjustment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("warehouse_id", "adjustment_number",
                         name="uq_adjustments_warehouse_number"),
        Index("ix_adjustments_warehouse_status", "warehouse_id", "status"),
        Index("ix_adjustments_tenant", "tenant_id"),
    )

    @property
    def total_lines(self) -> int:
        """Numero de lineas del ajuste (requiere lines cargadas)."""
        return len(self.lines)

    @property
    def total_variance_value(self) -> Optional[Decimal]:
        """Valor economico total de la varianza (suma de las lineas)."""
        costs = [l.total_variance_cost for l in self.lines if l.total_variance_cost is not None]
        return sum(costs) if costs else None


class AdjustmentLine(WMSTenantBase):
    """
    Línea de un ajuste de inventario (un SKU/ubicación con su varianza).
    Un InventoryAdjustment puede agrupar múltiples líneas contadas.
    """
    __tablename__ = "inventory_adjustment_lines"

    adjustment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventory_adjustments.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=True
    )
    lot_number: Mapped[Optional[str]] = mapped_column(String(50))

    quantity_system: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    quantity_physical: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    variance: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False, default=0)
    variance_type: Mapped[str] = mapped_column(
        String(20), default="none",
        comment="surplus | shortage | none"
    )
    unit_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    total_variance_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    adjustment: Mapped["InventoryAdjustment"] = relationship(back_populates="lines")

    __table_args__ = (
        Index("ix_adjustment_lines_adjustment", "adjustment_id"),
    )


# ─── STOCK ALERT ──────────────────────────────────────────────────────────────

class StockAlert(WMSTenantBase):
    """
    Alertas automaticas de nivel de stock.
    Generadas por el sistema cuando se detectan condiciones criticas.
    """
    __tablename__ = "stock_alerts"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="SET NULL"),
        nullable=True
    )

    alert_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="below_reorder_point | out_of_stock | near_expiry | expired | recall | temp_excursion"
    )
    severity: Mapped[str] = mapped_column(
        String(10), default="medium",
        comment="critical | high | medium | low"
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    current_value: Mapped[Optional[str]] = mapped_column(
        String(100), comment="Valor actual que genero la alerta (ej: 5 unidades, 3 dias para vencer)"
    )
    threshold_value: Mapped[Optional[str]] = mapped_column(
        String(100), comment="Umbral configurado que se supero"
    )

    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)

    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notified_users: Mapped[Optional[list]] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_stock_alerts_warehouse_type",
              "warehouse_id", "alert_type", "is_resolved"),
        Index("ix_stock_alerts_product", "product_id", "is_resolved"),
        Index("ix_stock_alerts_tenant_unresolved",
              "tenant_id", "is_resolved"),
    )
