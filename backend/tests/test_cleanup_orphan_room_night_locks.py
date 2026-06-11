"""Safety regression tests for ``backend/scripts/cleanup_orphan_room_night_locks.py``.

The script sweeps orphaned ``room_night_locks`` — locks whose owning booking is
missing/cancelled/no-show/checked-out — so empty rooms stop being rejected with
a phantom 409 at booking-creation time (Task #435). A bug in its guards or
filters could either (a) delete locks owned by a live/active booking, (b) delete
intentional OOO/OOS/maintenance/unmatched-hold inventory blocks, or (c) race an
in-flight booking creation. These tests pin the safety contract:

  * ``--apply`` without ``ALLOW_ORPHAN_LOCK_CLEANUP=true`` → fail-closed.
  * Active-booking locks and block/sentinel locks are NEVER orphans.
  * Missing booking, terminal booking, and missing-booking_id → orphans.
  * The age cutoff excludes fresh locks (no racing in-flight creation).
  * Dry-run never deletes anything (only writes the metric row).
  * Apply mode deletes ONLY the classified orphan rows, by exact tuple.
"""
from __future__ import annotations

import copy
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import cleanup_orphan_room_night_locks as cleanup  # noqa: E402


# ── In-memory Mongo fake (narrow surface used by the script) ────────────


def _match_scalar(doc_val: Any, cond: Any) -> bool:
    if isinstance(cond, dict):
        for op, ref in cond.items():
            if op == "$nin":
                if doc_val in ref:
                    return False
            elif op == "$in":
                if doc_val not in ref:
                    return False
            elif op == "$ne":
                if doc_val == ref:
                    return False
            else:
                raise AssertionError(f"unsupported op in test fake: {op}")
        return True
    return doc_val == cond


def _matches(doc: dict, filter_: dict) -> bool:
    for k, v in filter_.items():
        if k == "$and":
            if not all(_matches(doc, sub) for sub in v):
                return False
        elif k == "$or":
            if not any(_matches(doc, sub) for sub in v):
                return False
        else:
            if not _match_scalar(doc.get(k), v):
                return False
    return True


class _FakeCursor:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    def max_time_ms(self, _ms: int):
        return self

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return copy.deepcopy(next(self._iter))
        except StopIteration:
            raise StopAsyncIteration


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.inserts: list[dict] = []

    def seed(self, doc: dict) -> None:
        self.docs.append(copy.deepcopy(doc))

    def find(self, filter_, projection=None):
        return _FakeCursor([d for d in self.docs if _matches(d, filter_)])

    async def find_one(self, filter_, projection=None):
        for d in self.docs:
            if _matches(d, filter_):
                return copy.deepcopy(d)
        return None

    async def delete_many(self, filter_):
        keep = [d for d in self.docs if not _matches(d, filter_)]
        n = len(self.docs) - len(keep)
        self.docs = keep

        class _Res:
            deleted_count = n

        return _Res()

    async def insert_one(self, doc):
        self.inserts.append(copy.deepcopy(doc))


class _FakeDB:
    def __init__(self) -> None:
        self.room_night_locks = _FakeCollection()
        self.bookings = _FakeCollection()
        self.orphan_room_night_lock_scans = _FakeCollection()

    def __getitem__(self, name):
        return getattr(self, name)


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(cleanup, "db", db)
    return db


def _old(hours: int = 48) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def _fresh() -> str:
    return datetime.now(UTC).isoformat()


TENANT = "5bad4a34-6ee3-4566-9053-741b7375a9cf"
OTHER = "other-tenant"


def _seed_mixed(db: _FakeDB):
    # Live active booking + its lock → NOT orphan (keep).
    db.bookings.seed({"id": "bk-active", "tenant_id": TENANT, "status": "confirmed"})
    db.room_night_locks.seed({
        "tenant_id": TENANT, "room_id": "r1", "night_date": "2026-07-10",
        "booking_id": "bk-active", "lock_type": "booking", "created_at": _old(),
    })

    # Terminal (cancelled) booking + lingering lock → orphan (booking_terminal).
    db.bookings.seed({"id": "bk-cxl", "tenant_id": TENANT, "status": "cancelled"})
    db.room_night_locks.seed({
        "tenant_id": TENANT, "room_id": "r2", "night_date": "2026-07-11",
        "booking_id": "bk-cxl", "lock_type": "booking", "created_at": _old(),
    })

    # Ghost booking (no bookings row) — the f107faaf class → orphan (booking_missing).
    db.room_night_locks.seed({
        "tenant_id": TENANT, "room_id": "r3", "night_date": "2026-07-11",
        "booking_id": "f107faaf", "lock_type": "booking", "created_at": _old(),
    })

    # Missing booking_id → orphan (missing_booking_id).
    db.room_night_locks.seed({
        "tenant_id": TENANT, "room_id": "r4", "night_date": "2026-07-12",
        "booking_id": None, "lock_type": "booking", "created_at": _old(),
    })

    # OOO inventory block → NEVER orphan (excluded by lock_type AND prefix).
    db.room_night_locks.seed({
        "tenant_id": TENANT, "room_id": "r5", "night_date": "2026-07-11",
        "booking_id": "OOO:r5", "lock_type": "ooo", "created_at": _old(),
    })

    # OTA unmatched-hold sentinel → NEVER orphan (excluded by lock_type).
    db.room_night_locks.seed({
        "tenant_id": TENANT, "room_id": "sentinel", "night_date": "2026-07-11",
        "booking_id": "hold-xyz", "lock_type": "ota_unmatched_hold",
        "created_at": _old(),
    })

    # Fresh ghost lock → skipped by age guard (don't race in-flight creation).
    db.room_night_locks.seed({
        "tenant_id": TENANT, "room_id": "r6", "night_date": "2026-07-13",
        "booking_id": "ghost-fresh", "lock_type": "booking", "created_at": _fresh(),
    })

    # Ghost lock in OTHER tenant → present, only swept when unscoped.
    db.room_night_locks.seed({
        "tenant_id": OTHER, "room_id": "r7", "night_date": "2026-07-11",
        "booking_id": "ghost-other", "lock_type": "booking", "created_at": _old(),
    })


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_without_allow_env_fails_closed(fake_db, monkeypatch):
    monkeypatch.delenv("ALLOW_ORPHAN_LOCK_CLEANUP", raising=False)
    monkeypatch.setattr(sys, "argv", ["cleanup_orphan_room_night_locks", "--apply"])
    rc = await cleanup.main()
    assert rc == 2
    # No DB access whatsoever — including no metric row.
    assert fake_db.orphan_room_night_lock_scans.inserts == []


@pytest.mark.asyncio
async def test_dry_run_classifies_but_writes_nothing(fake_db, monkeypatch):
    _seed_mixed(fake_db)
    monkeypatch.setattr(
        sys, "argv", ["cleanup_orphan_room_night_locks", "--tenant", TENANT]
    )
    before = {(d["room_id"], d["booking_id"]) for d in fake_db.room_night_locks.docs}
    rc = await cleanup.main()

    # Orphans present → non-zero exit so cron can alert.
    assert rc == 1

    # Nothing deleted.
    after = {(d["room_id"], d["booking_id"]) for d in fake_db.room_night_locks.docs}
    assert before == after

    # Exactly one metric row recording the classification.
    assert len(fake_db.orphan_room_night_lock_scans.inserts) == 1
    summary = fake_db.orphan_room_night_lock_scans.inserts[0]
    assert summary["mode"] == "dry_run"
    assert summary["found_total"] == 3
    assert summary["by_cause"] == {
        "booking_terminal": 1,
        "booking_missing": 1,
        "missing_booking_id": 1,
    }
    assert summary["applied_deleted"] == 0


@pytest.mark.asyncio
async def test_apply_deletes_only_orphans(fake_db, monkeypatch):
    _seed_mixed(fake_db)
    monkeypatch.setenv("ALLOW_ORPHAN_LOCK_CLEANUP", "true")
    monkeypatch.setattr(
        sys, "argv", ["cleanup_orphan_room_night_locks", "--tenant", TENANT, "--apply"]
    )
    rc = await cleanup.main()
    assert rc == 0  # orphans handled

    remaining = {
        (d["room_id"], d["booking_id"]) for d in fake_db.room_night_locks.docs
    }
    # Orphans gone.
    assert ("r2", "bk-cxl") not in remaining
    assert ("r3", "f107faaf") not in remaining
    assert ("r4", None) not in remaining
    # Active, OOO, sentinel, fresh, and other-tenant → preserved.
    assert ("r1", "bk-active") in remaining
    assert ("r5", "OOO:r5") in remaining
    assert ("sentinel", "hold-xyz") in remaining
    assert ("r6", "ghost-fresh") in remaining
    assert ("r7", "ghost-other") in remaining

    summary = fake_db.orphan_room_night_lock_scans.inserts[0]
    assert summary["mode"] == "apply"
    assert summary["applied_deleted"] == 3


@pytest.mark.asyncio
async def test_booking_filter_focuses_single_ghost(fake_db, monkeypatch):
    _seed_mixed(fake_db)
    monkeypatch.setattr(
        sys, "argv",
        ["cleanup_orphan_room_night_locks", "--tenant", TENANT, "--booking", "f107faaf"],
    )
    rc = await cleanup.main()
    assert rc == 1
    summary = fake_db.orphan_room_night_lock_scans.inserts[0]
    assert summary["found_total"] == 1
    assert summary["by_cause"] == {"booking_missing": 1}
    assert summary["sample_orphans"][0]["booking_id"] == "f107faaf"
    assert summary["sample_orphans"][0]["night_date"] == "2026-07-11"


@pytest.mark.asyncio
async def test_unscoped_scan_covers_all_tenants(fake_db, monkeypatch):
    _seed_mixed(fake_db)
    monkeypatch.setattr(sys, "argv", ["cleanup_orphan_room_night_locks"])
    rc = await cleanup.main()
    assert rc == 1
    summary = fake_db.orphan_room_night_lock_scans.inserts[0]
    # 3 in TENANT + 1 ghost in OTHER.
    assert summary["found_total"] == 4
    assert summary["by_cause"]["booking_missing"] == 2


@pytest.mark.asyncio
async def test_clean_table_returns_zero_exit(fake_db, monkeypatch):
    # Only a live active booking lock → no orphans → rc 0, metric still written.
    fake_db.bookings.seed({"id": "bk", "tenant_id": TENANT, "status": "confirmed"})
    fake_db.room_night_locks.seed({
        "tenant_id": TENANT, "room_id": "r1", "night_date": "2026-07-10",
        "booking_id": "bk", "lock_type": "booking", "created_at": _old(),
    })
    monkeypatch.setattr(
        sys, "argv", ["cleanup_orphan_room_night_locks", "--tenant", TENANT]
    )
    rc = await cleanup.main()
    assert rc == 0
    assert fake_db.orphan_room_night_lock_scans.inserts[0]["found_total"] == 0
