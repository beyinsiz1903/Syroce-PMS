"""Cross-page financial reports against an isolated, real local Mongo ledger."""
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook
from pydantic import ValidationError

from core import tenant_currency, utils
from routers.finance import accounting, dashboards, folio, mobile

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)

USER = SimpleNamespace(tenant_id="A", role="admin", id="operator", username="operator", email="operator@example.test")


@pytest.fixture(autouse=True)
def context(monkeypatch, ledger_db):
    for module in (accounting, dashboards, folio, mobile, utils):
        monkeypatch.setattr(module, "db", ledger_db)
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(accounting, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    for module in (mobile, dashboards, folio):
        monkeypatch.setattr(module, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-02"}))
    monkeypatch.setattr(mobile, "get_current_user", AsyncMock(return_value=USER))


async def seed_folios(db):
    await db.folios.insert_many([
        {"id": "eur", "tenant_id": "A", "status": "open", "currency": " EUR ", "booking_id": "be", "company_id": "c", "balance": 0, "created_at": "2026-09-01"},
        {"id": "try", "tenant_id": "A", "status": "open", "booking_id": "bt", "company_id": "c", "balance": 999, "created_at": datetime(2026, 9, 1, tzinfo=UTC)},
        {"id": "credit", "tenant_id": "A", "status": "open", "currency": "TRY", "balance": 999},
    ])
    await db.bookings.insert_many([
        {"id": "be", "tenant_id": "B", "guest_name": "Wrong hotel", "check_out": "2020-01-01", "currency": "USD"},
        {"id": "be", "tenant_id": "A", "guest_name": "Euro guest", "check_out": datetime(2026, 9, 1, tzinfo=UTC), "currency": "EUR"},
        {"id": "bt", "tenant_id": "A", "guest_name": "Lira guest", "check_out": "2026-10-02", "currency": " TL "},
    ])
    await db.folio_charges.insert_many([
        {"id": "ce", "tenant_id": "A", "folio_id": "eur", "amount": 100, "created_at": "2026-09-01"},
        {"id": "ct", "tenant_id": "A", "folio_id": "try", "total": 100, "created_at": datetime(2026, 9, 1, tzinfo=UTC)},
        {"tenant_id": "A", "folio_id": "try", "total": 9000, "voided": True},
        {"tenant_id": "B", "folio_id": "try", "total": 9000},
    ])
    await db.payments.insert_many([
        {"id": "p", "tenant_id": "A", "folio_id": "eur", "amount": 30, "currency": "EUR", "method": "cash", "idempotency_key": "same", "created_at": "2026-09-01"},
        {"id": "retry", "tenant_id": "A", "folio_id": "eur", "amount": 30, "currency": "EUR", "method": "cash", "idempotency_key": "same", "created_at": "2026-09-01"},
        {"id": "refund", "tenant_id": "A", "folio_id": "eur", "amount": 10, "payment_type": "refund", "created_at": "2026-09-02"},
        {"id": "failed", "tenant_id": "A", "folio_id": "eur", "amount": 1000, "status": "failed", "created_at": "2026-09-02"},
        {"id": "pending", "tenant_id": "A", "folio_id": "try", "amount": 1000, "status": "pending"},
        {"id": "void", "tenant_id": "A", "folio_id": "try", "amount": 1000, "voided": True},
        {"id": "offset", "tenant_id": "A", "folio_id": "try", "amount": 20, "method": "discount"},
        {"id": "advance", "tenant_id": "A", "folio_id": "credit", "amount": 200, "currency": "TRY"},
    ])


async def test_pending_overdue_and_extract_reconcile_without_stored_balance_or_fx_sum(ledger_db):
    await seed_folios(ledger_db)
    pending = await mobile.get_pending_receivables_mobile.__wrapped__(current_user=USER)
    assert pending["totals_by_currency"] == {"EUR": 80, "TRY": 80}
    assert pending["total_pending"] is None
    assert pending["overdue_by_currency"] == {"EUR": 80}
    assert pending["receivables_count"] == 2
    assert pending["as_of_date"] == "2026-10-02"
    by_id = {r["folio_id"]: r for r in pending["receivables"]}
    assert not by_id["try"]["is_overdue"]
    assert by_id["eur"]["guest_name"] == "Euro guest"
    overdue = await mobile.get_overdue_accounts_mobile.__wrapped__(min_days=7, current_user=USER)
    assert overdue["summary"]["totals_by_currency"] == {"EUR": 80}
    assert overdue["overdue_accounts"][0]["days_overdue"] == 31
    extract = await mobile.get_folio_full_extract_mobile("eur", credentials=None)
    assert extract["folio"]["currency"] == "EUR"
    assert extract["summary"]["current_balance"] == 80
    assert extract["summary"]["total_charges"] == 100
    assert extract["summary"]["total_payments"] == 20
    assert {p["id"] for p in extract["payments"]} == {"p", "refund"}
    assert next(p for p in extract["payments"] if p["id"] == "refund")["amount"] == -10
    assert all(isinstance(row["date"], str) for row in extract["charges"] + extract["payments"])
    assert await utils.calculate_folio_balance("eur", "A") == extract["summary"]["current_balance"]


async def test_company_summary_detail_and_aging_have_no_mixed_scalar(ledger_db):
    await seed_folios(ledger_db)
    await ledger_db.companies.insert_one({"tenant_id": "A", "id": "c", "name": "Company"})
    result = await folio.get_pending_ar.__wrapped__(current_user=USER)
    assert result[0]["total_outstanding_by_currency"] == {"EUR": 80, "TRY": 80}
    detail = await folio.get_pending_ar_details("c", current_user=USER)
    assert detail["total_outstanding_by_currency"] == result[0]["total_outstanding_by_currency"]
    assert result[0]["total_outstanding"] is None
    details = await folio.get_pending_ar_details("c", current_user=USER)
    assert details["total_outstanding_by_currency"] == result[0]["total_outstanding_by_currency"]
    assert details["total_outstanding"] is None
    response = await folio.export_pending_ar(current_user=USER)
    content = b"".join([chunk async for chunk in response.body_iterator])
    workbook = load_workbook(BytesIO(content))
    totals = {}
    for row in list(workbook.active.values)[2:]:
        totals[row[6]] = totals.get(row[6], 0) + row[7]
    assert totals == details["total_outstanding_by_currency"]


async def test_company_ar_database_failure_is_not_empty_zero_balance(monkeypatch):
    monkeypatch.setattr(folio, "db", SimpleNamespace(companies=SimpleNamespace(find=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("unavailable")))))
    with pytest.raises(HTTPException) as exc:
        await folio.get_pending_ar.__wrapped__(current_user=USER)
    assert exc.value.status_code == 503


async def test_company_ar_preserves_debt_with_missing_company_metadata(ledger_db):
    await seed_folios(ledger_db)
    result = await folio.get_pending_ar.__wrapped__(current_user=USER)
    assert result[0]["company_name"] == "Şirket kaydı bulunamadı"
    assert result[0]["total_outstanding_by_currency"] == {"EUR": 80, "TRY": 80}
    detail = await folio.get_pending_ar_details("c", current_user=USER)
    assert detail["company"]["name"] == "Şirket kaydı bulunamadı"
    assert detail["total_outstanding_by_currency"] == result[0]["total_outstanding_by_currency"]


async def test_receivable_totals_include_more_than_five_thousand_folios(ledger_db):
    await ledger_db.folios.insert_many([{"id": str(i), "tenant_id": "A", "status": "open", "currency": "EUR", "balance": 0, "booking_id": "old"} for i in range(5001)])
    await ledger_db.bookings.insert_one({"id": "old", "tenant_id": "A", "check_out": "2026-09-01"})
    await ledger_db.folio_charges.insert_many([{"folio_id": str(i), "tenant_id": "A", "total": 1} for i in range(5001)])
    result = await mobile.get_pending_receivables_mobile.__wrapped__(current_user=USER)
    assert result["totals_by_currency"] == {"EUR": 5001}
    assert result["receivables_count"] == 5001
    assert result["truncated"] is True and result["returned_count"] == 20
    overdue = await mobile.get_overdue_accounts_mobile.__wrapped__(min_days=7, current_user=USER)
    assert overdue["summary"]["total_count"] == 5001
    assert overdue["summary"]["totals_by_currency"] == {"EUR": 5001}


async def test_credit_limits_compare_only_the_limit_currency_and_report_other_debt(ledger_db):
    await seed_folios(ledger_db)
    await ledger_db.companies.insert_one({"id": "c", "tenant_id": "A", "name": "Company"})
    await ledger_db.credit_limits.insert_one({"id": "limit", "tenant_id": "A", "company_id": "c", "credit_limit": 100})
    result = await mobile.get_credit_limit_violations_mobile.__wrapped__(current_user=USER)
    assert not result["violations"]  # TRY 80, not EUR 80 + TRY 80
    assert result["currency_mismatches"][0]["debt_by_currency"] == {"EUR": 80, "TRY": 80}
    await ledger_db.credit_limits.update_one({"id": "limit"}, {"$set": {"currency": "EUR", "credit_limit": 70}})
    result = await mobile.get_credit_limit_violations_mobile.__wrapped__(current_user=USER)
    assert result["violations"][0]["currency"] == "EUR"
    assert result["violations"][0]["over_limit_amount"] == 10


async def test_risk_alias_is_read_only_tenant_safe_and_does_not_invent_credit_limits(ledger_db):
    await seed_folios(ledger_db)
    result = await dashboards.get_risk_alerts(current_user=USER)
    assert result["overdue_accounts"][0]["guest_name"] == "Euro guest"
    assert result["summary"]["total_overdue_by_currency"] == {"EUR": 80}
    assert not result["over_limit_accounts"]
    assert await ledger_db.notifications.count_documents({}) == 0


async def test_suspicious_receivables_do_not_hide_small_foreign_currency_old_debt(ledger_db):
    await seed_folios(ledger_db)
    result = await mobile.get_suspicious_receivables_mobile.__wrapped__(current_user=USER)
    assert result["suspicious_receivables"][0]["currency"] == "EUR"
    assert result["summary"]["totals_by_currency"] == {"EUR": 80}


async def test_expenses_and_cashflow_use_full_iso_bson_days_and_keep_currencies(ledger_db):
    await ledger_db.expenses.insert_many([
        {"tenant_id": "A", "date": "2026-10-02", "total_amount": 100, "amount": 50, "currency": " TL ", "category": "supplies"},
        {"tenant_id": "A", "date": datetime(2026, 10, 2, 23, tzinfo=UTC), "amount": 20, "currency": "EUR"},
        {"tenant_id": "A", "date": "2026-10-03", "amount": 9999},
    ])
    expense = await mobile.get_daily_expenses_mobile(credentials=None)
    assert expense["date"] == "2026-10-02"
    assert expense["totals_by_currency"] == {"EUR": 20, "TRY": 100}
    assert expense["total_expenses"] is None
    await ledger_db.cash_flow.insert_many([
        {"tenant_id": "A", "date": "2026-10-02", "amount": 100, "transaction_type": "income", "currency": "TRY"},
        {"tenant_id": "A", "date": datetime(2026, 10, 2, 23, tzinfo=UTC), "amount": 20, "transaction_type": "expense", "currency": "EUR"},
        {"tenant_id": "A", "date": "2026-10-03", "amount": 9999, "transaction_type": "income"},
    ])
    cash = await accounting.get_cash_flow("2026-10-02", "2026-10-02", current_user=USER)
    assert cash["total_income_by_currency"] == {"TRY": 100}
    assert cash["total_expense_by_currency"] == {"EUR": 20}


async def test_invoice_report_does_not_truncate_or_drop_end_day_or_partial_balance(ledger_db):
    await ledger_db.accounting_invoices.insert_many([
        {"id": str(i), "tenant_id": "A", "created_at": "2026-10-02T23:59:00Z", "status": "pending", "total": 1, "currency": "TRY"} for i in range(101)
    ] + [{"id": "partial", "tenant_id": "A", "created_at": datetime(2026, 10, 2, 23, tzinfo=UTC), "status": "partial", "total": 100, "amount_paid": 20, "currency": "EUR"},
         {"id": "void", "tenant_id": "A", "created_at": "2026-10-02", "status": "cancelled", "total": 9999}])
    result = await mobile.get_invoices_mobile("2026-10-02", "2026-10-02", unpaid_only=True, credentials=None)
    assert result["summary"]["total_count"] == 102
    assert result["summary"]["unpaid_by_currency"] == {"EUR": 80, "TRY": 101}
    assert result["summary"]["total_amount"] is None
    assert next(i for i in result["invoices"] if i["id"] == "partial")["outstanding_amount"] == 80


@pytest.mark.parametrize("transaction_type", [None, "income"])
async def test_cash_flow_month_boundaries_keep_iso_and_bson_rows_and_tenant_scope(ledger_db, transaction_type):
    dates = ["2026-09-01", "2026-09-01T00:00:00Z", datetime(2026, 9, 1, tzinfo=UTC),
             "2026-09-30", "2026-09-30T23:59:59.999999Z", datetime(2026, 9, 30, 23, 59, 59, 999000, tzinfo=UTC)]
    await ledger_db.cash_flow.insert_many([
        {"id": f"in-{index}", "tenant_id": "A", "date": day, "amount": 2 ** index, "transaction_type": "income", "currency": "TRY"}
        for index, day in enumerate(dates)
    ] + [
        {"id": "eur-first", "tenant_id": "A", "date": dates[2], "amount": 5, "transaction_type": "expense", "currency": "EUR"},
        {"id": "eur-last", "tenant_id": "A", "date": dates[4], "amount": 5, "transaction_type": "expense", "currency": "EUR"},
        {"id": "usd", "tenant_id": "A", "date": dates[3], "amount": 3, "transaction_type": "income", "currency": "USD"},
        {"id": "other-tenant", "tenant_id": "B", "date": dates[0], "amount": 99999, "transaction_type": "income", "currency": "TRY"},
    ] + [
        {"id": f"outside-{index}", "tenant_id": "A", "date": day, "amount": 99999, "transaction_type": "income", "currency": "TRY"}
        for index, day in enumerate(["2026-08-31T23:59:59.999999Z", datetime(2026, 8, 31, 23, 59, 59, tzinfo=UTC),
                                     "2026-10-01", datetime(2026, 10, 1, tzinfo=UTC)])
    ])
    result = await accounting.get_cash_flow("2026-09-01", "2026-09-30", transaction_type=transaction_type, current_user=USER)
    expected_ids = {f"in-{index}" for index in range(6)} | {"usd"}
    if transaction_type is None:
        expected_ids |= {"eur-first", "eur-last"}
    assert {row["id"] for row in result["transactions"]} == expected_ids
    assert result["total_income"] == 63
    assert result["total_income_by_currency"] == {"TRY": 63, "USD": 3}
    assert result["total_expense_by_currency"] == ({"EUR": 10} if transaction_type is None else {})


async def test_bank_report_reads_legacy_balance_and_iso_sync_without_mislabeling_fx(ledger_db):
    await ledger_db.bank_accounts.insert_many([
        {"id": "try", "tenant_id": "A", "is_active": True, "balance": 100, "currency": " TL ", "last_sync": "2026-10-01T12:00:00Z"},
        {"id": "eur", "tenant_id": "A", "is_active": True, "current_balance": 0, "balance": 999, "currency": "EUR"},
    ])
    result = await mobile.get_bank_balances_mobile(credentials=None)
    assert result["total_balance_try"] == 100
    assert result["totals_by_currency"] == {"EUR": 0, "TRY": 100}
    assert result["bank_accounts"][0]["available_balance"] is None


async def test_one_folio_never_offsets_foreign_debt_with_unrelated_currency_credit(ledger_db):
    await ledger_db.folios.insert_one({"id": "mixed", "tenant_id": "A", "status": "open", "currency": "TRY"})
    await ledger_db.folio_charges.insert_one({"folio_id": "mixed", "tenant_id": "A", "charge_amount": 100, "currency": "EUR"})
    await ledger_db.payments.insert_one({"folio_id": "mixed", "tenant_id": "A", "amount": 50, "currency": "TRY"})
    extract = await mobile.get_folio_full_extract_mobile("mixed", credentials=None)
    assert extract["summary"]["balance_by_currency"] == {"EUR": 100, "TRY": -50}
    assert extract["summary"]["current_balance"] is None
    pending = await mobile.get_pending_receivables_mobile.__wrapped__(current_user=USER)
    assert pending["totals_by_currency"] == {"EUR": 100}
    with pytest.raises(HTTPException) as ambiguous:
        await utils.calculate_folio_balance("mixed", "A")
    assert ambiguous.value.status_code == 409


async def test_folio_detail_cannot_read_another_tenants_booking(ledger_db):
    await ledger_db.folios.insert_one({"id": "f", "tenant_id": "A", "booking_id": "foreign"})
    await ledger_db.bookings.insert_one({"id": "foreign", "tenant_id": "B", "guest_name": "Private guest"})
    result = await dashboards.get_folio_detail("f", current_user=USER)
    assert result["booking"] is None


async def test_mobile_collection_reconciles_stale_balance_before_deciding_to_close(ledger_db, monkeypatch):
    from domains.pms import cashier_service

    await seed_folios(ledger_db)
    monkeypatch.setattr(cashier_service, "ensure_active_shift", AsyncMock())
    monkeypatch.setattr(cashier_service, "record_cash_transaction", AsyncMock())
    monkeypatch.setattr(mobile, "claim_short_window_dedup", AsyncMock(return_value={"status": "acquired", "lock_id": "lock"}))
    monkeypatch.setattr(mobile, "stamp_open_business_date", AsyncMock())
    result = await mobile.record_payment_mobile(mobile.RecordPaymentRequest(folio_id="try", amount=80, currency="TRY", payment_method="card"), credentials=None)
    assert result["new_balance"] == 0 and result["folio_closed"] is True
    saved = await ledger_db.payments.find_one({"id": result["payment_id"]})
    assert saved["currency"] == "TRY"
    assert (await ledger_db.folios.find_one({"id": "try"}))["status"] == "closed"


async def test_mobile_collection_rejects_currency_mismatch_before_any_payment(ledger_db):
    await seed_folios(ledger_db)
    count = await ledger_db.payments.count_documents({})
    with pytest.raises(HTTPException) as exc:
        await mobile.record_payment_mobile(mobile.RecordPaymentRequest(folio_id="eur", amount=80, currency="TRY", payment_method="card"), credentials=None)
    assert exc.value.status_code == 409
    assert await ledger_db.payments.count_documents({}) == count


async def test_foreign_currency_compact_payment_never_books_a_fictitious_one_to_one_rate(ledger_db):
    await seed_folios(ledger_db)
    count = await ledger_db.payments.count_documents({})
    with pytest.raises(HTTPException) as exc:
        await mobile.record_payment_mobile(mobile.RecordPaymentRequest(folio_id="eur", amount=80, currency="EUR", payment_method="cash"), credentials=None)
    assert exc.value.status_code == 409
    assert "kur bilgisi" in exc.value.detail
    assert await ledger_db.payments.count_documents({}) == count


@pytest.mark.parametrize("amount", [-1, 0, float("nan"), float("inf")])
def test_mobile_collection_rejects_invalid_amounts(amount):
    with pytest.raises(ValidationError):
        mobile.RecordPaymentRequest(folio_id="f", amount=amount, payment_method="card")
