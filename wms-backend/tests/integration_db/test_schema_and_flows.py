"""
WMS Panamá — Tests de integración (PostgreSQL real)
====================================================
Cubren los flujos reconciliados extremo a extremo contra una BD real:
  1. El esquema completo se materializa en PostgreSQL (create_all).
  2. Inbound: ciclo de Orden de Compra (crear → confirmar → historial).
  3. Inventory: ciclo de ajuste (crear → aprobar → aplicar → stock actualizado).

Se ejecutan solo si WMS_TEST_DATABASE_URL apunta a un PostgreSQL accesible
(ver conftest.py). En caso contrario, se saltan automáticamente.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.base import WMSBase
from app.models.inbound import POStatus, PurchaseOrder
from app.models.inventory import (
    AdjustmentStatus,
    InventoryAdjustment,
    InventoryLevel,
    InventoryMovement,
)
from app.schemas.inventory import AdjustmentApproveRequest, AdjustmentLineCreate, InventoryAdjustmentCreate
from app.services.inbound_service import InboundService
from app.services.inventory_service import InventoryService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ── 1. Esquema ────────────────────────────────────────────────────────────────

async def test_schema_creates_all_tables(engine):
    """El esquema completo (Inbound+Outbound+Inventory+AI+core+master) se crea en PostgreSQL."""
    expected = len(WMSBase.metadata.tables)
    assert expected >= 50, f"Se esperaban >=50 tablas en metadata, hay {expected}"

    def _list_tables(sync_conn):
        from sqlalchemy import inspect as sa_inspect
        return set(sa_inspect(sync_conn).get_table_names())

    async with engine.connect() as conn:
        present = await conn.run_sync(_list_tables)

    missing = set(WMSBase.metadata.tables.keys()) - present
    assert not missing, f"Tablas faltantes en la BD: {sorted(missing)}"


# ── 2. Inbound — ciclo de Orden de Compra ───────────────────────────────────────

async def test_purchase_order_lifecycle(seed):
    """Crear OC (DRAFT) → confirmar (CONFIRMED) con historial de estados, contra PostgreSQL."""
    svc = InboundService(db=seed.db, tenant_id=seed.tenant_id, user_id=seed.user_id)

    po = await svc.create_purchase_order(
        warehouse_id=seed.warehouse_id,
        supplier_id=seed.supplier_id,
        order_date=date.today(),
        lines_data=[dict(
            product_id=seed.product_id,
            quantity_ordered=Decimal("25"),
            unit_cost=Decimal("3.50"),
            uom="UN",
        )],
    )
    await seed.db.flush()

    fetched = await svc.po_repo.get_by_id(po.id)
    assert fetched is not None
    assert fetched.status == POStatus.DRAFT
    assert len(fetched.lines) == 1
    assert fetched.lines[0].quantity_ordered == Decimal("25")
    # total_amount = 25 * 3.50
    assert fetched.total_amount == Decimal("87.50")
    # Historial: una transición inicial a DRAFT
    assert len(fetched.status_history) == 1
    assert fetched.status_history[0].to_status == POStatus.DRAFT.value

    # Confirmar
    await svc.confirm_purchase_order(po.id)
    await seed.db.flush()

    confirmed = await svc.po_repo.get_by_id(po.id)
    assert confirmed.status == POStatus.CONFIRMED
    assert confirmed.confirmed_date is not None
    # Historial: DRAFT (creación) + CONFIRMED
    history = sorted(confirmed.status_history, key=lambda h: h.created_at)
    assert [h.to_status for h in history][-1] == POStatus.CONFIRMED.value


# ── 3. Inventory — ciclo de ajuste ──────────────────────────────────────────────

async def test_inventory_adjustment_lifecycle(seed, inventory_level):
    """
    Crear ajuste (cabecera+línea) → aprobar → aplicar.
    Verifica que el stock se descuenta y se genera un movimiento, contra PostgreSQL.
    Este flujo era NO funcional antes de la reconciliación (reason_code/created_by/enum).
    """
    svc = InventoryService(db=seed.db, tenant_id=seed.tenant_id, user_id=seed.user_id)

    body = InventoryAdjustmentCreate(
        warehouse_id=seed.warehouse_id,
        reason="Conteo cíclico mensual con faltante",
        reason_code="COUNT_ERROR",
        reference_number="CC-2026-06",
        lines=[AdjustmentLineCreate(
            product_id=seed.product_id,
            location_id=seed.location_id,
            quantity_system=Decimal("100"),
            quantity_physical=Decimal("95"),
            unit_cost=Decimal("3.50"),
        )],
    )

    adj = await svc.create_adjustment(body)
    await seed.db.flush()
    assert adj.status == AdjustmentStatus.PENDING_APPROVAL
    assert adj.reason_code == "COUNT_ERROR"
    assert adj.requested_by == seed.user_id

    # Aprobar
    await svc.approve_adjustment(adj.id, AdjustmentApproveRequest(approved=True, notes="ok"))
    await seed.db.flush()
    approved = await svc.adjustments.get_by_id(adj.id, seed.tenant_id)
    assert approved.status == AdjustmentStatus.APPROVED
    assert approved.approved_by == seed.user_id

    # Aplicar → descuenta 5 unidades y crea un movimiento de ajuste
    await svc.apply_adjustment(adj.id)
    await seed.db.flush()
    applied = await svc.adjustments.get_by_id(adj.id, seed.tenant_id)
    assert applied.status == AdjustmentStatus.APPLIED
    assert applied.applied_by == seed.user_id

    # Stock: 100 - 5 = 95
    level = (
        await seed.db.execute(
            select(InventoryLevel).where(InventoryLevel.id == inventory_level.id)
        )
    ).scalar_one()
    assert level.quantity_on_hand == Decimal("95")
    assert level.quantity_available == Decimal("95")

    # Se generó exactamente un movimiento de ajuste para este tenant
    movements = (
        await seed.db.execute(
            select(func.count(InventoryMovement.id)).where(
                InventoryMovement.tenant_id == seed.tenant_id,
                InventoryMovement.reference_id == adj.id,
            )
        )
    ).scalar_one()
    assert movements == 1
