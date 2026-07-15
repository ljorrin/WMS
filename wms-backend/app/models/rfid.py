"""
WMS Panamá — Hardware RFID/RF (Fase 2 del plan de implementación)
====================================================================
Modela la topología física real de una instalación RFID EPC Gen2 (UHF) tal
como se despliega en un CD: un READER fijo (p. ej. Zebra FX9600, Impinj
Speedway) por dock/portal, con varias ANTENAS conectadas (cada una cubre una
puerta de andén, un túnel de conveyor o un frente de picking), y el log de
TAG READS que esas antenas capturan.

El reader habla LLRP (Low Level Reader Protocol, el estándar EPCglobal/GS1
para readers RFID fijos) con un gateway/middleware fuera de este proceso
(p. ej. Zebra IoT Connector, o un cliente LLRP dedicado) — FastAPI no
implementa el protocolo binario LLRP en el request/response de una API HTTP;
en su lugar, ese gateway hace POST de cada lectura decodificada a
`RfidService.ingest_tag_read`. Ver `scripts/rfid_reader_simulator.py` para
simular ese gateway sin hardware real.

Convenciones del proyecto: columnas String para tipo/estado (sin enums
nativos), igual que YMS/Labor/Slotting. Multitenancy vía tenant_id.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import WMSTenantBase

READER_STATUSES = ("active", "inactive", "offline")
READER_PROTOCOLS = ("LLRP",)  # estándar EPCglobal/GS1 para readers fijos
EPC_SCHEMES = ("sgtin96", "sscc96", "unknown")


class RfidReader(WMSTenantBase):
    """Reader RFID fijo (p. ej. portal de dock, túnel de conveyor)."""
    __tablename__ = "rfid_readers"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False, comment="Código interno único por bodega.")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    vendor: Mapped[Optional[str]] = mapped_column(
        String(30), comment="zebra | impinj | honeywell | alien | otro",
    )
    model: Mapped[Optional[str]] = mapped_column(String(60))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    port: Mapped[int] = mapped_column(Integer, default=5084, comment="Puerto LLRP (5084 = default EPCglobal).")
    protocol: Mapped[str] = mapped_column(String(10), default="LLRP")
    status: Mapped[str] = mapped_column(String(20), default="inactive", comment="active | inactive | offline")
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), comment="Último heartbeat/lectura recibida del gateway LLRP.",
    )
    notes: Mapped[Optional[str]] = mapped_column(String(255))

    __table_args__ = (
        UniqueConstraint("tenant_id", "warehouse_id", "code", name="uq_rfid_reader_code"),
        Index("ix_rfid_readers_warehouse", "warehouse_id", "status"),
    )


class RfidAntenna(WMSTenantBase):
    """
    Antena física conectada a un puerto de un RfidReader. Cada antena cubre
    una ubicación/zona física (p. ej. la antena del puerto 1 apunta a la
    puerta de andén D-01) — esto permite atribuir automáticamente cada
    lectura de tag a una ubicación sin que el operario escanee nada.
    """
    __tablename__ = "rfid_antennas"

    reader_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfid_readers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    antenna_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Número de puerto físico en el reader (1-N).",
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True,
        comment="Ubicación física que cubre esta antena (dock door, frente de picking, etc).",
    )
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zones.id", ondelete="SET NULL"), nullable=True,
    )
    transmit_power_dbm: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), comment="Potencia de transmisión configurada (dBm).",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("reader_id", "antenna_number", name="uq_rfid_antenna_port"),
    )


class RfidTagRead(WMSTenantBase):
    """
    Evento de lectura de un tag RFID (una fila por cada EPC leído). El
    volumen puede ser alto (una antena en un portal puede leer el mismo tag
    decenas de veces mientras el pallet cruza) — `processed` marca si la
    lógica de negocio (p. ej. confirmar llegada de ASN, completar putaway)
    ya consumió esta lectura, para evitar reprocesar duplicados.
    """
    __tablename__ = "rfid_tag_reads"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    reader_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfid_readers.id", ondelete="CASCADE"), nullable=False,
    )
    antenna_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfid_antennas.id", ondelete="SET NULL"), nullable=True,
    )

    epc_hex: Mapped[str] = mapped_column(String(24), nullable=False, index=True, comment="EPC crudo leído del tag (24 hex = 96 bits).")
    epc_scheme: Mapped[str] = mapped_column(String(10), default="unknown", comment="sgtin96 | sscc96 | unknown")
    gtin: Mapped[Optional[str]] = mapped_column(String(14))
    sscc: Mapped[Optional[str]] = mapped_column(String(18))
    serial: Mapped[Optional[int]] = mapped_column(BigInteger)

    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True,
        comment="Producto resuelto por GTIN (si el EPC es SGTIN-96 y el GTIN existe en el catálogo).",
    )
    rssi_dbm: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), comment="Intensidad de señal reportada por el reader (dBm).")
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    process_notes: Mapped[Optional[str]] = mapped_column(String(255))

    __table_args__ = (
        Index("ix_rfid_tag_reads_warehouse_time", "warehouse_id", "read_at"),
        Index("ix_rfid_tag_reads_epc", "tenant_id", "epc_hex"),
        Index("ix_rfid_tag_reads_unprocessed", "warehouse_id", "processed"),
    )
