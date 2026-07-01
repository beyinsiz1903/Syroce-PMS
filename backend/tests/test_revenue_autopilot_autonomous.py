"""Targeted verification for Rota 1-A (autonomous Revenue Autopilot wiring).

Pins the three behaviours the task requires without a full Celery dispatch:
  1. ``calculate_optimal_prices`` produces a SEPARATE deterministic price per
     concrete ``room_type`` (not a single 'Standard'), and stays fail-closed for
     types without a real ``base_price > 0``.
  2. In ``full_auto`` mode the cycle emits ONE idempotent ``RATE_UPDATED`` outbox
     event per room_type/date; a duplicate re-run (retry / re-tick) does not
     double-write. ``supervised`` mode emits nothing (pending_approval).
  3. The beat dispatcher ticks every minute and, at each tenant's LOCAL
     configured time (DST-aware), enqueues it via an atomic per-local-day claim
     at most once per local day even across duplicate ticks. Outside that local
     time window it enqueues nothing.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pymongo.errors import DuplicateKeyError

pytestmark = pytest.mark.asyncio


# ── Narrow in-memory Mongo fake (only the surface these paths touch) ────────


def _match_scalar(doc_val: Any, cond: Any) -> bool:
    if isinstance(cond, dict):
        for op, ref in cond.items():
            if op == "$gt":
                if doc_val is None or not (doc_val > ref):
                    return False
            elif op == "$lt":
                if doc_val is None or not (doc_val < ref):
                    return False
            elif op == "$exists":
                present = doc_val is not None
                if present != ref:
                    return False
            else:
                raise AssertionError(f"unsupported op in fake: {op}")
        return True
    return doc_val == cond


def _matches(doc: dict, filter_: dict) -> bool:
    for k, v in filter_.items():
        if k == "$or":
            if not any(_matches(doc, sub) for sub in v):
                return False
        elif k == "$and":
            if not all(_matches(doc, sub) for sub in v):
                return False
        else:
            if not _match_scalar(doc.get(k), v):
                return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, _n):
        return list(self._docs)


class _Collection:
    def __init__(self):
        self.docs: list[dict] = []
        self._unique_keys: set[str] = set()

    def find(self, filter_=None, projection=None):
        filter_ = filter_ or {}
        out = [dict(d) for d in self.docs if _matches(d, filter_)]
        return _Cursor(out)

    async def find_one(self, filter_, projection=None):
        for d in self.docs:
            if _matches(d, filter_):
                return dict(d)
        return None

    async def count_documents(self, filter_):
        return sum(1 for d in self.docs if _matches(d, filter_))

    async def distinct(self, field, filter_=None):
        filter_ = filter_ or {}
        vals = []
        for d in self.docs:
            if _matches(d, filter_) and d.get(field) not in vals:
                vals.append(d.get(field))
        return vals

    async def insert_one(self, doc, session=None):
        ik = doc.get("idempotency_key")
        if "uniq_idem" in self._unique_keys and ik is not None:
            if any(e.get("idempotency_key") == ik for e in self.docs):
                raise DuplicateKeyError("dup idempotency_key")
        self.docs.append(dict(doc))

    async def create_index(self, keys, **kwargs):
        if kwargs.get("unique"):
            self._unique_keys.add("uniq_idem")
        return "idx"

    async def update_one(self, filter_, update, upsert=False):
        for d in self.docs:
            if _matches(d, filter_):
                if "$set" in update:
                    d.update(update["$set"])
                if "$setOnInsert" in update:
                    pass
                return _Res(matched=1, modified=1)
        if upsert:
            new = {}
            for k, v in filter_.items():
                if not isinstance(v, dict) and k not in ("$or", "$and"):
                    new[k] = v
            if "$setOnInsert" in update:
                new.update(update["$setOnInsert"])
            if "$set" in update:
                new.update(update["$set"])
            self.docs.append(new)
            return _Res(matched=0, modified=0, upserted=True)
        return _Res(matched=0, modified=0)


class _Res:
    def __init__(self, matched=0, modified=0, upserted=False):
        self.matched_count = matched
        self.modified_count = modified
        self.upserted_id = "x" if upserted else None


class _FakeDB:
    def __init__(self):
        self._cols: dict[str, _Collection] = {}

    def __getattr__(self, name):
        cols = self.__dict__.setdefault("_cols", {})
        if name not in cols:
            cols[name] = _Collection()
        return cols[name]


# ── 1. Per-room_type deterministic pricing + fail-closed ───────────────────


async def test_calculate_optimal_prices_per_room_type():
    from domains.ai.revenue_autopilot import RevenueAutopilot

    db = _FakeDB()
    db.rooms.docs = [
        {"tenant_id": "t1", "room_type": "Deluxe", "base_price": 200.0},
        {"tenant_id": "t1", "room_type": "Deluxe", "base_price": 220.0},
        {"tenant_id": "t1", "room_type": "Suite", "base_price": 400.0},
        # base_price 0 -> excluded by query AND fail-closed grouping
        {"tenant_id": "t1", "room_type": "Economy", "base_price": 0.0},
    ]
    ap = RevenueAutopilot(db)
    prices = await ap.calculate_optimal_prices("t1", [], {"avg_occupancy": 50.0})

    types = {p["room_type"]: p for p in prices}
    assert set(types) == {"Deluxe", "Suite"}  # Economy fail-closed (no base)
    assert types["Deluxe"]["current_price"] == 210.0  # (200+220)/2
    assert types["Suite"]["current_price"] == 400.0
    # No competitor data, occupancy<=75 -> demand_factor 1.0 -> optimal==base
    assert types["Deluxe"]["optimal_price"] == 210.0
    assert types["Suite"]["optimal_price"] == 400.0


async def test_calculate_optimal_prices_fail_closed_no_base():
    from domains.ai.revenue_autopilot import RevenueAutopilot

    db = _FakeDB()
    db.rooms.docs = [{"tenant_id": "t1", "room_type": "X", "base_price": 0.0}]
    ap = RevenueAutopilot(db)
    prices = await ap.calculate_optimal_prices("t1", [], {"avg_occupancy": 90.0})
    assert prices == []


async def test_competitor_rate_per_type_then_global_fallback():
    from domains.ai.revenue_autopilot import RevenueAutopilot

    db = _FakeDB()
    db.rooms.docs = [
        {"tenant_id": "t1", "room_type": "Deluxe", "base_price": 100.0},
        {"tenant_id": "t1", "room_type": "Suite", "base_price": 300.0},
    ]
    ap = RevenueAutopilot(db)
    competitors = [
        {"hotel": "A", "rate": 150.0, "room_type": "Deluxe"},
        {"hotel": "B", "rate": 250.0},  # no room_type -> global only
    ]
    prices = {p["room_type"]: p for p in
              await ap.calculate_optimal_prices("t1", competitors, {"avg_occupancy": 50.0})}
    # Deluxe uses its type-specific competitor avg (150)
    assert prices["Deluxe"]["optimal_price"] == 150.0
    # Suite has no type-specific competitor -> global avg (150+250)/2 = 200
    assert prices["Suite"]["optimal_price"] == 200.0


# ── 2. Autonomous RATE_UPDATED emission (idempotent) + mode gating ─────────


async def test_full_auto_emits_idempotent_rate_updated(monkeypatch):
    from datetime import UTC, datetime

    import domains.ai.revenue_autopilot as mod
    from domains.ai.revenue_autopilot import RevenueAutopilot

    # Canliya-gecis zirhi: emit yolu YALNIZCA cift kilit acikken test edilir.
    monkeypatch.setenv("REVENUE_AUTOPILOT_EMISSION_ENABLED", "true")
    monkeypatch.setenv("REVENUE_AUTOPILOT_PILOT_TENANTS", "t1")

    db = _FakeDB()
    await db.outbox_events.create_index([("idempotency_key", 1)], unique=True)
    db.rooms.docs = [
        {"tenant_id": "t1", "room_type": "Deluxe", "base_price": 200.0, "status": "available"},
        {"tenant_id": "t1", "room_type": "Suite", "base_price": 400.0, "status": "available"},
    ]
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    ap = RevenueAutopilot(db)
    ap.mode = "full_auto"
    r1 = await ap.daily_optimization_cycle("t1")
    assert any(a.get("rate_events_emitted") == 2 for a in r1["actions"])
    assert len(db.outbox_events.docs) == 2
    evt_types = {e["event_type"] for e in db.outbox_events.docs}
    assert evt_types == {"rate.updated.v1"}
    entity_ids = {e["entity_id"] for e in db.outbox_events.docs}
    assert entity_ids == {f"t1:{today}:Deluxe", f"t1:{today}:Suite"}

    # Re-run same day (retry / re-tick) -> idempotent, still 2 events.
    await ap.daily_optimization_cycle("t1")
    assert len(db.outbox_events.docs) == 2


async def test_supervised_mode_emits_no_events():
    from domains.ai.revenue_autopilot import RevenueAutopilot

    db = _FakeDB()
    await db.outbox_events.create_index([("idempotency_key", 1)], unique=True)
    db.rooms.docs = [
        {"tenant_id": "t1", "room_type": "Deluxe", "base_price": 200.0},
    ]
    ap = RevenueAutopilot(db)
    ap.mode = "supervised"
    report = await ap.daily_optimization_cycle("t1")
    assert len(db.outbox_events.docs) == 0
    assert any(a.get("status") == "pending_approval" for a in report["actions"])


# ── 2b. Canliya-gecis ZIRHI: global kill-switch + pilot allowlist (fail-closed)


async def test_full_auto_gated_when_killswitch_off(monkeypatch):
    """full_auto istense bile global kill-switch kapaliyken emit YOK (fail-closed
    shadow): emission_gated True, effective_mode supervised, outbox bos."""
    from domains.ai.revenue_autopilot import RevenueAutopilot

    monkeypatch.delenv("REVENUE_AUTOPILOT_EMISSION_ENABLED", raising=False)
    monkeypatch.setenv("REVENUE_AUTOPILOT_PILOT_TENANTS", "t1")

    db = _FakeDB()
    await db.outbox_events.create_index([("idempotency_key", 1)], unique=True)
    db.rooms.docs = [
        {"tenant_id": "t1", "room_type": "Deluxe", "base_price": 200.0},
    ]
    ap = RevenueAutopilot(db)
    ap.mode = "full_auto"
    report = await ap.daily_optimization_cycle("t1")
    assert len(db.outbox_events.docs) == 0
    assert report["emission_gated"] is True
    assert report["effective_mode"] == "supervised"
    assert any(
        a.get("status") == "emission_gated_fail_closed" for a in report["actions"]
    )


async def test_full_auto_gated_when_tenant_not_in_allowlist(monkeypatch):
    """Kill-switch acik ama tenant pilot allowlist'te DEGIL -> emit YOK."""
    from domains.ai.revenue_autopilot import RevenueAutopilot

    monkeypatch.setenv("REVENUE_AUTOPILOT_EMISSION_ENABLED", "true")
    monkeypatch.setenv("REVENUE_AUTOPILOT_PILOT_TENANTS", "some-other-tenant")

    db = _FakeDB()
    await db.outbox_events.create_index([("idempotency_key", 1)], unique=True)
    db.rooms.docs = [
        {"tenant_id": "t1", "room_type": "Deluxe", "base_price": 200.0},
    ]
    ap = RevenueAutopilot(db)
    ap.mode = "full_auto"
    report = await ap.daily_optimization_cycle("t1")
    assert len(db.outbox_events.docs) == 0
    assert report["emission_gated"] is True


async def test_autopilot_emission_allowed_double_lock(monkeypatch):
    """Cift kilit: ikisi birden saglanmadan asla True donmez (fail-closed)."""
    from domains.ai.revenue_autopilot import autopilot_emission_allowed

    monkeypatch.delenv("REVENUE_AUTOPILOT_EMISSION_ENABLED", raising=False)
    monkeypatch.delenv("REVENUE_AUTOPILOT_PILOT_TENANTS", raising=False)
    assert autopilot_emission_allowed("t1") is False  # ikisi de kapali

    monkeypatch.setenv("REVENUE_AUTOPILOT_EMISSION_ENABLED", "true")
    assert autopilot_emission_allowed("t1") is False  # allowlist bos

    monkeypatch.setenv("REVENUE_AUTOPILOT_PILOT_TENANTS", "t1,t2")
    assert autopilot_emission_allowed("t1") is True  # ikisi de acik
    assert autopilot_emission_allowed("t3") is False  # allowlist disi
    assert autopilot_emission_allowed("") is False  # bos tenant

    monkeypatch.setenv("REVENUE_AUTOPILOT_EMISSION_ENABLED", "false")
    assert autopilot_emission_allowed("t1") is False  # kill-switch kapali


# ── 3. Dispatcher local-time atomic per-local-day claim ────────────────────

# 23:00 UTC == 02:00 Europe/Istanbul (UTC+3, the default tenant timezone), i.e.
# the default local target hour the dispatcher fires at.
_ISTANBUL_0200_UTC = datetime(2026, 6, 26, 23, 0, tzinfo=UTC)


async def test_dispatcher_claims_each_tenant_once_per_local_day(monkeypatch):
    import celery_tasks

    db = _FakeDB()
    db.users.docs = [
        {"tenant_id": "t1", "is_active": True},
        {"tenant_id": "t2", "is_active": True},
        {"tenant_id": "t3", "active": False},  # inactive -> skipped
    ]
    enqueued: list[str] = []

    class _FakeTask:
        def apply_async(self, args=None, queue=None):
            assert queue == "pricing"
            enqueued.append(args[0])

    monkeypatch.setattr(celery_tasks, "_fresh_mongo", lambda: (_Closeable(), db))
    monkeypatch.setattr(celery_tasks, "revenue_autopilot_for_tenant", _FakeTask())
    # Tenants without tenant_settings fall back to the default Europe/Istanbul.
    monkeypatch.setattr(celery_tasks, "_now_utc", lambda: _ISTANBUL_0200_UTC)

    res1 = await celery_tasks._revenue_autopilot_dispatch_async()
    assert res1["success"] is True
    assert sorted(res1["queued"]) == ["t1", "t2"]
    assert sorted(enqueued) == ["t1", "t2"]

    # Second tick same local day -> no re-dispatch (atomic per-local-day claim).
    enqueued.clear()
    res2 = await celery_tasks._revenue_autopilot_dispatch_async()
    assert res2["queued"] == []
    assert enqueued == []


async def test_dispatcher_skips_tenants_outside_local_target_time(monkeypatch):
    import celery_tasks

    db = _FakeDB()
    db.users.docs = [{"tenant_id": "t1", "is_active": True}]
    enqueued: list[str] = []

    class _FakeTask:
        def apply_async(self, args=None, queue=None):
            enqueued.append(args[0])

    monkeypatch.setattr(celery_tasks, "_fresh_mongo", lambda: (_Closeable(), db))
    monkeypatch.setattr(celery_tasks, "revenue_autopilot_for_tenant", _FakeTask())
    # One hour earlier -> 01:00 Istanbul, before the 02:00 target -> no dispatch.
    monkeypatch.setattr(
        celery_tasks, "_now_utc",
        lambda: _ISTANBUL_0200_UTC.replace(hour=22),
    )

    res = await celery_tasks._revenue_autopilot_dispatch_async()
    assert res["success"] is True
    assert res["queued"] == []
    assert enqueued == []


async def test_dispatcher_uses_tenant_local_timezone(monkeypatch):
    import celery_tasks

    db = _FakeDB()
    db.users.docs = [
        {"tenant_id": "ist", "is_active": True},
        {"tenant_id": "nyc", "is_active": True},
    ]
    # nyc explicitly in America/New_York; at _ISTANBUL_0200_UTC it is NOT 02:00
    # local there, so only the Istanbul-default tenant should fire.
    db.tenant_settings.docs = [
        {"tenant_id": "nyc", "timezone": "America/New_York"},
    ]
    enqueued: list[str] = []

    class _FakeTask:
        def apply_async(self, args=None, queue=None):
            enqueued.append(args[0])

    monkeypatch.setattr(celery_tasks, "_fresh_mongo", lambda: (_Closeable(), db))
    monkeypatch.setattr(celery_tasks, "revenue_autopilot_for_tenant", _FakeTask())
    monkeypatch.setattr(celery_tasks, "_now_utc", lambda: _ISTANBUL_0200_UTC)

    res = await celery_tasks._revenue_autopilot_dispatch_async()
    assert res["queued"] == ["ist"]
    assert enqueued == ["ist"]


class _Closeable:
    def close(self):
        pass
