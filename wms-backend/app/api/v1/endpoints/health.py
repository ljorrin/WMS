"""
WMS Panama — Health Check Endpoints
======================================
Endpoints de salud del sistema para:
- Load balancers (AWS ALB, Nginx)
- Kubernetes liveness/readiness probes
- Monitoring (Datadog, Prometheus)
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings
from app.db.session import check_db_connection
from app.db.redis import check_redis_connection

router = APIRouter()


class ServiceStatus(BaseModel):
    status: str        # "ok" | "degraded" | "down"
    latency_ms: float | None = None
    message: str | None = None


class HealthResponse(BaseModel):
    status: str        # "healthy" | "degraded" | "unhealthy"
    app: str
    version: str
    environment: str
    timestamp: datetime
    services: dict[str, ServiceStatus]


@router.get(
    "",
    response_model=HealthResponse,
    summary="Health check completo",
    description="Verifica el estado de todos los servicios del WMS.",
)
async def health_check() -> HealthResponse:
    """
    Health check completo — verifica BD, Redis y servicios críticos.
    Usado por: Kubernetes readiness probe, monitoring.
    """
    import time

    services: dict[str, ServiceStatus] = {}
    overall_status = "healthy"

    # ── PostgreSQL ──
    start = time.monotonic()
    db_ok = await check_db_connection()
    db_latency = (time.monotonic() - start) * 1000

    services["database"] = ServiceStatus(
        status="ok" if db_ok else "down",
        latency_ms=round(db_latency, 2),
        message=None if db_ok else "No se puede conectar a PostgreSQL",
    )
    if not db_ok:
        overall_status = "unhealthy"

    # ── Redis ──
    start = time.monotonic()
    redis_ok = await check_redis_connection()
    redis_latency = (time.monotonic() - start) * 1000

    services["redis"] = ServiceStatus(
        status="ok" if redis_ok else "degraded",
        latency_ms=round(redis_latency, 2),
        message=None if redis_ok else "Redis no responde — cache/rate limiting afectado",
    )
    if not redis_ok and overall_status == "healthy":
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(timezone.utc),
        services=services,
    )


@router.get(
    "/live",
    summary="Liveness probe",
    description="Verifica que el proceso API está corriendo. Sin chequeos de dependencias.",
    status_code=status.HTTP_200_OK,
)
async def liveness() -> dict:
    """
    Kubernetes liveness probe — solo verifica que el proceso vive.
    Si este endpoint no responde, k8s reinicia el pod.
    """
    return {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get(
    "/ready",
    summary="Readiness probe",
    description="Verifica que el servicio está listo para recibir tráfico.",
)
async def readiness() -> dict:
    """
    Kubernetes readiness probe — verifica BD disponible.
    Si falla, k8s saca el pod del balanceador sin reiniciarlo.
    """
    db_ok = await check_db_connection()
    if not db_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de datos no disponible.",
        )
    return {"status": "ready", "timestamp": datetime.now(timezone.utc).isoformat()}
