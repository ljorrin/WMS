"""
WMS Panama — Pytest Configuration
====================================
Fixtures compartidas para todos los tests.
Usa una BD en memoria / test separada para evitar afectar datos reales.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Configurar entorno de test ANTES de importar la app
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_testing_only_32_chars")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_SYNC_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")  # DB 15 para tests

from app.main import app
from app.models.base import WMSBase
from app.db.session import get_db
from app.core.security import create_access_token, hash_password
from app.models.core import Tenant, TenantPlan, TenantStatus, User, UserStatus


# ── Configuración async ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Event loop compartido para toda la sesión de tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Base de datos en memoria ───────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Motor SQLite en memoria para tests — se crea fresh por cada test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(WMSBase.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(WMSBase.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Sesión de BD para tests."""
    TestSession = async_sessionmaker(db_engine, expire_on_commit=False)
    async with TestSession() as session:
        yield session


# ── Fixtures de datos ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def tenant(db: AsyncSession) -> Tenant:
    """Tenant de prueba."""
    t = Tenant(
        name="Test Company S.A.",
        slug="test-company",
        plan=TenantPlan.ENTERPRISE,
        status=TenantStatus.ACTIVE,
        max_warehouses=10,
        max_users=100,
        max_skus=100_000,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


@pytest_asyncio.fixture
async def superadmin(db: AsyncSession, tenant: Tenant) -> User:
    """Usuario superadmin de prueba."""
    user = User(
        tenant_id=tenant.id,
        email="admin@test.com",
        first_name="Admin",
        last_name="Test",
        hashed_password=hash_password("Admin123!"),
        status=UserStatus.ACTIVE,
        is_superadmin=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(superadmin: User) -> dict[str, str]:
    """Headers de autenticación para el superadmin de prueba."""
    token = create_access_token(
        subject=superadmin.id,
        tenant_id=superadmin.tenant_id,
    )
    return {"Authorization": f"Bearer {token}"}


# ── HTTP Client ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Cliente HTTP asíncrono con override de la BD."""

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
