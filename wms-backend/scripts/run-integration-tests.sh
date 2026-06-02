#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# WMS Panamá — Ejecutar la suite de integración con PostgreSQL real
# ─────────────────────────────────────────────────────────────────────────────
# Levanta (si hace falta) el servicio `postgres`, crea una BD de pruebas
# (wms_test) y ejecuta `pytest tests/integration_db` dentro del contenedor `api`
# apuntando a esa BD. No toca la BD de la aplicación (wms_db).
#
# Uso:
#   ./scripts/run-integration-tests.sh
#   POSTGRES_USER=otro POSTGRES_PASSWORD=otro ./scripts/run-integration-tests.sh
#
# Requisitos: docker compose con los servicios `postgres` y `api` (este repo).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PGUSER="${POSTGRES_USER:-wms_user}"
PGPASS="${POSTGRES_PASSWORD:-wms_secret}"
APPDB="${POSTGRES_DB:-wms_db}"
TESTDB="${WMS_TEST_DB:-wms_test}"

# docker compose v2 ("docker compose") o v1 ("docker-compose")
if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi

echo "▶ Asegurando servicios postgres y api..."
$DC up -d postgres api

echo "▶ Esperando a que PostgreSQL esté listo..."
for i in $(seq 1 30); do
  if $DC exec -T postgres pg_isready -U "$PGUSER" -d "$APPDB" >/dev/null 2>&1; then break; fi
  sleep 2
  [ "$i" = "30" ] && { echo "✖ PostgreSQL no respondió a tiempo"; exit 1; }
done

echo "▶ Creando la BD de pruebas '$TESTDB' (si no existe)..."
EXISTS="$($DC exec -T postgres psql -U "$PGUSER" -d "$APPDB" -tAc \
  "SELECT 1 FROM pg_database WHERE datname='$TESTDB'" 2>/dev/null || true)"
if [ "$EXISTS" != "1" ]; then
  $DC exec -T postgres createdb -U "$PGUSER" "$TESTDB"
  echo "  BD '$TESTDB' creada."
else
  echo "  BD '$TESTDB' ya existe."
fi

echo "▶ Ejecutando tests de integración (tests/integration_db)..."
$DC exec -T \
  -e WMS_TEST_DATABASE_URL="postgresql+asyncpg://${PGUSER}:${PGPASS}@postgres:5432/${TESTDB}" \
  api pytest tests/integration_db -v

echo "✓ Suite de integración finalizada."
