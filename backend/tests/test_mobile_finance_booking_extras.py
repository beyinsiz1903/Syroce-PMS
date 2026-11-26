"""Mobile collection must not close a folio while owned extra debt remains."""
from unittest.mock import AsyncMock

import pytest

from domains.pms import cashier_service
from routers.finance import mobile
from tests.test_finance_report_reconciliation import context as finance_context
from tests.test_finance_report_reconciliation import seed_folios

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
context = finance_context


async def seed_extra(db):
    await seed_folios(db)
    await db.extra_charges.insert_one({"tenant_id": "A", "id": "extra", "booking_id": "bt", "folio_id": "try",
        "currency": "TRY", "amount": 120, "total": 120, "quantity": 1, "vat_amount": 20})


async def test_mobile_extract_includes_owned_extra_and_matches_receivable_list(ledger_db):
    await seed_extra(ledger_db)
    extract = await mobile.get_folio_full_extract_mobile("try", credentials=None)
    assert extract["summary"]["current_balance"] == 200
    assert extract["summary"]["total_charges"] == 220
    assert {row["id"] for row in extract["charges"]} == {"ct", "extra"}


async def test_mobile_partial_payment_does_not_close_unpaid_extra_debt(ledger_db, monkeypatch):
    await seed_extra(ledger_db)
    monkeypatch.setattr(cashier_service, "ensure_active_shift", AsyncMock())
    monkeypatch.setattr(cashier_service, "record_cash_transaction", AsyncMock())
    monkeypatch.setattr(mobile, "claim_short_window_dedup", AsyncMock(return_value={"status": "acquired", "lock_id": "lock"}))
    monkeypatch.setattr(mobile, "stamp_open_business_date", AsyncMock())
    result = await mobile.record_payment_mobile(mobile.RecordPaymentRequest(
        folio_id="try", amount=80, currency="TRY", payment_method="card"), credentials=None)
    assert result["new_balance"] == 120
    assert result["folio_closed"] is False
    assert (await ledger_db.folios.find_one({"id": "try"}))["status"] == "open"
    extract = await mobile.get_folio_full_extract_mobile("try", credentials=None)
    assert extract["summary"]["current_balance"] == 120


@pytest.mark.parametrize("method", ["cash", "card", "transfer", "check"])
async def test_cashier_failure_cannot_acknowledge_or_keep_mobile_payment(ledger_db, monkeypatch, method):
    await seed_extra(ledger_db)
    monkeypatch.setattr(cashier_service, "ensure_active_shift", AsyncMock())
    monkeypatch.setattr(cashier_service, "record_cash_transaction", AsyncMock(side_effect=RuntimeError("cashier unavailable")))
    monkeypatch.setattr(mobile, "claim_short_window_dedup", AsyncMock(return_value={"status": "acquired", "lock_id": "lock"}))
    monkeypatch.setattr(mobile, "release_idempotency", AsyncMock())
    monkeypatch.setattr(mobile, "stamp_open_business_date", AsyncMock())
    before = await ledger_db.payments.count_documents({})
    with pytest.raises(Exception):
        await mobile.record_payment_mobile(mobile.RecordPaymentRequest(
            folio_id="try", amount=20, currency="TRY", payment_method=method), credentials=None)
    assert await ledger_db.payments.count_documents({}) == before
    assert (await ledger_db.folios.find_one({"id": "try"}))["balance"] == 999


async def seed_cash_shift(ledger_db, monkeypatch):
    await seed_extra(ledger_db)
    monkeypatch.setattr(cashier_service, "db", ledger_db)
    from core.business_date_service import stamp_open_business_date

    await ledger_db.tenant_settings.update_one({"tenant_id": "A"}, {"$set": {"business_date": "2026-11-13"}}, upsert=True)
    monkeypatch.setattr(cashier_service, "stamp_open_business_date", stamp_open_business_date)
    monkeypatch.setattr(mobile, "stamp_open_business_date", stamp_open_business_date)
    monkeypatch.setattr(mobile, "claim_short_window_dedup", AsyncMock(return_value={"status": "acquired", "lock_id": "lock"}))
    monkeypatch.setattr(mobile, "release_idempotency", AsyncMock())
    await ledger_db.cashier_shifts.insert_one({"tenant_id": "A", "id": "shift", "status": "open", "business_date": "2026-11-13", "cash_in": 0, "transactions": []})


async def test_mobile_cash_and_projection_commit_together(ledger_db, monkeypatch):
    await seed_cash_shift(ledger_db, monkeypatch)
    result = await mobile.record_payment_mobile(mobile.RecordPaymentRequest(
        folio_id="try", amount=20, currency="TRY", payment_method="cash"), credentials=None)
    shift = await ledger_db.cashier_shifts.find_one({"id": "shift"})
    assert shift["cash_in"] == 20 and len(shift["transactions"]) == 1
    assert shift["transactions"][0]["ref_id"] == result["payment_id"]
    assert result["new_balance"] == 180 and not result["folio_closed"]
    assert (await ledger_db.folios.find_one({"id": "try"}))["balance"] == 180


async def test_projection_failure_rolls_back_payment_and_real_cashier_write(ledger_db, monkeypatch):
    await seed_cash_shift(ledger_db, monkeypatch)
    snapshots = mobile.folio_snapshots
    async def fail_inside_transaction(*args, **kwargs):
        if kwargs.get("session") is not None:
            raise RuntimeError("projection unavailable")
        return await snapshots(*args, **kwargs)
    monkeypatch.setattr(mobile, "folio_snapshots", fail_inside_transaction)
    before = await ledger_db.payments.count_documents({})
    with pytest.raises(RuntimeError, match="projection unavailable"):
        await mobile.record_payment_mobile(mobile.RecordPaymentRequest(
            folio_id="try", amount=20, currency="TRY", payment_method="cash"), credentials=None)
    assert await ledger_db.payments.count_documents({}) == before
    shift = await ledger_db.cashier_shifts.find_one({"id": "shift"})
    assert shift["cash_in"] == 0 and shift["transactions"] == []
    assert (await ledger_db.folios.find_one({"id": "try"}))["balance"] == 999
    mobile.release_idempotency.assert_awaited_once()


async def test_lost_ack_keeps_duplicate_guard_after_durable_commit(ledger_db, monkeypatch):
    await seed_cash_shift(ledger_db, monkeypatch)
    transaction = mobile.with_resource_locks
    async def lost_ack(**kwargs):
        await transaction(**kwargs)
        raise RuntimeError("ack lost")
    monkeypatch.setattr(mobile, "with_resource_locks", lost_ack)
    with pytest.raises(RuntimeError, match="ack lost"):
        await mobile.record_payment_mobile(mobile.RecordPaymentRequest(
            folio_id="try", amount=20, currency="TRY", payment_method="cash"), credentials=None)
    assert (await ledger_db.cashier_shifts.find_one({"id": "shift"}))["cash_in"] == 20
    assert await ledger_db.payments.count_documents({"payment_method": "cash", "amount": 20}) == 1
    mobile.release_idempotency.assert_not_awaited()


async def test_cashier_noop_cannot_keep_cash_payment(ledger_db, monkeypatch):
    await seed_cash_shift(ledger_db, monkeypatch)
    monkeypatch.setattr(cashier_service, "record_cash_transaction", AsyncMock(return_value=None))
    before = await ledger_db.payments.count_documents({})
    with pytest.raises(mobile.HTTPException) as exc:
        await mobile.record_payment_mobile(mobile.RecordPaymentRequest(
            folio_id="try", amount=20, currency="TRY", payment_method="cash"), credentials=None)
    assert exc.value.status_code == 409
    assert await ledger_db.payments.count_documents({}) == before
