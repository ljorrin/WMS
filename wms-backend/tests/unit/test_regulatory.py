"""Tests de builders regulatorios (REG-001/002) — puro código, sin red ni BD."""
import os
for _k, _v in {"SECRET_KEY": "x" * 40, "DATABASE_URL": "postgresql+asyncpg://u:p@h/d",
               "DATABASE_SYNC_URL": "postgresql://u:p@h/d", "REDIS_URL": "redis://h/0"}.items():
    os.environ.setdefault(_k, _v)
from app.integrations.regulatory.ana_siga import build_dam_xml
from app.integrations.regulatory.dgi import build_invoice


def test_dam_xml_valido():
    xml = build_dam_xml({
        "regime": "IMPORTACION", "declarant_ruc": "12345-6",
        "importer": {"name": "Acme", "ruc": "9-99-99"},
        "items": [{"tariff_code": "8471.30", "description": "Laptop", "quantity": 2, "unit_value": 500}],
        "currency": "USD",
    })
    from xml.etree import ElementTree as ET
    root = ET.fromstring(xml)
    assert root.tag == "DAM"
    assert root.find("Totales/ValorTotal").text == "1000.00"


def test_dgi_itbms_7pct():
    det = build_invoice({
        "document_number": "FE-0001",
        "receptor": {"name": "Cliente", "ruc": "8-888-8888"},
        "items": [{"description": "Producto", "quantity": 10, "unit_price": "1.00"}],
    })
    assert det["totales"]["subtotal"] == "10.00"
    assert det["totales"]["itbms"] == "0.70"   # 7%
    assert det["totales"]["total"] == "10.70"
    assert len(det["cufe"]) == 64 and det["qr_payload"].startswith("https://")


def test_dgi_exento():
    det = build_invoice({"document_number": "FE-0002",
                         "items": [{"description": "Exento", "quantity": 1, "unit_price": "100", "itbms_exempt": True}]})
    assert det["totales"]["itbms"] == "0.00"
    assert det["totales"]["total"] == "100.00"
