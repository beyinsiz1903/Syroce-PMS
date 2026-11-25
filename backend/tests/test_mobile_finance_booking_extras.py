"""Mobile collection must not close a folio while owned extra debt remains."""
from unittest.mock import AsyncMock

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
