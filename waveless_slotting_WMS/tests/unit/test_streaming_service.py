"""
WMS Panamá — Tests Unitarios: Order Streaming / Waveless (FR-055)
=================================================================
Tests PUROS sin BD. Cubren el control de WIP y la selección de la siguiente
tarea (prioridad → proximidad → antigüedad).

Ejecutar:  pytest tests/unit/test_streaming_service.py --noconftest
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.streaming_service import StreamingService


def _dt(m=0):
    return datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=m)


class _Task:
    def __init__(self, id, priority=5, pick_sequence=None, created_offset=0):
        self.id = id
        self.priority = priority
        self.pick_sequence = pick_sequence
        self.created_at = _dt(created_offset)


# ── Control de WIP ─────────────────────────────────────────────────────────────
class TestShouldRelease:
    def test_releases_when_below_max(self):
        assert StreamingService.should_release(0, 1) is True

    def test_blocks_when_at_max(self):
        assert StreamingService.should_release(1, 1) is False

    def test_allows_multiple_wip(self):
        assert StreamingService.should_release(2, 3) is True


# ── Selección de la siguiente tarea ────────────────────────────────────────────
class TestSelectNextPick:
    def test_empty_returns_none(self):
        assert StreamingService.select_next_pick([]) is None

    def test_priority_wins(self):
        low = _Task("low", priority=8, pick_sequence=1)
        high = _Task("high", priority=1, pick_sequence=900)
        assert StreamingService.select_next_pick([low, high]).id == "high"

    def test_proximity_breaks_priority_ties(self):
        near = _Task("near", priority=5, pick_sequence=12)
        far = _Task("far", priority=5, pick_sequence=800)
        # operario en secuencia 10 → 'near' (|12-10|=2) gana a 'far'
        assert StreamingService.select_next_pick([far, near], current_pick_sequence=10).id == "near"

    def test_without_current_seq_prefers_low_sequence(self):
        a = _Task("a", priority=5, pick_sequence=500)
        b = _Task("b", priority=5, pick_sequence=20)
        assert StreamingService.select_next_pick([a, b]).id == "b"

    def test_age_breaks_remaining_ties(self):
        older = _Task("older", priority=5, pick_sequence=10, created_offset=0)
        newer = _Task("newer", priority=5, pick_sequence=10, created_offset=30)
        assert StreamingService.select_next_pick([newer, older], current_pick_sequence=10).id == "older"
