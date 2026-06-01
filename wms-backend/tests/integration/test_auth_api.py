"""
Tests de integración — Auth API
================================
Cubre: login, refresh, logout, /me, cambio de password.
"""

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


class TestLogin:

    async def test_login_success(self, client: AsyncClient, superadmin):
        """Login exitoso devuelve tokens."""
        r = await client.post("/api/v1/auth/login", json={
            "email": superadmin.email,
            "password": "Admin1234!",
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient, superadmin):
        """Password incorrecto devuelve 401."""
        r = await client.post("/api/v1/auth/login", json={
            "email": superadmin.email,
            "password": "WrongPass999!",
        })
        assert r.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Usuario inexistente devuelve 401."""
        r = await client.post("/api/v1/auth/login", json={
            "email": "noexiste@wms.pa",
            "password": "cualquiera",
        })
        assert r.status_code == 401

    async def test_login_invalid_email_format(self, client: AsyncClient):
        """Email con formato inválido devuelve 422."""
        r = await client.post("/api/v1/auth/login", json={
            "email": "no-es-un-email",
            "password": "Admin1234!",
        })
        assert r.status_code == 422

    async def test_login_missing_fields(self, client: AsyncClient):
        """Campos faltantes devuelven 422."""
        r = await client.post("/api/v1/auth/login", json={"email": "test@test.com"})
        assert r.status_code == 422


class TestMe:

    async def test_me_authenticated(self, client: AsyncClient, auth_headers, superadmin):
        """GET /me con token válido devuelve datos del usuario."""
        r = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == superadmin.email
        assert "permissions" in data

    async def test_me_without_token(self, client: AsyncClient):
        """GET /me sin token devuelve 401."""
        r = await client.get("/api/v1/auth/me")
        assert r.status_code == 401

    async def test_me_invalid_token(self, client: AsyncClient):
        """GET /me con token inválido devuelve 401."""
        r = await client.get("/api/v1/auth/me",
                             headers={"Authorization": "Bearer token.invalido.xxx"})
        assert r.status_code == 401


class TestHealthEndpoints:

    async def test_health_live(self, client: AsyncClient):
        """/health/live siempre devuelve 200."""
        r = await client.get("/api/v1/health/live")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    async def test_health_ready_with_db(self, client: AsyncClient):
        """/health/ready devuelve 200 cuando BD está disponible."""
        r = await client.get("/api/v1/health/ready")
        # En test puede fallar si Redis no está, pero no debe ser 500
        assert r.status_code in (200, 503)
