"""
WMS Panamá — Dashboard en tiempo real vía WebSocket (FR-070)
=============================================================
Canal WebSocket que empuja las métricas de los dashboards (inbound, outbound,
inventario) cada pocos segundos (<5s), sin recargar la página. La autenticación
se realiza con el access token JWT pasado como query param `?token=`.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger

router = APIRouter()
log = get_logger(__name__)

_PUSH_INTERVAL_SECONDS = 5


def _jsonable(value):
    """Convierte Decimal/UUID/None a tipos serializables por JSON."""
    from decimal import Decimal
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


@router.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket, token: str = Query(...)):
    """Empuja KPIs de inbound/outbound/inventario cada ~5s hasta desconexión."""
    from app.core.security import decode_access_token
    from jose import JWTError

    await websocket.accept()

    # Autenticación por token (query param)
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
        tenant_id = uuid.UUID(payload["tid"])
    except (JWTError, KeyError, ValueError, TypeError):
        await websocket.close(code=4401)
        return

    from app.db.session import AsyncSessionLocal
    from app.services.inbound_service import InboundService
    from app.services.outbound_service import OutboundService
    from app.services.inventory_service import InventoryService

    try:
        while True:
            try:
                async with AsyncSessionLocal() as db:
                    inbound = await InboundService(db, tenant_id, user_id).get_dashboard_metrics()
                    outbound = await OutboundService(db, tenant_id, user_id).get_dashboard_metrics()
                    inventory = await InventoryService(db, tenant_id, user_id).get_dashboard_metrics()
                await websocket.send_json(_jsonable({
                    "type": "dashboard",
                    "inbound": inbound,
                    "outbound": outbound,
                    "inventory": inventory,
                }))
            except Exception as exc:  # no derribar el socket por un fallo de query
                log.warning("ws_dashboard_metrics_failed", error=str(exc))
                await websocket.send_json({"type": "error", "detail": "No se pudieron calcular las métricas."})
            await asyncio.sleep(_PUSH_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        return
    except Exception:  # cierre limpio ante cualquier error de transporte
        try:
            await websocket.close()
        except Exception:
            pass
