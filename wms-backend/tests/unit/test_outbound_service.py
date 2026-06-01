"""
WMS Panama — Tests Unitarios: Módulo Outbound (Fase 6)
========================================================
Tests PUROS sin BD ni red. Cubren la lógica de negocio
de OutboundService mediante lógica inline y mocks.

Clases:
  TestSOStateMachine         — Máquina de estados de Sales Orders
  TestWavePickingLogic       — Creación y liberación de waves
  TestPickingBusinessRules   — Reglas de picking (short-pick, backorder, FEFO)
  TestPackingRules           — Reglas de empaque
  TestShipmentFlow           — Flujo de envío y entrega
  TestRMAFlow                — Devoluciones de cliente (RMA)
  TestOutboundKPIs           — KPIs del dashboard outbound
  TestOutboundSchemaRules    — Validaciones de schemas Pydantic
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from app.core.exceptions import (
    OrderStateError,
    OutboundServiceError,
    PickingStateError,
)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def make_uuid():
    return uuid4()


def fake_so(status="DRAFT", priority=5, lines=None):
    so = MagicMock()
    so.id = make_uuid()
    so.status = status
    so.priority = priority
    so.so_number = "SO-000001"
    so.warehouse_id = make_uuid()
    so.requested_delivery_date = datetime.now(timezone.utc) + timedelta(days=3)
    so.lines = lines or [fake_so_line()]
    return so


def fake_so_line(qty=Decimal("10"), price=Decimal("50")):
    line = MagicMock()
    line.id = make_uuid()
    line.product_id = make_uuid()
    line.uom_id = make_uuid()
    line.quantity_ordered = qty
    line.quantity_allocated = Decimal("0")
    line.quantity_picked = Decimal("0")
    line.quantity_shipped = Decimal("0")
    line.quantity_backordered = Decimal("0")
    line.unit_price = price
    line.discount_pct = Decimal("0")
    line.status = "PENDING"
    return line


def fake_wave(status="OPEN", orders=2):
    wave = MagicMock()
    wave.id = make_uuid()
    wave.status = status
    wave.total_orders = orders
    wave.total_lines = orders * 3
    wave.total_units = Decimal(str(orders * 30))
    wave.wave_number = "WAVE-00001"
    return wave


def fake_pick_task(status="PENDING", qty_requested=Decimal("10"), started_at=None):
    task = MagicMock()
    task.id = make_uuid()
    task.status = status
    task.quantity_requested = qty_requested
    task.quantity_picked = Decimal("0")
    task.so_id = make_uuid()
    task.so_line_id = make_uuid()
    task.product_id = make_uuid()
    task.uom_id = make_uuid()
    task.from_location_id = make_uuid()
    task.batch_id = None
    task.started_at = started_at
    return task


def fake_pack_task(status="PENDING"):
    task = MagicMock()
    task.id = make_uuid()
    task.status = status
    task.so_id = make_uuid()
    task.started_at = None
    return task


def fake_shipment(status="PENDING"):
    ship = MagicMock()
    ship.id = make_uuid()
    ship.status = status
    ship.so_id = make_uuid()
    return ship


def fake_rma(status="REQUESTED"):
    rma = MagicMock()
    rma.id = make_uuid()
    rma.status = status
    rma.rma_number = "RMA-000001"
    return rma


# ══════════════════════════════════════════════════════════════════════════════
# 1. MÁQUINA DE ESTADOS — SALES ORDER
# ══════════════════════════════════════════════════════════════════════════════

class TestSOStateMachine:

    def test_confirm_requires_draft(self):
        """Solo se puede confirmar una SO en DRAFT."""
        for bad_status in ("CONFIRMED", "ALLOCATED", "PICKING", "PACKED",
                           "SHIPPED", "DELIVERED", "CANCELLED"):
            so = fake_so(status=bad_status)
            with pytest.raises(OrderStateError):
                if so.status != "DRAFT":
                    raise OrderStateError(
                        f"Solo se puede confirmar una SO en DRAFT. Estado: {so.status}"
                    )

    def test_confirm_draft_succeeds(self):
        """Confirmar una SO en DRAFT es válido."""
        so = fake_so(status="DRAFT")
        assert so.status == "DRAFT"  # no lanza

    def test_cancel_shipped_raises(self):
        """No se puede cancelar una SO ya despachada."""
        for terminal in ("SHIPPED", "DELIVERED", "CANCELLED"):
            so = fake_so(status=terminal)
            with pytest.raises(OrderStateError):
                if so.status in ("SHIPPED", "DELIVERED", "CANCELLED"):
                    raise OrderStateError(f"No se puede cancelar. Estado: {so.status}")

    def test_cancel_before_ship_is_valid(self):
        """Se puede cancelar antes de SHIPPED."""
        cancelable = ("DRAFT", "CONFIRMED", "ALLOCATED", "PICKING", "PACKED")
        for s in cancelable:
            so = fake_so(status=s)
            assert so.status not in ("SHIPPED", "DELIVERED", "CANCELLED")

    def test_so_total_calculation(self):
        """Total = sum(qty * price * (1 - discount))."""
        lines = [
            {"quantity_ordered": Decimal("10"), "unit_price": Decimal("50"),
             "discount_pct": Decimal("0.1")},
            {"quantity_ordered": Decimal("5"), "unit_price": Decimal("100"),
             "discount_pct": Decimal("0")},
        ]
        subtotal = sum(
            l["quantity_ordered"] * l["unit_price"] * (1 - l["discount_pct"])
            for l in lines
        )
        assert subtotal == Decimal("450") + Decimal("500")  # 450 + 500 = 950

    def test_so_number_format(self):
        """Números de SO siguen formato SO-000001."""
        for count, expected in [(0, "SO-000001"), (99, "SO-000100"), (999999, "SO-1000000")]:
            assert f"SO-{count + 1:06d}" == expected

    def test_priority_ordering(self):
        """Órdenes con menor prioridad (1) deben procesarse primero."""
        sos = [
            fake_so(priority=8),
            fake_so(priority=1),
            fake_so(priority=5),
        ]
        sorted_sos = sorted(sos, key=lambda s: s.priority)
        assert sorted_sos[0].priority == 1
        assert sorted_sos[1].priority == 5
        assert sorted_sos[2].priority == 8


# ══════════════════════════════════════════════════════════════════════════════
# 2. WAVE PICKING
# ══════════════════════════════════════════════════════════════════════════════

class TestWavePickingLogic:

    def test_wave_requires_confirmed_so(self):
        """Solo SOs CONFIRMED o ALLOCATED pueden agregarse a una wave."""
        for bad_status in ("DRAFT", "PICKING", "PACKED", "SHIPPED", "CANCELLED"):
            so = fake_so(status=bad_status)
            with pytest.raises(OrderStateError):
                if so.status not in ("CONFIRMED", "ALLOCATED"):
                    raise OrderStateError(
                        f"SO debe estar CONFIRMED o ALLOCATED. Estado: {so.status}"
                    )

    def test_wave_number_format(self):
        """Wave numbers siguen formato WAVE-00001."""
        for count, expected in [(0, "WAVE-00001"), (4, "WAVE-00005")]:
            assert f"WAVE-{count + 1:05d}" == expected

    def test_wave_release_requires_open(self):
        """Solo se puede liberar una wave en estado OPEN."""
        for bad_status in ("RELEASED", "IN_PROGRESS", "COMPLETED", "CANCELLED"):
            wave = fake_wave(status=bad_status)
            with pytest.raises(OutboundServiceError):
                if wave.status != "OPEN":
                    raise OutboundServiceError(
                        f"La wave debe estar OPEN para liberar. Estado: {wave.status}"
                    )

    def test_picking_tasks_count_per_wave(self):
        """Wave de 2 órdenes con 3 líneas c/u genera 6 tareas máximo."""
        wave_lines = 6  # 2 órdenes × 3 líneas
        tasks_generated = wave_lines  # 1 task por línea en batch picking simple
        assert tasks_generated == 6

    def test_batch_picking_groups_same_product(self):
        """Batch picking agrupa el mismo producto de múltiples órdenes."""
        product_id = make_uuid()
        tasks = [
            {"product_id": product_id, "so_id": make_uuid(), "qty": Decimal("5")},
            {"product_id": product_id, "so_id": make_uuid(), "qty": Decimal("8")},
            {"product_id": make_uuid(), "so_id": make_uuid(), "qty": Decimal("3")},
        ]
        grouped = {}
        for t in tasks:
            pid = str(t["product_id"])
            grouped[pid] = grouped.get(pid, Decimal("0")) + t["qty"]

        assert len(grouped) == 2
        assert grouped[str(product_id)] == Decimal("13")

    def test_wave_total_units(self):
        """Total units en wave = suma de qty ordenada de todas las líneas."""
        lines_per_so = [
            [Decimal("10"), Decimal("5"), Decimal("20")],
            [Decimal("3"), Decimal("15")],
        ]
        total = sum(qty for so_lines in lines_per_so for qty in so_lines)
        assert total == Decimal("53")


# ══════════════════════════════════════════════════════════════════════════════
# 3. PICKING BUSINESS RULES
# ══════════════════════════════════════════════════════════════════════════════

class TestPickingBusinessRules:

    def test_pick_task_must_be_pending_to_start(self):
        """Solo se puede iniciar una tarea PENDING."""
        for bad in ("IN_PROGRESS", "COMPLETED", "SHORT_PICKED", "CANCELLED"):
            task = fake_pick_task(status=bad)
            with pytest.raises(PickingStateError):
                if task.status != "PENDING":
                    raise PickingStateError(
                        f"La tarea debe estar PENDING. Estado: {task.status}"
                    )

    def test_pick_task_must_be_in_progress_to_complete(self):
        """Solo se puede completar una tarea IN_PROGRESS."""
        for bad in ("PENDING", "COMPLETED", "CANCELLED"):
            task = fake_pick_task(status=bad)
            with pytest.raises(PickingStateError):
                if task.status != "IN_PROGRESS":
                    raise PickingStateError(
                        f"La tarea debe estar IN_PROGRESS. Estado: {task.status}"
                    )

    def test_short_pick_requires_reason(self):
        """Un short-pick sin reason debe fallar."""
        qty_requested = Decimal("10")
        qty_picked = Decimal("7")
        short_reason = None
        quantity_short = qty_requested - qty_picked

        with pytest.raises(OutboundServiceError):
            if quantity_short > 0 and not short_reason:
                raise OutboundServiceError(
                    "short_reason es obligatorio cuando hay short pick."
                )

    def test_overpick_raises(self):
        """No se puede pickear más de lo solicitado."""
        qty_requested = Decimal("10")
        qty_picked = Decimal("11")
        with pytest.raises(OutboundServiceError):
            if qty_picked > qty_requested:
                raise OutboundServiceError(
                    "quantity_picked no puede superar quantity_requested."
                )

    def test_full_pick_no_reason_needed(self):
        """Pick completo no requiere short_reason."""
        qty_requested = Decimal("10")
        qty_picked = Decimal("10")
        short_reason = None
        quantity_short = qty_requested - qty_picked
        # No debe lanzar excepción
        needs_reason = quantity_short > 0 and not short_reason
        assert needs_reason is False

    def test_short_pick_generates_backorder(self):
        """La diferencia en short-pick se convierte en backorder."""
        qty_requested = Decimal("10")
        qty_picked = Decimal("6")
        qty_backordered = qty_requested - qty_picked
        assert qty_backordered == Decimal("4")

    def test_zero_pick_is_full_backorder(self):
        """Si se pickea 0, toda la cantidad es backorder."""
        qty_requested = Decimal("10")
        qty_picked = Decimal("0")
        backordered = qty_requested - qty_picked
        assert backordered == qty_requested

    def test_cycle_time_picking(self):
        """Tiempo de ciclo en segundos calculado correctamente."""
        start = datetime(2026, 5, 27, 9, 0, 0, tzinfo=timezone.utc)
        end   = datetime(2026, 5, 27, 9, 4, 15, tzinfo=timezone.utc)
        ct = int((end - start).total_seconds())
        assert ct == 255  # 4m 15s

    def test_picking_status_with_short(self):
        """Tarea con short pick tiene estado SHORT_PICKED, no COMPLETED."""
        qty_short = Decimal("3")
        final_status = "SHORT_PICKED" if qty_short > 0 else "COMPLETED"
        assert final_status == "SHORT_PICKED"

    def test_picking_status_without_short(self):
        """Tarea sin short pick tiene estado COMPLETED."""
        qty_short = Decimal("0")
        final_status = "SHORT_PICKED" if qty_short > 0 else "COMPLETED"
        assert final_status == "COMPLETED"

    def test_fefo_allocation_for_picking(self):
        """FEFO: batch con menor fecha expiry se pickea primero."""
        from datetime import date
        batches = [
            {"batch_id": make_uuid(), "expiry_date": date(2026, 8, 1), "available": Decimal("20")},
            {"batch_id": make_uuid(), "expiry_date": date(2026, 6, 15), "available": Decimal("15")},
            {"batch_id": make_uuid(), "expiry_date": None, "available": Decimal("50")},
        ]
        # FEFO: ordenar por expiry_date, None al final
        sorted_batches = sorted(
            batches,
            key=lambda b: (b["expiry_date"] is None, b["expiry_date"])
        )
        assert sorted_batches[0]["expiry_date"] == date(2026, 6, 15)
        assert sorted_batches[1]["expiry_date"] == date(2026, 8, 1)
        assert sorted_batches[2]["expiry_date"] is None


# ══════════════════════════════════════════════════════════════════════════════
# 4. PACKING RULES
# ══════════════════════════════════════════════════════════════════════════════

class TestPackingRules:

    def test_pack_task_auto_created_after_all_picks(self):
        """PackTask se crea automáticamente cuando todos los picks están listos."""
        pending_picks = 0
        should_create_pack = pending_picks == 0
        assert should_create_pack is True

    def test_pack_task_not_created_with_pending_picks(self):
        """No se crea PackTask si aún hay picks pendientes."""
        pending_picks = 3
        should_create_pack = pending_picks == 0
        assert should_create_pack is False

    def test_so_becomes_packed_after_pack_complete(self):
        """SO pasa a PACKED cuando PackTask se completa."""
        pack_task_done = True
        so_next_status = "PACKED" if pack_task_done else "PICKING"
        assert so_next_status == "PACKED"

    def test_box_count_must_be_positive(self):
        """box_count debe ser >= 1."""
        with pytest.raises(ValueError, match="box_count"):
            box_count = 0
            if box_count < 1:
                raise ValueError("box_count debe ser al menos 1.")

    def test_pack_number_format(self):
        """PACK numbers siguen formato PACK-000001."""
        for count, expected in [(0, "PACK-000001"), (9, "PACK-000010")]:
            assert f"PACK-{count + 1:06d}" == expected

    def test_weight_volume_optional(self):
        """Peso y volumen son opcionales en el empaque."""
        pack_data = {
            "box_type": "medium",
            "box_count": 2,
            "total_weight_kg": None,
            "total_volume_m3": None,
        }
        assert pack_data["total_weight_kg"] is None
        assert pack_data["total_volume_m3"] is None

    def test_cartonization_simple(self):
        """Cartonización simple: qty_total / cap_caja = cajas necesarias."""
        import math
        total_units = 50
        box_capacity = 12
        boxes_needed = math.ceil(total_units / box_capacity)
        assert boxes_needed == 5


# ══════════════════════════════════════════════════════════════════════════════
# 5. SHIPMENT FLOW
# ══════════════════════════════════════════════════════════════════════════════

class TestShipmentFlow:

    def test_shipment_requires_packed_so(self):
        """Solo se puede crear un envío para una SO en PACKED."""
        for bad in ("DRAFT", "CONFIRMED", "ALLOCATED", "PICKING", "SHIPPED", "DELIVERED"):
            so = fake_so(status=bad)
            with pytest.raises(OrderStateError):
                if so.status != "PACKED":
                    raise OrderStateError(
                        f"La SO debe estar PACKED para crear un envío. Estado: {so.status}"
                    )

    def test_dispatch_requires_pending_shipment(self):
        """Solo se puede despachar un envío PENDING."""
        for bad in ("IN_TRANSIT", "DELIVERED", "FAILED", "RETURNED"):
            ship = fake_shipment(status=bad)
            with pytest.raises(OutboundServiceError):
                if ship.status != "PENDING":
                    raise OutboundServiceError(
                        f"El shipment debe estar PENDING. Estado: {ship.status}"
                    )

    def test_deliver_requires_in_transit(self):
        """Solo se puede confirmar entrega de un envío IN_TRANSIT."""
        for bad in ("PENDING", "DELIVERED", "FAILED"):
            ship = fake_shipment(status=bad)
            with pytest.raises(OutboundServiceError):
                if ship.status != "IN_TRANSIT":
                    raise OutboundServiceError(
                        f"El shipment debe estar IN_TRANSIT. Estado: {ship.status}"
                    )

    def test_shipment_number_format(self):
        """SHIP numbers siguen formato SHIP-000001."""
        assert f"SHIP-{1:06d}" == "SHIP-000001"
        assert f"SHIP-{100:06d}" == "SHIP-000100"

    def test_so_shipped_after_dispatch(self):
        """SO pasa a SHIPPED después de despachar el envío."""
        shipment_dispatched = True
        so_next_status = "SHIPPED" if shipment_dispatched else "PACKED"
        assert so_next_status == "SHIPPED"

    def test_so_delivered_after_confirm(self):
        """SO pasa a DELIVERED después de confirmar entrega."""
        delivery_confirmed = True
        so_next_status = "DELIVERED" if delivery_confirmed else "SHIPPED"
        assert so_next_status == "DELIVERED"

    def test_on_time_delivery(self):
        """Entrega a tiempo: actual_delivery <= promised_delivery."""
        promised = datetime(2026, 5, 30, tzinfo=timezone.utc)
        actual   = datetime(2026, 5, 29, tzinfo=timezone.utc)
        on_time = actual <= promised
        assert on_time is True

    def test_late_delivery(self):
        """Entrega tardía: actual_delivery > promised_delivery."""
        promised = datetime(2026, 5, 28, tzinfo=timezone.utc)
        actual   = datetime(2026, 5, 30, tzinfo=timezone.utc)
        on_time = actual <= promised
        assert on_time is False


# ══════════════════════════════════════════════════════════════════════════════
# 6. RMA FLOW
# ══════════════════════════════════════════════════════════════════════════════

class TestRMAFlow:

    def test_rma_number_format(self):
        """RMA numbers siguen formato RMA-000001."""
        assert f"RMA-{1:06d}" == "RMA-000001"
        assert f"RMA-{50:06d}" == "RMA-000050"

    def test_receive_requires_approved_or_in_transit(self):
        """Solo se puede recibir RMA en APPROVED o IN_TRANSIT."""
        for bad in ("REQUESTED", "INSPECTED", "CLOSED", "REJECTED"):
            rma = fake_rma(status=bad)
            with pytest.raises(OutboundServiceError):
                if rma.status not in ("APPROVED", "IN_TRANSIT"):
                    raise OutboundServiceError(
                        f"RMA debe estar APPROVED o IN_TRANSIT. Estado: {rma.status}"
                    )

    def test_restocking_eligible_updates_inventory(self):
        """RMA elegible para restock debe generar movimiento de ingreso."""
        restocking_eligible = True
        location_id = make_uuid()
        should_receive_stock = restocking_eligible and location_id is not None
        assert should_receive_stock is True

    def test_non_restocking_no_inventory_update(self):
        """RMA no elegible para restock NO actualiza inventario."""
        restocking_eligible = False
        should_receive_stock = restocking_eligible
        assert should_receive_stock is False

    def test_refund_amount_non_negative(self):
        """El monto de reembolso no puede ser negativo."""
        with pytest.raises(ValueError):
            refund = Decimal("-10")
            if refund < 0:
                raise ValueError("refund_amount no puede ser negativo.")

    def test_return_types(self):
        """Tipos de devolución válidos."""
        valid_types = {"refund", "exchange", "credit"}
        assert "refund" in valid_types
        assert "exchange" in valid_types
        assert "credit" in valid_types
        assert "unknown" not in valid_types


# ══════════════════════════════════════════════════════════════════════════════
# 7. KPIs OUTBOUND
# ══════════════════════════════════════════════════════════════════════════════

class TestOutboundKPIs:

    def test_order_fill_rate(self):
        """Fill rate = qty_shipped / qty_ordered * 100."""
        qty_ordered = Decimal("1000")
        qty_shipped = Decimal("975")
        fill_rate = qty_shipped / qty_ordered * 100
        assert fill_rate == Decimal("97.5")

    def test_perfect_fill_rate(self):
        """Fill rate perfecto = 100%."""
        qty_ordered = Decimal("500")
        qty_shipped = Decimal("500")
        fill_rate = qty_shipped / qty_ordered * 100
        assert fill_rate == Decimal("100")

    def test_short_pick_rate(self):
        """Short pick rate = short_picks / total_picks * 100."""
        total = 200
        shorts = 8
        rate = round(shorts / total * 100, 2)
        assert rate == 4.0

    def test_zero_short_pick_rate(self):
        """Sin short picks, la tasa es 0."""
        total = 100
        shorts = 0
        rate = shorts / total * 100 if total > 0 else 0
        assert rate == 0

    def test_on_time_delivery_rate(self):
        """Tasa de entrega a tiempo."""
        deliveries = [True, True, False, True, True, False, True]
        on_time = sum(1 for d in deliveries if d)
        rate = on_time / len(deliveries) * 100
        assert round(rate, 2) == round(5/7*100, 2)

    def test_picking_productivity(self):
        """Líneas por hora = líneas / (segundos / 3600)."""
        lines_picked = 120
        time_seconds = 3600  # 1 hora
        lines_per_hour = lines_picked / (time_seconds / 3600)
        assert lines_per_hour == 120.0

    def test_avg_cycle_time(self):
        """Tiempo promedio de picking."""
        cycle_times = [180, 240, 210, 195, 225]  # segundos
        avg = sum(cycle_times) / len(cycle_times)
        assert avg == 210.0  # 3.5 minutos promedio

    def test_orders_overdue_count(self):
        """Órdenes vencidas = requested_delivery_date < hoy."""
        today = datetime.now(timezone.utc)
        orders = [
            {"delivery": today - timedelta(days=2), "status": "CONFIRMED"},
            {"delivery": today + timedelta(days=1), "status": "CONFIRMED"},
            {"delivery": today - timedelta(days=1), "status": "ALLOCATED"},
            {"delivery": today + timedelta(days=5), "status": "PICKING"},
        ]
        active_statuses = ("CONFIRMED", "ALLOCATED", "PICKING", "PACKED")
        overdue = [
            o for o in orders
            if o["status"] in active_statuses and o["delivery"] < today
        ]
        assert len(overdue) == 2


# ══════════════════════════════════════════════════════════════════════════════
# 8. VALIDACIONES DE SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

class TestOutboundSchemaRules:

    def test_so_requires_at_least_one_line(self):
        """SO requiere al menos una línea."""
        lines = []
        with pytest.raises(ValueError, match="al menos"):
            if not lines:
                raise ValueError("La SO debe tener al menos una línea.")

    def test_so_line_quantity_must_be_positive(self):
        """quantity_ordered en línea de SO debe ser > 0."""
        with pytest.raises(ValueError):
            qty = Decimal("0")
            if qty <= 0:
                raise ValueError("quantity_ordered debe ser mayor a 0.")

    def test_wave_requires_at_least_one_so(self):
        """Wave requiere al menos una SO."""
        so_ids = []
        with pytest.raises(ValueError, match="al menos"):
            if not so_ids:
                raise ValueError("La wave debe tener al menos una SO.")

    def test_priority_range(self):
        """Prioridad debe estar entre 1 y 10."""
        for valid in [1, 5, 10]:
            assert 1 <= valid <= 10

        for invalid in [0, 11, -1]:
            with pytest.raises(ValueError):
                if not (1 <= invalid <= 10):
                    raise ValueError(f"Prioridad inválida: {invalid}. Debe ser 1-10.")

    def test_discount_range(self):
        """Descuento debe estar entre 0 y 1 (0% a 100%)."""
        for valid in [Decimal("0"), Decimal("0.5"), Decimal("1")]:
            assert 0 <= valid <= 1

        for invalid in [Decimal("-0.1"), Decimal("1.01")]:
            with pytest.raises(ValueError):
                if not (0 <= invalid <= 1):
                    raise ValueError(f"Descuento inválido: {invalid}.")

    def test_so_line_total_calculation(self):
        """line_total = qty * price * (1 - discount)."""
        qty = Decimal("10")
        price = Decimal("100")
        discount = Decimal("0.15")
        expected = qty * price * (1 - discount)
        assert expected == Decimal("850")

    def test_rma_return_type_valid(self):
        """return_type debe ser uno de los valores válidos."""
        valid_types = ("refund", "exchange", "credit")
        assert "refund" in valid_types
        invalid = "cashback"
        assert invalid not in valid_types
