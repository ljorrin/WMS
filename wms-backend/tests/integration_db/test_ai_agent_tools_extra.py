"""
WMS Panamá — Tools ampliadas del Asistente IA (cobertura total de módulos) — Fase 5
======================================================================================
Complementa test_ai_agent_tools.py: verifica que las tools nuevas (inbound, outbound,
inventario extendido, maestros, bodegas, slotting, streaming, hardware) ejecutan
consultas reales sin lanzar excepciones (firma de repos/servicios correcta), y que
al menos una de cada dominio devuelve datos reales cuando existen.

Se salta automáticamente si no hay PostgreSQL de test accesible (ver conftest.py).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.slotting import SlottingRecommendation
from app.services.ai import tools as ai_tools

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _ctx(seed):
    return ai_tools.ToolContext(
        db=seed.db, tenant_id=seed.tenant_id, user_id=seed.user_id, is_superadmin=True,
    )


async def test_list_purchase_orders_empty_ok(seed):
    result = await ai_tools.execute_tool("list_purchase_orders", {"warehouse_id": str(seed.warehouse_id)}, _ctx(seed))
    assert result["ok"] is True
    assert result["total"] == 0
    assert result["items"] == []


async def test_list_sales_orders_empty_ok(seed):
    result = await ai_tools.execute_tool("list_sales_orders", {}, _ctx(seed))
    assert result["ok"] is True
    assert result["total"] == 0


async def test_list_grns_qc_putaway_rtv_empty_ok(seed):
    for tool_name, args in [
        ("list_grns", {}), ("list_quality_inspections", {}),
        ("list_putaway_tasks", {}), ("list_rtvs", {}),
    ]:
        result = await ai_tools.execute_tool(tool_name, args, _ctx(seed))
        assert result["ok"] is True, f"{tool_name} failed: {result}"
        assert result["total"] == 0


async def test_list_waves_picking_pack_shipments_returns_empty_ok(seed):
    for tool_name in ["list_picking_waves", "list_picking_tasks", "list_pack_tasks", "list_shipments", "list_returns"]:
        result = await ai_tools.execute_tool(tool_name, {}, _ctx(seed))
        assert result["ok"] is True, f"{tool_name} failed: {result}"
        assert result["total"] == 0


async def test_list_inventory_adjustments_and_cycle_counts_empty_ok(seed):
    for tool_name in ["list_inventory_adjustments", "list_cycle_counts"]:
        result = await ai_tools.execute_tool(tool_name, {"warehouse_id": str(seed.warehouse_id)}, _ctx(seed))
        assert result["ok"] is True, f"{tool_name} failed: {result}"
        assert result["total"] == 0


async def test_list_near_expiry_batches_requires_warehouse(seed):
    missing = await ai_tools.execute_tool("list_near_expiry_batches", {}, _ctx(seed))
    assert missing["ok"] is False

    result = await ai_tools.execute_tool(
        "list_near_expiry_batches", {"warehouse_id": str(seed.warehouse_id)}, _ctx(seed),
    )
    assert result["ok"] is True
    assert result["total"] == 0


async def test_search_products_suppliers_customers_locations(seed):
    from sqlalchemy import select

    from app.models.master_data import Product, Supplier

    product = (await seed.db.execute(select(Product).where(Product.id == seed.product_id))).scalar_one()
    supplier = (await seed.db.execute(select(Supplier).where(Supplier.id == seed.supplier_id))).scalar_one()

    prod_result = await ai_tools.execute_tool("search_products", {"search": product.sku}, _ctx(seed))
    assert prod_result["ok"] is True
    assert prod_result["total"] == 1
    assert prod_result["items"][0]["sku"] == product.sku

    sup_result = await ai_tools.execute_tool("search_suppliers", {"search": supplier.code}, _ctx(seed))
    assert sup_result["ok"] is True
    assert sup_result["total"] == 1

    cust_result = await ai_tools.execute_tool("search_customers", {}, _ctx(seed))
    assert cust_result["ok"] is True

    loc_result = await ai_tools.execute_tool(
        "search_locations", {"warehouse_id": str(seed.warehouse_id)}, _ctx(seed),
    )
    assert loc_result["ok"] is True
    assert loc_result["total"] == 1


async def test_list_warehouses_real(seed):
    from sqlalchemy import select

    from app.models.core import Warehouse
    wh = (await seed.db.execute(select(Warehouse).where(Warehouse.id == seed.warehouse_id))).scalar_one()

    result = await ai_tools.execute_tool("list_warehouses", {"search": wh.code}, _ctx(seed))
    assert result["ok"] is True
    assert result["total"] == 1
    assert result["items"][0]["code"] == wh.code


async def test_list_slotting_recommendations_real(seed):
    rec = SlottingRecommendation(
        id=uuid4(), tenant_id=seed.tenant_id, warehouse_id=seed.warehouse_id, product_id=seed.product_id,
        abc_class="A", status="pending", reason="Alta rotación",
    )
    seed.db.add(rec)
    await seed.db.flush()

    result = await ai_tools.execute_tool(
        "list_slotting_recommendations", {"warehouse_id": str(seed.warehouse_id)}, _ctx(seed),
    )
    assert result["ok"] is True
    assert result["total"] == 1
    assert result["items"][0]["abc_class"] == "A"


async def test_get_streaming_metrics_ok(seed):
    result = await ai_tools.execute_tool("get_streaming_metrics", {"warehouse_id": str(seed.warehouse_id)}, _ctx(seed))
    assert result["ok"] is True
    assert result["queue_pending"] == 0


async def test_list_rfid_readers_empty_ok(seed):
    result = await ai_tools.execute_tool("list_rfid_readers", {"warehouse_id": str(seed.warehouse_id)}, _ctx(seed))
    assert result["ok"] is True
    assert result["count"] == 0


async def test_get_dashboard_kpis_all_modules(seed):
    for module in ["inbound", "outbound", "inventory", "labor", "slotting", "streaming"]:
        result = await ai_tools.execute_tool(
            "get_dashboard_kpis", {"module": module, "warehouse_id": str(seed.warehouse_id)}, _ctx(seed),
        )
        assert result["ok"] is True, f"module={module} failed: {result}"


async def test_get_dashboard_kpis_denies_without_permission(seed):
    ctx = ai_tools.ToolContext(
        db=seed.db, tenant_id=seed.tenant_id, user_id=seed.user_id,
        permissions=frozenset(), is_superadmin=False,
    )
    result = await ai_tools.execute_tool("get_dashboard_kpis", {"module": "labor"}, ctx)
    assert result["ok"] is False
    assert "Permiso denegado" in result["error"]
