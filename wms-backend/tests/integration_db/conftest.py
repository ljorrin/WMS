"""
WMS Panamá — Tests de integración con PostgreSQL REAL
======================================================
Estos tests ejercen el stack repo + service + modelo contra una base de datos
PostgreSQL real (no mocks, no SQLite). Son la "red de seguridad" que faltaba:
detectan desalineaciones schema↔modelo, tipos ENUM, NOT NULL y FKs que los
tests unitarios (con mocks) no ven.

REQUISITO: una BD PostgreSQL accesible. Configúrala con la variable de entorno
`WMS_TEST_DATABASE_URL` (driver asyncpg). Ejemplo con el docker-compose del repo:

    docker compose up -d db
    export WMS_TEST_DATABASE_URL="postgresql+asyncpg://wms_user:wms_secret@localhost:5432/wms_test"
    pytest tests/integration_db -v

Si no hay PostgreSQL accesible, TODO el módulo se SALTA automáticamente
(no rompe la suite). El esquema se crea con metadata.create_all al inicio y se
elimina al final; cada test corre en una transacción que se revierte.
"""

from __future__ import annotations

import os
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio

# Entorno mínimo para importar la app/config sin tocar la BD de producción
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_testing_only_32_chars_long")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

_TEST_DB_URL = (
    os.environ.get("WMS_TEST_DATABASE_URL")
    or os.environ.get("TEST_DATABASE_URL")
    or ""
)

# Solo corremos si hay una URL PostgreSQL explícita (asyncpg)
_HAS_PG = _TEST_DB_URL.startswith("postgresql")

# La app exige DATABASE_URL/SYNC para importar settings; usar la de test o dummies
os.environ.setdefault("DATABASE_URL", _TEST_DB_URL or "postgresql+asyncpg://u:p@localhost/db")
os.environ.setdefault(
    "DATABASE_SYNC_URL",
    _TEST_DB_URL.replace("+asyncpg", "+psycopg2") if _TEST_DB_URL else "postgresql+psycopg2://u:p@localhost/db",
)

pytestmark = pytest.mark.integration

# Importar modelos + metadata
import app.models  # noqa: E402,F401
import app.models.outbound  # noqa: E402,F401
import app.models.ai  # noqa: E402,F401
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from app.models.base import WMSBase  # noqa: E402
from app.models.core import Company, Tenant, User, Warehouse  # noqa: E402
from app.models.master_data import Location, Product, Supplier  # noqa: E402
from app.models.inventory import InventoryLevel  # noqa: E402


@pytest_asyncio.fixture
async def engine():
    """Motor + esquema por test (función) para evitar problemas de event loop
    entre fixtures de distinto scope en pytest-asyncio."""
    if not _HAS_PG:
        pytest.skip(
            "No hay PostgreSQL de test. Define WMS_TEST_DATABASE_URL "
            "(postgresql+asyncpg://...) para ejecutar estos tests."
        )
    eng = create_async_engine(_TEST_DB_URL, echo=False)
    # Verificar conectividad antes de crear el esquema; si no, saltar todo el módulo
    try:
        async with eng.connect() as conn:  # noqa: F841
            pass
    except Exception as exc:  # asyncpg / socket / auth
        await eng.dispose()
        pytest.skip(f"PostgreSQL de test no accesible: {exc}")

    async with eng.begin() as conn:
        await conn.run_sync(WMSBase.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(WMSBase.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    """Sesión transaccional: se revierte al terminar cada test (aislamiento)."""
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture
async def seed(db: AsyncSession):
    """
    Crea el grafo mínimo de datos maestros y devuelve sus IDs.
    Todo bajo un tenant único por test (evita colisiones de unique constraints).
    """
    tenant = Tenant(id=uuid4(), name="Integración S.A.", slug=f"int-{uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()

    user = User(
        id=uuid4(), tenant_id=tenant.id, email=f"it-{uuid4().hex[:8]}@wms.pa",
        first_name="Inte", last_name="Gración", is_superadmin=True,
    )
    company = Company(id=uuid4(), tenant_id=tenant.id, name="Compañía Test")
    db.add_all([user, company])
    await db.flush()

    warehouse = Warehouse(
        id=uuid4(), tenant_id=tenant.id, company_id=company.id,
        code="WH-IT-01", name="Almacén Integración",
    )
    product = Product(id=uuid4(), tenant_id=tenant.id, sku=f"SKU-{uuid4().hex[:6]}", name="Producto Test")
    supplier = Supplier(id=uuid4(), tenant_id=tenant.id, code=f"SUP-{uuid4().hex[:6]}", name="Proveedor Test")
    db.add_all([warehouse, product, supplier])
    await db.flush()

    location = Location(id=uuid4(), tenant_id=tenant.id, warehouse_id=warehouse.id, code="A-01-01")
    db.add(location)
    await db.flush()

    return SimpleNamespace(
        db=db,
        tenant_id=tenant.id,
        user_id=user.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        supplier_id=supplier.id,
        location_id=location.id,
    )


@pytest_asyncio.fixture
async def inventory_level(seed):
    """Un nivel de stock con 100 unidades on-hand/available para el producto/ubicación."""
    level = InventoryLevel(
        id=uuid4(), tenant_id=seed.tenant_id, warehouse_id=seed.warehouse_id,
        location_id=seed.location_id, product_id=seed.product_id,
        quantity_on_hand=Decimal("100"), quantity_available=Decimal("100"),
    )
    seed.db.add(level)
    await seed.db.flush()
    return level


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: tests de integración que requieren PostgreSQL real"
    )
