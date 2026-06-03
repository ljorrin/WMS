"""Test del listener de auditoría (FR-004) sin base de datos."""
import os
for _k, _v in {"SECRET_KEY": "x" * 40, "DATABASE_URL": "postgresql+asyncpg://u:p@h/d",
               "DATABASE_SYNC_URL": "postgresql://u:p@h/d", "REDIS_URL": "redis://h/0"}.items():
    os.environ.setdefault(_k, _v)
import uuid
from app.models.core import AuditLog, AuditAction
from app.services.audit_listener import _audit_before_flush


class _Obj:
    __tablename__ = "widgets"
    def __init__(self):
        self.id = uuid.uuid4()
        self.tenant_id = uuid.uuid4()
        self.created_by_id = uuid.uuid4()


class _FakeSession:
    def __init__(self, new=None, dirty=None, deleted=None):
        self.new = new or []
        self.dirty = dirty or []
        self.deleted = deleted or []
        self.added = []
    def is_modified(self, obj, include_collections=False):
        return True
    def add(self, obj):
        self.added.append(obj)


def test_listener_audita_create_update_delete():
    s = _FakeSession(new=[_Obj()], dirty=[_Obj()], deleted=[_Obj()])
    _audit_before_flush(s, None, None)
    assert len(s.added) == 3
    actions = {a.action for a in s.added}
    assert actions == {AuditAction.CREATE, AuditAction.UPDATE, AuditAction.DELETE}
    for a in s.added:
        assert isinstance(a, AuditLog)
        assert a.tenant_id is not None and a.entity_type == "widgets"
        assert a.occurred_at is not None


def test_listener_omite_objetos_sin_tenant_y_auditlog():
    class NoTenant:
        __tablename__ = "x"; id = uuid.uuid4()
    s = _FakeSession(new=[NoTenant(), AuditLog(tenant_id=uuid.uuid4(), action=AuditAction.CREATE, entity_type="y")])
    _audit_before_flush(s, None, None)
    assert s.added == []  # sin tenant_id se omite; AuditLog no se re-audita


def test_listener_nunca_lanza():
    class Boom:
        __tablename__ = "b"
        @property
        def tenant_id(self):  # acceso que revienta
            raise RuntimeError("boom")
    s = _FakeSession(new=[Boom()])
    _audit_before_flush(s, None, None)  # no debe propagar
    assert s.added == []
