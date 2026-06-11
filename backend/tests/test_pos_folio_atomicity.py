"""Task #360 — POS create-order atomic + idempotent folio posting.

Pinned contract:
  * Same idempotency_key replay (retry / double-tap / network replay) -> one
    pos_order + one charge set; second response is an idempotent replay.
  * Concurrent (here: serialized) posts to the SAME folio leave a correct
    final balance, recalculated from the ledger (never $inc).
  * A partial-failure re-post of the same source order cannot double-post the
    same charge line (the (tenant_id, source_pos_order_id, line_no) unique
    partial index dedups it at the DB layer).
  * No idempotency_key -> classic behaviour, every call inserts a fresh order.

These run against in-memory fakes that mimic Mongo unique partial indexes,
sessions and `with_transaction`. Real cross-process snapshot serialization is
provided by Mongo's folio lock document + driver retry and is not unit-testable
without a live replica set; the balance-correctness assertion here verifies the
recalc-from-ledger strategy that the lock makes race-safe.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from pymongo.errors import DuplicateKeyError

from domains.pms.pos_extensions import _idem
from domains.pms.pos_fnb_router import pos_core


# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, data):
        self._data = data

    async def to_list(self, _n):
        return list(self._data)


class _Coll:
    def __init__(self, name):
        self.name = name
        self.docs: list[dict] = []
        self.insert_calls = 0
        # (fields_tuple, partial_field_or_None)
        self._uniques: list[tuple[tuple[str, ...], str | None]] = []

    async def create_index(self, keys, *_a, **kw):
        if kw.get("unique"):
            fields = tuple(k for k, _ in keys)
            pfe = kw.get("partialFilterExpression") or {}
            partial_field = next(iter(pfe.keys()), None)
            self._uniques.append((fields, partial_field))
        return "idx"

    def _violates_unique(self, doc) -> bool:
        for fields, pf in self._uniques:
            if pf is not None and not isinstance(doc.get(pf), str):
                continue  # partial: row exempt from the index
            if not all(f in doc for f in fields):
                continue
            for d in self.docs:
                if all(d.get(f) == doc.get(f) for f in fields):
                    return True
        return False

    async def insert_one(self, doc, session=None):
        if self._violates_unique(doc):
            raise DuplicateKeyError("dup")
        self.insert_calls += 1
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id="x")

    async def find_one(self, flt, proj=None, session=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                r = dict(d)
                r.pop("_id", None)
                return r
        return None

    async def update_one(self, flt, update, upsert=False, session=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                if "$set" in update:
                    d.update(update["$set"])
                return SimpleNamespace(matched_count=1, modified_count=1)
        if upsert:
            newd = dict(flt)
            if "$setOnInsert" in update:
                newd.update(update["$setOnInsert"])
            if "$set" in update:
                newd.update(update["$set"])
            self.docs.append(newd)
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id="x")
        return SimpleNamespace(matched_count=0, modified_count=0)

    def aggregate(self, pipeline, session=None):
        match = pipeline[0]["$match"]
        group = pipeline[1]["$group"]
        rows = [d for d in self.docs if all(d.get(k) == v for k, v in match.items())]
        sum_spec = group["total"]["$sum"]
        total = 0.0
        for d in rows:
            if isinstance(sum_spec, dict) and "$ifNull" in sum_spec:
                a, b = sum_spec["$ifNull"]
                val = d.get(a[1:])
                if val is None:
                    val = d.get(b[1:])
                total += val or 0
            elif isinstance(sum_spec, str):
                total += d.get(sum_spec[1:]) or 0
        return _FakeCursor([{"total": total}] if rows else [])


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def with_transaction(self, cb, **_kw):
        return await cb(self)


class _FakeClient:
    async def start_session(self):
        return _FakeSession()


class _FakeDB:
    def __init__(self):
        self.client = _FakeClient()
        self._colls: dict[str, _Coll] = {}

    def _get(self, name) -> _Coll:
        if name not in self._colls:
            self._colls[name] = _Coll(name)
        return self._colls[name]

    def __getattr__(self, name):
        # Only collections reach here (real attrs handled normally).
        if name.startswith("_") or name == "client":
            raise AttributeError(name)
        return self._get(name)

    def __getitem__(self, name):
        return self._get(name)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_user():
    return SimpleNamespace(
        id="u1", tenant_id="tenant-A", role="manager",
        name="Cashier", email="c@example.com",
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake_db = _FakeDB()
    # Seed two menu items + an open folio with a booking.
    fake_db.pos_menu_items.docs.extend([
        {"id": "m1", "tenant_id": "tenant-A", "item_name": "Burger",
         "category": "food", "unit_price": 100.0},
        {"id": "m2", "tenant_id": "tenant-A", "item_name": "Cola",
         "category": "beverage", "unit_price": 50.0},
    ])
    fake_db.folios.docs.append({
        "id": "F1", "tenant_id": "tenant-A", "status": "open",
        "booking_id": "B1", "guest_id": "G1", "balance": 0.0,
    })

    monkeypatch.setattr(pos_core, "db", fake_db)

    async def _user(_creds):
        return SimpleNamespace(
            id="u1", tenant_id="tenant-A", role="manager",
            name="Cashier", email="c@example.com",
        )

    monkeypatch.setattr(pos_core, "get_current_user", _user)

    # Index-ready cache is process-global; reset so each test re-registers the
    # unique partial indexes on its fresh fake collections.
    _idem._INDEXES_READY.clear()
    return fake_db


def _req(items, *, folio_id="F1", idem=None):
    return pos_core.POSOrderCreateRequest(
        folio_id=folio_id,
        order_items=[pos_core.POSOrderItemRequest(item_id=i, quantity=q) for i, q in items],
        idempotency_key=idem,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_same_key_replay_single_order_and_charge_set(_patch):
    req = _req([("m1", 1), ("m2", 2)], idem="ORDER-1")
    r1 = await pos_core.create_pos_order(data=req, credentials=None)
    r2 = await pos_core.create_pos_order(data=_req([("m1", 1), ("m2", 2)], idem="ORDER-1"), credentials=None)

    assert r1["idempotent_replay"] is False
    assert r2["idempotent_replay"] is True
    assert r1["order_id"] == r2["order_id"]
    # Exactly one order, one charge set (2 lines), not doubled.
    assert _patch.pos_orders.insert_calls == 1
    assert len(_patch.folio_charges.docs) == 2


async def test_concurrent_same_folio_balance_is_correct(_patch):
    # Two genuine orders (distinct keys) to the SAME folio.
    await pos_core.create_pos_order(data=_req([("m1", 1)], idem="K1"), credentials=None)
    await pos_core.create_pos_order(data=_req([("m2", 1)], idem="K2"), credentials=None)

    # m1: 100 net -> total 118 ; m2: 50 net -> total 59 ; balance = 177.
    folio = await _patch.folios.find_one({"id": "F1", "tenant_id": "tenant-A"})
    assert folio["balance"] == pytest.approx(177.0)
    assert len(_patch.folio_charges.docs) == 2


async def test_partial_failure_repost_does_not_double_post_charges(_patch):
    """The (tenant, source_pos_order_id, line_no) unique partial index must
    dedup a re-post of the same source order's charges at the DB layer."""
    # Build one order's docs and persist its charges twice with the SAME
    # source order id (simulating a re-post after a partial failure).
    charge_docs = [
        {"id": "c0", "tenant_id": "tenant-A", "folio_id": "F1", "booking_id": "B1",
         "amount": 100.0, "total": 118.0, "voided": False,
         "source_pos_order_id": "ORD-X", "line_no": 0},
        {"id": "c1", "tenant_id": "tenant-A", "folio_id": "F1", "booking_id": "B1",
         "amount": 50.0, "total": 59.0, "voided": False,
         "source_pos_order_id": "ORD-X", "line_no": 1},
    ]
    await pos_core._ensure_pos_atomicity_indexes(folio_post=True)

    order_a = {"id": "ORD-X", "tenant_id": "tenant-A", "folio_id": "F1"}
    await pos_core._persist_pos_order_atomic(
        order_doc=order_a, charge_docs=[dict(c) for c in charge_docs],
        folio_id="F1", tenant_id="tenant-A", idempotency_key=None,
    )
    # Re-post the SAME source order's charges (order doc differs so it isn't a
    # key replay; the charge source index is what must dedup).
    order_b = {"id": "ORD-X2", "tenant_id": "tenant-A", "folio_id": "F1"}
    await pos_core._persist_pos_order_atomic(
        order_doc=order_b, charge_docs=[dict(c) for c in charge_docs],
        folio_id="F1", tenant_id="tenant-A", idempotency_key=None,
    )

    # Only the first charge set survived; the re-post was deduped.
    assert len(_patch.folio_charges.docs) == 2


async def test_no_key_creates_two_orders(_patch):
    r1 = await pos_core.create_pos_order(data=_req([("m1", 1)]), credentials=None)
    r2 = await pos_core.create_pos_order(data=_req([("m1", 1)]), credentials=None)
    assert r1["order_id"] != r2["order_id"]
    assert _patch.pos_orders.insert_calls == 2
    assert len(_patch.folio_charges.docs) == 2


async def test_index_ensure_failure_is_fail_closed_503(_patch, monkeypatch):
    from fastapi import HTTPException

    async def _boom(*_a, **_kw):
        raise RuntimeError("index perms lost")

    monkeypatch.setattr(pos_core, "_ensure_pos_atomicity_indexes", _boom)
    with pytest.raises(HTTPException) as exc:
        await pos_core.create_pos_order(data=_req([("m1", 1)], idem="K"), credentials=None)
    assert exc.value.status_code == 503


async def test_missing_folio_is_404(_patch):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await pos_core.create_pos_order(
            data=_req([("m1", 1)], folio_id="NOPE", idem="K"), credentials=None
        )
    assert exc.value.status_code == 404


@pytest.mark.parametrize("status", ["closed", "transferred", "voided"])
async def test_closed_folio_rejects_pos_charge(_patch, status):
    """Task #374 — POS create-order must refuse posting to a non-open folio
    (closed / checked-out / transferred / voided), in parity with the other
    folio-charge endpoints."""
    from fastapi import HTTPException

    _patch.folios.docs.append({
        "id": "FC", "tenant_id": "tenant-A", "status": status,
        "booking_id": "B2", "guest_id": "G2", "balance": 0.0,
    })

    with pytest.raises(HTTPException) as exc:
        await pos_core.create_pos_order(
            data=_req([("m1", 1)], folio_id="FC", idem="K"), credentials=None
        )
    assert exc.value.status_code == 400
    # Guard fires BEFORE any order / charge is written.
    assert _patch.pos_orders.insert_calls == 0
    assert len(_patch.folio_charges.docs) == 0


async def test_open_folio_normal_flow_unaffected(_patch):
    """The closed-folio guard must not break the normal open-folio path."""
    r = await pos_core.create_pos_order(
        data=_req([("m1", 1)], idem="OK1"), credentials=None
    )
    assert r["success"] is True
    assert r["idempotent_replay"] is False
    assert _patch.pos_orders.insert_calls == 1
    assert len(_patch.folio_charges.docs) == 1


async def test_no_folio_order_is_idempotent(_patch):
    r1 = await pos_core.create_pos_order(data=_req([("m1", 1)], folio_id=None, idem="NF1"), credentials=None)
    r2 = await pos_core.create_pos_order(data=_req([("m1", 1)], folio_id=None, idem="NF1"), credentials=None)
    assert r1["order_id"] == r2["order_id"]
    assert r2["idempotent_replay"] is True
    assert _patch.pos_orders.insert_calls == 1
    assert len(_patch.folio_charges.docs) == 0
