"""
WMS Panamá — Endpoints de Integraciones (ERP, eCommerce, Transporte, Regulatorio)
==================================================================================
Exponen la lógica de los adaptadores de `app/integrations`. Las credenciales y
endpoints se parametrizan por entorno; sin configurar, las acciones devuelven
`configured=False` (sin llamadas externas) y `/status` indica qué falta definir.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Depends

from app.core.dependencies import CurrentUserDep, require_permission
from app.integrations import carrier, config, ecommerce, erp
from app.integrations.regulatory import ana_siga, dgi

router = APIRouter()


@router.get("/status", summary="Estado de configuración de integraciones")
async def integrations_status(current_user: CurrentUserDep) -> dict:
    """Indica qué integraciones están configuradas y qué variables faltan."""
    cfgs = {
        "erp": config.erp_config(), "ecommerce": config.ecommerce_config(),
        "carrier": config.carrier_config(), "siga": config.siga_config(),
        "dgi": config.dgi_config(),
    }
    return {name: {"configured": c.configured, "missing": c.missing, "extra": c.extra}
            for name, c in cfgs.items()}


# ── Transporte ────────────────────────────────────────────────────────────────
@router.post("/carrier/quote", summary="Cotizar envío (con tarifa de respaldo)",
             dependencies=[Depends(require_permission("outbound:shipping:manage"))])
async def carrier_quote(payload: dict = Body(...)) -> dict:
    return await carrier.quote(
        weight_kg=float(payload.get("weight_kg", 0) or 0),
        zone=str(payload.get("zone", "nacional")),
        destination=payload.get("destination"),
    )


@router.get("/carrier/track/{tracking_number}", summary="Tracking de envío",
            dependencies=[Depends(require_permission("outbound:shipping:manage"))])
async def carrier_track(tracking_number: str) -> dict:
    return await carrier.track(tracking_number)


# ── eCommerce ─────────────────────────────────────────────────────────────────
@router.post("/ecommerce/stock-sync", summary="Sincronizar stock hacia la tienda",
             dependencies=[Depends(require_permission("outbound:shipping:manage"))])
async def ecommerce_stock_sync(payload: dict = Body(...)) -> dict:
    return await ecommerce.sync_stock(items=payload.get("items", []) or [])


@router.get("/ecommerce/orders", summary="Traer órdenes de la tienda",
            dependencies=[Depends(require_permission("outbound:shipping:manage"))])
async def ecommerce_orders(since: Optional[str] = None) -> dict:
    return await ecommerce.pull_orders(since=since)


# ── ERP ───────────────────────────────────────────────────────────────────────
@router.get("/erp/purchase-orders", summary="Traer OCs del ERP",
            dependencies=[Depends(require_permission("inbound:po:create"))])
async def erp_pull_pos(since: Optional[str] = None) -> dict:
    return await erp.pull_purchase_orders(since=since)


@router.get("/erp/sales-orders", summary="Traer SOs del ERP",
            dependencies=[Depends(require_permission("inbound:po:create"))])
async def erp_pull_sos(since: Optional[str] = None) -> dict:
    return await erp.pull_sales_orders(since=since)


# ── Regulatorio Panamá ────────────────────────────────────────────────────────
@router.post("/regulatory/dam", summary="Generar y enviar DAM a ANA/SIGA (REG-001)",
             dependencies=[Depends(require_permission("outbound:shipping:manage"))])
async def regulatory_dam(declaration: dict = Body(...)) -> dict:
    return await ana_siga.submit_dam(declaration)


@router.post("/regulatory/invoice", summary="Generar y enviar factura electrónica DGI (REG-002)",
             dependencies=[Depends(require_permission("outbound:shipping:manage"))])
async def regulatory_invoice(document: dict = Body(...)) -> dict:
    return await dgi.submit_invoice(document)
