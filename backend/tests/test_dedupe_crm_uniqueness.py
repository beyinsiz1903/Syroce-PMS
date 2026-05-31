"""Safety regression tests for ``backend/scripts/dedupe_crm_uniqueness.py``.

The script retires duplicate CRM client accounts / corporate contracts so the
Task #205 partial unique indexes can build. A bug in its guards could mutate
the pilot tenant without opt-in or run a destructive ``--apply`` without the
env gate. These tests pin the fail-closed contract and the pure (DB-free)
selection helpers.

The end-to-end dedupe/index-build behaviour is verified against a real
MongoDB (aggregation ``$group`` is impractical to fake faithfully); here we
pin only the parts that must hold regardless of the data: the canonical-row
choice, the pilot partition, and the refuse branches that return *before* any
DB access.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import dedupe_crm_uniqueness as dd  # noqa: E402


# ── Pure helper: canonical = oldest created_at, missing sorts last ──────


def test_canonical_sort_key_prefers_oldest_datetime():
    old = {"id": "a", "created_at": datetime(2024, 1, 1, tzinfo=UTC)}
    new = {"id": "b", "created_at": datetime(2024, 6, 1, tzinfo=UTC)}
    assert sorted([new, old], key=dd._canonical_sort_key)[0]["id"] == "a"


def test_canonical_sort_key_mixes_iso_string_and_datetime():
    # mice_accounts stores ISO strings, corporate_contracts datetimes; both
    # must normalize to a comparable value.
    iso_old = {"id": "a", "created_at": "2024-01-01T00:00:00+00:00"}
    dt_new = {"id": "b", "created_at": datetime(2024, 6, 1, tzinfo=UTC)}
    assert sorted([dt_new, iso_old], key=dd._canonical_sort_key)[0]["id"] == "a"


def test_canonical_sort_key_missing_created_at_sorts_last():
    has = {"id": "a", "created_at": "2024-05-01T00:00:00+00:00"}
    missing = {"id": "z"}
    assert sorted([missing, has], key=dd._canonical_sort_key)[0]["id"] == "a"


def test_canonical_sort_key_tiebreak_by_id():
    d1 = {"id": "b", "created_at": "2024-01-01T00:00:00+00:00"}
    d2 = {"id": "a", "created_at": "2024-01-01T00:00:00+00:00"}
    assert sorted([d1, d2], key=dd._canonical_sort_key)[0]["id"] == "a"


# ── Pure helper: pilot partition ───────────────────────────────────────


def _groups():
    return [
        {"tenant_id": "t1", "field": "tax_no"},
        {"tenant_id": "pilot", "field": "tax_no"},
        {"tenant_id": "t2", "field": "email"},
    ]


def test_partition_pilot_skips_pilot_when_not_opted_in():
    do, skip = dd._partition_pilot(_groups(), "pilot", allow_pilot=False)
    assert [g["tenant_id"] for g in skip] == ["pilot"]
    assert "pilot" not in [g["tenant_id"] for g in do]


def test_partition_pilot_includes_pilot_when_opted_in():
    do, skip = dd._partition_pilot(_groups(), "pilot", allow_pilot=True)
    assert skip == []
    assert "pilot" in [g["tenant_id"] for g in do]


def test_partition_pilot_no_pilot_configured_passes_all_through():
    do, skip = dd._partition_pilot(_groups(), None, allow_pilot=False)
    assert skip == []
    assert len(do) == 3


# ── Fail-closed guards in main() — all return *before* DB access ────────


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for var in ("E2E_PILOT_TENANT_ID", "PILOT_TENANT_ID",
                "ALLOW_CRM_DEDUPE", "ALLOW_PILOT_CRM_DEDUPE"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.asyncio
async def test_apply_without_allow_env_refuses(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog", "--apply"])
    monkeypatch.setenv("E2E_PILOT_TENANT_ID", "pilot")
    assert await dd.main() == 2


@pytest.mark.asyncio
async def test_apply_without_pilot_id_and_no_tenant_refuses(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog", "--apply"])
    monkeypatch.setenv("ALLOW_CRM_DEDUPE", "true")
    # No pilot id set and no --tenant pin → cannot guarantee pilot exclusion.
    assert await dd.main() == 2


@pytest.mark.asyncio
async def test_tenant_equals_pilot_without_optin_refuses(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog", "--tenant", "pilot"])
    monkeypatch.setenv("PILOT_TENANT_ID", "pilot")
    assert await dd.main() == 2
