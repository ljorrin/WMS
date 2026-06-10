"""
WMS Panama — Demo Data Seed
=============================
Generates comprehensive demo data (products, movements, adjustments, POs, SOs)
for presentation and testing purposes.
"""
import asyncio
import os
import sys
import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from faker import Faker

from app.db.session import AsyncSessionLocal
from app.models.core import Tenant, Company, Warehouse, WarehouseStatus
from app.models.master_data import (
    Product, ProductCategory, Supplier, Customer, Zone, Location,
    LocationType, LocationStatus, IndustryType, TrackingType, CustomerType, ProductStatus, SupplierStatus
)
from app.models.inventory import (
    InventoryLevel, InventoryMovement, Batch, MovementType,
    InventoryAdjustment, AdjustmentLine, AdjustmentStatus
)
from app.models.inbound import (
    PurchaseOrder, PurchaseOrderLine, GoodsReceipt, GoodsReceiptLine,
    QualityInspection, QualityInspectionLine,
    PutawayTask,
    POStatus, GRNStatus, QCStatus, PutawayStatus
)

fake = Faker('es_MX')

FOOD_PRODUCTS = [
    "Arroz Blanco Grano Largo Especial 5kg", "Frijol Chiricano 1kg",
    "Frijol Mantequilla 1kg", "Frijol Negro 1kg", "Lentejas 1kg",
    "Harina de Trigo Todo Uso 2kg", "Harina de Maiz Blanco 1kg",
    "Azucar Blanca Refinada 2kg", "Azucar Morena 1kg", "Sal Yodada 500g",
    "Aceite Vegetal 1L", "Aceite de Oliva Extra Virgen 500ml",
    "Salsa de Tomate Ketchup 400g", "Pasta de Tomate 200g",
    "Mayonesa Regular 450g", "Mostaza 250g", "Atun en Agua 140g",
    "Atun en Aceite 140g", "Sardinas en Salsa de Tomate 150g",
    "Salchichas Viena enlatadas 200g", "Maiz Dulce enlatado 300g",
    "Guisantes enlatados 300g", "Pasta Spaghetti 500g", "Pasta Macarrones 500g",
    "Pasta Coditos 500g", "Avena en Hojuelas 500g", "Leche Evaporada 400ml",
    "Leche Condensada 395g", "Leche Entera UHT 1L", "Leche Descremada UHT 1L",
    "Cafe Molido Tradicional 425g", "Cafe Instantaneo 200g", "Te de Manzanilla 25 bolsitas",
    "Cereal de Maiz 500g", "Cereal de Trigo y Miel 400g", "Galletas de Soda 300g",
    "Galletas Dulces Vainilla 250g", "Galletas Rellenas de Chocolate 300g",
    "Pan de Molde Blanco 500g", "Pan Integral 500g", "Harina para Hotcakes 500g",
    "Sirope de Maple 400ml", "Mermelada de Fresa 300g", "Crema de Cacahuate 400g",
    "Margarina 500g", "Queso Amarillo Procesado 200g", "Vinagre Blanco 1L",
    "Salsa de Soya 500ml", "Salsa Inglesa 200ml", "Salsa Picante 150ml",
    "Caldo de Pollo en cubitos 100g", "Sazonador Completo 200g", "Canela en Polvo 50g",
    "Pimienta Negra Molida 50g", "Ajo en Polvo 100g", "Paprika 50g",
    "Curry en Polvo 50g", "Miel de Abeja 500g", "Gelatina de Fresa 100g",
    "Polvo para Hornear 150g", "Extracto de Vainilla 100ml", "Chocolate en Polvo 400g",
    "Te Frio en Polvo Limon 500g", "Refresco en Polvo Naranja 30g",
    "Agua Embotellada 500ml", "Agua Embotellada 1.5L", "Jugo de Naranja 1L",
    "Jugo de Manzana 1L", "Jugo de Pina 1L", "Bebida Isotonica 600ml",
    "Gaseosa Cola 2L", "Gaseosa Limon 2L", "Papas Fritas Snacks 150g",
    "Platanitos Snacks 150g", "Tostillas de Maiz 200g", "Cacahuates Salados 100g",
    "Almendras 100g", "Pasitas 150g", "Ciruelas Pasas 200g", "Ajo Entero Malla",
    "Cebolla Amarilla 1kg", "Papa Blanca 2kg", "Zanahoria 1kg", "Limon Criollo 500g",
    "Huevos Blancos Docena", "Sopa Instantanea Pollo 80g", "Pure de Papa Instantaneo 200g",
    "Crema de Mariscos sobre 60g", "Frijoles Molidos lata 400g",
    "Chicharrones Snacks 100g", "Salsa para Pasta Queso 400g",
    "Aceitunas Verdes frasco 300g", "Alcaparras frasco 100g",
    "Melocoton en Almibar 800g", "Pina en Rodajas lata 800g",
    "Leche de Coco lata 400ml", "Masa de Maiz para Empanadas 500g",
    "Leche en Polvo Entera 800g", "Crema de Leche lata 300ml",
    "Bicarbonato de Sodio 100g"
]

def generate_sku(idx):
    return f"PROD-{fake.random_int(10000, 99999)}-{idx}"

async def seed_demo_data(db: AsyncSession):
    print("Obteniendo Tenant 'wms-demo'...")
    tenant = (await db.execute(select(Tenant).where(Tenant.slug == "wms-demo"))).scalar_one_or_none()
    if not tenant:
        print("Tenant 'wms-demo' no encontrado. Por favor corre seeds.run_all primero.")
        return

    tid = tenant.id

    # Opcional: Limpiar datos transaccionales para evitar colisiones
    # print("Limpiando datos de prueba anteriores...")
    # await db.execute(delete(InventoryMovement).where(InventoryMovement.tenant_id == tid))
    # await db.execute(delete(InventoryLevel).where(InventoryLevel.tenant_id == tid))
    # await db.execute(delete(Batch).where(Batch.tenant_id == tid))
    # await db.flush()

    # 1. Crear Company y Warehouse
    print("Generando Company y Warehouse...")
    company = (await db.execute(select(Company).where(Company.tenant_id == tid))).scalars().first()
    if not company:
        company = Company(tenant_id=tid, name="Demo Logistics PA", legal_name="Demo Logistics S.A.", ruc="123-456", country="PA")
        db.add(company)
        await db.flush()

    warehouse = (await db.execute(select(Warehouse).where(Warehouse.tenant_id == tid))).scalars().first()
    if not warehouse:
        warehouse = Warehouse(tenant_id=tid, company_id=company.id, code="WH-01", name="Centro de Distribución Milla 8", status=WarehouseStatus.ACTIVE)
        db.add(warehouse)
        await db.flush()

    # 2. Crear Zones y Locations
    print("Generando Zonas y Ubicaciones...")
    zone = (await db.execute(select(Zone).where(Zone.warehouse_id == warehouse.id))).scalars().first()
    if not zone:
        zone = Zone(tenant_id=tid, warehouse_id=warehouse.id, code="Z-SEC", name="Secos Principal", zone_type="storage")
        db.add(zone)
        await db.flush()

    locations = (await db.execute(select(Location).where(Location.zone_id == zone.id))).scalars().all()
    if not locations:
        for i in range(1, 11):
            loc = Location(tenant_id=tid, warehouse_id=warehouse.id, zone_id=zone.id, code=f"A-01-B-{i:02d}", location_type=LocationType.STANDARD, status=LocationStatus.ACTIVE)
            db.add(loc)
            locations.append(loc)
        await db.flush()

    # 3. Proveedores y Clientes
    print("Generando Proveedores y Clientes...")
    suppliers = (await db.execute(select(Supplier).where(Supplier.tenant_id == tid))).scalars().all()
    if not suppliers:
        for i in range(5):
            sup = Supplier(tenant_id=tid, code=f"SUP-{i}", name=fake.company(), status=SupplierStatus.ACTIVE)
            db.add(sup)
            suppliers.append(sup)
        await db.flush()

    customers = (await db.execute(select(Customer).where(Customer.tenant_id == tid))).scalars().all()
    if not customers:
        for i in range(5):
            cus = Customer(tenant_id=tid, code=f"CUS-{i}", name=fake.company(), customer_type=CustomerType.RETAIL, is_active=True, delivery_country="PA")
            db.add(cus)
            customers.append(cus)
        await db.flush()

    # 4. Productos (Alimentos Secos)
    print("Generando 100 Productos (Alimentos Secos)...")
    products = (await db.execute(select(Product).where(Product.tenant_id == tid))).scalars().all()
    if len(products) < 10:
        for i, food in enumerate(FOOD_PRODUCTS[:100]):
            p = Product(
                tenant_id=tid,
                sku=generate_sku(i),
                name=food,
                status=ProductStatus.ACTIVE,
                industry=IndustryType.AGRO_FOOD,
                tracking_type=TrackingType.LOT_EXPIRY,
                uom="UN"
            )
            db.add(p)
            products.append(p)
        await db.flush()

    print(f"Productos listos: {len(products)}")

    # 5. Inventario: Batches, Levels y Movements
    print("Generando Lotes, Stock y Movimientos...")
    now = datetime.now(timezone.utc)
    for p in products[:30]:  # Generar stock para los primeros 30 productos
        # Crear 2 lotes por producto
        for b_idx in range(2):
            is_near_expiry = (b_idx == 0) # El primer lote de algunos productos estará por vencer
            is_expired = (b_idx == 1 and random.random() < 0.2) # 20% expirados

            if is_expired:
                expiry = now - timedelta(days=random.randint(1, 10))
            elif is_near_expiry:
                expiry = now + timedelta(days=random.randint(5, 20)) # Por vencer en 5-20 días
            else:
                expiry = now + timedelta(days=random.randint(90, 365)) # Lotes buenos

            batch = Batch(
                tenant_id=tid,
                product_id=p.id,
                warehouse_id=warehouse.id,
                batch_number=fake.bothify(text='LOTE-####-??'),
                manufacture_date=now - timedelta(days=60),
                expiry_date=expiry,
                received_date=now - timedelta(days=50),
                is_blocked=is_expired,
                blocked_reason="EXPIRED" if is_expired else None
            )
            db.add(batch)
            await db.flush()

            # Nivel de stock
            loc = random.choice(locations)
            qty = random.randint(10, 500)
            level = InventoryLevel(
                tenant_id=tid,
                warehouse_id=warehouse.id,
                location_id=loc.id,
                product_id=p.id,
                batch_id=batch.id,
                quantity_on_hand=qty,
                quantity_available=qty
            )
            db.add(level)
            await db.flush()

            # Movimientos (Historial)
            for _ in range(random.randint(1, 3)):
                mov = InventoryMovement(
                    tenant_id=tid,
                    warehouse_id=warehouse.id,
                    product_id=p.id,
                    batch_id=batch.id,
                    to_location_id=loc.id,
                    movement_type=MovementType.RECEIPT,
                    quantity=random.randint(10, 100),
                    reference=fake.bothify(text='DOC-####'),
                    source_document_type='RECEIPT',
                    source_document_number=fake.bothify(text='DOC-####'),
                    occurred_at=now - timedelta(days=random.randint(0, 30))
                )
                db.add(mov)

    await db.flush()

    # 6. Ajustes de Inventario
    print("Generando Ajustes de Inventario...")
    p_adj = random.choice(products)
    loc_adj = random.choice(locations)
    adj = InventoryAdjustment(
        tenant_id=tid,
        warehouse_id=warehouse.id,
        adjustment_number=fake.bothify(text='ADJ-####'),
        status=AdjustmentStatus.PENDING_APPROVAL,
        reason="cycle_count",
        reason_code="CYCLE_COUNT",
        notes="Ajuste generado por conteo cíclico"
    )
    db.add(adj)
    await db.flush()

    adj_line = AdjustmentLine(
        tenant_id=tid,
        adjustment_id=adj.id,
        product_id=p_adj.id,
        location_id=loc_adj.id,
        quantity_system=100,
        quantity_physical=95,
        variance=-5
    )
    db.add(adj_line)

    # 7. Inbound: Purchase Orders & GRNs
    print("Generando Purchase Orders e Inbound (PO, GRN)...")
    sup = random.choice(suppliers)
    for _ in range(25): # 25 POs
        po = PurchaseOrder(
            tenant_id=tid,
            warehouse_id=warehouse.id,
            supplier_id=sup.id,
            po_number=f"PO-{fake.unique.random_int(min=10000, max=99999)}",
            status=random.choice(list(POStatus)),
            order_date=now.date(),
            expected_delivery_date=now + timedelta(days=random.randint(-5, 15))
        )
        db.add(po)
        await db.flush()

        total_po = Decimal("0")
        for line_idx in range(1, 4):
            qty = random.randint(50, 200)
            price = Decimal(str(random.uniform(5.0, 50.0))).quantize(Decimal("0.01"))
            line_total = qty * price
            po_line = PurchaseOrderLine(
                tenant_id=tid,
                purchase_order_id=po.id,
                line_number=line_idx,
                product_id=random.choice(products).id,
                quantity_ordered=qty,
                quantity_received=random.randint(0, 50),
                unit_price=price,
                line_total=line_total
            )
            db.add(po_line)
            total_po += line_total
        po.total_amount = total_po
        await db.flush()

        if po.status != POStatus.DRAFT:
            # Create GRN
            grn = GoodsReceipt(
                tenant_id=tid,
                warehouse_id=warehouse.id,
                purchase_order_id=po.id,
                grn_number=fake.bothify(text='GRN-####'),
                status=GRNStatus.COMPLETED,
                received_at=now - timedelta(hours=random.randint(1, 48))
            )
            db.add(grn)
            await db.flush()
            # Create GRN Lines based on PO Lines
            for i in range(1, 4):
                grn_line = GoodsReceiptLine(
                    tenant_id=tid,
                    grn_id=grn.id,
                    line_number=i,
                    po_line_id=None,
                    product_id=random.choice(products).id,
                    quantity_expected=random.randint(50, 200),
                    quantity_received=random.randint(0, 50),
                    unit_cost=Decimal(str(random.uniform(5.0, 50.0))).quantize(Decimal("0.01"))
                )
                db.add(grn_line)
            await db.flush()

            # Quality Inspection for every GRN
            if True:
                total_inspected = grn_line.quantity_received
                total_approved = grn_line.quantity_received
                total_rejected = Decimal("0")
                
                qi = QualityInspection(
                    tenant_id=tid,
                    grn_id=grn.id,
                    warehouse_id=warehouse.id,
                    qi_number=fake.bothify(text='QI-####'),
                    status=random.choice(list(QCStatus)),
                    inspection_date=now - timedelta(hours=random.randint(1, 24)),
                    total_inspected=total_inspected,
                    total_approved=total_approved,
                    total_rejected=total_rejected,
                    defect_rate=Decimal("0.0")
                )
                db.add(qi)
                await db.flush()
                
                qi_line = QualityInspectionLine(
                    tenant_id=tid,
                    qi_id=qi.id,
                    grn_line_id=grn_line.id,
                    product_id=grn_line.product_id,
                    line_number=1,
                    quantity_inspected=total_inspected,
                    quantity_approved=total_approved,
                    quantity_rejected=total_rejected,
                    quantity_defective=Decimal("0")
                )
                db.add(qi_line)
                await db.flush()

            # Always generate a PutawayTask for the received GRN Line
            task_status = random.choice(list(PutawayStatus))
            putaway = PutawayTask(
                tenant_id=tid,
                warehouse_id=warehouse.id,
                grn_id=grn.id,
                grn_line_id=grn_line.id,
                product_id=grn_line.product_id,
                quantity=grn_line.quantity_received,
                from_location_id=random.choice(locations).id,
                suggested_location_id=random.choice(locations).id,
                status=task_status,
                priority=random.randint(1, 10),
                created_at=now - timedelta(hours=random.randint(1, 24)),
                cycle_time_seconds=random.randint(120, 1800) if task_status == PutawayStatus.COMPLETED else None,
                started_at=(now - timedelta(minutes=random.randint(10, 60))) if task_status in [PutawayStatus.IN_PROGRESS, PutawayStatus.COMPLETED] else None,
                completed_at=now if task_status == PutawayStatus.COMPLETED else None
            )
            db.add(putaway)
            await db.flush()

    # 8. Outbound: Sales Orders
    print("Generando Outbound y Sales Orders...")
    try:
        from app.models.outbound import SalesOrder, SalesOrderLine, SOStatus, SOLineStatus, PickingWave, WaveStatus, PickingTask, PickingStatus, PackTask, PackStatus, Shipment, ShipmentStatus, ReturnOrder, ReturnOrderStatus
        from app.models.core import User
        
        admin = (await db.execute(select(User).where(User.tenant_id == tid))).scalars().first()
        locs = (await db.execute(select(Location).where(Location.tenant_id == tid))).scalars().all()
        
        for _ in range(15):
            cus = random.choice(customers)
            status = random.choice(list(SOStatus))
            so = SalesOrder(
                tenant_id=tid,
                warehouse_id=warehouse.id,
                customer_id=cus.id,
                created_by_id=admin.id if admin else uuid.uuid4(),
                so_number=fake.bothify(text='SO-#####'),
                status=status,
                order_date=now.date(),
                requested_delivery_date=now + timedelta(days=random.randint(0, 5))
            )
            db.add(so)
            await db.flush()

            # Añadir líneas de orden de venta
            created_lines = []
            for line_idx in range(1, random.randint(2, 5)):
                so_line = SalesOrderLine(
                    tenant_id=tid,
                    so_id=so.id,
                    line_number=line_idx,
                    product_id=random.choice(products).id,
                    uom_id=uuid.uuid4(),
                    quantity_ordered=Decimal(random.randint(10, 50)),
                    quantity_allocated=Decimal(random.randint(5, 10)) if status != SOStatus.DRAFT else Decimal("0"),
                    status=SOLineStatus.PENDING
                )
                db.add(so_line)
                created_lines.append(so_line)
            await db.flush()
            
            # Generar datos secuenciales si la orden no está en DRAFT
            if status != SOStatus.DRAFT:
                # 1. Picking Wave
                wave = PickingWave(
                    tenant_id=tid,
                    warehouse_id=warehouse.id,
                    wave_number=fake.bothify(text='WAVE-#####'),
                    status=random.choice([WaveStatus.IN_PROGRESS, WaveStatus.COMPLETED]),
                    created_by_id=admin.id,
                    total_orders=1,
                    total_lines=len(created_lines)
                )
                db.add(wave)
                await db.flush()
                
                so.wave_id = wave.id
                
                # 2. Picking Tasks
                for line in created_lines:
                    loc = random.choice(locs) if locs else None
                    pick = PickingTask(
                        tenant_id=tid,
                        wave_id=wave.id,
                        so_id=so.id,
                        so_line_id=line.id,
                        product_id=line.product_id,
                        uom_id=line.uom_id,
                        quantity_requested=line.quantity_ordered,
                        quantity_picked=line.quantity_ordered if wave.status == WaveStatus.COMPLETED else Decimal("0"),
                        from_location_id=loc.id if loc else uuid.uuid4(),
                        status=PickingStatus.COMPLETED if wave.status == WaveStatus.COMPLETED else PickingStatus.PENDING,
                        assigned_to_id=admin.id
                    )
                    db.add(pick)
                await db.flush()
                
                # 3. Pack Task (Si Picking está completado)
                if wave.status == WaveStatus.COMPLETED:
                    pack_status = random.choice([PackStatus.PENDING, PackStatus.COMPLETED])
                    pack = PackTask(
                        tenant_id=tid,
                        so_id=so.id,
                        pack_task_number=fake.bothify(text='PACK-#####'),
                        status=pack_status,
                        box_count=random.randint(1, 4),
                        total_weight_kg=Decimal(random.uniform(5.0, 50.0)),
                        created_by_id=admin.id,
                        assigned_to_id=admin.id if pack_status == PackStatus.COMPLETED else None
                    )
                    db.add(pack)
                    await db.flush()
                    
                    # 4. Shipment (Si Packing está completado)
                    if pack_status == PackStatus.COMPLETED:
                        ship_status = random.choice(list(ShipmentStatus))
                        ship = Shipment(
                            tenant_id=tid,
                            so_id=so.id,
                            warehouse_id=warehouse.id,
                            shipment_number=fake.bothify(text='SHIP-#####'),
                            status=ship_status,
                            tracking_number=fake.bothify(text='TRK-#########'),
                            total_boxes=pack.box_count,
                            total_weight_kg=pack.total_weight_kg,
                            created_by_id=admin.id
                        )
                        db.add(ship)
                        await db.flush()
                        
                        # 5. Return Order (Si Shipment está entregado o fallido)
                        if ship_status in [ShipmentStatus.DELIVERED, ShipmentStatus.FAILED] and random.random() < 0.3:
                            rma = ReturnOrder(
                                tenant_id=tid,
                                warehouse_id=warehouse.id,
                                so_id=so.id,
                                customer_id=cus.id,
                                rma_number=fake.bothify(text='RMA-#####'),
                                status=random.choice(list(ReturnOrderStatus)),
                                reason="Producto dañado en transporte" if ship_status == ShipmentStatus.FAILED else "El cliente cambió de opinión",
                                return_type=random.choice(["refund", "exchange"]),
                                created_by_id=admin.id
                            )
                            db.add(rma)
                            await db.flush()
    except Exception as e:
        print(f"Skipping Outbound due to error: {e}")

    await db.commit()
    print("¡Generación de datos finalizada con éxito!")

async def run_seeds():
    async with AsyncSessionLocal() as db:
        await seed_demo_data(db)

if __name__ == "__main__":
    asyncio.run(run_seeds())
