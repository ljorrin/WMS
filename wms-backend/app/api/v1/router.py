"""
WMS Panama — Router Principal API v1
======================================
Agrega todos los sub-routers de los módulos.
Prefijo: /api/v1
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, tenants, users, warehouses, master_data, inventory, inbound, outbound, ai, realtime, integrations

api_router = APIRouter(prefix="/api/v1")

# ── Endpoints base ─────────────────────────────────────────────────────────────
api_router.include_router(health.router,     prefix="/health",     tags=["⚡ Health"])
api_router.include_router(auth.router,       prefix="/auth",       tags=["🔐 Auth"])

# ── Módulos core ───────────────────────────────────────────────────────────────
api_router.include_router(tenants.router,    prefix="/tenants",    tags=["🏢 Tenants"])
api_router.include_router(users.router,      prefix="/users",      tags=["👤 Users"])
api_router.include_router(warehouses.router, prefix="/warehouses", tags=["🏭 Warehouses"])
api_router.include_router(master_data.router, prefix="/master",     tags=["📚 Master Data"])

# ── Módulos WMS ────────────────────────────────────────────────────────────────
api_router.include_router(inventory.router,  prefix="/inventory",  tags=["📦 Inventory"])
api_router.include_router(inbound.router,   prefix="/inbound",    tags=["🚚 Inbound"])
api_router.include_router(outbound.router,  prefix="/outbound",   tags=["📤 Outbound"])
api_router.include_router(ai.router,        prefix="/ai",         tags=["🤖 AI/ML"])

# ── Tiempo real (WebSocket) ──────────────────────────────────────────────────
api_router.include_router(realtime.router,  tags=["📡 Realtime"])

# ── Integraciones (ERP, eCommerce, transporte, regulatorio Panamá) ───────────
api_router.include_router(integrations.router, prefix="/integrations", tags=["🔌 Integraciones"])
