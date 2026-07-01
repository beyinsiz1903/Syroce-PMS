"""Tests for the per-outlet, daily-resetting adisyon (check) number counter.

Task #601 T001. The restaurant POS must number adisyon (checks) sequentially
per outlet, resetting every business day — mirroring how Turkish F&B outlets
number their physical checks. Contract pinned here:

  * Sequential per (tenant_id, outlet_id, business_date): 1, 2, 3, ...
  * Independent counters per outlet — outlet A and outlet B both start at 1.
  * Resets on a new business_date.
  * Scoped per tenant — tenant B's counter is independent of tenant A's.
  * A concurrent first-insert race (DuplicateKeyError on upsert) is retried
    rather than bubbling, so two waiters never share a number.
  * `_get_pos_business_date` prefers the night-audit business_date on
    tenant_settings and falls back to the UTC date when unset.
"""
import asyncio
from datetime import UTC, datetime

import pytest
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from domains.pms.pos_fnb_router import pos_core


class _FakeCounterColl:
    """In-memory stand-in for db.pos_adisyon_counters supporting the atomic
    find_one_and_update($inc, upsert) the counter relies on."""

    def __init__(self):
        self.docs: list[dict] = []
        self.fail_upsert_once = False

    def _match(self, flt, d):
        return all(d.get(k) == v for k, v in flt.items())

    async def create_index(self, *a, **k):
        return "uq_adisyon_counter"

    async def find_one_and_update(self, flt, update, upsert=False, return_document=None):
        existing = next((d for d in self.docs if self._match(flt, d)), None)
        if existing is None:
            if not upsert:
                return None
            if self.fail_upsert_once:
                self.fail_upsert_once = False
                raise DuplicateKeyError("dup")
            doc = dict(flt)
            doc["seq"] = 0
            set_on_insert = update.get("$setOnInsert", {})
            doc.update(set_on_insert)
            self.docs.append(doc)
            existing = doc
        inc = update.get("$inc", {})
        for k, v in inc.items():
            existing[k] = existing.get(k, 0) + v
        return dict(existing)


class _FakeSettingsColl:
    def __init__(self, business_date=None):
        self._business_date = business_date

    async def find_one(self, flt, proj=None):
        if self._business_date is None:
            return None
        return {"tenant_id": flt.get("tenant_id"), "business_date": self._business_date}


@pytest.fixture(autouse=True)
def _reset_index_flag():
    pos_core._ADISYON_COUNTER_INDEX_READY = False
    yield
    pos_core._ADISYON_COUNTER_INDEX_READY = False


@pytest.mark.asyncio
async def test_sequential_per_outlet_and_date(monkeypatch):
    coll = _FakeCounterColl()
    monkeypatch.setattr(pos_core.db, "pos_adisyon_counters", coll, raising=False)

    n1 = await pos_core._next_adisyon_number("t1", "outletA", "2026-06-14")
    n2 = await pos_core._next_adisyon_number("t1", "outletA", "2026-06-14")
    n3 = await pos_core._next_adisyon_number("t1", "outletA", "2026-06-14")
    assert [n1, n2, n3] == [1, 2, 3]


@pytest.mark.asyncio
async def test_independent_counters_per_outlet(monkeypatch):
    coll = _FakeCounterColl()
    monkeypatch.setattr(pos_core.db, "pos_adisyon_counters", coll, raising=False)

    a1 = await pos_core._next_adisyon_number("t1", "outletA", "2026-06-14")
    b1 = await pos_core._next_adisyon_number("t1", "outletB", "2026-06-14")
    a2 = await pos_core._next_adisyon_number("t1", "outletA", "2026-06-14")
    assert a1 == 1
    assert b1 == 1  # outlet B has its own counter
    assert a2 == 2


@pytest.mark.asyncio
async def test_resets_on_new_business_date(monkeypatch):
    coll = _FakeCounterColl()
    monkeypatch.setattr(pos_core.db, "pos_adisyon_counters", coll, raising=False)

    d1 = await pos_core._next_adisyon_number("t1", "outletA", "2026-06-14")
    d1b = await pos_core._next_adisyon_number("t1", "outletA", "2026-06-14")
    d2 = await pos_core._next_adisyon_number("t1", "outletA", "2026-06-15")
    assert [d1, d1b] == [1, 2]
    assert d2 == 1  # new business day resets the counter


@pytest.mark.asyncio
async def test_scoped_per_tenant(monkeypatch):
    coll = _FakeCounterColl()
    monkeypatch.setattr(pos_core.db, "pos_adisyon_counters", coll, raising=False)

    t1 = await pos_core._next_adisyon_number("t1", "outletA", "2026-06-14")
    t2 = await pos_core._next_adisyon_number("t2", "outletA", "2026-06-14")
    assert t1 == 1
    assert t2 == 1  # tenant 2 independent of tenant 1


@pytest.mark.asyncio
async def test_none_outlet_defaults(monkeypatch):
    coll = _FakeCounterColl()
    monkeypatch.setattr(pos_core.db, "pos_adisyon_counters", coll, raising=False)

    n1 = await pos_core._next_adisyon_number("t1", None, "2026-06-14")
    n2 = await pos_core._next_adisyon_number("t1", None, "2026-06-14")
    assert [n1, n2] == [1, 2]
    # the row keys outlet_id as "default"
    assert coll.docs[0]["outlet_id"] == "default"


@pytest.mark.asyncio
async def test_concurrent_first_insert_race_retried(monkeypatch):
    coll = _FakeCounterColl()
    coll.fail_upsert_once = True  # first upsert hits a DuplicateKeyError
    monkeypatch.setattr(pos_core.db, "pos_adisyon_counters", coll, raising=False)

    # Even though the first upsert raises DuplicateKeyError, the retry loop must
    # recover and still return a valid sequential number (never bubble).
    n = await pos_core._next_adisyon_number("t1", "outletA", "2026-06-14")
    assert n == 1


@pytest.mark.asyncio
async def test_business_date_prefers_tenant_settings(monkeypatch):
    monkeypatch.setattr(
        pos_core.db, "tenant_settings", _FakeSettingsColl("2026-06-10"), raising=False
    )
    bd = await pos_core._get_pos_business_date("t1")
    assert bd == "2026-06-10"


@pytest.mark.asyncio
async def test_business_date_falls_back_to_utc(monkeypatch):
    monkeypatch.setattr(
        pos_core.db, "tenant_settings", _FakeSettingsColl(None), raising=False
    )
    bd = await pos_core._get_pos_business_date("t1")
    assert bd == datetime.now(UTC).date().isoformat()
