"""
WMS Panamá — Tests Unitarios: Labor Management (FR-090…093)
============================================================
Tests PUROS sin BD ni red. Cubren la lógica de negocio de LaborService:
cálculo de estándar/real/desempeño, motor de interleaving y máquina de estados.

Ejecutar:  pytest tests/unit/test_labor_service.py --noconftest
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import LaborTaskStateError
from app.services.labor_service import LaborService


def _dt(minutes_offset=0):
    return datetime(2026, 7, 14, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes_offset)


def fake_task(zone=None, priority=5, created_offset=0, task_id=None):
    t = MagicMock()
    t.id = task_id or uuid4()
    t.zone = zone
    t.priority = priority
    t.created_at = _dt(created_offset)
    return t


# ── Cálculo de tiempo estándar ─────────────────────────────────────────────────
class TestStandardMinutes:
    def test_fixed_plus_variable(self):
        # 2 min de setup + 0.5 min por unidad × 10 unidades = 7.0
        assert LaborService.compute_standard_minutes(2, Decimal("0.5"), 10) == Decimal("7.0000")

    def test_zero_quantity_is_fixed_only(self):
        assert LaborService.compute_standard_minutes(3, 1, 0) == Decimal("3.0000")

    def test_handles_none(self):
        assert LaborService.compute_standard_minutes(None, None, None) == Decimal("0.0000")


# ── Cálculo de tiempo real ─────────────────────────────────────────────────────
class TestActualMinutes:
    def test_elapsed(self):
        assert LaborService.compute_actual_minutes(_dt(0), _dt(6)) == Decimal("6.0000")

    def test_negative_clamped_to_zero(self):
        assert LaborService.compute_actual_minutes(_dt(6), _dt(0)) == Decimal("0.0000")

    def test_missing_timestamps_raises(self):
        with pytest.raises(LaborTaskStateError):
            LaborService.compute_actual_minutes(None, _dt(6))


# ── Cálculo de desempeño ───────────────────────────────────────────────────────
class TestPerformance:
    def test_on_standard_is_100(self):
        assert LaborService.compute_performance_pct(Decimal("6"), Decimal("6")) == Decimal("100.00")

    def test_faster_is_above_100(self):
        # estándar 6, real 4 → 150% (más rápido que el estándar)
        assert LaborService.compute_performance_pct(Decimal("6"), Decimal("4")) == Decimal("150.00")

    def test_slower_is_below_100(self):
        # estándar 6, real 12 → 50%
        assert LaborService.compute_performance_pct(Decimal("6"), Decimal("12")) == Decimal("50.00")

    def test_zero_actual_returns_none(self):
        assert LaborService.compute_performance_pct(Decimal("6"), Decimal("0")) is None


# ── Motor de interleaving ──────────────────────────────────────────────────────
class TestInterleaving:
    def test_empty_queue_returns_none(self):
        assert LaborService.choose_next_task([], current_zone="A") is None

    def test_prefers_same_zone(self):
        far = fake_task(zone="Z", priority=1)      # prioridad alta pero otra zona
        near = fake_task(zone="A", priority=5)     # misma zona
        chosen = LaborService.choose_next_task([far, near], current_zone="A")
        assert chosen is near  # misma zona gana pese a menor prioridad

    def test_priority_breaks_ties_within_zone(self):
        low = fake_task(zone="A", priority=8)
        high = fake_task(zone="A", priority=2)
        chosen = LaborService.choose_next_task([low, high], current_zone="A")
        assert chosen is high

    def test_created_at_breaks_priority_ties(self):
        newer = fake_task(zone="A", priority=5, created_offset=10)
        older = fake_task(zone="A", priority=5, created_offset=0)
        chosen = LaborService.choose_next_task([newer, older], current_zone="A")
        assert chosen is older

    def test_no_zone_context_falls_back_to_priority(self):
        a = fake_task(zone="X", priority=7)
        b = fake_task(zone="Y", priority=3)
        chosen = LaborService.choose_next_task([a, b], current_zone=None)
        assert chosen is b


# ── Integración de cálculo (completar una tarea, sin BD) ───────────────────────
class TestCompletionMath:
    def test_end_to_end_numbers(self):
        # estándar: 1 min fijo + 0.4/unid × 20 unid = 9 min; real 8 min → 112.5%
        std = LaborService.compute_standard_minutes(1, Decimal("0.4"), 20)
        act = LaborService.compute_actual_minutes(_dt(0), _dt(8))
        perf = LaborService.compute_performance_pct(std, act)
        assert std == Decimal("9.0000")
        assert act == Decimal("8.0000")
        assert perf == Decimal("112.50")
