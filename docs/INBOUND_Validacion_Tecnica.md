# Validación técnica del módulo Inbound — Reporte basado en evidencia

**Proyecto:** WMS Panamá · **Rama:** `feature/inbound-module` · **Fecha:** 2026-06-01
**Método:** análisis del patch + ejecución real de Python (construcción de objetos ORM, invocación de repositorios con sesión mockeada, comparación schema↔columnas). Nada asumido.

> **Conclusión principal (sin rodeos):** de los 4 módulos solicitados, **solo Purchase Orders quedó realmente desarrollado y funcional**. GRN, Quality Control y Putaway **existen como código pero NO son funcionales**: su creación falla en tiempo de ejecución con `TypeError` por desalineación schema↔modelo (el mismo defecto que tenía PO antes de reconciliarlo). No fueron reconciliados en esta entrega.

---

## 1. Inventario de cambios (evidencia: `git diff --stat`, `wc -l`)

### Archivos modificados (20 · +632 / −74 líneas)

| Archivo | Δ |
|---|---|
| wms-backend/app/api/v1/endpoints/inbound.py | +45 |
| wms-backend/app/api/v1/router.py | +3/−1 |
| wms-backend/app/models/__init__.py | +25 |
| wms-backend/app/models/ai.py | +2/−1 |
| wms-backend/app/models/base.py | +4/−2 |
| wms-backend/app/models/core.py | +4/−2 |
| wms-backend/app/models/inbound.py | +67 |
| wms-backend/app/models/inventory.py | +53 |
| wms-backend/app/models/outbound.py | +2/−1 |
| wms-backend/app/repositories/inbound.py | +93 |
| wms-backend/app/repositories/inventory.py | +4 |
| wms-backend/app/schemas/inbound.py | +77 |
| wms-backend/app/services/inbound_service.py | +55 |
| wms-backend/app/services/inventory_service.py | +7 |
| wms-backend/seeds/run_all.py | +30 |
| wms-backend/tests/unit/test_inbound_service.py | +96 |
| wms-frontend/src/api/endpoints.ts | +19 |
| wms-frontend/src/pages/inbound/GRNListPage.tsx | +19 |
| wms-frontend/src/pages/inbound/POListPage.tsx | +50 |
| wms-frontend/src/types/index.ts | +51 |

### Archivos nuevos (9 · ~1.074 líneas)

`docs/INBOUND_Analisis_y_Plan.md` (113), `wms-backend/app/api/v1/endpoints/master_data.py` (175), `wms-frontend/src/components/ui/Combobox.tsx` (93), `…/Select.tsx` (40), `…/inbound/GRNDetailModal.tsx` (83), `GRNFormModal.tsx` (203), `PODetailModal.tsx` (108), `POEditModal.tsx` (81), `POFormModal.tsx` (178).

> Nota de procedencia: `master_data.py`, `Combobox`, `Select`, `GRNDetailModal`, `GRNFormModal`, `PODetailModal`, `POFormModal` provienen de una sesión previa; en esta sesión se crearon `POEditModal.tsx` y el documento de análisis, y se modificaron el resto.

### Archivos eliminados
**Ninguno** (`git diff --diff-filter=D` vacío).

### Migraciones agregadas
**Ninguna.** `alembic/versions/` está vacío/ausente; el esquema se materializa por `create_all`. **Riesgo:** los renombrados de columna y las 2 tablas nuevas (abajo) requieren migración antes de cualquier despliegue.

### Cambios de base de datos (modelos)
- **Tabla nueva** `po_status_history` (historial de estados de OC).
- **Tabla nueva** `inventory_adjustment_lines` (modelo `AdjustmentLine`, faltaba; se añadió solo para desbloquear el import del que depende Inbound).
- **Renombrados base (afectan TODAS las tablas):** `created_by`→`created_by_id`, `updated_by`→`updated_by_id`.
- **Renombrados/altas en `purchase_orders`:** `expected_date`→`expected_delivery_date`, `erp_po_number`→`erp_reference`, `erp_sync_at`→`erp_synced_at`, **+**`supplier_po_reference`, **+**`closed_date`.
- **Columnas renombradas (atributo Python, col física = "metadata"):** `AuditLog.metadata`→`event_metadata`, `InventoryMovement.metadata`→`movement_metadata`.

### Endpoints (evidencia: decoradores en `inbound.py`)
- **Nuevos:** `PUT /inbound/purchase-orders/{id}` (editar), `DELETE /inbound/purchase-orders/{id}` (borrado lógico).
- **Sin cambios funcionales:** los ~29 endpoints restantes de Inbound (ASN, GRN, QC, Putaway, RTV, dashboard) ya existían; solo se volvieron *importables* gracias a los arreglos de arranque.
- El router completo importa: **115 rutas** (antes: el backend no importaba en absoluto).

### Componentes frontend
- **Nuevo (esta sesión):** `POEditModal.tsx`.
- **Modificados:** `POListPage.tsx` (botones editar/eliminar), `PODetailModal` (timeline de historial), `types/index.ts` (+`POStatusHistory`, +`PurchaseOrderUpdate`, campos de cabecera), `endpoints.ts` (+`updatePO`, +`deletePO`).
- Frontend `tsc --noEmit` = **0**.

### Modelos / servicios / repositorios afectados
- **Modelos:** base, core, inventory, inbound, outbound, ai (arreglos de import/columnas) + `POStatusHistory` y `AdjustmentLine` nuevos.
- **Repositorios:** `inbound` (PO: mapeo de líneas, soft-delete, historial, update) e `inventory` (created_by_id).
- **Servicios:** `inbound_service` (update/delete PO + registro de historial), `inventory_service` (imports).

---

## 2. Estado por módulo (con evidencia)

### 2.1 Purchase Orders — **FUNCIONAL ✅**
- **Implementado y verificado:** listado, creación, detalle, **edición (DRAFT)**, confirmar, cancelar, **borrado lógico (DRAFT/CANCELLED)**, **historial de estados**, validaciones, relación con proveedor, líneas.
- **Evidencia en vivo:** `PurchaseOrderRepository.create(...)` con sesión mockeada → **OK**. Serialización `PurchaseOrderResponse` con líneas + historial → **OK**. Diff schema↔columnas → **0 mismatches**.
- **Pendiente:** edición de *líneas* (solo se editan campos de cabecera); generar migración para las columnas nuevas.
- **Riesgo:** bajo. El borrado lógico filtra `deleted_at IS NULL` solo en PO (correcto para PO).

### 2.2 GRN (Recepción) — **NO FUNCIONAL ❌**
- **Código presente:** endpoints (crear/listar/detalle/confirmar), lógica de recepción parcial/total, validación vs OC, generación de putaway, frontend (`GRNListPage`/`GRNFormModal`/`GRNDetailModal`).
- **Evidencia de fallo (en vivo):** `GRNRepository.create(...)` → **`TypeError: 'received_by_id' is an invalid keyword argument for GoodsReceipt'`**. El modelo tiene `received_by`/`received_date`, no `received_by_id`/`received_at`.
- **Diff schema↔modelo:** cabecera sobra `dock_number`, `po_id`; **línea** sobra `batch_number`, `currency`, `expiry_date`, `location_id`, `manufacture_date`, `unit_cost`, `uom_id` → todos `TypeError`.
- **Conclusión:** **no se puede crear ninguna recepción.** Recepción parcial/total, diferencias de cantidad y movimientos de inventario están **codificados pero son inalcanzables**.
- **Pendiente:** reconciliar `GRNCreate`/`GRNLineCreate` ↔ `GoodsReceipt`/`GoodsReceiptLine` y los kwargs del repo (igual que se hizo en PO).

### 2.3 Quality Control — **NO FUNCIONAL ❌**
- **Código presente:** endpoints crear/listar pendientes/detalle/resolver (aprobar/rechazar/disposición), frontend `QualityPage`.
- **Evidencia de fallo:** diff schema↔modelo → cabecera `QualityInspectionCreate` pasa `grn_id` que **no es columna** de `QualityInspection` (y el repo lo pasa explícito) → `TypeError`; **línea** `QCLineCreate` sobra `defect_codes`, `notes`, `quantity_approved`, `quantity_rejected` → `TypeError`.
- **Conclusión:** **no se puede crear ninguna inspección.** Aprobación/rechazo/parcial existen en código pero son inalcanzables.
- **Pendiente:** reconciliar QC schema↔modelo + kwargs del repo.

### 2.4 Putaway — **NO FUNCIONAL (inalcanzable) ❌**
- **Código presente:** listar/detalle/iniciar/completar, generación de tareas (`create_bulk`), y `complete_putaway_task` llama a `InventoryService.receive_stock` para mover inventario.
- **Por qué no funciona:** las tareas de putaway **solo se generan dentro de** `confirm_grn`/`resolve_quality_inspection`, que pertenecen a flujos que **fallan al crear GRN/QC**. Sin GRN/QC funcionales, **nunca se generan tareas de putaway**.
- **Conclusión:** inalcanzable end-to-end. No verificable hasta arreglar GRN y QC.

---

## 3. Matriz de cumplimiento

"Código presente" = existe la implementación. "Funcional (verificado)" = se ejecuta sin romper, comprobado empíricamente.

| Módulo | Código presente | Funcional (verificado) | Notas |
|---|---|---|---|
| **Purchase Orders** | 100 % | **100 %** | + edición/historial/borrado lógico nuevos |
| **GRN (Recepción)** | ~85 % | **0 %** | `create` lanza `TypeError`; flujo bloqueado |
| **Quality Control** | ~85 % | **0 %** | `create` lanza `TypeError`; flujo bloqueado |
| **Putaway** | ~75 % | **0 %** | inalcanzable: depende de GRN/QC |
| **Cumplimiento global Inbound** | ~86 % | **~25 %** | solo 1 de 4 módulos funcional |

> La pregunta de fondo —¿los 4 módulos fueron desarrollados y no solo documentados?— se responde con evidencia: **solo Purchase Orders está desarrollado y funcional.** Los otros tres están escritos pero **rotos en ejecución** y no fueron reconciliados en esta entrega.

---

## 4. Resumen técnico

- **Líneas agregadas:** ~632 (tracked) + ~1.074 (archivos nuevos) ≈ **1.706**. **Eliminadas:** ~74.
- **Base de datos:** 2 tablas nuevas (`po_status_history`, `inventory_adjustment_lines`); renombrado global `created_by`/`updated_by`→`*_id`; 5 cambios de columna en `purchase_orders`; 2 columnas `metadata` renombradas a nivel de atributo. **0 migraciones** (pendiente).
- **Backend:** estabilizado (de "no importa" a router con 115 rutas y `app.main` instanciable); PO reconciliado y con 3 features nuevas; 8 tests nuevos.
- **Frontend:** edición/borrado/historial de OC; `tsc` limpio.
- **Permisos/seguridad:** `seeds/run_all.py` ahora siembra todos los códigos exigidos por endpoints (faltaban `po:confirm/cancel`, `grn:read/confirm`, `qc:create/resolve`, `putaway:manage`, `rtv:*`) + nuevos `po:update`/`po:delete`; roles actualizados. (Esto era una causa real de "los menús no hacían nada" para no-superadmin.)

---

## 5. Verificación de funcionalidades concretas (item 6 del pedido)

| Funcionalidad | ¿Implementación funcional? | Evidencia |
|---|---|---|
| Recepción parcial | ❌ No | lógica en `inbound_service`, pero `GRNRepository.create` lanza `TypeError` → inalcanzable |
| Recepción total | ❌ No | igual que arriba |
| Historial de estados | ✅ Sí, **solo PO** | `POStatusHistory` + `add_status_history` en create/confirm/cancel; mostrado en `PODetailModal`. No existe para GRN/QC/Putaway |
| Borrado lógico | ✅ Sí, **solo PO** | `soft_delete` + filtro `deleted_at IS NULL` + `DELETE` endpoint. No existe para GRN/QC/Putaway |
| Control de calidad | ❌ No | `QualityInspectionCreate`/`QCLineCreate` desalineados → `TypeError` al crear |
| Tareas de Putaway | ❌ No | se generan solo dentro de GRN/QC (rotos) → nunca se crean |
| Gestión de ubicaciones | ⚠️ Solo lectura | `master_data.py` expone ubicaciones **read-only**; no hay alta/edición de ubicaciones |
| Movimientos de inventario | ⚠️ Parcial/no verificado | `complete_putaway_task`→`InventoryService.receive_stock` existe, pero es inalcanzable vía Inbound; el módulo de inventario tiene sus propios defectos (p. ej. flujo de ajustes cabecera/líneas) |

---

## 6. Qué falta explícitamente (para cerrar el alcance de los 4 módulos)

1. **GRN:** reconciliar `GoodsReceipt`/`GoodsReceiptLine` ↔ schemas y kwargs del repo (`received_by_id`→`received_by`, `received_at`→`received_date`; línea: `unit_cost`→columna real, `uom_id`/`location_id`/`batch_number`/`expiry_date`/`manufacture_date`/`currency`, `grn_id`→`goods_receipt_id`). Sin esto no hay recepciones.
2. **QC:** reconciliar `QualityInspection`/`QualityInspectionLine` (`grn_id`, `defect_codes`, `notes`, `quantity_approved/rejected`, `inspection_id`). Sin esto no hay inspecciones.
3. **Putaway:** validar tras arreglar GRN/QC; revisar que `tasks_data` del servicio coincida con columnas de `PutawayTask` (`assigned_to`, `goods_receipt_id`, `grn_line_id`, `suggested_location_id`).
4. **Inventario:** corregir flujo de ajustes (cabecera vs líneas) y verificar `receive_stock` end-to-end.
5. **Migraciones Alembic** para todos los cambios de esquema + **tests de integración con BD** (la red de seguridad ausente que ocultó todos estos defectos).

---

## 7. Recomendación

**No marcar el módulo Inbound como completo.** Solo Purchase Orders cumple el alcance y está verificado. Antes de cualquier push/PR que pretenda cerrar "Inbound", deben reconciliarse y verificarse GRN, QC y Putaway con la misma metodología aplicada a PO. El patch actual es un avance sólido (backend que arranca + PO funcional + permisos), pero **cubre 1 de los 4 módulos**.
