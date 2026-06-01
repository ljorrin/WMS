"""
WMS Panama — Detector de Anomalías en Inventario
==================================================
Detecta comportamientos anómalos en movimientos de inventario
usando métodos estadísticos clásicos y opcionalmente scikit-learn.

Métodos implementados:
  1. Z-Score      : detecta outliers en cantidades de movimiento
  2. IQR          : rango intercuartílico para valores extremos
  3. Velocity     : cambio abrupto en la velocidad de movimiento del producto
  4. Duplicados   : movimientos duplicados en ventana de tiempo
  5. Stock negativo: stock físico por debajo de 0 (error de sistema)

Cada anomalía se registra como AnomalyEvent en la BD y puede
generar una ReplenishmentAlert de tipo ANOMALY_MOVEMENT.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

import structlog

log = structlog.get_logger(__name__)


def _z_score(value: float, mean: float, std: float) -> float:
    """Z-Score: desviaciones estándar desde la media."""
    return (value - mean) / std if std > 0 else 0.0


def _is_outlier_iqr(value: float, q1: float, q3: float, multiplier: float = 1.5) -> bool:
    """Outlier por IQR: valor fuera de [Q1 - k*IQR, Q3 + k*IQR]."""
    iqr = q3 - q1
    return value < q1 - multiplier * iqr or value > q3 + multiplier * iqr


class AnomalyDetector:
    """
    Detector de anomalías. Se instancia por petición o como tarea Celery.
    """

    Z_THRESHOLD      = 3.0    # Z-Score para considerar outlier
    IQR_MULTIPLIER   = 2.0    # Multiplicador IQR para extreme outliers
    VELOCITY_CHANGE  = 0.50   # 50% cambio en velocidad = anomalía
    DUPLICATE_WINDOW = 60     # Segundos para considerar movimiento duplicado
    MIN_HISTORY      = 30     # Días mínimos de historial para calcular estadísticas

    def __init__(self, db, tenant_id: UUID, user_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    # ── API pública ───────────────────────────────────────────────────────────

    async def run_full_scan(
        self,
        warehouse_id: Optional[UUID] = None,
        days_back: int = 7,
    ) -> dict:
        """
        Ejecuta todos los detectores sobre los movimientos recientes.
        Retorna resumen de anomalías encontradas.
        """
        log.info("anomaly.scan_start", tenant=str(self.tenant_id), days=days_back)

        results = {
            "quantity_outliers":  await self._detect_quantity_outliers(warehouse_id, days_back),
            "velocity_changes":   await self._detect_velocity_changes(warehouse_id),
            "duplicate_movements": await self._detect_duplicates(warehouse_id, days_back),
            "negative_stock":     await self._detect_negative_stock(warehouse_id),
        }

        total = sum(len(v) for v in results.values())
        log.info("anomaly.scan_complete", total=total)

        return {
            "scanned_days": days_back,
            "total_anomalies": total,
            "breakdown": {k: len(v) for k, v in results.items()},
            "anomalies": [a for lst in results.values() for a in lst],
        }

    async def get_anomalies(
        self,
        is_resolved: Optional[bool] = False,
        product_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """Lista anomalías con filtros."""
        from sqlalchemy import select, func, and_
        from app.models.ai import AnomalyEvent

        filters = [AnomalyEvent.tenant_id == self.tenant_id]
        if is_resolved is not None:
            filters.append(AnomalyEvent.is_resolved == is_resolved)
        if product_id:
            filters.append(AnomalyEvent.product_id == product_id)

        total = (await self.db.execute(
            select(func.count(AnomalyEvent.id)).where(and_(*filters))
        )).scalar_one()

        rows = (await self.db.execute(
            select(AnomalyEvent)
            .where(and_(*filters))
            .order_by(AnomalyEvent.detected_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )).scalars().all()

        return {"items": rows, "total": total, "page": page, "page_size": page_size}

    async def resolve_anomaly(
        self,
        anomaly_id: UUID,
        is_false_positive: bool,
        resolution_notes: str,
    ) -> None:
        from sqlalchemy import update
        from app.models.ai import AnomalyEvent

        await self.db.execute(
            update(AnomalyEvent)
            .where(and_(
                AnomalyEvent.id == anomaly_id,
                AnomalyEvent.tenant_id == self.tenant_id,
            ))
            .values(
                is_resolved=True,
                is_false_positive=is_false_positive,
                resolved_at=datetime.now(timezone.utc),
                resolved_by_id=self.user_id,
                resolution_notes=resolution_notes,
                updated_at=datetime.now(timezone.utc),
            )
        )

    # ── Detectores ────────────────────────────────────────────────────────────

    async def _detect_quantity_outliers(
        self, warehouse_id: Optional[UUID], days_back: int
    ) -> list[dict]:
        """Z-Score e IQR sobre cantidades de movimientos recientes."""
        movements = await self._load_recent_movements(warehouse_id, days_back)
        if len(movements) < self.MIN_HISTORY:
            return []

        quantities = [float(m["quantity"]) for m in movements]
        mean_q = statistics.mean(quantities)
        std_q  = statistics.stdev(quantities) if len(quantities) > 1 else 0

        sorted_q = sorted(quantities)
        q1 = sorted_q[len(sorted_q) // 4]
        q3 = sorted_q[3 * len(sorted_q) // 4]

        anomalies = []
        for m in movements:
            qty = float(m["quantity"])
            z = _z_score(qty, mean_q, std_q)
            is_iqr_outlier = _is_outlier_iqr(qty, q1, q3, self.IQR_MULTIPLIER)

            if abs(z) > self.Z_THRESHOLD or is_iqr_outlier:
                from app.models.ai import AnomalyType, AlertSeverity
                severity = AlertSeverity.CRITICAL if abs(z) > 5 else AlertSeverity.WARNING

                event = await self._save_anomaly(
                    anomaly_type=AnomalyType.UNUSUAL_QUANTITY,
                    severity=severity,
                    product_id=m.get("product_id"),
                    warehouse_id=warehouse_id,
                    reference_type="movement",
                    reference_id=m.get("id"),
                    detected_value=qty,
                    expected_value=mean_q,
                    z_score=round(z, 2),
                    confidence=min(1.0, abs(z) / self.Z_THRESHOLD) if std_q > 0 else 0.5,
                    description=(
                        f"Cantidad inusual en movimiento: {qty:.2f} uds "
                        f"(media: {mean_q:.2f}, Z={z:.2f})"
                    ),
                    context_data={"q1": q1, "q3": q3, "iqr_outlier": is_iqr_outlier},
                )
                anomalies.append(event)

        return anomalies

    async def _detect_velocity_changes(self, warehouse_id: Optional[UUID]) -> list[dict]:
        """
        Detecta cambios abruptos en la velocidad de rotación de productos.
        Compara la velocidad de los últimos 7 días vs los 30 días anteriores.
        """
        products = await self._load_active_products(warehouse_id)
        anomalies = []

        for product_id in products:
            hist_7  = await self._load_product_velocity(product_id, days=7)
            hist_30 = await self._load_product_velocity(product_id, days=30)

            if hist_30 == 0:
                continue

            change_pct = abs(hist_7 - hist_30) / hist_30

            if change_pct >= self.VELOCITY_CHANGE:
                from app.models.ai import AnomalyType, AlertSeverity
                severity = AlertSeverity.WARNING if change_pct < 1.0 else AlertSeverity.CRITICAL

                direction = "aumento" if hist_7 > hist_30 else "disminución"
                event = await self._save_anomaly(
                    anomaly_type=AnomalyType.VELOCITY_CHANGE,
                    severity=severity,
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    reference_type=None,
                    reference_id=None,
                    detected_value=hist_7,
                    expected_value=hist_30,
                    z_score=None,
                    confidence=min(1.0, change_pct),
                    description=(
                        f"Cambio abrupto de {direction} en velocidad de movimiento: "
                        f"{hist_30:.2f} u/día → {hist_7:.2f} u/día ({change_pct*100:.0f}%)"
                    ),
                    context_data={
                        "velocity_7d": hist_7,
                        "velocity_30d": hist_30,
                        "change_pct": round(change_pct * 100, 1),
                    },
                )
                anomalies.append(event)

        return anomalies

    async def _detect_duplicates(
        self, warehouse_id: Optional[UUID], days_back: int
    ) -> list[dict]:
        """
        Detecta movimientos idénticos (mismo producto, qty, tipo) dentro
        de una ventana de tiempo estrecha (DUPLICATE_WINDOW segundos).
        """
        movements = await self._load_recent_movements(warehouse_id, days_back)
        anomalies = []
        seen: dict[str, datetime] = {}

        for m in movements:
            key = f"{m.get('product_id')}:{m.get('movement_type')}:{m.get('quantity')}"
            ts  = m.get("created_at")
            if not ts:
                continue

            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)

            if key in seen:
                delta = abs((ts - seen[key]).total_seconds())
                if delta <= self.DUPLICATE_WINDOW:
                    from app.models.ai import AnomalyType, AlertSeverity
                    event = await self._save_anomaly(
                        anomaly_type=AnomalyType.DUPLICATE_MOVEMENT,
                        severity=AlertSeverity.WARNING,
                        product_id=m.get("product_id"),
                        warehouse_id=warehouse_id,
                        reference_type="movement",
                        reference_id=m.get("id"),
                        detected_value=delta,
                        expected_value=self.DUPLICATE_WINDOW,
                        z_score=None,
                        confidence=0.85,
                        description=(
                            f"Posible movimiento duplicado detectado: mismo producto "
                            f"y cantidad registrados {delta:.0f}s apart."
                        ),
                        context_data={"window_seconds": self.DUPLICATE_WINDOW},
                    )
                    anomalies.append(event)
            else:
                seen[key] = ts

        return anomalies

    async def _detect_negative_stock(self, warehouse_id: Optional[UUID]) -> list[dict]:
        """
        Detecta niveles de inventario con quantity_on_hand < 0 (inconsistencia).
        """
        from sqlalchemy import select, and_
        from app.models.inventory import InventoryLevel

        filters = [
            InventoryLevel.tenant_id == self.tenant_id,
            InventoryLevel.quantity_on_hand < 0,
        ]
        if warehouse_id:
            filters.append(InventoryLevel.warehouse_id == warehouse_id)

        result = await self.db.execute(
            select(InventoryLevel).where(and_(*filters))
        )
        negative_levels = result.scalars().all()
        anomalies = []

        for level in negative_levels:
            from app.models.ai import AnomalyType, AlertSeverity
            event = await self._save_anomaly(
                anomaly_type=AnomalyType.NEGATIVE_STOCK,
                severity=AlertSeverity.CRITICAL,
                product_id=level.product_id,
                warehouse_id=warehouse_id or level.warehouse_id,
                reference_type="inventory_level",
                reference_id=level.id,
                detected_value=float(level.quantity_on_hand),
                expected_value=0.0,
                z_score=None,
                confidence=1.0,
                description=(
                    f"Stock negativo detectado: {float(level.quantity_on_hand):.4f} uds. "
                    f"Ubicación: {level.location_id}."
                ),
                context_data={"location_id": str(level.location_id)},
            )
            anomalies.append(event)

        return anomalies

    # ── Persistencia ──────────────────────────────────────────────────────────

    async def _save_anomaly(
        self,
        anomaly_type,
        severity,
        product_id,
        warehouse_id,
        reference_type,
        reference_id,
        detected_value,
        expected_value,
        z_score,
        confidence,
        description,
        context_data=None,
    ) -> dict:
        from app.models.ai import AnomalyEvent

        event = AnomalyEvent(
            id=uuid4(),
            tenant_id=self.tenant_id,
            warehouse_id=warehouse_id or self.tenant_id,
            product_id=product_id,
            anomaly_type=anomaly_type,
            severity=severity,
            reference_type=reference_type,
            reference_id=reference_id,
            detected_value=detected_value,
            expected_value=expected_value,
            z_score=z_score,
            confidence=confidence,
            description=description,
            context_data=context_data or {},
            detected_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        await self.db.flush()
        return {"id": str(event.id), "type": anomaly_type.value, "description": description}

    # ── Data helpers ──────────────────────────────────────────────────────────

    async def _load_recent_movements(
        self, warehouse_id: Optional[UUID], days: int
    ) -> list[dict]:
        from sqlalchemy import select, and_
        from app.models.inventory import InventoryMovement

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        filters = [
            InventoryMovement.tenant_id == self.tenant_id,
            InventoryMovement.created_at >= cutoff,
        ]
        try:
            result = await self.db.execute(
                select(InventoryMovement).where(and_(*filters)).limit(5000)
            )
            rows = result.scalars().all()
            return [
                {
                    "id": str(r.id),
                    "product_id": r.product_id,
                    "quantity": float(r.quantity),
                    "movement_type": r.movement_type,
                    "created_at": r.created_at,
                }
                for r in rows
            ]
        except Exception:
            return []

    async def _load_active_products(self, warehouse_id: Optional[UUID]) -> list[UUID]:
        from sqlalchemy import select, distinct, and_
        from app.models.inventory import InventoryLevel

        filters = [InventoryLevel.tenant_id == self.tenant_id]
        if warehouse_id:
            filters.append(InventoryLevel.warehouse_id == warehouse_id)

        try:
            result = await self.db.execute(
                select(distinct(InventoryLevel.product_id)).where(and_(*filters)).limit(200)
            )
            return [r[0] for r in result.all()]
        except Exception:
            return []

    async def _load_product_velocity(self, product_id: UUID, days: int) -> float:
        """Unidades promedio por día para el producto en los últimos N días."""
        from sqlalchemy import select, func, and_
        from app.models.inventory import InventoryMovement

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        try:
            result = await self.db.execute(
                select(func.sum(InventoryMovement.quantity)).where(
                    and_(
                        InventoryMovement.tenant_id == self.tenant_id,
                        InventoryMovement.product_id == product_id,
                        InventoryMovement.movement_type.in_(["PICK", "ISSUE"]),
                        InventoryMovement.created_at >= cutoff,
                    )
                )
            )
            total = float(result.scalar_one() or 0)
            return total / days
        except Exception:
            return 0.0
