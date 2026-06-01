"""
WMS Panama — Alembic Environment
===================================
Soporta migraciones síncronas (default de Alembic) y async
usando el driver psycopg2 para la URL sincrónica.

Comandos útiles:
    alembic revision --autogenerate -m "descripcion del cambio"
    alembic upgrade head
    alembic downgrade -1
    alembic history
    alembic current
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Cargar settings del WMS ────────────────────────────────────────────────────
# Usamos dotenv directamente para no depender del ciclo de vida del app
from dotenv import load_dotenv
load_dotenv()

# ── Metadata de todos los modelos ─────────────────────────────────────────────
# IMPORTANTE: importar todos los modelos aquí para que Alembic los detecte
from app.models.base import WMSBase
import app.models.core          # noqa: F401
import app.models.master_data   # noqa: F401
import app.models.inventory     # noqa: F401
import app.models.inbound       # noqa: F401

target_metadata = WMSBase.metadata

# ── Configuración ─────────────────────────────────────────────────────────────

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# URL sincrónica para Alembic (psycopg2)
DATABASE_SYNC_URL = os.environ.get("DATABASE_SYNC_URL", "")
if not DATABASE_SYNC_URL:
    # Fallback: construir desde variables individuales
    user = os.environ.get("POSTGRES_USER", "wms_user")
    pwd  = os.environ.get("POSTGRES_PASSWORD", "wms_secret")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db   = os.environ.get("POSTGRES_DB", "wms_db")
    DATABASE_SYNC_URL = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"

config.set_main_option("sqlalchemy.url", DATABASE_SYNC_URL)


# ── Exclusiones de autogenerate ───────────────────────────────────────────────

def include_object(object, name, type_, reflected, compare_to):
    """Excluir objetos de herramientas externas (ej: tablas de extensiones PG)."""
    # Ignorar tablas de extensiones de PostgreSQL
    excluded_schemas = {"tiger", "topology"}
    if hasattr(object, "schema") and object.schema in excluded_schemas:
        return False
    return True


def run_migrations_offline() -> None:
    """
    Modo offline: genera SQL sin conectarse a la BD.
    Útil para revisar las migraciones antes de ejecutarlas.
    alembic upgrade head --sql > migration.sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Modo online: conecta a la BD y aplica migraciones directamente.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            compare_server_default=True,
            # Esquema por defecto
            version_table="alembic_version",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
