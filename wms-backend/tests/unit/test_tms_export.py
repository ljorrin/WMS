"""Mapeo Shipment/SO del WMS → OrdenCanonica del TMS (contrato 1.0)."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import uuid4

from app.models.master_data import IndustryType, StorageCondition
from app.models.outbound import PackStatus
from app.services.outbound_service import delivery_defaults_from_customer, shipment_totals_from_packs
from app.services.tms_export_service import (
    build_canonical_order,
    cargo_type_for,
    destination_code,
    priority_for,
)

PA = timezone(timedelta(hours=-5))


def product(**kw):
    base = dict(id=uuid4(), sku="SKU-1", name="Arroz 5kg", gtin_13="7450001000017", gtin_14=None, uom="CJ",
                weight_kg=Decimal("20.5"), volume_m3=Decimal("0.028"), is_hazmat=False,
                storage_condition=StorageCondition.AMBIENT, industry=IndustryType.AGRO_FOOD,
                is_controlled_substance=False, min_temp_celsius=None, max_temp_celsius=None)
    return NS(**{**base, **kw})


def customer(**kw):
    base = dict(id=uuid4(), name="Super CDE", ruc="155-1", contact_name="Ana", contact_phone="+507 6000",
                contact_email="a@b.pa", delivery_address="Av. Centenario", delivery_city="Panamá",
                delivery_province="Panamá", delivery_country="PA", delivery_instructions=None,
                delivery_latitude=Decimal("9.0110000"), delivery_longitude=Decimal("-79.4700000"),
                receiving_hours_from="06:00", receiving_hours_to="14:00", service_time_min=30, gln=None)
    return NS(**{**base, **kw})


def so(cust, lines, **kw):
    base = dict(id=uuid4(), so_number="SO-1", customer_id=cust.id, customer_po_reference=None,
                ship_to_name=None, ship_to_address=None, ship_to_city=None, ship_to_country=None,
                ship_to_phone=None, ship_to_contact_name=None, ship_to_email=None,
                ship_to_latitude=None, ship_to_longitude=None, ruc_cliente=None, cargo_type=None,
                priority=5, service_level="standard", requested_delivery_date=datetime(2026, 10, 6, tzinfo=PA),
                delivery_window_start=None, delivery_window_end=None, service_time_min=None,
                total_amount=Decimal("100"), currency="USD", delivery_instructions=None, lines=lines)
    return NS(**{**base, **kw})


def line(p, qty="10"):
    return NS(product_id=p.id, gtin=None, description=None, quantity_ordered=Decimal(qty),
              quantity_picked=Decimal(qty), quantity_packed=Decimal(qty))


def shipment(order, **kw):
    base = dict(id=uuid4(), so_id=order.id, warehouse_id=uuid4(), shipment_number="SHP-1",
                total_weight_kg=None, total_volume_m3=None, total_boxes=0,
                estimated_delivery=None, notes=None)
    return NS(**{**base, **kw})


def pack(**kw):
    base = dict(status=PackStatus.COMPLETED, box_count=3, total_weight_kg=Decimal("61.5"),
                total_volume_m3=Decimal("0.084"), sscc="074500010000000013")
    return NS(**{**base, **kw})


def test_orden_completa_con_coordenadas_del_cliente_y_carga_del_empaque():
    p, c = product(), customer()
    o = so(c, [line(p)])
    wh = NS(name="CD Milla 8", address="Transístmica", city="San Miguelito", country="PA",
            latitude=Decimal("9.0647"), longitude=Decimal("-79.515"))
    r = build_canonical_order(shipment(o), o, c, wh, {p.id: p}, [pack()])
    assert r["destino"]["lat"] == 9.011 and r["destino"]["lon"] == -79.47
    assert r["destino"]["horario_desde"] == "06:00" and r["destino"]["contacto_telefono"] == "+507 6000"
    assert r["origen"]["lat"] == 9.0647 and r["origen"]["nombre"] == "CD Milla 8"
    assert r["peso_kg"] == 61.5 and r["bultos"] == 3 and r["sscc"] == ["074500010000000013"]
    assert r["tiempo_servicio_min"] == 30 and r["fecha_compromiso"] == "2026-10-06"
    assert r["lineas"][0] == {"sku": "7450001000017", "descripcion": "Arroz 5kg", "cantidad": 10,
                              "uom": "CJ", "temp_objetivo_c": None}
    assert r["faltantes"] == []


def test_direccion_alterna_no_hereda_coordenadas_del_cliente():
    p, c = product(), customer()
    o = so(c, [line(p)], ship_to_address="Otra sucursal")
    r = build_canonical_order(shipment(o), o, c, None, {p.id: p}, [])
    assert r["destino"]["lat"] is None and "destino.lat/lon" in r["faltantes"]
    o2 = so(c, [line(p)], ship_to_address="Otra sucursal", ship_to_latitude=Decimal("9.05"),
            ship_to_longitude=Decimal("-79.457"))
    assert build_canonical_order(shipment(o2), o2, c, None, {p.id: p}, [])["destino"]["lat"] == 9.05


def test_peso_estimado_desde_maestro_si_no_hay_empaque():
    p, c = product(), customer()
    o = so(c, [line(p, "4")])
    r = build_canonical_order(shipment(o), o, c, None, {p.id: p}, [])
    assert r["peso_kg"] == 82.0 and r["advertencias"]


def test_tipo_de_mercancia_y_temperatura():
    frio = product(storage_condition=StorageCondition.REFRIGERATED, min_temp_celsius=Decimal("2"),
                   max_temp_celsius=Decimal("8"))
    c = customer()
    o = so(c, [line(frio)])
    r = build_canonical_order(shipment(o), o, c, None, {frio.id: frio}, [pack()])
    assert r["tipo_mercancia"] == "refrigerada" and r["lineas"][0]["temp_objetivo_c"] == 5.0
    assert cargo_type_for(o, [product(is_hazmat=True), frio]) == "peligrosa"
    assert cargo_type_for(o, [product(industry=IndustryType.PHARMACEUTICAL)]) == "farmaceutica"
    assert cargo_type_for(o, [product(industry=IndustryType.AUTOMOTIVE)]) == "repuestos"
    assert cargo_type_for(NS(cargo_type="fragil"), [frio]) == "fragil"


def test_prioridad():
    assert priority_for(NS(priority=5, service_level="same_day")) == "same_day"
    assert priority_for(NS(priority=1, service_level=None)) == "express"
    assert priority_for(NS(priority=5, service_level="scheduled")) == "programada"
    assert priority_for(NS(priority=5, service_level="standard")) == "normal"


def test_codigo_destino_compatible_con_el_adaptador_del_tms():
    import hashlib
    o = NS(customer_id="cu-1", ship_to_address="Av. Balboa", ship_to_city="Panamá")
    esperado = "WMS-DST-" + hashlib.sha1("cu-1|av. balboa|panamá".encode()).hexdigest()[:12]
    assert destination_code(o) == esperado


def test_defaults_de_entrega_y_totales_de_empaque():
    d = delivery_defaults_from_customer(customer())
    assert d["ship_to_latitude"] == Decimal("9.0110000") and d["ship_to_contact_name"] == "Ana"
    t = shipment_totals_from_packs([pack(), pack(box_count=2, total_weight_kg=Decimal("10"))])
    assert t["total_boxes"] == 5 and t["total_weight_kg"] == Decimal("71.5")
    assert shipment_totals_from_packs([]) == {}


async def _create_so(ship_to: dict):
    from unittest.mock import AsyncMock, MagicMock
    from app.services.outbound_service import OutboundService

    svc = OutboundService.__new__(OutboundService)
    svc.user_id = uuid4()
    svc.so_repo = MagicMock()
    svc.so_repo.get_customer = AsyncMock(return_value=customer())
    svc.so_repo.create = AsyncMock(side_effect=lambda data, lines_data, created_by_id: NS(id=uuid4(), **data))
    return await svc.create_sales_order(uuid4(), uuid4(), datetime.now(PA), [], **ship_to)


def test_so_sin_entrega_hereda_ficha_del_cliente():
    so_ = asyncio.run(_create_so({}))
    assert so_.ship_to_address == "Av. Centenario" and so_.ship_to_latitude == Decimal("9.0110000")
    assert so_.ship_to_contact_name == "Ana" and so_.service_time_min == 30


def test_so_a_otra_direccion_no_hereda_coordenadas_del_cliente():
    so_ = asyncio.run(_create_so({"ship_to_address": "Sucursal Brisas"}))
    assert so_.ship_to_address == "Sucursal Brisas"
    assert getattr(so_, "ship_to_latitude", None) is None and getattr(so_, "ship_to_city", None) is None
    assert so_.ship_to_phone == "+507 6000"  # el contacto sí se hereda
