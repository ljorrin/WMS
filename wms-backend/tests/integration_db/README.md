# Tests de integración con PostgreSQL real

Estos tests son la **red de seguridad** que faltaba: ejercen `repo + service + modelo`
contra una base de datos PostgreSQL real (sin mocks, sin SQLite), por lo que detectan
desalineaciones schema↔modelo, tipos ENUM, `NOT NULL` y claves foráneas que los tests
unitarios (con mocks) no pueden ver.

## Por qué PostgreSQL y no SQLite
Los modelos usan tipos nativos de PostgreSQL (`UUID`, `JSONB`) y `ENUM`. SQLite no puede
materializar ese esquema, así que estos tests **requieren** PostgreSQL.

## Cómo ejecutarlos

```bash
# 1) Levantar una BD de pruebas (ej. con el docker-compose del repo)
docker compose up -d db
#    o crear una BD limpia: createdb wms_test

# 2) Apuntar los tests a esa BD (driver asyncpg)
export WMS_TEST_DATABASE_URL="postgresql+asyncpg://wms_user:wms_secret@localhost:5432/wms_test"

# 3) Ejecutar
cd wms-backend
pytest tests/integration_db -v
```

Si `WMS_TEST_DATABASE_URL` no está definida o la BD no es accesible, **todo el módulo
se salta automáticamente** (no rompe la suite). El esquema se crea con
`metadata.create_all` al inicio de cada test y se elimina al final; cada test corre en su
propia transacción que se revierte (aislamiento).

## Qué cubren (`test_schema_and_flows.py`)
1. **Esquema**: las ~51 tablas (Inbound + Outbound + Inventory + AI + core + master) se
   materializan en PostgreSQL.
2. **Inbound**: ciclo de Orden de Compra — crear (DRAFT) → confirmar (CONFIRMED) con
   historial de estados y `total_amount` calculado.
3. **Inventory**: ciclo de ajuste (cabecera + línea) — crear → aprobar → aplicar; verifica
   que el stock se descuenta y que se genera el movimiento. Este flujo era **no funcional**
   antes de la reconciliación de junio 2026.

> Nota: estos tests se escribieron y validaron a nivel de colección/skip en un entorno sin
> PostgreSQL. Ejecútalos contra tu PostgreSQL para validación completa. Para datos maestros
> los fixtures construyen el grafo mínimo (tenant, company, warehouse, product, supplier,
> location, inventory level) a partir de los campos obligatorios reales de los modelos.
