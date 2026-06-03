"""DGI — Factura electrónica (DET) con ITBMS — REG-002.

Construye el documento electrónico tributario (DET) con cálculo de ITBMS (7%) y
lo envía a la plataforma DGI. Configurar: DGI_BASE_URL, DGI_API_KEY,
DGI_RUC_EMISOR, DGI_ENVIRONMENT.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.integrations import config, http_client

ITBMS_RATE = Decimal("0.07")  # 7% Panamá


def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_invoice(document: dict) -> dict:
    """Construye el DET. `document` admite:
      receptor{name,ruc,dv,email}, items[{description,quantity,unit_price,
      itbms_exempt(bool)}], document_number, currency.
    Devuelve la estructura del documento con totales e ITBMS calculado.
    """
    cfg = config.dgi_config()
    items_out = []
    subtotal = Decimal("0")
    tax_total = Decimal("0")
    for i, it in enumerate(document.get("items", []) or [], start=1):
        qty = Decimal(str(it.get("quantity", 0) or 0))
        price = _money(it.get("unit_price", 0))
        line_net = _money(qty * price)
        tax = Decimal("0") if it.get("itbms_exempt") else _money(line_net * ITBMS_RATE)
        subtotal += line_net
        tax_total += tax
        items_out.append({
            "linea": i, "descripcion": str(it.get("description", "")),
            "cantidad": f"{qty:g}", "precio_unitario": str(price),
            "valor_neto": str(line_net), "tasa_itbms": "0.07" if tax else "0.00",
            "itbms": str(tax), "valor_total": str(_money(line_net + tax)),
        })
    total = _money(subtotal + tax_total)
    emisor_ruc = cfg.extra.get("ruc_emisor") or "<DGI_RUC_EMISOR>"
    receptor = document.get("receptor", {}) or {}
    doc_number = str(document.get("document_number", ""))
    issued_at = datetime.now(timezone.utc).isoformat()
    # CUFE/folio: hash determinístico (placeholder hasta firma real DGI)
    cufe = hashlib.sha256(f"{emisor_ruc}|{doc_number}|{total}|{issued_at}".encode()).hexdigest().upper()
    return {
        "tipo_documento": "01",  # Factura
        "ambiente": cfg.extra.get("environment"),
        "emisor": {"ruc": emisor_ruc},
        "receptor": {"nombre": receptor.get("name", ""), "ruc": receptor.get("ruc", ""),
                     "dv": receptor.get("dv", ""), "email": receptor.get("email", "")},
        "numero_documento": doc_number,
        "fecha_emision": issued_at,
        "moneda": document.get("currency", "USD"),
        "items": items_out,
        "totales": {"subtotal": str(_money(subtotal)), "itbms": str(_money(tax_total)),
                    "total": str(total)},
        "cufe": cufe,
        "qr_payload": f"https://dgi-fep.mef.gob.pa/Consultas/FacturasPorCUFE?CUFE={cufe}",
    }


async def submit_invoice(document: dict) -> dict:
    """Construye y envía el DET a DGI (si está configurado)."""
    det = build_invoice(document)
    cfg = config.dgi_config()
    result = await http_client.call(cfg, "POST", "/det", json=det)
    result["document"] = det
    result["environment"] = cfg.extra.get("environment")
    return result
