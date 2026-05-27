"""Regression tests for Idempotency-Key handling on the PMS-core folio
split / split-by-amount / city-ledger-transfer endpoints.

Task #102: tasks #60 and #80 protected charge / payment / refund /
void-charge / void-payment. The sibling endpoints on the same router
still create new folios and move balances around — a double-tap could
produce two ghost folios or transfer the same balance twice. These
tests pin the contract (mirrors test_pms_hardening_folio_idempotency.py):

  * First call with a key performs the operation and caches the response.
  * A replay with the same key returns the cached response — no second
    folio insert, no second transfer.
  * In-flight collision returns 409.
  * Different source folios share a key safely (per-source scope).
  * No header → classic behaviour; nothing is cached.
  * Failure path releases the slot so the same key can be retried.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from routers import pms_hardening as router_mod
from modules.pms_core import folio_hardening_service as fhs_mod


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []
        self.insert_calls = 0
        self.update_calls = 0

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                return {k: v for k, v in d.items()}
        return None

    async def insert_one(self, doc):
        self.insert_calls += 1
        if "_id" in doc:
            for d in self.docs:
                if d.get("_id") == doc["_id"]:
                    raise DuplicateKeyError("duplicate _id")
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("_id", "x"))

    async def update_one(self, flt, update, upsert=False):
        self.update_calls += 1
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
                else:
                    if dv != v:
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
        self.payments = _Coll()
        self.folio_operations = _Coll()
        self.pms_audit_trail = _Coll()
        self.city_ledger_transactions = _Coll()
        self.idempotency_keys = _Coll()
        self.counters = _Coll()


class _FakeRequest:
    def __init__(self, idem: str | None = None, *, header: str = "Idempotency-Key"):
        self.headers = {}
        if idem:
            self.headers[header] = idem


@pytest.fixture
def fake_user():
    return SimpleNamespace(
        id="u1",
        tenant_id="tenant-A",
        role="manager",
        name="Cashier One",
        email="cashier@example.com",
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake_db = _FakeDB()
    # Two open source folios — one per `req.source_folio_id` / `req.folio_id`
    # scope so we can prove per-source isolation under the same key.
    fake_db.folios.docs.append({
        "id": "F1",
        "tenant_id": "tenant-A",
        "status": "open",
        "booking_id": "B1",
        "folio_number": "1001",
        "balance": 200.0,
    })
    fake_db.folios.docs.append({
        "id": "F2",
        "tenant_id": "tenant-A",
        "status": "open",
        "booking_id": "B2",
        "folio_number": "1002",
        "balance": 200.0,
    })
    # Two chargeable rows on F1 for the charge-list `split` path.
    fake_db.folio_charges.docs.append({
        "id": "C1",
        "tenant_id": "tenant-A",
        "folio_id": "F1",
        "voided": False,
        "total": 80.0,
    })
    fake_db.folio_charges.docs.append({
        "id": "C2",
        "tenant_id": "tenant-A",
        "folio_id": "F1",
        "voided": False,
        "total": 40.0,
    })

    monkeypatch.setattr(router_mod, "db", fake_db)
    monkeypatch.setattr(fhs_mod, "db", fake_db)

    monkeypatch.setattr(
        router_mod.perm_svc, "enforce_permission", lambda *a, **kw: None
    )

    async def _noop(*_a, **_kw):
        return None

    monkeypatch.setattr(
        fhs_mod.FolioHardeningService, "_recalculate_folio_balance", _noop
    )
    monkeypatch.setattr(fhs_mod.FolioHardeningService, "_log_audit", _noop)

    # `split_folio` / `split_folio_by_amounts` import generate_folio_number;
    # the city-ledger path imports calculate_folio_balance. Stub both.
    import sys
    import types as _types

    utils_stub = _types.ModuleType("core.utils")

    async def _gen_folio_number(_tenant_id):
        utils_stub._n = getattr(utils_stub, "_n", 1000) + 1
        return str(utils_stub._n)

    async def _calc_balance(folio_id, _tenant_id):
        for d in fake_db.folios.docs:
            if d.get("id") == folio_id:
                return float(d.get("balance", 0))
        return 0.0

    utils_stub.generate_folio_number = _gen_folio_number
    utils_stub.calculate_folio_balance = _calc_balance
    sys.modules["core.utils"] = utils_stub

    return fake_db


# ---------------------------------------------------------------------------
# SPLIT (charge-list)
# ---------------------------------------------------------------------------


def _split_req(source="F1", charge_ids=("C1",)):
    return router_mod.SplitFolioRequest(
        source_folio_id=source,
        charge_ids=list(charge_ids),
        target_folio_type="guest",
        reason="VIP separation",
    )


async def test_split_replay_with_same_key_returns_one_folio(_patch, fake_user):
    r1 = await router_mod.api_split_folio(
        req=_split_req(),
        request=_FakeRequest("IDEM-SPLIT-1"),
        current_user=fake_user,
    )
    folios_after_first = len(_patch.folios.docs)
    r2 = await router_mod.api_split_folio(
        req=_split_req(),
        request=_FakeRequest("IDEM-SPLIT-1"),
        current_user=fake_user,
    )
    # Same payload back, and NO second folio insert on replay.
    assert r1["new_folio"]["id"] == r2["new_folio"]["id"]
    assert len(_patch.folios.docs) == folios_after_first


async def test_split_no_key_creates_two_ghost_folios(_patch, fake_user):
    folios_before = len(_patch.folios.docs)
    await router_mod.api_split_folio(
        req=_split_req(charge_ids=("C1",)),
        request=_FakeRequest(),
        current_user=fake_user,
    )
    # Restore C1 back to F1 so the second call also has work to do.
    for c in _patch.folio_charges.docs:
        if c["id"] == "C1":
            c["folio_id"] = "F1"
    await router_mod.api_split_folio(
        req=_split_req(charge_ids=("C1",)),
        request=_FakeRequest(),
        current_user=fake_user,
    )
    # Without a key, the classic path runs both times → two new folios.
    assert len(_patch.folios.docs) == folios_before + 2


async def test_split_in_flight_same_key_returns_409(_patch, fake_user):
    from shared_kernel.idempotency import _lock_id

    seeded = _lock_id("tenant-A", "folio_split:F1", "SPLIT-INFLIGHT")
    _patch.idempotency_keys.docs.append({
        "_id": seeded,
        "tenant_id": "tenant-A",
        "scope": "folio_split:F1",
        "idempotency_key": "SPLIT-INFLIGHT",
        "status": "processing",
    })
    folios_before = len(_patch.folios.docs)
    with pytest.raises(HTTPException) as exc:
        await router_mod.api_split_folio(
            req=_split_req(),
            request=_FakeRequest("SPLIT-INFLIGHT", header="X-Idempotency-Key"),
            current_user=fake_user,
        )
    assert exc.value.status_code == 409
    # No new folio inserted while the lock is processing.
    assert len(_patch.folios.docs) == folios_before


async def test_split_failure_releases_lock(_patch, fake_user):
    # Use a non-existent charge id → service returns success=False → 400.
    with pytest.raises(HTTPException) as exc:
        await router_mod.api_split_folio(
            req=_split_req(charge_ids=("MISSING",)),
            request=_FakeRequest("SPLIT-FAIL"),
            current_user=fake_user,
        )
    assert exc.value.status_code == 400
    # Slot released so the same key can be retried with valid state.
    assert len(_patch.idempotency_keys.docs) == 0


async def test_split_key_scoped_per_source_folio(_patch, fake_user):
    # F2 needs its own chargeable row for the second call to succeed.
    _patch.folio_charges.docs.append({
        "id": "C3",
        "tenant_id": "tenant-A",
        "folio_id": "F2",
        "voided": False,
        "total": 25.0,
    })
    r1 = await router_mod.api_split_folio(
        req=_split_req(source="F1", charge_ids=("C1",)),
        request=_FakeRequest("SAME-SPLIT"),
        current_user=fake_user,
    )
    r2 = await router_mod.api_split_folio(
        req=_split_req(source="F2", charge_ids=("C3",)),
        request=_FakeRequest("SAME-SPLIT"),
        current_user=fake_user,
    )
    # Same key but different source → two distinct new folios.
    assert r1["new_folio"]["id"] != r2["new_folio"]["id"]


# ---------------------------------------------------------------------------
# SPLIT BY AMOUNT
# ---------------------------------------------------------------------------


def _split_amt_req(source="F1", amounts=(50.0,)):
    return router_mod.SplitFolioByAmountRequest(
        source_folio_id=source,
        splits=[
            router_mod.FolioSplitItem(amount=a, target_folio_type="guest")
            for a in amounts
        ],
        reason="split-by-amount",
    )


async def test_split_by_amount_replay_with_same_key_returns_cached(_patch, fake_user):
    r1 = await router_mod.api_split_folio_by_amount(
        req=_split_amt_req(),
        request=_FakeRequest("SBA-1"),
        current_user=fake_user,
    )
    folios_after_first = len(_patch.folios.docs)
    charges_after_first = len(_patch.folio_charges.docs)
    r2 = await router_mod.api_split_folio_by_amount(
        req=_split_amt_req(),
        request=_FakeRequest("SBA-1"),
        current_user=fake_user,
    )
    # Same payload back, NO second set of folios / adjustment charges.
    assert r1 == r2
    assert len(_patch.folios.docs) == folios_after_first
    assert len(_patch.folio_charges.docs) == charges_after_first


async def test_split_by_amount_in_flight_returns_409(_patch, fake_user):
    from shared_kernel.idempotency import _lock_id

    seeded = _lock_id("tenant-A", "folio_split_by_amount:F1", "SBA-INFLIGHT")
    _patch.idempotency_keys.docs.append({
        "_id": seeded,
        "tenant_id": "tenant-A",
        "scope": "folio_split_by_amount:F1",
        "idempotency_key": "SBA-INFLIGHT",
        "status": "processing",
    })
    folios_before = len(_patch.folios.docs)
    with pytest.raises(HTTPException) as exc:
        await router_mod.api_split_folio_by_amount(
            req=_split_amt_req(),
            request=_FakeRequest("SBA-INFLIGHT", header="X-Idempotency-Key"),
            current_user=fake_user,
        )
    assert exc.value.status_code == 409
    assert len(_patch.folios.docs) == folios_before


async def test_split_by_amount_failure_releases_lock(_patch, fake_user):
    # Splits that swallow the whole source balance trip the service guard.
    with pytest.raises(HTTPException) as exc:
        await router_mod.api_split_folio_by_amount(
            req=_split_amt_req(amounts=(500.0,)),  # > source balance 200
            request=_FakeRequest("SBA-FAIL"),
            current_user=fake_user,
        )
    assert exc.value.status_code == 400
    assert len(_patch.idempotency_keys.docs) == 0


async def test_split_by_amount_no_key_runs_classic_path(_patch, fake_user):
    folios_before = len(_patch.folios.docs)
    r1 = await router_mod.api_split_folio_by_amount(
        req=_split_amt_req(amounts=(50.0,)),
        request=_FakeRequest(),
        current_user=fake_user,
    )
    assert r1["success"] is True
    # A second call without a key creates yet another new folio — proving
    # nothing got cached.
    r2 = await router_mod.api_split_folio_by_amount(
        req=_split_amt_req(amounts=(50.0,)),
        request=_FakeRequest(),
        current_user=fake_user,
    )
    assert r2["success"] is True
    assert len(_patch.folios.docs) == folios_before + 2


# ---------------------------------------------------------------------------
# CITY LEDGER TRANSFER
# ---------------------------------------------------------------------------


def _clt_req(folio="F1"):
    return router_mod.CityLedgerTransferRequest(
        folio_id=folio, account_id="ACC-9", reason="month-end"
    )


async def test_city_ledger_replay_with_same_key_transfers_once(_patch, fake_user):
    r1 = await router_mod.api_city_ledger_transfer(
        req=_clt_req(),
        request=_FakeRequest("CLT-1"),
        current_user=fake_user,
    )
    # The first call closed the folio. Re-open it so a real second call
    # WOULD transfer again — the cache must short-circuit before the
    # service runs.
    for d in _patch.folios.docs:
        if d["id"] == "F1":
            d["status"] = "open"
    transactions_before = len(_patch.city_ledger_transactions.docs)
    r2 = await router_mod.api_city_ledger_transfer(
        req=_clt_req(),
        request=_FakeRequest("CLT-1"),
        current_user=fake_user,
    )
    assert r1 == r2
    # Exactly one city-ledger transaction posted.
    assert len(_patch.city_ledger_transactions.docs) == transactions_before


async def test_city_ledger_in_flight_returns_409(_patch, fake_user):
    from shared_kernel.idempotency import _lock_id

    seeded = _lock_id("tenant-A", "folio_city_ledger:F1", "CLT-INFLIGHT")
    _patch.idempotency_keys.docs.append({
        "_id": seeded,
        "tenant_id": "tenant-A",
        "scope": "folio_city_ledger:F1",
        "idempotency_key": "CLT-INFLIGHT",
        "status": "processing",
    })
    txn_before = len(_patch.city_ledger_transactions.docs)
    with pytest.raises(HTTPException) as exc:
        await router_mod.api_city_ledger_transfer(
            req=_clt_req(),
            request=_FakeRequest("CLT-INFLIGHT", header="X-Idempotency-Key"),
            current_user=fake_user,
        )
    assert exc.value.status_code == 409
    assert len(_patch.city_ledger_transactions.docs) == txn_before


async def test_city_ledger_failure_releases_lock(_patch, fake_user):
    # Zero-balance folio trips the service "no outstanding balance" guard.
    for d in _patch.folios.docs:
        if d["id"] == "F1":
            d["balance"] = 0.0
    with pytest.raises(HTTPException) as exc:
        await router_mod.api_city_ledger_transfer(
            req=_clt_req(),
            request=_FakeRequest("CLT-FAIL"),
            current_user=fake_user,
        )
    assert exc.value.status_code == 400
    assert len(_patch.idempotency_keys.docs) == 0


async def test_city_ledger_key_scoped_per_folio(_patch, fake_user):
    r1 = await router_mod.api_city_ledger_transfer(
        req=_clt_req(folio="F1"),
        request=_FakeRequest("SAME-CLT"),
        current_user=fake_user,
    )
    r2 = await router_mod.api_city_ledger_transfer(
        req=_clt_req(folio="F2"),
        request=_FakeRequest("SAME-CLT"),
        current_user=fake_user,
    )
    # Same key but different source folio → two independent transfers.
    assert r1["success"] is True and r2["success"] is True
    assert len(_patch.city_ledger_transactions.docs) == 2
