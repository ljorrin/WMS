"""
WMS Panamá — Endpoints de Integraciones (ERP, eCommerce, Transporte, Regulatorio)
==================================================================================
Exponen la lógica de los adaptadores de `app/integrations`. Las credenciales y
endpoints se parametrizan por entorno; sin configurar, las acciones devuelven
`configured=False` (sin llamadas externas) y `/status` indica qué falta definir.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.dependencies import CurrentUserDep, DBDep, require_permission
from app.integrations import carrier, config, ecommerce, erp
from app.integrations.regulatory import ana_siga, dgi
from app.models.outbound import ShipmentStatus
from app.services.tms_export_service import (
    CONTRATO_VERSION,
    TmsExportService,
    TmsPushService,
    tms_missing_config,
)

router = APIRouter()


@router.get("/status", summary="Estado de configuración de integraciones")
async def integrations_status(current_user: CurrentUserDep) -> dict:
    """Indica qué integraciones están configuradas y qué variables faltan."""
    cfgs = {
        "erp": config.erp_config(), "ecommerce": config.ecommerce_config(),
        "carrier": config.carrier_config(), "siga": config.siga_config(),
        "dgi": config.dgi_config(),
    }
    out = {name: {"configured": c.configured, "missing": c.missing, "extra": c.extra}
           for name, c in cfgs.items()}
    tms = config.tms_config()
    missing = tms_missing_config(tms)
    out["tms"] = {"configured": not missing, "missing": missing,
                  "extra": {"base_url": tms.base_url, "connector_id": tms.extra.get("connector_id")}}
    return out


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


# ── TMS (contrato canónico 1.0) ───────────────────────────────────────────────
@router.get("/tms/orders", summary="Envíos listos para el TMS en formato canónico",
            dependencies=[Depends(require_permission("outbound:shipping:manage"))])
async def tms_orders(
    db: DBDep,
    current_user: CurrentUserDep,
    status: ShipmentStatus = Query(ShipmentStatus.PENDING),
    warehouse_id: Optional[UUID] = Query(None),
    only_ready: bool = Query(False, description="Solo órdenes sin datos faltantes"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
) -> dict:
    """Órdenes de transporte (`OrdenCanonica` del TMS) con destino georreferenciado,
    origen, carga, SSCC, tipo de mercancía, ventanas y líneas por GTIN.
    Cada orden incluye `faltantes` y `advertencias` para corregir en el WMS."""
    svc = TmsExportService(db, current_user.tenant_id)
    items, total = await svc.list_orders(status, warehouse_id, page, page_size)
    if only_ready:
        items = [o for o in items if not o["faltantes"]]
    return {"contrato": CONTRATO_VERSION, "items": items, "total": total,
            "page": page, "page_size": page_size,
            "incompletas": sum(1 for o in items if o["faltantes"])}


class TmsSendRequest(BaseModel):
    shipment_ids: list[UUID] = Field(default_factory=list, max_length=500)
    all_pending: bool = Field(False, description="Todos los envíos pendientes aún no enviados")
    force: bool = Field(False, description="Enviar aunque falten datos (el TMS intentará geocodificar)")


@router.post("/tms/send", summary="Enviar envíos pendientes al TMS (push del contrato canónico)",
             dependencies=[Depends(require_permission("outbound:shipping:manage"))])
async def tms_send(payload: TmsSendRequest, db: DBDep, current_user: CurrentUserDep) -> dict:
    cfg = config.tms_config()
    missing = tms_missing_config(cfg)
    if missing:
        raise HTTPException(status_code=503,
                            detail=f"Integración TMS no configurada. Definir: {', '.join(missing)}.")
    svc = TmsPushService(db, current_user.tenant_id, cfg)
    ids = await svc.pending_ids() if payload.all_pending else payload.shipment_ids
    if not ids:
        return {"enviadas": 0, "resultados": []}
    results = await svc.send(ids, force=payload.force)
    await db.commit()
    ok = sum(1 for r in results if r["resultado"] in ("creada", "ya_existia"))
    return {"enviadas": ok, "con_error": len(results) - ok, "resultados": results}


@router.post("/tms/preview", summary="Vista previa de lo que se enviará al TMS",
             dependencies=[Depends(require_permission("outbound:shipping:manage"))])
async def tms_preview(payload: TmsSendRequest, db: DBDep, current_user: CurrentUserDep) -> dict:
    """Mismas órdenes canónicas que `/tms/send` enviaría, con `faltantes` y `advertencias`,
    para confirmar antes del envío. No llama al TMS."""
    cfg = config.tms_config()
    push = TmsPushService(db, current_user.tenant_id, cfg)
    ids = await push.pending_ids() if payload.all_pending else payload.shipment_ids
    items = await push.export.preview(ids)
    return {"items": items, "total": len(items),
            "incompletas": sum(1 for o in items if o["faltantes"]),
            "configured": not tms_missing_config(cfg)}


@router.get("/tms/orders/{shipment_id}", summary="Un envío en formato canónico del TMS",
            dependencies=[Depends(require_permission("outbound:shipping:manage"))])
async def tms_order(shipment_id: UUID, db: DBDep, current_user: CurrentUserDep) -> dict:
    order = await TmsExportService(db, current_user.tenant_id).get_order(shipment_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Envío no encontrado.")
    return order


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
