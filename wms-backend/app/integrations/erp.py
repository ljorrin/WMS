"""Adaptador ERP genérico (SAP/Oracle/Dynamics/Odoo vía REST) — INT/ERP.

Implementa el contrato bidireccional descrito en el SRS: empuje de
OC/ASN/GRN/ajustes/despachos al ERP y recepción de órdenes/maestros. El tipo de
ERP se selecciona por ERP_TYPE; el mapeo de payload se normaliza a un formato
canónico (el adaptador específico puede sobreescribir `map_*`).
"""

from __future__ import annotations

from app.integrations import config, http_client


async def push_goods_receipt(grn_payload: dict) -> dict:
    """Notifica una recepción (GRN) al ERP."""
    cfg = config.erp_config()
    body = {"document_type": "GRN", "erp_type": cfg.extra["type"], "payload": grn_payload}
    return await http_client.call(cfg, "POST", "/inventory/goods-receipts", json=body)


async def push_inventory_adjustment(adj_payload: dict) -> dict:
    cfg = config.erp_config()
    body = {"document_type": "ADJUSTMENT", "payload": adj_payload}
    return await http_client.call(cfg, "POST", "/inventory/adjustments", json=body)


async def push_shipment(shipment_payload: dict) -> dict:
    cfg = config.erp_config()
    body = {"document_type": "SHIPMENT", "payload": shipment_payload}
    return await http_client.call(cfg, "POST", "/sales/shipments", json=body)


async def pull_purchase_orders(since: str | None = None) -> dict:
    """Trae OCs nuevas del ERP para crearlas en el WMS."""
    cfg = config.erp_config()
    return await http_client.call(cfg, "GET", "/purchasing/orders", params={"since": since})


async def pull_sales_orders(since: str | None = None) -> dict:
    cfg = config.erp_config()
    return await http_client.call(cfg, "GET", "/sales/orders", params={"since": since})
