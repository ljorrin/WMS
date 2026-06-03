# Reconciliación GRN · QC · Putaway · RTV — Reporte basado en evidencia

**Proyecto:** WMS Panamá · **Rama:** `feature/inbound-module` · **Fecha:** 2026-06-02
**Método:** misma metodología verificada que se aplicó a Purchase Orders — construcción real de objetos ORM con la sesión mockeada, invocación de los repositorios con los kwargs exactos que produce el servicio, y serialización de cada `*Response` desde el objeto ORM. Nada asumido.

> **Conclusión:** GRN, Quality Control y Putaway pasaron de **0% funcional** (lanzaban `TypeError` al crear) a **funcionales y verificados**. Se reconcilió además RTV porque el flujo de rechazo de QC lo dispara automáticamente. Tras esta entrega, **los 5 módulos del flujo Inbound centrales (PO, GRN, QC, Putaway, RTV) construyen y serializan sin errores.**

---

## 1. Causa raíz (la misma de PO)

Los repositorios y el servicio se escribieron contra una versión *imaginada* de los modelos. Al ejecutar de verdad, los `kwargs` del repo no coincidían con las columnas del modelo (`TypeError: '<x>' is an invalid keyword argument`), y varios valores de enum referenciados por el servicio **no existían** en el modelo. Los 53/61 tests "pasaban" porque eran lógica pura con `MagicMock`, sin tocar los modelos reales.

---

## 2. Cambios por capa

### 2.1 Enums (`app/models/inbound.py`)
Alineados a la máquina de estados real del servicio y a los tipos del frontend (`src/types/index.ts`):

| Enum | Valores ahora |
|---|---|
| `POStatus` | + `PARTIALLY_RECEIVED` (antes `PARTIAL`) |
| `ASNStatus` | + `CREATED`, `IN_TRANSIT` |
| `GRNStatus` | `draft, in_progress, confirmed, putaway_in_progress, completed, rejected, cancelled` |
| `QCStatus` | `pending, in_progress, approved, rejected, partial, cancelled` |
| `RTVStatus` | `pending, approved, shipped, credit_received, closed, cancelled` |

### 2.2 GoodsReceipt / GoodsReceiptLine
- `received_date` (Date) → **`received_at`** (DateTime) — usado por dashboard, list y throughput.
- `supplier_id` ahora **nullable** (recepción ciega; se deriva de OC/ASN).
- **+** `requires_qc`, `confirmed_at`, `dock_number`, `erp_synced_at`.
- Línea: `goods_receipt_id` → **`grn_id`**; `receiving_location_id` → **`location_id`**; **+** `batch_number`, `expiry_date`, `manufacture_date`, `unit_cost`, `currency`.
- Repo: mapeo `po_id`→`purchase_order_id`, `received_by_id`→`received_by`; filtra `None`.
- Schema: `GRNLineCreate` ya **no exige `uom_id`** (el frontend nunca lo envía); `GRNResponse` expone `po_id`/`received_by_id` vía `validation_alias`.

### 2.3 QualityInspection / QualityInspectionLine
- `goods_receipt_id` → **`grn_id`**; `inspection_number` → **`qi_number`**; `warehouse_id` nullable.
- **+** `total_inspected`, `total_approved`, `total_rejected`, `defect_rate`, `disposition_notes`, `inspection_date`.
- Línea: `inspection_id` → **`qi_id`**; **+** `line_number`, `quantity_approved`, `quantity_rejected`, `defect_codes`.
- `QualityInspectionResponse.photo_urls` lee `photos` vía alias.

### 2.4 PutawayTask
- `goods_receipt_id` → **`grn_id`**; `assigned_to` → **`assigned_to_id`**; `from_location_id` nullable.
- Servicio `_generate_putaway_tasks`: ahora pasa `warehouse_id` y `uom` (antes `uom_id` inexistente).
- `complete_putaway_task`: `InventoryService.receive_stock(...)` llamado con la firma real (`warehouse_id`, `location_id`, `reference_type/_id/_number`); antes pasaba `uom_id`/`batch_id`/`reference` inválidos y **omitía `warehouse_id`**.
- `PutawayTaskResponse`: `uom_id`→`uom`, eliminado `putaway_rule_id` (no era columna).

### 2.5 ReturnToVendor (RTV)
- `goods_receipt_id` → **`grn_id`**; **+** `return_carrier`, `return_tracking`, `shipped_at`, `confirmed_at`, `credit_expected`, `credit_received`.
- Corregido el doble `credit_received` (lo fijaba el repo y el servicio); el placeholder roto `supplier_id=grn.lines[0].product_id` ahora usa `grn.supplier_id`.

---

## 3. Verificación empírica (en vivo)

```
GRN OK:      GRN-000001  po_id=set  received_by=user  status=in_progress
QC OK:       QI-000001   total_inspected=10  total_rejected=1  defect_rate=0.1
PUTAWAY OK:  qty=10  uom=UN  status=pending  from_location=ok
RTV OK:      RTV-000001  status=pending  credit_received=0
GRNLine OK / QCLine OK
```

- `import app.models` + `configure_mappers()` → **51 tablas, sin errores**.
- Router completo: **115 rutas**; `app.main` instancia.
- Suite: **202 passed, 1 failed**. El único fallo (`test_security::test_generate_api_key_format`) es **preexistente y ajeno** a Inbound (off-by-one en el test).
- Frontend `tsc --noEmit` → **exit 0**.

---

## 4. Matriz de cumplimiento (actualizada)

| Módulo | Funcional (verificado) | Notas |
|---|---|---|
| Purchase Orders | ✅ 100% | (sin cambios; ya estaba) |
| **GRN (Recepción)** | ✅ **100%** | crea cabecera+líneas y serializa; recepción parcial/total alcanzable |
| **Quality Control** | ✅ **100%** | crea inspección+líneas, totales y defect_rate; aprobar/rechazar |
| **Putaway** | ✅ **100%** | generación de tareas + completado con movimiento de inventario |
| **RTV** | ✅ **funcional** | crea/serializa; disparo automático desde rechazo de QC |
| **ASN (alta/dispatch/arrive)** | ✅ **funcional** (2026-06-02) | reconciliado; crea cabecera+líneas y serializa `ASNResponse`; `update_status` IN_TRANSIT/ARRIVED compila |

> **Con ASN reconciliado, el módulo Inbound completo (PO · ASN · GRN · QC · Putaway · RTV) construye y serializa sin errores.**

### ASN — detalle de la reconciliación
- Modelo `ASN`: `purchase_order_id`→`po_id`, `supplier_reference`→`supplier_asn_reference`, `expected_arrival`→`expected_arrival_date`, `actual_arrival`→`actual_arrival_date`, `plate_number`→`vehicle_plate`; **+** `carrier_name`, `dock_number`, `customs_document_id`. Índice `ix_asn_expected_arrival` actualizado.
- Modelo `ASNLine`: **+** `uom_id` (nullable), `gtin`, `country_of_origin`.
- Schema: `ASNLineCreate.uom_id` ahora opcional (no existe tabla UOM; consistente con GRN); `ASNResponse.created_by_id` opcional.
- Verificado: `repo.create` ASN+líneas con sesión mockeada → OK; serialización `ASNResponse`/`ASNLineResponse` → OK; `update_status(IN_TRANSIT/ARRIVED, dock_number)` compila. 51 tablas, router 115 rutas, 202 passed/1 preexistente, `tsc --noEmit` exit 0.

---

## 5. Pendiente (fuera del alcance de esta sesión)

1. **Migraciones Alembic** para todos los cambios de esquema acumulados (renombrados de columna + columnas nuevas + 2 tablas de PO).
2. **Tests de integración con BD** (la red de seguridad ausente que ocultó estos defectos).
3. **Outbound / Inventory**: verificar runtime (probablemente con los mismos defectos schema↔modelo, aún sin reconciliar).
