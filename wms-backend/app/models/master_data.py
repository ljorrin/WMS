"""
WMS Panama — Master Data Models
=================================
Modelos de datos maestros:
- ProductCategory / ProductFamily
- Product (SKU maestro multi-industria)
- ProductPackaging (jerarquia GS1)
- Location (ubicacion en bodega con geometria)
- Zone (agrupacion logica de ubicaciones)
- Aisle / Rack / Level / Position
- Supplier (proveedor)
- Customer (cliente)
- Carrier (transportista)
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional, List

from sqlalchemy import (
    Boolean, Enum, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import WMSTenantBase
from app.models.core import IndustryType


# ─── ENUMS ────────────────────────────────────────────────────────────────────

class ProductStatus(str, PyEnum):
    ACTIVE      = "active"
    INACTIVE    = "inactive"
    DISCONTINUED = "discontinued"
    SEASONAL    = "seasonal"


class TrackingType(str, PyEnum):
    """Como se rastrea el inventario de este producto."""
    NONE        = "none"         # Sin trazabilidad especial (granel simple)
    LOT         = "lot"          # Por numero de lote
    SERIAL      = "serial"       # Por numero de serie (1:1 con unidad)
    LOT_EXPIRY  = "lot_expiry"   # Lote + fecha de vencimiento (farma, alimentos)
    SERIAL_LOT  = "serial_lot"   # Serie + lote (automotriz)


class RotationStrategy(str, PyEnum):
    FEFO = "FEFO"  # First Expired First Out (farma, alimentos)
    FIFO = "FIFO"  # First In First Out (general)
    LIFO = "LIFO"  # Last In First Out (casos especiales)
    LEFO = "LEFO"  # Least Expired First Out (variante FEFO)


class StorageCondition(str, PyEnum):
    AMBIENT         = "ambient"         # Temperatura ambiente
    CONTROLLED      = "controlled"      # Temperatura controlada (15-25°C)
    REFRIGERATED    = "refrigerated"    # Refrigerado (2-8°C)
    FROZEN          = "frozen"          # Congelado (-18°C o menos)
    ULTRA_FROZEN    = "ultra_frozen"    # Ultra congelado (-80°C)
    FLAMMABLE       = "flammable"       # Inflamable
    HAZMAT          = "hazmat"          # Material peligroso
    CONTROLLED_SUBSTANCE = "controlled_substance"  # Sustancia controlada


class LocationType(str, PyEnum):
    STANDARD    = "standard"      # Ubicacion estandar de picking
    BULK        = "bulk"          # Zona de bulto/reserva
    FLOOR       = "floor"         # Piso (sin rack)
    MEZZANINE   = "mezzanine"     # Mezanine
    COLD_ROOM   = "cold_room"     # Cuarto frio
    HAZMAT      = "hazmat"        # Zona de materiales peligrosos
    QUARANTINE  = "quarantine"    # Cuarentena
    RECEIVING   = "receiving"     # Zona de recepcion
    SHIPPING    = "shipping"      # Zona de despacho
    STAGING     = "staging"       # Zona de staging/consolidacion
    CROSS_DOCK  = "cross_dock"    # Cross-docking
    DAMAGED     = "damaged"       # Productos danados
    RETURNS     = "returns"       # Zona de devoluciones


class LocationStatus(str, PyEnum):
    ACTIVE      = "active"
    INACTIVE    = "inactive"
    BLOCKED     = "blocked"       # Bloqueada temporalmente
    MAINTENANCE = "maintenance"   # En mantenimiento


class SupplierStatus(str, PyEnum):
    ACTIVE    = "active"
    INACTIVE  = "inactive"
    BLOCKED   = "blocked"
    PENDING   = "pending"         # En proceso de homologacion


class CustomerType(str, PyEnum):
    RETAIL          = "retail"
    WHOLESALE       = "wholesale"
    DISTRIBUTOR     = "distributor"
    ECOMMERCE       = "ecommerce"
    GOVERNMENT      = "government"
    INTERNAL        = "internal"    # Transfer entre plantas propias


# ─── PRODUCT CATEGORY ─────────────────────────────────────────────────────────

class ProductCategory(WMSTenantBase):
    """
    Categoria jerarquica de productos.
    Soporta hasta 3 niveles: Categoria > Subcategoria > Sub-subcategoria.
    """
    __tablename__ = "product_categories"

    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_categories.id", ondelete="RESTRICT"),
        nullable=True,
        comment="NULL = categoria raiz"
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    level: Mapped[int] = mapped_column(
        Integer, default=1,
        comment="Nivel jerarquico: 1=raiz, 2=subcategoria, 3=sub-sub"
    )
    industry: Mapped[Optional[IndustryType]] = mapped_column(
        Enum(IndustryType), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relaciones
    parent: Mapped[Optional["ProductCategory"]] = relationship(
        "ProductCategory", remote_side="ProductCategory.id", back_populates="children"
    )
    children: Mapped[List["ProductCategory"]] = relationship(
        back_populates="parent"
    )
    products: Mapped[List["Product"]] = relationship(back_populates="category")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_product_categories_tenant_code"),
        Index("ix_product_categories_tenant_parent", "tenant_id", "parent_id"),
    )


# ─── PRODUCT ──────────────────────────────────────────────────────────────────

class Product(WMSTenantBase):
    """
    Product = SKU maestro del WMS.
    Modelo multi-industria con atributos variables por JSONB.
    Un Product puede tener multiples ProductPackaging (jerarquia GS1).

    CRITICO: Este es el modelo mas importante del WMS.
    Errores en maestro de productos impactan TODA la operacion.
    """
    __tablename__ = "products"

    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_categories.id", ondelete="SET NULL"),
        nullable=True
    )

    # Identificacion primaria
    sku: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="SKU interno del tenant (codigo de articulo)"
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    short_description: Mapped[Optional[str]] = mapped_column(String(500))

    # Nombres en multiples idiomas
    name_en: Mapped[Optional[str]] = mapped_column(
        String(300), comment="Nombre en ingles para documentos de exportacion"
    )

    # GS1 / Codigos
    gtin_13: Mapped[Optional[str]] = mapped_column(
        String(14), nullable=True, index=True,
        comment="GTIN-13 (EAN-13): codigo de barras del producto individual"
    )
    gtin_14: Mapped[Optional[str]] = mapped_column(
        String(14), nullable=True, index=True,
        comment="GTIN-14: codigo de barras de la caja/embalaje"
    )
    upc: Mapped[Optional[str]] = mapped_column(
        String(12), nullable=True,
        comment="UPC-A: codigo para mercado norteamericano"
    )
    isbn: Mapped[Optional[str]] = mapped_column(
        String(13), nullable=True,
        comment="ISBN para libros y publicaciones"
    )
    internal_code: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Codigo interno adicional (ej: codigo del ERP)"
    )
    supplier_sku: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="SKU del proveedor principal"
    )

    # Clasificacion
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus), default=ProductStatus.ACTIVE
    )
    industry: Mapped[IndustryType] = mapped_column(
        Enum(IndustryType), default=IndustryType.GENERAL
    )

    # Trazabilidad
    tracking_type: Mapped[TrackingType] = mapped_column(
        Enum(TrackingType), nullable=False, default=TrackingType.LOT,
        comment="Como se rastrea el inventario de este producto"
    )
    rotation_strategy: Mapped[RotationStrategy] = mapped_column(
        Enum(RotationStrategy), default=RotationStrategy.FEFO
    )
    shelf_life_days: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="Vida util en dias (para FEFO y alertas de vencimiento)"
    )
    days_before_expiry_alert: Mapped[int] = mapped_column(
        Integer, default=30,
        comment="Dias antes del vencimiento para generar alerta"
    )
    min_remaining_shelf_life_pct: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="% minimo de vida util restante para aceptar en recepcion"
    )

    # Almacenamiento
    storage_condition: Mapped[StorageCondition] = mapped_column(
        Enum(StorageCondition), default=StorageCondition.AMBIENT
    )
    min_temp_celsius: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), comment="Temperatura minima de almacenamiento (°C)"
    )
    max_temp_celsius: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), comment="Temperatura maxima de almacenamiento (°C)"
    )
    min_humidity_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    max_humidity_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    is_hazmat: Mapped[bool] = mapped_column(Boolean, default=False)
    hazmat_class: Mapped[Optional[str]] = mapped_column(
        String(20), comment="Clase de material peligroso (ONU)"
    )
    is_controlled_substance: Mapped[bool] = mapped_column(Boolean, default=False)

    # Dimensiones de la unidad base
    weight_kg: Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    length_cm: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    width_cm: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    height_cm: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    volume_m3: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))

    # Unidad de medida
    uom: Mapped[str] = mapped_column(
        String(20), default="UN",
        comment="Unidad de medida: UN, KG, LT, MT, CJ, PAL, etc."
    )
    uom_purchase: Mapped[Optional[str]] = mapped_column(
        String(20), comment="Unidad de medida de compra (puede diferir de venta)"
    )

    # Valoracion (referencia — valoracion definitiva en ERP)
    cost_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 4), comment="Costo referencial en USD"
    )
    sale_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 4), comment="Precio de venta referencial en USD"
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Regulatorio Panama
    sanitary_registry: Mapped[Optional[str]] = mapped_column(
        String(50), comment="Numero de registro sanitario MINSA (farma/alimentos)"
    )
    tariff_code: Mapped[Optional[str]] = mapped_column(
        String(20), comment="Codigo arancelario (partida arancelaria)"
    )
    country_of_origin: Mapped[Optional[str]] = mapped_column(
        String(2), comment="Pais de origen ISO 3166-1 alpha-2"
    )
    requires_customs_clearance: Mapped[bool] = mapped_column(Boolean, default=False)

    # Picking / WMS
    abc_classification: Mapped[Optional[str]] = mapped_column(
        String(1), comment="Clasificacion ABC de rotacion: A=alta, B=media, C=baja"
    )
    xyz_classification: Mapped[Optional[str]] = mapped_column(
        String(1), comment="Clasificacion XYZ de variabilidad: X=estable, Y=variable, Z=esporadico"
    )
    pick_face_quantity: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Cantidad de unidades en el frente de picking"
    )
    min_pick_quantity: Mapped[Optional[int]] = mapped_column(Integer, default=1)
    max_stack_count: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Numero maximo de unidades apilables"
    )

    # Reposicion
    reorder_point: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Punto de reposicion (unidades)"
    )
    reorder_quantity: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Cantidad de reposicion sugerida"
    )
    safety_stock: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Stock de seguridad (unidades)"
    )
    lead_time_days: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Lead time de reposicion en dias"
    )

    # Atributos extra por industria (JSONB flexible)
    custom_attributes: Mapped[Optional[dict]] = mapped_column(
        JSONB, default=dict,
        comment="Atributos adicionales por industria (color, talla, material, etc.)"
    )

    # Medios
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    documents: Mapped[Optional[dict]] = mapped_column(
        JSONB, comment="URLs de fichas tecnicas, MSDS, certificados"
    )

    # Relaciones
    category: Mapped[Optional["ProductCategory"]] = relationship(back_populates="products")
    packagings: Mapped[List["ProductPackaging"]] = relationship(
        back_populates="product", order_by="ProductPackaging.level"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_products_tenant_sku"),
        Index("ix_products_tenant_sku", "tenant_id", "sku"),
        Index("ix_products_gtin13", "gtin_13"),
        Index("ix_products_gtin14", "gtin_14"),
        Index("ix_products_tenant_status", "tenant_id", "status"),
        Index("ix_products_tenant_abc", "tenant_id", "abc_classification"),
        Index("ix_products_sanitary_registry", "sanitary_registry"),
    )

    def __repr__(self) -> str:
        return f"<Product {self.sku} - {self.name}>"


class ProductPackaging(WMSTenantBase):
    """
    Jerarquia de embalaje GS1 de un producto.
    Un producto tiene multiples niveles de embalaje:
      Nivel 1: Unidad (GTIN-13)
      Nivel 2: Caja (GTIN-14, contiene N unidades)
      Nivel 3: Palet (SSCC, contiene M cajas)
      Nivel 4: Contenedor (contiene P palets)
    """
    __tablename__ = "product_packagings"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False
    )

    level: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="Nivel en la jerarquia: 1=unidad, 2=caja, 3=palet, 4=contenedor"
    )
    name: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Nombre del nivel: Unidad, Caja, Palet, Contenedor"
    )
    gtin: Mapped[Optional[str]] = mapped_column(
        String(14), nullable=True,
        comment="GTIN de este nivel de embalaje"
    )
    quantity_per_parent: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Cantidad de unidades del nivel inferior que contiene"
    )
    quantity_base_units: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Cantidad total de unidades base en este nivel"
    )

    # Dimensiones del embalaje
    weight_kg: Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    length_cm: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    width_cm: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    height_cm: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    volume_m3: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))

    uom: Mapped[str] = mapped_column(String(20), default="UN")
    is_default_receiving: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="True si este nivel es el predeterminado para recepcion"
    )
    is_default_shipping: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="True si este nivel es el predeterminado para despacho"
    )

    # Relacion
    product: Mapped["Product"] = relationship(back_populates="packagings")

    __table_args__ = (
        UniqueConstraint("product_id", "level", name="uq_product_packagings_level"),
        Index("ix_product_packagings_gtin", "gtin"),
        Index("ix_product_packagings_product", "product_id"),
    )


# ─── LOCATION ─────────────────────────────────────────────────────────────────

class Zone(WMSTenantBase):
    """
    Zona = agrupacion logica de ubicaciones dentro de una bodega.
    Ejemplos: Zona A (alta rotacion), Zona Frio, Zona Hazmat, Zona Picking Fino.
    """
    __tablename__ = "zones"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    zone_type: Mapped[str] = mapped_column(
        String(30), default="storage",
        comment="storage | receiving | shipping | staging | quarantine | cold"
    )
    storage_condition: Mapped[StorageCondition] = mapped_column(
        Enum(StorageCondition), default=StorageCondition.AMBIENT
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    color_hex: Mapped[Optional[str]] = mapped_column(
        String(7), comment="Color para mapa de bodega (ej: #FF0000)"
    )
    settings: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    # Relaciones
    locations: Mapped[List["Location"]] = relationship(back_populates="zone")

    __table_args__ = (
        UniqueConstraint("warehouse_id", "code", name="uq_zones_warehouse_code"),
        Index("ix_zones_warehouse", "warehouse_id"),
    )


class Location(WMSTenantBase):
    """
    Location = Ubicacion fisica especifica dentro de la bodega.
    Estructura: Zona > Pasillo > Rack > Nivel > Posicion
    Codigo ejemplo: A-01-B-03-01 (Zona A, Pasillo 01, Rack B, Nivel 03, Posicion 01)

    Cada ubicacion tiene:
    - Capacidad (peso, volumen, unidades)
    - Restricciones (temperatura, peligrosidad, compatibilidad)
    - Estado (activa, bloqueada, mantenimiento)
    """
    __tablename__ = "locations"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zones.id", ondelete="SET NULL"),
        nullable=True
    )

    # Coordenadas en bodega
    code: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="Codigo legible de la ubicacion (ej: A-01-B-03-01)"
    )
    aisle: Mapped[Optional[str]] = mapped_column(
        String(10), comment="Pasillo (ej: 01, A, 01A)"
    )
    rack: Mapped[Optional[str]] = mapped_column(
        String(10), comment="Rack / Estante (ej: B, 02)"
    )
    level: Mapped[Optional[str]] = mapped_column(
        String(10), comment="Nivel / Piso (ej: 01, A, 1)"
    )
    position: Mapped[Optional[str]] = mapped_column(
        String(10), comment="Posicion dentro del nivel (ej: 01, 1)"
    )

    # Tipo y estado
    location_type: Mapped[LocationType] = mapped_column(
        Enum(LocationType), nullable=False, default=LocationType.STANDARD
    )
    status: Mapped[LocationStatus] = mapped_column(
        Enum(LocationStatus), nullable=False, default=LocationStatus.ACTIVE
    )

    # GS1
    sgln: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="SGLN (Serial GLN): identificador GS1 de la ubicacion"
    )

    # Capacidad
    max_weight_kg: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    max_volume_m3: Mapped[Optional[float]] = mapped_column(Numeric(8, 4))
    max_units: Mapped[Optional[int]] = mapped_column(Integer)
    max_pallets: Mapped[Optional[int]] = mapped_column(Integer)

    # Condiciones de almacenamiento
    storage_condition: Mapped[StorageCondition] = mapped_column(
        Enum(StorageCondition), default=StorageCondition.AMBIENT
    )
    min_temp_celsius: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    max_temp_celsius: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    allows_hazmat: Mapped[bool] = mapped_column(Boolean, default=False)
    allows_controlled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Restricciones
    allowed_product_families: Mapped[Optional[list]] = mapped_column(
        JSONB, comment="Lista de codigos de familia de productos permitidos (NULL = todos)"
    )
    blocked_reason: Mapped[Optional[str]] = mapped_column(
        Text, comment="Razon del bloqueo si status=blocked"
    )

    # Slotting / Optimizacion
    pick_sequence: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Orden de picking en la ruta optima de la bodega"
    )
    replenishment_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
        comment="Ubicacion de reserva/bulk para reponer este frente de picking"
    )
    is_pick_face: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="True si es frente de picking activo"
    )
    is_bulk: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="True si es ubicacion de reserva/bulk"
    )

    # Dimensiones fisicas de la ubicacion
    length_cm: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    width_cm: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    height_cm: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))

    # Relaciones
    zone: Mapped[Optional["Zone"]] = relationship(back_populates="locations")
    replenishment_source: Mapped[Optional["Location"]] = relationship(
        "Location", foreign_keys=[replenishment_location_id]
    )

    __table_args__ = (
        UniqueConstraint("warehouse_id", "code", name="uq_locations_warehouse_code"),
        Index("ix_locations_warehouse_zone", "warehouse_id", "zone_id"),
        Index("ix_locations_warehouse_status", "warehouse_id", "status"),
        Index("ix_locations_tenant_warehouse", "tenant_id", "warehouse_id"),
        Index("ix_locations_pick_sequence", "warehouse_id", "pick_sequence"),
        Index("ix_locations_type", "warehouse_id", "location_type"),
    )

    def __repr__(self) -> str:
        return f"<Location {self.code} [{self.status}]>"


# ─── SUPPLIER ─────────────────────────────────────────────────────────────────

class Supplier(WMSTenantBase):
    """
    Supplier = Proveedor de productos o servicios del tenant.
    Incluye SLA contractual, historial de calidad e integracion con ANA (Panama).
    """
    __tablename__ = "suppliers"

    # Identificacion
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    legal_name: Mapped[Optional[str]] = mapped_column(String(300))
    ruc: Mapped[Optional[str]] = mapped_column(
        String(20), comment="RUC panamenio o NIT del pais de origen"
    )
    tax_id_country: Mapped[Optional[str]] = mapped_column(
        String(2), default="PA",
        comment="Pais del RUC/NIT"
    )

    # Clasificacion
    status: Mapped[SupplierStatus] = mapped_column(
        Enum(SupplierStatus), default=SupplierStatus.ACTIVE
    )
    supplier_type: Mapped[str] = mapped_column(
        String(30), default="product",
        comment="product | service | 3pl | carrier | customs_agent"
    )
    industry: Mapped[Optional[IndustryType]] = mapped_column(Enum(IndustryType))

    # Contacto principal
    contact_name: Mapped[Optional[str]] = mapped_column(String(200))
    contact_email: Mapped[Optional[str]] = mapped_column(String(200))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(30))
    emergency_phone: Mapped[Optional[str]] = mapped_column(String(30))

    # Direccion
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    country: Mapped[Optional[str]] = mapped_column(String(2))

    # SLA contractual
    lead_time_days: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Lead time de entrega en dias habiles"
    )
    sla_on_time_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), comment="SLA de entrega a tiempo contractual (%)"
    )
    sla_quality_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), comment="SLA de calidad contractual (%)"
    )
    payment_terms_days: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Dias de credito (ej: 30, 60, 90)"
    )

    # Metricas reales (calculadas)
    actual_on_time_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    actual_quality_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    total_incidents: Mapped[int] = mapped_column(Integer, default=0)

    # Aduanas Panama
    is_importer: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="True si este proveedor realiza importaciones para el tenant"
    )
    customs_agent_code: Mapped[Optional[str]] = mapped_column(
        String(50), comment="Codigo de agente aduanero ANA (si aplica)"
    )

    # Certificaciones
    certifications: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        comment="Certificaciones: ISO9001, HACCP, GDP, BPM, etc. con fechas"
    )

    # GS1
    gln: Mapped[Optional[str]] = mapped_column(String(13))

    custom_attributes: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_suppliers_tenant_code"),
        Index("ix_suppliers_tenant_status", "tenant_id", "status"),
        Index("ix_suppliers_tenant_ruc", "tenant_id", "ruc"),
    )

    def __repr__(self) -> str:
        return f"<Supplier {self.code} - {self.name}>"


# ─── CUSTOMER ─────────────────────────────────────────────────────────────────

class Customer(WMSTenantBase):
    """
    Customer = Cliente al que se despachan pedidos.
    Puede ser: retail, distribuidor, eCommerce, gobierno, o planta interna.
    """
    __tablename__ = "customers"

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    legal_name: Mapped[Optional[str]] = mapped_column(String(300))
    ruc: Mapped[Optional[str]] = mapped_column(String(20))
    dv: Mapped[Optional[str]] = mapped_column(String(2))

    customer_type: Mapped[CustomerType] = mapped_column(
        Enum(CustomerType), default=CustomerType.RETAIL
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Contacto
    contact_name: Mapped[Optional[str]] = mapped_column(String(200))
    contact_email: Mapped[Optional[str]] = mapped_column(String(200))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(30))

    # Direccion de entrega principal
    delivery_address: Mapped[Optional[str]] = mapped_column(Text)
    delivery_city: Mapped[Optional[str]] = mapped_column(String(100))
    delivery_province: Mapped[Optional[str]] = mapped_column(String(100))
    delivery_country: Mapped[str] = mapped_column(String(2), default="PA")
    delivery_instructions: Mapped[Optional[str]] = mapped_column(Text)

    # SLA
    sla_lead_time_hours: Mapped[Optional[int]] = mapped_column(
        Integer, comment="Horas de plazo de entrega contractual"
    )
    sla_otif_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), comment="SLA OTIF contractual (%)"
    )

    # eCommerce
    external_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="ID en plataforma eCommerce externa (Shopify, VTEX, etc.)"
    )
    ecommerce_platform: Mapped[Optional[str]] = mapped_column(
        String(50), comment="shopify | vtex | woocommerce | magento | mercadolibre"
    )

    # GS1
    gln: Mapped[Optional[str]] = mapped_column(String(13))

    # Facturacion
    billing_address: Mapped[Optional[str]] = mapped_column(Text)
    requires_electronic_invoice: Mapped[bool] = mapped_column(Boolean, default=True)
    tax_exemption: Mapped[Optional[str]] = mapped_column(
        String(100), comment="Numero de exoneracion si el cliente esta exento de ITBMS"
    )

    credit_limit: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    payment_terms_days: Mapped[Optional[int]] = mapped_column(Integer)

    custom_attributes: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_customers_tenant_code"),
        Index("ix_customers_tenant_type", "tenant_id", "customer_type"),
        Index("ix_customers_tenant_ruc", "tenant_id", "ruc"),
        Index("ix_customers_external_id", "external_id", "ecommerce_platform"),
    )

    def __repr__(self) -> str:
        return f"<Customer {self.code} - {self.name}>"


# ─── CARRIER ──────────────────────────────────────────────────────────────────

class Carrier(WMSTenantBase):
    """
    Carrier = Transportista o agencia de transporte.
    Puede ser: transportista local, courier internacional, operador logistico.
    """
    __tablename__ = "carriers"

    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    carrier_type: Mapped[str] = mapped_column(
        String(30), default="courier",
        comment="courier | ltl | ftl | last_mile | maritime | air | customs_agent"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Integracion API
    api_provider: Mapped[Optional[str]] = mapped_column(
        String(50),
        comment="Proveedor API: dhl | fedex | correos_panama | custom"
    )
    api_url: Mapped[Optional[str]] = mapped_column(String(500))
    api_credentials: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        comment="Credenciales API (cifradas via Vault, no en texto plano)"
    )
    tracking_url_template: Mapped[Optional[str]] = mapped_column(
        String(500),
        comment="Template URL de tracking: https://track.dhl.com/{tracking_number}"
    )

    # Tarifas (referencia)
    rate_table: Mapped[Optional[dict]] = mapped_column(
        JSONB, comment="Tabla de tarifas por zona y peso"
    )

    contact_email: Mapped[Optional[str]] = mapped_column(String(200))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(30))

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_carriers_tenant_code"),
        Index("ix_carriers_tenant", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<Carrier {self.code} - {self.name}>"
