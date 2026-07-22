"""Unit tests for the Folyo Böl garanti-folio endpoint (task #423).

A confirmed reservation can carry charges (e.g. restaurant) while `db.folios`
stays empty, because folios are created lazily at payment/split time. The
`/api/pms/reservations/{booking_id}/ensure-folio` endpoint guarantees an open
guest folio so the "Folyo Böl" flow opens instead of erroring with
"Bölünecek folyo bulunmuyor".

These tests prove:
  * charges-but-no-folio → a new open guest folio is created, orphan charges
    (folio_id empty / pointing at no existing folio) are bound to it, and the
    balance recalculates from the now-bound charges.
  * the endpoint is idempotent: an already-open folio is returned unchanged and
    no second folio is created (no mutation).
  * charges already living on a CLOSED folio are NOT re-bound (regression).
  * a missing booking returns 404.
  * a foreign-tenant caller cannot reach another tenant's booking (404, no
    mutation).

The fakes mirror test_pms_hardening_folio_split_by_amount_rules.py so the
folio test suite stays consistent.
"""
from __future__ import annotations

import sys
import types as _types
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import reservation_detail as router_mod
from modules.pms_core import folio_hardening_service as fhs_mod


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                return {k: v for k, v in d.items()}
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("_id", "x"))

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                if "$set" in update:
                    d.update(update["$set"])
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    def find(self, flt, proj=None):
        matches = []
        for d in self.docs:
            ok = True
            for k, v in flt.items():
                dv = d.get(k)
                if isinstance(v, dict) and "$in" in v:
                    if dv not in v["$in"]:
                        ok = False
                        break
                elif dv != v:
                    ok = False
                    break
            if ok:
                matches.append({k: vv for k, vv in d.items()})
        return _Cursor(matches)


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_a, **_kw):
        return self

    async def to_list(self, _limit):
        return list(self._docs)

    def __aiter__(self):
        self._i = 0
        return self

    async def __anext__(self):
        if self._i >= len(self._docs):
            raise StopAsyncIteration
        d = self._docs[self._i]
        self._i += 1
        return d


class _FakeDB:
    def __init__(self):
        self.bookings = _Coll()
        self.folios = _Coll()
        self.folio_charges = _Coll()
        self.reservation_activity_log = _Coll()
        self.pms_audit_trail = _Coll()


def _user(tenant_id="tenant-A"):
    return SimpleNamespace(
        id="u1",
        tenant_id=tenant_id,
        role="manager",
        name="Cashier One",
        email="cashier@example.com",
    )


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    db = _FakeDB()
    # Reservation owned by tenant-A.
    db.bookings.docs.append({
        "id": "B1", "tenant_id": "tenant-A", "guest_id": "G1",
    })
    monkeypatch.setattr(router_mod, "db", db)
    monkeypatch.setattr(fhs_mod, "db", db)
    monkeypatch.setattr(router_mod, "_enforce_perm", lambda *a, **kw: None)

    # Stub core.utils: folio numbers + balance = sum(non-voided totals).
    utils_stub = _types.ModuleType("core.utils")

    async def _gen_folio_number(_tenant_id):
        utils_stub._n = getattr(utils_stub, "_n", 5000) + 1
        return str(utils_stub._n)

    async def _calc_balance(folio_id, tenant_id):
        total = 0.0
        for c in db.folio_charges.docs:
            if (c.get("folio_id") == folio_id
                    and c.get("tenant_id") == tenant_id
                    and not c.get("voided")):
                total += float(c.get("total", 0) or 0)
        return round(total, 2)

    utils_stub.generate_folio_number = _gen_folio_number
    utils_stub.calculate_folio_balance = _calc_balance
    monkeypatch.setitem(sys.modules, "core.utils", utils_stub)

    return db


def _charge(cid, *, folio_id=None, total=0.0, voided=False, tenant_id="tenant-A", booking_id="B1"):
    return {
        "id": cid, "tenant_id": tenant_id, "booking_id": booking_id,
        "folio_id": folio_id, "total": total, "voided": voided,
    }


# ---------------------------------------------------------------------------
# CREATE + ORPHAN BACKFILL
# ---------------------------------------------------------------------------


async def test_creates_folio_and_binds_orphan_charges(fake_db):
    fake_db.folio_charges.docs.append(_charge("C1", folio_id=None, total=60.0))
    fake_db.folio_charges.docs.append(_charge("C2", folio_id="", total=40.0))

    res = await router_mod.ensure_folio("B1", current_user=_user(), _perm=None)

    assert res["success"] is True
    assert res["created"] is True
    assert res["bound_charges"] == 2

    # Exactly one new open guest folio.
    assert len(fake_db.folios.docs) == 1
    folio = fake_db.folios.docs[0]
    assert folio["status"] == "open"
    assert folio["folio_type"] == "guest"
    assert folio["booking_id"] == "B1"
    assert folio["tenant_id"] == "tenant-A"

    # Both orphan charges now point at the new folio.
    for cid in ("C1", "C2"):
        c = await fake_db.folio_charges.find_one({"id": cid})
        assert c["folio_id"] == folio["id"]

    # Balance recalculated from the bound charges (60 + 40).
    assert round(folio["balance"], 2) == 100.0
    assert round(res["folio"]["balance"], 2) == 100.0


# ---------------------------------------------------------------------------
# IDEMPOTENCY — open folio returned unchanged
# ---------------------------------------------------------------------------


async def test_idempotent_returns_existing_open_folio(fake_db):
    fake_db.folios.docs.append({
        "id": "F-OPEN", "tenant_id": "tenant-A", "booking_id": "B1",
        "status": "open", "folio_type": "guest", "folio_number": "1001",
        "balance": 25.0, "guest_id": "G1",
    })
    fake_db.folio_charges.docs.append(_charge("C1", folio_id="F-OPEN", total=25.0))

    res = await router_mod.ensure_folio("B1", current_user=_user(), _perm=None)

    assert res["success"] is True
    assert res["created"] is False
    assert res["bound_charges"] == 0
    assert res["folio"]["id"] == "F-OPEN"
    # No second folio created.
    assert len(fake_db.folios.docs) == 1


async def test_second_call_after_create_is_idempotent(fake_db):
    fake_db.folio_charges.docs.append(_charge("C1", folio_id=None, total=60.0))

    first = await router_mod.ensure_folio("B1", current_user=_user(), _perm=None)
    assert first["created"] is True
    created_id = first["folio"]["id"]

    second = await router_mod.ensure_folio("B1", current_user=_user(), _perm=None)
    assert second["created"] is False
    assert second["bound_charges"] == 0
    assert second["folio"]["id"] == created_id
    # Still exactly one folio.
    assert len(fake_db.folios.docs) == 1


# ---------------------------------------------------------------------------
# REGRESSION — charges on a CLOSED folio are NOT re-bound
# ---------------------------------------------------------------------------


async def test_does_not_rebind_charges_on_closed_folio(fake_db):
    fake_db.folios.docs.append({
        "id": "F-CLOSED", "tenant_id": "tenant-A", "booking_id": "B1",
        "status": "closed", "folio_type": "guest", "folio_number": "1002",
        "balance": 50.0,
    })
    fake_db.folio_charges.docs.append(_charge("C-CLOSED", folio_id="F-CLOSED", total=50.0))
    fake_db.folio_charges.docs.append(_charge("C-ORPHAN", folio_id=None, total=70.0))

    res = await router_mod.ensure_folio("B1", current_user=_user(), _perm=None)

    assert res["created"] is True
    # Only the genuine orphan is bound; the closed-folio charge is untouched.
    assert res["bound_charges"] == 1
    closed_charge = await fake_db.folio_charges.find_one({"id": "C-CLOSED"})
    assert closed_charge["folio_id"] == "F-CLOSED"
    orphan = await fake_db.folio_charges.find_one({"id": "C-ORPHAN"})
    assert orphan["folio_id"] == res["folio"]["id"]
    # New folio balance reflects only the bound orphan.
    assert round(res["folio"]["balance"], 2) == 70.0


# ---------------------------------------------------------------------------
# GUARDS — missing booking + cross-tenant
# ---------------------------------------------------------------------------


async def test_missing_booking_returns_404(fake_db):
    with pytest.raises(HTTPException) as exc:
        await router_mod.ensure_folio("DOES-NOT-EXIST", current_user=_user(), _perm=None)
    assert exc.value.status_code == 404
    assert len(fake_db.folios.docs) == 0


async def test_cross_tenant_caller_cannot_reach_booking(fake_db):
    fake_db.folio_charges.docs.append(_charge("C1", folio_id=None, total=60.0))
    attacker = _user(tenant_id="tenant-B")

    with pytest.raises(HTTPException) as exc:
        await router_mod.ensure_folio("B1", current_user=attacker, _perm=None)
    assert exc.value.status_code == 404
    # No folio created, victim charge untouched.
    assert len(fake_db.folios.docs) == 0
    c = await fake_db.folio_charges.find_one({"id": "C1"})
    assert c["folio_id"] is None
