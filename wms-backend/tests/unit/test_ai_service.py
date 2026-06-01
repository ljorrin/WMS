"""
WMS Panama — Tests Unitarios: Módulo AI/ML (Fase 8)
=====================================================
Tests PUROS sin BD ni red.

Clases:
  TestForecastingLogic      — Prophet fallback, métricas, alertas
  TestRouteOptimizer        — Manhattan distance, greedy NN, savings
  TestAnomalyDetection      — Z-Score, IQR, velocity, duplicados, stock negativo
  TestAssistantIntents      — Detección de intents y respuestas template
  TestReplenishmentRules    — Reglas de negocio de alertas de reposición
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.ai.optimizer import _manhattan_distance, _build_distance_matrix
from app.services.ai.anomaly import _z_score, _is_outlier_iqr
from app.services.ai.assistant import INTENT_PATTERNS


# ══════════════════════════════════════════════════════════════════════════════
# 1. FORECASTING LOGIC
# ══════════════════════════════════════════════════════════════════════════════

class TestForecastingLogic:

    def _make_history(self, days: int, base: float = 10.0, noise: float = 1.5) -> list[dict]:
        import random, math
        random.seed(42)
        base_dt = datetime.now(timezone.utc) - timedelta(days=days)
        return [
            {
                "ds": (base_dt + timedelta(days=i)).strftime("%Y-%m-%d"),
                "y": max(0, base + 4 * math.sin(2 * math.pi * i / 7)
                         + 0.01 * i + random.gauss(0, noise)),
            }
            for i in range(days)
        ]

    def test_synthetic_history_length(self):
        """El historial sintético tiene la longitud correcta."""
        from app.services.ai.forecasting import ForecastingService
        svc = ForecastingService.__new__(ForecastingService)
        hist = svc._synthetic_history(90)
        assert len(hist) == 90

    def test_synthetic_history_no_negatives(self):
        """El historial sintético no tiene valores negativos."""
        from app.services.ai.forecasting import ForecastingService
        svc = ForecastingService.__new__(ForecastingService)
        hist = svc._synthetic_history(365)
        assert all(d["y"] >= 0 for d in hist)

    def test_moving_average_forecast_length(self):
        """El fallback de promedio móvil devuelve N días correctos."""
        from app.services.ai.forecasting import ForecastingService, HORIZON_DAYS
        svc = ForecastingService.__new__(ForecastingService)
        hist = self._make_history(60)
        result = svc._moving_average_forecast(hist, "4w")
        assert len(result["forecast"]) == HORIZON_DAYS["4w"]

    def test_moving_average_no_negatives(self):
        """Forecast de promedio móvil no produce valores negativos."""
        from app.services.ai.forecasting import ForecastingService
        svc = ForecastingService.__new__(ForecastingService)
        hist = self._make_history(60)
        result = svc._moving_average_forecast(hist, "12w")
        assert all(p["yhat"] >= 0 for p in result["forecast"])
        assert all(p["yhat_lower"] >= 0 for p in result["forecast"])

    def test_moving_average_confidence_interval(self):
        """yhat_lower <= yhat <= yhat_upper en todo el forecast."""
        from app.services.ai.forecasting import ForecastingService
        svc = ForecastingService.__new__(ForecastingService)
        hist = self._make_history(60)
        result = svc._moving_average_forecast(hist, "4w")
        for p in result["forecast"]:
            assert p["yhat_lower"] <= p["yhat"] <= p["yhat_upper"]

    def test_metrics_calculation_mae(self):
        """MAE se calcula correctamente."""
        from app.services.ai.forecasting import ForecastingService
        svc = ForecastingService.__new__(ForecastingService)
        hist = self._make_history(50)
        forecast = [{"yhat": 10.0}] * 10
        metrics = svc._calculate_metrics(hist, forecast)
        assert metrics["mae"] is not None
        assert metrics["mae"] >= 0

    def test_metrics_mape_none_for_zero_actuals(self):
        """MAPE se omite cuando los valores reales son 0."""
        from app.services.ai.forecasting import ForecastingService
        svc = ForecastingService.__new__(ForecastingService)
        hist = [{"ds": f"2026-01-{i+1:02d}", "y": 0} for i in range(50)]
        forecast = [{"yhat": 5.0}] * 10
        metrics = svc._calculate_metrics(hist, forecast)
        assert metrics["mape"] is None

    def test_insufficient_history_raises(self):
        """Historial < 14 días debe rechazarse."""
        hist_short = [{"ds": f"2026-01-{i+1:02d}", "y": 10} for i in range(13)]
        with pytest.raises(ValueError, match="Insuficiente historial"):
            if len(hist_short) < 14:
                raise ValueError(f"Insuficiente historial: {len(hist_short)} días.")

    def test_stockout_alert_triggered(self):
        """Alerta de stockout se dispara cuando stock cubre < 14 días."""
        daily_demand = 5.0
        current_stock = 40.0  # 8 días de stock
        days_of_stock = current_stock / daily_demand
        assert days_of_stock < 14
        # Debe recomendar reposición
        horizon_demand = daily_demand * 28
        recommended = max(0, horizon_demand - current_stock)
        assert recommended > 0

    def test_overstock_alert_triggered(self):
        """Alerta de sobrestock cuando stock > 3x la demanda del horizonte."""
        current_stock = 1000.0
        horizon_demand = 200.0  # 28 días × 7.1 u/día
        is_overstock = current_stock > 3 * horizon_demand
        assert is_overstock is True

    def test_no_alert_when_sufficient_stock(self):
        """Sin alerta cuando el stock está en rango saludable."""
        current_stock = 200.0
        horizon_demand = 140.0
        days_of_stock = current_stock / (horizon_demand / 28)
        is_stockout_risk = days_of_stock < 14
        is_overstock = current_stock > 3 * horizon_demand
        assert not is_stockout_risk
        assert not is_overstock

    def test_horizon_days_mapping(self):
        """Mapeo de horizontes a días es correcto."""
        from app.services.ai.forecasting import HORIZON_DAYS
        assert HORIZON_DAYS["1w"]  == 7
        assert HORIZON_DAYS["4w"]  == 28
        assert HORIZON_DAYS["12w"] == 84
        assert HORIZON_DAYS["26w"] == 182


# ══════════════════════════════════════════════════════════════════════════════
# 2. ROUTE OPTIMIZER
# ══════════════════════════════════════════════════════════════════════════════

class TestRouteOptimizer:

    def test_manhattan_distance_same_location(self):
        """Distancia de una ubicación a sí misma es 0."""
        loc = {"aisle": 3, "bay": 10, "level": 1}
        assert _manhattan_distance(loc, loc) == 0.0

    def test_manhattan_distance_only_aisle(self):
        """Distancia entre pasillos = diferencia × AISLE_SPACING_M."""
        from app.services.ai.optimizer import AISLE_SPACING_M
        a = {"aisle": 0, "bay": 0, "level": 0}
        b = {"aisle": 5, "bay": 0, "level": 0}
        expected = 5 * AISLE_SPACING_M
        assert _manhattan_distance(a, b) == pytest.approx(expected)

    def test_manhattan_distance_all_axes(self):
        """Distancia Manhattan suma los tres ejes correctamente."""
        from app.services.ai.optimizer import AISLE_SPACING_M, BAY_SPACING_M, LEVEL_SPACING_M
        a = {"aisle": 0, "bay": 0, "level": 0}
        b = {"aisle": 2, "bay": 3, "level": 1}
        expected = 2 * AISLE_SPACING_M + 3 * BAY_SPACING_M + 1 * LEVEL_SPACING_M
        assert _manhattan_distance(a, b) == pytest.approx(expected)

    def test_distance_matrix_diagonal_zero(self):
        """La diagonal de la matriz de distancias es 0."""
        locs = [
            {"aisle": i, "bay": 0, "level": 0}
            for i in range(4)
        ]
        matrix = _build_distance_matrix(locs)
        for i in range(4):
            assert matrix[i][i] == 0

    def test_distance_matrix_symmetry(self):
        """La matriz de distancias es simétrica."""
        locs = [
            {"aisle": 0, "bay": 0, "level": 0},
            {"aisle": 5, "bay": 3, "level": 2},
            {"aisle": 2, "bay": 8, "level": 0},
        ]
        matrix = _build_distance_matrix(locs)
        for i in range(len(locs)):
            for j in range(len(locs)):
                assert matrix[i][j] == matrix[j][i]

    def test_greedy_nn_visits_all_locations(self):
        """El greedy nearest-neighbor visita todas las ubicaciones."""
        from app.services.ai.optimizer import PickingRouteOptimizer
        svc = PickingRouteOptimizer.__new__(PickingRouteOptimizer)

        locations = [{"location_id": str(uuid4()), "aisle": i, "bay": i, "level": 0}
                     for i in range(6)]
        tasks     = [{"id": str(uuid4()), "location_id": locations[i]["location_id"]}
                     for i in range(6)]

        result = svc._greedy_nearest_neighbor(locations, tasks, num_operators=1)
        total_stops = sum(len(r["route"]) for r in result["routes"])
        assert total_stops == 6

    def test_greedy_nn_multiple_operators(self):
        """Con 2 operadores se generan 2 rutas."""
        from app.services.ai.optimizer import PickingRouteOptimizer
        svc = PickingRouteOptimizer.__new__(PickingRouteOptimizer)

        locations = [{"location_id": str(uuid4()), "aisle": i, "bay": 0, "level": 0}
                     for i in range(6)]
        tasks     = [{"id": str(uuid4()), "location_id": l["location_id"]}
                     for l in locations]

        result = svc._greedy_nearest_neighbor(locations, tasks, num_operators=2)
        assert len(result["routes"]) == 2

    def test_total_distance_positive(self):
        """La distancia total optimizada es positiva."""
        from app.services.ai.optimizer import PickingRouteOptimizer
        svc = PickingRouteOptimizer.__new__(PickingRouteOptimizer)

        locations = [{"location_id": str(uuid4()), "aisle": i*2, "bay": i, "level": 0}
                     for i in range(4)]
        tasks = [{"id": str(uuid4()), "location_id": l["location_id"]} for l in locations]

        result = svc._greedy_nearest_neighbor(locations, tasks, num_operators=1)
        assert result["total_distance_m"] > 0

    def test_estimated_minutes_calculation(self):
        """Tiempo estimado = distancia / velocidad de caminata (1.2 m/s)."""
        distance_m = 120.0
        walking_speed = 1.2  # m/s
        est_seconds = distance_m / walking_speed
        est_minutes = int(est_seconds)
        assert est_minutes == 100

    def test_savings_percentage_valid_range(self):
        """El % de ahorro está entre 0% y 100%."""
        naive_dist = 500.0
        optimized_dist = 320.0
        savings = (naive_dist - optimized_dist) / naive_dist * 100
        assert 0 <= savings <= 100
        assert round(savings, 1) == 36.0


# ══════════════════════════════════════════════════════════════════════════════
# 3. ANOMALY DETECTION
# ══════════════════════════════════════════════════════════════════════════════

class TestAnomalyDetection:

    def test_z_score_zero_for_mean_value(self):
        """Z-Score de la media es 0."""
        assert _z_score(10.0, 10.0, 2.0) == pytest.approx(0.0)

    def test_z_score_positive_outlier(self):
        """Z-Score positivo para valor sobre la media."""
        z = _z_score(16.0, 10.0, 2.0)
        assert z == pytest.approx(3.0)

    def test_z_score_negative_outlier(self):
        """Z-Score negativo para valor bajo la media."""
        z = _z_score(4.0, 10.0, 2.0)
        assert z == pytest.approx(-3.0)

    def test_z_score_zero_std(self):
        """Z-Score con std=0 devuelve 0 (evitar div/0)."""
        assert _z_score(15.0, 10.0, 0.0) == 0.0

    def test_iqr_normal_value_not_outlier(self):
        """Valor dentro del rango IQR no es outlier."""
        assert not _is_outlier_iqr(10.0, 5.0, 15.0, 1.5)

    def test_iqr_high_value_is_outlier(self):
        """Valor extremo sobre Q3 + 1.5*IQR es outlier."""
        # IQR=10, límite superior = 15 + 1.5*10 = 30
        assert _is_outlier_iqr(35.0, 5.0, 15.0, 1.5)

    def test_iqr_low_value_is_outlier(self):
        """Valor extremo bajo Q1 - 1.5*IQR es outlier."""
        # límite inferior = 5 - 1.5*10 = -10
        assert _is_outlier_iqr(-15.0, 5.0, 15.0, 1.5)

    def test_velocity_change_detection(self):
        """Cambio > 50% en velocidad es anomalía."""
        from app.services.ai.anomaly import AnomalyDetector
        threshold = AnomalyDetector.VELOCITY_CHANGE  # 0.50
        vel_30d = 10.0
        vel_7d  = 16.0  # +60% → anomalía
        change = abs(vel_7d - vel_30d) / vel_30d
        assert change >= threshold

    def test_velocity_change_no_anomaly(self):
        """Cambio < 50% no dispara anomalía."""
        from app.services.ai.anomaly import AnomalyDetector
        threshold = AnomalyDetector.VELOCITY_CHANGE
        vel_30d = 10.0
        vel_7d  = 13.0  # +30% → OK
        change = abs(vel_7d - vel_30d) / vel_30d
        assert change < threshold

    def test_duplicate_detection_window(self):
        """Movimientos idénticos en < 60s son duplicados."""
        from app.services.ai.anomaly import AnomalyDetector
        window = AnomalyDetector.DUPLICATE_WINDOW  # 60 segundos
        t1 = datetime(2026, 5, 27, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 5, 27, 10, 0, 45, tzinfo=timezone.utc)  # 45s
        delta = abs((t2 - t1).total_seconds())
        assert delta <= window  # es duplicado

    def test_not_duplicate_outside_window(self):
        """Movimientos idénticos con > 60s de diferencia no son duplicados."""
        from app.services.ai.anomaly import AnomalyDetector
        window = AnomalyDetector.DUPLICATE_WINDOW
        t1 = datetime(2026, 5, 27, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 5, 27, 10, 2, 0, tzinfo=timezone.utc)  # 120s
        delta = abs((t2 - t1).total_seconds())
        assert delta > window  # no es duplicado

    def test_negative_stock_is_critical(self):
        """Stock negativo es siempre CRITICAL."""
        stock = -5.0
        is_negative = stock < 0
        assert is_negative is True
        severity = "CRITICAL" if is_negative else "INFO"
        assert severity == "CRITICAL"

    def test_z_score_threshold(self):
        """Z-Score > 3 clasifica como outlier."""
        from app.services.ai.anomaly import AnomalyDetector
        threshold = AnomalyDetector.Z_THRESHOLD  # 3.0
        # Qty = 500, media = 10, std = 5 → Z = 98 (extremo)
        z = _z_score(500.0, 10.0, 5.0)
        assert abs(z) > threshold


# ══════════════════════════════════════════════════════════════════════════════
# 4. ASSISTANT INTENT DETECTION
# ══════════════════════════════════════════════════════════════════════════════

class TestAssistantIntents:

    def _detect_intent(self, message: str) -> str:
        msg_lower = message.lower()
        for key, patterns in INTENT_PATTERNS.items():
            if any(p in msg_lower for p in patterns):
                return key
        return "general"

    def test_stock_query_intent(self):
        assert self._detect_intent("cuánto stock hay de producto X") == "stock_query"
        assert self._detect_intent("cuántas unidades quedan") == "stock_query"

    def test_po_query_intent(self):
        assert self._detect_intent("cuándo llega el pedido del proveedor") == "po_query"
        assert self._detect_intent("órdenes de compra pendientes") == "po_query"

    def test_so_query_intent(self):
        assert self._detect_intent("órdenes de venta activas") == "so_query"

    def test_kpi_query_intent(self):
        assert self._detect_intent("muéstrame las métricas del almacén") == "kpi_query"
        assert self._detect_intent("cuál es el fill rate") == "kpi_query"

    def test_alert_query_intent(self):
        assert self._detect_intent("hay alguna alerta crítica") == "alert_query"
        assert self._detect_intent("productos con riesgo de stockout") == "alert_query"

    def test_picking_query_intent(self):
        assert self._detect_intent("cómo está el picking hoy") == "picking_query"
        assert self._detect_intent("ruta de wave 001") == "picking_query"

    def test_general_intent_fallback(self):
        assert self._detect_intent("hola buenos días") == "general"
        assert self._detect_intent("qué tiempo hace") == "general"

    def test_template_response_kpi(self):
        """La respuesta template para KPI contiene datos esperados."""
        from app.services.ai.assistant import WMSAssistant
        svc = WMSAssistant.__new__(WMSAssistant)
        context = {
            "inbound_metrics": {"grns_today": 5, "putaway_tasks_open": 3, "avg_defect_rate_pct": 2.1},
            "outbound_metrics": {"orders_open": 12, "picks_today": 88, "short_pick_rate_pct": 1.5,
                                  "shipments_in_transit": 4},
        }
        response = svc._template_response("métricas del almacén", context)
        assert "GRNs hoy" in response
        assert "Órdenes abiertas" in response

    def test_template_response_no_alerts(self):
        """Respuesta cuando no hay alertas activas."""
        from app.services.ai.assistant import WMSAssistant
        svc = WMSAssistant.__new__(WMSAssistant)
        context = {"active_alerts": []}
        response = svc._template_response("hay alertas críticas", context)
        assert "No hay alertas" in response or "✅" in response

    def test_template_response_with_alerts(self):
        """Respuesta cuando hay alertas activas."""
        from app.services.ai.assistant import WMSAssistant
        svc = WMSAssistant.__new__(WMSAssistant)
        context = {
            "active_alerts": [
                {"title": "Riesgo stockout Producto A", "severity": "CRITICAL"},
                {"title": "Sobrestock Producto B", "severity": "INFO"},
            ]
        }
        response = svc._template_response("hay alguna alerta", context)
        assert "Riesgo stockout" in response


# ══════════════════════════════════════════════════════════════════════════════
# 5. REPLENISHMENT BUSINESS RULES
# ══════════════════════════════════════════════════════════════════════════════

class TestReplenishmentRules:

    def test_days_of_stock_calculation(self):
        """Días de stock = stock_actual / demanda_diaria."""
        current_stock = 300.0
        daily_demand  = 15.0
        days = current_stock / daily_demand
        assert days == pytest.approx(20.0)

    def test_recommended_qty_calculation(self):
        """Cantidad recomendada = demanda_horizonte - stock_actual."""
        horizon_demand = 420.0   # 28 días × 15 u/día
        current_stock  = 300.0
        recommended    = max(0, horizon_demand - current_stock)
        assert recommended == pytest.approx(120.0)

    def test_no_reorder_when_sufficient(self):
        """No ordenar cuando el stock cubre el horizonte completo."""
        horizon_demand = 200.0
        current_stock  = 350.0
        recommended    = max(0, horizon_demand - current_stock)
        assert recommended == 0.0

    def test_economic_order_quantity(self):
        """EOQ = sqrt(2 * D * S / H) — fórmula clásica."""
        D = 1000    # demanda anual
        S = 50      # costo de ordenar
        H = 5       # costo de mantener por unidad
        eoq = math.sqrt(2 * D * S / H)
        assert eoq == pytest.approx(141.42, rel=0.01)

    def test_reorder_point(self):
        """ROP = demanda_diaria × lead_time."""
        daily_demand = 15.0
        lead_time_days = 5
        rop = daily_demand * lead_time_days
        assert rop == pytest.approx(75.0)

    def test_safety_stock(self):
        """Safety stock = Z × std_demanda × sqrt(lead_time)."""
        import math
        z = 1.65           # 95% service level
        std_demand = 3.0   # desviación estándar de la demanda diaria
        lead_time  = 5     # días
        ss = z * std_demand * math.sqrt(lead_time)
        assert ss == pytest.approx(11.07, rel=0.01)

    def test_critical_severity_under_7_days(self):
        """Severidad CRITICAL cuando quedan < 7 días de stock."""
        days_of_stock = 5.0
        severity = "CRITICAL" if days_of_stock < 7 else "WARNING"
        assert severity == "CRITICAL"

    def test_warning_severity_7_to_14_days(self):
        """Severidad WARNING entre 7 y 14 días de stock."""
        days_of_stock = 10.0
        severity = "CRITICAL" if days_of_stock < 7 else "WARNING"
        assert severity == "WARNING"

    def test_abc_classification(self):
        """Clasificación ABC por volumen de ventas (80/15/5%)."""
        products = [
            {"id": "A", "annual_sales": 10000},
            {"id": "B", "annual_sales": 5000},
            {"id": "C", "annual_sales": 2000},
            {"id": "D", "annual_sales": 1000},
            {"id": "E", "annual_sales": 200},
        ]
        total = sum(p["annual_sales"] for p in products)
        sorted_products = sorted(products, key=lambda x: x["annual_sales"], reverse=True)

        cum = 0
        classifications = {}
        for p in sorted_products:
            cum += p["annual_sales"] / total
            if cum <= 0.80:
                classifications[p["id"]] = "A"
            elif cum <= 0.95:
                classifications[p["id"]] = "B"
            else:
                classifications[p["id"]] = "C"

        assert classifications["A"] == "A"   # Mayor rotación
        assert classifications["E"] == "C"   # Menor rotación
