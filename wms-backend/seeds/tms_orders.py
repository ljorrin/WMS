"""
WMS Panama — Seed de órdenes listas para el TMS
=================================================
Crea 12 envíos (`Shipment` en estado PENDING, SO en PACKED, empaque completado
con SSCC) con TODOS los datos del contrato canónico del TMS: destino con
coordenadas reales de Panamá, contacto, horario de recepción, ventana de
entrega, tiempo de servicio, peso/volumen/bultos, tipo de mercancía (seco,
refrigerado, farma, peligroso, repuestos) y líneas por GTIN.

El TMS los captura con el conector `wms_panama` (Sincronizar) y puede
planificarlos y despacharlos sin completar datos a mano.

Idempotente: reutiliza clientes/productos por código y no duplica envíos
(`SHP-TMS-xxxx`); al re-ejecutarlo, los envíos aún PENDING se re-programan a
partir de hoy (útil para demos en días posteriores). Requiere haber corrido `seeds.run_all` (tenant `wms-demo`).

Uso (desde wms-backend/):
    python -m seeds.tms_orders
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.gs1 import generate_sscc, gs1_check_digit
from app.db.session import AsyncSessionLocal
from app.models.core import Company, Tenant, User, Warehouse, WarehouseStatus
from app.models.master_data import (
    Customer, CustomerType, IndustryType, Product, ProductStatus, StorageCondition, TrackingType,
)
from app.models.outbound import (
    PackStatus, PackTask, SalesOrder, SalesOrderLine, Shipment, ShipmentStatus,
    ShippingCarrierType, SOLineStatus, SOStatus,
)

PA_TZ = timezone(timedelta(hours=-5))  # Panamá no aplica horario de verano
GS1_PREFIX = "7450001"                  # 745 = GS1 Panamá

# Bodega origen (solo se completa si la bodega no tiene coordenadas)
WAREHOUSE_GEO = {
    "address": "Vía Transístmica, Milla 8, San Miguelito",
    "city": "San Miguelito", "province": "Panamá",
    "latitude": Decimal("9.0647000"), "longitude": Decimal("-79.5150000"),
}

# sku, nombre, industria, condición, tmin, tmax, peso_kg, volumen_m3, hazmat, clase ONU
PRODUCTS = [
    ("TMS-ARZ-5KG", "Arroz Grano Largo 5kg (fardo 4u)", IndustryType.AGRO_FOOD, StorageCondition.AMBIENT,
     None, None, "20.5", "0.028000", False, None),
    ("TMS-ACE-1L", "Aceite Vegetal 1L (caja 12u)", IndustryType.AGRO_FOOD, StorageCondition.AMBIENT,
     None, None, "11.8", "0.016000", False, None),
    ("TMS-LEC-UHT", "Leche UHT 1L (caja 12u)", IndustryType.AGRO_FOOD, StorageCondition.AMBIENT,
     None, None, "12.6", "0.015000", False, None),
    ("TMS-YOG-1KG", "Yogurt Natural 1kg (caja 6u)", IndustryType.AGRO_FOOD, StorageCondition.REFRIGERATED,
     "2", "8", "6.4", "0.009000", False, None),
    ("TMS-POL-CONG", "Pechuga de Pollo Congelada 2kg (caja 6u)", IndustryType.AGRO_FOOD, StorageCondition.FROZEN,
     "-22", "-18", "12.3", "0.018000", False, None),
    ("TMS-ACET-500", "Acetaminofén 500mg x100 (caja 24u)", IndustryType.PHARMACEUTICAL, StorageCondition.CONTROLLED,
     "15", "25", "3.2", "0.006000", False, None),
    ("TMS-INS-10ML", "Insulina 10ml (caja 10u)", IndustryType.PHARMACEUTICAL, StorageCondition.REFRIGERATED,
     "2", "8", "0.9", "0.002000", False, None),
    ("TMS-ALC-1GL", "Alcohol Isopropílico 1gal (caja 4u)", IndustryType.CHEMICAL, StorageCondition.FLAMMABLE,
     None, None, "15.6", "0.020000", True, "3"),
    ("TMS-FIL-ACE", "Filtro de Aceite Motor (caja 20u)", IndustryType.AUTOMOTIVE, StorageCondition.AMBIENT,
     None, None, "7.5", "0.012000", False, None),
    ("TMS-PAS-BRK", "Pastillas de Freno Delanteras (caja 10u)", IndustryType.AUTOMOTIVE, StorageCondition.AMBIENT,
     None, None, "9.8", "0.010000", False, None),
]

# código, nombre, RUC, contacto, teléfono, email, dirección, ciudad, provincia, lat, lon, desde, hasta, min servicio
CUSTOMERS = [
    ("TMS-CLI-01", "Supermercado Costa del Este", "155612345-2-2019", "Ana Morales", "+507 6612-1001",
     "recepcion@super-cde.pa", "Av. Centenario, Plaza Costa del Este, Local 3", "Panamá", "Panamá",
     "9.0110000", "-79.4700000", "06:00", "14:00", 30),
    ("TMS-CLI-02", "Farmacia El Dorado", "8-765-4321 DV 45", "Carlos Pinzón", "+507 6612-1002",
     "compras@farmaeldorado.pa", "Centro Comercial El Dorado, Calle Miguel Brostella", "Panamá", "Panamá",
     "9.0050000", "-79.5370000", "08:00", "17:00", 15),
    ("TMS-CLI-03", "Minisuper Albrook", "155698765-2-2020", "Luis Chen", "+507 6612-1003",
     "luis.chen@minialbrook.pa", "Albrook, Calle Principal, Casa 812", "Panamá", "Panamá",
     "8.9730000", "-79.5500000", "07:00", "19:00", 15),
    ("TMS-CLI-04", "Tienda Obarrio Calle 50", "155611111-2-2018", "María Batista", "+507 6612-1004",
     "tienda50@obarrio.pa", "Calle 50 y Calle 53 Este, Obarrio", "Panamá", "Panamá",
     "8.9850000", "-79.5200000", "09:00", "16:00", 20),
    ("TMS-CLI-05", "Restaurante Casco Viejo", "155622222-2-2021", "Javier Arosemena", "+507 6612-1005",
     "cocina@rcascoviejo.pa", "Calle 3ra, Plaza Herrera, Casco Antiguo", "Panamá", "Panamá",
     "8.9530000", "-79.5340000", "07:00", "11:00", 20),
    ("TMS-CLI-06", "Distribuidora Juan Díaz", "155633333-2-2017", "Rosa Quintero", "+507 6612-1006",
     "despacho@distjuandiaz.pa", "Vía José Agustín Arango, Galera 14, Juan Díaz", "Panamá", "Panamá",
     "9.0300000", "-79.4500000", "06:00", "15:00", 45),
    ("TMS-CLI-07", "Repuestos Tocumen", "155644444-2-2016", "Pedro Castillo", "+507 6612-1007",
     "ventas@reptocumen.pa", "Vía Domingo Díaz, frente a Plaza Tocumen", "Panamá", "Panamá",
     "9.0700000", "-79.3850000", "08:00", "17:00", 20),
    ("TMS-CLI-08", "Supermercado Vista Alegre", "155655555-2-2019", "Diana Ríos", "+507 6612-1008",
     "recibo@supervistaalegre.pa", "Carretera Panamericana, Vista Alegre, Arraiján", "Arraiján",
     "Panamá Oeste", "8.9300000", "-79.6550000", "06:00", "13:00", 30),
    ("TMS-CLI-09", "Farmacia La Chorrera", "155666666-2-2022", "Edwin Vega", "+507 6612-1009",
     "farmachorrera@correo.pa", "Calle Central, frente al Parque Libertador, La Chorrera", "La Chorrera",
     "Panamá Oeste", "8.8800000", "-79.7830000", "08:00", "18:00", 15),
    ("TMS-CLI-10", "Importadora Zona Libre Colón", "155677777-2-2015", "Yamileth Ho", "+507 6612-1010",
     "bodega@impzlc.pa", "Zona Libre de Colón, Calle 16, Edificio 45", "Colón", "Colón",
     "9.3550000", "-79.8950000", "08:00", "16:00", 40),
]

# envío, cliente, prioridad SO (1=urgente), nivel de servicio, días a la entrega,
# ventana (desde, hasta) o None, líneas [(sku, cantidad)], cajas, dirección alterna o None
ORDERS = [
    ("0001", "TMS-CLI-01", 5, "standard", 1, ("07:00", "11:00"),
     [("TMS-ARZ-5KG", 10), ("TMS-ACE-1L", 8), ("TMS-LEC-UHT", 12)], 6, None),
    ("0002", "TMS-CLI-02", 2, "express", 1, None,
     [("TMS-ACET-500", 15)], 3, None),
    ("0003", "TMS-CLI-03", 5, "standard", 2, None,
     [("TMS-ARZ-5KG", 4), ("TMS-LEC-UHT", 6)], 3, None),
    ("0004", "TMS-CLI-04", 5, "standard", 1, ("09:00", "12:00"),
     [("TMS-ACE-1L", 6), ("TMS-LEC-UHT", 6)], 2, None),
    ("0005", "TMS-CLI-05", 1, "same_day", 0, "auto",
     [("TMS-YOG-1KG", 10), ("TMS-POL-CONG", 8)], 4, None),
    ("0006", "TMS-CLI-06", 5, "standard", 2, None,
     [("TMS-ARZ-5KG", 25), ("TMS-ACE-1L", 20), ("TMS-LEC-UHT", 20)], 12, None),
    ("0007", "TMS-CLI-07", 5, "standard", 1, None,
     [("TMS-FIL-ACE", 10), ("TMS-PAS-BRK", 8)], 4, None),
    ("0008", "TMS-CLI-08", 3, "standard", 1, ("06:00", "10:00"),
     [("TMS-ARZ-5KG", 12), ("TMS-YOG-1KG", 6)], 5, None),
    ("0009", "TMS-CLI-09", 2, "express", 1, None,
     [("TMS-INS-10ML", 6), ("TMS-ACET-500", 10)], 2, None),
    ("0010", "TMS-CLI-10", 5, "scheduled", 3, ("08:00", "12:00"),
     [("TMS-ALC-1GL", 12)], 3, None),
    ("0011", "TMS-CLI-06", 4, "standard", 2, None,
     [("TMS-ALC-1GL", 4), ("TMS-FIL-ACE", 5)], 2, None),
    # Entrega en una sucursal distinta a la dirección principal del cliente
    ("0012", "TMS-CLI-01", 5, "standard", 2, ("06:00", "09:00"),
     [("TMS-LEC-UHT", 10), ("TMS-YOG-1KG", 4)], 3,
     ("Supermercado Costa del Este — Sucursal Brisas", "Brisas del Golf, Calle Principal, Local 7",
      "San Miguelito", "Panamá", "9.0500000", "-79.4570000")),
]


def gtin13(n: int) -> str:
    body = f"{GS1_PREFIX}{n:05d}"
    return body + str(gs1_check_digit(body))


def at(days: int, hhmm: str) -> datetime:
    base = datetime.now(PA_TZ).replace(second=0, microsecond=0) + timedelta(days=days)
    h, m = map(int, hhmm.split(":"))
    return base.replace(hour=h, minute=m)


def schedule(days: int, window) -> dict:
    """Fechas de la orden relativas a hoy (hora de Panamá).

    `window="auto"` (same_day): ventana de 4 h que empieza en la próxima hora en
    punto + 1 h; si ya es tarde para entregar hoy, pasa a mañana 07:00–11:00.
    """
    if window == "auto":
        now = datetime.now(PA_TZ).replace(minute=0, second=0, microsecond=0)
        start = now + timedelta(hours=2)
        if start.hour >= 17 or start.date() != now.date():
            start = at(1, "07:00")
        ws, we = start, start + timedelta(hours=4)
    elif window:
        ws, we = at(days, window[0]), at(days, window[1])
    else:
        ws = we = None
    day = (ws or at(days, "00:00")).replace(hour=0, minute=0)
    return {
        "requested_delivery_date": day,
        "delivery_window_start": ws,
        "delivery_window_end": we,
        "scheduled_pickup": (ws - timedelta(hours=1, minutes=30)) if ws else day.replace(hour=5, minute=30),
        "estimated_delivery": we or day.replace(hour=17),
    }


async def seed_tms_orders(db: AsyncSession) -> None:
    tenant = (await db.execute(select(Tenant).where(Tenant.slug == "wms-demo"))).scalar_one_or_none()
    if not tenant:
        print("Tenant 'wms-demo' no encontrado. Corre primero: python -m seeds.run_all")
        return
    tid = tenant.id
    admin = (await db.execute(select(User).where(User.tenant_id == tid))).scalars().first()
    if not admin:
        print("No hay usuarios en el tenant. Corre primero: python -m seeds.run_all")
        return

    # ── Bodega origen con coordenadas ─────────────────────────────────────────
    warehouse = (await db.execute(select(Warehouse).where(Warehouse.tenant_id == tid)
                                  .order_by(Warehouse.created_at))).scalars().first()
    if not warehouse:
        company = (await db.execute(select(Company).where(Company.tenant_id == tid))).scalars().first()
        if not company:
            company = Company(tenant_id=tid, name="Demo Logistics PA", legal_name="Demo Logistics S.A.",
                              ruc="123-456", country="PA")
            db.add(company)
            await db.flush()
        warehouse = Warehouse(tenant_id=tid, company_id=company.id, code="WH-01",
                              name="Centro de Distribución Milla 8", status=WarehouseStatus.ACTIVE)
        db.add(warehouse)
        await db.flush()
    if warehouse.latitude is None or warehouse.longitude is None:
        for k, v in WAREHOUSE_GEO.items():
            if getattr(warehouse, k, None) in (None, ""):
                setattr(warehouse, k, v)
    if not warehouse.gln:
        body = f"{GS1_PREFIX}00001"
        warehouse.gln = body + str(gs1_check_digit(body))
    print(f"Bodega origen: {warehouse.code} ({warehouse.latitude}, {warehouse.longitude})")

    # ── Productos ─────────────────────────────────────────────────────────────
    products: dict[str, Product] = {}
    for i, (sku, name, industry, cond, tmin, tmax, kg, m3, hazmat, un_class) in enumerate(PRODUCTS, start=1):
        p = (await db.execute(select(Product).where(Product.tenant_id == tid, Product.sku == sku))).scalar_one_or_none()
        if p is None:
            p = Product(tenant_id=tid, sku=sku, name=name, status=ProductStatus.ACTIVE,
                        tracking_type=TrackingType.LOT, uom="CJ")
            db.add(p)
        p.industry, p.storage_condition = industry, cond
        p.min_temp_celsius = Decimal(tmin) if tmin else None
        p.max_temp_celsius = Decimal(tmax) if tmax else None
        p.weight_kg, p.volume_m3 = Decimal(kg), Decimal(m3)
        p.is_hazmat, p.hazmat_class = hazmat, un_class
        p.gtin_13 = p.gtin_13 or gtin13(i)
        products[sku] = p
    await db.flush()
    print(f"Productos: {len(products)}")

    # ── Clientes con punto de entrega georreferenciado ────────────────────────
    customers: dict[str, Customer] = {}
    for i, (code, name, ruc, contact, phone, email, addr, city, prov, lat, lon, h1, h2, svc) in \
            enumerate(CUSTOMERS, start=1):
        c = (await db.execute(select(Customer).where(Customer.tenant_id == tid, Customer.code == code))) \
            .scalar_one_or_none()
        if c is None:
            c = Customer(tenant_id=tid, code=code, name=name, customer_type=CustomerType.RETAIL,
                         is_active=True, created_by_id=admin.id)
            db.add(c)
        c.ruc, c.contact_name, c.contact_phone, c.contact_email = ruc, contact, phone, email
        c.delivery_address, c.delivery_city, c.delivery_province, c.delivery_country = addr, city, prov, "PA"
        c.delivery_latitude, c.delivery_longitude = Decimal(lat), Decimal(lon)
        c.receiving_hours_from, c.receiving_hours_to, c.service_time_min = h1, h2, svc
        body = f"{GS1_PREFIX}1{i:04d}"
        c.gln = c.gln or body + str(gs1_check_digit(body))
        customers[code] = c
    await db.flush()
    print(f"Clientes: {len(customers)}")

    # ── SO (PACKED) + empaque (COMPLETED, con SSCC) + envío (PENDING) ─────────
    created = refreshed = skipped = 0
    for (num, ccode, prio, level, days, window, lines, boxes, alt) in ORDERS:
        ship_number = f"SHP-TMS-{num}"
        dates = schedule(days, window)
        existing = (await db.execute(select(Shipment).where(
            Shipment.tenant_id == tid, Shipment.shipment_number == ship_number))).scalar_one_or_none()
        if existing is not None:
            if existing.status == ShipmentStatus.PENDING:
                # Aún no la tomó el TMS: se mueven sus fechas a hoy para que no quede vencida
                so = await db.get(SalesOrder, existing.so_id)
                for k in ("requested_delivery_date", "delivery_window_start", "delivery_window_end"):
                    setattr(so, k, dates[k])
                existing.scheduled_pickup = dates["scheduled_pickup"]
                existing.estimated_delivery = dates["estimated_delivery"]
                refreshed += 1
            else:
                skipped += 1
            continue
        c = customers[ccode]
        now = datetime.now(timezone.utc)
        if alt:
            ship_name, ship_addr, ship_city, ship_prov, ship_lat, ship_lon = alt
            ship_lat, ship_lon = Decimal(ship_lat), Decimal(ship_lon)
        else:
            ship_name, ship_addr, ship_city, ship_prov = c.name, c.delivery_address, c.delivery_city, c.delivery_province
            ship_lat, ship_lon = c.delivery_latitude, c.delivery_longitude

        so = SalesOrder(
            id=uuid.uuid4(), tenant_id=tid, warehouse_id=warehouse.id, customer_id=c.id,
            so_number=f"SO-TMS-{num}", customer_po_reference=f"PO-{ccode[-2:]}-{num}",
            status=SOStatus.PACKED, order_date=now - timedelta(days=1), confirmed_date=now - timedelta(hours=20),
            requested_delivery_date=dates["requested_delivery_date"], priority=prio, service_level=level,
            carrier_type=ShippingCarrierType.OWN_FLEET,
            currency="USD", ruc_cliente=c.ruc,
            ship_to_name=ship_name, ship_to_address=ship_addr, ship_to_city=ship_city,
            ship_to_province=ship_prov, ship_to_country="PA", ship_to_phone=c.contact_phone,
            ship_to_contact_name=c.contact_name, ship_to_email=c.contact_email,
            ship_to_latitude=ship_lat, ship_to_longitude=ship_lon, ship_to_gln=None if alt else c.gln,
            delivery_window_start=dates["delivery_window_start"],
            delivery_window_end=dates["delivery_window_end"],
            service_time_min=c.service_time_min,
            delivery_instructions=f"Entregar por andén de recepción. Contacto: {c.contact_name} {c.contact_phone}",
            created_by_id=admin.id,
        )
        db.add(so)
        await db.flush()

        subtotal, weight, volume = Decimal("0"), Decimal("0"), Decimal("0")
        for n, (sku, qty) in enumerate(lines, start=1):
            p = products[sku]
            q = Decimal(qty)
            price = Decimal("18.50")
            db.add(SalesOrderLine(
                id=uuid.uuid4(), tenant_id=tid, so_id=so.id, line_number=n, product_id=p.id,
                description=p.name, gtin=p.gtin_13, quantity_ordered=q, quantity_allocated=q,
                quantity_picked=q, quantity_packed=q, unit_price=price, line_total=q * price,
                status=SOLineStatus.PACKED,
            ))
            subtotal += q * price
            weight += q * Decimal(p.weight_kg)
            volume += q * Decimal(p.volume_m3)
        so.subtotal = so.total_amount = subtotal

        pack = PackTask(
            id=uuid.uuid4(), tenant_id=tid, so_id=so.id, pack_task_number=f"PACK-TMS-{num}",
            status=PackStatus.COMPLETED, box_type="pallet" if boxes >= 6 else "large", box_count=boxes,
            total_weight_kg=weight.quantize(Decimal("0.001")), total_volume_m3=volume.quantize(Decimal("0.0001")),
            sscc=generate_sscc(GS1_PREFIX, serial=int(num)), started_at=now - timedelta(hours=3),
            completed_at=now - timedelta(hours=2), cycle_time_seconds=3600,
            label_printed=True, packing_list_printed=True, created_by_id=admin.id, assigned_to_id=admin.id,
        )
        db.add(pack)
        db.add(Shipment(
            id=uuid.uuid4(), tenant_id=tid, so_id=so.id, warehouse_id=warehouse.id,
            shipment_number=ship_number, status=ShipmentStatus.PENDING,
            carrier_type=so.carrier_type, scheduled_pickup=dates["scheduled_pickup"],
            estimated_delivery=dates["estimated_delivery"],
            total_boxes=boxes, total_weight_kg=pack.total_weight_kg, total_volume_m3=pack.total_volume_m3,
            delivery_note_number=f"NE-TMS-{num}", notes="Envío generado por seeds.tms_orders",
            created_by_id=admin.id,
        ))
        await db.flush()
        created += 1

    await db.commit()
    print(f"Envíos listos para el TMS: {created} creados, {refreshed} pendientes con fechas "
          f"actualizadas, {skipped} ya tomados por el TMS (sin cambios).")
    print("Verifica: GET /api/v1/integrations/tms/orders?status=pending")


async def run() -> None:
    async with AsyncSessionLocal() as db:
        await seed_tms_orders(db)


if __name__ == "__main__":
    asyncio.run(run())
