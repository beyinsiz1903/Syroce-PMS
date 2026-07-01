"""Safety regression tests for ``backend/scripts/cleanup_stress_crm_residue.py``.

The script sweeps stress-test CRM residue (``corporate_contracts`` +
``mice_accounts``) from the dedicated stress tenant so the *global* CRM
uniqueness backstops can rebuild. A bug in its guards or filters could either
(a) delete production data outside the stress tenant, (b) delete the pilot
tenant's live data, or (c) delete rows from an in-flight stress run. These
tests pin the safety contract:

  * Missing ``E2E_STRESS_TENANT_ID`` → fail-closed, no DB access.
  * Stress tenant resolving to the pilot tenant → fail-closed.
  * ``--apply`` without ``E2E_ALLOW_STRESS_CLEANUP=true`` → fail-closed.
  * Scan filters tenant_id, E2E_ prefix, AND a 24h age cutoff.
  * Dry-run never deletes anything (only writes the metric row).
  * Apply mode HARD-DELETES residue rows, scoped to the stress tenant only.
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

from scripts import cleanup_stress_crm_residue as cleanup  # noqa: E402


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
        self.corporate_contracts = _FakeCollection()
        self.mice_accounts = _FakeCollection()
        self.stress_crm_residue_scans = _FakeCollection()

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


STRESS = "23377306-a501-4232-adc8-8aea50e243c0"
OTHER = "other-tenant"
PILOT = cleanup.PILOT_TENANT_UUID


def _seed_mixed(db: _FakeDB):
    # Old E2E_STRESS contract in stress tenant → target (created_at as BSON
    # datetime to exercise the mixed str/datetime $or branch).
    db.corporate_contracts.seed({
        "id": "ct-old", "tenant_id": STRESS,
        "company_name": "E2E_STRESS_123_AcmeCo", "rate_code": "E2E_STRESS_RC1",
        "contact_email": "e2e_stress@example.com",
        "created_at": datetime.now(UTC) - timedelta(hours=48),
    })
    # Old E2E mice client account in stress tenant → target.
    db.mice_accounts.seed({
        "id": "ma-old", "tenant_id": STRESS, "account_type": "client",
        "name": "E2E_STRESS_123_Account_01", "tax_no": "E2E_STRESS_TAX1",
        "email": "e2e_stress_acct@example.com",
        "stress_seed": True, "stress_prefix": "E2E_STRESS_123_",
        "created_at": _old(),
    })
    # Old E2E banquet competitor (also mice_accounts) → target.
    db.mice_accounts.seed({
        "id": "ma-comp", "tenant_id": STRESS, "account_type": "banquet_competitor",
        "name": "E2E_STRESS_123_Competitor_01",
        "stress_seed": True, "stress_prefix": "E2E_STRESS_123_",
        "created_at": _old(),
    })
    # Fresh E2E contract in stress tenant → skipped by age guard.
    db.corporate_contracts.seed({
        "id": "ct-fresh", "tenant_id": STRESS,
        "company_name": "E2E_STRESS_999_Fresh", "rate_code": "E2E_STRESS_RC9",
        "created_at": _fresh(),
    })
    # Old non-E2E contract in stress tenant → skipped by prefix guard.
    db.corporate_contracts.seed({
        "id": "ct-real", "tenant_id": STRESS,
        "company_name": "Acme Holdings", "rate_code": "CORP2026",
        "created_at": _old(),
    })
    # Old E2E account in OTHER tenant → skipped by tenant guard.
    db.mice_accounts.seed({
        "id": "ma-other", "tenant_id": OTHER, "account_type": "client",
        "name": "E2E_STRESS_123_Account_X", "created_at": _old(),
    })


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_stress_tenant_env_fails_closed(fake_db, monkeypatch):
    monkeypatch.delenv("E2E_STRESS_TENANT_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["cleanup_stress_crm_residue"])
    rc = await cleanup.main()
    assert rc == 2
    # No DB access whatsoever — including no metric row.
    assert fake_db.stress_crm_residue_scans.inserts == []


@pytest.mark.asyncio
async def test_pilot_tenant_blocked_fails_closed(fake_db, monkeypatch):
    # Even if E2E_STRESS_TENANT_ID is misconfigured to the pilot, refuse.
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", PILOT)
    monkeypatch.setattr(sys, "argv", ["cleanup_stress_crm_residue"])
    rc = await cleanup.main()
    assert rc == 2
    assert fake_db.stress_crm_residue_scans.inserts == []


@pytest.mark.asyncio
async def test_pilot_tenant_env_blocked_fails_closed(fake_db, monkeypatch):
    # PILOT_TENANT_ID env match is also blocked (even with a non-default UUID).
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", OTHER)
    monkeypatch.setenv("PILOT_TENANT_ID", OTHER)
    monkeypatch.setattr(sys, "argv", ["cleanup_stress_crm_residue"])
    rc = await cleanup.main()
    assert rc == 2
    assert fake_db.stress_crm_residue_scans.inserts == []


@pytest.mark.asyncio
async def test_apply_without_allow_env_fails_closed(fake_db, monkeypatch):
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", STRESS)
    monkeypatch.delenv("E2E_ALLOW_STRESS_CLEANUP", raising=False)
    monkeypatch.setattr(sys, "argv", ["cleanup_stress_crm_residue", "--apply"])
    rc = await cleanup.main()
    assert rc == 2
    assert fake_db.stress_crm_residue_scans.inserts == []


@pytest.mark.asyncio
async def test_dry_run_finds_residue_but_writes_nothing(fake_db, monkeypatch):
    _seed_mixed(fake_db)
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", STRESS)
    monkeypatch.delenv("PILOT_TENANT_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["cleanup_stress_crm_residue"])
    rc = await cleanup.main()

    # Residue present → non-zero exit so cron can alert.
    assert rc == 1

    # Nothing deleted.
    contract_ids = {c["id"] for c in fake_db.corporate_contracts.docs}
    account_ids = {a["id"] for a in fake_db.mice_accounts.docs}
    assert contract_ids == {"ct-old", "ct-fresh", "ct-real"}
    assert account_ids == {"ma-old", "ma-comp", "ma-other"}

    # Exactly one metric row, scoped to stress, recording the find.
    assert len(fake_db.stress_crm_residue_scans.inserts) == 1
    summary = fake_db.stress_crm_residue_scans.inserts[0]
    assert summary["tenant_id"] == STRESS
    assert summary["mode"] == "dry_run"
    assert summary["found"]["corporate_contracts"] == 1  # only ct-old
    assert summary["found"]["mice_accounts"] == 2  # ma-old + ma-comp
    assert summary["found_total"] == 3
    assert summary["applied"] == {
        "corporate_contracts": 0, "mice_accounts": 0,
    }


@pytest.mark.asyncio
async def test_apply_deletes_residue_only_in_stress(fake_db, monkeypatch):
    _seed_mixed(fake_db)
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", STRESS)
    monkeypatch.setenv("E2E_ALLOW_STRESS_CLEANUP", "true")
    monkeypatch.delenv("PILOT_TENANT_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["cleanup_stress_crm_residue", "--apply"])
    rc = await cleanup.main()
    assert rc == 0  # residue handled

    contract_ids = {c["id"] for c in fake_db.corporate_contracts.docs}
    account_ids = {a["id"] for a in fake_db.mice_accounts.docs}

    # Old E2E stress residue gone.
    assert "ct-old" not in contract_ids
    assert "ma-old" not in account_ids
    assert "ma-comp" not in account_ids

    # Fresh test, real contract, other tenant → preserved.
    assert "ct-fresh" in contract_ids
    assert "ct-real" in contract_ids
    assert "ma-other" in account_ids

    summary = fake_db.stress_crm_residue_scans.inserts[0]
    assert summary["mode"] == "apply"
    assert summary["applied"] == {
        "corporate_contracts": 1, "mice_accounts": 2,
    }


@pytest.mark.asyncio
async def test_clean_stress_returns_zero_exit(fake_db, monkeypatch):
    # No residue at all → rc 0, metric row still written with found_total=0.
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", STRESS)
    monkeypatch.delenv("PILOT_TENANT_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["cleanup_stress_crm_residue"])
    rc = await cleanup.main()
    assert rc == 0
    assert fake_db.stress_crm_residue_scans.inserts[0]["found_total"] == 0
