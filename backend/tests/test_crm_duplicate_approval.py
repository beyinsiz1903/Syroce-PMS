"""Task #176 — CRM duplicate guard + corporate-contract approval lifecycle.

Targeted unit coverage (no live server) for:
  * mice_accounts tenant-scoped duplicate tax_no/email guard (_assert_account_unique).
  * corporate_contracts tenant-scoped duplicate rate_code/contact_email guard
    (_assert_contract_unique).
  * corporate-contract approval state machine map (CONTRACT_APPROVAL_TRANSITIONS).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from routers.mice import AccountIn, _assert_account_unique
from domains.revenue.rms_router.sales import (
    CONTRACT_APPROVAL_TRANSITIONS,
    CorporateContractCreate,
    _assert_contract_unique,
)


def _fake_db(find_one_return):
    db = MagicMock()
    db.mice_accounts = MagicMock()
    db.mice_accounts.find_one = AsyncMock(return_value=find_one_return)
    db.corporate_contracts = MagicMock()
    db.corporate_contracts.find_one = AsyncMock(return_value=find_one_return)
    return db


# ── Account duplicate guard ──────────────────────────────────────


def _acct(**kw) -> AccountIn:
    base = {"name": "Acme", "tax_no": "TX1", "email": "a@b.invalid"}
    base.update(kw)
    return AccountIn(**base)


async def test_account_unique_passes_when_no_collision():
    db = _fake_db(None)
    await _assert_account_unique(db, "tenant-1", _acct())  # no raise


async def test_account_duplicate_tax_no_rejected():
    db = _fake_db({"id": "existing"})
    with pytest.raises(HTTPException) as exc:
        await _assert_account_unique(db, "tenant-1", _acct(email=None))
    assert exc.value.status_code == 409


async def test_account_duplicate_email_rejected():
    db = _fake_db({"id": "existing"})
    with pytest.raises(HTTPException) as exc:
        await _assert_account_unique(db, "tenant-1", _acct(tax_no=None))
    assert exc.value.status_code == 409


async def test_account_blank_identifiers_skip_check():
    db = _fake_db({"id": "existing"})  # would collide if queried
    await _assert_account_unique(db, "tenant-1", _acct(tax_no="  ", email=""))
    db.mice_accounts.find_one.assert_not_called()


async def test_account_update_excludes_self():
    db = _fake_db(None)
    await _assert_account_unique(db, "tenant-1", _acct(), exclude_id="self-id")
    flt = db.mice_accounts.find_one.call_args[0][0]
    assert flt["id"] == {"$ne": "self-id"}
    assert flt["tenant_id"] == "tenant-1"


# ── Contract duplicate guard ─────────────────────────────────────


def _contract(**kw) -> CorporateContractCreate:
    base = {
        "company_name": "Acme", "contract_type": "negotiated",
        "rate_code": "RC1", "start_date": "2026-01-01", "end_date": "2026-12-31",
        "contact_person": "P", "contact_email": "c@b.invalid",
        "contact_phone": "+900000000000",
    }
    base.update(kw)
    return CorporateContractCreate(**base)


async def test_contract_unique_passes_when_no_collision(monkeypatch):
    import domains.revenue.rms_router.sales as sales
    monkeypatch.setattr(sales, "db", _fake_db(None))
    await _assert_contract_unique("tenant-1", _contract())


async def test_contract_duplicate_rate_code_rejected(monkeypatch):
    import domains.revenue.rms_router.sales as sales
    monkeypatch.setattr(sales, "db", _fake_db({"id": "existing"}))
    with pytest.raises(HTTPException) as exc:
        await _assert_contract_unique("tenant-1", _contract())
    assert exc.value.status_code == 409


async def test_contract_update_excludes_self(monkeypatch):
    import domains.revenue.rms_router.sales as sales
    fdb = _fake_db(None)
    monkeypatch.setattr(sales, "db", fdb)
    await _assert_contract_unique("tenant-1", _contract(), exclude_id="self-id")
    flt = fdb.corporate_contracts.find_one.call_args[0][0]
    assert flt["id"] == {"$ne": "self-id"}


# ── Approval state machine map ───────────────────────────────────


def test_approval_state_machine_allowed_transitions():
    assert CONTRACT_APPROVAL_TRANSITIONS["draft"] == {"pending"}
    assert CONTRACT_APPROVAL_TRANSITIONS["pending"] == {"approved", "rejected"}
    assert CONTRACT_APPROVAL_TRANSITIONS["rejected"] == {"draft"}
    assert CONTRACT_APPROVAL_TRANSITIONS["approved"] == set()


def test_approval_state_machine_rejects_skips_and_terminal_reopen():
    # draft → approved skip is illegal
    assert "approved" not in CONTRACT_APPROVAL_TRANSITIONS["draft"]
    # approved is terminal — no outgoing transitions
    assert CONTRACT_APPROVAL_TRANSITIONS["approved"] == set()
    # pending cannot jump back to draft
    assert "draft" not in CONTRACT_APPROVAL_TRANSITIONS["pending"]
