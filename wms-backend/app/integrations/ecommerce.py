"""Adaptador eCommerce genérico (Shopify/WooCommerce/Magento/VTEX/MercadoLibre/Amazon).

Sincroniza inventario hacia la tienda, trae órdenes y actualiza estado de
fulfillment/tracking. La plataforma se selecciona por ECOMMERCE_PLATFORM.
"""

from __future__ import annotations

from app.integrations import config, http_client


async def sync_stock(items: list[dict]) -> dict:
    """Empuja niveles de stock (sku, available) a la tienda."""
    cfg = config.ecommerce_config()
    return await http_client.call(cfg, "POST", "/inventory/sync",
                                  json={"platform": cfg.extra["platform"], "items": items})


async def pull_orders(since: str | None = None) -> dict:
    cfg = config.ecommerce_config()
    return await http_client.call(cfg, "GET", "/orders", params={"since": since})


async def update_fulfillment(order_id: str, tracking_number: str, carrier: str) -> dict:
    cfg = config.ecommerce_config()
    return await http_client.call(cfg, "POST", f"/orders/{order_id}/fulfillment",
                                  json={"tracking_number": tracking_number, "carrier": carrier})
