"""
WMS Panama — Exportación de envíos al TMS (contrato canónico 1.0)
==================================================================
Convierte cada Shipment del WMS en una `OrdenCanonica` del TMS
(`GET /api/v1/integracion/contrato` del TMS) con todo lo necesario para
planificar y despachar sin intervención manual:

  - destino con coordenadas WGS84, contacto y horario de recepción,
  - origen = bodega del WMS con sus coordenadas y GLN,
  - peso / volumen / bultos (shipment → empaque → maestro de productos),
  - tipo de mercancía derivado de los productos (frío, peligrosos, farma),
  - SSCC de las unidades logísticas empacadas,
  - ventana de entrega, tiempo de servicio, valor declarado y líneas por GTIN.

Cada orden se acompaña de `faltantes` (datos que impiden rutear) y
`advertencias` (datos estimados), para que el operador los corrija en el WMS
antes de que el TMS la tome.
"""

from __future__ import annotations

import hashlib
import math
from datetime import timedelta, timezone
from decimal import Decimal
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.core import Warehouse
from app.models.master_data import Customer, IndustryType, Product, StorageCondition
from app.models.outbound import PackStatus, PackTask, SalesOrder, Shipment, ShipmentStatus

CONTRATO_VERSION = "1.0"

PA_TZ = timezone(timedelta(hours=-5))  # la fecha de compromiso se expresa en hora de Panamá
CARGO_TYPES = ("consumo_masivo", "farmaceutica", "repuestos", "refrigerada", "peligrosa", "fragil")
_COLD = {StorageCondition.REFRIGERATED, StorageCondition.FROZEN, StorageCondition.ULTRA_FROZEN}
_DANGEROUS = {StorageCondition.FLAMMABLE, StorageCondition.HAZMAT}


def _f(value) -> Optional[float]:
    return float(value) if value is not None else None


def _hhmm(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    if len(value) == 4 and value[1] == ":":  # "8:00" → "08:00"
        value = "0" + value
    return value if len(value) == 5 and value[2] == ":" else None


def destination_code(so) -> str:
    """Código estable del punto de entrega (mismo algoritmo que el adaptador del TMS,
    para que los nodos ya creados en el TMS se reutilicen y reciban coordenadas)."""
    base = "|".join(str(getattr(so, k, None) or "").strip().lower()
                    for k in ("customer_id", "ship_to_address", "ship_to_city"))
    return "WMS-DST-" + hashlib.sha1(base.encode()).hexdigest()[:12]


def cargo_type_for(so, products: Iterable) -> str:
    """Override de la SO o, si no hay, el tipo más restrictivo de sus productos."""
    if getattr(so, "cargo_type", None) in CARGO_TYPES:
        return so.cargo_type
    products = [p for p in products if p is not None]
    if any(p.is_hazmat or p.storage_condition in _DANGEROUS for p in products):
        return "peligrosa"
    if any(p.storage_condition in _COLD for p in products):
        return "refrigerada"
    if any(p.industry == IndustryType.PHARMACEUTICAL or p.is_controlled_substance for p in products):
        return "farmaceutica"
    if products and all(p.industry == IndustryType.AUTOMOTIVE for p in products):
        return "repuestos"
    return "consumo_masivo"


def priority_for(so) -> str:
    level = (getattr(so, "service_level", None) or "").strip().lower()
    if level in ("same_day", "same-day", "mismo_dia"):
        return "same_day"
    if level == "express" or int(getattr(so, "priority", None) or 10) <= 2:
        return "express"
    if level in ("scheduled", "programada"):
        return "programada"
    return "normal"


def target_temp(product) -> Optional[float]:
    """Temperatura objetivo de transporte para productos de cadena de frío."""
    if product is None or product.storage_condition not in _COLD:
        return None
    lo, hi = _f(product.min_temp_celsius), _f(product.max_temp_celsius)
    if lo is not None and hi is not None:
        return round((lo + hi) / 2, 1)
    return hi if hi is not None else lo


def _line_qty(line) -> int:
    for attr in ("quantity_packed", "quantity_picked", "quantity_ordered"):
        q = getattr(line, attr, None)
        if q is not None and Decimal(str(q)) > 0:
            return max(1, math.ceil(Decimal(str(q))))
    return 1


def build_canonical_order(shipment, so, customer=None, warehouse=None,
                          products: Optional[dict] = None, packs: Iterable = ()) -> dict:
    """Shipment + SO (+ cliente, bodega, productos, empaques) → OrdenCanonica (dict).

    Devuelve además `faltantes` (bloquean el ruteo) y `advertencias` (estimaciones);
    el TMS ignora esas claves al validar el contrato.
    """
    products = products or {}
    packs = [p for p in packs if p.status == PackStatus.COMPLETED]
    lines = list(getattr(so, "lines", None) or [])
    line_products = [products.get(ln.product_id) for ln in lines]
    faltantes: list[str] = []
    advertencias: list[str] = []

    # ── Destino ──────────────────────────────────────────────────────────────
    address = so.ship_to_address or (customer.delivery_address if customer else None)
    city = so.ship_to_city or (customer.delivery_city if customer else None)
    lat, lon = _f(so.ship_to_latitude), _f(so.ship_to_longitude)
    if (lat is None or lon is None) and customer is not None:
        # Las coordenadas del cliente solo valen si la SO va a su dirección principal
        same_place = not so.ship_to_address or (
            (so.ship_to_address or "").strip().lower() == (customer.delivery_address or "").strip().lower())
        if same_place:
            lat, lon = _f(customer.delivery_latitude), _f(customer.delivery_longitude)
    if lat is None or lon is None:
        lat = lon = None
        faltantes.append("destino.lat/lon")
    if not address:
        faltantes.append("destino.direccion")

    # ── Carga ────────────────────────────────────────────────────────────────
    weight = _f(shipment.total_weight_kg)
    if not weight:
        weight = sum(_f(p.total_weight_kg) or 0 for p in packs) or None
    if not weight:
        est = sum((_f(p.weight_kg) or 0) * _line_qty(ln)
                  for ln, p in zip(lines, line_products) if p is not None)
        if est:
            weight = round(est, 3)
            advertencias.append("peso_kg estimado desde el maestro de productos")
    if not weight:
        weight = 1.0
        faltantes.append("peso_kg")
    volume = _f(shipment.total_volume_m3) or (sum(_f(p.total_volume_m3) or 0 for p in packs) or None)
    if volume is None:
        est = sum((_f(p.volume_m3) or 0) * _line_qty(ln)
                  for ln, p in zip(lines, line_products) if p is not None)
        if est:
            volume = round(est, 4)
            advertencias.append("volumen_m3 estimado desde el maestro de productos")
    boxes = shipment.total_boxes or sum(p.box_count or 0 for p in packs) or None

    # ── Origen (bodega del WMS) ──────────────────────────────────────────────
    origen = {
        "codigo": f"WMS-WH-{shipment.warehouse_id}",
        "nombre": warehouse.name if warehouse else f"Almacén WMS {str(shipment.warehouse_id)[:8]}",
        "direccion": warehouse.address if warehouse else None,
        "ciudad": warehouse.city if warehouse else None,
        "pais": (warehouse.country if warehouse else None) or "PA",
        "lat": _f(warehouse.latitude) if warehouse else None,
        "lon": _f(warehouse.longitude) if warehouse else None,
    }
    if origen["lat"] is None or origen["lon"] is None:
        advertencias.append("origen sin coordenadas (el TMS usará el depósito del conector)")

    fecha = so.requested_delivery_date or shipment.estimated_delivery
    notas = [so.delivery_instructions, shipment.notes,
             f"SO {so.so_number}" + (f" · PO cliente {so.customer_po_reference}" if so.customer_po_reference else "")]
    service_time = so.service_time_min or (customer.service_time_min if customer else None)

    return {
        "referencia_externa": str(shipment.id),
        "numero": shipment.shipment_number or so.so_number,
        "cliente": {
            "codigo": str(so.customer_id),
            "nombre": (customer.name if customer else None) or so.ship_to_name or "Cliente WMS",
            "ruc": so.ruc_cliente or (customer.ruc if customer else None),
            "email": customer.contact_email if customer else None,
            "telefono": customer.contact_phone if customer else None,
        },
        "origen": origen,
        "destino": {
            "codigo": destination_code(so),
            "nombre": so.ship_to_name or (customer.name if customer else None) or "Destino",
            "direccion": address,
            "ciudad": city,
            "pais": so.ship_to_country or (customer.delivery_country if customer else None) or "PA",
            "lat": lat,
            "lon": lon,
            "contacto_nombre": so.ship_to_contact_name or (customer.contact_name if customer else None)
                               or so.ship_to_name,
            "contacto_telefono": so.ship_to_phone or (customer.contact_phone if customer else None),
            "contacto_email": so.ship_to_email or (customer.contact_email if customer else None),
            "horario_desde": _hhmm(customer.receiving_hours_from) if customer else None,
            "horario_hasta": _hhmm(customer.receiving_hours_to) if customer else None,
        },
        "peso_kg": weight,
        "volumen_m3": volume,
        "bultos": boxes,
        "sscc": sorted({p.sscc for p in packs if p.sscc}),
        "tipo_mercancia": cargo_type_for(so, line_products),
        "prioridad": priority_for(so),
        "fecha_compromiso": (fecha.astimezone(PA_TZ) if fecha.tzinfo else fecha).date().isoformat()
                            if fecha else None,
        "ventana_desde": so.delivery_window_start.isoformat() if so.delivery_window_start else None,
        "ventana_hasta": so.delivery_window_end.isoformat() if so.delivery_window_end else None,
        "tiempo_servicio_min": service_time,
        "valor_declarado": _f(so.total_amount) or None,
        "moneda": so.currency or "USD",
        "notas": "\n".join(n for n in notas if n) or None,
        "lineas": [
            {
                "sku": ln.gtin or (p.gtin_14 or p.gtin_13 or p.sku if p else str(ln.product_id)),
                "descripcion": ln.description or (p.name if p else None),
                "cantidad": _line_qty(ln),
                "uom": (p.uom if p else None) or "UN",
                "temp_objetivo_c": target_temp(p),
            }
            for ln, p in zip(lines, line_products)
        ],
        "faltantes": faltantes,
        "advertencias": advertencias,
    }


class TmsExportService:
    """Arma las órdenes canónicas de los envíos del tenant (instanciar por request)."""

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def list_orders(
        self,
        status: ShipmentStatus = ShipmentStatus.PENDING,
        warehouse_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[dict], int]:
        filters = [Shipment.tenant_id == self.tenant_id, Shipment.status == status]
        if warehouse_id:
            filters.append(Shipment.warehouse_id == warehouse_id)
        total = (await self.db.execute(
            select(func.count(Shipment.id)).where(and_(*filters)))).scalar_one()
        shipments = list((await self.db.execute(
            select(Shipment).where(and_(*filters))
            .order_by(Shipment.created_at)
            .offset((page - 1) * page_size).limit(page_size))).scalars().all())
        return await self._build(shipments), total

    async def get_order(self, shipment_id: UUID) -> Optional[dict]:
        shipment = (await self.db.execute(select(Shipment).where(and_(
            Shipment.id == shipment_id, Shipment.tenant_id == self.tenant_id)))).scalar_one_or_none()
        if shipment is None:
            return None
        return (await self._build([shipment]))[0]

    async def preview(self, shipment_ids: list[UUID]) -> list[dict]:
        """Órdenes canónicas de varios envíos, en el orden pedido (vista previa del push)."""
        if not shipment_ids:
            return []
        rows = {s.id: s for s in (await self.db.execute(select(Shipment).where(and_(
            Shipment.tenant_id == self.tenant_id, Shipment.id.in_(shipment_ids))))).scalars().all()}
        shipments = [rows[i] for i in shipment_ids if i in rows]
        built = {o["referencia_externa"]: o for o in await self._build(shipments)}
        return [{**built[str(s.id)], "estado_envio": s.status.value,
                 "enviado_tms": s.tms_sent_at.isoformat() if s.tms_sent_at else None}
                for s in shipments if str(s.id) in built]

    async def _build(self, shipments: list) -> list[dict]:
        if not shipments:
            return []
        so_ids = {s.so_id for s in shipments}
        orders = {so.id: so for so in (await self.db.execute(
            select(SalesOrder).options(selectinload(SalesOrder.lines))
            .where(SalesOrder.id.in_(so_ids)))).scalars().all()}
        customers = await self._by_id(Customer, {so.customer_id for so in orders.values()})
        warehouses = await self._by_id(Warehouse, {s.warehouse_id for s in shipments})
        products = await self._by_id(
            Product, {ln.product_id for so in orders.values() for ln in so.lines})
        packs: dict = {}
        for p in (await self.db.execute(select(PackTask).where(and_(
                PackTask.tenant_id == self.tenant_id, PackTask.so_id.in_(so_ids))))).scalars().all():
            packs.setdefault(p.so_id, []).append(p)

        out = []
        for s in shipments:
            so = orders.get(s.so_id)
            if so is None:
                continue
            out.append(build_canonical_order(
                s, so, customers.get(so.customer_id), warehouses.get(s.warehouse_id),
                products, packs.get(s.so_id, [])))
        return out

    async def _by_id(self, model, ids: set) -> dict:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = (await self.db.execute(select(model).where(and_(
            model.id.in_(ids), model.tenant_id == self.tenant_id)))).scalars().all()
        return {r.id: r for r in rows}


# ══════════════════════════════════════════════════════════════════════════════
# PUSH AL TMS (botón «Enviar al TMS»)
# ══════════════════════════════════════════════════════════════════════════════

def tms_missing_config(cfg) -> list[str]:
    missing = list(cfg.missing)
    if not cfg.extra.get("connector_id"):
        missing.append("TMS_CONNECTOR_ID")
    return missing


class TmsPushService:
    """Envía envíos al webhook de órdenes del TMS
    (`POST {TMS_BASE_URL}/integracion/webhook/{TMS_CONNECTOR_ID}/ordenes`).

    Un POST por envío para enlazar cada Shipment con su orden en el TMS. El TMS es
    idempotente por `referencia_externa` (= Shipment.id): reenviar no duplica.
    Los hitos de despacho/entrega vuelven por el conector `wms_panama` del TMS.
    """

    def __init__(self, db: AsyncSession, tenant_id: UUID, cfg, client=None):
        self.db = db
        self.tenant_id = tenant_id
        self.cfg = cfg
        self.export = TmsExportService(db, tenant_id)
        self._client = client

    async def pending_ids(self) -> list[UUID]:
        rows = await self.db.execute(select(Shipment.id).where(and_(
            Shipment.tenant_id == self.tenant_id,
            Shipment.status == ShipmentStatus.PENDING,
            Shipment.tms_sent_at.is_(None),
        )).order_by(Shipment.created_at))
        return [r[0] for r in rows.all()]

    async def send(self, shipment_ids: list[UUID], force: bool = False) -> list[dict]:
        import httpx
        from datetime import datetime, timezone as tz

        url = (f"{self.cfg.base_url.rstrip('/')}/integracion/webhook/"
               f"{self.cfg.extra['connector_id']}/ordenes")
        headers = {"X-API-Key": self.cfg.api_key}
        results = []
        client = self._client or httpx.AsyncClient(timeout=20.0)
        try:
            for sid in shipment_ids:
                shipment = (await self.db.execute(select(Shipment).where(and_(
                    Shipment.id == sid, Shipment.tenant_id == self.tenant_id)))).scalar_one_or_none()
                base = {"shipment_id": str(sid),
                        "numero": shipment.shipment_number if shipment else None}
                if shipment is None:
                    results.append({**base, "resultado": "error", "error": "Envío no encontrado."})
                    continue
                if shipment.status != ShipmentStatus.PENDING:
                    results.append({**base, "resultado": "error",
                                    "error": f"Solo se envían envíos pendientes (estado: {shipment.status.value})."})
                    continue
                order = (await self.export._build([shipment]))[0]
                if order["faltantes"] and not force:
                    results.append({**base, "resultado": "incompleta", "faltantes": order["faltantes"],
                                    "error": "Faltan datos: " + ", ".join(order["faltantes"])})
                    continue
                payload = {k: v for k, v in order.items() if k not in ("faltantes", "advertencias")}
                try:
                    resp = await client.post(url, json=[payload], headers=headers)
                except httpx.HTTPError as exc:
                    msg = f"No se pudo conectar con el TMS: {exc.__class__.__name__}"
                    shipment.tms_last_error = msg
                    results.append({**base, "resultado": "error", "error": msg})
                    continue
                if resp.status_code >= 400:
                    msg = f"TMS HTTP {resp.status_code}: {resp.text[:300]}"
                    shipment.tms_last_error = msg[:500]
                    results.append({**base, "resultado": "error", "error": msg})
                    continue
                data = resp.json()
                if data.get("errores"):
                    msg = "; ".join(str(e.get("error")) for e in data["errores"])[:500]
                    shipment.tms_last_error = msg
                    results.append({**base, "resultado": "error", "error": msg})
                    continue
                creada = bool(data.get("creadas"))
                if creada and data.get("ordenes"):
                    shipment.tms_order_id = str(data["ordenes"][0])
                shipment.tms_sent_at = shipment.tms_sent_at or datetime.now(tz.utc)
                shipment.tms_last_error = None
                results.append({**base, "resultado": "creada" if creada else "ya_existia",
                                "tms_order_id": shipment.tms_order_id,
                                "advertencias": order["advertencias"]})
        finally:
            if self._client is None:
                await client.aclose()
        return results
