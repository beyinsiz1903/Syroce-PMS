"""Cross-page reporting acceptance, using only isolated local test records."""
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401
from core import tenant_currency
from modules.analytics_export.service import AnalyticsExportService
from modules.pms_core.reporting_financials import report_payment_day_match
from modules.pms_core.reporting_ledger import charge_amount, posted_revenue_rows
from routers.departments import reports
from routers.finance import accounting, dashboards, mobile
from routers import pms_analytics

USER = SimpleNamespace(tenant_id="A", role="admin", id="u")


@pytest.fixture(autouse=True)
def reporting_context(monkeypatch):
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    for module in (reports, mobile):
        monkeypatch.setattr(module, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-02"}))
    monkeypatch.setattr(reports, "_enforce", lambda *_: None)


async def test_legacy_payment_has_one_authoritative_day_not_every_timestamp(ledger_db):
    await ledger_db.payments.insert_one({"tenant_id": "A", "payment_date": "2026-10-01", "processed_at": "2026-10-02T02:00:00Z", "created_at": datetime(2026, 10, 3, tzinfo=UTC)})
    assert await ledger_db.payments.count_documents(report_payment_day_match("2026-10-01")) == 1
    assert await ledger_db.payments.count_documents(report_payment_day_match("2026-10-02")) == 0
    assert await ledger_db.payments.count_documents(report_payment_day_match("2026-10-03")) == 0


async def test_mobile_collection_currency_is_inherited_from_authorized_folio(ledger_db, monkeypatch):
    monkeypatch.setattr(mobile, "db", ledger_db)
    await ledger_db.folios.insert_many([
        {"id": "f", "tenant_id": "A", "currency": "EUR"},
        {"id": "other", "tenant_id": "B", "currency": "USD"},
    ])
    await ledger_db.payments.insert_many([
        {"id": "p", "tenant_id": "A", "folio_id": "f", "business_date": "2026-10-02", "amount": 20, "method": "cash"},
        {"id": "r", "tenant_id": "A", "folio_id": "other", "business_date": "2026-10-02", "amount": 10, "method": "cash"},
    ])
    result = await mobile.get_daily_collections_mobile.__wrapped__(current_user=USER)
    assert result["received_totals_by_currency"] == {"EUR": 20, "TRY": 10}
    assert result["total_collected"] == 10
    assert result["conversion_issue_count"] == 1


@pytest.mark.parametrize("month", [0, 13])
async def test_mobile_monthly_reports_reject_invalid_month(month, monkeypatch):
    monkeypatch.setattr(mobile, "get_current_user", AsyncMock(return_value=USER))
    for call in (mobile.get_monthly_costs_mobile, mobile.get_monthly_collections_mobile.__wrapped__):
        with pytest.raises(HTTPException) as invalid:
            await call(month=month, **({"credentials": None} if call is mobile.get_monthly_costs_mobile else {"current_user": USER}))
        assert invalid.value.status_code == 422


async def test_legacy_profit_loss_route_uses_canonical_report(monkeypatch):
    monkeypatch.setattr(mobile, "get_current_user", AsyncMock(return_value=USER))
    builder = AsyncMock(return_value={"revenue_by_currency": {"EUR": 50}})
    monkeypatch.setattr(accounting, "get_profit_loss_report", builder)
    assert await mobile.get_profit_loss_report_v2(credentials=None) == {"revenue_by_currency": {"EUR": 50}}
    builder.assert_awaited_once_with("2026-10-01", "2026-10-02", current_user=USER)


async def test_accounting_documents_include_bare_start_day_and_bson_end_day(ledger_db, monkeypatch):
    monkeypatch.setattr(accounting, "db", ledger_db)
    await ledger_db.accounting_invoices.insert_many([
        {"tenant_id": "A", "status": "paid", "invoice_type": "sale", "issue_date": "2026-10-01", "currency": " TL ", "total": 100, "total_vat": 10, "items": [{"description": "Room", "total": 100}]},
        {"tenant_id": "A", "status": "paid", "invoice_type": "sale", "issue_date": datetime(2026, 10, 2, 23, tzinfo=UTC), "currency": "EUR", "total": 20, "total_vat": 2},
        {"tenant_id": "A", "status": "paid", "invoice_type": "sale", "issue_date": "2026-10-03", "currency": "EUR", "total": 9999},
    ])
    await ledger_db.expenses.insert_one({"tenant_id": "A", "date": datetime(2026, 10, 2, 23, tzinfo=UTC), "currency": "TL", "total_amount": 40, "vat_amount": 4, "category": "supplies"})
    result = await accounting.get_profit_loss_report.__wrapped__("2026-10-01", "2026-10-02", current_user=USER)
    assert result["total_revenue_by_currency"] == {"EUR": 20, "TRY": 100}
    assert result["gross_profit_by_currency"] == {"EUR": 20, "TRY": 60}
    vat = await accounting.get_vat_report("2026-10-01", "2026-10-02", current_user=USER)
    assert vat["vat_payable_by_currency"] == {"EUR": 2, "TRY": 6}


async def test_finance_snapshot_and_mobile_use_same_dates_currency_and_collections(ledger_db, monkeypatch):
    for module in (reports, mobile):
        monkeypatch.setattr(module, "db", ledger_db)
    await ledger_db.payments.insert_many([
        {"id": "p", "tenant_id": "A", "business_date": datetime(2026, 10, 2, tzinfo=UTC), "amount": 100, "currency": "TRY", "method": "cash"},
        {"id": "old", "tenant_id": "A", "payment_date": "2026-10-01", "processed_at": "2026-10-02", "amount": 20, "currency": "TRY", "method": "cash"},
        {"id": "retry1", "tenant_id": "A", "business_date": "2026-10-02", "idempotency_key": "same", "amount": 50, "currency": "TRY", "method": "card"},
        {"id": "retry2", "tenant_id": "A", "business_date": "2026-10-02", "idempotency_key": "same", "amount": 50, "currency": "TRY", "method": "card"},
        {"id": "ar", "tenant_id": "A", "business_date": "2026-10-02", "amount": 999, "currency": "TRY", "method": "city_ledger"},
        {"id": "foreign", "tenant_id": "B", "business_date": "2026-10-02", "amount": 999, "currency": "TRY"},
    ])
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "business_date": datetime(2026, 10, 2, tzinfo=UTC), "charge_amount": 100, "currency": "TRY"})
    await ledger_db.extra_charges.insert_one({"tenant_id": "A", "business_date": "2026-10-02", "total": 20, "currency": "TRY"})
    await ledger_db.pos_orders.insert_one({"tenant_id": "A", "id": "pos", "status": "closed", "business_date": "2026-10-02", "grand_total": 30, "currency": "TRY"})
    snapshot = await reports.get_finance_snapshot.__wrapped__(USER)
    daily = await mobile.get_daily_collections_mobile.__wrapped__(current_user=USER)
    monthly = await mobile.get_monthly_collections_mobile.__wrapped__(current_user=USER)
    assert snapshot["todays_collections"]["amount"] == daily["total_collected"] == 150
    assert snapshot["mtd_collections"]["amount"] == monthly["total_collected"] == 170
    assert snapshot["mtd_collections"]["revenue_by_currency"] == {"TRY": 150}


async def test_standard_ledger_legacy_pos_refund_removes_proportional_tip(ledger_db):
    await ledger_db.pos_orders.insert_one({"tenant_id": "A", "id": "pos", "currency": "EUR"})
    await ledger_db.pos_transactions.insert_many([
        {"tenant_id": "A", "id": "sale", "order_id": "pos", "status": "completed", "business_date": "2026-10-01", "total_amount": 110, "tip_amount": 10, "currency": "EUR"},
        {"tenant_id": "A", "id": "refund", "order_id": "pos", "original_transaction_id": "sale", "status": "refunded", "business_date": "2026-10-02", "total_amount": -55},
    ])
    rows = await posted_revenue_rows("A", date(2026, 10, 2), date(2026, 10, 2), database=ledger_db)
    assert sum(charge_amount(row) for row in rows) == -50


async def test_expense_list_includes_end_day_and_more_than_one_thousand_rows(ledger_db, monkeypatch):
    monkeypatch.setattr(accounting, "db", ledger_db)
    await ledger_db.expenses.insert_many([
        {"id": f"e{i}", "tenant_id": "A", "date": "2026-10-02T23:00:00", "total_amount": 1, "currency": "EUR"} for i in range(1001)
    ] + [{"id": "bson", "tenant_id": "A", "date": datetime(2026, 10, 2, 12, tzinfo=UTC), "total_amount": 2, "currency": "TRY"},
         {"tenant_id": "A", "date": "2026-10-03", "total_amount": 1000},
         {"tenant_id": "B", "date": "2026-10-02", "total_amount": 1000}])
    result = await accounting.get_expenses("2026-10-01", "2026-10-02", current_user=USER)
    assert len(result) == 1002
    with pytest.raises(HTTPException) as invalid:
        await accounting.get_expenses("2026-10-03", "2026-10-01", current_user=USER)
    assert invalid.value.status_code == 422


async def test_analytics_exports_respect_end_day_bson_and_full_row_count(ledger_db):
    await ledger_db.messaging_delivery_logs.insert_many([
        {"tenant_id": "A", "created_at": "2026-10-02T23:00:00", "channel": "email", "status": "sent"} for _ in range(501)
    ] + [{"tenant_id": "A", "created_at": datetime(2026, 10, 2, tzinfo=UTC), "channel": "email", "status": "sent"},
         {"tenant_id": "A", "created_at": "2026-10-03", "channel": "email", "status": "sent"}])
    service = AnalyticsExportService(ledger_db)
    result = await service.create_export("A", "messaging_delivery_performance", "csv", {"date_from": "2026-10-01", "date_to": "2026-10-02"}, "u")
    assert result["success"] and result["row_count"] == 502
    invalid = await service.create_export("A", "messaging_delivery_performance", "pdf", {}, "u")
    assert not invalid["success"]


async def test_cash_flow_keeps_currencies_and_does_not_treat_sales_invoices_as_payables(ledger_db, monkeypatch):
    monkeypatch.setattr(mobile, "db", ledger_db)
    await ledger_db.payments.insert_many([
        {"id": "try", "tenant_id": "A", "business_date": "2026-10-02", "amount": 100, "currency": "TRY", "method": "cash"},
        {"id": "eur", "tenant_id": "A", "business_date": "2026-10-02", "amount": 20, "currency": "EUR", "method": "cash"},
    ])
    await ledger_db.cash_flow.insert_one({"tenant_id": "A", "transaction_type": "expense", "date": "2026-10-02", "amount": 5, "currency": "EUR"})
    await ledger_db.accounting_invoices.insert_one({"tenant_id": "A", "status": "pending", "due_date": "2026-10-03", "total": 999, "currency": "TRY"})
    await ledger_db.expenses.insert_one({"tenant_id": "A", "business_date": "2026-09-01", "payment_status": "partial", "date": "2026-10-01", "due_date": datetime(2026, 10, 3, tzinfo=UTC), "total_amount": 50, "amount_paid": 10, "currency": "USD"})
    await ledger_db.bookings.insert_one({"id": "b", "tenant_id": "A", "status": "checked_in", "check_out": "2026-10-03T12:00:00"})
    await ledger_db.folios.insert_many([
        {"id": "f1", "tenant_id": "A", "booking_id": "b", "status": "open", "currency": "EUR", "balance": 20},
        {"id": "f2", "tenant_id": "A", "booking_id": "b", "status": "open", "currency": "TRY", "balance": 100},
    ])
    await ledger_db.bank_accounts.insert_one({"tenant_id": "A", "is_active": True, "currency": "EUR", "current_balance": 50, "last_sync": "2026-10-02"})
    result = await mobile.get_cash_flow_summary_mobile.__wrapped__(current_user=USER)
    assert result["today"]["cash_inflow"] is None and result["today"]["net_flow"] is None
    assert result["today"]["net_by_currency"] == {"TRY": 100, "EUR": 15}
    plan = next(row for row in result["weekly_plan"] if row["date"] == "2026-10-03")
    assert plan["collections_by_currency"] == {"EUR": 20, "TRY": 100}
    assert plan["payments_by_currency"] == {"USD": 40}
    assert result["bank_balances"][0]["account_number"] == ""
    monkeypatch.setattr(dashboards, "db", ledger_db)
    dashboard = await dashboards.get_cash_flow_dashboard.__wrapped__(current_user=USER)
    assert dashboard["today"]["cash_inflow"] is None
    assert dashboard["bank_balances"]["accounts"][0]["balance"] == 50
    assert len(dashboard["bank_balances"]["accounts"]) == 1  # no fabricated banks


async def test_analytics_excel_is_a_workbook_not_csv_and_keeps_numeric_cells(ledger_db):
    from io import BytesIO
    from openpyxl import load_workbook
    await ledger_db.ml_snapshots.insert_one({"tenant_id": "A", "model_type": "revenue_ml", "created_at": "2026-10-02", "confidence_avg": .75, "id": "=1+1\x00"})
    result = await AnalyticsExportService(ledger_db).create_export("A", "revenue_ml_outputs", "excel", {"date_from": "2026-10-01", "date_to": "2026-10-02"}, "u")
    assert result["success"] and result["content"].startswith(b"PK")
    sheet = load_workbook(BytesIO(result["content"])).active
    assert sheet["C2"].value == .75 and sheet["C2"].data_type == "n"
    assert sheet["D2"].data_type == "s"
    assert "\x00" not in sheet["D2"].value


async def test_prediction_retains_all_summary_rows_and_currency_without_amount_based_risk(ledger_db, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 2, 12, tzinfo=UTC)
    monkeypatch.setattr(pms_analytics, "datetime", Clock)
    monkeypatch.setattr(pms_analytics, "db", ledger_db)
    await ledger_db.bookings.insert_many([
        {"tenant_id": "A", "id": f"next{i}", "channel": "direct", "check_in": "2026-10-03T14:00:00", "status": "confirmed", "total_amount": 100, "currency": "EUR"} for i in range(501)
    ] + [{"tenant_id": "A", "id": "usd", "channel": "direct", "check_in": datetime(2026, 10, 3, 14, tzinfo=UTC), "status": "confirmed", "total_amount": 100000, "currency": "USD"},
         {"tenant_id": "A", "id": "past", "channel": "direct", "check_in": "2026-10-01", "created_at": "2025-01-01", "status": "no_show"},
         {"tenant_id": "A", "id": "outside", "channel": "direct", "check_in": "2026-10-04", "status": "confirmed"}])
    result = await pms_analytics.get_noshow_prediction(days_ahead=2, current_user=USER)
    assert result["summary"]["total_upcoming"] == result["matched_count"] == 502
    assert result["truncated"] and len(result["predictions"]) == 50
    assert result["summary"]["potential_loss_by_currency"] == {"EUR": 50100, "USD": 100000}
    assert result["historical_rates"]["by_channel"] == {"direct": 100}


async def test_no_show_reports_use_same_arrival_cohort_and_never_sum_currencies(ledger_db, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 2, 12, tzinfo=UTC)
    monkeypatch.setattr(pms_analytics, "datetime", Clock)
    monkeypatch.setattr(pms_analytics, "db", ledger_db)
    await ledger_db.bookings.insert_many([
        {"tenant_id": "A", "id": "n1", "channel": "direct", "check_in": "2026-10-01", "created_at": "2025-01-01", "no_show_at": "2026-10-01", "status": "no_show", "total_amount": 100, "currency": "EUR", "no_show_reason": "overbooking"},
        {"tenant_id": "A", "id": "n2", "channel": "direct", "check_in": datetime(2026, 10, 1, tzinfo=UTC), "created_at": "2025-01-01", "no_show_at": datetime(2026, 10, 1, tzinfo=UTC), "status": "no_show", "total_amount": 100, "currency": "TRY"},
        {"tenant_id": "A", "id": "ok1", "channel": "direct", "check_in": "2026-10-01", "created_at": "2026-10-01", "status": "checked_out"},
        {"tenant_id": "A", "id": "ok2", "channel": "direct", "check_in": "2026-10-01", "created_at": "2026-10-01", "status": "checked_out"},
    ])
    result = await pms_analytics.get_channel_loss_analytics(days=7, current_user=USER)
    assert result["total_loss"] is None
    assert result["loss_by_currency"] == {"EUR": 100, "TRY": 100}
    assert result["channels"][0]["no_show_rate"] == 50
    heatmap = await pms_analytics.get_overbooking_heatmap(days=7, current_user=USER)
    assert heatmap["loss_by_currency"] == {"EUR": 100}
    assert len(heatmap["heatmap"]) == 7  # zero-event days belong in averages too


def test_scheduled_csv_escapes_formula_cells():
    from routers.report_scheduler import _payload_to_csv
    value = _payload_to_csv("=1+1", {"rows": [{"label": "=2+2", "value": " @SUM(1,2)"}]}).decode("utf-8")
    assert "'=1+1" in value and "'=2+2" in value and "'@SUM" in value


async def test_expense_summary_does_not_return_demo_numbers(ledger_db, monkeypatch):
    monkeypatch.setattr(dashboards, "db", ledger_db)
    empty = await dashboards.get_expense_summary(date="2026-10-02", period="week", current_user=USER)
    assert empty["total_expenses"] == 0 and empty["categories"] == {}
    assert empty["start_date"] == "2026-09-26"
    await ledger_db.expenses.insert_many([
        {"tenant_id": "A", "date": "2026-10-02T23:00:00", "total_amount": 100, "currency": "TRY", "category": "food"},
        {"tenant_id": "A", "date": datetime(2026, 10, 2, tzinfo=UTC), "total_amount": 20, "currency": "EUR", "category": "food"},
    ])
    actual = await dashboards.get_expense_summary(date="2026-10-02", period="week", current_user=USER)
    assert actual["total_expenses"] is None and actual["by_currency"] == {"EUR": 20, "TRY": 100}


async def test_cashier_report_never_claims_an_uncounted_shift_balanced(ledger_db, monkeypatch):
    monkeypatch.setattr(mobile, "db", ledger_db)
    monkeypatch.setattr(mobile, "get_current_user", AsyncMock(return_value=USER))
    await ledger_db.payments.insert_many([
        {"tenant_id": "A", "id": "p1", "business_date": "2026-10-02", "amount": 100, "currency": "TRY", "method": "bank_transfer"},
        {"tenant_id": "A", "id": "p2", "business_date": "2026-10-02", "amount": 20, "currency": "EUR", "method": "cash"},
    ])
    result = await mobile.get_cashier_shift_report(shift_date="2026-10-02", credentials=None)
    assert result["opening_balance"] is None and result["variance"] is None
    assert result["collections"]["total"] is None and result["collections"]["transfer"] == 100
    assert result["average_transaction"] is None
    assert result["payment_method_counts"] == {"transfer": 1, "cash": 1}
