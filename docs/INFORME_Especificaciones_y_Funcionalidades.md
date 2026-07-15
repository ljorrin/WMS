# Informe de Especificaciones y Funcionalidades Implementadas — WMS Panamá

**Fecha:** 2026-07-14 · **Rama:** `feature/inbound-module` (commit `4d017996`)
**Fuentes:** SRS (`WMS_Panama_SRS_Requerimientos.docx`), `TRASPASO_WMS_Panama.md`, reportes `docs/*.md` y **revisión directa del código** (backend y frontend).
**Metodología:** "nada asumido" — cada afirmación de implementación está respaldada por evidencia en el código (archivo, ruta o modelo). Se distingue explícitamente lo **verificado estáticamente** de lo **pendiente de validación en runtime**.

---

## 1. Resumen ejecutivo

WMS Panamá es un **Warehouse Management System multiempresa, multi-bodega y multi-país** para la República de Panamá, que cubre la cadena logística completa (fabricante → aduanas → CD → retail → eCommerce) con cumplimiento del marco regulatorio panameño (Ley 81/2019, ANA/SIGA, DGI) y estándares GS1.

Estado global: la implementación cubre **la gran mayoría de los 53 requerimientos funcionales/regulatorios del SRS a nivel de código**, con:

- **Backend:** 14 routers bajo `/api/v1` con **156 rutas HTTP/WS**, ~60 entidades ORM, 5 migraciones Alembic, 259 funciones de test.
- **Frontend:** SPA React con **28 vistas/modales** organizadas en 7 módulos y 53 endpoints consumidos.
- **Riesgo principal (sin cambios):** nada se ha ejercitado **end-to-end contra PostgreSQL real desde la API**; las verificaciones son estáticas (construcción ORM + serialización con sesión mockeada). La profundidad de regulatorio/integraciones/IA es funcional pero **no certificada contra los formatos oficiales** de ANA/DGI.

---

## 2. Especificación del sistema (según SRS v1.0, mayo 2026)

### 2.1 Propósito y alcance

El SRS es el "contrato" funcional del proyecto (53 RF/REG + NFR + INT). Alcance declarado:

- Gestión de múltiples empresas, bodegas y países desde una sola plataforma.
- Industrias: consumo masivo, automotriz, farmacéutico, ferretería, electrónica, moda, agro-alimentario.
- Integración con entidades regulatorias: ANA, DGI, MINSA, AUPSA, MIDA, ATTT, VUPE.
- Estándares GS1: GTIN-13/14, SSCC, GLN, GS1-128, DataMatrix.
- IA: predicción de demanda, optimización de slotting/rutas, consultas NLP, detección de anomalías.
- Operación offline completa para bodegas sin conectividad continua.

**Fuera de alcance:** ERP, POS, contabilidad, plataformas eCommerce (solo integración vía API) y desarrollo de hardware (RF/impresoras/báscula: integración vía drivers).

### 2.2 Usuarios del sistema

Gerente de Logística, Jefe de Bodega, Operario de Recepción, Operario de Bodega (putaway), Picker, Despachador, Agente Aduanero, Auditor de Inventario, Administrador TI y Director/C-Level.

### 2.3 Restricciones

Cumplimiento Ley 81/2019 (datos personales), formatos oficiales ANA/SIGA para aduanas, especificaciones DGI para factura electrónica (ITBMS 7%), moneda funcional **USD** (paridad Balboa), operación **offline**, codificación de productos **GS1**.

### 2.4 Catálogo de requerimientos del SRS

| Módulo SRS | Requerimientos |
|---|---|
| 3.1 Seguridad, usuarios y acceso | FR-001 MFA · FR-002 RBAC · FR-003 Multitenancy · FR-004 Auditoría · FR-005 SSO · FR-006 Offline/Sync |
| 3.2 Maestro de datos | FR-010 Productos multi-industria · FR-011 Jerarquía embalaje GS1 · FR-012 Ubicaciones 3D · FR-013 Proveedores con SLA · FR-014 Migración/carga masiva · FR-015 Deduplicación |
| 3.3 Inbound | FR-020 PO→ASN→GRN · FR-021 Recepción RF tiempo real · FR-022 QC en recepción · FR-023 RTV · FR-024 Cadena de frío · FR-025 Modo descarga contenedores |
| 3.4 Putaway | FR-030 Dirigido por reglas · FR-031 Multi-paso RF · FR-032 Zona de cuarentena |
| 3.5 Inventario | FR-040 Tiempo real por ubicación · FR-041 Ciclos de conteo · FR-042 Ajustes con aprobación · FR-043 FEFO/FIFO/LIFO · FR-044 Reservas · FR-045 Transferencias · FR-046 Alertas stock mínimo |
| 3.6 Outbound (picking) | FR-050 Orden completa · FR-051 Por zona · FR-052 Batch · FR-053 Wave · FR-054 Cluster · FR-055 Verificación · FR-056 Packing + etiquetas |
| 3.7 Despacho | FR-060 Cita transporte/dock · FR-061 Documentos de despacho · FR-062 Confirmación de carga y cierre |
| 3.8 Regulatorio Panamá | REG-001 ANA/SIGA DAM · REG-002 Factura DGI/ITBMS · REG-003 Zonas francas (ZLC) · REG-004 Trazabilidad MINSA · REG-005 Sanitario AUPSA/MIDA · REG-006 Ley 81/2019 |
| 3.9 KPIs | FR-070 Dashboard tiempo real · FR-071 Productividad · FR-072 Precisión/calidad · FR-073 Utilización infraestructura · FR-074 Reportes regulatorios |
| 3.10 IA | FR-080 Slotting · FR-081 Forecasting · FR-082 NLP · FR-083 Anomalías |
| 4. NFR seguridad | NFR-001 Cifrado · NFR-002 Gestión de secretos · NFR-003 Escaneo CI/CD |
| 5. Integraciones | ERP (SAP/Oracle/Dynamics/Odoo) · eCommerce · Transportistas · Dispositivos de bodega |

---

## 3. Arquitectura y stack implementados

### 3.1 Stack real (verificado en `requirements.txt` / `package.json`)

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12 · FastAPI 0.115.5 · SQLAlchemy 2.0.36 **async** (`Mapped`/`mapped_column`) · PostgreSQL 16 · Alembic · Redis 5.2 (hiredis) · Celery 5.4 · Meilisearch 0.31.5 · pyotp 2.9 (MFA) · Sentry SDK |
| IA/ML | Prophet 1.1.6 · scikit-learn 1.5.2 · LangChain 0.3.7 (+ langchain-openai) · OR-Tools 9.11 |
| Frontend | React 18 · Vite · TypeScript · React Query · Zustand · Tailwind · react-hook-form + zod · Radix UI · Recharts |
| Infra | Docker Compose (dev y `docker-compose.prod.yml`) · Nginx (`nginx.prod.conf`, `nginx.laragon.conf`) · Prometheus (`monitoring/prometheus.yml`) · GitHub Actions (`.github/workflows/ci.yml`) · scripts `deploy.sh`/`healthcheck.sh` · guía de despliegue Windows Server 2022 |

Nota: el SRS/informe técnico contemplaba un stack Go+Python; la decisión registrada en el traspaso es que **el stack real es 100 % Python + React** (no hay Go ni PHP).

### 3.2 Patrón de arquitectura backend

Capas estrictas **Modelo → Repositorio → Servicio → Endpoint**, con:

- **Multi-tenant transversal (FR-003):** `tenant_id` vía `TenantMixin` en casi todos los modelos; base `WMSTenantBase`.
- **Auditoría y soft-delete:** `AuditMixin` (`created_by_id`/`updated_by_id`), `SoftDeleteMixin` (`deleted_at`/`deleted_by`), `TimestampMixin`.
- **Permisos declarativos (FR-002):** dependencia `require_permission("modulo:entidad:accion")` en endpoints. **Verificado:** los **41 permisos** exigidos por endpoints están **todos sembrados** en `seeds/run_all.py` (0 huérfanos), junto con 4 roles de sistema (Administrador WMS, Supervisor de Bodega, Operador de Bodega, Analista IA).
- **Esquema por Alembic:** 5 migraciones en `alembic/versions/` (`bcf617d7ac65_initial_schema`, `yms0001_yard_management`, `9f76b3221a22` quantity_in_transit + cycle count, y 2 fixes de nullabilidad `uom_id`).

### 3.3 Superficie de la API (`/api/v1`, 156 rutas)

| Router | Rutas | Ámbito |
|---|---|---|
| `health` | 4 | Liveness/readiness, `/metrics` Prometheus |
| `auth` | 10 | Login, login RF (PIN), refresh, logout, me, reset/cambio de contraseña, **MFA enroll/verify/disable** |
| `tenants` / `users` / `warehouses` | 3 / 7 / 3 | Core multi-tenant; incluye `POST /users/{id}/anonymize` (Ley 81) |
| `master` | 15 | CRUD productos/proveedores/ubicaciones, **bulk-import** ×3, **duplicates** ×2, SLA proveedor |
| `inventory` | 23 | Stock, kardex, transferencias, ajustes (aprobar/aplicar), ciclos de conteo, vencimientos, reservas, reorder-proposals, dashboard |
| `inbound` | 31 | PO (CRUD+confirm/cancel), ASN (dispatch/arrive), GRN (confirm), QC (resolve), Putaway (start/complete), RTV (ship/credit), dashboards |
| `outbound` | 30 | SO (confirm/cancel), Waves (release, pick-list), Picking, Packing, Shipments (dispatch/deliver, packing-list PDF), RMA, dashboards |
| `ai` | 12 | Forecast, alertas, optimización de rutas, escaneo/gestión de anomalías, asistente conversacional |
| `integrations` | 9 | Status, carrier quote/track, eCommerce stock-sync/orders, ERP POs/SOs, **regulatory/dam** y **regulatory/invoice** |
| `realtime` | 1 (WS) | WebSocket `/ws/dashboard` con autenticación por token y push de métricas |
| `sync` | 2 | `POST /sync/operations`: lote offline idempotente (dedupe por `client_op_id` vía Redis) |
| `yms` | 7 | Docks, citas de patio (assign-dock/arrive/depart) |

### 3.4 Modelo de datos (~60 entidades ORM)

- **Core:** Tenant, Company, User, Role, Permission, RolePermission, UserRole, AuditLog, Warehouse, Zone, Location.
- **Maestros:** Product, ProductCategory, ProductPackaging (jerarquía GS1), Supplier, Customer, Carrier, SerialNumber, Batch.
- **Inbound:** PurchaseOrder(+Line, +StatusHistory), ASN(+Line), GoodsReceipt(+Line), QualityInspection(+Line), PutawayTask, ReturnToVendor.
- **Inventory:** InventoryLevel, InventoryMovement, InventoryAdjustment(+AdjustmentLine), InventoryReservation, CycleCount(+Line), StockAlert, ReplenishmentAlert.
- **Outbound:** SalesOrder(+Line), PickingWave, PickingTask, PackTask, Shipment, ReturnOrder (RMA).
- **YMS:** Dock, YardAppointment.
- **IA:** DemandForecast, AnomalyEvent, AIConversation(+Message), PickingRouteOptimization.
- **Enums de dominio:** RotationStrategy (FEFO/FIFO/LIFO), PickingMethod, StorageCondition (cadena frío), ReceivingMode, TrackingType (lote/serie), IndustryType, etc.

---

## 4. Funcionalidades implementadas por módulo (evidencia en código)

### 4.1 Seguridad, usuarios y acceso

| Funcionalidad | Evidencia | Estado |
|---|---|---|
| Autenticación JWT (access/refresh/reset) + hashing | `core/security.py` | Implementado |
| **MFA TOTP** (enroll/verify/disable) | `auth.py` + pyotp (FR-001) | Implementado (TOTP; SMS/email no) |
| Login RF con PIN para operarios | `POST /auth/login/rf`, `generate_rf_pin` | Implementado |
| RBAC granular por permiso | `require_permission` en 41 permisos, seeds sincronizados | Implementado y verificado |
| Multitenancy con aislamiento | `TenantMixin` transversal | Implementado (falta prueba E2E de aislamiento) |
| **Auditoría automática** | `services/audit_listener.py`: listener global `before_flush` sobre toda entidad con `tenant_id`, best-effort, tabla `AuditLog` | Implementado (retención 5 años/append-only se refuerza en BD al desplegar) |
| Sync offline idempotente | `sync.py`: lote de operaciones, dedupe Redis por `client_op_id`, fallos aislados no detienen el lote (FR-006) | Implementado |
| API keys y enmascaramiento de sensibles | `core/security.py` | Implementado |
| SSO SAML/OIDC (FR-005) | — | **No implementado** (pendiente declarado) |

### 4.2 Maestro de datos

| Funcionalidad | Evidencia | Estado |
|---|---|---|
| CRUD productos/proveedores/ubicaciones | `master_data.py` (15 rutas) | Implementado |
| Carga masiva con validación (FR-014) | `POST /{products,suppliers,locations}/bulk-import` | Implementado |
| Deduplicación (FR-015) | `GET /{products,suppliers}/duplicates` | Implementado |
| SLA de proveedores (FR-013) | `GET /suppliers/{id}/sla` | Implementado |
| Jerarquía de embalaje GS1 (FR-011) | modelo `ProductPackaging`; `core/gs1.py`: dígito verificador, validación GTIN, **generación SSCC** | Implementado |
| Atributos multi-industria (FR-010) | enums `IndustryType`, `TrackingType`, `StorageCondition`; lote/serie/vencimiento | Implementado |

### 4.3 Inbound (FR-020…025, FR-030…032)

Flujo completo **PO → ASN → GRN → QC → Putaway → RTV** con 31 rutas:

- PO con edición, confirmación, cancelación, borrado lógico e historial de estados (`POStatusHistory`).
- ASN con despacho y llegada; GRN con confirmación; QC con inspecciones y resolución (incluye disposición a cuarentena — FR-032); Putaway con start/complete; RTV con ship y nota de crédito.
- Dashboards de recepción y throughput.
- Modo de recepción de contenedores: enum `ReceivingMode` (FR-025). Cadena de frío: `StorageCondition` a nivel de producto/ubicación (FR-024, sin telemetría de temperatura en tránsito).
- **Estado:** reconciliado y verificado estáticamente (docs `INBOUND_*.md`). Pendiente E2E vivo. Hardware RF real (FR-021): fuera del código, vía dispositivos.

### 4.4 Inventario (FR-040…046)

- Stock por ubicación/lote, resumen por producto, kardex de movimientos, transferencias.
- Ajustes **cabecera + líneas** con flujo crear → aprobar → aplicar (FR-042); locks distribuidos Redis para concurrencia.
- Ciclos de conteo (crear, registrar resultados, completar) — FR-041, con página frontend dedicada.
- Rotación **FEFO/FIFO/LIFO/LEFO** (`RotationStrategy`), consultas de lotes por vencer/vencidos (FR-043).
- Reservas de inventario (crear/listar/liberar) — FR-044.
- Alertas de stock (`StockAlert`, `ReplenishmentAlert`) y `GET /reorder-proposals` — FR-046.

### 4.5 Outbound (FR-050…062)

Flujo completo **SO → Wave → Picking → Pack → Shipment → RMA** con 30 rutas:

- SO con confirmación/cancelación; olas con liberación y pick-list; picking y packing con start/complete; shipments con dispatch/deliver; RMA con recepción.
- **Modos de picking** (FR-050…054): enum `PickingMethod` con `discrete` (orden completa), `batch`, `zone` y `cluster`; el wave picking (FR-053) se cubre con la entidad `PickingWave` y sus rutas de liberación.
- KPIs OTD y fill-rate calculados en `outbound_service.py` (FR-072).
- Documentos de despacho (FR-061): `document_service.build_packing_list_pdf` + `GET /shipments/{id}/packing-list`.
- Citas de transporte y docks (FR-060): módulo **YMS** (docks, citas, assign-dock/arrive/depart).
- Integración con `InventoryService` (reservas, FEFO, pick) corregida y alineada (doc `OUTBOUND_Validacion_y_Fixes.md`).

### 4.6 Regulatorio Panamá (REG-001…006)

| Req | Evidencia | Profundidad real |
|---|---|---|
| REG-001 ANA/SIGA DAM | `integrations/regulatory/ana_siga.py` (70 líneas): construye XML de la DAM (régimen, aduana, RUC, transporte, ítems arancelarios, totales USD) y lo envía a SIGA vía `http_client` (config `SIGA_BASE_URL`/`API_KEY`) | Funcional pero **formato no certificado** contra esquema oficial SIGA; requiere credenciales reales |
| REG-002 Factura DGI | `integrations/regulatory/dgi.py` (77 líneas) + `POST /integrations/regulatory/invoice` | Ídem: ITBMS calculado, **sin certificación DGI** (firma electrónica/PAC pendiente) |
| REG-003 Zonas francas ZLC | Referencias en modelos (`core`, `inventory`, `master_data`) | **Parcial** — atributos de datos, sin flujo operativo dedicado |
| REG-004 Trazabilidad MINSA | `SerialNumber`, `Batch`, `TrackingType`, kardex | **Parcial** — trazabilidad genérica lote/serie, sin reporte MINSA específico |
| REG-005 AUPSA/MIDA | Atributos en maestros | **Parcial** — sin flujo dedicado |
| REG-006 Ley 81/2019 | `POST /users/{id}/anonymize`, enmascaramiento, auditoría | Implementado (núcleo) |

### 4.7 KPIs y tiempo real (FR-070…074)

- Dashboards por módulo (`/inventory/dashboard`, `/inbound/dashboard[/throughput]`, `/outbound/dashboard[/throughput]`).
- KPIs OTD / fill-rate / recepción (commit `6b7f510`, FR-072/061).
- **WebSocket** `/ws/dashboard` con autenticación por token y push periódico de métricas (FR-070).
- `/metrics` Prometheus + `monitoring/prometheus.yml` (NFR observabilidad).
- FR-074 (reportes regulatorios formales): **parcial**.

### 4.8 IA/ML (FR-080…083)

12 rutas en `/ai` respaldadas por `services/ai/`:

- **Forecasting** (`forecasting.py`): usa **Prophet** (import real, lazy); persiste `DemandForecast`.
- **Optimización de rutas de picking** (`optimizer.py`): **OR-Tools** (constraint solver, import real); `PickingRouteOptimization`.
- **Asistente NLP** (`assistant.py`): **LangChain + ChatOpenAI** (import real, lazy) con conversaciones persistidas (`AIConversation`).
- **Anomalías** (`anomaly.py`): escaneo y resolución (`AnomalyEvent`).
- Los imports de librerías reales son lazy (con fallback si no están disponibles); la **calidad de resultados con datos reales no está validada** y el asistente requiere API key de OpenAI.

### 4.9 Integraciones (sección 5 del SRS)

- Conectores `erp.py`, `ecommerce.py`, `carrier.py` sobre `http_client.py` común + `config.py` (27–72 líneas c/u): **scaffolding funcional + wiring API**, no adaptadores productivos por proveedor (SAP/Oracle/Shopify… pendientes de credenciales y mapeos reales).
- **Celery** (`tasks/`): `pull_erp_orders`, `sync_ecommerce_stock`, `update_fulfillment`.
- Dispositivos de bodega (RF Zebra/Honeywell, ZPL, báscula): **no implementado** (pendiente declarado).

### 4.10 Frontend (28 vistas/modales, 26 rutas SPA)

| Módulo | Páginas |
|---|---|
| Auth | Login |
| Dashboard | Dashboard con sección de inventario y KPIs (Recharts) |
| Inbound | POs (lista + form + detalle + edición), GRNs (lista + form + detalle), Calidad, Putaway, RTV |
| Inventory | Stock, Movimientos/kardex, Ajustes, Vencimientos, Ciclos de conteo, Transferencias |
| Outbound | SOs (lista + form), Olas, Picking, Packing, Envíos (+ modal creación), Devoluciones |
| Maestros | MasterDataPage (productos/proveedores/ubicaciones) |
| Settings | Configuración |

Componentes UI propios (Card, Table, Badge, Modal, Combobox, KpiCard, Pagination…), cliente API con 53 endpoints tipados, tipos alineados con enums del backend, `tsc --noEmit` en 0.

---

## 5. Calidad, pruebas y CI

| Aspecto | Evidencia |
|---|---|
| Tests | **259 funciones de test** en `tests/{unit, integration, integration_db, load}`. Unit por servicio (inbound, inventory, outbound, IA, regulatorio, GS1, seguridad, auditoría); integración de API por módulo; suite `integration_db` contra **PostgreSQL real** con runner de un comando |
| CI | `.github/workflows/ci.yml` valida migración + suite `integration_db` contra PostgreSQL real |
| Calidad estática | Ruff + mypy (backend), `tsc --noEmit` = 0 (frontend) |
| Estado reportado | ~202 tests verdes con 1 fallo preexistente ajeno (`test_security.py`, formato API key) — según traspaso 2026-06-07 |

---

## 6. Matriz de trazabilidad SRS → implementación

| Requerimiento | Estado | Nota |
|---|---|---|
| FR-001 MFA | ✅ Parcial-alto | TOTP sí; SMS/email no |
| FR-002 RBAC · FR-003 Multitenant · FR-004 Auditoría | ✅ | Seeds sincronizados (41/41 permisos); auditoría automática global |
| FR-005 SSO | ❌ | Pendiente (SAML/OIDC) |
| FR-006 Offline/Sync | ✅ | Lote idempotente + dedupe Redis; falta prueba de 500 ops/conflictos |
| FR-010…015 Maestros | ✅ | CRUD + bulk-import + dedupe + SLA + GS1 |
| FR-020…023 Inbound núcleo | ✅ | Flujo completo PO→ASN→GRN→QC→RTV |
| FR-024 Cadena frío · FR-025 Contenedores | 🟡 | Atributos/enums presentes; sin telemetría ni flujo dedicado completo |
| FR-030…032 Putaway | ✅ | Tareas start/complete + cuarentena; reglas de putaway dirigido básicas |
| FR-040…046 Inventario | ✅ | Tiempo real, conteos, ajustes con aprobación, FEFO/FIFO/LIFO, reservas, transferencias, alertas |
| FR-050…056 Picking/Packing | ✅ | 4 métodos de picking + waves + verificación + packing |
| FR-060…062 Despacho | ✅ | YMS (docks/citas), packing-list PDF, dispatch/deliver |
| REG-001/002 ANA-DGI | 🟡 | Código funcional; **sin certificación oficial ni credenciales** |
| REG-003/004/005 | 🟡 | Parciales (atributos/trazabilidad genérica) |
| REG-006 Ley 81 | ✅ | Anonimización + auditoría + enmascaramiento |
| FR-070…073 KPIs | ✅ | Dashboards + WS tiempo real + /metrics |
| FR-074 Reportes regulatorios | 🟡 | Parcial |
| FR-080…083 IA | ✅ Código | Prophet/OR-Tools/LangChain reales (lazy); calidad con datos reales sin validar |
| NFR-001 Cifrado | 🟡 | TLS vía Nginx; cifrado en reposo depende del despliegue |
| NFR-002 Secretos (Vault) · NFR-003 Escaneo CI (Trivy) | ❌ | Pendientes declarados |
| INT ERP/eCommerce/Carrier | 🟡 | Scaffolding + Celery; sin adaptadores productivos por proveedor |
| INT Dispositivos (RF/ZPL/báscula) | ❌ | Pendiente |

**Leyenda:** ✅ implementado (verificado estáticamente) · 🟡 parcial/scaffolding · ❌ no implementado.

---

## 7. Riesgos y trabajo pendiente (priorizado)

1. **Validación end-to-end en vivo** contra PostgreSQL real desde la API (crear→confirmar→recibir→QC→putaway→picking→despacho). Es el riesgo principal: todo lo "✅" está verificado estáticamente, no en runtime completo.
2. **Consolidación Alembic** del esquema acumulado (las 5 migraciones deben cubrir todos los modelos actuales; verificar drift).
3. **Certificación regulatoria:** formatos oficiales SIGA/DGI, credenciales y firma electrónica (ruta crítica con dependencias externas).
4. **Seguridad avanzada:** SSO (FR-005), Vault (NFR-002), Trivy en CI (NFR-003).
5. **Dispositivos de bodega:** RF Zebra/Honeywell, impresión ZPL, báscula.
6. **Profundizar integraciones** ERP/eCommerce/carrier con adaptadores reales por proveedor.
7. Evidencias/adjuntos en QC (si se habilita almacenamiento de archivos).

---

*Informe generado a partir de revisión directa del código en la rama `feature/inbound-module` (2026-07-14). Los `.docx` de la raíz son fotos históricas; ante divergencia, prevalece el código y el `git log`.*
