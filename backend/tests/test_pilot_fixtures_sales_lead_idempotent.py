"""Idempotency contract for the pilot sales-lead fixture.

Task #67 added `_ensure_sales_lead` to
`backend/domains/admin/router/pilot_fixtures.py`. The room_block and
kbs_report branches already had implicit coverage; this test pins the
new sales-lead branch so a future refactor cannot silently break the
F9C § 98 step J real-id cross-tenant IDOR probe.

Locks in:
  * Second `ensure_pilot_fixtures` call reuses the same `sales_lead_id`.
  * `created.sales_lead` flips True → False between the two calls.
  * Persisted doc carries `_kind="lead"`, `pilot_fixture=True`,
    `company_name="IDOR_PROBE_SEED"`.
  * `company_name` does NOT start with `E2E_` so the residue cleanup
    script's `^E2E_` regex (`backend/scripts/cleanup_e2e_pilot_residue
    .E2E_PREFIX_REGEX`) leaves the fixture alone.
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

import pytest

from domains.admin.router import pilot_fixtures
from scripts.cleanup_e2e_pilot_residue import E2E_PREFIX_REGEX


class _FakeColl:
    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    async def find_one(self, filter_: dict, _proj: dict | None = None):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in filter_.items()):
                return dict(doc)
        return None

    async def insert_one(self, doc: dict):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))


class _FakeDB:
    def __init__(self) -> None:
        self.room_blocks = _FakeColl()
        self.kbs_reports = _FakeColl()
        self.mice_opportunities = _FakeColl()


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(pilot_fixtures, "db", db)
    return db


@pytest.fixture
def pilot_tid(monkeypatch):
    tid = "pilot-tenant-test"
    monkeypatch.setenv("PILOT_TENANT_ID", tid)
    return tid


@pytest.fixture
def super_admin_user():
    return SimpleNamespace(id="admin-1", tenant_id="pilot-tenant-test",
                           role="super_admin")


@pytest.mark.asyncio
async def test_sales_lead_fixture_is_idempotent(
    fake_db, pilot_tid, super_admin_user,
):
    req = pilot_fixtures.PilotFixturesRequest(pilot_tenant_id=pilot_tid)

    first = await pilot_fixtures.ensure_pilot_fixtures(
        req=req, current_user=super_admin_user,
    )
    second = await pilot_fixtures.ensure_pilot_fixtures(
        req=req, current_user=super_admin_user,
    )

    # Same id on the second call → real idempotency, not a fresh insert.
    assert first["sales_lead_id"] == second["sales_lead_id"]
    assert first["sales_lead_id"]  # non-empty

    # `created.sales_lead` flips True → False on the second pass.
    assert first["created"]["sales_lead"] is True
    assert second["created"]["sales_lead"] is False

    # Exactly one persisted lead doc — no duplicate insert.
    leads = fake_db.mice_opportunities.docs
    assert len(leads) == 1
    doc = leads[0]

    # Contract the F9C § 98 step J IDOR probe relies on.
    assert doc["_kind"] == "lead"
    assert doc["pilot_fixture"] is True
    assert doc["tenant_id"] == pilot_tid
    assert doc["company_name"] == "IDOR_PROBE_SEED"
    assert doc["id"] == first["sales_lead_id"]

    # Residue-cleanup safety: the company_name must NOT match the
    # `^E2E_` regex that `cleanup_e2e_pilot_residue.py` sweeps on,
    # otherwise the long-lived fixture would be cancelled/voided after
    # 24h and the IDOR probe would fall back to BOGUS_UUID.
    assert not re.search(E2E_PREFIX_REGEX, doc["company_name"])
