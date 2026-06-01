"""Tests de integración — health check endpoints."""

import pytest


@pytest.mark.asyncio
async def test_health_live(client):
    """El endpoint /live siempre debe responder 200."""
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """El root / debe retornar info del sistema."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "app" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_root_health(client):
    """El /health sin prefijo debe responder OK."""
    response = await client.get("/health")
    assert response.status_code == 200
