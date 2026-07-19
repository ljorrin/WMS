"""
WMS Panama — Registro de herramientas (tools) del Asistente IA — Fase 5
==========================================================================
Define las acciones reales que el asistente puede invocar via tool-calling
(function calling) del LLM. Cada tool ejecuta contra los servicios/repos
reales del WMS (las mismas rutas que ya usan los endpoints REST) — no hay
"herramientas" que devuelvan datos inventados.

Seguridad: cada tool declara el permiso WMS que su acción requiere. La
ejecucion verifica ese permiso contra los permisos reales del usuario que
inicio la conversacion (los mismos que llevan sus tokens JWT) antes de
tocar la base de datos — el asistente nunca puede hacer algo que el
usuario mismo no podria hacer por la UI/API.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ToolContext:
    db: AsyncSession
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    permissions: frozenset[str] = field(default_factory=frozenset)
    is_superadmin: bool = False

    def has_permission(self, code: Optional[str]) -> bool:
        if code is None or self.is_superadmin:
            return True
        return code in self.permissions


ToolHandler = Callable[[ToolContext, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class AgentTool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema (formato OpenAI function-calling)
    handler: ToolHandler
    permission: Optional[str] = None  # None = solo requiere ai:assistant:use (ya validado en el endpoint)

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ── Handlers ─────────────────────────────────────────────────────────────────

async def _get_stock_summary(ctx: ToolContext, args: dict) -> dict:
    from sqlalchemy import and_, func, select

    from app.models.inventory import InventoryLevel
    from app.models.master_data import Product

    query = args.get("product_query")
    conditions = [InventoryLevel.tenant_id == ctx.tenant_id]

    if query:
        prod_rows = (await ctx.db.execute(
            select(Product.id, Product.sku, Product.name).where(and_(
                Product.tenant_id == ctx.tenant_id,
                Product.deleted_at.is_(None),
                (Product.sku.ilike(f"%{query}%") | Product.name.ilike(f"%{query}%")),
            )).limit(5)
        )).all()
        if not prod_rows:
            return {"found": False, "message": f"No se encontró ningún producto que coincida con '{query}'."}
        product_ids = [r.id for r in prod_rows]
        conditions.append(InventoryLevel.product_id.in_(product_ids))

        results = []
        for prod in prod_rows:
            agg = (await ctx.db.execute(
                select(
                    func.coalesce(func.sum(InventoryLevel.quantity_available), 0),
                    func.coalesce(func.sum(InventoryLevel.quantity_reserved), 0),
                    func.count(InventoryLevel.id),
                ).where(and_(
                    InventoryLevel.tenant_id == ctx.tenant_id,
                    InventoryLevel.product_id == prod.id,
                ))
            )).one()
            results.append({
                "sku": prod.sku, "name": prod.name,
                "quantity_available": float(agg[0] or 0),
                "quantity_reserved": float(agg[1] or 0),
                "locations_count": agg[2] or 0,
            })
        return {"found": True, "products": results}

    row = (await ctx.db.execute(
        select(
            func.coalesce(func.sum(InventoryLevel.quantity_available), 0),
            func.coalesce(func.sum(InventoryLevel.quantity_reserved), 0),
            func.count(InventoryLevel.id),
        ).where(and_(*conditions))
    )).one()
    return {
        "total_available": float(row[0] or 0),
        "total_reserved": float(row[1] or 0),
        "locations_count": row[2] or 0,
    }


_DASHBOARD_MODULE_PERMISSIONS = {
    "inbound": "inbound:po:read",
    "outbound": "outbound:so:read",
    "inventory": "inventory:read",
    "labor": "labor:read",
    "slotting": "slotting:read",
    "streaming": "outbound:order:read",
}


async def _get_dashboard_kpis(ctx: ToolContext, args: dict) -> dict:
    module = args.get("module", "inbound")
    warehouse_id = _parse_uuid(args.get("warehouse_id"))

    required_permission = _DASHBOARD_MODULE_PERMISSIONS.get(module)
    if not ctx.has_permission(required_permission):
        return {"ok": False, "error": f"Permiso denegado: se requiere '{required_permission}' para ver KPIs de '{module}'."}

    if module == "outbound":
        from app.services.outbound_service import OutboundService
        return await OutboundService(ctx.db, ctx.tenant_id, ctx.user_id).get_dashboard_metrics(warehouse_id)
    if module == "inventory":
        from app.services.inventory_service import InventoryService
        return await InventoryService(ctx.db, ctx.tenant_id, ctx.user_id).get_dashboard_metrics(warehouse_id)
    if module == "labor":
        from app.services.labor_service import LaborService
        return await LaborService(ctx.db).get_dashboard_metrics(ctx.tenant_id, warehouse_id)
    if module == "slotting":
        from app.services.slotting_service import SlottingService
        return await SlottingService(ctx.db).get_dashboard_metrics(ctx.tenant_id, warehouse_id)
    if module == "streaming":
        from app.services.streaming_service import StreamingService
        return await StreamingService(ctx.db).get_metrics(ctx.tenant_id, warehouse_id)

    from app.services.inbound_service import InboundService
    return await InboundService(ctx.db, ctx.tenant_id, ctx.user_id).get_dashboard_metrics(warehouse_id)


async def _list_active_alerts(ctx: ToolContext, args: dict) -> dict:
    from sqlalchemy import and_, select

    from app.models.ai import ReplenishmentAlert

    rows = (await ctx.db.execute(
        select(ReplenishmentAlert).where(and_(
            ReplenishmentAlert.tenant_id == ctx.tenant_id,
            ReplenishmentAlert.is_resolved == False,  # noqa: E712
        )).order_by(ReplenishmentAlert.created_at.desc()).limit(10)
    )).scalars().all()
    return {"count": len(rows), "alerts": [
        {"id": str(a.id), "title": a.title, "severity": a.severity.value,
         "product_id": str(a.product_id), "recommendation": a.recommendation}
        for a in rows
    ]}


async def _list_open_anomalies(ctx: ToolContext, args: dict) -> dict:
    from app.services.ai.anomaly import AnomalyDetector

    svc = AnomalyDetector(ctx.db, ctx.tenant_id, ctx.user_id)
    result = await svc.get_anomalies(is_resolved=False, page=1, page_size=10)
    return {"count": result["total"], "anomalies": [
        {"id": str(a.id), "type": a.anomaly_type.value if hasattr(a.anomaly_type, "value") else a.anomaly_type,
         "severity": a.severity.value if hasattr(a.severity, "value") else a.severity,
         "description": a.description}
        for a in result["items"]
    ]}


async def _resolve_anomaly(ctx: ToolContext, args: dict) -> dict:
    from app.services.ai.anomaly import AnomalyDetector

    anomaly_id = _parse_uuid(args.get("anomaly_id"))
    if not anomaly_id:
        return {"ok": False, "error": "anomaly_id inválido o no provisto."}

    svc = AnomalyDetector(ctx.db, ctx.tenant_id, ctx.user_id)
    await svc.resolve_anomaly(
        anomaly_id=anomaly_id,
        is_false_positive=bool(args.get("is_false_positive", False)),
        resolution_notes=str(args.get("resolution_notes", "Resuelto por el Asistente IA")),
    )
    return {"ok": True, "anomaly_id": str(anomaly_id)}


async def _resolve_replenishment_alert(ctx: ToolContext, args: dict) -> dict:
    from sqlalchemy import and_, update

    from app.models.ai import ReplenishmentAlert

    alert_id = _parse_uuid(args.get("alert_id"))
    if not alert_id:
        return {"ok": False, "error": "alert_id inválido o no provisto."}

    result = await ctx.db.execute(
        update(ReplenishmentAlert)
        .where(and_(
            ReplenishmentAlert.id == alert_id,
            ReplenishmentAlert.tenant_id == ctx.tenant_id,
        ))
        .values(
            is_resolved=True,
            resolved_at=datetime.now(timezone.utc),
            resolved_by_id=ctx.user_id,
            action_taken=str(args.get("action_taken", "Resuelto por el Asistente IA")),
        )
    )
    if result.rowcount == 0:
        return {"ok": False, "error": f"No se encontró la alerta {alert_id}."}
    return {"ok": True, "alert_id": str(alert_id)}


async def _suggest_next_labor_task(ctx: ToolContext, args: dict) -> dict:
    from app.services.labor_service import LaborService

    warehouse_id = _parse_uuid(args.get("warehouse_id"))
    if not warehouse_id:
        return {"ok": False, "error": "warehouse_id inválido o no provisto."}

    svc = LaborService(ctx.db)
    task = await svc.suggest_next_task(ctx.tenant_id, warehouse_id, args.get("zone"))
    if task is None:
        return {"ok": True, "found": False, "message": "No hay tareas pendientes en esta bodega."}
    return {"ok": True, "found": True, "task": _labor_task_to_dict(task)}


async def _assign_next_labor_task(ctx: ToolContext, args: dict) -> dict:
    from app.services.labor_service import LaborService

    warehouse_id = _parse_uuid(args.get("warehouse_id"))
    operator_id = _parse_uuid(args.get("operator_id"))
    if not warehouse_id or not operator_id:
        return {"ok": False, "error": "warehouse_id y operator_id son requeridos y deben ser UUID válidos."}

    svc = LaborService(ctx.db)
    task = await svc.assign_next_task(ctx.tenant_id, warehouse_id, operator_id, args.get("zone"))
    if task is None:
        return {"ok": True, "found": False, "message": "No había tareas pendientes para asignar."}
    return {"ok": True, "found": True, "task": _labor_task_to_dict(task)}


def _labor_task_to_dict(task) -> dict:
    return {
        "id": str(task.id), "activity_type": task.activity_type, "status": task.status,
        "quantity": float(task.quantity) if task.quantity is not None else None,
        "assigned_to_id": str(task.user_id) if task.user_id else None,
    }


def _parse_uuid(value: Any) -> Optional[uuid.UUID]:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


def _num(v: Any) -> Optional[float]:
    return float(v) if v is not None else None


def _page(items: list[dict], total: int) -> dict:
    return {"total": total, "count": len(items), "items": items}


# ── Inbound: consultas ────────────────────────────────────────────────────────

async def _list_purchase_orders(ctx: ToolContext, args: dict) -> dict:
    from app.services.inbound_service import InboundService

    svc = InboundService(ctx.db, ctx.tenant_id, ctx.user_id)
    rows, total = await svc.po_repo.list(
        warehouse_id=_parse_uuid(args.get("warehouse_id")), status=args.get("status"),
        search=args.get("search"), page=1, page_size=8,
    )
    return _page([{
        "id": str(po.id), "po_number": po.po_number, "status": po.status.value,
        "supplier_id": str(po.supplier_id), "order_date": str(po.order_date),
        "expected_delivery_date": str(po.expected_delivery_date) if po.expected_delivery_date else None,
        "total_amount": _num(po.total_amount), "currency": po.currency,
    } for po in rows], total)


async def _list_grns(ctx: ToolContext, args: dict) -> dict:
    from app.services.inbound_service import InboundService

    svc = InboundService(ctx.db, ctx.tenant_id, ctx.user_id)
    rows, total = await svc.grn_repo.list(
        warehouse_id=_parse_uuid(args.get("warehouse_id")), status=args.get("status"), page=1, page_size=8,
    )
    return _page([{
        "id": str(g.id), "grn_number": g.grn_number, "status": g.status.value,
        "requires_qc": g.requires_qc, "received_at": str(g.received_at) if g.received_at else None,
    } for g in rows], total)


async def _list_quality_inspections(ctx: ToolContext, args: dict) -> dict:
    from app.services.inbound_service import InboundService

    svc = InboundService(ctx.db, ctx.tenant_id, ctx.user_id)
    rows, total = await svc.qi_repo.list(
        warehouse_id=_parse_uuid(args.get("warehouse_id")), status=args.get("status"), page=1, page_size=8,
    )
    return _page([{
        "id": str(qi.id), "qi_number": qi.qi_number, "status": qi.status.value,
        "defect_rate": _num(qi.defect_rate), "disposition": qi.disposition,
    } for qi in rows], total)


async def _list_putaway_tasks(ctx: ToolContext, args: dict) -> dict:
    from app.services.inbound_service import InboundService

    svc = InboundService(ctx.db, ctx.tenant_id, ctx.user_id)
    rows, total = await svc.putaway_repo.list(status=args.get("status"), page=1, page_size=8)
    return _page([{
        "id": str(t.id), "product_id": str(t.product_id), "quantity": _num(t.quantity),
        "status": t.status.value, "priority": t.priority,
        "suggested_location_code": getattr(t, "suggested_location_code", None),
    } for t in rows], total)


async def _list_rtvs(ctx: ToolContext, args: dict) -> dict:
    from app.services.inbound_service import InboundService

    svc = InboundService(ctx.db, ctx.tenant_id, ctx.user_id)
    rows, total = await svc.rtv_repo.list(status=args.get("status"), page=1, page_size=8)
    return _page([{
        "id": str(r.id), "rtv_number": r.rtv_number, "status": r.status.value,
        "reason": r.reason, "credit_expected": _num(r.credit_expected),
    } for r in rows], total)


# ── Outbound: consultas ────────────────────────────────────────────────────────

async def _list_sales_orders(ctx: ToolContext, args: dict) -> dict:
    from app.services.outbound_service import OutboundService

    svc = OutboundService(ctx.db, ctx.tenant_id, ctx.user_id)
    rows, total = await svc.so_repo.list(
        warehouse_id=_parse_uuid(args.get("warehouse_id")), status=args.get("status"),
        search=args.get("search"), page=1, page_size=8,
    )
    return _page([{
        "id": str(so.id), "so_number": so.so_number, "status": so.status.value,
        "customer_id": str(so.customer_id), "priority": so.priority,
        "total_amount": _num(so.total_amount), "requested_delivery_date":
            str(so.requested_delivery_date) if so.requested_delivery_date else None,
    } for so in rows], total)


async def _list_picking_waves(ctx: ToolContext, args: dict) -> dict:
    from app.services.outbound_service import OutboundService

    svc = OutboundService(ctx.db, ctx.tenant_id, ctx.user_id)
    rows, total = await svc.wave_repo.list(
        status=args.get("status"), warehouse_id=_parse_uuid(args.get("warehouse_id")), page=1, page_size=8,
    )
    return _page([{
        "id": str(w.id), "wave_number": w.wave_number, "status": w.status.value,
        "total_orders": w.total_orders, "total_lines": w.total_lines,
    } for w in rows], total)


async def _list_picking_tasks(ctx: ToolContext, args: dict) -> dict:
    from app.services.outbound_service import OutboundService

    svc = OutboundService(ctx.db, ctx.tenant_id, ctx.user_id)
    rows, total = await svc.pick_repo.list(
        wave_id=_parse_uuid(args.get("wave_id")), status=args.get("status"), page=1, page_size=8,
    )
    return _page([{
        "id": str(t.id), "so_id": str(t.so_id), "status": t.status.value,
        "quantity_requested": _num(t.quantity_requested), "quantity_picked": _num(t.quantity_picked),
        "product_name": getattr(t, "product_name", None),
    } for t in rows], total)


async def _list_pack_tasks(ctx: ToolContext, args: dict) -> dict:
    from app.services.outbound_service import OutboundService

    svc = OutboundService(ctx.db, ctx.tenant_id, ctx.user_id)
    rows, total = await svc.pack_repo.list(status=args.get("status"), page=1, page_size=8)
    return _page([{
        "id": str(t.id), "pack_task_number": t.pack_task_number, "status": t.status.value,
        "box_count": t.box_count, "so_number": getattr(t, "so_number", None),
    } for t in rows], total)


async def _list_shipments(ctx: ToolContext, args: dict) -> dict:
    from app.services.outbound_service import OutboundService

    svc = OutboundService(ctx.db, ctx.tenant_id, ctx.user_id)
    rows, total = await svc.ship_repo.list(
        status=args.get("status"), warehouse_id=_parse_uuid(args.get("warehouse_id")), page=1, page_size=8,
    )
    return _page([{
        "id": str(s.id), "shipment_number": s.shipment_number, "status": s.status.value,
        "carrier_name": s.carrier_name, "tracking_number": s.tracking_number,
        "estimated_delivery": str(s.estimated_delivery) if s.estimated_delivery else None,
    } for s in rows], total)


async def _list_returns(ctx: ToolContext, args: dict) -> dict:
    from app.services.outbound_service import OutboundService

    svc = OutboundService(ctx.db, ctx.tenant_id, ctx.user_id)
    rows, total = await svc.rma_repo.list(status=args.get("status"), page=1, page_size=8)
    return _page([{
        "id": str(r.id), "rma_number": r.rma_number, "status": r.status.value,
        "reason": r.reason, "refund_amount": _num(r.refund_amount),
    } for r in rows], total)


# ── Inventario: consultas adicionales ─────────────────────────────────────────

async def _list_inventory_adjustments(ctx: ToolContext, args: dict) -> dict:
    from app.services.inventory_service import InventoryService

    svc = InventoryService(ctx.db, ctx.tenant_id, ctx.user_id)
    rows, total = await svc.adjustments.list(
        tenant_id=ctx.tenant_id, warehouse_id=_parse_uuid(args.get("warehouse_id")),
        status=args.get("status"), offset=0, limit=8,
    )
    return _page([{
        "id": str(a.id), "adjustment_number": a.adjustment_number, "status": a.status.value,
        "reason": a.reason, "adjustment_value": _num(a.adjustment_value),
    } for a in rows], total)


async def _list_cycle_counts(ctx: ToolContext, args: dict) -> dict:
    from app.services.inventory_service import InventoryService

    svc = InventoryService(ctx.db, ctx.tenant_id, ctx.user_id)
    rows, total = await svc.cycle_counts.list(
        tenant_id=ctx.tenant_id, warehouse_id=_parse_uuid(args.get("warehouse_id")),
        status=args.get("status"), offset=0, limit=8,
    )
    return _page([{
        "id": str(c.id), "count_number": c.count_number, "name": c.name,
        "status": c.status.value, "count_type": c.count_type,
    } for c in rows], total)


async def _list_near_expiry_batches(ctx: ToolContext, args: dict) -> dict:
    from app.services.inventory_service import InventoryService

    warehouse_id = _parse_uuid(args.get("warehouse_id"))
    if not warehouse_id:
        return {"ok": False, "error": "warehouse_id es requerido y debe ser un UUID válido."}

    svc = InventoryService(ctx.db, ctx.tenant_id, ctx.user_id)
    rows, total = await svc.batches.get_near_expiry(
        tenant_id=ctx.tenant_id, warehouse_id=warehouse_id,
        days_ahead=int(args.get("days_ahead", 30)), offset=0, limit=8,
    )
    return _page([{
        "batch_number": b.batch_number, "product_code": getattr(b, "product_code", None),
        "product_name": getattr(b, "product_name", None),
        "expiry_date": str(b.expiry_date) if b.expiry_date else None,
        "days_to_expiry": getattr(b, "days_to_expiry", None),
        "quantity_available": _num(getattr(b, "quantity_available", None)),
    } for b in rows], total)


# ── Maestros ───────────────────────────────────────────────────────────────────

async def _search_products(ctx: ToolContext, args: dict) -> dict:
    from sqlalchemy import func, select

    from app.models.master_data import Product

    stmt = select(Product).where(Product.tenant_id == ctx.tenant_id)
    search = args.get("search")
    if search:
        stmt = stmt.where(Product.sku.ilike(f"%{search}%") | Product.name.ilike(f"%{search}%"))
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.db.execute(stmt.order_by(Product.sku).limit(8))).scalars().all()
    return _page([{
        "id": str(p.id), "sku": p.sku, "name": p.name, "uom": p.uom,
        "status": p.status.value, "gtin_13": p.gtin_13,
    } for p in rows], total)


async def _search_suppliers(ctx: ToolContext, args: dict) -> dict:
    from sqlalchemy import func, select

    from app.models.master_data import Supplier

    stmt = select(Supplier).where(Supplier.tenant_id == ctx.tenant_id)
    search = args.get("search")
    if search:
        stmt = stmt.where(Supplier.code.ilike(f"%{search}%") | Supplier.name.ilike(f"%{search}%"))
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.db.execute(stmt.order_by(Supplier.code).limit(8))).scalars().all()
    return _page([{
        "id": str(s.id), "code": s.code, "name": s.name, "status": s.status.value,
        "lead_time_days": s.lead_time_days,
    } for s in rows], total)


async def _search_customers(ctx: ToolContext, args: dict) -> dict:
    from sqlalchemy import func, select

    from app.models.master_data import Customer

    stmt = select(Customer).where(Customer.tenant_id == ctx.tenant_id)
    search = args.get("search")
    if search:
        stmt = stmt.where(Customer.code.ilike(f"%{search}%") | Customer.name.ilike(f"%{search}%"))
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.db.execute(stmt.order_by(Customer.code).limit(8))).scalars().all()
    return _page([{
        "id": str(c.id), "code": c.code, "name": c.name, "is_active": c.is_active,
        "delivery_city": c.delivery_city,
    } for c in rows], total)


async def _search_locations(ctx: ToolContext, args: dict) -> dict:
    from sqlalchemy import and_, func, select

    from app.models.master_data import Location

    conditions = [Location.tenant_id == ctx.tenant_id]
    warehouse_id = _parse_uuid(args.get("warehouse_id"))
    if warehouse_id:
        conditions.append(Location.warehouse_id == warehouse_id)
    search = args.get("search")
    if search:
        conditions.append(Location.code.ilike(f"%{search}%"))
    stmt = select(Location).where(and_(*conditions))
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.db.execute(stmt.order_by(Location.code).limit(8))).scalars().all()
    return _page([{
        "id": str(l.id), "code": l.code, "location_type": l.location_type.value,
        "status": l.status.value,
    } for l in rows], total)


async def _list_warehouses(ctx: ToolContext, args: dict) -> dict:
    from sqlalchemy import func, select

    from app.models.core import Warehouse

    stmt = select(Warehouse).where(Warehouse.tenant_id == ctx.tenant_id)
    search = args.get("search")
    if search:
        stmt = stmt.where(Warehouse.name.ilike(f"%{search}%") | Warehouse.code.ilike(f"%{search}%"))
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.db.execute(stmt.order_by(Warehouse.code).limit(8))).scalars().all()
    return _page([{
        "id": str(w.id), "code": w.code, "name": w.name, "type": w.type.value,
        "status": w.status.value, "picking_strategy": w.picking_strategy,
        "has_cold_storage": w.has_cold_storage,
    } for w in rows], total)


# ── Slotting / Streaming / Hardware ───────────────────────────────────────────

async def _list_slotting_recommendations(ctx: ToolContext, args: dict) -> dict:
    from sqlalchemy import and_, func, select

    from app.models.slotting import SlottingRecommendation

    conditions = [
        SlottingRecommendation.tenant_id == ctx.tenant_id,
        SlottingRecommendation.deleted_at.is_(None),
    ]
    warehouse_id = _parse_uuid(args.get("warehouse_id"))
    if warehouse_id:
        conditions.append(SlottingRecommendation.warehouse_id == warehouse_id)
    if args.get("status"):
        conditions.append(SlottingRecommendation.status == args["status"])
    stmt = select(SlottingRecommendation).where(and_(*conditions))
    total = (await ctx.db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await ctx.db.execute(
        stmt.order_by(SlottingRecommendation.velocity_score.desc().nullslast()).limit(8)
    )).scalars().all()
    return _page([{
        "id": str(r.id), "product_id": str(r.product_id), "abc_class": r.abc_class,
        "current_zone_code": r.current_zone_code, "recommended_zone_code": r.recommended_zone_code,
        "status": r.status, "reason": r.reason,
    } for r in rows], total)


async def _get_streaming_metrics(ctx: ToolContext, args: dict) -> dict:
    from app.services.streaming_service import StreamingService

    svc = StreamingService(ctx.db)
    return await svc.get_metrics(ctx.tenant_id, _parse_uuid(args.get("warehouse_id")))


async def _list_rfid_readers(ctx: ToolContext, args: dict) -> dict:
    from app.services.rfid_service import RfidService

    svc = RfidService(ctx.db)
    rows = await svc.list_readers(ctx.tenant_id, _parse_uuid(args.get("warehouse_id")))
    return {"count": len(rows), "readers": [{
        "id": str(r.id), "code": r.code, "name": r.name, "status": r.status,
        "vendor": r.vendor, "ip_address": r.ip_address,
    } for r in rows]}


# ── Registro de herramientas ──────────────────────────────────────────────────

AGENT_TOOLS: dict[str, AgentTool] = {}


def _register(tool: AgentTool) -> None:
    AGENT_TOOLS[tool.name] = tool


_register(AgentTool(
    name="get_stock_summary",
    description=(
        "Consulta el stock real de inventario. Si se da product_query (SKU o nombre, "
        "puede ser parcial), busca productos que coincidan y devuelve el stock de cada "
        "uno. Si se omite, devuelve el total agregado del tenant."
    ),
    parameters={
        "type": "object",
        "properties": {
            "product_query": {"type": "string", "description": "SKU o nombre (parcial) del producto a buscar."},
        },
        "required": [],
    },
    handler=_get_stock_summary,
    permission="inventory:read",
))

_register(AgentTool(
    name="get_dashboard_kpis",
    description=(
        "Obtiene los KPIs actuales del dashboard de un módulo: inbound, outbound, "
        "inventory, labor, slotting o streaming."
    ),
    parameters={
        "type": "object",
        "properties": {
            "module": {"type": "string", "enum": ["inbound", "outbound", "inventory", "labor", "slotting", "streaming"]},
            "warehouse_id": {"type": "string", "description": "UUID de la bodega (opcional, si se omite agrega todas)."},
        },
        "required": ["module"],
    },
    handler=_get_dashboard_kpis,
    permission=None,
))

_register(AgentTool(
    name="list_active_alerts",
    description="Lista las alertas de reposición (replenishment) activas, no resueltas, más recientes.",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=_list_active_alerts,
    permission="ai:forecast:create",
))

_register(AgentTool(
    name="list_open_anomalies",
    description="Lista las anomalías de inventario detectadas que aún no han sido resueltas.",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=_list_open_anomalies,
    permission="ai:anomaly:manage",
))

_register(AgentTool(
    name="resolve_anomaly",
    description="Marca una anomalía como resuelta (o falso positivo), con una nota de resolución.",
    parameters={
        "type": "object",
        "properties": {
            "anomaly_id": {"type": "string", "description": "UUID de la anomalía a resolver."},
            "is_false_positive": {"type": "boolean", "description": "True si fue un falso positivo."},
            "resolution_notes": {"type": "string", "description": "Explicación de la resolución."},
        },
        "required": ["anomaly_id", "resolution_notes"],
    },
    handler=_resolve_anomaly,
    permission="ai:anomaly:manage",
))

_register(AgentTool(
    name="resolve_replenishment_alert",
    description="Marca una alerta de reposición como resuelta, indicando qué acción se tomó.",
    parameters={
        "type": "object",
        "properties": {
            "alert_id": {"type": "string", "description": "UUID de la alerta a resolver."},
            "action_taken": {"type": "string", "description": "Acción tomada (p. ej. 'OC creada con el proveedor X')."},
        },
        "required": ["alert_id", "action_taken"],
    },
    handler=_resolve_replenishment_alert,
    permission="ai:forecast:create",
))

_register(AgentTool(
    name="suggest_next_labor_task",
    description=(
        "Sugiere (sin asignar) la mejor siguiente tarea de labor pendiente en una bodega, "
        "por proximidad de zona."
    ),
    parameters={
        "type": "object",
        "properties": {
            "warehouse_id": {"type": "string", "description": "UUID de la bodega."},
            "zone": {"type": "string", "description": "Zona actual del operario (opcional)."},
        },
        "required": ["warehouse_id"],
    },
    handler=_suggest_next_labor_task,
    permission="labor:read",
))

_register(AgentTool(
    name="assign_next_labor_task",
    description=(
        "Asigna la siguiente mejor tarea de labor pendiente a un operario específico "
        "(task interleaving). Acción real: cambia el estado de la tarea en la BD."
    ),
    parameters={
        "type": "object",
        "properties": {
            "warehouse_id": {"type": "string", "description": "UUID de la bodega."},
            "operator_id": {"type": "string", "description": "UUID del operario a quien asignar la tarea."},
            "zone": {"type": "string", "description": "Zona actual del operario (opcional)."},
        },
        "required": ["warehouse_id", "operator_id"],
    },
    handler=_assign_next_labor_task,
    permission="labor:task:execute",
))

# ── Inbound: consultas ─────────────────────────────────────────────────────────

_register(AgentTool(
    name="list_purchase_orders",
    description="Lista órdenes de compra (PO), opcionalmente filtradas por bodega, estado o búsqueda de texto.",
    parameters={
        "type": "object",
        "properties": {
            "warehouse_id": {"type": "string", "description": "UUID de la bodega."},
            "status": {"type": "string", "description": "draft | confirmed | sent | partially_received | received | closed | cancelled"},
            "search": {"type": "string", "description": "Busca por número de OC o referencia del proveedor."},
        },
        "required": [],
    },
    handler=_list_purchase_orders, permission="inbound:po:read",
))

_register(AgentTool(
    name="list_grns",
    description="Lista recepciones de mercancía (GRN), opcionalmente filtradas por bodega o estado.",
    parameters={
        "type": "object",
        "properties": {
            "warehouse_id": {"type": "string", "description": "UUID de la bodega."},
            "status": {"type": "string", "description": "draft | in_progress | confirmed | putaway_in_progress | completed | rejected | cancelled"},
        },
        "required": [],
    },
    handler=_list_grns, permission="inbound:grn:read",
))

_register(AgentTool(
    name="list_quality_inspections",
    description="Lista inspecciones de control de calidad, opcionalmente filtradas por bodega o estado.",
    parameters={
        "type": "object",
        "properties": {
            "warehouse_id": {"type": "string", "description": "UUID de la bodega."},
            "status": {"type": "string", "description": "pending | in_progress | approved | rejected | partial | cancelled"},
        },
        "required": [],
    },
    handler=_list_quality_inspections, permission="inbound:qc:create",
))

_register(AgentTool(
    name="list_putaway_tasks",
    description="Lista tareas de putaway (ubicación de mercancía recibida) pendientes o en curso.",
    parameters={
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "pending | assigned | in_progress | completed | cancelled"},
        },
        "required": [],
    },
    handler=_list_putaway_tasks, permission="inbound:putaway:manage",
))

_register(AgentTool(
    name="list_rtvs",
    description="Lista devoluciones a proveedor (RTV), opcionalmente filtradas por estado.",
    parameters={
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "draft | approved | shipped | credited | cancelled"},
        },
        "required": [],
    },
    handler=_list_rtvs, permission="inbound:rtv:create",
))

# ── Outbound: consultas ────────────────────────────────────────────────────────

_register(AgentTool(
    name="list_sales_orders",
    description="Lista órdenes de venta (SO), opcionalmente filtradas por bodega, estado o búsqueda de texto.",
    parameters={
        "type": "object",
        "properties": {
            "warehouse_id": {"type": "string", "description": "UUID de la bodega."},
            "status": {"type": "string", "description": "draft | confirmed | allocated | picking | packed | shipped | delivered | cancelled | partially_shipped"},
            "search": {"type": "string", "description": "Busca por número de SO."},
        },
        "required": [],
    },
    handler=_list_sales_orders, permission="outbound:so:read",
))

_register(AgentTool(
    name="list_picking_waves",
    description="Lista waves (olas) de picking, opcionalmente filtradas por bodega o estado.",
    parameters={
        "type": "object",
        "properties": {
            "warehouse_id": {"type": "string", "description": "UUID de la bodega."},
            "status": {"type": "string", "description": "open | released | in_progress | completed | cancelled"},
        },
        "required": [],
    },
    handler=_list_picking_waves, permission="outbound:wave:create",
))

_register(AgentTool(
    name="list_picking_tasks",
    description="Lista tareas de picking, opcionalmente filtradas por wave o estado.",
    parameters={
        "type": "object",
        "properties": {
            "wave_id": {"type": "string", "description": "UUID de la wave."},
            "status": {"type": "string", "description": "pending | in_progress | completed | short_picked | cancelled"},
        },
        "required": [],
    },
    handler=_list_picking_tasks, permission="outbound:picking:manage",
))

_register(AgentTool(
    name="list_pack_tasks",
    description="Lista tareas de empaque (packing), opcionalmente filtradas por estado.",
    parameters={
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "pending | in_progress | completed | cancelled"},
        },
        "required": [],
    },
    handler=_list_pack_tasks, permission="outbound:packing:manage",
))

_register(AgentTool(
    name="list_shipments",
    description="Lista envíos/despachos, opcionalmente filtrados por bodega o estado.",
    parameters={
        "type": "object",
        "properties": {
            "warehouse_id": {"type": "string", "description": "UUID de la bodega."},
            "status": {"type": "string", "description": "pending | dispatched | in_transit | delivered | cancelled"},
        },
        "required": [],
    },
    handler=_list_shipments, permission="outbound:shipping:manage",
))

_register(AgentTool(
    name="list_returns",
    description="Lista devoluciones de cliente (RMA), opcionalmente filtradas por estado.",
    parameters={
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "pending | received | inspected | refunded | rejected | cancelled"},
        },
        "required": [],
    },
    handler=_list_returns, permission="outbound:rma:create",
))

# ── Inventario: consultas adicionales ─────────────────────────────────────────

_register(AgentTool(
    name="list_inventory_adjustments",
    description="Lista ajustes de inventario, opcionalmente filtrados por bodega o estado.",
    parameters={
        "type": "object",
        "properties": {
            "warehouse_id": {"type": "string", "description": "UUID de la bodega."},
            "status": {"type": "string", "description": "draft | pending_approval | approved | applied | rejected"},
        },
        "required": [],
    },
    handler=_list_inventory_adjustments, permission=None,
))

_register(AgentTool(
    name="list_cycle_counts",
    description="Lista conteos cíclicos de inventario, opcionalmente filtrados por bodega o estado.",
    parameters={
        "type": "object",
        "properties": {
            "warehouse_id": {"type": "string", "description": "UUID de la bodega."},
            "status": {"type": "string", "description": "draft | in_progress | pending_review | completed | cancelled"},
        },
        "required": [],
    },
    handler=_list_cycle_counts, permission=None,
))

_register(AgentTool(
    name="list_near_expiry_batches",
    description="Lista lotes próximos a vencer en una bodega (requiere warehouse_id).",
    parameters={
        "type": "object",
        "properties": {
            "warehouse_id": {"type": "string", "description": "UUID de la bodega (requerido)."},
            "days_ahead": {"type": "integer", "description": "Días hacia adelante a considerar (default 30)."},
        },
        "required": ["warehouse_id"],
    },
    handler=_list_near_expiry_batches, permission=None,
))

# ── Maestros ───────────────────────────────────────────────────────────────────

_register(AgentTool(
    name="search_products",
    description="Busca productos del catálogo por SKU o nombre (parcial).",
    parameters={
        "type": "object",
        "properties": {"search": {"type": "string", "description": "SKU o nombre (parcial)."}},
        "required": [],
    },
    handler=_search_products, permission=None,
))

_register(AgentTool(
    name="search_suppliers",
    description="Busca proveedores por código o nombre (parcial).",
    parameters={
        "type": "object",
        "properties": {"search": {"type": "string", "description": "Código o nombre (parcial)."}},
        "required": [],
    },
    handler=_search_suppliers, permission=None,
))

_register(AgentTool(
    name="search_customers",
    description="Busca clientes por código o nombre (parcial).",
    parameters={
        "type": "object",
        "properties": {"search": {"type": "string", "description": "Código o nombre (parcial)."}},
        "required": [],
    },
    handler=_search_customers, permission=None,
))

_register(AgentTool(
    name="search_locations",
    description="Busca ubicaciones físicas de una bodega por código.",
    parameters={
        "type": "object",
        "properties": {
            "warehouse_id": {"type": "string", "description": "UUID de la bodega."},
            "search": {"type": "string", "description": "Código de ubicación (parcial)."},
        },
        "required": [],
    },
    handler=_search_locations, permission=None,
))

_register(AgentTool(
    name="list_warehouses",
    description="Lista las bodegas del tenant, opcionalmente filtradas por nombre o código.",
    parameters={
        "type": "object",
        "properties": {"search": {"type": "string", "description": "Nombre o código (parcial)."}},
        "required": [],
    },
    handler=_list_warehouses, permission=None,
))

# ── Slotting / Streaming / Hardware ───────────────────────────────────────────

_register(AgentTool(
    name="list_slotting_recommendations",
    description="Lista recomendaciones de slotting (reubicación de productos) pendientes o aplicadas.",
    parameters={
        "type": "object",
        "properties": {
            "warehouse_id": {"type": "string", "description": "UUID de la bodega."},
            "status": {"type": "string", "description": "pending | applied | rejected | expired"},
        },
        "required": [],
    },
    handler=_list_slotting_recommendations, permission="slotting:read",
))

_register(AgentTool(
    name="get_streaming_metrics",
    description="Obtiene métricas de la cola de streaming/waveless (picking sin waves).",
    parameters={
        "type": "object",
        "properties": {"warehouse_id": {"type": "string", "description": "UUID de la bodega."}},
        "required": [],
    },
    handler=_get_streaming_metrics, permission="outbound:order:read",
))

_register(AgentTool(
    name="list_rfid_readers",
    description="Lista los readers RFID físicos registrados y su estado de conexión.",
    parameters={
        "type": "object",
        "properties": {"warehouse_id": {"type": "string", "description": "UUID de la bodega."}},
        "required": [],
    },
    handler=_list_rfid_readers, permission="hardware:read",
))


def to_openai_tool_schemas() -> list[dict[str, Any]]:
    return [t.to_openai_schema() for t in AGENT_TOOLS.values()]


async def execute_tool(name: str, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Punto único de ejecución: valida el permiso y despacha al handler real."""
    tool = AGENT_TOOLS.get(name)
    if tool is None:
        return {"ok": False, "error": f"Herramienta desconocida: '{name}'."}

    if not ctx.has_permission(tool.permission):
        return {"ok": False, "error": f"Permiso denegado: se requiere '{tool.permission}' para usar '{name}'."}

    try:
        result = await tool.handler(ctx, args)
    except Exception as e:  # noqa: BLE001 — cualquier fallo de una tool debe ser reportable al LLM, no tumbar el chat
        return {"ok": False, "error": f"Error ejecutando '{name}': {e}"}

    if "ok" not in result:
        result = {"ok": True, **result}
    return result
