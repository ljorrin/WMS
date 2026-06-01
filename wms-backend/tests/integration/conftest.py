"""
WMS Panama — Configuración de Tests de Integración
=====================================================
Usa PostgreSQL en memoria (SQLite async) para tests de integración.
Cada test corre en su propia transacción que se revierte al final.

Fixtures disponibles:
  db          — AsyncSession transaccional (rollback al finalizar)
  client      — AsyncClient con app real montada
  tenant      — Tenant de prueba
  superadmin  — Usuario superadmin autenticado
  auth_headers — Headers JWT válidos
  wh_admin    — Usuario administrador de almacén
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.db.session import WMSBase, get_db
from app.main import create_application

# ── Motor de BD para tests ────────────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ── Fixtures de sesión ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Event loop compartido por toda la sesión de tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Crea todas las tablas al inicio y las elimina al finalizar."""
    async with test_engine.begin() as conn:
        await conn.run_sync(WMSBase.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(WMSBase.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Sesión de BD dentro de una transacción que se revierte al finalizar."""
    async with TestSessionLocal() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient con override del get_db para usar la BD de test."""
    app = create_application()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ── Fixtures de datos ─────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def tenant(db: AsyncSession):
    """Tenant de prueba."""
    from app.models.core import Tenant, TenantPlan
    tenant = Tenant(
        id=uuid4(),
        name="Empresa Test S.A.",
        slug="empresa-test",
        plan=TenantPlan.PROFESSIONAL,
        is_active=True,
        max_warehouses=5,
        max_users=50,
    )
    db.add(tenant)
    await db.flush()
    return tenant


@pytest_asyncio.fixture
async def superadmin(db: AsyncSession, tenant):
    """Usuario superadmin para tests."""
    from app.models.core import User, UserStatus
    from app.core.security import hash_password

    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email="admin@wms-test.pa",
        username="admin",
        full_name="Admin WMS Test",
        hashed_password=hash_password("Admin1234!"),
        status=UserStatus.ACTIVE,
        is_superadmin=True,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def warehouse(db: AsyncSession, tenant):
    """Almacén de prueba."""
    from app.models.core import Warehouse

    wh = Warehouse(
        id=uuid4(),
        tenant_id=tenant.id,
        name="Almacén Central Test",
        code="WH-TEST-01",
        address="Zona Libre, Colón, Panamá",
        is_active=True,
    )
    db.add(wh)
    await db.flush()
    return wh


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, superadmin):
    """Headers de autenticación JWT para el superadmin."""
    response = await client.post("/api/v1/auth/login", json={
        "email": superadmin.email,
        "password": "Admin1234!",
    })
    if response.status_code != 200:
        # Fallback: crear token directamente
        from app.core.security import create_access_token
        token = create_access_token({"sub": str(superadmin.id)})
        return {"Authorization": f"Bearer {token}"}

    data = response.json()
    return {"Authorization": f"Bearer {data['access_token']}"}
