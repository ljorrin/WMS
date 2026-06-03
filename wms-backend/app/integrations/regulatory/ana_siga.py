"""ANA/SIGA — Declaración Aduanera de Mercancías (DAM) — REG-001.

Construye el XML de la DAM a partir de un despacho/orden y lo envía a SIGA.
Configurar en despliegue: SIGA_BASE_URL, SIGA_API_KEY, SIGA_ENVIRONMENT.
"""

from __future__ import annotations

from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from app.integrations import config, http_client


def build_dam_xml(declaration: dict) -> str:
    """Construye el XML de la DAM. `declaration` admite:
      regime, customs_office, declarant_ruc, importer{name,ruc,address},
      transport{mode,carrier,bl_number}, currency, items[{tariff_code,description,
      origin_country,quantity,uom,unit_value,gross_weight_kg,net_weight_kg}].
    """
    root = ET.Element("DAM", attrib={"version": "1.0", "pais": "PA"})
    ET.SubElement(root, "FechaEmision").text = datetime.now(timezone.utc).isoformat()
    ET.SubElement(root, "Regimen").text = str(declaration.get("regime", "IMPORTACION"))
    ET.SubElement(root, "Aduana").text = str(declaration.get("customs_office", ""))
    ET.SubElement(root, "DeclaranteRUC").text = str(declaration.get("declarant_ruc", ""))

    imp = declaration.get("importer", {}) or {}
    e_imp = ET.SubElement(root, "Importador")
    ET.SubElement(e_imp, "Nombre").text = str(imp.get("name", ""))
    ET.SubElement(e_imp, "RUC").text = str(imp.get("ruc", ""))
    ET.SubElement(e_imp, "Direccion").text = str(imp.get("address", ""))

    tr = declaration.get("transport", {}) or {}
    e_tr = ET.SubElement(root, "Transporte")
    ET.SubElement(e_tr, "Modalidad").text = str(tr.get("mode", ""))
    ET.SubElement(e_tr, "Transportista").text = str(tr.get("carrier", ""))
    ET.SubElement(e_tr, "BL").text = str(tr.get("bl_number", ""))

    e_items = ET.SubElement(root, "Items")
    total_value = 0.0
    for i, it in enumerate(declaration.get("items", []) or [], start=1):
        e = ET.SubElement(e_items, "Item", attrib={"linea": str(i)})
        ET.SubElement(e, "CodigoArancelario").text = str(it.get("tariff_code", ""))
        ET.SubElement(e, "Descripcion").text = str(it.get("description", ""))
        ET.SubElement(e, "PaisOrigen").text = str(it.get("origin_country", ""))
        qty = float(it.get("quantity", 0) or 0)
        uv = float(it.get("unit_value", 0) or 0)
        ET.SubElement(e, "Cantidad").text = f"{qty:g}"
        ET.SubElement(e, "UnidadMedida").text = str(it.get("uom", "UN"))
        ET.SubElement(e, "ValorUnitario").text = f"{uv:.2f}"
        ET.SubElement(e, "ValorTotal").text = f"{qty * uv:.2f}"
        ET.SubElement(e, "PesoBrutoKg").text = f"{float(it.get('gross_weight_kg', 0) or 0):.3f}"
        ET.SubElement(e, "PesoNetoKg").text = f"{float(it.get('net_weight_kg', 0) or 0):.3f}"
        total_value += qty * uv

    tot = ET.SubElement(root, "Totales")
    ET.SubElement(tot, "Moneda").text = str(declaration.get("currency", "USD"))
    ET.SubElement(tot, "ValorTotal").text = f"{total_value:.2f}"

    return ET.tostring(root, encoding="unicode")


async def submit_dam(declaration: dict) -> dict:
    """Construye y envía la DAM a SIGA (si está configurado)."""
    xml = build_dam_xml(declaration)
    cfg = config.siga_config()
    result = await http_client.call(cfg, "POST", "/dam", json={"dam_xml": xml})
    result["dam_xml"] = xml
    result["environment"] = cfg.extra.get("environment")
    return result
