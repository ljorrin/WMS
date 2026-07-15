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


def build_sscc_label_pdf(pack_task, sales_order=None, company_name=None) -> bytes:
    """
    Construye la etiqueta de bulto (SSCC) en PDF para un PackTask completado,
    replicando el diseño de "Etiqueta de paleta estándar" de la Guía AECOC/GS1
    "Iniciación a la codificación GS1-128" (pág. 3 y Anexo I): tarjeta con borde
    naranja, cabecera con razón social, título del bulto, cuadrícula de datos y
    la línea de SSCC sobre el símbolo de barras.

    Contenido del símbolo:
      Start Code + FNC1 + AI(00) + SSCC(18) + checksum + Stop.

    Se codifica como "bulto de picking/multireferencia" (pág. 7 de la guía):
    solo el SSCC (IA 00), sin GTIN de producto, porque un PackTask agrupa
    ítems de varias líneas de una SO — el detalle del contenido viaja en el
    sistema (equivalente al mensaje EDI DESADV que menciona la guía), no en
    el símbolo. Reportlab usa Code Set C automáticamente por ser numérico de
    longitud par, tal como recomienda la guía para optimizar espacio.

    Si el SSCC capturado no son 18 dígitos numéricos (formato exigido por el
    IA 00), se degrada a un Code128 plano del valor tal cual, marcado como no
    conforme GS1-128 en la etiqueta.
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.graphics.barcode import createBarcodeDrawing
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    FNC1 = "\xf1"
    AI_SSCC = "00"

    ORANGE = colors.HexColor("#E8863C")
    CREAM = colors.HexColor("#FBEEDD")
    NAVY = colors.HexColor("#1F4E79")
    GRAY = colors.HexColor("#666666")

    # Tamaño de "etiqueta de paleta estándar" de la guía (Anexo I, pág. 14)
    label_size = (148 * mm, 210 * mm)
    outer_margin = 4 * mm
    card_margin = 8 * mm

    def g(o, attr, default="—"):
        v = getattr(o, attr, None) if o is not None else None
        return default if v in (None, "") else str(v)

    def draw_card_border(canvas_obj, doc_obj):
        canvas_obj.saveState()
        w, h = label_size
        canvas_obj.setFillColor(CREAM)
        canvas_obj.setStrokeColor(ORANGE)
        canvas_obj.setLineWidth(1.4)
        canvas_obj.roundRect(outer_margin, outer_margin, w - 2 * outer_margin, h - 2 * outer_margin,
                              radius=6 * mm, fill=1, stroke=1)
        canvas_obj.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=label_size,
        leftMargin=card_margin, rightMargin=card_margin,
        topMargin=card_margin, bottomMargin=card_margin,
        title=f"Etiqueta {g(pack_task, 'pack_task_number')}",
    )
    styles = getSampleStyleSheet()
    company_style = ParagraphStyle("company", parent=styles["Heading1"], fontSize=15,
                                    textColor=NAVY, leading=17)
    address_style = ParagraphStyle("address", parent=styles["Normal"], fontSize=8, textColor=GRAY)
    title_style = ParagraphStyle("title", parent=styles["Heading2"], fontSize=13, leading=15)
    label_style = ParagraphStyle("label", parent=styles["Normal"], fontSize=8, textColor=GRAY)
    value_style = ParagraphStyle("value", parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold")
    sscc_label_style = ParagraphStyle("ssccLabel", parent=styles["Normal"], fontSize=9, textColor=GRAY)
    sscc_value_style = ParagraphStyle("ssccValue", parent=styles["Normal"], fontName="Courier-Bold", fontSize=13)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=7.5, textColor=colors.red)

    sscc = g(pack_task, "sscc", "")
    is_valid_sscc = bool(sscc) and sscc.isdigit() and len(sscc) == 18
    content_width = label_size[0] - 2 * card_margin

    el = []

    # ── Cabecera: razón social de la empresa (campo A obligatorio) ──
    header = Table(
        [[Paragraph(company_name or "WMS Panamá", company_style)],
         [Paragraph("Sistema de Gestión de Almacén — Panamá", address_style)]],
        colWidths=[content_width],
    )
    header.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    el.append(header)

    # ── Título del bulto (equivalente a "PALET LECHE ENTERA 1L") ──
    title_text = g(sales_order, "so_number", g(pack_task, "pack_task_number"))
    customer = g(sales_order, "ship_to_name", g(sales_order, "customer_id", ""))
    title = Table(
        [[Paragraph(f"ORDEN {title_text}" + (f" — {customer}" if customer and customer != "—" else ""), title_style)]],
        colWidths=[content_width],
    )
    title.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("LINEABOVE", (0, 0), (-1, 0), 0, colors.white),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    el.append(title)

    # ── Cuadrícula de datos (equivalente a GS1/CANTIDAD/LOTE + F.CONSUMO PREFERENTE) ──
    grid = Table(
        [
            [Paragraph("PACK Nº", label_style), Paragraph(g(pack_task, "pack_task_number"), value_style),
             Paragraph("TIPO DE CAJA", label_style), Paragraph(g(pack_task, "box_type"), value_style)],
            [Paragraph("CAJAS", label_style), Paragraph(g(pack_task, "box_count", "1"), value_style),
             Paragraph("PESO (KG)", label_style), Paragraph(g(pack_task, "total_weight_kg"), value_style)],
        ],
        colWidths=[content_width * 0.22, content_width * 0.28, content_width * 0.22, content_width * 0.28],
    )
    grid.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BBBBBB")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    el.append(grid)

    # ── Línea SSCC (equivalente a "SSCC: 384567890000000060") ──
    if is_valid_sscc:
        sscc_text = f"(00) {sscc}"
    elif sscc:
        sscc_text = sscc
    else:
        sscc_text = "Sin asignar"
    sscc_row = Table(
        [[Paragraph("SSCC", sscc_label_style), Paragraph(sscc_text, sscc_value_style)]],
        colWidths=[content_width * 0.22, content_width * 0.78],
    )
    sscc_row.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    el.append(sscc_row)

    if sscc and not is_valid_sscc:
        el.append(Spacer(1, 3))
        el.append(Paragraph(
            "El SSCC capturado no tiene 18 dígitos — no cumple el formato GS1 del "
            "IA (00); el código de abajo no es un símbolo GS1-128 válido.",
            small,
        ))

    el.append(Spacer(1, 10))

    # ── Símbolo de barras, centrado, dentro de una caja blanca como en la guía ──
    if sscc:
        barcode_value = (FNC1 + AI_SSCC + sscc) if is_valid_sscc else sscc
        drawing = createBarcodeDrawing(
            "Code128", value=barcode_value,
            barHeight=36 * mm, barWidth=1.0, humanReadable=False,
        )
        barcode_box = Table([[drawing]], colWidths=[content_width])
        barcode_box.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        el.append(barcode_box)
    else:
        el.append(Paragraph("(sin SSCC — no se pudo generar el código de barras)", small))

    doc.build(el, onFirstPage=draw_card_border, onLaterPages=draw_card_border)
    return buf.getvalue()
