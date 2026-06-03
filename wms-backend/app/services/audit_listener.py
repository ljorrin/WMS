"""
WMS Panamá — Auditoría automática de operaciones (FR-004)
==========================================================
Listener global `before_flush` que registra en AuditLog cada alta/edición/baja
de entidades multi-tenant. Es **best-effort**: cualquier error se traga y se
loguea, de modo que la auditoría NUNCA pueda romper una operación de negocio.

Cobertura: toda entidad con `tenant_id`. Se excluye el propio AuditLog para
evitar recursión. El detalle antes/después fino y la retención de 5 años se
refuerzan a nivel de base de datos (tabla append-only) en despliegue.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.logging import get_logger

log = get_logger(__name__)
_registered = False


def register() -> None:
    """Registra el listener una sola vez (idempotente)."""
    global _registered
    if _registered:
        return
    event.listen(Session, "before_flush", _audit_before_flush)
    _registered = True


def _audit_before_flush(session, flush_context, instances) -> None:
    try:
        from datetime import datetime, timezone
        from app.models.core import AuditLog, AuditAction

        action_map = {
            "create": AuditAction.CREATE,
            "update": AuditAction.UPDATE,
            "delete": AuditAction.DELETE,
        }

        pending: list[tuple[object, str]] = []
        for obj in list(session.new):
            pending.append((obj, "create"))
        for obj in list(session.dirty):
            try:
                if session.is_modified(obj, include_collections=False):
                    pending.append((obj, "update"))
            except Exception:
                continue
        for obj in list(session.deleted):
            pending.append((obj, "delete"))

        audits = []
        for obj, action in pending:
            if isinstance(obj, AuditLog):
                continue
            try:
                tenant_id = getattr(obj, "tenant_id", None)
                if tenant_id is None:
                    continue  # solo entidades multi-tenant
                entity_type = getattr(obj, "__tablename__", obj.__class__.__name__)
                user_id = getattr(obj, "updated_by_id", None) or getattr(obj, "created_by_id", None)
                audits.append(AuditLog(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    action=action_map[action],
                    entity_type=str(entity_type),
                    entity_id=getattr(obj, "id", None),
                    description=f"{action} {entity_type}",
                    occurred_at=datetime.now(timezone.utc),
                ))
            except Exception:
                continue  # nunca dejar que un objeto rompa la auditoría

        for a in audits:
            session.add(a)
    except Exception:
        log.warning("audit_listener_failed", exc_info=True)
