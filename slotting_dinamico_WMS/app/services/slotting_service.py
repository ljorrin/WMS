"""
WMS Panamá — Slotting Dinámico Service — FR-094…097
====================================================
Motor de slotting por rotación:

  • Mide la velocidad de cada producto (frecuencia de picks en una ventana).
  • Clasifica ABC por Pareto acumulado (A ≈ 80% del volumen, B hasta 95%, C resto).
  • Determina si un producto necesita re-slotting: los A fuera de la zona dorada
    se acercan; los C que ocupan la zona dorada se envían a bulk.
  • Persiste recomendaciones y actualiza Product.abc_classification.

La inteligencia (clasificación ABC y regla de re-slot) vive en métodos estáticos
puros, testeables sin base de datos. Los modelos pesados se importan dentro de los
métodos async (patrón usado en app/core/dependencies.py) para mantener el módulo
ligero e importable en tests unitarios con --noconftest.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import SlottingPolicyError, SlottingServiceError, SlottingStateError
from app.models.slotting import SlottingPolicy, SlottingRecommendation


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SlottingService:
    """Servicio de slotting dinámico."""

    DEFAULT_WINDOW_DAYS = 90
    DEFAULT_A = 0.80
    DEFAULT_B = 0.95

    def __init__(self, db: AsyncSession):
        self.db = db

    # ══════════════════════════════════════════════════════════════════════════
    # LÓGICA PURA (testeable sin BD)
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def classify_abc(
        scored: list[tuple], a_threshold: float = 0.80, b_threshold: float = 0.95,
    ) -> dict:
        """
        Clasificación ABC por Pareto acumulado sobre la velocidad.

        Un ítem es 'A' mientras la cuota acumulada ANTES de sumarlo no alcance
        a_threshold (así el ítem que cruza el umbral sigue siendo A y el de mayor
        velocidad siempre es A); 'B' hasta b_threshold; 'C' el resto.

        `scored`: lista de (clave, velocidad). Devuelve {clave: 'A'|'B'|'C'}.
        """
        items = sorted(scored, key=lambda x: (x[1] or 0), reverse=True)
        total = sum((s or 0) for _, s in items)
        if total <= 0:
            return {k: "C" for k, _ in items}

        result: dict = {}
        cum_before = 0.0
        for key, score in items:
            share_before = cum_before / total
            if share_before < a_threshold:
                result[key] = "A"
            elif share_before < b_threshold:
                result[key] = "B"
            else:
                result[key] = "C"
            cum_before += (score or 0)
        return result

    @staticmethod
    def velocity_score(pick_count: int, qty_moved: Decimal | float = 0) -> Decimal:
        """
        Score de velocidad. La frecuencia de picks es el driver principal de
        recorrido (cada pick = un viaje), por lo que pondera más que la cantidad.
        """
        picks = Decimal(str(pick_count or 0))
        qty = Decimal(str(qty_moved or 0))
        # Frecuencia con un aporte marginal del volumen (log-lite: qty/100).
        return (picks + qty / Decimal("100")).quantize(Decimal("0.0001"))

    @staticmethod
    def evaluate_reslot(
        abc_class: str,
        current_zone: Optional[str],
        golden_zone: Optional[str],
        bulk_zone: Optional[str] = None,
    ) -> tuple:
        """
        Decide si un producto necesita re-slotting.

        Devuelve (needs_move: bool, recommended_zone: str|None, reason: str).
        - A fuera de la zona dorada → mover a la zona dorada.
        - C ocupando la zona dorada → mover a bulk (si hay) o liberar.
        - En otro caso, no mover.
        """
        if abc_class == "A" and golden_zone and current_zone != golden_zone:
            return (True, golden_zone,
                    "Producto de alta rotación (A) fuera de la zona dorada de picking.")
        if abc_class == "C" and golden_zone and current_zone == golden_zone:
            return (True, bulk_zone,
                    "Producto de baja rotación (C) ocupando la zona dorada; liberar espacio.")
        return (False, None, "")

    # ══════════════════════════════════════════════════════════════════════════
    # POLÍTICA
    # ══════════════════════════════════════════════════════════════════════════

    async def upsert_policy(
        self, tenant_id: uuid.UUID, data: dict, user_id: Optional[uuid.UUID] = None
    ) -> "SlottingPolicy":
        existing = (await self.db.execute(
            select(SlottingPolicy).where(and_(
                SlottingPolicy.tenant_id == tenant_id,
                SlottingPolicy.warehouse_id == data.get("warehouse_id"),
                SlottingPolicy.deleted_at.is_(None),
            ))
        )).scalar_one_or_none()
        if existing:
            for field, value in data.items():
                setattr(existing, field, value)
            existing.updated_by_id = user_id
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        policy = SlottingPolicy(
            id=uuid.uuid4(), tenant_id=tenant_id, created_by_id=user_id, **data
        )
        self.db.add(policy)
        await self.db.commit()
        await self.db.refresh(policy)
        return policy

    async def _load_policy(
        self, tenant_id: uuid.UUID, warehouse_id: uuid.UUID
    ) -> Optional["SlottingPolicy"]:
        rows = (await self.db.execute(
            select(SlottingPolicy).where(and_(
                SlottingPolicy.tenant_id == tenant_id,
                SlottingPolicy.is_active.is_(True),
                SlottingPolicy.deleted_at.is_(None),
                SlottingPolicy.warehouse_id.in_([warehouse_id, None]),
            ))
        )).scalars().all()
        if not rows:
            return None
        rows.sort(key=lambda p: 0 if p.warehouse_id == warehouse_id else 1)
        return rows[0]

    # ══════════════════════════════════════════════════════════════════════════
    # ANÁLISIS Y GENERACIÓN DE RECOMENDACIONES
    # ══════════════════════════════════════════════════════════════════════════

    async def analyze_and_generate(
        self, tenant_id: uuid.UUID, warehouse_id: uuid.UUID,
        window_days: Optional[int] = None, persist: bool = True,
    ) -> dict:
        """
        Ejecuta el análisis ABC de rotación y genera recomendaciones de re-slot.
        Actualiza Product.abc_classification. Devuelve un resumen.
        """
        from app.models.inventory import InventoryLevel, InventoryMovement, MovementType
        from app.models.master_data import Location, Product, Zone

        policy = await self._load_policy(tenant_id, warehouse_id)
        window = window_days or (policy.velocity_window_days if policy else None) or self.DEFAULT_WINDOW_DAYS
        a_th = float(policy.abc_a_threshold) if policy else self.DEFAULT_A
        b_th = float(policy.abc_b_threshold) if policy else self.DEFAULT_B
        golden = policy.golden_zone_code if policy else None
        bulk = policy.bulk_zone_code if policy else None
        since = _now() - timedelta(days=window)

        # 1) Velocidad por producto (frecuencia de picks + cantidad).
        rows = (await self.db.execute(
            select(
                InventoryMovement.product_id,
                func.count(InventoryMovement.id),
                func.coalesce(func.sum(InventoryMovement.quantity), 0),
            ).where(and_(
                InventoryMovement.tenant_id == tenant_id,
                InventoryMovement.warehouse_id == warehouse_id,
                InventoryMovement.movement_type == MovementType.PICK,
                InventoryMovement.occurred_at >= since,
            )).group_by(InventoryMovement.product_id)
        )).all()

        scored = [(r[0], float(self.velocity_score(r[1], r[2]))) for r in rows]
        pick_counts = {r[0]: int(r[1]) for r in rows}
        score_map = {k: s for k, s in scored}
        abc = self.classify_abc(scored, a_th, b_th)

        # 2) Zona actual de cada producto (ubicación con más stock).
        current = {}
        if abc:
            loc_rows = (await self.db.execute(
                select(
                    InventoryLevel.product_id, InventoryLevel.location_id, Zone.code,
                    InventoryLevel.quantity,
                ).join(Location, Location.id == InventoryLevel.location_id)
                 .join(Zone, Zone.id == Location.zone_id, isouter=True)
                 .where(and_(
                     InventoryLevel.tenant_id == tenant_id,
                     InventoryLevel.warehouse_id == warehouse_id,
                     InventoryLevel.product_id.in_(list(abc.keys())),
                 ))
            )).all()
            for pid, loc_id, zone_code, qty in loc_rows:
                prev = current.get(pid)
                if prev is None or (qty or 0) > prev[2]:
                    current[pid] = (loc_id, zone_code, qty or 0)

        # 3) Actualizar ABC en Product + generar recomendaciones.
        recs_created = 0
        counts = {"A": 0, "B": 0, "C": 0}
        for pid, klass in abc.items():
            counts[klass] = counts.get(klass, 0) + 1
            prod = (await self.db.execute(
                select(Product).where(and_(
                    Product.id == pid, Product.tenant_id == tenant_id
                ))
            )).scalar_one_or_none()
            if prod is not None:
                prod.abc_classification = klass

            loc_id, cur_zone, _ = current.get(pid, (None, None, 0))
            needs, rec_zone, reason = self.evaluate_reslot(klass, cur_zone, golden, bulk)
            if needs and persist:
                self.db.add(SlottingRecommendation(
                    id=uuid.uuid4(), tenant_id=tenant_id, warehouse_id=warehouse_id,
                    product_id=pid, abc_class=klass,
                    velocity_score=Decimal(str(score_map.get(pid, 0))),
                    pick_count=pick_counts.get(pid, 0),
                    current_location_id=loc_id, current_zone_code=cur_zone,
                    recommended_zone_code=rec_zone, reason=reason, status="pending",
                ))
                recs_created += 1

        await self.db.commit()
        return {
            "window_days": window,
            "products_analyzed": len(abc),
            "abc_counts": counts,
            "recommendations_created": recs_created,
            "golden_zone": golden,
            "bulk_zone": bulk,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # RECOMENDACIONES
    # ══════════════════════════════════════════════════════════════════════════

    async def _get_rec(self, tenant_id: uuid.UUID, rec_id: uuid.UUID) -> SlottingRecommendation:
        rec = (await self.db.execute(
            select(SlottingRecommendation).where(and_(
                SlottingRecommendation.id == rec_id,
                SlottingRecommendation.tenant_id == tenant_id,
                SlottingRecommendation.deleted_at.is_(None),
            ))
        )).scalar_one_or_none()
        if not rec:
            raise SlottingServiceError("Recomendación de slotting no encontrada.")
        return rec

    async def apply_recommendation(
        self, tenant_id: uuid.UUID, rec_id: uuid.UUID, user_id: uuid.UUID,
    ) -> SlottingRecommendation:
        rec = await self._get_rec(tenant_id, rec_id)
        if rec.status != "pending":
            raise SlottingStateError(
                f"Solo se aplica una recomendación 'pending' (actual: '{rec.status}')."
            )
        rec.status = "applied"
        rec.applied_at = _now()
        rec.applied_by = user_id
        await self.db.commit()
        await self.db.refresh(rec)
        return rec

    async def reject_recommendation(
        self, tenant_id: uuid.UUID, rec_id: uuid.UUID, user_id: uuid.UUID,
    ) -> SlottingRecommendation:
        rec = await self._get_rec(tenant_id, rec_id)
        if rec.status != "pending":
            raise SlottingStateError(
                f"Solo se rechaza una recomendación 'pending' (actual: '{rec.status}')."
            )
        rec.status = "rejected"
        rec.applied_by = user_id
        await self.db.commit()
        await self.db.refresh(rec)
        return rec

    async def get_dashboard_metrics(
        self, tenant_id: uuid.UUID, warehouse_id: Optional[uuid.UUID] = None,
    ) -> dict:
        base = [
            SlottingRecommendation.tenant_id == tenant_id,
            SlottingRecommendation.deleted_at.is_(None),
        ]
        if warehouse_id:
            base.append(SlottingRecommendation.warehouse_id == warehouse_id)

        async def _count(status: str) -> int:
            return (await self.db.execute(
                select(func.count(SlottingRecommendation.id)).where(
                    and_(*base, SlottingRecommendation.status == status)
                )
            )).scalar_one()

        by_class = {}
        for row in (await self.db.execute(
            select(SlottingRecommendation.abc_class, func.count(SlottingRecommendation.id))
            .where(and_(*base, SlottingRecommendation.status == "pending"))
            .group_by(SlottingRecommendation.abc_class)
        )).all():
            by_class[row[0] or "?"] = row[1]

        return {
            "pending": await _count("pending"),
            "applied": await _count("applied"),
            "rejected": await _count("rejected"),
            "pending_by_class": by_class,
        }
