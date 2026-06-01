"""
WMS Panama — Redis Client
===========================
Cliente Redis async con redis-py.
Múltiples DBs para separación de responsabilidades:
- DB 0: Default / Cache general
- DB 1: Cache de queries
- DB 2: Sesiones / Tokens revocados
- DB 3: Rate limiting

Funciones de utilidad: cache, bloqueo distribuido, pub/sub.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import timedelta
from functools import wraps
from typing import Any, Optional, AsyncGenerator

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Pool de conexiones global ─────────────────────────────────────────────────

_redis_pool: Optional[aioredis.ConnectionPool] = None


def _build_url(db: int) -> str:
    """Construye la URL de Redis con DB específica."""
    base = settings.REDIS_URL.rstrip("/")
    # Si la URL ya tiene DB (ej: .../0), reemplazamos
    if base.split("/")[-1].isdigit():
        base = "/".join(base.split("/")[:-1])
    return f"{base}/{db}"


async def get_redis(db: int = 0) -> Redis:
    """
    Obtiene un cliente Redis para la DB especificada.
    Usa un pool de conexiones compartido.
    """
    global _redis_pool

    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            _build_url(db),
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )

    return aioredis.Redis(connection_pool=_redis_pool)


async def get_cache_redis() -> Redis:
    """Redis para cache de queries (DB 1)."""
    return await get_redis(db=settings.REDIS_CACHE_DB)


async def get_session_redis() -> Redis:
    """Redis para tokens revocados y sesiones (DB 2)."""
    return await get_redis(db=settings.REDIS_SESSION_DB)


# ── FastAPI Dependency ─────────────────────────────────────────────────────────

async def get_redis_dependency() -> AsyncGenerator[Redis, None]:
    """
    Dependency de FastAPI para Redis.
    Uso: redis: Redis = Depends(get_redis_dependency)
    """
    client = await get_redis()
    try:
        yield client
    finally:
        pass  # El pool maneja el cierre de conexiones


# ── Cache Utilities ───────────────────────────────────────────────────────────

async def cache_set(
    key: str,
    value: Any,
    expire: int | timedelta = 300,
    redis: Optional[Redis] = None,
) -> bool:
    """
    Guarda un valor en cache Redis con TTL.
    El valor se serializa a JSON automáticamente.
    """
    client = redis or await get_cache_redis()
    ttl = int(expire.total_seconds()) if isinstance(expire, timedelta) else expire
    serialized = json.dumps(value, default=str)
    return await client.set(key, serialized, ex=ttl)


async def cache_get(
    key: str,
    redis: Optional[Redis] = None,
) -> Optional[Any]:
    """Obtiene un valor del cache Redis. Retorna None si no existe."""
    client = redis or await get_cache_redis()
    raw = await client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def cache_delete(key: str, redis: Optional[Redis] = None) -> int:
    """Elimina una o más claves del cache."""
    client = redis or await get_cache_redis()
    return await client.delete(key)


async def cache_invalidate_pattern(pattern: str, redis: Optional[Redis] = None) -> int:
    """
    Invalida todas las claves que coincidan con el patrón.
    ej: cache_invalidate_pattern("inventory:tenant_123:*")
    CUIDADO: scan no bloquea Redis, pero puede ser lento con muchas claves.
    """
    client = redis or await get_cache_redis()
    count = 0
    async for key in client.scan_iter(match=pattern, count=100):
        await client.delete(key)
        count += 1
    return count


# ── Distributed Lock ──────────────────────────────────────────────────────────

@asynccontextmanager
async def distributed_lock(
    lock_name: str,
    timeout: int = 30,
    redis: Optional[Redis] = None,
) -> AsyncGenerator[bool, None]:
    """
    Lock distribuido con Redis (patrón SETNX).
    Evita condiciones de carrera en operaciones críticas de inventario.

    Uso:
        async with distributed_lock("inventory:adjust:sku-123") as acquired:
            if acquired:
                # operación crítica
    """
    client = redis or await get_redis()
    lock_key = f"lock:{lock_name}"
    acquired = await client.set(lock_key, "1", ex=timeout, nx=True)

    try:
        yield bool(acquired)
    finally:
        if acquired:
            await client.delete(lock_key)


# ── Token Blacklist (Logout) ───────────────────────────────────────────────────

async def revoke_token(jti: str, ttl: int, redis: Optional[Redis] = None) -> None:
    """
    Agrega un JTI (JWT ID) a la lista negra.
    Se usa al hacer logout o al cambiar contraseña.
    TTL debe coincidir con el tiempo de expiración del token original.
    """
    client = redis or await get_session_redis()
    await client.set(f"revoked_token:{jti}", "1", ex=ttl)


async def is_token_revoked(jti: str, redis: Optional[Redis] = None) -> bool:
    """Verifica si un token ha sido revocado."""
    client = redis or await get_session_redis()
    return bool(await client.exists(f"revoked_token:{jti}"))


# ── Rate Limiting ─────────────────────────────────────────────────────────────

async def check_rate_limit(
    key: str,
    limit: int,
    window: int = 60,
    redis: Optional[Redis] = None,
) -> tuple[bool, int]:
    """
    Rate limiting con ventana deslizante usando Redis.
    Retorna (permitido: bool, requests_restantes: int).

    key: identificador único (ej: f"rate:auth:{ip_address}")
    limit: máximo de requests en la ventana
    window: tamaño de la ventana en segundos
    """
    client = redis or await get_redis()

    current = await client.incr(key)
    if current == 1:
        await client.expire(key, window)

    remaining = max(0, limit - current)
    allowed = current <= limit

    return allowed, remaining


# ── Health Check ──────────────────────────────────────────────────────────────

async def check_redis_connection() -> bool:
    """Verifica que Redis esté accesible."""
    try:
        client = await get_redis()
        return await client.ping()
    except Exception as e:
        logger.error("Redis connection failed", error=str(e))
        return False


# ── Cleanup ───────────────────────────────────────────────────────────────────

async def close_redis_pool() -> None:
    """Cierra el pool de conexiones Redis. Llamar al shutdown."""
    global _redis_pool
    if _redis_pool:
        await _redis_pool.disconnect()
        _redis_pool = None
        logger.info("Redis pool closed")
