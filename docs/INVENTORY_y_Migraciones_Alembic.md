# Inventory (ajustes) + Migración inicial Alembic — basado en evidencia

**Proyecto:** WMS Panamá · **Rama:** `feature/inbound-module` · **Fecha:** 2026-06-02

## 1. Inventory — flujo de ajustes (cabecera vs líneas) reconciliado

El ajuste es **cabecera + líneas** (`InventoryAdjustment` + `AdjustmentLine`), pero el modelo y el código estaban desalineados, con varios `TypeError`/`NOT NULL` en runtime:

- **Repo `AdjustmentRepository.create`** pasaba `reason_code=` (no era columna → `TypeError`) y `status="draft"` (no estaba en el enum).
- **Servicio `create_adjustment`** llamaba al repo con `created_by_id=` pero el parámetro es `created_by` (→ `TypeError`), y asignaba estados como strings `"pending_approval"` inexistentes en el enum.
- La cabecera exigía `product_id`/`location_id`/`quantity_before/after/delta`/`requested_by` como `NOT NULL`, pese a que el detalle vive en las líneas.
- Faltaban columnas que el código/respuesta usan: `notes`, `reference_number`, `applied_by`.
- `InventoryAdjustmentResponse` exponía `created_by` (el modelo tiene `created_by_id`) y campos calculados `total_lines`/`total_variance_value` sin fuente.

**Correcciones:**
- Enum `AdjustmentStatus` = `draft, pending_approval, approved, rejected, applied` (antes `pending/approved/rejected/applied`).
- `InventoryAdjustment`: columnas de un solo SKU (`product_id`, `location_id`, `quantity_before/after/delta`) y `requested_by` ahora **nullable**; **+** `reason_code`, `reference_number`, `notes`, `applied_by`; propiedades `total_lines` y `total_variance_value`.
- Repo `create`: usa `AdjustmentStatus.DRAFT`, fija `requested_by`/`created_by_id`, acepta `reference_number`; `list()` ahora hace `selectinload(lines)`.
- Servicio: `created_by=` correcto, reenvía `reference_number`, asigna **miembros de enum** (no strings) en create/approve/apply; en rechazo fija `rejected_by`.
- Schema response: `created_by`→`created_by_id`, **+** `updated_at`, defaults seguros en `total_lines`/`total_variance_value`.

**Verificación (en vivo):** `create_adjustment` (repo real + líneas) → OK; `approve` → `approved`; `apply` → `applied` con `movements.create` invocado; serialización `InventoryAdjustmentResponse` con `total_lines`/`total_variance_value`. 51 tablas, router 115 rutas, **202 passed / 1 preexistente**, `tsc --noEmit` exit 0.

## 2. Migración inicial Alembic

- `alembic/env.py`: ahora importa **todos** los modelos (faltaban `outbound` y `ai`).
- Generada `alembic/versions/bcf617d7ac65_initial_schema.py` (autogenerate contra una BD SQLite vacía como fuente de reflexión; los tipos se renderizan para Postgres).
- **Saneos aplicados al script** (defectos reales del autogenerate, detectados al renderizar SQL):
  1. `Text` no estaba importado (`postgresql.JSONB(astext_type=Text())`) → añadido `from sqlalchemy import Text`.
  2. Tipos ENUM compartidos por varias tablas (p. ej. `receivingmode`, `shippingcarriertype`, `industrytype`) provocaban `CREATE TYPE` duplicado → se crean **una sola vez** al inicio de `upgrade()` (`postgresql.ENUM(...).create(bind, checkfirst=True)`) y las columnas usan `postgresql.ENUM(..., create_type=False)`; `downgrade()` hace `DROP TYPE IF EXISTS`.
  3. `gen_random_uuid()` (server_default de los PK): `upgrade()` ahora ejecuta `CREATE EXTENSION IF NOT EXISTS pgcrypto` al inicio (idempotente; en PG16 ya es core, pero hace la migración autosuficiente en cualquier entorno).
- **Validación offline contra el dialecto Postgres** (`alembic upgrade head --sql`): exit 0, `CREATE EXTENSION pgcrypto` + **44 CREATE TYPE (0 duplicados)** + **52 CREATE TABLE** (incl. `alembic_version`), cierra en `COMMIT`. `downgrade ... --sql`: 52 DROP TABLE + 44 DROP TYPE.

### Aplicación automática en arranque (docker compose)
El servicio `api` ahora ejecuta las migraciones antes de servir, tanto en
desarrollo (`wms-backend/docker-compose.yml`) como en producción
(`docker-compose.prod.yml`):

```yaml
command: sh -c "alembic upgrade head && uvicorn app.main:app ..."
```

El `api` ya espera a `postgres` (`depends_on: condition: service_healthy`) y
`scripts/postgres/init.sql` crea las extensiones (`pgcrypto`, etc.). Por lo
tanto, un `docker compose up` sobre una BD limpia aplica el esquema solo.

### Aplicación manual

```bash
# Dentro del contenedor api (objetivo del Makefile)
make db-upgrade            # docker compose exec api alembic upgrade head
make db-downgrade          # baja una revisión
make db-history            # historial
make db-current            # revisión actual

# O directamente contra una BD Postgres
cd wms-backend
export DATABASE_SYNC_URL="postgresql+psycopg2://<user>:<pwd>@<host>:5432/<db>"
alembic upgrade head            # aplica el esquema
alembic upgrade head --sql      # solo generar SQL para revisión
```

> Si una BD ya tenía el esquema (creado fuera de Alembic), marca el baseline
> sin re-crear nada: `alembic stamp head`.
>
> Nota: la validación en este repo se hizo en modo **offline** (render de SQL)
> porque el entorno de desarrollo no disponía de PostgreSQL. Ejecuta
> `alembic upgrade head` contra una BD limpia para la validación en vivo
> (y, opcionalmente, `pytest tests/integration_db` apuntando a esa BD).
