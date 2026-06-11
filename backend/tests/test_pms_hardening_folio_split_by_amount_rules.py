"""Boundary-rule regression tests for the PMS-core
`/pms-core/folio/split-by-amount` endpoint (task #421).

Tasks #419/#420 pinned SplitFolioDialog's three modes (by_item, even,
custom) with frontend tests. The frontend clamps the amounts before they
ever hit the wire, but a direct API call bypasses those clamps. These
tests prove the backend is fail-closed regardless of the client:

  * total transfer >= source balance is rejected (the original folio must
    keep at least 0.01) — equal and over-balance both rejected.
  * an empty `splits` array is rejected.
  * a non-positive split amount is rejected.
  * a closed / non-existent folio is rejected.
  * a foreign-tenant caller cannot reach another tenant's folio
    (cross-tenant IDOR is denied; the victim folio is untouched).
  * a valid split creates the target folios, transfers the exact amounts,
    and leaves at least 0.01 on the source.

The fakes mirror test_pms_hardening_folio_split_idempotency.py so the two
files stay consistent. `calculate_folio_balance` is stubbed to sum the
non-voided charges of a folio so the valid-path balance assertions are
real, not pre-seeded constants.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import pms_hardening as router_mod
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

    async def delete_one(self, flt):
        for i, d in enumerate(list(self.docs)):
            if all(d.get(k) == v for k, v in flt.items()):
                self.docs.pop(i)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

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

    def batch_size(self, _n):
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
        self.folios = _Coll()
        self.folio_charges = _Coll()
        self.folio_operations = _Coll()
        self.pms_audit_trail = _Coll()
        self.idempotency_keys = _Coll()
        self.counters = _Coll()


class _FakeRequest:
    def __init__(self, idem: str | None = None):
        self.headers = {}
        if idem:
            self.headers["Idempotency-Key"] = idem


def _user(tenant_id="tenant-A"):
    return SimpleNamespace(
        id="u1",
        tenant_id=tenant_id,
        role="manager",
        name="Cashier One",
        email="cashier@example.com",
    )


@pytest.fixture
def fake_user():
    return _user()


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake_db = _FakeDB()
    # Open source folio owned by tenant-A with a 200.0 balance backed by a
    # real charge so balance recalculation is meaningful.
    fake_db.folios.docs.append({
        "id": "F1",
        "tenant_id": "tenant-A",
        "status": "open",
        "booking_id": "B1",
        "folio_number": "1001",
        "balance": 200.0,
        "guest_id": "G1",
    })
    fake_db.folio_charges.docs.append({
        "id": "C-SRC",
        "tenant_id": "tenant-A",
        "folio_id": "F1",
        "voided": False,
        "total": 200.0,
    })
    # A closed folio (also tenant-A) for the status guard.
    fake_db.folios.docs.append({
        "id": "F-CLOSED",
        "tenant_id": "tenant-A",
        "status": "closed",
        "folio_number": "1002",
        "balance": 200.0,
    })

    monkeypatch.setattr(router_mod, "db", fake_db)
    monkeypatch.setattr(fhs_mod, "db", fake_db)
    monkeypatch.setattr(
        router_mod.perm_svc, "enforce_permission", lambda *a, **kw: None
    )

    async def _noop(*_a, **_kw):
        return None

    monkeypatch.setattr(fhs_mod.FolioHardeningService, "_log_audit", _noop)

    # Stub core.utils: folio numbers + a real balance = sum(non-voided totals).
    import sys
    import types as _types

    utils_stub = _types.ModuleType("core.utils")

    async def _gen_folio_number(_tenant_id):
        utils_stub._n = getattr(utils_stub, "_n", 2000) + 1
        return str(utils_stub._n)

    async def _calc_balance(folio_id, tenant_id):
        total = 0.0
        for c in fake_db.folio_charges.docs:
            if (
                c.get("folio_id") == folio_id
                and c.get("tenant_id") == tenant_id
                and not c.get("voided")
            ):
                total += float(c.get("total", 0) or 0)
        return round(total, 2)

    utils_stub.generate_folio_number = _gen_folio_number
    utils_stub.calculate_folio_balance = _calc_balance
    sys.modules["core.utils"] = utils_stub

    return fake_db


def _amt_req(source="F1", amounts=(50.0,)):
    return router_mod.SplitFolioByAmountRequest(
        source_folio_id=source,
        splits=[
            router_mod.FolioSplitItem(amount=a, target_folio_type="guest")
            for a in amounts
        ],
        reason="split-by-amount",
    )


_svc = fhs_mod.FolioHardeningService()


# ---------------------------------------------------------------------------
# REJECTIONS — total vs source balance
# ---------------------------------------------------------------------------


async def test_rejects_total_over_source_balance(_patch, fake_user):
    res = await _svc.split_folio_by_amounts(
        "tenant-A", "F1", [{"amount": 250.0}], "r", "u1"
    )
    assert res["success"] is False
    assert "küçük olmalı" in res["error"]
    # No target folio created.
    assert len(_patch.folios.docs) == 2


async def test_rejects_total_equal_source_balance(_patch, fake_user):
    # Exactly equal would leave 0.00 on the source — must be rejected.
    res = await _svc.split_folio_by_amounts(
        "tenant-A", "F1", [{"amount": 200.0}], "r", "u1"
    )
    assert res["success"] is False
    assert "küçük olmalı" in res["error"]


async def test_rejects_total_equal_via_multiple_splits(_patch, fake_user):
    res = await _svc.split_folio_by_amounts(
        "tenant-A", "F1", [{"amount": 120.0}, {"amount": 80.0}], "r", "u1"
    )
    assert res["success"] is False


# ---------------------------------------------------------------------------
# REJECTIONS — splits shape
# ---------------------------------------------------------------------------


async def test_rejects_empty_splits(_patch, fake_user):
    res = await _svc.split_folio_by_amounts("tenant-A", "F1", [], "r", "u1")
    assert res["success"] is False
    assert "En az bir hedef" in res["error"]


async def test_rejects_nonpositive_amount(_patch, fake_user):
    res = await _svc.split_folio_by_amounts(
        "tenant-A", "F1", [{"amount": 0}], "r", "u1"
    )
    assert res["success"] is False
    assert "0'dan büyük" in res["error"]

    res2 = await _svc.split_folio_by_amounts(
        "tenant-A", "F1", [{"amount": -10.0}], "r", "u1"
    )
    assert res2["success"] is False


# ---------------------------------------------------------------------------
# REJECTIONS — folio state / existence / tenant
# ---------------------------------------------------------------------------


async def test_rejects_closed_folio(_patch, fake_user):
    res = await _svc.split_folio_by_amounts(
        "tenant-A", "F-CLOSED", [{"amount": 10.0}], "r", "u1"
    )
    assert res["success"] is False
    assert "cannot split" in res["error"]


async def test_rejects_missing_folio(_patch, fake_user):
    res = await _svc.split_folio_by_amounts(
        "tenant-A", "DOES-NOT-EXIST", [{"amount": 10.0}], "r", "u1"
    )
    assert res["success"] is False
    assert "not found" in res["error"]


async def test_rejects_cross_tenant_idor(_patch, fake_user):
    # tenant-B cannot reach tenant-A's open folio F1.
    res = await _svc.split_folio_by_amounts(
        "tenant-B", "F1", [{"amount": 10.0}], "r", "u1"
    )
    assert res["success"] is False
    assert "not found" in res["error"]
    # The victim folio's balance is untouched, no target folio created.
    f1 = await _patch.folios.find_one({"id": "F1"})
    assert f1["balance"] == 200.0
    assert len(_patch.folios.docs) == 2


# ---------------------------------------------------------------------------
# ROUTER — HTTP status mapping
# ---------------------------------------------------------------------------


async def test_router_maps_rejection_to_400(_patch, fake_user):
    with pytest.raises(HTTPException) as exc:
        await router_mod.api_split_folio_by_amount(
            req=_amt_req(amounts=(250.0,)),
            request=_FakeRequest(),
            current_user=fake_user,
        )
    assert exc.value.status_code == 400
    # Nothing created on the rejected path.
    assert len(_patch.folios.docs) == 2


async def test_router_cross_tenant_returns_400_and_no_mutation(_patch):
    attacker = _user(tenant_id="tenant-B")
    with pytest.raises(HTTPException) as exc:
        await router_mod.api_split_folio_by_amount(
            req=_amt_req(source="F1", amounts=(10.0,)),
            request=_FakeRequest(),
            current_user=attacker,
        )
    assert exc.value.status_code == 400
    f1 = await _patch.folios.find_one({"id": "F1"})
    assert f1["balance"] == 200.0
    assert len(_patch.folios.docs) == 2


# ---------------------------------------------------------------------------
# HAPPY PATH — amounts transferred, source keeps >= 0.01
# ---------------------------------------------------------------------------


async def test_valid_split_transfers_amounts_and_keeps_remainder(_patch, fake_user):
    res = await router_mod.api_split_folio_by_amount(
        req=_amt_req(amounts=(50.0, 30.0)),
        request=_FakeRequest(),
        current_user=fake_user,
    )
    assert res["success"] is True
    assert res["target_count"] == 2
    assert round(res["transferred_amount"], 2) == 80.0

    # Two new target folios created (2 seeded + 2 new = 4).
    assert len(_patch.folios.docs) == 4

    # Each target folio carries exactly its transferred amount.
    transferred = sorted(f["transferred_amount"] for f in res["new_folios"])
    assert transferred == [30.0, 50.0]
    for nf in res["new_folios"]:
        stored = await _patch.folios.find_one({"id": nf["id"]})
        assert stored["tenant_id"] == "tenant-A"
        assert round(stored["balance"], 2) == round(nf["transferred_amount"], 2)

    # Source folio keeps the remainder (200 - 80 = 120, well above 0.01).
    src = await _patch.folios.find_one({"id": "F1"})
    assert round(src["balance"], 2) == 120.0
    assert src["balance"] >= 0.01


async def test_valid_split_just_under_balance_keeps_min_remainder(_patch, fake_user):
    # 199.99 of a 200.00 balance leaves exactly 0.01 — the minimum allowed.
    res = await router_mod.api_split_folio_by_amount(
        req=_amt_req(amounts=(199.99,)),
        request=_FakeRequest(),
        current_user=fake_user,
    )
    assert res["success"] is True
    src = await _patch.folios.find_one({"id": "F1"})
    assert round(src["balance"], 2) == 0.01
    assert src["balance"] >= 0.01
