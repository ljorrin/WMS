"""
WMS Panamá — Servicio de Hardware RFID/RF — Fase 2 del plan de implementación
================================================================================
Registro de readers/antenas físicos e ingesta de lecturas de tags EPC Gen2.

El reader (Zebra FX9600, Impinj Speedway, etc.) habla LLRP con un
gateway/middleware fuera de este proceso — este servicio NO implementa el
protocolo LLRP binario; expone el punto de ingesta que ese gateway (o
`scripts/rfid_reader_simulator.py` para pruebas sin hardware) llama por cada
tag leído: decodifica el EPC (SGTIN-96/SSCC-96), resuelve el producto por
GTIN cuando aplica, atribuye la lectura a la ubicación física de la antena, y
persiste el evento.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.epc import EpcEncodingError, decode_epc96
from app.core.exceptions import RfidDeviceError, RfidServiceError
from app.models.master_data import Product
from app.models.rfid import RfidAntenna, RfidReader, RfidTagRead


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RfidService:
    """Servicio de hardware RFID/RF."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ══════════════════════════════════════════════════════════════════════════
    # READERS
    # ══════════════════════════════════════════════════════════════════════════

    async def register_reader(
        self, tenant_id: uuid.UUID, data: dict, user_id: Optional[uuid.UUID] = None
    ) -> RfidReader:
        existing = (await self.db.execute(
            select(RfidReader).where(and_(
                RfidReader.tenant_id == tenant_id,
                RfidReader.warehouse_id == data["warehouse_id"],
                RfidReader.code == data["code"],
                RfidReader.deleted_at.is_(None),
            ))
        )).scalar_one_or_none()
        if existing:
            raise RfidDeviceError(f"Ya existe un reader con código '{data['code']}' en esa bodega.")

        reader = RfidReader(
            id=uuid.uuid4(), tenant_id=tenant_id, created_by_id=user_id,
            status="inactive", **data,
        )
        self.db.add(reader)
        await self.db.commit()
        await self.db.refresh(reader)
        return reader

    async def update_reader(
        self, tenant_id: uuid.UUID, reader_id: uuid.UUID, data: dict,
    ) -> RfidReader:
        reader = await self._get_reader(tenant_id, reader_id)
        for field, value in data.items():
            if value is not None:
                setattr(reader, field, value)
        await self.db.commit()
        await self.db.refresh(reader)
        return reader

    async def list_readers(
        self, tenant_id: uuid.UUID, warehouse_id: Optional[uuid.UUID] = None
    ) -> list[RfidReader]:
        conditions = [RfidReader.tenant_id == tenant_id, RfidReader.deleted_at.is_(None)]
        if warehouse_id:
            conditions.append(RfidReader.warehouse_id == warehouse_id)
        rows = (await self.db.execute(
            select(RfidReader).where(and_(*conditions)).order_by(RfidReader.code)
        )).scalars().all()
        return list(rows)

    async def _get_reader(self, tenant_id: uuid.UUID, reader_id: uuid.UUID) -> RfidReader:
        reader = (await self.db.execute(
            select(RfidReader).where(and_(
                RfidReader.id == reader_id, RfidReader.tenant_id == tenant_id,
                RfidReader.deleted_at.is_(None),
            ))
        )).scalar_one_or_none()
        if not reader:
            raise RfidServiceError("Reader RFID no encontrado.")
        return reader

    # ══════════════════════════════════════════════════════════════════════════
    # ANTENAS
    # ══════════════════════════════════════════════════════════════════════════

    async def register_antenna(
        self, tenant_id: uuid.UUID, reader_id: uuid.UUID, data: dict,
    ) -> RfidAntenna:
        await self._get_reader(tenant_id, reader_id)  # valida que el reader exista y sea del tenant

        existing = (await self.db.execute(
            select(RfidAntenna).where(and_(
                RfidAntenna.reader_id == reader_id,
                RfidAntenna.antenna_number == data["antenna_number"],
                RfidAntenna.deleted_at.is_(None),
            ))
        )).scalar_one_or_none()
        if existing:
            raise RfidDeviceError(
                f"El puerto de antena {data['antenna_number']} ya está registrado en este reader."
            )

        antenna = RfidAntenna(id=uuid.uuid4(), tenant_id=tenant_id, reader_id=reader_id, **data)
        self.db.add(antenna)
        await self.db.commit()
        await self.db.refresh(antenna)
        return antenna

    async def list_antennas(self, tenant_id: uuid.UUID, reader_id: uuid.UUID) -> list[RfidAntenna]:
        rows = (await self.db.execute(
            select(RfidAntenna).where(and_(
                RfidAntenna.tenant_id == tenant_id, RfidAntenna.reader_id == reader_id,
                RfidAntenna.deleted_at.is_(None),
            )).order_by(RfidAntenna.antenna_number)
        )).scalars().all()
        return list(rows)

    # ══════════════════════════════════════════════════════════════════════════
    # INGESTA DE LECTURAS (desde el gateway LLRP / simulador)
    # ══════════════════════════════════════════════════════════════════════════

    async def ingest_tag_read(self, tenant_id: uuid.UUID, data: dict) -> RfidTagRead:
        """
        `data`: dict con reader_code, antenna_number (opcional), epc_hex,
        rssi_dbm (opcional), read_at (opcional).
        """
        reader = (await self.db.execute(
            select(RfidReader).where(and_(
                RfidReader.tenant_id == tenant_id, RfidReader.code == data["reader_code"],
                RfidReader.deleted_at.is_(None),
            ))
        )).scalar_one_or_none()
        if not reader:
            raise RfidServiceError(f"Reader con código '{data['reader_code']}' no registrado.")

        antenna = None
        if data.get("antenna_number") is not None:
            antenna = (await self.db.execute(
                select(RfidAntenna).where(and_(
                    RfidAntenna.reader_id == reader.id,
                    RfidAntenna.antenna_number == data["antenna_number"],
                    RfidAntenna.deleted_at.is_(None),
                ))
            )).scalar_one_or_none()

        epc_hex = data["epc_hex"].strip().upper()
        epc_scheme = "unknown"
        gtin = sscc = None
        serial = None
        product_id = None

        try:
            decoded = decode_epc96(epc_hex)
        except EpcEncodingError:
            decoded = None

        if decoded is not None:
            if hasattr(decoded, "gtin"):  # SgtinEpc
                epc_scheme = "sgtin96"
                gtin = decoded.gtin
                serial = decoded.serial
                # gtin es siempre GTIN-14 (indicador + 13 dígitos); el GTIN-13
                # equivalente se obtiene quitando exactamente el primer
                # dígito (el indicador) — NUNCA con lstrip("0"), que quita
                # tantos ceros como haya y corrompe el valor si el Company
                # Prefix también empieza en cero (bug real encontrado
                # ejecutando el test de integración de Fase 2).
                product = (await self.db.execute(
                    select(Product).where(and_(
                        Product.tenant_id == tenant_id,
                        or_(Product.gtin_14 == gtin, Product.gtin_13 == gtin[1:]),
                    ))
                )).scalar_one_or_none()
                if product:
                    product_id = product.id
            else:  # SsccEpc
                epc_scheme = "sscc96"
                sscc = decoded.sscc

        tag_read = RfidTagRead(
            id=uuid.uuid4(), tenant_id=tenant_id, warehouse_id=reader.warehouse_id,
            reader_id=reader.id, antenna_id=antenna.id if antenna else None,
            epc_hex=epc_hex, epc_scheme=epc_scheme, gtin=gtin, sscc=sscc, serial=serial,
            product_id=product_id, rssi_dbm=data.get("rssi_dbm"),
            read_at=data.get("read_at") or _now(),
        )
        self.db.add(tag_read)

        reader.last_seen_at = _now()
        reader.status = "active"

        await self.db.commit()
        await self.db.refresh(tag_read)
        return tag_read

    async def list_tag_reads(
        self, tenant_id: uuid.UUID, warehouse_id: Optional[uuid.UUID] = None,
        reader_id: Optional[uuid.UUID] = None, processed: Optional[bool] = None,
        offset: int = 0, limit: int = 50,
    ) -> tuple[list[RfidTagRead], int]:
        conditions = [RfidTagRead.tenant_id == tenant_id]
        if warehouse_id:
            conditions.append(RfidTagRead.warehouse_id == warehouse_id)
        if reader_id:
            conditions.append(RfidTagRead.reader_id == reader_id)
        if processed is not None:
            conditions.append(RfidTagRead.processed == processed)

        total = (await self.db.execute(
            select(func.count(RfidTagRead.id)).where(and_(*conditions))
        )).scalar_one()
        rows = (await self.db.execute(
            select(RfidTagRead).where(and_(*conditions))
            .order_by(RfidTagRead.read_at.desc()).offset(offset).limit(limit)
        )).scalars().all()
        return list(rows), total

    async def clear_tag_reads(
        self, tenant_id: uuid.UUID, warehouse_id: Optional[uuid.UUID] = None,
    ) -> int:
        """Borra (definitivamente) el historial de lecturas — útil para limpiar datos de prueba."""
        from sqlalchemy import delete

        conditions = [RfidTagRead.tenant_id == tenant_id]
        if warehouse_id:
            conditions.append(RfidTagRead.warehouse_id == warehouse_id)
        result = await self.db.execute(delete(RfidTagRead).where(and_(*conditions)))
        await self.db.commit()
        return result.rowcount or 0

    # ══════════════════════════════════════════════════════════════════════════
    # DASHBOARD
    # ══════════════════════════════════════════════════════════════════════════

    async def get_dashboard_metrics(
        self, tenant_id: uuid.UUID, warehouse_id: Optional[uuid.UUID] = None,
    ) -> dict:
        reader_conditions = [RfidReader.tenant_id == tenant_id, RfidReader.deleted_at.is_(None)]
        if warehouse_id:
            reader_conditions.append(RfidReader.warehouse_id == warehouse_id)

        readers_by_status: dict[str, int] = {}
        for row in (await self.db.execute(
            select(RfidReader.status, func.count(RfidReader.id))
            .where(and_(*reader_conditions)).group_by(RfidReader.status)
        )).all():
            readers_by_status[row[0]] = row[1]

        read_conditions = [RfidTagRead.tenant_id == tenant_id]
        if warehouse_id:
            read_conditions.append(RfidTagRead.warehouse_id == warehouse_id)
        since_24h = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        reads_today = (await self.db.execute(
            select(func.count(RfidTagRead.id)).where(and_(
                *read_conditions, RfidTagRead.read_at >= since_24h,
            ))
        )).scalar_one()
        # Un mismo tag suele leerse muchas veces (varias antenas o pasadas
        # repetidas) — esto cuenta EPCs (códigos) distintos, no lecturas crudas.
        unique_epcs_today = (await self.db.execute(
            select(func.count(func.distinct(RfidTagRead.epc_hex))).where(and_(
                *read_conditions, RfidTagRead.read_at >= since_24h,
            ))
        )).scalar_one()
        unprocessed = (await self.db.execute(
            select(func.count(RfidTagRead.id)).where(and_(
                *read_conditions, RfidTagRead.processed.is_(False),
            ))
        )).scalar_one()

        return {
            "readers_by_status": readers_by_status,
            "reads_today": reads_today,
            "unique_epcs_today": unique_epcs_today,
            "unprocessed_reads": unprocessed,
        }
