"""
WMS Panamá — Pruebas de concurrencia real (Fase 0.5 del plan de implementación)
================================================================================
A diferencia de `test_e2e_flow.py` (un flujo secuencial), estas pruebas lanzan
N operaciones REALMENTE concurrentes (cada una con su propia conexión/sesión,
tal como ocurriría con N requests HTTP simultáneas) contra el mismo
producto/ubicación, para verificar que el lock distribuido de Redis
(`app.db.redis.distributed_lock`, usado por `InventoryService`) evita tanto
la sobreventa de stock como la pérdida de actualizaciones (lost updates).

Encontró un bug real al ejecutarse por primera vez: `distributed_lock` hacía
un único intento SETNX y se rendía de inmediato ante la primera colisión
(`acquired=False`), por lo que bajo concurrencia real la mayoría de las
operaciones fallaban con "no se pudo obtener el lock" en vez de coordinarse
en serie — aunque había stock de sobra para atenderlas a todas. Corregido en
`app/db/redis.py` (reintento con poll hasta agotar `timeout`).

Se salta automáticamente si no hay PostgreSQL de test accesible (ver conftest.py).
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.core import Company, Tenant, User, Warehouse
from app.models.inventory import InventoryLevel
from app.models.master_data import Location, Product
from app.services.inventory_service import InventoryService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_concurrent_transfers_do_not_oversell_or_lose_stock(engine):
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    # ── Setup: tenant/warehouse/producto/2 ubicaciones + 100 unidades en origen ──
    async with SessionLocal() as setup_db:
        tenant = Tenant(id=uuid4(), name="Concurrencia S.A.", slug=f"conc-{uuid4().hex[:8]}")
        setup_db.add(tenant)
        await setup_db.flush()

        user = User(
            id=uuid4(), tenant_id=tenant.id, email=f"conc-{uuid4().hex[:8]}@wms.pa",
            first_name="Conc", last_name="Urrencia", is_superadmin=True,
        )
        company = Company(id=uuid4(), tenant_id=tenant.id, name="Compañía Concurrencia")
        setup_db.add_all([user, company])
        await setup_db.flush()

        warehouse = Warehouse(
            id=uuid4(), tenant_id=tenant.id, company_id=company.id,
            code="WH-CONC", name="Almacén Concurrencia",
        )
        product = Product(id=uuid4(), tenant_id=tenant.id, sku=f"SKU-{uuid4().hex[:6]}", name="Producto Concurrencia")
        setup_db.add_all([warehouse, product])
        await setup_db.flush()

        loc_from = Location(id=uuid4(), tenant_id=tenant.id, warehouse_id=warehouse.id, code="FROM-01")
        loc_to = Location(id=uuid4(), tenant_id=tenant.id, warehouse_id=warehouse.id, code="TO-01")
        setup_db.add_all([loc_from, loc_to])
        await setup_db.flush()

        total_stock = Decimal("100")
        level = InventoryLevel(
            id=uuid4(), tenant_id=tenant.id, warehouse_id=warehouse.id, location_id=loc_from.id,
            product_id=product.id, quantity_on_hand=total_stock, quantity_available=total_stock,
        )
        setup_db.add(level)
        await setup_db.commit()

        tenant_id, user_id, warehouse_id, product_id = tenant.id, user.id, warehouse.id, product.id
        loc_from_id, loc_to_id = loc_from.id, loc_to.id

    # 10 transferencias concurrentes de 15 unidades cada una = 150 solicitadas
    # contra 100 disponibles: solo caben 6 (90 unidades); las 4 restantes deben
    # fallar por stock insuficiente — NUNCA por no poder coordinarse ni por
    # sobrevender/perder unidades.
    n_workers = 10
    qty_each = Decimal("15")

    async def _worker() -> bool:
        async with SessionLocal() as db:
            svc = InventoryService(db, tenant_id, user_id)
            try:
                await svc.transfer_location(
                    warehouse_id=warehouse_id, product_id=product_id,
                    from_location_id=loc_from_id, to_location_id=loc_to_id,
                    quantity=qty_each,
                )
                await db.commit()
                return True
            except Exception:
                await db.rollback()
                return False

    results = await asyncio.gather(*[_worker() for _ in range(n_workers)])
    successes = sum(1 for r in results if r)

    async with SessionLocal() as check_db:
        from_level = (await check_db.execute(
            select(InventoryLevel).where(
                InventoryLevel.location_id == loc_from_id, InventoryLevel.product_id == product_id
            )
        )).scalar_one()
        to_level = (await check_db.execute(
            select(InventoryLevel).where(
                InventoryLevel.location_id == loc_to_id, InventoryLevel.product_id == product_id
            )
        )).scalar_one_or_none()

    moved = successes * qty_each

    # El lock coordina en serie: exactamente 6 caben en 100/15, ni más (sobreventa)
    # ni menos (falsos rechazos por contención del lock).
    assert successes == 6
    assert moved == Decimal("90")
    assert from_level.quantity_on_hand == total_stock - moved
    assert from_level.quantity_available == total_stock - moved
    assert from_level.quantity_on_hand >= 0  # nunca stock negativo
    assert to_level is not None
    assert to_level.quantity_on_hand == moved
