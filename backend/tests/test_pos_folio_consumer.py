"""Targeted tests for the IC POS->folio Outbox/Compensation consumer (Task #389).

Pins the contract of core.pos_folio_consumer:

  * pos.charge.posted.v1 inserts the folio charge(s) and recalculates the folio
    balance from the ledger (charges - payments) — never $inc.
  * Re-delivery of the same posted event is idempotent (DuplicateKey skip), so
    the charge is posted exactly once and the balance is unchanged.
  * Apply-time late-charge / AR guard: a charge targeting a NON-open folio is
    never silently written to it; it is routed to pos_late_charges instead.
  * A missing folio at apply time is retryable (not silently dropped).
  * pos.charge.reversed.v1 idempotently voids the charge(s) for the order and
    recalculates the balance; a second reversal is a safe no-op.
  * drain_pending_pos_charges applies queued posted events for a folio inline
    and marks them processed.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest
from pymongo.errors import DuplicateKeyError

from core import pos_folio_consumer as cons
from core.outbox_service import POS_CHARGE_POSTED, POS_CHARGE_REVERSED


# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------


def _resolve(doc: dict, key: str):
    cur = doc
    for part in key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _match(doc: dict, flt: dict) -> bool:
    for k, v in flt.items():
        dv = _resolve(doc, k)
        if isinstance(v, dict):
            if "$ne" in v and dv == v["$ne"]:
                return False
            if "$in" in v and dv not in v["$in"]:
                return False
            if "$type" in v:
                continue
        elif dv != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()

    async def to_list(self, _n):
        return list(self._docs)


class _Agg:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, _n):
        return list(self._docs)


class _Coll:
    def __init__(self, *, unique_pos_source=False):
        self.docs: list[dict] = []
        self.insert_calls = 0
        self._unique_pos_source = unique_pos_source

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if _match(d, flt):
                return copy.deepcopy(d)
        return None

    def find(self, flt, proj=None):
        return _Cursor([copy.deepcopy(d) for d in self.docs if _match(d, flt)])

    async def insert_one(self, doc, session=None):
        self.insert_calls += 1
        if self._unique_pos_source and doc.get("source_pos_order_id") is not None:
            for d in self.docs:
                if (
                    d.get("tenant_id") == doc.get("tenant_id")
                    and d.get("source_pos_order_id") == doc.get("source_pos_order_id")
                    and d.get("line_no") == doc.get("line_no")
                ):
                    raise DuplicateKeyError("dup pos source")
        self.docs.append(copy.deepcopy(doc))
        return SimpleNamespace(inserted_id=doc.get("id", "x"))

    async def update_one(self, flt, update, upsert=False, session=None):
        for d in self.docs:
            if _match(d, flt):
                if "$set" in update:
                    d.update(update["$set"])
                if "$setOnInsert" in update:
                    pass
                return SimpleNamespace(matched_count=1, modified_count=1)
        if upsert:
            new = {}
            for k, v in flt.items():
                if not isinstance(v, dict):
                    new[k] = v
            if "$set" in update:
                new.update(update["$set"])
            if "$setOnInsert" in update:
                new.update(update["$setOnInsert"])
            self.docs.append(new)
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=new.get("id"))
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def update_many(self, flt, update, session=None):
        n = 0
        for d in self.docs:
            if _match(d, flt):
                if "$set" in update:
                    d.update(update["$set"])
                n += 1
        return SimpleNamespace(matched_count=n, modified_count=n)

    def aggregate(self, pipeline):
        match = pipeline[0].get("$match", {})
        group = pipeline[1].get("$group", {})
        rows = [d for d in self.docs if _match(d, match)]
        if not rows:
            return _Agg([])
        sum_expr = group["total"]["$sum"]
        total = 0.0
        for d in rows:
            if isinstance(sum_expr, dict) and "$ifNull" in sum_expr:
                a, b = sum_expr["$ifNull"]
                fa = d.get(a[1:])
                val = fa if fa is not None else d.get(b[1:], 0)
            else:
                val = d.get(sum_expr[1:], 0)
            total += float(val or 0)
        return _Agg([{"_id": None, "total": total}])


class _FakeDB:
    def __init__(self):
        self.folios = _Coll()
        self.folio_charges = _Coll(unique_pos_source=True)
        self.payments = _Coll()
        self.pos_late_charges = _Coll()
        self.outbox_events = _Coll()

    def __getitem__(self, name):
        return getattr(self, name)


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(cons, "get_system_db", lambda: fake)

    async def _noop_index():
        return None

    monkeypatch.setattr(cons, "_ensure_folio_charge_index", _noop_index)
    return fake


def _charge(order_id="ORD1", line_no=0, total=100.0):
    return {
        "id": f"FC-{order_id}-{line_no}",
        "tenant_id": "tenant-A",
        "booking_id": "B1",
        "folio_id": "F1",
        "charge_type": "pos_fnb",
        "amount": total,
        "total": total,
        "voided": False,
        "source_pos_order_id": order_id,
        "line_no": line_no,
    }


def _posted_event(order_id="ORD1", charges=None):
    return {
        "id": f"EV-{order_id}",
        "tenant_id": "tenant-A",
        "event_type": POS_CHARGE_POSTED,
        "payload": {
            "tenant_id": "tenant-A",
            "folio_id": "F1",
            "source_pos_order_id": order_id,
            "booking_id": "B1",
            "charges": charges if charges is not None else [_charge(order_id)],
        },
    }


def _reversed_event(order_id="ORD1"):
    return {
        "id": f"REV-{order_id}",
        "tenant_id": "tenant-A",
        "event_type": POS_CHARGE_REVERSED,
        "payload": {
            "tenant_id": "tenant-A",
            "folio_id": "F1",
            "source_pos_order_id": order_id,
            "reason": "test reversal",
        },
    }


def _seed_open_folio(fake, balance=0.0):
    fake.folios.docs.append({
        "id": "F1", "tenant_id": "tenant-A", "status": "open",
        "booking_id": "B1", "guest_id": "G1", "balance": balance,
    })


# ---------------------------------------------------------------------------
# posted
# ---------------------------------------------------------------------------


async def test_posted_inserts_charge_and_recalcs_balance(_patch):
    _seed_open_folio(_patch)
    ok, msg = await cons.handle_ic_pos_event(_posted_event())
    assert ok, msg
    assert _patch.folio_charges.insert_calls == 1
    assert len(_patch.folio_charges.docs) == 1
    # balance recalculated from ledger (100 charge - 0 payment).
    assert _patch.folios.docs[0]["balance"] == 100.0


async def test_posted_balance_nets_payments(_patch):
    _seed_open_folio(_patch)
    _patch.payments.docs.append({
        "id": "P1", "tenant_id": "tenant-A", "folio_id": "F1",
        "amount": 30.0, "voided": False,
    })
    await cons.handle_ic_pos_event(_posted_event())
    assert _patch.folios.docs[0]["balance"] == 70.0


async def test_posted_redelivery_is_idempotent(_patch):
    _seed_open_folio(_patch)
    ev = _posted_event()
    await cons.handle_ic_pos_event(ev)
    ok, _ = await cons.handle_ic_pos_event(copy.deepcopy(ev))
    assert ok
    # second insert hit DuplicateKey -> skipped; exactly one charge, same balance.
    assert len(_patch.folio_charges.docs) == 1
    assert _patch.folios.docs[0]["balance"] == 100.0


async def test_posted_to_closed_folio_routes_late_charge_no_silent_write(_patch):
    _patch.folios.docs.append({
        "id": "F1", "tenant_id": "tenant-A", "status": "closed",
        "booking_id": "B1", "guest_id": "G1", "balance": 0.0,
    })
    ok, msg = await cons.handle_ic_pos_event(_posted_event())
    assert ok
    assert "late-charge" in msg
    # NO write to the closed folio.
    assert _patch.folio_charges.insert_calls == 0
    assert _patch.folios.docs[0]["balance"] == 0.0
    # Operator-visible AR record created instead.
    assert len(_patch.pos_late_charges.docs) == 1
    assert _patch.pos_late_charges.docs[0]["status"] == "pending_review"
    assert _patch.pos_late_charges.docs[0]["total"] == 100.0


async def test_posted_late_charge_is_idempotent(_patch):
    _patch.folios.docs.append({
        "id": "F1", "tenant_id": "tenant-A", "status": "checked_out",
        "booking_id": "B1", "balance": 0.0,
    })
    ev = _posted_event()
    await cons.handle_ic_pos_event(ev)
    await cons.handle_ic_pos_event(copy.deepcopy(ev))
    assert len(_patch.pos_late_charges.docs) == 1


async def test_posted_missing_folio_is_retryable(_patch):
    ok, msg = await cons.handle_ic_pos_event(_posted_event())
    assert not ok
    assert msg.startswith("retryable")
    assert _patch.folio_charges.insert_calls == 0


async def test_posted_malformed_is_permanent(_patch):
    ev = _posted_event()
    ev["tenant_id"] = ""
    ev["payload"]["tenant_id"] = ""
    ok, msg = await cons.handle_ic_pos_event(ev)
    assert not ok
    assert msg.startswith("permanent")


# ---------------------------------------------------------------------------
# reversed (compensation)
# ---------------------------------------------------------------------------


async def test_reversed_voids_charge_and_recalcs(_patch):
    _seed_open_folio(_patch, balance=100.0)
    _patch.folio_charges.docs.append(_charge())
    ok, msg = await cons.handle_ic_pos_event(_reversed_event())
    assert ok, msg
    assert _patch.folio_charges.docs[0]["voided"] is True
    # voided charge excluded from recalc -> balance back to 0.
    assert _patch.folios.docs[0]["balance"] == 0.0


async def test_double_reversal_is_safe_noop(_patch):
    _seed_open_folio(_patch, balance=100.0)
    _patch.folio_charges.docs.append(_charge())
    await cons.handle_ic_pos_event(_reversed_event())
    ok, msg = await cons.handle_ic_pos_event(_reversed_event())
    assert ok
    # second reversal modifies nothing (already voided).
    assert "reversed 0 charge" in msg
    assert _patch.folios.docs[0]["balance"] == 0.0


# ---------------------------------------------------------------------------
# drain
# ---------------------------------------------------------------------------


async def test_drain_applies_pending_and_marks_processed(_patch):
    _seed_open_folio(_patch)
    ev = _posted_event()
    ev["status"] = "pending"
    _patch.outbox_events.docs.append(ev)
    drained = await cons.drain_pending_pos_charges("tenant-A", "F1")
    assert drained == 1
    assert len(_patch.folio_charges.docs) == 1
    assert _patch.folios.docs[0]["balance"] == 100.0
    assert _patch.outbox_events.docs[0]["status"] == "processed"


async def test_drain_no_events_returns_zero(_patch):
    _seed_open_folio(_patch)
    assert await cons.drain_pending_pos_charges("tenant-A", "F1") == 0
