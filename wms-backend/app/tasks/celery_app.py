"""
WMS Panamá — Aplicación Celery
================================
Broker/Backend parametrizados por entorno (CELERY_BROKER_URL / REDIS_URL).
Define colas (default/high_priority/low_priority) y el calendario (beat) de las
tareas periódicas de integración. Sin credenciales externas, las tareas se
ejecutan igual (los adaptadores devuelven configured=False sin llamar afuera).
"""

from __future__ import annotations

from celery import Celery
from kombu import Queue

from app.core.config import settings

_broker = settings.CELERY_BROKER_URL or settings.REDIS_URL
_backend = settings.CELERY_RESULT_BACKEND or settings.REDIS_URL

celery_app = Celery("wms", broker=_broker, backend=_backend)

celery_app.conf.update(
    task_default_queue="default",
    task_queues=(
        Queue("default"),
        Queue("high_priority"),
        Queue("low_priority"),
    ),
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Panama",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "erp-pull-purchase-orders": {
            "task": "integrations.pull_erp_orders",
            "schedule": 900.0,  # cada 15 min
        },
        "ecommerce-sync-stock": {
            "task": "integrations.sync_ecommerce_stock",
            "schedule": 600.0,  # cada 10 min
            "options": {"queue": "low_priority"},
        },
    },
)

# Registrar las tareas
import app.tasks.integration_tasks  # noqa: E402,F401
