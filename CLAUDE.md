# CLAUDE.md

Guía para trabajar en este repositorio. **Idioma de trabajo: español** (respuestas, commits y documentación).

## Qué es

**WMS Panamá** — Warehouse Management System **multiempresa, multi-bodega y multi-país** para la República de Panamá. Cubre la cadena completa (fabricante → aduanas → transporte → centro de distribución → retail → eCommerce) con cumplimiento del marco regulatorio panameño (Ley 81/2019, ANA/SIGA, DGI) y estándares GS1.

El proyecto es una labor de **estabilización y reconciliación** de una base de código preexistente que nunca se había ejecutado. Historia y contexto completo en `TRASPASO_WMS_Panama.md` (fuente principal de este archivo).

- **Repo:** github.com/ljorrin/WMS · **Rama de trabajo:** `feature/inbound-module`
- **Fuente autoritativa del estado:** el `git log` y el código, **no** los `.docx` de la raíz (son fotos históricas, pueden estar desactualizadas).

## Stack

- **Backend** (`wms-backend/`): Python 3.12, FastAPI 0.115, SQLAlchemy 2.0 **async** (`Mapped`/`mapped_column`), PostgreSQL 16, Alembic, Redis, Celery, Meilisearch. IA/ML: Prophet, scikit-learn, LangChain, OR-Tools.
- **Frontend** (`wms-frontend/`): React 18, Vite, TypeScript, React Query, Zustand, Tailwind, react-hook-form + zod, Radix UI, Recharts.
- **Infra:** Docker Compose, Nginx, Prometheus, GitHub Actions CI.

## Arquitectura backend

Patrón de capas **estricto**: `Modelo → Repositorio → Servicio → Endpoint`.

- **Multi-tenant transversal:** `tenant_id` en casi todos los modelos vía `TenantMixin`. Auditoría (`created_by_id`/`updated_by_id`) y soft-delete (`deleted_at`/`deleted_by`) vía mixins en `WMSBase`.
- **Seguridad por permisos declarativos:** dependencia `require_permission("...")` en los endpoints. **Regla crítica:** todo permiso exigido por un endpoint debe estar sembrado en `seeds/run_all.py`, o el módulo devuelve 403 para roles no-superadmin.
- **Esquema BD vía Alembic** (no `create_all`). Mantener migraciones al día es requisito antes de producción.
- **Moneda funcional USD** (paridad Balboa/USD).

Rutas montadas bajo `/api/v1` (`app/api/v1/router.py`): `health, auth, tenants, users, warehouses, master, inventory, inbound, outbound, ai, realtime, integrations, sync, yms`.

## Estructura

```
wms-backend/app/
  api/v1/router.py, api/v1/endpoints/*.py   # capa HTTP por módulo
  models/*.py        # ORM: base (mixins), core, inbound, inventory, outbound, yms, master_data, ai
  repositories/*.py  # acceso a datos
  services/*.py, services/ai/*   # lógica de negocio + IA (anomaly, assistant, forecasting, optimizer)
  core/*.py          # config, dependencias, seguridad, GS1, logging, excepciones
  integrations/*     # erp, ecommerce, carrier, http_client + regulatory/ (ana_siga.py, dgi.py)
  tasks/*            # Celery (celery_app, integration_tasks)
  seeds/run_all.py   # siembra permisos/roles — MANTENER sincronizado con endpoints
  alembic/versions/* # migraciones (initial_schema, yms0001_yard_management)
  tests/{unit,integration,integration_db,load}/

wms-frontend/src/
  api/               # cliente y endpoints
  components/ui/, components/layout/, components/charts/
  pages/             # auth, dashboard, inbound, inventory, master, outbound, settings
  hooks/, store/, types/index.ts   # tipos deben coincidir con enums del backend
```

## Comandos (desde `wms-backend/`, vía Makefile)

```
make up                    # levanta servicios (API :8000, docs /api/docs, MailHog :8025, Meili :7700)
make down
make db-upgrade            # aplicar migraciones (upgrade head)
make db-migrate MSG="..."  # crear nueva migración
make seed                  # tenant demo, superadmin, permisos
make test                  # suite
make test-unit
make test-integration
make test-integration-db   # integración contra PostgreSQL real (crea wms_test)
make lint / format / typecheck   # Ruff + mypy
```

Frontend (`wms-frontend/`): `npm run dev`, `npm run build`, `npm run type-check` (`tsc --noEmit`).

## Estado de los módulos (verificar siempre contra el código)

| Módulo | Estado |
|---|---|
| Inbound (PO→ASN→GRN→QC→Putaway→RTV) | Reconciliado y verificado estáticamente |
| Inventory (ajustes cabecera+líneas, FEFO, kardex, locks Redis) | Reconciliado |
| Outbound (SO→Wave→Picking→Pack→Shipment→RMA) | Alineado |
| Maestros | CRUD + carga masiva |
| Seguridad | MFA TOTP + auditoría automática + `/metrics` |
| Regulatorio PA (ANA/SIGA DAM, DGI factura, Ley 81) | Presente — confirmar profundidad (productivo vs. stub) |
| Integraciones (ERP/eCommerce/carrier) | Scaffolding + wiring |
| YMS (patio/docks), Sync offline, Celery, IA/ML | Implementados — verificar profundidad |

**Riesgo principal / pendiente crítico:** nada se ha ejecutado **end-to-end contra PostgreSQL real** desde la API. Las reconciliaciones se verificaron construyendo ORM y serializando con sesión mockeada. Falta: validación en vivo end-to-end, consolidar migraciones Alembic, y confirmar la profundidad real de regulatorio/integraciones/IA.

## Convenciones

- **Commits en español:** `tipo(scope): descripción` referenciando IDs de requerimiento (`FR-xxx` funcional, `REG-xxx` regulatorio, `NFR`). Ej.: `feat(security): MFA TOTP + auditoría automática (FR-001/004 + NFR)`.
- **Metodología "nada asumido":** verificar cada afirmación técnica **ejecutando** (importar modelos, construir ORM, serializar `*Response`, correr la suite). Distinguir siempre lo verificado de lo pendiente.
- Reportes estructurados con tablas de estado por módulo/capa.

## Terminología del dominio

- **Inbound:** PO (orden de compra), ASN (aviso de despacho), GRN=`GoodsReceipt` (recepción), QC (control de calidad), Putaway (ubicación), RTV (devolución a proveedor).
- **Outbound:** SO (orden de venta), Wave (ola de picking), Picking, Pack, Shipment, RMA (devolución de cliente).
- **Inventory:** FEFO (primero en expirar, primero en salir), kardex, ajustes (cabecera+líneas), niveles por lote/ubicación.
- **Regulatorio PA:** ANA (aduanas), SIGA, DAM (declaración aduanera), DGI (impuestos / factura electrónica), ITBMS, MINSA, AUPSA/MIDA, ZLC (Zona Libre de Colón), VUPE, Ley 81/2019.
- **GS1:** GTIN-13/14, SSCC, GLN, GS1-128, DataMatrix.

## Documentación de referencia

- `TRASPASO_WMS_Panama.md` — traspaso completo (contexto, decisiones, estado, pendientes). **Leer primero.**
- `docs/*.md` — reportes de reconciliación basados en evidencia (INBOUND, INVENTORY, OUTBOUND).
- `.docx` raíz (SRS, Informe Técnico, Análisis y Plan, Herramientas) — contexto histórico; el SRS es el "contrato" funcional (53 RF/REG).
