"""
WMS Panamá — Tools del Asistente IA agéntico contra PostgreSQL real (Fase 5)
================================================================================
Verifica que cada tool ejecuta consultas/escrituras REALES (no datos
inventados): stock, KPIs, alertas de reposición, anomalías y asignación de
tareas de labor (task interleaving), incluyendo el gate de permisos.

Se salta automáticamente si no hay PostgreSQL de test accesible (ver conftest.py).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.ai import AlertSeverity, AlertType, AnomalyEvent, AnomalyType, ReplenishmentAlert
from app.models.labor import LaborTask
from app.services.ai import tools as ai_tools

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _ctx(seed, permissions=frozenset(), is_superadmin=True):
    return ai_tools.ToolContext(
        db=seed.db, tenant_id=seed.tenant_id, user_id=seed.user_id,
        permissions=permissions, is_superadmin=is_superadmin,
    )


async def test_get_stock_summary_total(seed, inventory_level):
    result = await ai_tools.execute_tool("get_stock_summary", {}, _ctx(seed))
    assert result["ok"] is True
    assert result["total_available"] == 100.0
    assert result["locations_count"] == 1


async def test_get_stock_summary_by_product_query(seed, inventory_level):
    from sqlalchemy import select

    from app.models.master_data import Product
    product = (await seed.db.execute(select(Product).where(Product.id == seed.product_id))).scalar_one()

    result = await ai_tools.execute_tool(
        "get_stock_summary", {"product_query": product.sku}, _ctx(seed),
    )
    assert result["ok"] is True
    assert result["found"] is True
    assert result["products"][0]["sku"] == product.sku
    assert result["products"][0]["quantity_available"] == 100.0


async def test_get_stock_summary_by_product_query_not_found(seed):
    result = await ai_tools.execute_tool(
        "get_stock_summary", {"product_query": "NO-EXISTE-XYZ"}, _ctx(seed),
    )
    assert result["ok"] is True
    assert result["found"] is False


async def test_dashboard_kpis_smoke(seed):
    result = await ai_tools.execute_tool(
        "get_dashboard_kpis", {"module": "inbound", "warehouse_id": str(seed.warehouse_id)}, _ctx(seed),
    )
    assert result["ok"] is True


async def test_alerts_lifecycle(seed):
    alert = ReplenishmentAlert(
        id=uuid4(), tenant_id=seed.tenant_id, warehouse_id=seed.warehouse_id, product_id=seed.product_id,
        alert_type=AlertType.STOCKOUT_RISK, severity=AlertSeverity.CRITICAL,
        title="Riesgo de quiebre de stock", is_resolved=False,
    )
    seed.db.add(alert)
    await seed.db.flush()

    listed = await ai_tools.execute_tool("list_active_alerts", {}, _ctx(seed))
    assert listed["ok"] is True
    assert listed["count"] == 1
    assert listed["alerts"][0]["id"] == str(alert.id)

    resolved = await ai_tools.execute_tool(
        "resolve_replenishment_alert",
        {"alert_id": str(alert.id), "action_taken": "OC de emergencia creada"},
        _ctx(seed),
    )
    assert resolved["ok"] is True

    await seed.db.refresh(alert)
    assert alert.is_resolved is True
    assert alert.action_taken == "OC de emergencia creada"

    listed_after = await ai_tools.execute_tool("list_active_alerts", {}, _ctx(seed))
    assert listed_after["count"] == 0


async def test_anomalies_lifecycle(seed):
    anomaly = AnomalyEvent(
        id=uuid4(), tenant_id=seed.tenant_id, warehouse_id=seed.warehouse_id, product_id=seed.product_id,
        anomaly_type=AnomalyType.NEGATIVE_STOCK, severity=AlertSeverity.CRITICAL,
        description="Stock negativo detectado", is_resolved=False,
    )
    seed.db.add(anomaly)
    await seed.db.flush()

    listed = await ai_tools.execute_tool("list_open_anomalies", {}, _ctx(seed))
    assert listed["ok"] is True
    assert listed["count"] == 1

    resolved = await ai_tools.execute_tool(
        "resolve_anomaly",
        {"anomaly_id": str(anomaly.id), "is_false_positive": False, "resolution_notes": "Ajuste manual aplicado"},
        _ctx(seed),
    )
    assert resolved["ok"] is True

    await seed.db.refresh(anomaly)
    assert anomaly.is_resolved is True
    assert anomaly.resolution_notes == "Ajuste manual aplicado"


async def test_labor_task_suggest_and_assign(seed):
    task = LaborTask(
        id=uuid4(), tenant_id=seed.tenant_id, warehouse_id=seed.warehouse_id,
        activity_type="putaway", status="pending", zone="A",
    )
    seed.db.add(task)
    await seed.db.flush()

    suggested = await ai_tools.execute_tool(
        "suggest_next_labor_task", {"warehouse_id": str(seed.warehouse_id)}, _ctx(seed),
    )
    assert suggested["ok"] is True
    assert suggested["found"] is True
    assert suggested["task"]["id"] == str(task.id)

    assigned = await ai_tools.execute_tool(
        "assign_next_labor_task",
        {"warehouse_id": str(seed.warehouse_id), "operator_id": str(seed.user_id)},
        _ctx(seed),
    )
    assert assigned["ok"] is True
    assert assigned["found"] is True
    assert assigned["task"]["assigned_to_id"] == str(seed.user_id)

    await seed.db.refresh(task)
    assert task.status == "assigned"
    assert task.user_id == seed.user_id


async def test_permission_denied_end_to_end_without_touching_handler(seed):
    """Un usuario sin el permiso requerido no puede resolver anomalías via el asistente."""
    anomaly = AnomalyEvent(
        id=uuid4(), tenant_id=seed.tenant_id, warehouse_id=seed.warehouse_id,
        anomaly_type=AnomalyType.NEGATIVE_STOCK, severity=AlertSeverity.WARNING,
        description="x", is_resolved=False,
    )
    seed.db.add(anomaly)
    await seed.db.flush()

    ctx = _ctx(seed, permissions=frozenset({"inventory:read"}), is_superadmin=False)
    result = await ai_tools.execute_tool(
        "resolve_anomaly",
        {"anomaly_id": str(anomaly.id), "resolution_notes": "no debería aplicar"},
        ctx,
    )
    assert result["ok"] is False
    assert "Permiso denegado" in result["error"]

    await seed.db.refresh(anomaly)
    assert anomaly.is_resolved is False  # no se tocó la BD
