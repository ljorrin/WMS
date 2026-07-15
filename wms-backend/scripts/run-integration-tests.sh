#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# WMS Panamá — Ejecutar la suite de integración con PostgreSQL real
# ─────────────────────────────────────────────────────────────────────────────
# Crea (si hace falta) una base de pruebas "wms_test" en el MISMO servidor
# PostgreSQL al que ya apunta el contenedor `api` (su DATABASE_URL — sea el
# contenedor `postgres` del compose o un PostgreSQL real del host vía
# host.docker.internal) y ejecuta `pytest tests/integration_db` contra ella.
# No toca la base de la aplicación.
#
# Uso:
#   ./scripts/run-integration-tests.sh
#   WMS_TEST_DB=otro_nombre ./scripts/run-integration-tests.sh
#
# Requisitos: docker compose con el servicio `api` de este repo arriba.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

TESTDB="${WMS_TEST_DB:-wms_test}"

# docker compose v2 ("docker compose") o v1 ("docker-compose")
if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi

echo "▶ Asegurando servicio api..."
$DC up -d api

echo "▶ Resolviendo/creando la base de pruebas '$TESTDB' en el servidor de DATABASE_URL del contenedor..."
TEST_URL="$($DC exec -T -e WMS_TEST_DB="$TESTDB" api python -c '
import asyncio, os, re
import asyncpg

base_url = os.environ["DATABASE_URL"]
m = re.match(r"postgresql\+asyncpg://([^:]+):([^@]+)@([^:/]+):(\d+)/(.+)", base_url)
user, pwd, host, port, _dbname = m.groups()
testdb = os.environ["WMS_TEST_DB"]

async def main():
    conn = await asyncpg.connect(user=user, password=pwd, host=host, port=int(port), database="postgres")
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", testdb)
        if not exists:
            await conn.execute(f"CREATE DATABASE \"{testdb}\"")
    finally:
        await conn.close()
    print(f"postgresql+asyncpg://{user}:{pwd}@{host}:{port}/{testdb}")

asyncio.run(main())
' 2>/tmp/wms_test_db_setup.log)"

if [ -z "$TEST_URL" ]; then
  echo "✖ No se pudo resolver/crear la base de pruebas. Log:"
  cat /tmp/wms_test_db_setup.log
  exit 1
fi
echo "  Base de pruebas lista."

echo "▶ Ejecutando tests de integración (tests/integration_db)..."
$DC exec -T -e WMS_TEST_DATABASE_URL="$TEST_URL" api pytest tests/integration_db -v

echo "✓ Suite de integración finalizada."
