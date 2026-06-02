# Módulo Inbound — Análisis (Fase 1) y Plan (Fase 2)

**Proyecto:** WMS Panamá · **Repositorio:** github.com/ljorrin/WMS · **Rama:** `feature/inbound-module`
**Fecha:** 2026-06-01

---

## Resumen ejecutivo

El brief pedía "implementar completamente el módulo Inbound porque los menús solo son listas/placeholders sin funcionalidad real". El análisis del repositorio real reveló algo distinto y más importante:

1. **El stack no es PHP.** Es **Python 3.12 + FastAPI + SQLAlchemy 2.0 async + PostgreSQL** (backend) y **React 18 + Vite + TypeScript** (frontend).
2. **El módulo Inbound ya estaba escrito casi por completo** (flujo PO → ASN → GRN → QC → Putaway → RTV, ~3.000 líneas) tanto en backend como en frontend. **No son placeholders.**
3. **El motivo real de que "no funcione" es que el backend nunca se había ejecutado.** Estaba lleno de defectos de integración que impedían incluso importar los modelos: nombres de columna reservados, clases inexistentes en imports, columnas/atributos desalineados entre modelo ↔ schema ↔ repositorio, y **permisos sembrados que no coinciden con los que exigen los endpoints**. Los 53 tests existentes pasaban porque son de lógica pura con mocks y **nunca importaban modelos, schemas ni la API**.

El trabajo de esta entrega se reorientó, con ese diagnóstico, a **hacer que el módulo funcione de verdad** y a **cerrar las brechas concretas de Órdenes de Compra** que pedía el brief (edición, historial de estados, borrado lógico), todo verificado ejecutando Python (no asumido).

---

## Fase 1 — Análisis

### Arquitectura encontrada

| Capa | Tecnología / Patrón |
|---|---|
| Backend | FastAPI, routers por módulo bajo `app/api/v1/endpoints/` |
| ORM | SQLAlchemy 2.0 (estilo `Mapped`/`mapped_column`), base común en `app/models/base.py` |
| Patrón | Modelo → Repositorio (acceso a datos) → Servicio (lógica) → Endpoint (HTTP) |
| Multi-tenant | `tenant_id` en casi todos los modelos (mixin `TenantMixin`) |
| Auditoría / soft-delete | Mixins `AuditMixin` (`created_by_id`/`updated_by_id`) y `SoftDeleteMixin` (`deleted_at`/`deleted_by`) en `WMSBase` |
| Seguridad | `require_permission("...")` como dependencia FastAPI; permisos y roles sembrados en `seeds/run_all.py` |
| Migraciones | Alembic configurado pero **`alembic/versions/` está vacío** → el esquema se crea desde los modelos (`create_all`) |
| Frontend | React Query + componentes UI en `src/components/ui/` (Card/Table/Badge/Button/Input/Modal/Combobox/Select), páginas en `src/pages/inbound/`, API en `src/api/endpoints.ts`, tipos en `src/types/index.ts` |

### Estado real del módulo Inbound (antes de esta entrega)

| Submódulo | Backend | Frontend |
|---|---|---|
| Purchase Orders | crear, listar, detalle, confirmar, cancelar | `POListPage`, `POFormModal`, `PODetailModal` |
| ASN | crear, listar, detalle, despachar, registrar llegada | — |
| GRN | crear, listar, detalle, confirmar | `GRNListPage`, `GRNFormModal`, `GRNDetailModal` |
| Quality Control | crear, listar pendientes, detalle, resolver | `QualityPage` |
| Putaway | listar, detalle, iniciar, completar (actualiza inventario) | `PutawayPage` |
| RTV | crear, listar, detalle, despachar, nota de crédito | — |

Conclusión: el módulo estaba **~90% implementado en código**, pero **0% funcional en ejecución** por los defectos descritos abajo.

### Componentes reutilizables (se reutilizaron, no se duplicó nada)

- UI: `Modal`, `Input`, `Button`, `Badge`, `Table`, `Combobox`, `Select`.
- Backend: mixins de `base.py` (soft-delete/auditoría), patrón repo/servicio, `require_permission`, paginación (`PaginationDep`).

### Defectos de integración verificados (causa raíz de la "no funcionalidad")

Todos confirmados ejecutando Python en este entorno.

**Bloqueantes de arranque (impedían importar el backend):**

1. `app/models/core.py` y `app/models/inventory.py`: columnas llamadas `metadata`, **nombre reservado** por la API Declarative de SQLAlchemy 2.0 → `app.models` no importaba.
2. `app/models/__init__.py`: importaba `GoodsReceiptNote` (clase inexistente; es `GoodsReceipt`).
3. `app/models/outbound.py` y `app/models/ai.py`: importaban `WMSBase` desde `app.db.session` (que no lo exporta) en lugar de `app.models.base`.
4. `app/repositories/inbound.py`: importaba `GRN` (clase inexistente).
5. `app/services/inventory_service.py`: importaba `AdjustmentLine` (modelo nunca definido) y `Warehouse` desde `app.models.master_data` (está en `app.models.core`).

**Desalineaciones modelo ↔ schema ↔ repositorio en Purchase Orders (rompían crear/listar/serializar):**

6. Atributo de auditoría: el código usa `created_by_id` en todo Inbound, pero la base definía `created_by`.
7. Líneas de OC: el repo construía con `po_id=` (la columna es `purchase_order_id`) y mapeaba `unit_cost`/`line_note` (las columnas son `unit_price`/`notes`).
8. Campos que el schema/servicio/AI usaban pero el modelo no tenía: `expected_delivery_date` (era `expected_date`), `erp_reference` (era `erp_po_number`), `erp_synced_at` (era `erp_sync_at`), `supplier_po_reference` y `closed_date` (no existían).
9. El schema de creación de línea exigía `uom_id: UUID` obligatorio, pero el frontend nunca lo envía → toda alta de OC habría fallado con 422.

**Seguridad (los menús "no hacían nada" para usuarios no-superadmin):**

10. Los endpoints exigen `inbound:po:confirm`, `inbound:po:cancel`, `inbound:grn:read/confirm`, `inbound:qc:create/resolve`, `inbound:putaway:manage`, `inbound:rtv:*`, pero `seeds/run_all.py` **solo sembraba** `inbound:po:read/create`, `inbound:grn:create/approve`, `inbound:putaway:execute`. Resultado: confirmar OC, resolver QC o gestionar putaway devolvían 403 para cualquier rol que no fuera superadmin.

### Riesgos

- **Sin tests de integración/BD:** los defectos anteriores fueron invisibles durante meses. Es el riesgo estructural principal.
- **Sin migraciones:** el esquema depende de `create_all`; cualquier cambio de columna requiere recrear/migrar. Hay que generar migraciones Alembic antes de producción.
- **Otros módulos comparten el mismo patrón de defectos** (ver "Trabajo pendiente"): el flujo de ajustes de inventario tiene una inconsistencia cabecera/líneas más profunda; ASN/GRN/QC/Putaway/RTV tienen desalineaciones análogas a las de PO que aún no se han reconciliado.

---

## Fase 2 — Plan y entregables

### Lo realizado en esta entrega (Fase 3 — Implementación, verificado)

**A. Estabilización del backend (ahora arranca).**
Corregidos los 5 bloqueantes de arranque. Verificación: `app.models` importa, `configure_mappers()` OK con **50 tablas**, y el **router completo importa con 115 rutas**; `app.main` instancia la app FastAPI "WMS Panamá".

**B. Reconciliación completa de Purchase Orders** (modelo ↔ schema ↔ repo), verificada construyendo objetos ORM y serializando `PurchaseOrderResponse` con líneas e historial. Se mantuvo estable el contrato del frontend (`unit_cost`, `expected_delivery_date`) usando alias Pydantic donde fue necesario.

**C. Brechas de OC cerradas (lo que pedía el brief):**

- **Edición de OC** (`PUT /inbound/purchase-orders/{id}`, solo en estado `DRAFT`): servicio `update_purchase_order`, repo `update_fields`, schema `PurchaseOrderUpdate`, y UI `POEditModal` + botón lápiz en el listado.
- **Historial de estados**: nuevo modelo `POStatusHistory` (tabla `po_status_history`) + repo `add_status_history`; se registra automáticamente en creación (→DRAFT), confirmación y cancelación; se expone en el detalle (`PurchaseOrderResponse.status_history`) y se muestra como línea de tiempo en `PODetailModal`.
- **Borrado lógico** (`DELETE /inbound/purchase-orders/{id}`, solo `DRAFT`/`CANCELLED`): servicio `delete_purchase_order`, repo `soft_delete` (marca `deleted_at`/`deleted_by`); `get_by_id`/`list` ahora filtran `deleted_at IS NULL`; UI con botón papelera + confirmación.

**D. Permisos alineados:** `seeds/run_all.py` ahora siembra todos los códigos que exigen los endpoints (incluidos los nuevos `inbound:po:update` e `inbound:po:delete`) y los roles del sistema se actualizaron en consecuencia.

**E. Pruebas:** 8 tests nuevos para la lógica de edición/borrado/historial (guardas de estado, registro de historial). Suite: **61 tests Inbound** y **202 tests en total** pasan. (1 fallo preexistente y ajeno en `test_security.py`, formato de API key — no tocado.) Frontend `tsc --noEmit` sale **0**.

### Trabajo pendiente recomendado (priorizado)

1. **Reconciliar ASN / GRN / QC / Putaway / RTV** igual que PO (mismos patrones de `created_by_id`, FKs de línea y campos schema↔modelo). Hasta hacerlo, esos flujos importan pero fallarán al crear registros.
2. **Arreglar el flujo de ajustes de inventario** (`InventoryAdjustment` está diseñado como una línea por ajuste, pero repo/servicio/schema lo tratan como cabecera+líneas; faltan `quantity_before/after` al crear). Se añadió el modelo `AdjustmentLine` faltante solo para desbloquear el import del que depende Inbound.
3. **Generar migraciones Alembic** del esquema actual (incluida `po_status_history`) y de los renombrados de columna, antes de cualquier despliegue.
4. **Añadir tests de integración con base de datos** (PostgreSQL de prueba) que ejerciten crear→confirmar→recibir→QC→putaway de punta a punta. Es la red de seguridad que falta.
5. Evidencias/adjuntos en Control de Calidad (si se habilita almacenamiento de archivos).

### Nota de Git

Trabajo en la rama `feature/inbound-module`. No se ejecutó `git pull origin main` porque el árbol tenía cambios sin commitear de la sesión previa y el push/pull requiere credenciales del usuario; la rama parte del estado local actual.
