"""
WMS Panama — Database Session (Async SQLAlchemy)
==================================================
Motor asíncrono PostgreSQL con asyncpg.
Pool configurado para producción.
Manejo de transacciones con context managers.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _create_engine() -> AsyncEngine:
    """
    Crea el motor de base de datos con configuración apropiada
    según el entorno (test usa NullPool para evitar interferencias).
    """
    engine_kwargs: dict = {
        "echo": settings.DB_ECHO,
        "future": True,
    }

    if settings.ENVIRONMENT == "test":
        # Tests: sin pool para evitar conexiones colgadas entre tests
        engine_kwargs["poolclass"] = NullPool
    else:
        # Producción/Desarrollo: pool configurado
        engine_kwargs.update({
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_recycle": settings.DB_POOL_RECYCLE,
            "pool_pre_ping": True,  # Verifica conexiones antes de usar
        })

    return create_async_engine(settings.DATABASE_URL, **engine_kwargs)


# Motor singleton
engine: AsyncEngine = _create_engine()

# Factory de sesiones async
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # Importante: evita lazy loads post-commit
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency de FastAPI para inyectar sesión de BD.
    Maneja commit/rollback automáticamente.

    Uso en endpoint:
        async def my_endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager para uso fuera de FastAPI (workers Celery, scripts, etc).

    Uso:
        async with get_db_context() as db:
            result = await db.execute(...)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    """
    Verifica que la BD esté accesible.
    Usado en el health check del API.
    """
    from sqlalchemy import text
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("Database connection failed", error=str(e))
        return False


async def dispose_engine() -> None:
    """Cierra todas las conexiones del pool. Llamar al shutdown del app."""
    await engine.dispose()
    logger.info("Database engine disposed")
