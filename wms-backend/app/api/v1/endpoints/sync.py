"""
WMS Panamá — Sincronización Offline (FR-006)
=============================================
Recibe un lote de operaciones encoladas por el dispositivo RF/móvil mientras
estuvo sin conexión y las aplica de forma idempotente (dedupe por client_op_id
vía Redis + dentro del lote). Cada operación se procesa de forma independiente:
un fallo aislado no detiene el resto.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Body

from app.core.dependencies import CurrentUserDep, DBDep
from app.core.logging import get_logger
from app.db.redis import cache_get, cache_set
from app.services.inbound_service import InboundService
from app.services.outbound_service import OutboundService

router = APIRouter()
log = get_logger(__name__)


async def _h_pick_complete(svc_in, svc_out, p):
    return await svc_out.complete_pick_task(
        task_id=UUID(p["task_id"]),
        quantity_picked=Decimal(str(p["quantity_picked"])),
        sscc_scanned=p.get("sscc_scanned"), gtin_scanned=p.get("gtin_scanned"),
        short_reason=p.get("short_reason"), notes=p.get("notes"),
    )


async def _h_pick_start(svc_in, svc_out, p):
    await svc_out.start_pick_task(UUID(p["task_id"])); return {"ok": True}


async def _h_putaway_complete(svc_in, svc_out, p):
    await svc_in.complete_putaway_task(
        task_id=UUID(p["task_id"]),
        actual_location_id=UUID(p["actual_location_id"]),
        override_reason=p.get("override_reason"),
    ); return {"ok": True}


async def _h_putaway_start(svc_in, svc_out, p):
    await svc_in.start_putaway_task(UUID(p["task_id"])); return {"ok": True}


async def _h_grn_confirm(svc_in, svc_out, p):
    await svc_in.confirm_grn(UUID(p["grn_id"])); return {"ok": True}


_HANDLERS = {
    "picking.complete": _h_pick_complete,
    "picking.start": _h_pick_start,
    "putaway.complete": _h_putaway_complete,
    "putaway.start": _h_putaway_start,
    "grn.confirm": _h_grn_confirm,
}


@router.post("/operations", summary="Aplicar operaciones encoladas offline (idempotente)")
async def sync_operations(current_user: CurrentUserDep, db: DBDep, payload: dict = Body(...)) -> dict:
    ops = payload.get("operations", []) or []
    svc_in = InboundService(db=db, tenant_id=current_user.tenant_id, user_id=current_user.id)
    svc_out = OutboundService(db=db, tenant_id=current_user.tenant_id, user_id=current_user.id)
    results: list[dict] = []
    seen: set[str] = set()

    for op in ops:
        cid = str(op.get("client_op_id") or "")
        typ = str(op.get("type") or "")
        if not cid:
            results.append({"client_op_id": cid, "status": "error", "detail": "client_op_id requerido"}); continue
        if cid in seen:
            results.append({"client_op_id": cid, "status": "duplicate"}); continue
        seen.add(cid)
        rkey = f"sync:op:{current_user.tenant_id}:{cid}"
        try:
            if await cache_get(rkey):
                results.append({"client_op_id": cid, "status": "duplicate"}); continue
        except Exception:
            pass  # Redis no disponible → dedupe sólo dentro del lote
        handler = _HANDLERS.get(typ)
        if handler is None:
            results.append({"client_op_id": cid, "status": "error", "detail": f"tipo no soportado: {typ}"}); continue
        try:
            res = await handler(svc_in, svc_out, op.get("payload") or {})
            await db.commit()
            try:
                await cache_set(rkey, {"applied": True}, expire=7 * 24 * 3600)
            except Exception:
                pass
            results.append({"client_op_id": cid, "status": "applied",
                            "result": res if isinstance(res, (dict, list)) else None})
        except Exception as e:
            await db.rollback()
            log.warning("sync_op_failed", client_op_id=cid, type=typ, error=str(e))
            results.append({"client_op_id": cid, "status": "error", "detail": str(e)})

    applied = sum(1 for r in results if r["status"] == "applied")
    return {"total": len(ops), "applied": applied,
            "duplicates": sum(1 for r in results if r["status"] == "duplicate"),
            "errors": sum(1 for r in results if r["status"] == "error"),
            "results": results}
