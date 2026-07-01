"""Safety regression tests for ``scripts/cleanup_stress_outbox_residue.py``.

The script sweeps stress-test outbox + reconciliation residue from the
dedicated stress tenant so the platform-wide outbox monitoring/poller scans
stop COLLSCANning a dead PENDING backlog. A bug in its guards or filters could
either (a) delete production data outside the stress tenant, (b) delete the
pilot tenant's live data, (c) delete rows from an in-flight stress run, or
(d) delete a real stuck PENDING delivery (masking a delivery bug). These tests
pin the safety contract:

  * Missing ``E2E_STRESS_TENANT_ID`` → fail-closed, no DB access.
  * Stress tenant resolving to the pilot tenant → fail-closed.
  * ``--apply`` without ``E2E_ALLOW_STRESS_CLEANUP=true`` → fail-closed.
  * Scan filters tenant_id AND a 24h age cutoff.
  * Outbox: PENDING swept only for the no-consumer event types; PENDING of
    other types preserved; terminal states swept.
  * Dry-run never deletes anything (only writes the metric row).
  * Apply mode deletes residue scoped to the stress tenant only.
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

from scripts import cleanup_stress_outbox_residue as cleanup  # noqa: E402


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
            elif op == "$in":
                if doc_val not in ref:
                    return False
            elif op == "$nin":
                if doc_val in ref:
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
    def __init__(self, docs: list[dict], projection=None):
        self._docs = docs
        self._projection = projection
        self._limit: int | None = None

    def limit(self, n: int):
        self._limit = n
        return self

    def max_time_ms(self, _ms: int):
        return self

    def _project(self, doc: dict) -> dict:
        if not self._projection:
            return copy.deepcopy(doc)
        # Only the include-form ({field: 1, "_id": 0}) is used by the script.
        out = {k: copy.deepcopy(doc[k]) for k in self._projection
               if self._projection[k] and k in doc}
        return out

    async def to_list(self, length: int | None = None):
        docs = self._docs
        if self._limit is not None:
            docs = docs[: self._limit]
        n = length if length is not None else len(docs)
        return [self._project(d) for d in docs[:n]]


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.inserts: list[dict] = []

    def seed(self, doc: dict) -> None:
        self.docs.append(copy.deepcopy(doc))

    def find(self, filter_, projection=None):
        return _FakeCursor(
            [d for d in self.docs if _matches(d, filter_)], projection
        )

    async def count_documents(self, filter_, **_kw):
        return len([d for d in self.docs if _matches(d, filter_)])

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
        self.outbox_events = _FakeCollection()
        self.channel_reconciliation_cases = _FakeCollection()
        self.stress_outbox_residue_scans = _FakeCollection()

    def __getitem__(self, name):
        return getattr(self, name)


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(cleanup, "db", db)
    return db


def _old(hours: int = 48) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def _old_dt(hours: int = 48) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


def _fresh() -> str:
    return datetime.now(UTC).isoformat()


STRESS = "23377306-a501-4232-adc8-8aea50e243c0"
OTHER = "other-tenant"
PILOT = cleanup.PILOT_TENANT_UUID


def _seed_mixed(db: _FakeDB):
    # Old PENDING dead event (checked_out) in stress → target.
    db.outbox_events.seed({
        "id": "ob-co", "tenant_id": STRESS, "status": "pending",
        "event_type": "guest.checked_out.v1", "created_at": _old(),
    })
    # Old PENDING dead event (checked_in) in stress → target.
    db.outbox_events.seed({
        "id": "ob-ci", "tenant_id": STRESS, "status": "pending",
        "event_type": "guest.checked_in.v1", "created_at": _old(),
    })
    # Old PENDING NON-dead event in stress → preserved (don't mask real
    # stuck-delivery).
    db.outbox_events.seed({
        "id": "ob-other-evt", "tenant_id": STRESS, "status": "pending",
        "event_type": "booking.created.v1", "created_at": _old(),
    })
    # Old TERMINAL (processed) in stress, created_at as BSON datetime to
    # exercise the mixed str/datetime $or branch → target.
    db.outbox_events.seed({
        "id": "ob-proc", "tenant_id": STRESS, "status": "processed",
        "event_type": "guest.checked_out.v1", "created_at": _old_dt(),
    })
    # Fresh PENDING dead event in stress → skipped by age guard.
    db.outbox_events.seed({
        "id": "ob-fresh", "tenant_id": STRESS, "status": "pending",
        "event_type": "guest.checked_out.v1", "created_at": _fresh(),
    })
    # Old PENDING dead event in OTHER tenant → skipped by tenant guard.
    db.outbox_events.seed({
        "id": "ob-xt", "tenant_id": OTHER, "status": "pending",
        "event_type": "guest.checked_out.v1", "created_at": _old(),
    })

    # Old recon case in stress → target.
    db.channel_reconciliation_cases.seed({
        "id": "rc-old", "tenant_id": STRESS, "status": "resolved",
        "case_type": "rate_mismatch", "created_at": _old(),
    })
    # Fresh recon case in stress → skipped by age guard.
    db.channel_reconciliation_cases.seed({
        "id": "rc-fresh", "tenant_id": STRESS, "status": "open",
        "created_at": _fresh(),
    })
    # Old recon case in OTHER tenant → skipped by tenant guard.
    db.channel_reconciliation_cases.seed({
        "id": "rc-xt", "tenant_id": OTHER, "status": "resolved",
        "created_at": _old(),
    })


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_stress_tenant_env_fails_closed(fake_db, monkeypatch):
    monkeypatch.delenv("E2E_STRESS_TENANT_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["cleanup_stress_outbox_residue"])
    rc = await cleanup.main()
    assert rc == 2
    # No DB access whatsoever — including no metric row.
    assert fake_db.stress_outbox_residue_scans.inserts == []


@pytest.mark.asyncio
async def test_pilot_tenant_blocked_fails_closed(fake_db, monkeypatch):
    # Even if E2E_STRESS_TENANT_ID is misconfigured to the pilot, refuse.
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", PILOT)
    monkeypatch.setattr(sys, "argv", ["cleanup_stress_outbox_residue"])
    rc = await cleanup.main()
    assert rc == 2
    assert fake_db.stress_outbox_residue_scans.inserts == []


@pytest.mark.asyncio
async def test_pilot_tenant_env_blocked_fails_closed(fake_db, monkeypatch):
    # PILOT_TENANT_ID env match is also blocked (even with a non-default UUID).
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", OTHER)
    monkeypatch.setenv("PILOT_TENANT_ID", OTHER)
    monkeypatch.setattr(sys, "argv", ["cleanup_stress_outbox_residue"])
    rc = await cleanup.main()
    assert rc == 2
    assert fake_db.stress_outbox_residue_scans.inserts == []


@pytest.mark.asyncio
async def test_apply_without_allow_env_fails_closed(fake_db, monkeypatch):
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", STRESS)
    monkeypatch.delenv("E2E_ALLOW_STRESS_CLEANUP", raising=False)
    monkeypatch.setattr(sys, "argv", ["cleanup_stress_outbox_residue", "--apply"])
    rc = await cleanup.main()
    assert rc == 2
    assert fake_db.stress_outbox_residue_scans.inserts == []


@pytest.mark.asyncio
async def test_dry_run_finds_residue_but_writes_nothing(fake_db, monkeypatch):
    _seed_mixed(fake_db)
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", STRESS)
    monkeypatch.delenv("PILOT_TENANT_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["cleanup_stress_outbox_residue"])
    rc = await cleanup.main()

    # Residue present → non-zero exit so cron can alert.
    assert rc == 1

    # Nothing deleted.
    outbox_ids = {d["id"] for d in fake_db.outbox_events.docs}
    recon_ids = {d["id"] for d in fake_db.channel_reconciliation_cases.docs}
    assert outbox_ids == {
        "ob-co", "ob-ci", "ob-other-evt", "ob-proc", "ob-fresh", "ob-xt"
    }
    assert recon_ids == {"rc-old", "rc-fresh", "rc-xt"}

    # Exactly one metric row, scoped to stress, recording the find.
    assert len(fake_db.stress_outbox_residue_scans.inserts) == 1
    summary = fake_db.stress_outbox_residue_scans.inserts[0]
    assert summary["tenant_id"] == STRESS
    assert summary["mode"] == "dry_run"
    # ob-co + ob-ci (dead pending) + ob-proc (terminal) = 3
    assert summary["found"]["outbox_events"] == 3
    assert summary["found"]["channel_reconciliation_cases"] == 1  # rc-old
    assert summary["found_total"] == 4
    assert summary["applied"] == {
        "outbox_events": 0, "channel_reconciliation_cases": 0,
    }


@pytest.mark.asyncio
async def test_apply_deletes_residue_only_in_stress(fake_db, monkeypatch):
    _seed_mixed(fake_db)
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", STRESS)
    monkeypatch.setenv("E2E_ALLOW_STRESS_CLEANUP", "true")
    monkeypatch.delenv("PILOT_TENANT_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["cleanup_stress_outbox_residue", "--apply"])
    rc = await cleanup.main()
    assert rc == 0  # residue handled

    outbox_ids = {d["id"] for d in fake_db.outbox_events.docs}
    recon_ids = {d["id"] for d in fake_db.channel_reconciliation_cases.docs}

    # Dead pending + terminal stress residue gone.
    assert "ob-co" not in outbox_ids
    assert "ob-ci" not in outbox_ids
    assert "ob-proc" not in outbox_ids
    # Real stuck pending (non-dead type) preserved — not masked.
    assert "ob-other-evt" in outbox_ids
    # Fresh + other-tenant preserved.
    assert "ob-fresh" in outbox_ids
    assert "ob-xt" in outbox_ids

    # Old stress recon gone; fresh + other-tenant preserved.
    assert "rc-old" not in recon_ids
    assert "rc-fresh" in recon_ids
    assert "rc-xt" in recon_ids

    summary = fake_db.stress_outbox_residue_scans.inserts[0]
    assert summary["mode"] == "apply"
    assert summary["applied"] == {
        "outbox_events": 3, "channel_reconciliation_cases": 1,
    }


@pytest.mark.asyncio
async def test_clean_stress_returns_zero_exit(fake_db, monkeypatch):
    # No residue at all → rc 0, metric row still written with found_total=0.
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", STRESS)
    monkeypatch.delenv("PILOT_TENANT_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["cleanup_stress_outbox_residue"])
    rc = await cleanup.main()
    assert rc == 0
    assert fake_db.stress_outbox_residue_scans.inserts[0]["found_total"] == 0
