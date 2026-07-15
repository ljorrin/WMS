"""
WMS Panamá — Schemas Pydantic: Hardware RFID/RF — Fase 2
============================================================
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Readers ────────────────────────────────────────────────────────────────────
class RfidReaderCreate(BaseModel):
    warehouse_id: uuid.UUID
    code: str = Field(..., max_length=30)
    name: str = Field(..., max_length=120)
    vendor: Optional[str] = Field(None, max_length=30, description="zebra | impinj | honeywell | alien | otro")
    model: Optional[str] = Field(None, max_length=60)
    ip_address: Optional[str] = Field(None, max_length=45)
    port: int = Field(5084, ge=1, le=65535, description="Puerto LLRP (5084 = default EPCglobal).")
    notes: Optional[str] = Field(None, max_length=255)


class RfidReaderResponse(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    code: str
    name: str
    vendor: Optional[str] = None
    model: Optional[str] = None
    ip_address: Optional[str] = None
    port: int
    protocol: str
    status: str
    last_seen_at: Optional[datetime] = None
    notes: Optional[str] = None
    model_config = {"from_attributes": True}


# ── Antenas ────────────────────────────────────────────────────────────────────
class RfidAntennaCreate(BaseModel):
    antenna_number: int = Field(..., ge=1, le=32, description="Puerto físico en el reader.")
    name: str = Field(..., max_length=120)
    location_id: Optional[uuid.UUID] = Field(None, description="Ubicación física que cubre (dock door, frente de picking).")
    zone_id: Optional[uuid.UUID] = None
    transmit_power_dbm: Optional[float] = Field(None, ge=0, le=33)


class RfidAntennaResponse(BaseModel):
    id: uuid.UUID
    reader_id: uuid.UUID
    antenna_number: int
    name: str
    location_id: Optional[uuid.UUID] = None
    zone_id: Optional[uuid.UUID] = None
    transmit_power_dbm: Optional[float] = None
    is_active: bool
    model_config = {"from_attributes": True}


# ── Tag reads (ingesta desde el gateway LLRP / simulador) ─────────────────────
class RfidTagReadIngest(BaseModel):
    """
    Payload que el gateway LLRP (o el simulador de hardware) envía por cada
    lectura de tag. `epc_hex` es el dato crudo tal como lo entrega el reader
    (24 caracteres hex = 96 bits, EPC Gen2).
    """
    reader_code: str = Field(..., max_length=30, description="Código del reader que reportó la lectura.")
    antenna_number: Optional[int] = Field(None, ge=1, le=32, description="Puerto de antena que detectó el tag.")
    epc_hex: str = Field(..., min_length=24, max_length=24)
    rssi_dbm: Optional[float] = Field(None, description="Intensidad de señal reportada por el reader.")
    read_at: Optional[datetime] = Field(None, description="Timestamp del reader; si se omite, se usa la hora de recepción.")


class RfidTagReadResponse(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    reader_id: uuid.UUID
    antenna_id: Optional[uuid.UUID] = None
    epc_hex: str
    epc_scheme: str
    gtin: Optional[str] = None
    sscc: Optional[str] = None
    serial: Optional[int] = None
    product_id: Optional[uuid.UUID] = None
    rssi_dbm: Optional[float] = None
    read_at: datetime
    processed: bool
    process_notes: Optional[str] = None
    model_config = {"from_attributes": True}


# ── Etiquetas ZPL ──────────────────────────────────────────────────────────────
class ZplPalletLabelRequest(BaseModel):
    sscc: str = Field(..., min_length=18, max_length=18, description="SSCC de 18 dígitos del pallet/bulto.")
    company_prefix: str = Field(..., min_length=6, max_length=12)
    description: Optional[str] = Field(None, max_length=60, description="Texto legible (p. ej. nombre del producto).")
    encode_rfid: bool = Field(False, description="Si True, incluye el comando ^RFW para grabar el EPC en el inlay RFID.")


class ZplLabelResponse(BaseModel):
    zpl: str
    epc_hex: Optional[str] = None
    epc_uri: Optional[str] = None
