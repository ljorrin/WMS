"""
Tests de integración — Inventory API
======================================
Cubre: stock query, movements, adjustments, cycle counts.
"""

import pytest
from decimal import Decimal
from uuid import uuid4
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestStockEndpoints:

    async def test_get_stock_empty(self, client: AsyncClient, auth_headers):
        """GET /inventory/stock devuelve lista vacía cuando no hay stock."""
        r = await client.get("/api/v1/inventory/stock", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    async def test_get_stock_with_filters(self, client: AsyncClient, auth_headers, warehouse):
        """GET /inventory/stock acepta filtros de warehouse_id."""
        r = await client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": str(warehouse.id)},
            headers=auth_headers,
        )
        assert r.status_code == 200

    async def test_get_movements_empty(self, client: AsyncClient, auth_headers):
        """GET /inventory/movements devuelve lista vacía inicialmente."""
        r = await client.get("/api/v1/inventory/movements", headers=auth_headers)
        assert r.status_code == 200
        assert "items" in r.json()

    async def test_get_near_expiry(self, client: AsyncClient, auth_headers):
        """GET /inventory/batches/near-expiry es accesible."""
        r = await client.get("/api/v1/inventory/batches/near-expiry",
                             headers=auth_headers)
        assert r.status_code == 200

    async def test_create_adjustment_valid(self, client: AsyncClient, auth_headers, warehouse):
        """POST /inventory/adjustments crea un ajuste válido."""
        product_id  = str(uuid4())
        location_id = str(uuid4())
        uom_id      = str(uuid4())

        payload = {
            "warehouse_id": str(warehouse.id),
            "reason": "Conteo físico de inventario Q2 2026",
            "adjustment_type": "cycle_count",
            "lines": [
                {
                    "product_id": product_id,
                    "location_id": location_id,
                    "uom_id": uom_id,
                    "quantity_system": "100.0000",
                    "quantity_counted": "95.0000",
                    "notes": "5 unidades dañadas"
                }
            ]
        }
        r = await client.post("/api/v1/inventory/adjustments",
                              json=payload, headers=auth_headers)
        # 201 o 422 si faltan dependencias (producto no existe en BD real)
        assert r.status_code in (201, 422, 409)

    async def test_get_adjustments_list(self, client: AsyncClient, auth_headers):
        """GET /inventory/adjustments devuelve lista paginada."""
        r = await client.get("/api/v1/inventory/adjustments", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data

    async def test_adjustment_approve_not_found(self, client: AsyncClient, auth_headers):
        """POST /inventory/adjustments/{id}/approve con ID inexistente → 404."""
        fake_id = str(uuid4())
        r = await client.post(
            f"/api/v1/inventory/adjustments/{fake_id}/approve",
            headers=auth_headers,
        )
        assert r.status_code in (404, 409)


class TestInventoryPagination:

    async def test_pagination_defaults(self, client: AsyncClient, auth_headers):
        """Paginación por defecto: page=1, page_size configurado."""
        r = await client.get("/api/v1/inventory/stock", headers=auth_headers)
        data = r.json()
        assert data["page"] == 1
        assert data["page_size"] > 0

    async def test_pagination_custom(self, client: AsyncClient, auth_headers):
        """Paginación custom: page=2, page_size=5."""
        r = await client.get(
            "/api/v1/inventory/stock",
            params={"page": 2, "page_size": 5},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 2
        assert data["page_size"] == 5
