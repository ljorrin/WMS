"""
WMS Panamá — Generación de documentos de despacho (FR-061)
===========================================================
Genera en PDF la Lista de Empaque / Remisión de un envío (Shipment) a partir
de la Orden de Venta (SalesOrder) y sus líneas. La DAM de exportación (ANA)
queda pendiente del módulo regulatorio (REG-001).
"""

from __future__ import annotations

import io
from datetime import datetime, timezone


def build_packing_list_pdf(shipment, sales_order) -> bytes:
    """Construye la lista de empaque/remisión en PDF y devuelve los bytes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Lista de Empaque {getattr(shipment, 'shipment_number', '')}",
    )
    styles = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=styles["Title"], fontSize=18, textColor=colors.HexColor("#1F4E79"))
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#666666"))
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9)

    el = []
    el.append(Paragraph("Lista de Empaque / Remisión", h))
    el.append(Paragraph("WMS Panamá — Documento de despacho", sub))
    el.append(Spacer(1, 10))

    def g(o, attr, default="—"):
        v = getattr(o, attr, None)
        return default if v is None else str(v)

    info = [
        ["Envío:", g(shipment, "shipment_number"), "Fecha:", datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")],
        ["Orden de Venta:", g(sales_order, "so_number"), "Transportista:", g(shipment, "carrier_name")],
        ["Cliente:", g(sales_order, "ship_to_name", g(sales_order, "customer_id")), "Tracking:", g(shipment, "tracking_number")],
        ["Dirección:", g(sales_order, "ship_to_address"), "Ciudad:", g(sales_order, "ship_to_city")],
    ]
    t_info = Table(info, colWidths=[3 * cm, 6 * cm, 3 * cm, 5 * cm])
    t_info.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#444444")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#444444")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    el.append(t_info)
    el.append(Spacer(1, 14))

    # Tabla de líneas
    header = ["#", "Producto (ID)", "Descripción", "Cant. pedida", "Cant. despachada"]
    rows = [header]
    lines = list(getattr(sales_order, "lines", []) or [])
    total_ord = total_shp = 0
    for ln in lines:
        qo = getattr(ln, "quantity_ordered", 0) or 0
        qs = getattr(ln, "quantity_shipped", 0) or 0
        total_ord += float(qo); total_shp += float(qs)
        rows.append([
            str(getattr(ln, "line_number", "")),
            str(getattr(ln, "product_id", ""))[:18],
            (getattr(ln, "description", "") or "")[:40],
            f"{float(qo):g}", f"{float(qs):g}",
        ])
    if not lines:
        rows.append(["—", "—", "Sin líneas", "0", "0"])
    rows.append(["", "", "TOTAL", f"{total_ord:g}", f"{total_shp:g}"])

    t = Table(rows, colWidths=[1.2 * cm, 4.3 * cm, 6.5 * cm, 2.7 * cm, 2.8 * cm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
        ("ALIGN", (3, 0), (4, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#EEF3F8")]),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#DDE7F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    el.append(t)
    el.append(Spacer(1, 26))
    el.append(Paragraph("Cajas: %s · Peso (kg): %s" % (g(shipment, "total_boxes", "0"), g(shipment, "total_weight_kg", "—")), small))
    el.append(Spacer(1, 30))
    firmas = Table([["_______________________", "_______________________"],
                    ["Despachado por", "Recibido por (conforme)"]], colWidths=[8 * cm, 8 * cm])
    firmas.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#666666"))]))
    el.append(firmas)

    doc.build(el)
    return buf.getvalue()
