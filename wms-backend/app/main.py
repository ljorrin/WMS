"""
WMS Panama — FastAPI Application Entry Point
=============================================
Configuración principal de la aplicación:
- Lifespan (startup / shutdown)
- Middleware (CORS, logging, rate limiting, request ID)
- Router principal /api/v1
- Manejo global de errores
- OpenAPI customizado

Ejecutar en desarrollo:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.redis import close_redis_pool
from app.db.session import dispose_engine

logger = get_logger(__name__)


# ── Lifespan (Startup / Shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manejo del ciclo de vida de la aplicación.
    startup: inicializar conexiones, logs, Sentry, Meilisearch.
    shutdown: cerrar pools, flush de buffers.
    """
    # ── STARTUP ──
    setup_logging(
        log_level=settings.LOG_LEVEL,
        json_logs=settings.is_production,
    )

    logger.info(
        "WMS Panama starting up",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
    )

    # Sentry (solo producción/staging)
    if settings.SENTRY_DSN and not settings.is_development:
        import sentry_sdk
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            environment=settings.ENVIRONMENT,
            release=f"{settings.APP_NAME}@{settings.APP_VERSION}",
        )
        logger.info("Sentry initialized")

    # Verificar BD en startup
    from app.db.session import check_db_connection
    db_ok = await check_db_connection()
    if not db_ok:
        logger.error("Database connection FAILED on startup — check DATABASE_URL")
    else:
        logger.info("Database connection OK")

    # Verificar Redis
    from app.db.redis import check_redis_connection
    redis_ok = await check_redis_connection()
    if not redis_ok:
        logger.warning("Redis connection FAILED — cache and rate limiting will be degraded")
    else:
        logger.info("Redis connection OK")

    logger.info("WMS Panama is READY", port=settings.PORT)

    yield  # ← La aplicación corre aquí

    # ── SHUTDOWN ──
    logger.info("WMS Panama shutting down...")
    await dispose_engine()
    await close_redis_pool()
    logger.info("WMS Panama shutdown complete")


# ── FastAPI App ────────────────────────────────────────────────────────────────

def create_application() -> FastAPI:
    """Factory de la aplicación FastAPI."""

    app = FastAPI(
        title=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        lifespan=lifespan,
        # Tags para organizar la documentación
        openapi_tags=[
            {"name": "⚡ Health",      "description": "Health checks y probes"},
            {"name": "🔐 Auth",        "description": "Autenticación y sesiones"},
            {"name": "🏢 Tenants",     "description": "Gestión de tenants (empresas)"},
            {"name": "👤 Users",       "description": "Gestión de usuarios"},
            {"name": "🏭 Warehouses",  "description": "Gestión de bodegas"},
            {"name": "📦 Inventory",   "description": "Inventario en tiempo real"},
            {"name": "📥 Inbound",     "description": "Recepción de mercancía"},
            {"name": "📤 Outbound",    "description": "Despacho de órdenes"},
            {"name": "🤖 AI",          "description": "Módulo de Inteligencia Artificial"},
        ],
    )

    # ── Middleware ─────────────────────────────────────────────────────────────

    # 1. CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # 2. Request ID + Logging de requests
    app.add_middleware(RequestLoggingMiddleware)

    # ── Routers ────────────────────────────────────────────────────────────────
    app.include_router(api_router)

    # ── Root ──────────────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/api/docs" if not settings.is_production else "Disabled in production",
            "health": "/api/v1/health",
        }

    @app.get("/health", include_in_schema=False)
    async def root_health() -> dict:
        """Alias /health para load balancers que no leen el prefijo."""
        return {"status": "ok"}

    # ── Exception Handlers ─────────────────────────────────────────────────────
    _register_exception_handlers(app)

    return app


# ── Middleware de Logging de Requests ─────────────────────────────────────────

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware que:
    - Asigna un ID único a cada request (X-Request-ID)
    - Loggea método, path, status code y tiempo de respuesta
    - Agrega el request_id al contexto de structlog
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start_time = time.monotonic()

        # Contexto de logging para toda la request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else "unknown",
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error("Unhandled exception in request", exc_info=exc)
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Error interno del servidor."},
            )

        duration_ms = round((time.monotonic() - start_time) * 1000, 2)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        # No loggear health checks (demasiado ruido)
        if "/health" not in request.url.path:
            log_fn = logger.warning if response.status_code >= 400 else logger.info
            log_fn(
                "HTTP request",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

        structlog.contextvars.clear_contextvars()
        return response


# ── Exception Handlers ─────────────────────────────────────────────────────────

def _register_exception_handlers(app: FastAPI) -> None:
    """Registra handlers globales de excepciones."""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """Formatea errores de validación Pydantic de forma legible."""
        errors = []
        for error in exc.errors():
            field = " → ".join(str(loc) for loc in error["loc"])
            errors.append({"field": field, "message": error["msg"], "type": error["type"]})

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Error de validación en los datos enviados.",
                "errors": errors,
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Captura cualquier excepción no manejada."""
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            exc_info=exc,
        )

        # En desarrollo mostramos el detalle, en producción no
        detail = str(exc) if settings.is_development else "Error interno del servidor."

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": detail},
        )


# ── Instancia de la app ────────────────────────────────────────────────────────
app = create_application()
