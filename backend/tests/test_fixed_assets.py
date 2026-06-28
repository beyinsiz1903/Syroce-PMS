"""Targeted tests for Fixed assets + depreciation.

Pinned contract (Kademe 2):
  * accumulated_depreciation is recomputed from depreciation_entries (ledger),
    never $inc; book_value = cost - accumulated.
  * Straight-line monthly = (cost - salvage) / useful_life_months.
  * Declining-balance monthly = book_value * annual_rate/12, never below salvage.
  * run-depreciation is idempotent per (tenant, asset, period); reruns no-op.
  * All tenant-scoped; mutations accounting-tier RBAC.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.accounting import fixed_asset_router as fa


def _match(doc: dict, flt: dict) -> bool:
    for k, v in flt.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        out = [{kk: vv for kk, vv in d.items() if kk != "_id"} for d in self._docs]
        return out[:n] if n else out


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []

    def find(self, flt=None, proj=None):
        return _Cursor([d for d in self.docs if _match(d, flt or {})])

    async def find_one(self, flt, proj=None, sort=None):
        for d in self.docs:
            if _match(d, flt):
                return {kk: vv for kk, vv in d.items() if kk != "_id"}
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id", "x"))

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if _match(d, flt):
                d.update(update.get("$set", {}))
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


class _FakeDB:
    def __init__(self):
        self.fixed_assets = _Coll()
        self.depreciation_entries = _Coll()


TENANT = "tenant-A"


def _user(role="accountant", *, super_admin=False, tenant=TENANT):
    return SimpleNamespace(
        id="u1", user_id="u1", tenant_id=tenant, role=role, is_super_admin=super_admin,
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake = _FakeDB()
    monkeypatch.setattr(fa, "db", fake)
    return fake


async def _mk_asset(user=None, **kw):
    params = {
        "name": "Laptop", "acquisition_date": "2026-01-15", "acquisition_cost": 12000.0,
        "salvage_value": 0.0, "useful_life_months": 12, "method": "straight_line",
    }
    params.update(kw)
    return (await fa.create_asset(fa.AssetIn(**params), current_user=user or _user("accountant")))["asset"]


# ---------------------------------------------------------------------------
# Asset register
# ---------------------------------------------------------------------------
async def test_create_asset_rbac_denies(_patch):
    with pytest.raises(HTTPException) as exc:
        await _mk_asset(user=_user("front_desk"))
    assert exc.value.status_code == 403


async def test_salvage_must_be_below_cost(_patch):
    with pytest.raises(HTTPException) as exc:
        await _mk_asset(salvage_value=12000.0)
    assert exc.value.status_code == 400


async def test_declining_requires_rate(_patch):
    with pytest.raises(HTTPException) as exc:
        await _mk_asset(method="declining_balance", declining_rate=0)
    assert exc.value.status_code == 400


async def test_invalid_method_400(_patch):
    with pytest.raises(HTTPException) as exc:
        await _mk_asset(method="bogus")
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Straight-line schedule + depreciation
# ---------------------------------------------------------------------------
async def test_straight_line_schedule(_patch):
    a = await _mk_asset(acquisition_cost=12000.0, salvage_value=0.0, useful_life_months=12)
    out = await fa.asset_schedule(a["id"], current_user=_user("accountant"))
    sched = out["schedule"]
    assert len(sched) == 12
    assert sched[0]["depreciation"] == 1000.0
    assert sched[0]["period"] == "2026-01"
    assert sched[-1]["book_value"] == 0.0


async def test_run_depreciation_creates_entry_and_recalcs(_patch):
    a = await _mk_asset(acquisition_cost=12000.0, useful_life_months=12)
    out = await fa.run_depreciation(period="2026-01", current_user=_user("accountant"))
    assert out["created"] == 1
    assert out["total_depreciation"] == 1000.0
    got = await fa.get_asset(a["id"], current_user=_user("accountant"))
    assert got["asset"]["accumulated_depreciation"] == 1000.0
    assert got["asset"]["book_value"] == 11000.0


async def test_run_depreciation_idempotent(_patch):
    a = await _mk_asset(acquisition_cost=12000.0, useful_life_months=12)
    await fa.run_depreciation(period="2026-01", current_user=_user("accountant"))
    second = await fa.run_depreciation(period="2026-01", current_user=_user("accountant"))
    assert second["created"] == 0
    assert second["skipped"] == 1
    entries = [e for e in _patch.depreciation_entries.docs if e["asset_id"] == a["id"]]
    assert len(entries) == 1


async def test_depreciation_accumulates_across_periods(_patch):
    a = await _mk_asset(acquisition_cost=12000.0, useful_life_months=12)
    await fa.run_depreciation(period="2026-01", current_user=_user("accountant"))
    await fa.run_depreciation(period="2026-02", current_user=_user("accountant"))
    got = await fa.get_asset(a["id"], current_user=_user("accountant"))
    assert got["asset"]["accumulated_depreciation"] == 2000.0
    assert got["asset"]["book_value"] == 10000.0


async def test_future_acquisition_skipped(_patch):
    await _mk_asset(acquisition_date="2026-05-01", acquisition_cost=12000.0, useful_life_months=12)
    out = await fa.run_depreciation(period="2026-01", current_user=_user("accountant"))
    assert out["created"] == 0
    assert out["skipped"] == 1


# ---------------------------------------------------------------------------
# Declining balance + salvage clamp
# ---------------------------------------------------------------------------
async def test_declining_balance_first_month(_patch):
    # 10000 cost, 24% annual -> monthly 2% of book = 200 first month
    a = await _mk_asset(
        acquisition_cost=10000.0, salvage_value=1000.0, useful_life_months=60,
        method="declining_balance", declining_rate=24.0,
    )
    out = await fa.asset_schedule(a["id"], current_user=_user("accountant"))
    sched = out["schedule"]
    assert sched[0]["depreciation"] == 200.0
    assert sched[1]["depreciation"] == round((10000 - 200) * 0.02, 2)
    # never below salvage
    assert all(s["book_value"] >= 1000.0 - 0.01 for s in sched)


async def test_salvage_clamp_straight_line(_patch):
    a = await _mk_asset(
        acquisition_cost=1000.0, salvage_value=100.0, useful_life_months=9,
    )
    out = await fa.asset_schedule(a["id"], current_user=_user("accountant"))
    sched = out["schedule"]
    assert sched[0]["depreciation"] == 100.0  # (1000-100)/9
    assert sched[-1]["book_value"] >= 100.0 - 0.01
    total = round(sum(s["depreciation"] for s in sched), 2)
    assert total == 900.0


async def test_dispose_stops_being_active(_patch):
    a = await _mk_asset()
    await fa.dispose_asset(a["id"], current_user=_user("accountant"))
    out = await fa.run_depreciation(period="2026-02", current_user=_user("accountant"))
    assert out["created"] == 0
