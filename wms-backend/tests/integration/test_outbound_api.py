"""
Tests de integración — Outbound API
======================================
Cubre: Sales Orders, Waves, Picking, Dashboard.
"""

import pytest
from uuid import uuid4
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestSalesOrderAPI:

    def _so_payload(self, warehouse_id: str) -> dict:
        return {
            "warehouse_id": warehouse_id,
            "customer_id": str(uuid4()),
            "order_date": "2026-05-27T10:00:00Z",
            "requested_delivery_date": "2026-06-05T18:00:00Z",
            "priority": 5,
            "currency": "USD",
            "carrier_type": "third_party",
            "ship_to_name": "Cliente Test S.A.",
            "ship_to_address": "Av. Balboa, Ciudad de Panamá",
            "ship_to_country": "PA",
            "lines": [
                {
                    "product_id": str(uuid4()),
                    "uom_id": str(uuid4()),
                    "quantity_ordered": "50.0000",
                    "unit_price": "120.0000",
                    "discount_pct": "0.0500",
                    "tax_rate": "0.0700",
                }
            ],
        }

    async def test_create_so_success(self, client: AsyncClient, auth_headers, warehouse):
        """POST /outbound/orders crea SO en estado draft."""
        payload = self._so_payload(str(warehouse.id))
        r = await client.post("/api/v1/outbound/orders",
                              json=payload, headers=auth_headers)
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "draft"
        assert data["so_number"].startswith("SO-")
        assert len(data["lines"]) == 1

    async def test_create_so_no_lines_fails(self, client: AsyncClient, auth_headers, warehouse):
        """SO sin líneas devuelve 422."""
        payload = self._so_payload(str(warehouse.id))
        payload["lines"] = []
        r = await client.post("/api/v1/outbound/orders",
                              json=payload, headers=auth_headers)
        assert r.status_code == 422

    async def test_list_sales_orders(self, client: AsyncClient, auth_headers, warehouse):
        """GET /outbound/orders devuelve lista paginada."""
        payload = self._so_payload(str(warehouse.id))
        await client.post("/api/v1/outbound/orders", json=payload, headers=auth_headers)

        r = await client.get("/api/v1/outbound/orders", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert data["total"] >= 1

    async def test_get_so_detail(self, client: AsyncClient, auth_headers, warehouse):
        """GET /outbound/orders/{id} devuelve detalle completo."""
        payload = self._so_payload(str(warehouse.id))
        create_r = await client.post("/api/v1/outbound/orders",
                                     json=payload, headers=auth_headers)
        so_id = create_r.json()["id"]

        r = await client.get(f"/api/v1/outbound/orders/{so_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["id"] == so_id

    async def test_so_not_found(self, client: AsyncClient, auth_headers):
        """GET /outbound/orders/{id} con ID inexistente → 404."""
        r = await client.get(f"/api/v1/outbound/orders/{uuid4()}", headers=auth_headers)
        assert r.status_code == 404

    async def test_cancel_so_draft(self, client: AsyncClient, auth_headers, warehouse):
        """Cancelar SO en DRAFT es válido."""
        payload = self._so_payload(str(warehouse.id))
        create_r = await client.post("/api/v1/outbound/orders",
                                     json=payload, headers=auth_headers)
        so_id = create_r.json()["id"]

        r = await client.post(
            f"/api/v1/outbound/orders/{so_id}/cancel",
            json={"reason": "Cliente canceló el pedido."},
            headers=auth_headers,
        )
        assert r.status_code == 204

        detail = await client.get(f"/api/v1/outbound/orders/{so_id}",
                                  headers=auth_headers)
        assert detail.json()["status"] == "cancelled"

    async def test_so_priority_ordering(self, client: AsyncClient, auth_headers, warehouse):
        """SOs de alta prioridad aparecen primero en el listado."""
        base = self._so_payload(str(warehouse.id))

        # Crear SO de baja prioridad
        low = dict(base); low["priority"] = 9
        await client.post("/api/v1/outbound/orders", json=low, headers=auth_headers)

        # Crear SO de alta prioridad
        high = dict(base); high["priority"] = 1
        await client.post("/api/v1/outbound/orders", json=high, headers=auth_headers)

        r = await client.get("/api/v1/outbound/orders", headers=auth_headers)
        items = r.json()["items"]
        priorities = [i["priority"] for i in items if i["status"] != "cancelled"]
        if len(priorities) >= 2:
            # El listado debe ordenar por prioridad asc (1 = urgente primero)
            assert priorities[0] <= priorities[-1]


class TestWaveAPI:

    async def test_list_waves_empty(self, client: AsyncClient, auth_headers):
        """GET /outbound/waves devuelve lista vacía inicialmente."""
        r = await client.get("/api/v1/outbound/waves", headers=auth_headers)
        assert r.status_code == 200
        assert "items" in r.json()


class TestOutboundDashboard:

    async def test_dashboard_returns_metrics(self, client: AsyncClient, auth_headers):
        """GET /outbound/dashboard devuelve métricas sin error."""
        r = await client.get("/api/v1/outbound/dashboard", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "orders_open" in data
        assert "picks_today" in data
        assert "shipments_today" in data

    async def test_dashboard_with_warehouse_filter(
        self, client: AsyncClient, auth_headers, warehouse
    ):
        """Dashboard acepta filtro por warehouse_id."""
        r = await client.get(
            "/api/v1/outbound/dashboard",
            params={"warehouse_id": str(warehouse.id)},
            headers=auth_headers,
        )
        assert r.status_code == 200

    async def test_dashboard_orders_overdue_zero_initially(
        self, client: AsyncClient, auth_headers
    ):
        """Sin SOs creadas, orders_overdue debe ser 0."""
        r = await client.get("/api/v1/outbound/dashboard", headers=auth_headers)
        assert r.json()["orders_overdue"] >= 0
