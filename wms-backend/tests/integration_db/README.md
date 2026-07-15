# Tests de integración con PostgreSQL real

Estos tests son la **red de seguridad** que faltaba: ejercen `repo + service + modelo`
contra una base de datos PostgreSQL real (sin mocks, sin SQLite), por lo que detectan
desalineaciones schema↔modelo, tipos ENUM, `NOT NULL` y claves foráneas que los tests
unitarios (con mocks) no pueden ver.

## Por qué PostgreSQL y no SQLite
Los modelos usan tipos nativos de PostgreSQL (`UUID`, `JSONB`) y `ENUM`. SQLite no puede
materializar ese esquema, así que estos tests **requieren** PostgreSQL.

## Cómo ejecutarlos

### Opción A — un solo comando (recomendado, con docker compose)
```bash
cd wms-backend
make test-integration-db
```
Esto levanta el servicio `postgres`, crea la BD de pruebas `wms_test` (sin tocar
`wms_db`) y ejecuta `pytest tests/integration_db` dentro del contenedor `api`.
Implementado en `scripts/run-integration-tests.sh` (variables overrideables:
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `WMS_TEST_DB`).

### Opción B — manual contra cualquier PostgreSQL
```bash
docker compose up -d postgres          # o usa tu propio PostgreSQL
createdb wms_test                      # si no existe
export WMS_TEST_DATABASE_URL="postgresql+asyncpg://wms_user:wms_secret@localhost:5432/wms_test"
cd wms-backend
pytest tests/integration_db -v
```

Si `WMS_TEST_DATABASE_URL` no está definida o la BD no es accesible, **todo el módulo
se salta automáticamente** (no rompe la suite). El esquema se crea con
`metadata.create_all` al inicio de cada test y se elimina al final; cada test corre en su
propia transacción que se revierte (aislamiento).

## Qué cubren

### `test_schema_and_flows.py`
1. **Esquema**: las ~51 tablas (Inbound + Outbound + Inventory + AI + core + master) se
   materializan en PostgreSQL.
2. **Inbound**: ciclo de Orden de Compra — crear (DRAFT) → confirmar (CONFIRMED) con
   historial de estados y `total_amount` calculado.
3. **Inventory**: ciclo de ajuste (cabecera + línea) — crear → aprobar → aplicar; verifica
   que el stock se descuenta y que se genera el movimiento. Este flujo era **no funcional**
   antes de la reconciliación de junio 2026.

### `test_e2e_flow.py` (Fase 0.3 del plan de implementación)
Un único test de punta a punta que recorre el flujo completo contra PostgreSQL real:

```
PO → ASN → GRN (ruptura de cadena de frío) → QC → Putaway (con override de ubicación)
  → SO-A → Wave → Pick → Pack (BoxType + SSCC) → Ship → Deliver
  → SO-B → Streaming (waveless, sin ola) → Pick
  → Labor: estándar + tarea (asignar → iniciar → completar) con performance_pct calculado
  → Slotting: política → análisis ABC → recomendación → aplicar
  → KPIs: dashboards de inbound / outbound / labor
  → Reconciliación: kardex (Σ RECEIPT − Σ PICK) == stock final (InventoryLevel)
```

Encontró y corrigió dos bugs reales al ejecutarse por primera vez contra PostgreSQL:
`performance_pct` desbordaba `NUMERIC(7,2)` en tareas completadas casi instantáneamente
(ahora acotado en `LaborService.compute_performance_pct`), y `_check_stock_alerts`
referenciaba `product.min_stock` (no existe; el campo real es `reorder_point`).

> Nota: los fixtures (`seed`/`inventory_level` en `conftest.py`, `flow_seed` en
> `test_e2e_flow.py`) construyen el grafo mínimo de datos maestros a partir de los
> campos obligatorios reales de los modelos — no de mocks.

### `test_concurrency.py` (Fase 0.5 del plan de implementación)

A diferencia de los demás tests (secuenciales), lanza **N operaciones REALMENTE
concurrentes** (cada una con su propia sesión/conexión, como N requests HTTP
simultáneas) contra el mismo producto/ubicación, para verificar que
`app.db.redis.distributed_lock` coordina correctamente el acceso concurrente a
`InventoryLevel` sin sobrevender stock ni perder actualizaciones.

Encontró un bug real la primera vez que se ejecutó: `distributed_lock` hacía un
único intento SETNX y se rendía de inmediato ante la primera colisión
(`acquired=False`), por lo que bajo concurrencia real la mayoría de las
operaciones fallaban con "no se pudo obtener el lock" — aun habiendo stock de
sobra para atenderlas en serie. Corregido en `app/db/redis.py`: ahora reintenta
(poll cada 100ms) hasta agotar `timeout`, coordinando las operaciones en vez de
rechazarlas.

También expuso, vía las nuevas aserciones de `test_e2e_flow.py` sobre slotting
(Fase 0.4 — mover stock físicamente), un segundo bug pre-existente más
profundo: `InventoryService.pick_stock` descontaba `quantity_available` al
completar un pick **sin liberar la reserva soft** creada antes en
`confirm_sales_order` (`create_reservation`), descontando el disponible DOS
veces (una al reservar, otra al pickear) mientras `quantity_on_hand` solo se
descontaba una vez — desalineando `available` de `on_hand` permanentemente en
cada venta confirmada y pickeada. Corregido en `pick_stock`: si el nivel tiene
`quantity_reserved > 0`, el pick consume esa reserva (`delta_reserved`) en vez
de volver a descontar `available`.
