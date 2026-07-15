"""
WMS Panamá — Test E2E completo contra PostgreSQL real (Fase 0.3 del plan)
==========================================================================
Recorre el flujo de punta a punta ejercitando servicio + repositorio + modelo
contra una base de datos PostgreSQL real (sin mocks):

    PO → ASN → GRN → QC → Putaway
      → SO-A → Wave → Pick → Pack (BoxType + SSCC) → Ship → Deliver
      → SO-B → Streaming (waveless) → Pick
      → Labor (tarea de putaway con estándar y performance calculado)
      → Slotting (política → análisis ABC → recomendación → aplicar)
      → KPIs (inbound / outbound / labor)
      → Reconciliación de inventario: kardex (movimientos) == stock final

Se salta automáticamente si no hay PostgreSQL de test accesible (ver conftest.py).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import and_, func, select

from app.core.gs1 import generate_sscc
from app.models.core import Company, Tenant, User, Warehouse
from app.models.inbound import GRNStatus, PutawayTask
from app.models.inventory import InventoryLevel, InventoryMovement, MovementType
from app.models.labor import LaborStandard
from app.models.master_data import Customer, Location, Product, Supplier, Zone
from app.models.slotting import SlottingPolicy, SlottingRecommendation
from app.services.inbound_service import InboundService
from app.services.labor_service import LaborService
from app.services.outbound_service import OutboundService
from app.services.slotting_service import SlottingService
from app.services.streaming_service import StreamingService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def flow_seed(db):
    """
    Grafo de datos maestros más rico que el `seed` genérico: incluye cliente,
    proveedor, dos zonas (picking dorada / reserva) y tres ubicaciones
    (staging de recepción, storage en zona reserva, frente de picking en zona
    dorada) — necesario para ejercitar putaway, FEFO, slotting y streaming.
    """
    tenant = Tenant(id=uuid4(), name="E2E S.A.", slug=f"e2e-{uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()

    user = User(
        id=uuid4(), tenant_id=tenant.id, email=f"e2e-{uuid4().hex[:8]}@wms.pa",
        first_name="E2E", last_name="Operador", is_superadmin=True,
    )
    company = Company(id=uuid4(), tenant_id=tenant.id, name="Compañía E2E")
    db.add_all([user, company])
    await db.flush()

    warehouse = Warehouse(
        id=uuid4(), tenant_id=tenant.id, company_id=company.id,
        code="WH-E2E", name="Almacén E2E",
    )
    product = Product(
        id=uuid4(), tenant_id=tenant.id, sku=f"SKU-{uuid4().hex[:6]}",
        name="Producto E2E",
    )
    supplier = Supplier(id=uuid4(), tenant_id=tenant.id, code=f"SUP-{uuid4().hex[:6]}", name="Proveedor E2E")
    customer = Customer(id=uuid4(), tenant_id=tenant.id, code=f"CUST-{uuid4().hex[:6]}", name="Cliente E2E")
    db.add_all([warehouse, product, supplier, customer])
    await db.flush()

    zone_pick = Zone(id=uuid4(), tenant_id=tenant.id, warehouse_id=warehouse.id, code="PICK", name="Zona Dorada")
    zone_reserve = Zone(id=uuid4(), tenant_id=tenant.id, warehouse_id=warehouse.id, code="RSV", name="Zona Reserva")
    db.add_all([zone_pick, zone_reserve])
    await db.flush()

    loc_staging = Location(
        id=uuid4(), tenant_id=tenant.id, warehouse_id=warehouse.id, code="STAGING-01",
    )
    loc_storage = Location(
        id=uuid4(), tenant_id=tenant.id, warehouse_id=warehouse.id, code="RSV-01",
        zone_id=zone_reserve.id, pick_sequence=500, is_pick_face=True, max_units=10_000,
    )
    loc_pickface = Location(
        id=uuid4(), tenant_id=tenant.id, warehouse_id=warehouse.id, code="PICK-01",
        zone_id=zone_pick.id, pick_sequence=5, is_pick_face=True, max_units=10_000,
    )
    db.add_all([loc_staging, loc_storage, loc_pickface])
    await db.flush()

    return SimpleNamespace(
        db=db,
        tenant_id=tenant.id,
        user_id=user.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        supplier_id=supplier.id,
        customer_id=customer.id,
        loc_staging_id=loc_staging.id,
        loc_storage_id=loc_storage.id,
        loc_pickface_id=loc_pickface.id,
        zone_pick_code=zone_pick.code,
        zone_reserve_code=zone_reserve.code,
    )


async def test_full_flow_po_to_kpis_with_reconciliation(flow_seed):
    s = flow_seed
    inbound = InboundService(db=s.db, tenant_id=s.tenant_id, user_id=s.user_id)
    outbound = OutboundService(db=s.db, tenant_id=s.tenant_id, user_id=s.user_id)
    labor = LaborService(db=s.db)
    slotting = SlottingService(db=s.db)
    streaming = StreamingService(db=s.db)

    RECEIVED_QTY = Decimal("100")
    SO_A_QTY = Decimal("20")
    SO_B_QTY = Decimal("15")

    # ═══ 1) INBOUND: PO → ASN → GRN (con ruptura de cadena de frío) → QC → Putaway ═══
    po = await inbound.create_purchase_order(
        warehouse_id=s.warehouse_id, supplier_id=s.supplier_id, order_date=date.today(),
        lines_data=[dict(product_id=s.product_id, quantity_ordered=RECEIVED_QTY,
                          unit_cost=Decimal("3.50"), uom="UN")],
    )
    await s.db.flush()
    await inbound.confirm_purchase_order(po.id)
    await s.db.flush()
    po = await inbound.po_repo.get_by_id(po.id)
    po_line_id = po.lines[0].id

    asn = await inbound.create_asn(
        warehouse_id=s.warehouse_id, supplier_id=s.supplier_id, po_id=po.id,
        lines_data=[dict(product_id=s.product_id, quantity_expected=RECEIVED_QTY, po_line_id=po_line_id)],
    )
    await s.db.flush()
    await inbound.dispatch_asn(asn.id)
    await inbound.arrive_asn(asn.id, dock_number="D-01")
    await s.db.flush()

    # product_temp_celsius fuera de rango (> 8.0°C) → requires_qc automático
    grn = await inbound.create_grn(
        warehouse_id=s.warehouse_id, asn_id=asn.id, po_id=po.id,
        product_temp_celsius=Decimal("12.0"),
        lines_data=[dict(
            product_id=s.product_id, po_line_id=po_line_id, quantity_received=RECEIVED_QTY,
            quantity_rejected=Decimal("0"), location_id=s.loc_staging_id, uom="UN",
        )],
    )
    await s.db.flush()
    assert grn.requires_qc is True

    await inbound.confirm_grn(grn.id)
    await s.db.flush()
    grn = await inbound.grn_repo.get_by_id(grn.id)
    assert grn.status == GRNStatus.CONFIRMED  # pendiente de QC, no fue directo a putaway

    qi = await inbound.qi_repo.get_by_grn(grn.id)
    assert qi is not None, "confirm_grn debe autogenerar la QC pendiente por ruptura de cadena de frío"

    qc_result = await inbound.resolve_quality_inspection(
        qi.id, approved=True, disposition="accept", disposition_notes="Aprobado tras inspección visual",
    )
    await s.db.flush()
    assert qc_result["approved"] is True

    grn = await inbound.grn_repo.get_by_id(grn.id)
    assert grn.status == GRNStatus.PUTAWAY_IN_PROGRESS

    putaway_tasks = (await s.db.execute(
        select(PutawayTask).where(PutawayTask.grn_id == grn.id)
    )).scalars().all()
    assert len(putaway_tasks) == 1
    putaway = putaway_tasks[0]
    assert putaway.quantity == RECEIVED_QTY

    await inbound.start_putaway_task(putaway.id)
    await s.db.flush()
    # La sugerencia automática (regla simplificada: menor pick_sequence activo)
    # apunta al frente de picking; el operario decide ubicarlo en reserva por
    # ser exceso de stock, así que se requiere override_reason. Esto deja el
    # producto en la zona RESERVA (no en la dorada) para que el motor de
    # slotting recomiende luego moverlo a la zona de picking.
    await inbound.complete_putaway_task(
        putaway.id, actual_location=str(s.loc_storage_id),
        override_reason="Exceso de stock: se ubica en reserva en vez del frente de picking sugerido",
    )
    await s.db.flush()

    grn = await inbound.grn_repo.get_by_id(grn.id)
    assert grn.status == GRNStatus.COMPLETED  # todos los putaway completados

    level_after_putaway = (await s.db.execute(
        select(InventoryLevel).where(and_(
            InventoryLevel.tenant_id == s.tenant_id, InventoryLevel.product_id == s.product_id,
            InventoryLevel.location_id == s.loc_storage_id,
        ))
    )).scalar_one()
    assert level_after_putaway.quantity_on_hand == RECEIVED_QTY
    assert level_after_putaway.quantity_available == RECEIVED_QTY

    # ═══ 2) LABOR: estándar de putaway + tarea con ciclo completo y performance ═══
    standard = LaborStandard(
        id=uuid4(), tenant_id=s.tenant_id, activity_type="putaway", uom="unit",
        fixed_minutes=Decimal("2"), std_minutes_per_unit=Decimal("0.1"), is_active=True,
    )
    s.db.add(standard)
    await s.db.flush()

    labor_task = await labor.create_task(
        tenant_id=s.tenant_id,
        data=dict(warehouse_id=s.warehouse_id, activity_type="putaway",
                  quantity=RECEIVED_QTY, uom="unit", user_id=s.user_id,
                  reference_type="putaway_task", reference_id=putaway.id),
        user_id=s.user_id,
    )
    await labor.start_task(s.tenant_id, labor_task.id)
    await labor.complete_task(s.tenant_id, labor_task.id)
    await s.db.flush()

    completed_task = await labor._get_task(s.tenant_id, labor_task.id)
    assert completed_task.status == "completed"
    # estándar = 2 + 0.1*100 = 12.0 minutos
    assert completed_task.standard_minutes == Decimal("12.0000")
    assert completed_task.performance_pct is not None

    # ═══ 3) OUTBOUND · SO-A por WAVE: confirmar → wave → pick → pack → ship → deliver ═══
    so_a = await outbound.create_sales_order(
        warehouse_id=s.warehouse_id, customer_id=s.customer_id, order_date=datetime.now(timezone.utc),
        lines_data=[dict(product_id=s.product_id, quantity_ordered=SO_A_QTY, unit_price=Decimal("9.99"))],
    )
    await s.db.flush()
    await outbound.confirm_sales_order(so_a.id)
    await s.db.flush()
    so_a = await outbound.so_repo.get_by_id(so_a.id)
    assert so_a.lines[0].quantity_allocated == SO_A_QTY  # stock disponible → reservado, no backorder

    wave = await outbound.create_wave(warehouse_id=s.warehouse_id, so_ids=[so_a.id])
    await s.db.flush()
    pick_tasks_a = await outbound.release_wave(wave.id)
    await s.db.flush()
    assert len(pick_tasks_a) == 1
    pick_a = pick_tasks_a[0]

    await outbound.start_pick_task(pick_a.id)
    await s.db.flush()
    pick_result = await outbound.complete_pick_task(pick_a.id, quantity_picked=SO_A_QTY)
    await s.db.flush()
    assert pick_result["so_ready_for_packing"] is True

    so_a = await outbound.so_repo.get_by_id(so_a.id)
    pack_task = await outbound.pack_repo.get_by_so(so_a.id)
    assert pack_task is not None

    await outbound.start_pack_task(pack_task.id)
    await s.db.flush()
    await outbound.complete_pack_task(
        pack_task.id, box_type="BOX-M", box_count=1,
        total_weight_kg=Decimal("12.5"), sscc=generate_sscc(company_prefix="0000000"),
    )
    await s.db.flush()
    so_a = await outbound.so_repo.get_by_id(so_a.id)
    assert so_a.status.value == "packed"

    shipment = await outbound.create_shipment(
        so_a.id, data={"warehouse_id": s.warehouse_id, "carrier_name": "DHL Panamá"},
    )
    await s.db.flush()
    await outbound.dispatch_shipment(shipment.id, {"tracking_number": "TRK-0001"})
    await s.db.flush()
    await outbound.deliver_shipment(shipment.id, {"delivered_to_name": "Juan Pérez"})
    await s.db.flush()

    so_a = await outbound.so_repo.get_by_id(so_a.id)
    assert so_a.status.value == "delivered"

    # ═══ 4) OUTBOUND · SO-B por STREAMING (waveless): confirmar → enqueue → next → pick ═══
    so_b = await outbound.create_sales_order(
        warehouse_id=s.warehouse_id, customer_id=s.customer_id, order_date=datetime.now(timezone.utc),
        lines_data=[dict(product_id=s.product_id, quantity_ordered=SO_B_QTY, unit_price=Decimal("9.99"))],
    )
    await s.db.flush()
    await outbound.confirm_sales_order(so_b.id)
    await s.db.flush()
    so_b = await outbound.so_repo.get_by_id(so_b.id)
    so_b_line = so_b.lines[0]

    # El streaming despacha por line.location_id ya asignado (no hace FEFO por sí
    # mismo); en el flujo real esa asignación la hace la ola o un paso previo.
    so_b_line.location_id = s.loc_storage_id
    await s.db.flush()

    enqueue_result = await streaming.enqueue_order(s.tenant_id, so_b.id, s.user_id)
    await s.db.flush()
    assert enqueue_result["tasks_created"] == 1

    dispatched = await streaming.stream_next(
        s.tenant_id, s.warehouse_id, s.user_id, current_pick_sequence=None, max_wip=1,
    )
    await s.db.flush()
    assert dispatched is not None
    assert dispatched.wave_id is None  # waveless

    await outbound.start_pick_task(dispatched.id)
    await s.db.flush()
    await outbound.complete_pick_task(dispatched.id, quantity_picked=SO_B_QTY)
    await s.db.flush()

    streaming_metrics = await streaming.get_metrics(s.tenant_id, s.warehouse_id)
    assert streaming_metrics["queue_pending"] == 0

    # ═══ 5) SLOTTING: política → análisis ABC → recomendación → aplicar ═══
    policy = SlottingPolicy(
        id=uuid4(), tenant_id=s.tenant_id, warehouse_id=s.warehouse_id,
        golden_zone_code=s.zone_pick_code, bulk_zone_code=s.zone_reserve_code, is_active=True,
    )
    s.db.add(policy)
    await s.db.flush()

    analysis = await slotting.analyze_and_generate(s.tenant_id, s.warehouse_id, persist=True)
    await s.db.flush()
    assert analysis["products_analyzed"] == 1
    assert analysis["abc_counts"]["A"] == 1  # único producto → 100% de la velocidad → clase A
    assert analysis["recommendations_created"] == 1  # está en RSV, no en la zona dorada → recomienda mover

    product = await s.db.get(Product, s.product_id)
    assert product.abc_classification == "A"

    rec = (await s.db.execute(
        select(SlottingRecommendation).where(SlottingRecommendation.warehouse_id == s.warehouse_id)
    )).scalar_one()
    assert rec.recommended_zone_code == s.zone_pick_code
    assert rec.recommended_location_id == s.loc_pickface_id  # único candidato en zona dorada

    applied = await slotting.apply_recommendation(s.tenant_id, rec.id, s.user_id)
    await s.db.flush()
    assert applied.status == "applied"

    # ═══ 6) KPIs: inbound, outbound y labor responden sin error con datos reales ═══
    inbound_kpis = await inbound.get_dashboard_metrics(s.warehouse_id)
    assert inbound_kpis["grns_today"] >= 1

    outbound_kpis = await outbound.get_dashboard_metrics(s.warehouse_id)
    assert outbound_kpis is not None

    labor_kpis = await labor.get_dashboard_metrics(s.tenant_id, s.warehouse_id, window_days=7)
    assert labor_kpis["tasks_completed"] >= 1
    assert labor_kpis["total_standard_hours"] > 0

    # ═══ 7) RECONCILIACIÓN: kardex (movimientos) == stock final (FR-042) ═══
    net_movements = (await s.db.execute(
        select(
            func.coalesce(func.sum(InventoryMovement.quantity).filter(
                InventoryMovement.movement_type == MovementType.RECEIPT), 0),
            func.coalesce(func.sum(InventoryMovement.quantity).filter(
                InventoryMovement.movement_type == MovementType.PICK), 0),
        ).where(and_(
            InventoryMovement.tenant_id == s.tenant_id,
            InventoryMovement.warehouse_id == s.warehouse_id,
            InventoryMovement.product_id == s.product_id,
        ))
    )).one()
    total_received, total_picked = net_movements[0], net_movements[1]
    kardex_net = total_received - total_picked

    total_on_hand = (await s.db.execute(
        select(func.coalesce(func.sum(InventoryLevel.quantity_on_hand), 0)).where(and_(
            InventoryLevel.tenant_id == s.tenant_id,
            InventoryLevel.warehouse_id == s.warehouse_id,
            InventoryLevel.product_id == s.product_id,
        ))
    )).scalar_one()

    assert total_received == RECEIVED_QTY
    assert total_picked == SO_A_QTY + SO_B_QTY
    assert kardex_net == total_on_hand == RECEIVED_QTY - SO_A_QTY - SO_B_QTY
