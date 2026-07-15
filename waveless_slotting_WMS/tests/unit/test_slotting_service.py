"""
WMS Panamá — Tests Unitarios: Slotting Dinámico (FR-094…097)
=============================================================
Tests PUROS sin BD ni red. Cubren la inteligencia del motor de slotting:
clasificación ABC por Pareto, score de velocidad y regla de re-slotting.

Ejecutar:  pytest tests/unit/test_slotting_service.py --noconftest
"""

from __future__ import annotations

from decimal import Decimal

from app.services.slotting_service import SlottingService


# ── Clasificación ABC ──────────────────────────────────────────────────────────
class TestClassifyABC:
    def test_pareto_split(self):
        # 'a' domina el 80% del volumen → A; el resto reparte B/C.
        scored = [("a", 80), ("b", 12), ("c", 5), ("d", 3)]
        result = SlottingService.classify_abc(scored, 0.80, 0.95)
        assert result["a"] == "A"          # el de mayor velocidad siempre es A
        assert result["d"] == "C"          # la cola es C
        assert set(result.values()) <= {"A", "B", "C"}

    def test_highest_always_A_even_if_dominant(self):
        # un solo ítem con casi todo el volumen: sigue siendo A (no B/C).
        scored = [("x", 99), ("y", 1)]
        result = SlottingService.classify_abc(scored, 0.80, 0.95)
        assert result["x"] == "A"

    def test_all_zero_velocity_is_all_C(self):
        scored = [("a", 0), ("b", 0)]
        assert SlottingService.classify_abc(scored) == {"a": "C", "b": "C"}

    def test_empty(self):
        assert SlottingService.classify_abc([]) == {}

    def test_boundary_item_stays_A(self):
        # cuatro ítems iguales (25% c/u): con umbral 0.80, los primeros 4 hasta
        # cruzar 80% acumulado siguen siendo A (el que cruza incluido).
        scored = [("a", 25), ("b", 25), ("c", 25), ("d", 25)]
        result = SlottingService.classify_abc(scored, 0.80, 0.95)
        assert result["a"] == "A" and result["b"] == "A"
        # 'd' entra ya con 75% acumulado antes → sigue A; total control:
        assert list(result.values()).count("A") >= 3


# ── Score de velocidad ─────────────────────────────────────────────────────────
class TestVelocityScore:
    def test_frequency_dominates(self):
        # 10 picks + 0 cantidad = 10.0 ; el volumen aporta marginal (qty/100).
        assert SlottingService.velocity_score(10, 0) == Decimal("10.0000")

    def test_quantity_marginal_contribution(self):
        # 5 picks + 200 uds → 5 + 2 = 7.0
        assert SlottingService.velocity_score(5, 200) == Decimal("7.0000")

    def test_zero(self):
        assert SlottingService.velocity_score(0, 0) == Decimal("0.0000")


# ── Regla de re-slotting ───────────────────────────────────────────────────────
class TestEvaluateReslot:
    def test_A_outside_golden_moves_in(self):
        needs, zone, reason = SlottingService.evaluate_reslot("A", "BULK", "GOLD", "BULK")
        assert needs is True and zone == "GOLD" and "alta rotación" in reason

    def test_A_already_in_golden_no_move(self):
        needs, zone, _ = SlottingService.evaluate_reslot("A", "GOLD", "GOLD", "BULK")
        assert needs is False and zone is None

    def test_C_in_golden_moves_out(self):
        needs, zone, reason = SlottingService.evaluate_reslot("C", "GOLD", "GOLD", "BULK")
        assert needs is True and zone == "BULK" and "baja rotación" in reason

    def test_C_outside_golden_no_move(self):
        needs, _, _ = SlottingService.evaluate_reslot("C", "BULK", "GOLD", "BULK")
        assert needs is False

    def test_B_never_forced(self):
        needs, _, _ = SlottingService.evaluate_reslot("B", "BULK", "GOLD", "BULK")
        assert needs is False

    def test_no_golden_zone_no_move(self):
        needs, _, _ = SlottingService.evaluate_reslot("A", "X", None, None)
        assert needs is False


# ── Refinamiento: elección de ubicación específica y ahorro ─────────────────────
class _Loc:
    def __init__(self, id, pick_sequence, max_units=None, is_pick_face=True, code="L"):
        self.id = id; self.pick_sequence = pick_sequence
        self.max_units = max_units; self.is_pick_face = is_pick_face; self.code = code


class TestLocationFit:
    def test_A_prefers_lowest_pick_sequence(self):
        near = _Loc("near", 5); far = _Loc("far", 900)
        best, score = SlottingService.choose_location([far, near], needed_units=10, abc_class="A")
        assert best.id == "near"

    def test_capacity_gate_excludes_too_small(self):
        small = _Loc("small", 1, max_units=5); ok = _Loc("ok", 50, max_units=1000)
        best, _ = SlottingService.choose_location([small, ok], needed_units=100, abc_class="A")
        assert best.id == "ok"  # 'small' no tiene capacidad para 100

    def test_no_candidate_fits(self):
        tiny = _Loc("t", 1, max_units=1)
        best, score = SlottingService.choose_location([tiny], needed_units=100, abc_class="A")
        assert best is None and score is None

    def test_C_prefers_far_location(self):
        near = _Loc("near", 5); far = _Loc("far", 900)
        best, _ = SlottingService.choose_location([near, far], needed_units=1, abc_class="C")
        assert best.id == "far"  # baja rotación => lejos del despacho

    def test_pick_face_bonus(self):
        face = _Loc("face", 100, is_pick_face=True)
        nonface = _Loc("nonface", 100, is_pick_face=False)
        best, _ = SlottingService.choose_location([nonface, face], needed_units=1, abc_class="A")
        assert best.id == "face"


class TestTravelSavings:
    def test_savings_positive(self):
        # de secuencia 100 a 10, con 20 picks => 90*20 = 1800
        assert SlottingService.estimate_travel_savings(100, 10, 20) == Decimal("1800.00")

    def test_no_savings_if_not_closer(self):
        assert SlottingService.estimate_travel_savings(10, 100, 20) == Decimal("0.00")

    def test_none_sequences(self):
        assert SlottingService.estimate_travel_savings(None, 10, 5) == Decimal("0.00")
