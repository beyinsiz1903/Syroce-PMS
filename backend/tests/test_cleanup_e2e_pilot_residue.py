"""Safety regression tests for ``backend/scripts/cleanup_e2e_pilot_residue.py``.

The script sweeps E2E test residue from the pilot tenant. A bug in its
guards or filters could either (a) mutate production data outside the
pilot tenant or (b) cancel/void rows from an in-flight test run. These
tests pin the safety contract:

  * Missing ``E2E_PILOT_TENANT_ID`` → fail-closed, no DB access.
  * ``--apply`` without ``E2E_ALLOW_PILOT_CLEANUP=true`` → fail-closed.
  * Scan filters tenant_id, E2E_ prefix, AND a 24h age cutoff.
  * Dry-run never mutates bookings/charges (only writes the metric row).
  * Apply mode flips bookings → cancelled and charges → voided=true,
    and never touches guests.
"""
from __future__ import annotations

import copy
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

# Allow `from scripts import ...` like the sibling cleanup tests do.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import cleanup_e2e_pilot_residue as cleanup  # noqa: E402


# ── In-memory Mongo fake (narrow surface used by the script) ────────────


def _match_scalar(doc_val: Any, cond: Any) -> bool:
    if isinstance(cond, dict):
        for op, ref in cond.items():
            if op == "$lte":
                if doc_val is None:
                    return False
                try:
                    if not (doc_val <= ref):
                        return False
                except TypeError:
                    # Mixed str/datetime: this branch of the $or doesn't apply.
                    return False
            elif op == "$nin":
                if doc_val in ref:
                    return False
            elif op == "$in":
                if doc_val not in ref:
                    return False
            elif op == "$ne":
                if doc_val == ref:
                    return False
            elif op == "$regex":
                if not isinstance(doc_val, str):
                    return False
                import re

                if not re.search(ref, doc_val):
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

    async def to_list(self, length: int | None = None):
        return [copy.deepcopy(d) for d in self._docs[: length or len(self._docs)]]

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

    def __aiter__(self):
        raise AssertionError("collection itself is not async-iterable")

    async def update_many(self, filter_, update):
        sets = update.get("$set", {})
        n = 0
        for d in self.docs:
            if _matches(d, filter_):
                d.update(sets)
                n += 1

        class _Res:
            modified_count = n

        return _Res()

    async def insert_one(self, doc):
        self.inserts.append(copy.deepcopy(doc))


class _FakeDB:
    def __init__(self) -> None:
        self.bookings = _FakeCollection()
        self.guests = _FakeCollection()
        self.folio_charges = _FakeCollection()
        self.e2e_residue_scans = _FakeCollection()

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


PILOT = "pilot-tenant-xyz"
OTHER = "other-tenant"


def _seed_mixed(db: _FakeDB):
    # Old E2E rows in pilot → targets.
    db.bookings.seed({
        "id": "b-old", "tenant_id": PILOT, "guest_name": "E2E_abc_GUEST",
        "status": "checked_in", "created_at": _old(),
    })
    db.folio_charges.seed({
        "id": "c-old", "tenant_id": PILOT, "description": "E2E_abc_FOLIO line",
        "voided": False, "created_at": _old(),
    })
    db.guests.seed({
        "id": "g-old", "tenant_id": PILOT, "first_name": "E2E_abc_GUEST",
        "last_name": "Test", "created_at": _old(),
    })
    # Fresh E2E rows in pilot → skipped by age guard.
    db.bookings.seed({
        "id": "b-fresh", "tenant_id": PILOT, "guest_name": "E2E_zzz_GUEST",
        "status": "checked_in", "created_at": _fresh(),
    })
    # Old non-E2E row in pilot → skipped by prefix guard.
    db.bookings.seed({
        "id": "b-real", "tenant_id": PILOT, "guest_name": "Mr. Smith",
        "status": "checked_in", "created_at": _old(),
    })
    # Old E2E row in OTHER tenant → skipped by tenant guard.
    db.bookings.seed({
        "id": "b-other", "tenant_id": OTHER, "guest_name": "E2E_xxx_GUEST",
        "status": "checked_in", "created_at": _old(),
    })
    # Already cancelled E2E booking → skipped by status guard (no-op).
    db.bookings.seed({
        "id": "b-cancelled", "tenant_id": PILOT, "guest_name": "E2E_abc_GUEST",
        "status": "cancelled", "created_at": _old(),
    })


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_pilot_tenant_env_fails_closed(fake_db, monkeypatch, capsys):
    monkeypatch.delenv("E2E_PILOT_TENANT_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["cleanup_e2e_pilot_residue"])
    rc = await cleanup.main()
    assert rc == 2
    # No DB access whatsoever — including no metric row.
    assert fake_db.e2e_residue_scans.inserts == []


@pytest.mark.asyncio
async def test_apply_without_allow_env_fails_closed(fake_db, monkeypatch):
    monkeypatch.setenv("E2E_PILOT_TENANT_ID", PILOT)
    monkeypatch.delenv("E2E_ALLOW_PILOT_CLEANUP", raising=False)
    monkeypatch.setattr(sys, "argv", ["cleanup_e2e_pilot_residue", "--apply"])
    rc = await cleanup.main()
    assert rc == 2
    assert fake_db.e2e_residue_scans.inserts == []


@pytest.mark.asyncio
async def test_dry_run_finds_residue_but_writes_nothing(fake_db, monkeypatch):
    _seed_mixed(fake_db)
    monkeypatch.setenv("E2E_PILOT_TENANT_ID", PILOT)
    monkeypatch.setattr(sys, "argv", ["cleanup_e2e_pilot_residue"])
    rc = await cleanup.main()

    # Residue present → non-zero exit so cron can alert.
    assert rc == 1

    # Bookings/charges untouched.
    booking_ids = {b["id"]: b for b in fake_db.bookings.docs}
    assert booking_ids["b-old"]["status"] == "checked_in"
    assert booking_ids["b-real"]["status"] == "checked_in"
    assert booking_ids["b-other"]["status"] == "checked_in"
    assert fake_db.folio_charges.docs[0]["voided"] is False

    # Exactly one metric row, scoped to pilot, recording the find.
    assert len(fake_db.e2e_residue_scans.inserts) == 1
    summary = fake_db.e2e_residue_scans.inserts[0]
    assert summary["tenant_id"] == PILOT
    assert summary["mode"] == "dry_run"
    assert summary["found"]["bookings"] == 1  # only b-old
    assert summary["found"]["folio_charges"] == 1  # only c-old
    assert summary["found"]["guests"] == 1  # only g-old
    assert summary["found_total"] == 3
    assert summary["applied"] == {"bookings_cancelled": 0, "charges_voided": 0}


@pytest.mark.asyncio
async def test_apply_cancels_bookings_and_voids_charges_only_in_pilot(
    fake_db, monkeypatch
):
    _seed_mixed(fake_db)
    monkeypatch.setenv("E2E_PILOT_TENANT_ID", PILOT)
    monkeypatch.setenv("E2E_ALLOW_PILOT_CLEANUP", "true")
    monkeypatch.setattr(sys, "argv", ["cleanup_e2e_pilot_residue", "--apply"])
    rc = await cleanup.main()
    assert rc == 0  # residue handled

    booking_ids = {b["id"]: b for b in fake_db.bookings.docs}
    # Pilot E2E old booking → cancelled.
    assert booking_ids["b-old"]["status"] == "cancelled"
    assert booking_ids["b-old"]["cancellation_reason"] == "E2E pilot residue sweep"
    # Real guest, other tenant, fresh test, already-cancelled → never mutated.
    assert booking_ids["b-real"]["status"] == "checked_in"
    assert booking_ids["b-other"]["status"] == "checked_in"
    assert booking_ids["b-fresh"]["status"] == "checked_in"
    assert booking_ids["b-cancelled"]["status"] == "cancelled"
    assert "cancellation_reason" not in booking_ids["b-cancelled"]

    # Pilot E2E old charge → voided.
    c = fake_db.folio_charges.docs[0]
    assert c["voided"] is True
    assert c["void_reason"] == "E2E pilot residue sweep"

    # Guests reported but NEVER auto-deleted.
    assert fake_db.guests.docs[0]["first_name"] == "E2E_abc_GUEST"

    summary = fake_db.e2e_residue_scans.inserts[0]
    assert summary["mode"] == "apply"
    assert summary["applied"] == {"bookings_cancelled": 1, "charges_voided": 1}


@pytest.mark.asyncio
async def test_clean_pilot_returns_zero_exit(fake_db, monkeypatch):
    # No residue at all → rc 0, metric row still written with found_total=0.
    monkeypatch.setenv("E2E_PILOT_TENANT_ID", PILOT)
    monkeypatch.setattr(sys, "argv", ["cleanup_e2e_pilot_residue"])
    rc = await cleanup.main()
    assert rc == 0
    assert fake_db.e2e_residue_scans.inserts[0]["found_total"] == 0
