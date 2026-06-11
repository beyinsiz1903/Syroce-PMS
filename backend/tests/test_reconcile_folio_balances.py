"""Safety + correctness tests for ``scripts/reconcile_folio_balances.py``.

The folio-balance reconciliation backstop recomputes ``folio.balance`` from
the authoritative ledger (folio_charges - payments) for open folios and, in
apply mode, repairs drift left by the async POS (B) path. These tests pin
the safety contract and the detect/dry-run/apply behaviour:

  * ``--apply`` without ``FOLIO_RECON_ALLOW_APPLY=true`` → fail-closed.
  * Explicitly targeting the pilot tenant with ``--apply`` → fail-closed.
  * Injected drift is detected; healthy folios are not false-positives.
  * Dry-run never mutates folios (only writes the metric row).
  * Apply repairs the cached balance from the authoritative total, scoped to
    the right tenant + status==open.
  * The pilot tenant is scanned/reported but never mutated (pilot_drift=0).
"""
from __future__ import annotations

import copy
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import reconcile_folio_balances as recon  # noqa: E402

PILOT = recon.PILOT_TENANT_UUID
TENANT = "tenant-real-1"
OTHER = "tenant-real-2"


# ── In-memory Mongo fake (narrow surface: find/aggregate/update_one/distinct) ──


def _match_scalar(doc_val: Any, cond: Any) -> bool:
    if isinstance(cond, dict):
        for op, ref in cond.items():
            if op == "$in":
                if doc_val not in ref:
                    return False
            elif op == "$ne":
                if doc_val == ref:
                    return False
            elif op == "$regex":
                if not isinstance(doc_val, str) or not re.search(ref, doc_val):
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


def _ifnull(doc: dict, total_field: str, fallback_field: str) -> float:
    val = doc.get(total_field)
    if val is None:
        val = doc.get(fallback_field)
    return float(val or 0.0)


class _FakeCursor:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    def max_time_ms(self, _ms: int):
        return self

    async def to_list(self, length: int | None = None):
        return [copy.deepcopy(d) for d in self._docs[: length or len(self._docs)]]


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []
        self.inserts: list[dict] = []

    def seed(self, doc: dict) -> None:
        self.docs.append(copy.deepcopy(doc))

    def find(self, filter_, projection=None):
        return _FakeCursor([d for d in self.docs if _matches(d, filter_)])

    def aggregate(self, pipeline):
        # Supports: [ {$match}, {$group: {_id:"$folio_id", total:{$sum: ...}}} ]
        match = pipeline[0]["$match"]
        group = pipeline[1]["$group"]
        rows = [d for d in self.docs if _matches(d, match)]
        sum_spec = group["total"]["$sum"]
        buckets: dict[str, float] = {}
        for d in rows:
            fid = d.get("folio_id")
            if isinstance(sum_spec, dict) and "$ifNull" in sum_spec:
                tf, ff = sum_spec["$ifNull"]
                amt = _ifnull(d, tf.lstrip("$"), ff.lstrip("$"))
            else:
                amt = float(d.get(sum_spec.lstrip("$")) or 0.0)
            buckets[fid] = buckets.get(fid, 0.0) + amt
        return _FakeCursor([{"_id": k, "total": v} for k, v in buckets.items()])

    async def distinct(self, field, filter_=None):
        filter_ = filter_ or {}
        seen = []
        for d in self.docs:
            if _matches(d, filter_):
                val = d.get(field)
                if val not in seen:
                    seen.append(val)
        return seen

    async def update_one(self, filter_, update):
        sets = update.get("$set", {})
        for d in self.docs:
            if _matches(d, filter_):
                d.update(sets)

                class _Res:
                    modified_count = 1

                return _Res()

        class _Res0:
            modified_count = 0

        return _Res0()

    async def insert_one(self, doc):
        self.inserts.append(copy.deepcopy(doc))


class _FakeDB:
    def __init__(self) -> None:
        self.folios = _FakeCollection()
        self.folio_charges = _FakeCollection()
        self.payments = _FakeCollection()
        self.folio_balance_recon_scans = _FakeCollection()

    def __getitem__(self, name):
        return getattr(self, name)


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(recon, "get_system_db", lambda: db)
    return db


def _old() -> str:
    return (datetime.now(UTC) - timedelta(hours=2)).isoformat()


def _seed_folio(db, tenant, fid, balance, charges, payments, updated=None):
    db.folios.seed({
        "id": fid, "tenant_id": tenant, "booking_id": f"bk-{fid}",
        "balance": balance, "status": "open",
        "updated_at": updated or _old(),
    })
    for i, c in enumerate(charges):
        db.folio_charges.seed({
            "id": f"{fid}-c{i}", "tenant_id": tenant, "folio_id": fid,
            "total": c, "voided": False,
        })
    for i, p in enumerate(payments):
        db.payments.seed({
            "id": f"{fid}-p{i}", "tenant_id": tenant, "folio_id": fid,
            "amount": p, "voided": False,
        })


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_without_allow_env_fails_closed(fake_db, monkeypatch):
    monkeypatch.delenv("FOLIO_RECON_ALLOW_APPLY", raising=False)
    monkeypatch.setattr(sys, "argv",
                        ["reconcile_folio_balances", "--apply"])
    rc = await recon.main()
    assert rc == 2
    assert fake_db.folio_balance_recon_scans.inserts == []


@pytest.mark.asyncio
async def test_apply_pilot_target_fails_closed(fake_db, monkeypatch):
    monkeypatch.setenv("FOLIO_RECON_ALLOW_APPLY", "true")
    monkeypatch.setattr(
        sys, "argv",
        ["reconcile_folio_balances", "--apply", "--tenant", PILOT])
    rc = await recon.main()
    assert rc == 2
    assert fake_db.folio_balance_recon_scans.inserts == []


@pytest.mark.asyncio
async def test_dry_run_detects_drift_but_writes_nothing(fake_db, monkeypatch):
    # Drifting folio: authoritative = 300-100 = 200, but cached says 50.
    _seed_folio(fake_db, TENANT, "f-drift", 50.0, [200.0, 100.0], [100.0])
    # Healthy folio: authoritative = 150-150 = 0, cached = 0.
    _seed_folio(fake_db, TENANT, "f-ok", 0.0, [150.0], [150.0])

    monkeypatch.setattr(
        sys, "argv",
        ["reconcile_folio_balances", "--tenant", TENANT, "--grace-minutes", "5"])
    rc = await recon.main()
    assert rc == 1  # drift present → alertable exit

    # Nothing mutated.
    folios = {f["id"]: f for f in fake_db.folios.docs}
    assert folios["f-drift"]["balance"] == 50.0
    assert folios["f-ok"]["balance"] == 0.0

    assert len(fake_db.folio_balance_recon_scans.inserts) == 1
    summary = fake_db.folio_balance_recon_scans.inserts[0]
    assert summary["tenant_id"] == TENANT
    assert summary["mode"] == "dry_run"
    assert summary["found_total"] == 1
    assert summary["repaired"] == 0
    assert summary["folios_checked"] == 2
    drift = summary["sample_drifts"][0]
    assert drift["folio_id"] == "f-drift"
    assert drift["authoritative_balance"] == 200.0
    assert drift["cached_balance"] == 50.0
    assert drift["difference"] == 150.0
    # PII-free: only ids + numbers.
    assert set(drift.keys()) == {
        "folio_id", "booking_id", "cached_balance",
        "authoritative_balance", "difference",
    }


@pytest.mark.asyncio
async def test_apply_repairs_balance_from_authority(fake_db, monkeypatch):
    _seed_folio(fake_db, TENANT, "f-drift", 50.0, [200.0, 100.0], [100.0])
    _seed_folio(fake_db, TENANT, "f-ok", 0.0, [150.0], [150.0])

    monkeypatch.setenv("FOLIO_RECON_ALLOW_APPLY", "true")
    monkeypatch.setattr(
        sys, "argv",
        ["reconcile_folio_balances", "--apply", "--tenant", TENANT])
    rc = await recon.main()
    assert rc == 0  # all drift repaired

    folios = {f["id"]: f for f in fake_db.folios.docs}
    assert folios["f-drift"]["balance"] == 200.0  # recomputed from authority
    assert folios["f-ok"]["balance"] == 0.0       # untouched (was correct)

    summary = fake_db.folio_balance_recon_scans.inserts[0]
    assert summary["mode"] == "apply"
    assert summary["found_total"] == 1
    assert summary["repaired"] == 1


@pytest.mark.asyncio
async def test_voided_items_excluded_no_false_positive(fake_db, monkeypatch):
    # Voided charge/payment must be ignored, matching the B-path formula.
    fake_db.folios.seed({
        "id": "f1", "tenant_id": TENANT, "booking_id": "bk", "balance": 100.0,
        "status": "open", "updated_at": _old(),
    })
    fake_db.folio_charges.seed({
        "id": "c1", "tenant_id": TENANT, "folio_id": "f1",
        "total": 100.0, "voided": False})
    fake_db.folio_charges.seed({
        "id": "c2", "tenant_id": TENANT, "folio_id": "f1",
        "total": 999.0, "voided": True})  # ignored
    fake_db.payments.seed({
        "id": "p1", "tenant_id": TENANT, "folio_id": "f1",
        "amount": 500.0, "voided": True})  # ignored

    monkeypatch.setattr(
        sys, "argv", ["reconcile_folio_balances", "--tenant", TENANT])
    rc = await recon.main()
    assert rc == 0  # authoritative=100, cached=100 → balanced
    assert fake_db.folio_balance_recon_scans.inserts[0]["found_total"] == 0


@pytest.mark.asyncio
async def test_pilot_scanned_but_never_mutated(fake_db, monkeypatch):
    # Pilot has drift; an all-tenant apply must report it but not repair it.
    _seed_folio(fake_db, PILOT, "pf", 0.0, [500.0], [])  # authoritative=500
    _seed_folio(fake_db, TENANT, "tf", 0.0, [200.0], [])  # authoritative=200

    monkeypatch.setenv("FOLIO_RECON_ALLOW_APPLY", "true")
    monkeypatch.setattr(sys, "argv", ["reconcile_folio_balances", "--apply"])
    rc = await recon.main()
    # Pilot drift left unrepaired → non-zero exit.
    assert rc == 1

    folios = {f["id"]: f for f in fake_db.folios.docs}
    assert folios["pf"]["balance"] == 0.0    # pilot NEVER mutated
    assert folios["tf"]["balance"] == 200.0  # real tenant repaired

    by_tenant = {
        s["tenant_id"]: s
        for s in fake_db.folio_balance_recon_scans.inserts
    }
    assert by_tenant[PILOT]["mode"] == "dry_run"
    assert by_tenant[PILOT]["pilot_skipped_apply"] is True
    assert by_tenant[PILOT]["found_total"] == 1
    assert by_tenant[PILOT]["repaired"] == 0
    assert by_tenant[TENANT]["mode"] == "apply"
    assert by_tenant[TENANT]["repaired"] == 1


@pytest.mark.asyncio
async def test_grace_window_skips_fresh_folios(fake_db, monkeypatch):
    # A drifting folio updated just now is skipped (in-flight apply guard).
    _seed_folio(
        fake_db, TENANT, "f-fresh", 0.0, [300.0], [],
        updated=datetime.now(UTC).isoformat())

    monkeypatch.setattr(
        sys, "argv",
        ["reconcile_folio_balances", "--tenant", TENANT, "--grace-minutes", "5"])
    rc = await recon.main()
    assert rc == 0
    summary = fake_db.folio_balance_recon_scans.inserts[0]
    assert summary["folios_checked"] == 0
    assert summary["skipped_fresh"] == 1
    assert summary["found_total"] == 0
