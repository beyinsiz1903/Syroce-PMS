"""Tests for the supplier credit-utilisation portfolio report
(``GET /api/procurement/credit-utilisation``, Task #79).

These lock the report's contract so finance can rely on it:

  a. Default (``include_unlimited=false``) returns only active suppliers
     with ``credit_limit > 0``, sorted by ``used_pct`` desc.
  b. Status badge mapping: ok / warning (>=80%) / exceeded (>100%).
  c. ``include_unlimited=true`` returns suppliers without a limit too,
     tagged ``no_limit`` and sorted after limited suppliers.
  d. cancelled / closed / received POs do not count toward the open
     commitment (matches the create-PO guard window).
  e. Tenant isolation: suppliers from another tenant are not returned
     and their open POs do not leak into this tenant's commitment.
"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.enums import UserRole
from routers import procurement as proc_module
from routers.procurement import router as proc_router


# ── Fake Mongo helpers ────────────────────────────────────────────────


class _FakeAggregateCursor:
    def __init__(self, rows):
        self._rows = list(rows)

    def __aiter__(self):
        self._iter = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class _FakeFindCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *_a, **_kw):
        return self

    async def to_list(self, _n):
        return list(self._docs)


class _FakePOs:
    def __init__(self, docs):
        self.docs = list(docs)

    def aggregate(self, pipeline):
        match = pipeline[0]["$match"]
        tenant = match["tenant_id"]
        statuses = set(match["status"]["$in"])
        sums: dict[str, float] = {}
        for d in self.docs:
            if d.get("tenant_id") != tenant:
                continue
            if d.get("status") not in statuses:
                continue
            sid = d.get("supplier_id")
            sums[sid] = sums.get(sid, 0.0) + float(d.get("grand_total", 0) or 0)
        rows = [{"_id": sid, "total": total} for sid, total in sums.items()]
        return _FakeAggregateCursor(rows)


class _FakeSuppliers:
    def __init__(self, docs):
        self.docs = list(docs)

    def find(self, query, _proj=None):
        tenant = query.get("tenant_id")
        active = query.get("active")
        cl = query.get("credit_limit")  # may be {"$gt": 0} or absent
        def _match(d):
            if d.get("tenant_id") != tenant:
                return False
            if active is not None and d.get("active") != active:
                return False
            if cl is not None:
                lim = d.get("credit_limit")
                if not (lim is not None and float(lim) > 0):
                    return False
            return True
        return _FakeFindCursor([d for d in self.docs if _match(d)])


class _FakeDB:
    def __init__(self, suppliers, pos):
        self.proc_suppliers = _FakeSuppliers(suppliers)
        self.proc_purchase_orders = _FakePOs(pos)


def _make_user(tenant_id: str = "t1"):
    return SimpleNamespace(
        id="u1", tenant_id=tenant_id, username="finance1",
        email="f@example.com", name="Finance One",
        role=UserRole.FINANCE, granted_permissions=[],
    )


def _build_client(monkeypatch, *, suppliers, pos, user):
    monkeypatch.setattr(proc_module, "_indexes_ready", True, raising=False)
    fake_db = _FakeDB(suppliers, pos)
    monkeypatch.setattr(proc_module, "get_system_db", lambda: fake_db)

    from core.security import get_current_user

    app = FastAPI()
    app.include_router(proc_router)

    async def _fake_user():
        return user

    async def _fake_perm():
        return None

    app.dependency_overrides[get_current_user] = _fake_user
    for route in app.routes:
        if getattr(route, "path", "") == \
                "/api/procurement/credit-utilisation":
            for dep in route.dependant.dependencies:
                if dep.name == "_perm":
                    app.dependency_overrides[dep.call] = _fake_perm

    return TestClient(app)


# ── Tests ─────────────────────────────────────────────────────────────


def test_report_lists_only_limited_active_suppliers_sorted(monkeypatch):
    """(a) Default response: limited + active only, sorted by used_pct desc."""
    suppliers = [
        # ok: 20% used
        {"id": "s_ok", "tenant_id": "t1", "name": "OK Supplier",
         "code": "S-OK", "active": True, "credit_limit": 1000.0},
        # warning: 80% used
        {"id": "s_warn", "tenant_id": "t1", "name": "Warn Supplier",
         "code": "S-W", "active": True, "credit_limit": 1000.0},
        # exceeded: 150% used
        {"id": "s_exc", "tenant_id": "t1", "name": "Exceeded Supplier",
         "code": "S-X", "active": True, "credit_limit": 1000.0},
        # filtered out: inactive
        {"id": "s_inactive", "tenant_id": "t1", "name": "Inactive",
         "code": "S-I", "active": False, "credit_limit": 1000.0},
        # filtered out: no limit (default include_unlimited=false)
        {"id": "s_nolim", "tenant_id": "t1", "name": "No Limit",
         "code": "S-N", "active": True, "credit_limit": None},
    ]
    pos = [
        {"tenant_id": "t1", "supplier_id": "s_ok",
         "status": "sent", "grand_total": 200.0},
        {"tenant_id": "t1", "supplier_id": "s_warn",
         "status": "sent", "grand_total": 800.0},
        {"tenant_id": "t1", "supplier_id": "s_exc",
         "status": "partially_received", "grand_total": 1500.0},
    ]
    client = _build_client(monkeypatch, suppliers=suppliers, pos=pos,
                           user=_make_user())

    r = client.get("/api/procurement/credit-utilisation")
    assert r.status_code == 200, r.text
    items = r.json()["items"]

    # (a) Inactive and no-limit suppliers are filtered out.
    ids = [row["supplier_id"] for row in items]
    assert ids == ["s_exc", "s_warn", "s_ok"], ids  # sorted by used_pct desc

    # (b) Status badge mapping.
    by_id = {row["supplier_id"]: row for row in items}
    assert by_id["s_ok"]["status"] == "ok"
    assert by_id["s_ok"]["used_pct"] == 20.0
    assert by_id["s_ok"]["headroom"] == 800.0
    assert by_id["s_warn"]["status"] == "warning"
    assert by_id["s_warn"]["used_pct"] == 80.0
    assert by_id["s_exc"]["status"] == "exceeded"
    assert by_id["s_exc"]["used_pct"] == 150.0
    assert by_id["s_exc"]["headroom"] == -500.0


def test_include_unlimited_appends_no_limit_rows_last(monkeypatch):
    """(c) include_unlimited=true returns no-limit suppliers after limited."""
    suppliers = [
        {"id": "s_lim", "tenant_id": "t1", "name": "Limited",
         "code": "L", "active": True, "credit_limit": 1000.0},
        {"id": "s_nolim", "tenant_id": "t1", "name": "No Limit",
         "code": "N", "active": True, "credit_limit": None},
    ]
    pos = [{"tenant_id": "t1", "supplier_id": "s_lim",
            "status": "sent", "grand_total": 100.0}]
    client = _build_client(monkeypatch, suppliers=suppliers, pos=pos,
                           user=_make_user())

    r = client.get("/api/procurement/credit-utilisation",
                   params={"include_unlimited": "true"})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [row["supplier_id"] for row in items] == ["s_lim", "s_nolim"]
    no_lim = items[-1]
    assert no_lim["status"] == "no_limit"
    assert no_lim["limit"] is None
    assert no_lim["used_pct"] is None
    assert no_lim["headroom"] is None


def test_closed_cancelled_received_pos_excluded_from_open(monkeypatch):
    """(d) Only draft/sent/partially_received contribute to open_total."""
    suppliers = [{"id": "s1", "tenant_id": "t1", "name": "Sup",
                  "code": "S", "active": True, "credit_limit": 1000.0}]
    pos = [
        {"tenant_id": "t1", "supplier_id": "s1",
         "status": "cancelled", "grand_total": 9000.0},
        {"tenant_id": "t1", "supplier_id": "s1",
         "status": "closed", "grand_total": 9000.0},
        {"tenant_id": "t1", "supplier_id": "s1",
         "status": "received", "grand_total": 9000.0},
        {"tenant_id": "t1", "supplier_id": "s1",
         "status": "draft", "grand_total": 150.0},
    ]
    client = _build_client(monkeypatch, suppliers=suppliers, pos=pos,
                           user=_make_user())

    r = client.get("/api/procurement/credit-utilisation")
    assert r.status_code == 200, r.text
    row = r.json()["items"][0]
    assert row["open_total"] == 150.0
    assert row["status"] == "ok"


def test_tenant_isolation(monkeypatch):
    """(e) Foreign-tenant suppliers and POs must not leak."""
    suppliers = [
        {"id": "s_mine", "tenant_id": "t1", "name": "Mine",
         "code": "M", "active": True, "credit_limit": 1000.0},
        {"id": "s_other", "tenant_id": "t2", "name": "Other",
         "code": "O", "active": True, "credit_limit": 1000.0},
    ]
    pos = [
        # Same supplier_id under a different tenant should NOT count.
        {"tenant_id": "t2", "supplier_id": "s_mine",
         "status": "sent", "grand_total": 999.0},
        {"tenant_id": "t1", "supplier_id": "s_mine",
         "status": "sent", "grand_total": 250.0},
    ]
    client = _build_client(monkeypatch, suppliers=suppliers, pos=pos,
                           user=_make_user(tenant_id="t1"))

    r = client.get("/api/procurement/credit-utilisation")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [row["supplier_id"] for row in items] == ["s_mine"]
    assert items[0]["open_total"] == 250.0
