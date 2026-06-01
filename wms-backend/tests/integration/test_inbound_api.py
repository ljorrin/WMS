"""
Tests de integración — Inbound API
=====================================
Cubre: Purchase Orders, GRN, Putaway, Dashboard.
"""

import pytest
from uuid import uuid4
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestPurchaseOrderAPI:

    def _po_payload(self, warehouse_id: str) -> dict:
        return {
            "warehouse_id": warehouse_id,
            "supplier_id": str(uuid4()),
            "order_date": "2026-05-27",
            "expected_delivery_date": "2026-06-10",
            "currency": "USD",
            "lines": [
                {
                    "product_id": str(uuid4()),
                    "uom_id": str(uuid4()),
                    "quantity_ordered": "100.0000",
                    "unit_cost": "25.5000",
                    "description": "Producto de prueba A",
                }
            ],
        }

    async def test_create_po_success(self, client: AsyncClient, auth_headers, warehouse):
        """POST /inbound/purchase-orders crea OC correctamente."""
        payload = self._po_payload(str(warehouse.id))
        r = await client.post("/api/v1/inbound/purchase-orders",
                              json=payload, headers=auth_headers)
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "draft"
        assert data["po_number"].startswith("PO-")
        assert len(data["lines"]) == 1

    async def test_create_po_auto_number(self, client: AsyncClient, auth_headers, warehouse):
        """Dos OCs consecutivas tienen números distintos."""
        payload = self._po_payload(str(warehouse.id))
        r1 = await client.post("/api/v1/inbound/purchase-orders",
                               json=payload, headers=auth_headers)
        r2 = await client.post("/api/v1/inbound/purchase-orders",
                               json=payload, headers=auth_headers)
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["po_number"] != r2.json()["po_number"]

    async def test_create_po_no_lines_fails(self, client: AsyncClient, auth_headers, warehouse):
        """OC sin líneas devuelve 422."""
        payload = self._po_payload(str(warehouse.id))
        payload["lines"] = []
        r = await client.post("/api/v1/inbound/purchase-orders",
                              json=payload, headers=auth_headers)
        assert r.status_code == 422

    async def test_list_pos(self, client: AsyncClient, auth_headers, warehouse):
        """GET /inbound/purchase-orders devuelve lista paginada."""
        # Crear una OC primero
        payload = self._po_payload(str(warehouse.id))
        await client.post("/api/v1/inbound/purchase-orders",
                          json=payload, headers=auth_headers)

        r = await client.get("/api/v1/inbound/purchase-orders", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert data["total"] >= 1

    async def test_get_po_detail(self, client: AsyncClient, auth_headers, warehouse):
        """GET /inbound/purchase-orders/{id} devuelve detalle de la OC."""
        payload = self._po_payload(str(warehouse.id))
        create_r = await client.post("/api/v1/inbound/purchase-orders",
                                     json=payload, headers=auth_headers)
        po_id = create_r.json()["id"]

        r = await client.get(f"/api/v1/inbound/purchase-orders/{po_id}",
                             headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["id"] == po_id

    async def test_confirm_po(self, client: AsyncClient, auth_headers, warehouse):
        """POST /inbound/purchase-orders/{id}/confirm cambia estado a confirmed."""
        payload = self._po_payload(str(warehouse.id))
        create_r = await client.post("/api/v1/inbound/purchase-orders",
                                     json=payload, headers=auth_headers)
        po_id = create_r.json()["id"]

        confirm_r = await client.post(
            f"/api/v1/inbound/purchase-orders/{po_id}/confirm",
            headers=auth_headers,
        )
        assert confirm_r.status_code == 204

        # Verificar estado
        detail_r = await client.get(f"/api/v1/inbound/purchase-orders/{po_id}",
                                    headers=auth_headers)
        assert detail_r.json()["status"] == "confirmed"

    async def test_confirm_already_confirmed_fails(self, client: AsyncClient, auth_headers, warehouse):
        """Confirmar una OC ya confirmada devuelve 409."""
        payload = self._po_payload(str(warehouse.id))
        create_r = await client.post("/api/v1/inbound/purchase-orders",
                                     json=payload, headers=auth_headers)
        po_id = create_r.json()["id"]

        await client.post(f"/api/v1/inbound/purchase-orders/{po_id}/confirm",
                          headers=auth_headers)
        # Segunda confirmación debe fallar
        r = await client.post(f"/api/v1/inbound/purchase-orders/{po_id}/confirm",
                              headers=auth_headers)
        assert r.status_code == 409

    async def test_get_po_not_found(self, client: AsyncClient, auth_headers):
        """GET /inbound/purchase-orders/{id} con ID inexistente → 404."""
        r = await client.get(f"/api/v1/inbound/purchase-orders/{uuid4()}",
                             headers=auth_headers)
        assert r.status_code == 404

    async def test_cancel_po(self, client: AsyncClient, auth_headers, warehouse):
        """POST /inbound/purchase-orders/{id}/cancel cancela la OC."""
        payload = self._po_payload(str(warehouse.id))
        create_r = await client.post("/api/v1/inbound/purchase-orders",
                                     json=payload, headers=auth_headers)
        po_id = create_r.json()["id"]

        r = await client.post(
            f"/api/v1/inbound/purchase-orders/{po_id}/cancel",
            headers=auth_headers,
        )
        assert r.status_code == 204

        detail = await client.get(f"/api/v1/inbound/purchase-orders/{po_id}",
                                  headers=auth_headers)
        assert detail.json()["status"] == "cancelled"


class TestInboundDashboard:

    async def test_dashboard_returns_metrics(self, client: AsyncClient, auth_headers):
        """GET /inbound/dashboard devuelve métricas sin error."""
        r = await client.get("/api/v1/inbound/dashboard", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        # Campos clave presentes
        assert "pos_open" in data
        assert "grns_today" in data
        assert "putaway_tasks_open" in data
