"""
WMS Panamá — Hardware RFID/RF contra PostgreSQL real (Fase 2 del plan de implementación)
==========================================================================================
Registra un reader + antena (topología física simulada, sin hardware real
disponible), ingiere lecturas de tags EPC SGTIN-96 (con resolución de
producto por GTIN) y SSCC-96, y verifica el dashboard de KPIs.

Se salta automáticamente si no hay PostgreSQL de test accesible (ver conftest.py).
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio

from app.core.epc import encode_sgtin96, encode_sscc96
from app.core.exceptions import RfidDeviceError, RfidServiceError
from app.core.gs1 import generate_sscc
from app.models.core import Company, Tenant, Warehouse
from app.models.master_data import Product
from app.services.rfid_service import RfidService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

COMPANY_PREFIX = "0614141"


def _valid_gtin13(company_prefix: str, item_ref: str) -> str:
    from app.core.gs1 import gs1_check_digit
    body = "0" + company_prefix + item_ref
    return body + str(gs1_check_digit(body))


@pytest_asyncio.fixture
async def rfid_seed(db):
    tenant = Tenant(id=uuid4(), name="RFID S.A.", slug=f"rfid-{uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()

    company = Company(id=uuid4(), tenant_id=tenant.id, name="Compañía RFID")
    warehouse = Warehouse(
        id=uuid4(), tenant_id=tenant.id, company_id=company.id, code="WH-RFID", name="Almacén RFID",
    )
    db.add_all([company, warehouse])
    await db.flush()

    gtin14 = _valid_gtin13(COMPANY_PREFIX, "12345")  # 14 dígitos: indicador '0' + 13
    product = Product(
        id=uuid4(), tenant_id=tenant.id, sku=f"SKU-{uuid4().hex[:6]}", name="Producto RFID",
        gtin_13=gtin14[1:],  # el catálogo real guarda el GTIN-13 (sin el indicador)
    )
    db.add(product)
    await db.flush()

    return SimpleNamespace(db=db, tenant_id=tenant.id, warehouse_id=warehouse.id, product_id=product.id, gtin=gtin14)


async def test_registrar_reader_y_antena(rfid_seed):
    s = rfid_seed
    svc = RfidService(db=s.db)

    reader = await svc.register_reader(s.tenant_id, dict(
        warehouse_id=s.warehouse_id, code="READER-01", name="Portal Dock 1", vendor="zebra",
    ))
    assert reader.status == "inactive"  # inactivo hasta la primera lectura

    antenna = await svc.register_antenna(s.tenant_id, reader.id, dict(antenna_number=1, name="Antena 1"))
    assert antenna.reader_id == reader.id

    # duplicados deben rechazarse
    with pytest.raises(RfidDeviceError):
        await svc.register_reader(s.tenant_id, dict(warehouse_id=s.warehouse_id, code="READER-01", name="Dup"))
    with pytest.raises(RfidDeviceError):
        await svc.register_antenna(s.tenant_id, reader.id, dict(antenna_number=1, name="Dup"))

    readers = await svc.list_readers(s.tenant_id, s.warehouse_id)
    assert len(readers) == 1
    antennas = await svc.list_antennas(s.tenant_id, reader.id)
    assert len(antennas) == 1


async def test_ingesta_sgtin_resuelve_producto(rfid_seed):
    s = rfid_seed
    svc = RfidService(db=s.db)
    reader = await svc.register_reader(s.tenant_id, dict(warehouse_id=s.warehouse_id, code="READER-02", name="Portal 2"))
    await svc.register_antenna(s.tenant_id, reader.id, dict(antenna_number=1, name="Antena 1"))

    epc = encode_sgtin96(s.gtin, company_prefix=COMPANY_PREFIX, serial=42, filter_value=2)
    tag_read = await svc.ingest_tag_read(s.tenant_id, dict(
        reader_code="READER-02", antenna_number=1, epc_hex=epc.epc_hex, rssi_dbm=-55.3,
    ))

    assert tag_read.epc_scheme == "sgtin96"
    assert tag_read.gtin == s.gtin.zfill(14)
    assert tag_read.serial == 42
    assert tag_read.product_id == s.product_id
    assert tag_read.antenna_id is not None
    assert tag_read.warehouse_id == s.warehouse_id

    reader_after = await svc._get_reader(s.tenant_id, reader.id)
    assert reader_after.status == "active"
    assert reader_after.last_seen_at is not None


async def test_ingesta_sscc_sin_producto(rfid_seed):
    s = rfid_seed
    svc = RfidService(db=s.db)
    reader = await svc.register_reader(s.tenant_id, dict(warehouse_id=s.warehouse_id, code="READER-03", name="Portal 3"))

    sscc = generate_sscc(COMPANY_PREFIX, serial=999)
    epc = encode_sscc96(sscc, company_prefix=COMPANY_PREFIX, filter_value=6)
    tag_read = await svc.ingest_tag_read(s.tenant_id, dict(
        reader_code="READER-03", epc_hex=epc.epc_hex, rssi_dbm=-60.0,
    ))

    assert tag_read.epc_scheme == "sscc96"
    assert tag_read.sscc == sscc
    assert tag_read.product_id is None
    assert tag_read.antenna_id is None  # no se especificó antena


async def test_ingesta_epc_no_decodificable_no_falla(rfid_seed):
    """Un EPC con header desconocido no debe romper la ingesta: se guarda como 'unknown'."""
    s = rfid_seed
    svc = RfidService(db=s.db)
    reader = await svc.register_reader(s.tenant_id, dict(warehouse_id=s.warehouse_id, code="READER-04", name="Portal 4"))

    tag_read = await svc.ingest_tag_read(s.tenant_id, dict(
        reader_code="READER-04", epc_hex="FF" + "00" * 11,
    ))
    assert tag_read.epc_scheme == "unknown"
    assert tag_read.gtin is None and tag_read.sscc is None


async def test_ingesta_reader_no_registrado_falla(rfid_seed):
    s = rfid_seed
    svc = RfidService(db=s.db)
    with pytest.raises(RfidServiceError):
        await svc.ingest_tag_read(s.tenant_id, dict(reader_code="NO-EXISTE", epc_hex="30" + "00" * 11))


async def test_dashboard_metrics(rfid_seed):
    s = rfid_seed
    svc = RfidService(db=s.db)
    reader = await svc.register_reader(s.tenant_id, dict(warehouse_id=s.warehouse_id, code="READER-05", name="Portal 5"))
    sscc = generate_sscc(COMPANY_PREFIX, serial=1)
    epc = encode_sscc96(sscc, company_prefix=COMPANY_PREFIX)
    await svc.ingest_tag_read(s.tenant_id, dict(reader_code="READER-05", epc_hex=epc.epc_hex))

    metrics = await svc.get_dashboard_metrics(s.tenant_id, s.warehouse_id)
    assert metrics["reads_today"] >= 1
    assert metrics["readers_by_status"].get("active", 0) >= 1
