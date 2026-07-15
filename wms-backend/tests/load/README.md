# Pruebas de carga — Locust (Fase 0.5 del plan de implementación)

`locustfile.py` simula 3 perfiles de usuario concurrentes (operador general,
operador de bodega, supervisor/analista) contra la API real, para detectar
cuellos de botella y errores bajo concurrencia antes de producción.

## Cómo ejecutarlas

Requiere el stack levantado (`docker compose up -d`, con datos sembrados vía
`make seed` + `python -m seeds.demo_data`) y `locust` instalado (ya está
pinneado en `requirements.txt`; si el contenedor no lo tiene instalado porque
la imagen no se reconstruyó desde que se agregó el pin, instalar con
`docker compose exec api pip install locust==2.45.0`).

```bash
docker compose exec api locust -f tests/load/locustfile.py \
  --host=http://localhost:8000 --users=15 --spawn-rate=5 --run-time=45s \
  --headless --only-summary

# o con UI web (http://localhost:8089):
docker compose exec api locust -f tests/load/locustfile.py --host=http://localhost:8000
```

SLA objetivo (ver el hook `on_quitting` en `locustfile.py`): P95 < 500ms y tasa
de error < 1% por endpoint.

## Ejecución real y bugs encontrados (2026-07-15)

Primera corrida real (15 usuarios concurrentes, 45s) contra el stack apuntando
a PostgreSQL 16 real, con credenciales desactualizadas en el propio
`locustfile.py` y con endpoints reales — encontró y corrigió:

1. **Credenciales de prueba obsoletas**: `DEMO_CREDENTIALS` apuntaba a
   `admin@wms-demo.pa` / `Admin1234!`, que no existen; el superadmin real
   sembrado por `seeds/run_all.py` es `admin@wmspanama.com` / `Admin123!`.
   Corregido en `locustfile.py`.

2. **`GET /inventory/batches/near-expiry` → 422 (100% de error)**: el
   endpoint exige `warehouse_id` (obligatorio) y `days_ahead` (no `days`); el
   locustfile no los enviaba. Corregido: `on_start` ahora resuelve
   `self.warehouse_id` desde `GET /warehouses` una vez por usuario virtual, y
   la tarea usa el nombre de parámetro correcto.

3. **Login síncrono bloqueaba el event loop completo** (bug real de
   rendimiento, no del script de prueba): `verify_password` (bcrypt, ~200-300ms
   de CPU) se llamaba de forma síncrona dentro de `async def login(...)` en
   `app/api/v1/endpoints/auth.py`. Bajo concurrencia, esto no solo hacía lento
   el login — **bloqueaba el único hilo del event loop de uvicorn**,
   serializando TODAS las requests del proceso (P95 de endpoints de solo
   lectura como `[Dashboard] Outbound KPIs` llegaba a 3400ms con apenas 15
   usuarios). Corregido: `verify_password` ahora corre en threadpool
   (`starlette.concurrency.run_in_threadpool`) en `/auth/login` y
   `/auth/password/change`. Tras el fix, con la misma carga: 0% de errores,
   login P95 bajó de 5100ms a 2800ms, y el resto de endpoints mejoró
   notablemente (ver comparación de corridas más abajo). El costo bcrypt en sí
   (12 rondas) no se tocó — es una decisión de seguridad, no un bug.

### Comparación antes/después del fix de login

| Métrica (15 usuarios, 45s) | Antes | Después |
|---|---|---|
| Tasa de error | 0.79% (near-expiry 422) | 0% |
| Login P95 / Max | 5100ms / 5140ms | 2800ms / 2756ms |
| `[Dashboard] Outbound KPIs` P95 | 3400ms | 1300ms |
| `[Putaway] Pending tasks` P95 | 1500ms | 480ms |

El login sigue por encima del SLA de 500ms (es inherente al costo de bcrypt de
12 rondas bajo concurrencia en un solo worker de desarrollo con `--reload`); no
es un objetivo realista para ese endpoint específico bajo este perfil de
pruebas, pero ya no arrastra al resto de la API con él.
