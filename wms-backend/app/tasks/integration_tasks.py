"""Tareas Celery de integración (ERP/eCommerce). Best-effort y parametrizadas.

Las funciones de integración son async; se ejecutan dentro de la tarea Celery
(sync) con asyncio.run. Si la integración no está configurada, retornan
`configured=False` sin llamadas externas.
"""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.tasks.celery_app import celery_app

log = get_logger(__name__)


def _run(coro):
    return asyncio.run(coro)


@celery_app.task(name="integrations.pull_erp_orders")
def pull_erp_orders(since: str | None = None) -> dict:
    """Trae OCs y SOs nuevas del ERP (si está configurado)."""
    from app.integrations import erp
    pos = _run(erp.pull_purchase_orders(since=since))
    sos = _run(erp.pull_sales_orders(since=since))
    log.info("celery.erp_pull", pos_ok=pos.get("ok"), sos_ok=sos.get("ok"))
    return {"purchase_orders": pos, "sales_orders": sos}


@celery_app.task(name="integrations.sync_ecommerce_stock")
def sync_ecommerce_stock(items: list[dict] | None = None) -> dict:
    """Empuja niveles de stock a la tienda. `items`=[{sku, available}].

    El detalle por tenant se inyecta cuando hay credenciales; sin configurar,
    no realiza llamadas externas.
    """
    from app.integrations import ecommerce
    result = _run(ecommerce.sync_stock(items or []))
    log.info("celery.ecommerce_sync", ok=result.get("ok"), configured=result.get("configured"))
    return result


@celery_app.task(name="integrations.update_fulfillment")
def update_fulfillment(order_id: str, tracking_number: str, carrier: str) -> dict:
    """Actualiza el estado de fulfillment/tracking de una orden en la tienda."""
    from app.integrations import ecommerce
    return _run(ecommerce.update_fulfillment(order_id, tracking_number, carrier))
