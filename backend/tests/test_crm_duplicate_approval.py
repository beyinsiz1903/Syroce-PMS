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
from pymongo.errors import DuplicateKeyError

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


# ── Task #205: race-safety DB-level partial unique indexes ───────


async def test_mice_ensure_indexes_builds_client_partial_unique(monkeypatch):
    """mice_accounts gets unique partial indexes scoped to client + non-blank."""
    import routers.mice as mice

    calls: list = []
    coll = MagicMock()
    coll.create_index = AsyncMock(
        side_effect=lambda keys, **kw: calls.append((keys, kw)))

    class _FakeDB:
        def __getattr__(self, name):
            return coll

    monkeypatch.setattr(mice, "get_system_db", lambda: _FakeDB())
    monkeypatch.setattr(mice, "_indexes_ready", False)
    await mice._ensure_indexes()

    by_name = {kw.get("name"): (keys, kw) for keys, kw in calls if kw.get("name")}
    for field, idx_name in (("tax_no", "uniq_mice_acc_client_taxno"),
                            ("email", "uniq_mice_acc_client_email")):
        assert idx_name in by_name, f"missing {idx_name}"
        keys, kw = by_name[idx_name]
        assert keys == [("tenant_id", 1), (field, 1)]
        assert kw["unique"] is True
        pfe = kw["partialFilterExpression"]
        assert pfe["account_type"] == "client"  # piggyback rows excluded
        assert pfe[field] == {"$gt": "", "$type": "string"}  # blanks excluded
    monkeypatch.setattr(mice, "_indexes_ready", False)


async def test_create_account_duplicate_key_translated_to_409(monkeypatch):
    """A concurrent insert that loses the race surfaces the same field 409."""
    import routers.mice as mice

    fdb = MagicMock()
    fdb.mice_accounts = MagicMock()
    fdb.mice_accounts.find_one = AsyncMock(return_value=None)  # guard passes
    fdb.mice_accounts.insert_one = AsyncMock(
        side_effect=DuplicateKeyError(
            "E11000 dup key: uniq_mice_acc_client_taxno"))
    monkeypatch.setattr(mice, "get_system_db", lambda: fdb)
    monkeypatch.setattr(mice, "require_mice_ops", lambda u: None)
    user = MagicMock(tenant_id="t1", username="u")

    with pytest.raises(HTTPException) as exc:
        await mice.create_account(_acct(email=None), current_user=user, _perm=None)
    assert exc.value.status_code == 409
    assert "tax_no" in exc.value.detail


async def test_ensure_contract_indexes_partial_unique(monkeypatch):
    """corporate_contracts gets unique partial indexes on non-blank strings."""
    import domains.revenue.rms_router.sales as sales

    calls: list = []
    cc = MagicMock()
    cc.create_index = AsyncMock(
        side_effect=lambda keys, **kw: calls.append((keys, kw)))
    fdb = MagicMock()
    fdb.corporate_contracts = cc
    monkeypatch.setattr(sales, "db", fdb)
    monkeypatch.setattr(sales, "_contract_indexes_ready", False)

    await sales._ensure_contract_indexes()

    by_name = {kw["name"]: (keys, kw) for keys, kw in calls}
    for field, idx_name in (("rate_code", "uniq_corp_contract_rate_code"),
                            ("contact_email", "uniq_corp_contract_contact_email")):
        assert idx_name in by_name, f"missing {idx_name}"
        keys, kw = by_name[idx_name]
        assert keys == [("tenant_id", 1), (field, 1)]
        assert kw["unique"] is True
        assert kw["partialFilterExpression"][field] == {"$gt": "", "$type": "string"}
    monkeypatch.setattr(sales, "_contract_indexes_ready", False)


async def test_ensure_contract_indexes_tolerates_build_failure(monkeypatch):
    """A pre-existing duplicate must not crash boot — failure is logged only."""
    import domains.revenue.rms_router.sales as sales

    cc = MagicMock()
    cc.create_index = AsyncMock(side_effect=Exception("E11000 existing dup"))
    fdb = MagicMock()
    fdb.corporate_contracts = cc
    monkeypatch.setattr(sales, "db", fdb)
    monkeypatch.setattr(sales, "_contract_indexes_ready", False)

    await sales._ensure_contract_indexes()  # no raise
    assert sales._contract_indexes_ready is True
    monkeypatch.setattr(sales, "_contract_indexes_ready", False)


async def test_create_contract_duplicate_key_translated_to_409(monkeypatch):
    """A concurrent contract insert that loses the race surfaces the same 409."""
    import domains.revenue.rms_router.sales as sales

    fdb = MagicMock()
    fdb.corporate_contracts = MagicMock()
    fdb.corporate_contracts.find_one = AsyncMock(return_value=None)  # guard passes
    fdb.corporate_contracts.insert_one = AsyncMock(
        side_effect=DuplicateKeyError(
            "E11000 dup key: uniq_corp_contract_contact_email"))
    monkeypatch.setattr(sales, "db", fdb)
    monkeypatch.setattr(sales, "_contract_indexes_ready", True)  # skip build
    user = MagicMock(tenant_id="t1", username="u")
    monkeypatch.setattr(sales, "get_current_user", AsyncMock(return_value=user))

    with pytest.raises(HTTPException) as exc:
        await sales.create_corporate_contract(
            _contract(), credentials=None, _perm=None)
    assert exc.value.status_code == 409
    assert "contact_email" in exc.value.detail
    monkeypatch.setattr(sales, "_contract_indexes_ready", False)
