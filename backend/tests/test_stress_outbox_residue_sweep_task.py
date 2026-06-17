"""Safety + behaviour tests for ``celery_tasks.stress_outbox_residue_sweep_task``.

Plan A (Task #620): a dedicated nightly Celery beat that sweeps the stress
tenant's dead-PENDING ``guest.checked_in/out.v1`` outbox backlog, decoupled
from the e2e-stress suite teardown. These tests pin the fail-closed contract so
a bug in its guards or filter can never (a) delete production data outside the
stress tenant, (b) delete the pilot tenant's live data, (c) delete an in-flight
run's fresh events, (d) delete a real stuck PENDING delivery (masking a bug), or
(e) delete anything at all while the enable flag is off.

The task body uses ``_fresh_mongo`` for both the main scan/delete and the
metric write, so a single in-memory fake DB is injected by monkeypatching
``celery_tasks._fresh_mongo``.
"""
from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

pytestmark = pytest.mark.asyncio


# ── In-memory Mongo fake (narrow surface used by the task) ─────────────────


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
                    return False
            elif op == "$in":
                if doc_val not in ref:
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

    def _project(self, doc: dict) -> dict:
        if not self._projection:
            return copy.deepcopy(doc)
        out = {k: copy.deepcopy(doc[k]) for k in self._projection
               if self._projection[k] and k in doc}
        # _id is included unless explicitly excluded.
        if self._projection.get("_id", 1) and "_id" in doc:
            out["_id"] = copy.deepcopy(doc["_id"])
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
        d = copy.deepcopy(doc)
        d.setdefault("_id", f"oid-{len(self.docs)}")
        self.docs.append(d)

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
        self.stress_outbox_residue_scans = _FakeCollection()

    def __getitem__(self, name):
        return getattr(self, name)


class _FakeClient:
    def __init__(self, db: _FakeDB):
        self._db = db
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def fake_db(monkeypatch):
    import celery_tasks

    db = _FakeDB()

    def _fresh():
        return _FakeClient(db), db

    monkeypatch.setattr(celery_tasks, "_fresh_mongo", _fresh)
    return db


STRESS = "23377306-a501-4232-adc8-8aea50e243c0"
OTHER = "other-tenant"


def _old(hours: int = 48) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def _old_dt(hours: int = 48) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


def _fresh_ts() -> str:
    return datetime.now(UTC).isoformat()


def _seed_mixed(db: _FakeDB):
    # Old PENDING dead events in stress → targets.
    db.outbox_events.seed({
        "id": "ob-co", "tenant_id": STRESS, "status": "pending",
        "event_type": "guest.checked_out.v1", "created_at": _old(),
    })
    db.outbox_events.seed({
        "id": "ob-ci", "tenant_id": STRESS, "status": "pending",
        "event_type": "guest.checked_in.v1", "created_at": _old(),
    })
    # Old PENDING NON-dead event in stress → preserved (don't mask real stuck).
    db.outbox_events.seed({
        "id": "ob-other-evt", "tenant_id": STRESS, "status": "pending",
        "event_type": "booking.created.v1", "created_at": _old(),
    })
    # Old TERMINAL (processed), BSON datetime created_at → target.
    db.outbox_events.seed({
        "id": "ob-proc", "tenant_id": STRESS, "status": "processed",
        "event_type": "guest.checked_out.v1", "created_at": _old_dt(),
    })
    # Fresh PENDING dead event in stress → skipped by age guard.
    db.outbox_events.seed({
        "id": "ob-fresh", "tenant_id": STRESS, "status": "pending",
        "event_type": "guest.checked_out.v1", "created_at": _fresh_ts(),
    })
    # Old PENDING dead event in OTHER tenant → skipped by tenant guard.
    db.outbox_events.seed({
        "id": "ob-xt", "tenant_id": OTHER, "status": "pending",
        "event_type": "guest.checked_out.v1", "created_at": _old(),
    })


# ── Fail-closed guards ─────────────────────────────────────────────────────


async def test_missing_stress_tenant_no_delete(fake_db, monkeypatch):
    _seed_mixed(fake_db)
    monkeypatch.delenv("E2E_STRESS_TENANT_ID", raising=False)
    monkeypatch.setenv("STRESS_OUTBOX_SWEEP_ENABLED", "true")
    from celery_tasks import _stress_outbox_residue_sweep_async

    summary = await _stress_outbox_residue_sweep_async()

    assert summary["mode"] == "skipped_no_tenant"
    assert summary["applied"] == 0
    # Nothing deleted.
    assert len(fake_db.outbox_events.docs) == 6
    # A metric row is still recorded.
    assert len(fake_db.stress_outbox_residue_scans.inserts) == 1


async def test_pilot_tenant_blocked_no_delete(fake_db, monkeypatch):
    _seed_mixed(fake_db)
    import celery_tasks

    monkeypatch.setenv("E2E_STRESS_TENANT_ID", celery_tasks._PILOT_TENANT_UUID)
    monkeypatch.setenv("STRESS_OUTBOX_SWEEP_ENABLED", "true")

    summary = await celery_tasks._stress_outbox_residue_sweep_async()

    assert summary["mode"] == "pilot_blocked"
    assert summary["applied"] == 0
    assert len(fake_db.outbox_events.docs) == 6
    assert len(fake_db.stress_outbox_residue_scans.inserts) == 1


async def test_pilot_env_blocked_no_delete(fake_db, monkeypatch):
    _seed_mixed(fake_db)
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", OTHER)
    monkeypatch.setenv("PILOT_TENANT_ID", OTHER)
    monkeypatch.setenv("STRESS_OUTBOX_SWEEP_ENABLED", "true")
    from celery_tasks import _stress_outbox_residue_sweep_async

    summary = await _stress_outbox_residue_sweep_async()

    assert summary["mode"] == "pilot_blocked"
    assert summary["applied"] == 0
    assert len(fake_db.outbox_events.docs) == 6


async def test_disabled_flag_metric_only_no_delete(fake_db, monkeypatch):
    """Enable flag off (default) → scan + metric row, but zero deletions."""
    _seed_mixed(fake_db)
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", STRESS)
    monkeypatch.delenv("STRESS_OUTBOX_SWEEP_ENABLED", raising=False)
    monkeypatch.delenv("PILOT_TENANT_ID", raising=False)
    from celery_tasks import _stress_outbox_residue_sweep_async

    summary = await _stress_outbox_residue_sweep_async()

    assert summary["mode"] == "disabled"
    assert summary["enabled"] is False
    # Found the residue (2 dead-pending + 1 terminal) but applied nothing.
    assert summary["found_total"] == 3
    assert summary["applied"] == 0
    assert {d["id"] for d in fake_db.outbox_events.docs} == {
        "ob-co", "ob-ci", "ob-other-evt", "ob-proc", "ob-fresh", "ob-xt"
    }
    assert len(fake_db.stress_outbox_residue_scans.inserts) == 1
    assert fake_db.stress_outbox_residue_scans.inserts[0]["mode"] == "disabled"


# ── Apply path ─────────────────────────────────────────────────────────────


async def test_enabled_deletes_only_stress_dead_pending(fake_db, monkeypatch):
    _seed_mixed(fake_db)
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", STRESS)
    monkeypatch.setenv("STRESS_OUTBOX_SWEEP_ENABLED", "true")
    monkeypatch.delenv("PILOT_TENANT_ID", raising=False)
    from celery_tasks import _stress_outbox_residue_sweep_async

    summary = await _stress_outbox_residue_sweep_async()

    assert summary["mode"] == "apply"
    assert summary["found_total"] == 3
    assert summary["applied"] == 3

    ids = {d["id"] for d in fake_db.outbox_events.docs}
    # Dead pending + terminal stress residue gone.
    assert "ob-co" not in ids
    assert "ob-ci" not in ids
    assert "ob-proc" not in ids
    # Real stuck pending (non-dead type) preserved — not masked.
    assert "ob-other-evt" in ids
    # Fresh (age guard) + other-tenant (tenant guard) preserved.
    assert "ob-fresh" in ids
    assert "ob-xt" in ids


async def test_clean_tenant_zero_found(fake_db, monkeypatch):
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", STRESS)
    monkeypatch.setenv("STRESS_OUTBOX_SWEEP_ENABLED", "true")
    monkeypatch.delenv("PILOT_TENANT_ID", raising=False)
    from celery_tasks import _stress_outbox_residue_sweep_async

    summary = await _stress_outbox_residue_sweep_async()

    assert summary["found_total"] == 0
    assert summary["applied"] == 0
    assert fake_db.stress_outbox_residue_scans.inserts[0]["found_total"] == 0


async def test_batched_delete_handles_large_backlog(fake_db, monkeypatch):
    # 12 dead-pending rows with batch size 5 → 3 delete passes (5+5+2).
    for i in range(12):
        fake_db.outbox_events.seed({
            "id": f"ob-{i}", "tenant_id": STRESS, "status": "pending",
            "event_type": "guest.checked_in.v1", "created_at": _old(),
        })
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", STRESS)
    monkeypatch.setenv("STRESS_OUTBOX_SWEEP_ENABLED", "true")
    monkeypatch.setenv("STRESS_OUTBOX_SWEEP_BATCH", "5")
    monkeypatch.delenv("PILOT_TENANT_ID", raising=False)
    from celery_tasks import _stress_outbox_residue_sweep_async

    summary = await _stress_outbox_residue_sweep_async()

    assert summary["found_total"] == 12
    assert summary["applied"] == 12
    assert fake_db.outbox_events.docs == []
