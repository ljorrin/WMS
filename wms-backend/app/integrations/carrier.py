"""Adaptador de transportista genérico (Correos de Panamá/DHL/FedEx/local).

Cotización de tarifa, generación de guía/label y consulta de tracking. El
transportista se selecciona por CARRIER_NAME. Incluye un cálculo de tarifa de
respaldo (peso × zona) cuando no hay endpoint configurado.
"""

from __future__ import annotations

from decimal import Decimal

from app.integrations import config, http_client

# Tarifa de respaldo (USD) por kg y por zona — configurable/operacional.
_FALLBACK_RATE_PER_KG = {"local": Decimal("1.50"), "nacional": Decimal("2.50"), "internacional": Decimal("8.00")}
_FALLBACK_BASE = Decimal("3.00")


def fallback_rate(weight_kg: float, zone: str = "nacional") -> Decimal:
    """Tarifa estimada sin proveedor externo (peso × zona)."""
    per_kg = _FALLBACK_RATE_PER_KG.get(zone, _FALLBACK_RATE_PER_KG["nacional"])
    return (_FALLBACK_BASE + per_kg * Decimal(str(max(weight_kg, 0.1)))).quantize(Decimal("0.01"))


async def quote(weight_kg: float, zone: str = "nacional", destination: dict | None = None) -> dict:
    cfg = config.carrier_config()
    if not cfg.configured:
        return {"ok": True, "configured": False, "source": "fallback",
                "amount": str(fallback_rate(weight_kg, zone)), "currency": "USD",
                "message": "Tarifa estimada local; configurar CARRIER_BASE_URL/API_KEY para tarifa real."}
    return await http_client.call(cfg, "POST", "/rates",
                                  json={"weight_kg": weight_kg, "zone": zone, "destination": destination or {}})


async def create_label(shipment_payload: dict) -> dict:
    cfg = config.carrier_config()
    return await http_client.call(cfg, "POST", "/labels", json=shipment_payload)


async def track(tracking_number: str) -> dict:
    cfg = config.carrier_config()
    return await http_client.call(cfg, "GET", f"/tracking/{tracking_number}")
