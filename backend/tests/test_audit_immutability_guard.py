"""
Tests: append-only immutability guard for audit collections (Task #568).

The guard must let inserts/reads through but block every update/delete/replace
on `audit_logs` / `audit_logs_archive` from application code, while still
permitting the controlled retention move under audit_retention_context().
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core.tenant_db import (
    AppendOnlyCollection,
    AuditImmutabilityError,
    audit_retention_context,
)


class _RecordingColl:
    """Stand-in for a Motor collection: records which ops were invoked."""

    def __init__(self):
        self.calls = []
        self.name = "audit_logs"

    async def insert_one(self, doc, *a, **k):
        self.calls.append(("insert_one", doc))
        return "ok"

    async def delete_one(self, flt, *a, **k):
        self.calls.append(("delete_one", flt))
        return "deleted"

    async def update_one(self, flt, upd, *a, **k):
        self.calls.append(("update_one", flt))
        return "updated"

    def find(self, *a, **k):
        self.calls.append(("find", a))
        return "cursor"


@pytest.mark.parametrize("op", [
    "update_one", "update_many", "delete_one", "delete_many",
    "find_one_and_update", "find_one_and_delete", "find_one_and_replace",
    "replace_one", "drop", "rename",
])
def test_blocked_ops_raise(op):
    guard = AppendOnlyCollection(_RecordingColl(), "audit_logs")
    with pytest.raises(AuditImmutabilityError):
        getattr(guard, op)


async def test_insert_and_read_pass_through():
    inner = _RecordingColl()
    guard = AppendOnlyCollection(inner, "audit_logs")
    assert await guard.insert_one({"x": 1}) == "ok"
    assert guard.find({"x": 1}) == "cursor"
    assert ("insert_one", {"x": 1}) in inner.calls


async def test_retention_context_permits_delete():
    inner = _RecordingColl()
    guard = AppendOnlyCollection(inner, "audit_logs")
    # Outside the context → blocked.
    with pytest.raises(AuditImmutabilityError):
        getattr(guard, "delete_one")
    # Inside the sanctioned retention context → allowed.
    with audit_retention_context():
        assert await guard.delete_one({"_id": 1}) == "deleted"
    assert ("delete_one", {"_id": 1}) in inner.calls
    # Context resets afterwards → blocked again.
    with pytest.raises(AuditImmutabilityError):
        getattr(guard, "delete_one")


def test_proxy_wraps_audit_collections():
    """The transparent proxy must return the guard for audit collections."""
    from core.tenant_db import TenantAwareDBProxy

    class _RawDB:
        def __getitem__(self, name):
            return _RecordingColl()

    proxy = TenantAwareDBProxy(_RawDB())
    assert isinstance(proxy.audit_logs, AppendOnlyCollection)
    assert isinstance(proxy["audit_logs_archive"], AppendOnlyCollection)


# ── Canonical write path: direct inserts are auto-chained + attributed ──

async def test_direct_insert_is_chained(monkeypatch):
    """A call site that inserts straight into audit_logs (bypassing
    append_audit_log) is still tamper-evidently chained at the DB layer."""
    import core.audit_chain as ac

    async def fake_link(tenant_id, entry):
        assert tenant_id == "t1"
        return (7, "PREVHASH", "RECHASH")

    monkeypatch.setattr(ac, "_link_chain", fake_link)
    inner = _RecordingColl()
    guard = AppendOnlyCollection(inner, "audit_logs")
    doc = {"tenant_id": "t1", "action": "X"}
    await guard.insert_one(doc)
    assert doc["seq"] == 7
    assert doc["prev_hash"] == "PREVHASH"
    assert doc["record_hash"] == "RECHASH"
    assert ("insert_one", doc) in inner.calls


async def test_already_chained_not_relinked(monkeypatch):
    """Idempotent: a record append_audit_log already linked is not re-chained."""
    import core.audit_chain as ac

    async def boom(*a, **k):
        raise AssertionError("must not re-chain an already-linked record")

    monkeypatch.setattr(ac, "_link_chain", boom)
    guard = AppendOnlyCollection(_RecordingColl(), "audit_logs")
    doc = {"tenant_id": "t1", "record_hash": "EXISTING", "seq": 3}
    await guard.insert_one(doc)
    assert doc["record_hash"] == "EXISTING"
    assert doc["seq"] == 3


async def test_insert_stamps_ip_and_user_agent(monkeypatch):
    """Attribution: IP + user-agent are filled from the request context when the
    caller omitted them."""
    import core.audit_chain as ac
    from common.request_context import set_request_context, clear_request_context

    async def fake_link(tenant_id, entry):
        return (1, "", "H")

    monkeypatch.setattr(ac, "_link_chain", fake_link)
    set_request_context("9.9.9.9", "Mozilla/Test")
    try:
        guard = AppendOnlyCollection(_RecordingColl(), "audit_logs")
        doc = {"tenant_id": "t1"}
        await guard.insert_one(doc)
        assert doc["ip_address"] == "9.9.9.9"
        assert doc["user_agent"] == "Mozilla/Test"
    finally:
        clear_request_context()


async def test_caller_supplied_ip_ua_not_overwritten(monkeypatch):
    import core.audit_chain as ac
    from common.request_context import set_request_context, clear_request_context

    async def fake_link(tenant_id, entry):
        return (1, "", "H")

    monkeypatch.setattr(ac, "_link_chain", fake_link)
    set_request_context("9.9.9.9", "ctx-ua")
    try:
        guard = AppendOnlyCollection(_RecordingColl(), "audit_logs")
        doc = {"tenant_id": "t1", "ip_address": "1.1.1.1", "user_agent": "real-ua"}
        await guard.insert_one(doc)
        assert doc["ip_address"] == "1.1.1.1"
        assert doc["user_agent"] == "real-ua"
    finally:
        clear_request_context()


async def test_archive_insert_not_chained(monkeypatch):
    """Archive inserts (the retention move) copy records verbatim — never
    re-chained or re-attributed."""
    import core.audit_chain as ac

    async def boom(*a, **k):
        raise AssertionError("archive inserts must not be chained")

    monkeypatch.setattr(ac, "_link_chain", boom)
    inner = _RecordingColl()
    inner.name = "audit_logs_archive"
    guard = AppendOnlyCollection(inner, "audit_logs_archive")
    doc = {"tenant_id": "t1", "record_hash": "orig", "seq": 3}
    await guard.insert_one(doc)
    assert doc["seq"] == 3
    assert doc["record_hash"] == "orig"


def test_get_system_db_guards_audit_only(monkeypatch):
    """get_system_db() returns the immutability/canonical guard for audit
    collections but passes every other collection + db method straight through."""
    import core.database as coredb
    from core.tenant_db import get_system_db

    class _FakeRaw:
        def __init__(self):
            self._c = {}

        def __getitem__(self, name):
            return self._c.setdefault(name, _RecordingColl())

        def ping(self):
            return "pong"

    fake = _FakeRaw()
    monkeypatch.setattr(coredb, "_raw_db", fake)
    sysdb = get_system_db()
    assert isinstance(sysdb["audit_logs"], AppendOnlyCollection)
    assert isinstance(sysdb.audit_logs_archive, AppendOnlyCollection)
    # Non-audit collection → raw passthrough (same object).
    assert sysdb["folio_charges"] is fake["folio_charges"]
    # Db-level method → delegated to the raw db.
    assert sysdb.ping() == "pong"
