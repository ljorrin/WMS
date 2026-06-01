"""
WMS Panama — Tests de Carga con Locust
=========================================
Simula usuarios concurrentes del WMS para detectar
cuellos de botella antes de producción.

Perfiles de carga:
  WMSUser         — Usuario típico (dashboard + lecturas)
  WarehouseOperator — Operador de almacén (picking intensivo)
  SupervisorUser  — Supervisor (reportes + aprobaciones)

Uso:
  locust -f tests/load/locustfile.py \
    --host=http://localhost:8000 \
    --users=50 --spawn-rate=5 --run-time=5m

  O con UI:
  locust -f tests/load/locustfile.py --host=http://localhost:8000
"""

import json
import random
from locust import HttpUser, task, between, events
from locust.exception import StopUser


# ── Credenciales de prueba ────────────────────────────────────────────────────

DEMO_CREDENTIALS = {
    "email": "admin@wms-demo.pa",
    "password": "Admin1234!",
}


class BaseWMSUser(HttpUser):
    """Base con autenticación y headers JWT."""
    abstract = True

    def on_start(self):
        """Login al inicio de cada usuario virtual."""
        resp = self.client.post(
            "/api/v1/auth/login",
            json=DEMO_CREDENTIALS,
            name="[Auth] Login",
        )
        if resp.status_code != 200:
            raise StopUser()
        token = resp.json().get("access_token", "")
        self.headers = {"Authorization": f"Bearer {token}"}

    def on_stop(self):
        """Logout al terminar."""
        self.client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": ""},
            headers=self.headers,
            name="[Auth] Logout",
        )


# ══════════════════════════════════════════════════════════════════════════════
# PERFIL 1: Usuario General (60% de los usuarios)
# ══════════════════════════════════════════════════════════════════════════════

class WMSUser(BaseWMSUser):
    """
    Usuario típico: navega el dashboard, consulta stock y órdenes.
    Peso 60% → la mayoría de usuarios.
    """
    wait_time = between(2, 5)
    weight = 60

    @task(5)
    def dashboard_inbound(self):
        """Dashboard inbound — consulta más frecuente."""
        self.client.get(
            "/api/v1/inbound/dashboard",
            headers=self.headers,
            name="[Dashboard] Inbound KPIs",
        )

    @task(5)
    def dashboard_outbound(self):
        self.client.get(
            "/api/v1/outbound/dashboard",
            headers=self.headers,
            name="[Dashboard] Outbound KPIs",
        )

    @task(4)
    def stock_query(self):
        """Consulta de stock — página 1."""
        self.client.get(
            "/api/v1/inventory/stock",
            params={"page": 1, "page_size": 20},
            headers=self.headers,
            name="[Inventory] Stock list",
        )

    @task(3)
    def movements_query(self):
        self.client.get(
            "/api/v1/inventory/movements",
            params={"page": 1, "page_size": 20},
            headers=self.headers,
            name="[Inventory] Movements",
        )

    @task(3)
    def po_list(self):
        self.client.get(
            "/api/v1/inbound/purchase-orders",
            params={"page": 1, "page_size": 20},
            headers=self.headers,
            name="[Inbound] PO list",
        )

    @task(3)
    def so_list(self):
        self.client.get(
            "/api/v1/outbound/orders",
            params={"page": 1, "page_size": 20},
            headers=self.headers,
            name="[Outbound] SO list",
        )

    @task(2)
    def grn_list(self):
        self.client.get(
            "/api/v1/inbound/grn",
            headers=self.headers,
            name="[Inbound] GRN list",
        )

    @task(2)
    def shipments_list(self):
        self.client.get(
            "/api/v1/outbound/shipments",
            headers=self.headers,
            name="[Outbound] Shipments",
        )

    @task(1)
    def health_check(self):
        self.client.get(
            "/api/v1/health/live",
            name="[Health] Liveness",
        )

    @task(1)
    def near_expiry_check(self):
        self.client.get(
            "/api/v1/inventory/batches/near-expiry",
            params={"days": 30},
            headers=self.headers,
            name="[Inventory] Near expiry",
        )


# ══════════════════════════════════════════════════════════════════════════════
# PERFIL 2: Operador de Almacén (30% de los usuarios)
# ══════════════════════════════════════════════════════════════════════════════

class WarehouseOperator(BaseWMSUser):
    """
    Operador RF: hace picking, putaway y consultas de ubicación.
    Peticiones más frecuentes y cortas.
    """
    wait_time = between(0.5, 2)
    weight = 30

    @task(6)
    def get_picking_tasks(self):
        """Operador consulta sus tareas de picking."""
        self.client.get(
            "/api/v1/outbound/picking",
            params={"status": "pending", "my_tasks": True, "page_size": 10},
            headers=self.headers,
            name="[Picking] My tasks",
        )

    @task(5)
    def get_putaway_tasks(self):
        """Operador consulta tareas de putaway pendientes."""
        self.client.get(
            "/api/v1/inbound/putaway",
            params={"status": "pending", "page_size": 10},
            headers=self.headers,
            name="[Putaway] Pending tasks",
        )

    @task(4)
    def stock_location_scan(self):
        """Escaneo de ubicación — consulta de stock específico."""
        self.client.get(
            "/api/v1/inventory/stock",
            params={"page_size": 5},
            headers=self.headers,
            name="[Inventory] Location scan",
        )

    @task(3)
    def pack_tasks_list(self):
        self.client.get(
            "/api/v1/outbound/packing",
            params={"status": "pending", "page_size": 10},
            headers=self.headers,
            name="[Packing] Pending tasks",
        )

    @task(2)
    def quality_inspections(self):
        self.client.get(
            "/api/v1/inbound/quality-inspections",
            headers=self.headers,
            name="[QC] Pending inspections",
        )

    @task(1)
    def rma_list(self):
        self.client.get(
            "/api/v1/outbound/returns",
            headers=self.headers,
            name="[RMA] Returns list",
        )


# ══════════════════════════════════════════════════════════════════════════════
# PERFIL 3: Supervisor / Analista (10% de los usuarios)
# ══════════════════════════════════════════════════════════════════════════════

class SupervisorUser(BaseWMSUser):
    """
    Supervisor: consulta reportes, aprueba ajustes, monitorea AI alerts.
    Peticiones menos frecuentes pero más pesadas.
    """
    wait_time = between(3, 8)
    weight = 10

    @task(4)
    def ai_alerts(self):
        """Consulta alertas de reposición generadas por AI."""
        self.client.get(
            "/api/v1/ai/alerts",
            params={"is_resolved": False},
            headers=self.headers,
            name="[AI] Replenishment alerts",
        )

    @task(3)
    def ai_anomalies(self):
        self.client.get(
            "/api/v1/ai/anomalies",
            params={"is_resolved": False},
            headers=self.headers,
            name="[AI] Anomaly events",
        )

    @task(3)
    def adjustments_pending(self):
        self.client.get(
            "/api/v1/inventory/adjustments",
            params={"status": "pending_approval"},
            headers=self.headers,
            name="[Inventory] Pending adjustments",
        )

    @task(3)
    def wave_management(self):
        self.client.get(
            "/api/v1/outbound/waves",
            params={"status": "open"},
            headers=self.headers,
            name="[Outbound] Open waves",
        )

    @task(2)
    def optimize_routes(self):
        """Consulta historial de optimizaciones."""
        self.client.get(
            "/api/v1/ai/optimize/routes",
            headers=self.headers,
            name="[AI] Route optimizations",
        )

    @task(2)
    def forecasts_list(self):
        self.client.get(
            "/api/v1/ai/forecast",
            headers=self.headers,
            name="[AI] Demand forecasts",
        )

    @task(1)
    def assistant_chat(self):
        """Consulta al asistente WMS."""
        self.client.post(
            "/api/v1/ai/assistant/chat",
            json={"message": "Muéstrame las métricas clave del almacén."},
            headers=self.headers,
            name="[AI] Assistant chat",
        )


# ══════════════════════════════════════════════════════════════════════════════
# EVENT HOOKS — Reportes personalizados
# ══════════════════════════════════════════════════════════════════════════════

@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """Al terminar la prueba, imprime un resumen de SLAs."""
    stats = environment.stats
    print("\n" + "="*60)
    print("WMS Panama — Load Test Summary")
    print("="*60)

    sla_failures = []
    for name, stat in stats.entries.items():
        p95 = stat.get_response_time_percentile(0.95)
        p99 = stat.get_response_time_percentile(0.99)
        fail_pct = stat.fail_ratio * 100

        # SLA: P95 < 500ms, error rate < 1%
        if p95 and p95 > 500:
            sla_failures.append(f"❌ P95 > 500ms: {name[1]} ({p95:.0f}ms)")
        if fail_pct > 1:
            sla_failures.append(f"❌ Error rate > 1%: {name[1]} ({fail_pct:.1f}%)")

    if sla_failures:
        print("\n⚠️  SLA Violations:")
        for f in sla_failures:
            print(f"  {f}")
    else:
        print("\n✅ All SLAs passed (P95 < 500ms, error rate < 1%)")
    print("="*60 + "\n")
