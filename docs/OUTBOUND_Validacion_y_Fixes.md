# Outbound — Validación y correcciones (basado en evidencia)

**Proyecto:** WMS Panamá · **Rama:** `feature/inbound-module` · **Fecha:** 2026-06-02
**Método:** construcción real de ORM vía repos con sesión mockeada + serialización de cada `*Response`; verificación de las firmas de integración con `inspect.signature().bind()` y ejecución de `release_wave` con mocks.

> **Conclusión:** a diferencia de Inbound, las capas **modelo ↔ repo ↔ schema** de Outbound ya estaban alineadas (SO, Wave, Picking, Pack, Shipment, RMA crean y serializan sin errores). Los únicos defectos reales estaban en la **integración con InventoryService** dentro del servicio — el mismo tipo de bug que `receive_stock` en Inbound. Se corrigieron 3 llamadas.

## 1. Estado de create + serialize (verificado)
SO · Wave · PickingTask · PackTask · Shipment · ReturnOrder → todos construyen vía su repo y serializan su `*Response`. (Los defaults de columna se aplican en `flush`/BD; en runtime real no son `None`.)

## 2. Defectos corregidos (integración inventario)

1. **`confirm_sales_order` → `create_reservation`**: se llamaba con kwargs (`warehouse_id`, `uom_id`, `reference`...), pero la firma real es `create_reservation(body: InventoryReservationCreate)`. Ahora construye el `InventoryReservationCreate` (`reference_type="SO"`, `reference_id=so_id`, `reference_number=so.so_number`).
2. **`release_wave` → FEFO**: usaba `self.inv_service.inv_repo` (**no existe**; `AttributeError`) y leía claves `["available"]`/`["location_id"]`/`.get("batch_id")` inexistentes. Ahora usa `self.inv_service.levels.get_available_batches_fefo(tenant_id=..., ...)` y lee `alloc["quantity_to_use"]` + `alloc["level"].batch_id/location_id` (forma real `{level, batch, quantity_to_use}`).
3. **`complete_pick_task` → `pick_stock`**: se llamaba con kwargs inválidos (`location_id`/`uom_id`/`batch_id`/`reference`) y sin `warehouse_id`. Ahora usa la firma real: `pick_stock(warehouse_id, product_id, quantity, reference_type, reference_id, reference_number, force_location_id)`; `warehouse_id` se deriva de la SO y `force_location_id` fija la ubicación de la tarea.

## 3. Verificación
- `InventoryReservationCreate(...)` construye; `pick_stock`/`get_available_batches_fefo`/`create_reservation` aceptan los kwargs (bind de firma OK).
- `release_wave` ejecuta end-to-end con mocks y genera `tasks_data` con `from_location_id`/`batch_id` tomados de `level`.
- Router 115 rutas; suite **202 passed / 1 fallo preexistente y ajeno** (`test_security`); frontend `tsc --noEmit` exit 0.

## 4. Pendiente
- Migraciones Alembic (esquema acumulado de Inbound + Outbound).
- Tests de integración con BD real (cubrirían los flujos de inventario que aquí se verifican con mocks).
- Inventory: revisar flujo de ajustes (cabecera vs líneas).
