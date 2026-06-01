"""
WMS Panama — Configuración Central
====================================
Settings via Pydantic v2 BaseSettings.
Todas las variables se leen de .env o variables de entorno.
Nunca hardcodear secrets aquí — siempre desde .env.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional, List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuración central del WMS.
    Variables con defaults seguros para desarrollo.
    En producción TODAS las que no tienen default deben venir de .env
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Identificación ───────────────────────────────────────────────────────
    APP_NAME: str = "WMS Panama"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "Warehouse Management System — Panamá"
    ENVIRONMENT: str = "development"  # development | staging | production
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Servidor ─────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1
    RELOAD: bool = False

    # ── Seguridad / JWT ───────────────────────────────────────────────────────
    SECRET_KEY: str  # OBLIGATORIO — sin default
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60        # 1 hora
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7           # 7 días
    RESET_PASSWORD_TOKEN_EXPIRE_HOURS: int = 24

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10         # Más estricto en auth

    # ── Base de Datos ─────────────────────────────────────────────────────────
    DATABASE_URL: str         # postgresql+asyncpg://user:pass@host:5432/db
    DATABASE_SYNC_URL: str    # postgresql+psycopg2://... (para Alembic)
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600
    DB_ECHO: bool = False     # True solo en debug extremo

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str            # redis://:password@host:6379/0
    REDIS_CACHE_DB: int = 1   # DB separada para cache
    REDIS_SESSION_DB: int = 2 # DB separada para sesiones
    REDIS_MAX_CONNECTIONS: int = 50

    # ── Meilisearch ───────────────────────────────────────────────────────────
    MEILI_URL: str = "http://localhost:7700"
    MEILI_MASTER_KEY: str = ""
    MEILI_SEARCH_KEY: str = ""

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = ""  # Si vacío, usa REDIS_URL
    CELERY_RESULT_BACKEND: str = ""

    # ── Email (SMTP) ──────────────────────────────────────────────────────────
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = False
    SMTP_SSL: bool = False
    EMAIL_FROM: str = "noreply@wmspanama.com"
    EMAIL_FROM_NAME: str = "WMS Panama"

    # ── Keycloak / SSO (opcional) ─────────────────────────────────────────────
    KEYCLOAK_ENABLED: bool = False
    KEYCLOAK_SERVER_URL: str = ""
    KEYCLOAK_REALM: str = ""
    KEYCLOAK_CLIENT_ID: str = ""
    KEYCLOAK_CLIENT_SECRET: str = ""

    # ── AI / ML ───────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    AI_ENABLED: bool = False

    # ── Storage (S3 / MinIO) ──────────────────────────────────────────────────
    S3_ENDPOINT_URL: str = ""       # Vacío = AWS S3, URL = MinIO
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET_NAME: str = "wms-files"
    S3_REGION: str = "us-east-1"

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # ── Paginación ────────────────────────────────────────────────────────────
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 500

    # ── Sentry (Observabilidad) ───────────────────────────────────────────────
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # ── Propiedades derivadas ─────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def celery_broker(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def celery_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    # ── Validadores ───────────────────────────────────────────────────────────

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY debe tener al menos 32 caracteres.")
        return v

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT debe ser uno de: {allowed}")
        return v

    @model_validator(mode="after")
    def set_debug_from_environment(self) -> "Settings":
        if self.ENVIRONMENT == "development" and not self.DEBUG:
            object.__setattr__(self, "DEBUG", True)
        if self.ENVIRONMENT == "production":
            object.__setattr__(self, "DEBUG", False)
            object.__setattr__(self, "DB_ECHO", False)
        return self


@lru_cache()
def get_settings() -> Settings:
    """
    Singleton de configuración — cacheado por lru_cache.
    En tests, usar: app.dependency_overrides[get_settings] = lambda: Settings(...)
    """
    return Settings()


# Instancia global para importar directamente
settings: Settings = get_settings()
