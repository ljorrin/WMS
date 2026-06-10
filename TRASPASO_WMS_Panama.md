# Documento de Traspaso — WMS Panamá

**Propósito:** trasladar este trabajo a un proyecto nuevo sin perder contexto.
**Fecha del traspaso:** 2026-06-07 · **Autor del proyecto:** Alejo (aguevarar@gmail.com)
**Repositorio:** https://github.com/ljorrin/WMS.git (cuenta `ljorrin`) · **Rama de trabajo:** `feature/inbound-module`
**Estado de referencia:** historial Git al commit `23af4a9` (2026-06-02).

> **Cómo leer este documento.** La sección de *Estado actual* toma el **historial Git como fuente autoritativa**. El informe ejecutivo en `WMS_Panama_Analisis_Estado_y_Plan.docx` es una **foto puntual anterior** a los últimos commits y, por tanto, subestima varios módulos (ver §6, "Divergencia documentación ↔ código").

---

## 1. Qué es el proyecto

WMS (Warehouse Management System) **multiempresa, multi-bodega y multi-país** para la República de Panamá. Cubre la cadena de valor completa (fabricante → aduanas → transporte → centro de distribución → retail → eCommerce) en múltiples industrias (consumo masivo, automotriz, farmacéutico, ferretería, electrónica, moda, agro-alimentario), con cumplimiento del marco regulatorio panameño y estándares GS1.

El proyecto **no es un desarrollo desde cero**: es una labor de **estabilización y reconciliación** de una base de código que existía pero **nunca se había ejecutado**. El hallazgo central, repetido y verificado en todos los reportes, es que el código se escribió contra una versión *imaginada* de los modelos: tenía defectos de integración (columnas con nombres reservados, imports a clases inexistentes, desalineación modelo↔schema↔repositorio, permisos sembrados incompletos) y los tests "verdes" eran lógica pura con mocks que nunca importaban modelos, schemas ni la API.

---

## 2. Decisiones clave

1. **Stack real = Python, no PHP, ni Go.** Aunque el informe técnico y el SRS contemplaban un stack Go + Python (y la instrucción inicial mencionaba PHP), la implementación real es **Python 3.12 + FastAPI** (backend) y **React 18 + Vite + TypeScript** (frontend). No hay microservicios Go ni PHP en el código.
2. **Patrón de capas estricto en backend:** Modelo (SQLAlchemy 2.0 `Mapped`/`mapped_column`) → Repositorio (acceso a datos) → Servicio (lógica) → Endpoint (HTTP).
3. **Multi-tenant transversal:** `tenant_id` en casi todos los modelos vía mixin `TenantMixin`. Auditoría (`created_by_id`/`updated_by_id`) y soft-delete (`deleted_at`/`deleted_by`) vía mixins en `WMSBase`.
4. **Seguridad por permisos declarativos:** dependencia `require_permission("...")` en los endpoints; los códigos de permiso y roles se siembran en `seeds/run_all.py`. Regla aprendida: **todo permiso exigido por un endpoint debe estar sembrado**, o el módulo "no hace nada" para roles no-superadmin (devuelve 403).
5. **Metodología "nada asumido":** cada afirmación técnica se verifica **ejecutando** (construir objetos ORM, invocar repos con los kwargs reales del servicio, serializar cada `*Response`, correr la suite). Esto nació precisamente del problema raíz del proyecto.
6. **Esquema de BD:** se pasó de depender de `create_all` a tener **migración inicial Alembic** (auto-aplicable en arranque). Mantener Alembic al día es requisito antes de producción.
7. **Convención de commits:** `tipo(scope): descripción` en español, referenciando IDs de requerimiento (`FR-xxx`, `REG-xxx`, `NFR`). Ej.: `feat(security): MFA TOTP + auditoría automática + /metrics (FR-001/004 + NFR)`.
8. **Moneda funcional USD** (paridad Balboa/USD); cumplimiento Ley 81/2019 de protección de datos; formatos oficiales ANA/SIGA y DGI para integraciones regulatorias.

---

## 3. Estado actual (autoritativo = Git)

### Backend (`wms-backend/`)

Routers montados bajo `/api/v1` (ver `app/api/v1/router.py`): `health, auth, tenants, users, warehouses, master, inventory, inbound, outbound, ai, realtime, integrations, sync, yms`.

| Módulo | Estado | Notas |
|---|---|---|
| **Inbound** (PO → ASN → GRN → QC → Putaway → RTV) | Reconciliado y verificado (construye y serializa) | PO con edición, historial de estados (`POStatusHistory`) y borrado lógico. GRN/QC/Putaway/RTV reconciliados (commit `69ec15b`, `f2c5633`). |
| **Inventory** | Reconciliado | Flujo de ajustes cabecera+líneas (`InventoryAdjustment`+`AdjustmentLine`); FEFO; locks distribuidos (Redis); kardex y transferencias. |
| **Outbound** (SO → Wave → Picking → Pack → Shipment → RMA) | Alineado | Corregidas 3 llamadas a `InventoryService` (reservas, FEFO, pick). Modos de picking añadidos. |
| **Maestros** | CRUD + carga masiva | Antes era solo lectura (commit `d99124f`). |
| **Seguridad** | MFA TOTP + auditoría automática + `/metrics` | Commit `691f98e`. |
| **Regulatorio Panamá** | ANA/SIGA (DAM) y DGI (factura) | Código presente en `app/integrations/regulatory/` (`ana_siga.py`, `dgi.py`); wiring API. Ley 81. Commits `61fca45`, `af8165f`. |
| **Integraciones** | ERP / eCommerce / carrier (scaffolding + wiring) | `app/integrations/` (`erp.py`, `ecommerce.py`, `carrier.py`, `http_client.py`). |
| **YMS** (patio/docks) | Implementado | `app/models/yms.py`, endpoint `yms`, migración `yms0001_yard_management.py`. |
| **Sync offline** | Implementado | endpoint `sync` (FR-006). |
| **IA/ML** | Servicios presentes | `app/services/ai/` (anomaly, assistant, forecasting, optimizer). Verificar si usan librerías reales (Prophet/OR-Tools/LangChain) o heurísticas. |
| **Tareas async** | Celery | `app/tasks/` (celery_app, integration_tasks). |

### Frontend (`wms-frontend/`)

SPA React 18 + Vite + TS + React Query + Zustand + Tailwind + react-hook-form/zod. Componentes UI reutilizables en `src/components/ui/` (Card, Table, Badge, Button, Input, Modal, Combobox, Select, KpiCard, Pagination). Páginas por módulo en `src/pages/` (auth, dashboard, inbound, etc.). Cliente API en `src/api/`. El informe ejecutivo menciona ~22 vistas reales (sin pantallas "en construcción").

### Pruebas y CI

- Suite reportada: **~202 tests pasan**, con **1 fallo preexistente y ajeno** en `tests/unit/test_security.py` (formato de API key, no tocado).
- Tipos frontend: `tsc --noEmit` sale **0**.
- Hay suite de integración contra **PostgreSQL real** (`tests/integration_db/`) con runner de un comando, y CI en `.github/workflows/ci.yml`.

### Lo que **no** está verificado (riesgo principal)

**Nada se ha ejecutado end-to-end contra un PostgreSQL real desde la API.** Las reconciliaciones se verificaron construyendo ORM y serializando con sesión mockeada. La red de seguridad que falta son tests de integración end-to-end (crear → confirmar → recibir → QC → putaway → picking → despacho) contra BD real.

---

## 4. Trabajo pendiente (priorizado)

1. **Validación en vivo:** levantar el stack y ejercitar los flujos end-to-end contra PostgreSQL real; ampliar `tests/integration_db/`.
2. **Migraciones Alembic:** consolidar el esquema acumulado (Inbound + Inventory + Outbound + YMS + maestros + regulatorio) y los renombrados de columna; no depender de `create_all`.
3. **Confirmar profundidad real** de regulatorio, integraciones e IA: distinguir scaffolding/stubs de implementación productiva (las credenciales ANA/DGI y los formatos oficiales son ruta crítica con dependencias externas).
4. **Seguridad avanzada restante:** SSO (SAML/OIDC), gestión de secretos (Vault), escaneo CI (Trivy).
5. **Dispositivos de bodega:** RF (Zebra/Honeywell), impresión ZPL, báscula.
6. **Tiempo real:** dashboard vía WebSockets.
7. **Evidencias/adjuntos en Control de Calidad** (si se habilita almacenamiento de archivos).

---

## 5. Archivos y carpetas relevantes

### Documentación (raíz `.docx`/`.xlsx`)

- `WMS_Panama_Analisis_Estado_y_Plan.docx` — informe ejecutivo de estado + plan de completación por fases, backlog y roadmap. **Snapshot anterior a los últimos commits** (ver §6).
- `WMS_Panama_SRS_Requerimientos.docx` — Especificación formal: 53 RF/REG, NFR e integraciones, usuarios, restricciones (Ley 81, ANA/SIGA, DGI, USD, offline, GS1). Es el "contrato" funcional.
- `WMS_Panama_Informe_Tecnico.docx` — definición técnica/arquitectural; historia del proceso colaborativo por roles; decisiones de stack.
- `WMS_Panama_Herramientas_Entorno_Desarrollo.docx` — checklist de instalación del entorno (VS Code, Python 3.12 vía pyenv, Node 20 vía nvm, uv, Ruff, mypy, pytest, Docker, DBeaver/RedisInsight, etc.).
- `Comparativo_WMS_Panama_vs_Competencia.xlsx` — comparativo de funcionalidades vs. competencia.

### Documentación (`docs/*.md`) — reportes basados en evidencia

- `INBOUND_Analisis_y_Plan.md` — diagnóstico raíz y reconciliación de Purchase Orders.
- `INBOUND_Reconciliacion_GRN_QC_Putaway.md` — reconciliación de GRN/QC/Putaway/RTV.
- `INBOUND_Validacion_Tecnica.md` — validación técnica (qué quedó funcional vs. pendiente en su momento).
- `INBOUND_Diagnostico_y_Plan_Publicacion.md` — diagnóstico de publicación (problemas de `git index.lock`, credenciales).
- `INVENTORY_y_Migraciones_Alembic.md` — reconciliación de ajustes de inventario + migración inicial Alembic.
- `OUTBOUND_Validacion_y_Fixes.md` — validación Outbound y fixes de integración con InventoryService.
- `Guia_Habilitacion_Git_GitHub_macOS.md` — guía para publicar (sandbox Linux vs. Keychain de macOS, `gh`, token).

### Código backend (`wms-backend/app/`)

- `api/v1/router.py` y `api/v1/endpoints/*.py` — capa HTTP por módulo.
- `models/*.py` — ORM (`base.py` con mixins; `core.py`, `inbound.py`, `inventory.py`, `outbound.py`, `yms.py`, `master_data.py`, `ai.py`).
- `repositories/*.py` — acceso a datos (inbound, inventory, outbound).
- `services/*.py` y `services/ai/*` — lógica de negocio y módulo IA.
- `core/*.py` — config, dependencias, seguridad, GS1, logging, excepciones.
- `integrations/*` — ERP, eCommerce, carrier, y `regulatory/` (ANA/SIGA, DGI).
- `tasks/*` — Celery.
- `seeds/run_all.py` — siembra de permisos/roles (**mantener sincronizado con los endpoints**).
- `alembic/versions/*` — migraciones.
- `tests/{unit,integration,integration_db,load}/` — suites.

### Código frontend (`wms-frontend/src/`)

- `api/` (cliente y endpoints), `components/ui/` y `components/layout/`, `pages/` por módulo, `hooks/`, `types/index.ts` (tipos compartidos; deben coincidir con los enums del backend).

### Infraestructura / DevOps

- `docker-compose.prod.yml`, `wms-backend/docker-compose.yml`, `wms-backend/Dockerfile`, `nginx/nginx.prod.conf`, `monitoring/prometheus.yml`, `scripts/deploy.sh`, `scripts/healthcheck.sh`, `.github/workflows/ci.yml`.

### Credenciales — acción requerida

- Existe un archivo `gh_token` en la raíz (token de GitHub). Está en `.gitignore`, pero **vive en la carpeta local**. **Recomendación para el proyecto nuevo: regenerar el token** (revocar el actual desde GitHub) y **no copiar este archivo**; gestionarlo fuera del repo (variable de entorno o gestor de secretos). No se incluye su contenido en este traspaso a propósito.

---

## 6. Divergencia documentación ↔ código (importante)

El informe `WMS_Panama_Analisis_Estado_y_Plan.docx` reporta Regulatorio al **0 %**, MFA/SSO pendientes, maestros solo lectura e IA heurística. Sin embargo, **commits posteriores del 2026-06-02** añadieron: MFA TOTP (`691f98e`), maestros CRUD + carga masiva (`d99124f`), regulatorio ANA/SIGA + DGI (`61fca45`), YMS + sync offline + Ley 81 + wiring ERP (`af8165f`) y tareas Celery (`23af4a9`).

**Conclusión:** trata el `.docx` como una foto histórica útil para el *plan/roadmap*, pero valida el **estado real contra el código y el `git log`**. Lo que queda genuinamente por confirmar es la **profundidad** (productivo vs. scaffolding/stub) de regulatorio, integraciones e IA, y la **validación en runtime** contra BD real.

---

## 7. Preferencias y terminología

**Preferencias de trabajo (Alejo):**
- Idioma: **español** en todo (respuestas, commits, documentación).
- **Evidencia antes que afirmación:** ejecutar y verificar; distinguir explícitamente lo verificado de lo pendiente. Nunca dar por hecho el estado de un módulo sin comprobarlo.
- Commits descriptivos en español con `tipo(scope): …` y referencia a IDs de requerimiento.
- Reportes estructurados con tablas de estado por módulo/capa.

**Terminología y siglas del dominio:**
- **Inbound:** PO (orden de compra), ASN (aviso de despacho), GRN (`GoodsReceipt`, recepción), QC (control de calidad), Putaway (ubicación), RTV (devolución a proveedor).
- **Outbound:** SO (orden de venta), Wave (ola de picking), Picking, Pack, Shipment, RMA (devolución de cliente).
- **Inventory:** FEFO (primero en expirar, primero en salir), kardex, ajustes (cabecera+líneas), niveles por lote/ubicación.
- **Regulatorio Panamá:** ANA (aduanas), SIGA, DAM (declaración aduanera), DGI (impuestos / factura electrónica), ITBMS (impuesto), MINSA, AUPSA/MIDA, ZLC (Zona Libre de Colón), VUPE, Ley 81/2019 (protección de datos).
- **Estándares GS1:** GTIN-13/14, SSCC, GLN, GS1-128, DataMatrix.
- **Arquitectura:** multi-tenant (`tenant_id`), soft-delete, `require_permission`, mixins de `WMSBase`.
- **IDs de requerimiento:** `FR-xxx` (funcional), `REG-xxx` (regulatorio), `NFR` (no funcional).

---

## 8. Prompt inicial recomendado para el proyecto nuevo

> Eres mi colaborador técnico en el **WMS Panamá**, un Warehouse Management System multiempresa/multi-bodega para Panamá. Stack real: **backend Python 3.12 + FastAPI + SQLAlchemy 2.0 async + PostgreSQL 16** (carpeta `wms-backend`, patrón Modelo→Repositorio→Servicio→Endpoint, multi-tenant por `tenant_id`, permisos vía `require_permission` sembrados en `seeds/run_all.py`) y **frontend React 18 + Vite + TypeScript + React Query + Tailwind** (`wms-frontend`). Repo: github.com/ljorrin/WMS, rama `feature/inbound-module`.
>
> **Reglas de colaboración:**
> 1. Respóndeme **siempre en español**.
> 2. Metodología **"nada asumido"**: verifica cada afirmación técnica **ejecutando** (importar modelos, construir ORM, serializar `*Response`, correr la suite, contar rutas/tablas) y distingue lo verificado de lo pendiente.
> 3. Toma el **`git log` y el código como fuente autoritativa** del estado; los `.docx` de la raíz son contexto histórico (pueden estar desactualizados).
> 4. Commits en español con formato `tipo(scope): descripción (FR-xxx/REG-xxx)`.
> 5. Si un endpoint exige un permiso, asegúrate de que esté **sembrado** en `seeds/run_all.py`.
>
> **Contexto de estado:** Inbound (PO/GRN/QC/Putaway/RTV), Inventory (ajustes/FEFO) y Outbound están reconciliados y verificados estáticamente; maestros CRUD, MFA TOTP, regulatorio ANA-SIGA/DGI, YMS, sync offline y Celery fueron añadidos después del informe ejecutivo. **Lo crítico pendiente es la validación end-to-end contra PostgreSQL real** y consolidar las migraciones Alembic.
>
> **Primera tarea:** levanta el stack en local, aplica migraciones, siembra datos y ejecuta la suite (incluida `tests/integration_db/`). Dame un **reporte de estado real verificado** por módulo (qué funciona end-to-end vs. qué falla o es scaffolding), y a partir de ahí proponme el plan priorizado. Antes de codificar, confírmame el alcance.

---

## 9. Checklist de arranque del proyecto nuevo

- [ ] Clonar el repo y situarse en `feature/inbound-module` (o integrar a `main` según se decida).
- [ ] **Regenerar el token de GitHub**; no copiar `gh_token`.
- [ ] Instalar entorno según `WMS_Panama_Herramientas_Entorno_Desarrollo.docx` (Python 3.12, Node 20, Docker, uv, Ruff, mypy).
- [ ] `docker compose up` (PostgreSQL 16, Redis 7, Meilisearch); aplicar migraciones Alembic; correr `seeds/run_all.py`.
- [ ] Levantar API (Uvicorn) y revisar `/docs`; levantar frontend (`npm run dev`).
- [ ] Ejecutar suites: unit, `integration`, `integration_db` (PostgreSQL real) y `tsc --noEmit`.
- [ ] Generar **reporte de estado real verificado** por módulo y consolidar migraciones.
