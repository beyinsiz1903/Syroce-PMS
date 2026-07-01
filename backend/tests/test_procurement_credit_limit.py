"""Unit tests for the supplier credit-limit guard in
``create_purchase_order`` (backend/routers/procurement.py, Task #19).

These cases lock the guard's behaviour at the FastAPI layer so a future
change to the open-PO status set or the ``manage_credit_limit`` override
permission key is caught before it ships:

  a. PO under limit succeeds (200).
  b. PO that breaches limit → 409.
  c. cancelled / closed POs do not count toward open commitment.
  d. ``override_credit_limit=true`` without ``manage_credit_limit`` → 403.
  e. ``override_credit_limit=true`` *with* ``manage_credit_limit`` → 200
     even when the projected total is over the limit.
  f. supplier with no ``credit_limit`` → guard is skipped entirely.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
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


class _FakePOs:
    """Fake ``proc_purchase_orders`` collection.

    Holds an in-memory list of PO docs; ``aggregate`` filters by the
    same status set the real handler uses so test (c) really exercises
    the status filter.
    """

    def __init__(self, docs):
        self.docs = list(docs)
        self.inserted: list[dict] = []

    def aggregate(self, pipeline):
        match = pipeline[0]["$match"]
        statuses = set(match["status"]["$in"])
        tenant = match["tenant_id"]
        sup = match["supplier_id"]
        total = sum(
            float(d.get("grand_total", 0) or 0)
            for d in self.docs
            if d.get("tenant_id") == tenant
            and d.get("supplier_id") == sup
            and d.get("status") in statuses
        )
        rows = [{"_id": None, "total": total}] if total else []
        return _FakeAggregateCursor(rows)

    async def insert_one(self, doc):
        self.inserted.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))


class _FakeSuppliers:
    def __init__(self, supplier):
        self._supplier = supplier

    async def find_one(self, query, *_a, **_kw):
        if not self._supplier:
            return None
        if self._supplier.get("id") != query.get("id"):
            return None
        if self._supplier.get("tenant_id") != query.get("tenant_id"):
            return None
        return dict(self._supplier)


class _FakePRs:
    async def find_one(self, *_a, **_kw):
        return None


class _FakeCounters:
    """`_next_no` calls `find_one_and_update` with upsert + return_document."""

    def __init__(self):
        self._seq = 0

    async def find_one_and_update(self, *_a, **_kw):
        self._seq += 1
        return {"seq": self._seq}


class _FakeDB:
    def __init__(self, supplier, pos):
        self.proc_suppliers = _FakeSuppliers(supplier)
        self.proc_purchase_orders = _FakePOs(pos)
        self.proc_purchase_requests = _FakePRs()
        self.proc_counters = _FakeCounters()


# ── Fixtures ──────────────────────────────────────────────────────────


def _make_user(*, role: UserRole = UserRole.PROCUREMENT,
               granted: list[str] | None = None):
    return SimpleNamespace(
        id="u1",
        tenant_id="t1",
        username="buyer1",
        email="buyer@example.com",
        name="Buyer One",
        role=role,
        granted_permissions=list(granted or []),
    )


def _build_client(monkeypatch, *, supplier, pos, user, override_perm=False):
    # Skip Mongo index creation entirely.
    monkeypatch.setattr(proc_module, "_indexes_ready", True, raising=False)

    fake_db = _FakeDB(supplier, pos)
    monkeypatch.setattr(proc_module, "get_system_db", lambda: fake_db)

    # Silence the audit logger — it would otherwise try to write to a
    # real collection.
    async def _no_audit(*_a, **_kw):
        return None

    monkeypatch.setattr(proc_module, "log_audit_event", _no_audit)

    # Pin the override permission decision so we don't depend on the
    # full RolePermissionService graph.
    def _fake_check_permission(self, role, perm, granted_permissions=None):
        if perm == "manage_credit_limit":
            return override_perm
        return True

    monkeypatch.setattr(
        proc_module.RolePermissionService,
        "check_permission",
        _fake_check_permission,
    )

    from core.security import get_current_user

    app = FastAPI()
    app.include_router(proc_router)

    async def _fake_user():
        return user

    async def _fake_perm():
        return None

    app.dependency_overrides[get_current_user] = _fake_user
    for route in app.routes:
        if getattr(route, "path", "") == "/api/procurement/purchase-orders" \
                and "POST" in getattr(route, "methods", set()):
            for dep in route.dependant.dependencies:
                if dep.name == "_perm":
                    app.dependency_overrides[dep.call] = _fake_perm

    return TestClient(app), fake_db


def _po_body(qty=10, unit_cost=100.0):
    return {
        "supplier_id": "sup1",
        "tax_rate": 0,  # keep math obvious: grand_total = qty * unit_cost
        "lines": [{
            "item_name": "Widget",
            "quantity": qty,
            "unit": "adet",
            "unit_cost": unit_cost,
        }],
    }


# ── Tests ─────────────────────────────────────────────────────────────


def test_po_under_credit_limit_succeeds(monkeypatch):
    """(a) New PO that fits inside the supplier's credit limit is accepted."""
    supplier = {"id": "sup1", "tenant_id": "t1", "name": "Sup",
                "active": True, "credit_limit": 5000.0}
    existing = [{"tenant_id": "t1", "supplier_id": "sup1",
                 "status": "sent", "grand_total": 1000.0}]
    client, db = _build_client(monkeypatch, supplier=supplier,
                               pos=existing, user=_make_user())

    # 1000 (open) + 3000 (new) = 4000 ≤ 5000
    r = client.post("/api/procurement/purchase-orders",
                    json=_po_body(qty=30, unit_cost=100.0))
    assert r.status_code == 200, r.text
    assert r.json()["grand_total"] == 3000.0
    assert len(db.proc_purchase_orders.inserted) == 1


def test_po_breaching_credit_limit_is_rejected(monkeypatch):
    """(b) Projected commitment > credit_limit → 409 with no insert."""
    supplier = {"id": "sup1", "tenant_id": "t1", "name": "Sup",
                "active": True, "credit_limit": 5000.0}
    existing = [{"tenant_id": "t1", "supplier_id": "sup1",
                 "status": "sent", "grand_total": 4000.0}]
    client, db = _build_client(monkeypatch, supplier=supplier,
                               pos=existing, user=_make_user())

    # 4000 (open) + 2000 (new) = 6000 > 5000
    r = client.post("/api/procurement/purchase-orders",
                    json=_po_body(qty=20, unit_cost=100.0))
    assert r.status_code == 409, r.text
    assert "kredi limiti" in r.json()["detail"].lower()
    assert db.proc_purchase_orders.inserted == []


def test_cancelled_and_closed_pos_do_not_count(monkeypatch):
    """(c) Only draft/sent/partially_received POs count toward commitment.

    A cancelled PO and a fully-received (closed) PO together total well
    over the credit limit, but the guard must ignore both.
    """
    supplier = {"id": "sup1", "tenant_id": "t1", "name": "Sup",
                "active": True, "credit_limit": 5000.0}
    existing = [
        {"tenant_id": "t1", "supplier_id": "sup1",
         "status": "cancelled", "grand_total": 9000.0},
        {"tenant_id": "t1", "supplier_id": "sup1",
         "status": "received", "grand_total": 8000.0},
        {"tenant_id": "t1", "supplier_id": "sup1",
         "status": "closed", "grand_total": 7000.0},
    ]
    client, db = _build_client(monkeypatch, supplier=supplier,
                               pos=existing, user=_make_user())

    # Open commitment computed by the guard should be 0, so a 4000 PO fits.
    r = client.post("/api/procurement/purchase-orders",
                    json=_po_body(qty=40, unit_cost=100.0))
    assert r.status_code == 200, r.text
    assert len(db.proc_purchase_orders.inserted) == 1


def test_override_without_permission_is_403(monkeypatch):
    """(d) `override_credit_limit=true` requires `manage_credit_limit`."""
    supplier = {"id": "sup1", "tenant_id": "t1", "name": "Sup",
                "active": True, "credit_limit": 1000.0}
    client, db = _build_client(monkeypatch, supplier=supplier, pos=[],
                               user=_make_user(), override_perm=False)

    body = _po_body(qty=20, unit_cost=100.0)  # 2000 > 1000
    body["override_credit_limit"] = True

    r = client.post("/api/procurement/purchase-orders", json=body)
    assert r.status_code == 403, r.text
    assert "manage_credit_limit" in r.json()["detail"]
    assert db.proc_purchase_orders.inserted == []


def test_override_with_permission_bypasses_guard(monkeypatch):
    """(e) With `manage_credit_limit`, override accepts an over-limit PO."""
    supplier = {"id": "sup1", "tenant_id": "t1", "name": "Sup",
                "active": True, "credit_limit": 1000.0}
    user = _make_user(granted=["manage_credit_limit"])
    client, db = _build_client(monkeypatch, supplier=supplier, pos=[],
                               user=user, override_perm=True)

    body = _po_body(qty=20, unit_cost=100.0)  # 2000 > 1000
    body["override_credit_limit"] = True

    r = client.post("/api/procurement/purchase-orders", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["grand_total"] == 2000.0
    assert len(db.proc_purchase_orders.inserted) == 1


def test_supplier_without_credit_limit_skips_guard(monkeypatch):
    """(f) Supplier with no `credit_limit` configured → guard is skipped."""
    supplier = {"id": "sup1", "tenant_id": "t1", "name": "Sup",
                "active": True, "credit_limit": None}
    # Existing huge open commitment must not matter when no limit is set.
    existing = [{"tenant_id": "t1", "supplier_id": "sup1",
                 "status": "sent", "grand_total": 999_999.0}]
    client, db = _build_client(monkeypatch, supplier=supplier,
                               pos=existing, user=_make_user())

    r = client.post("/api/procurement/purchase-orders",
                    json=_po_body(qty=100, unit_cost=100.0))
    assert r.status_code == 200, r.text
    assert len(db.proc_purchase_orders.inserted) == 1
