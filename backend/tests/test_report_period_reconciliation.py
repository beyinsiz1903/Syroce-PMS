"""Independent ledger, document-boundary and export reconciliation cases."""

from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook

from core import database, tenant_currency, utils
from routers.departments import reports
from routers.finance import accounting

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(tenant_id="A", role="admin", id="operator", name="Operator", granted_permissions=[])


@pytest.fixture(autouse=True)
def context(ledger_db, monkeypatch):
    for module in (reports, accounting):
        monkeypatch.setattr(module, "db", ledger_db)
    monkeypatch.setattr(reports, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-07"}))
    monkeypatch.setattr(database, "_raw_db", ledger_db)
    monkeypatch.setattr(utils, "db", ledger_db)
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(accounting, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))


async def workbook(response):
    content = b"".join([chunk async for chunk in response.body_iterator])
    return load_workbook(BytesIO(content))


async def test_company_reports_do_not_cancel_euro_debt_with_lira_credit(ledger_db):
    await ledger_db.folios.insert_one({"tenant_id": "A", "id": "f", "folio_type": "company", "status": "open", "company_id": "c", "currency": "EUR", "due_date": "2026-10-01"})
    await ledger_db.companies.insert_many([{"tenant_id": "A", "id": "c", "name": "Company"}, {"tenant_id": "B", "id": "c", "name": "Do not expose"}])
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "folio_id": "f", "total": 100, "currency": "EUR"})
    await ledger_db.payments.insert_one({"tenant_id": "A", "folio_id": "f", "amount": 200, "currency": "TRY", "status": "paid"})
    aging = await reports._compute_company_aging("A")
    snapshot = await reports.get_finance_snapshot.__wrapped__(USER)
    assert aging["total_ar_by_currency"] == {"EUR": 100}
    assert aging["companies"][0]["company_name"] == "Company"
    assert snapshot["pending_ar"]["by_currency"]["EUR"]["total"] == 100
    assert snapshot["pending_ar"]["total"] == aging["total_ar"] == 100
    sheet = (await workbook(await reports.export_company_aging_excel(USER))).active
    assert list(sheet.values)[2][2:4] == ("EUR", 100)
    # Read-only reporting must not weaken the operational settlement guard.
    with pytest.raises(HTTPException) as error:
        await utils.calculate_folio_balance("f", "A")
    assert error.value.status_code == 409


async def test_company_reports_resolve_legacy_currency_from_booking_before_property(ledger_db):
    await ledger_db.folios.insert_one({"tenant_id": "A", "id": "f", "folio_type": "company", "status": "open", "booking_id": "b"})
    await ledger_db.bookings.insert_one({"tenant_id": "A", "id": "b", "currency": "EUR"})
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "folio_id": "f", "total": 30})
    await ledger_db.payments.insert_one({"tenant_id": "A", "folio_id": "f", "amount": 5, "status": "paid"})
    aging = await reports._compute_company_aging("A")
    snapshot = await reports.get_finance_snapshot.__wrapped__(USER)
    assert aging["total_ar_by_currency"] == {"EUR": 25}
    assert snapshot["pending_ar"]["by_currency"] == {"EUR": {"total": 25, "0-30_days": 0, "30-60_days": 0, "60_plus_days": 25, "overdue_invoices_count": 1}}


async def test_missing_native_currency_uses_property_currency_not_the_try_reporting_unit(ledger_db, monkeypatch):
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("EUR", "€")))
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "business_date": "2026-10-07", "total": 30, "category": "room"})
    await ledger_db.payments.insert_one({"tenant_id": "A", "business_date": "2026-10-07", "amount": 5, "status": "paid"})
    await ledger_db.accounting_invoices.insert_one({"tenant_id": "A", "status": "pending", "total": 15})
    await ledger_db.purchase_orders.insert_one({"tenant_id": "A", "status": "received", "created_at": "2026-10-07", "total_amount": 10})
    await ledger_db.bookings.insert_one({"tenant_id": "A", "status": "confirmed", "check_in": "2026-10-07", "check_out": "2026-10-08", "total_amount": 20})
    snapshot = await reports.get_finance_snapshot.__wrapped__(USER)
    assert snapshot["accounting_invoices"]["by_currency"] == {"EUR": 15}
    assert snapshot["todays_collections"]["amount"] == 0
    assert snapshot["todays_collections"]["conversion_issue_count"] == 1
    assert snapshot["mtd_collections"]["revenue_by_currency"] == {"EUR": 30}
    costs = await reports._compute_mtd_cost_summary("A")
    assert costs["total_mtd_costs_by_currency"] == {"EUR": 10}
    assert costs["financial_metrics"]["by_currency"]["EUR"]["mtd_revenue"] == 30
    segments = await reports.get_market_segment_report.__wrapped__("2026-10-07", "2026-10-07", USER)
    assert segments["market_segments"]["other"]["revenue_by_currency"] == {"EUR": 20}
    sheet = (await workbook(await reports.export_channel_distribution_excel("2026-10-07", "2026-10-07", USER))).active
    assert list(sheet.values)[2][1] == "EUR"


async def test_cost_summary_legacy_and_native_profit_reconcile_to_displayed_totals(ledger_db):
    await ledger_db.purchase_orders.insert_one({"tenant_id": "A", "status": "received", "created_at": "2026-10-07", "total_amount": 0.005, "currency": "EUR", "category": "food"})
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "business_date": "2026-10-07", "total": 2.664, "currency": "EUR", "category": "room"})
    costs = await reports._compute_mtd_cost_summary("A")
    financial = costs["financial_metrics"]
    assert financial["mtd_revenue"] == 2.66 and financial["mtd_costs"] == 0.01
    assert financial["gross_profit"] == financial["by_currency"]["EUR"]["gross_profit"] == 2.65
    assert costs["top_3_categories"][0]["amount"] == costs["cost_categories"]["fnb"] == 0.01


async def test_finance_snapshot_does_not_include_voided_or_deleted_pending_invoices(ledger_db):
    await ledger_db.accounting_invoices.insert_many(
        [
            {"tenant_id": "A", "status": "partial", "total": 100, "amount_paid": 25, "currency": "EUR"},
            {"tenant_id": "A", "status": "pending", "total": 999, "currency": "TRY", "voided": True},
            {"tenant_id": "A", "status": "pending", "total": 999, "currency": "TRY", "deleted": True},
            {"tenant_id": "B", "status": "pending", "total": 999, "currency": "TRY"},
        ]
    )
    snapshot = await reports.get_finance_snapshot.__wrapped__(USER)
    assert snapshot["accounting_invoices"] == {"pending_count": 1, "pending_total": 75, "by_currency": {"EUR": 75}}


async def test_mixed_currency_folio_is_counted_once_in_overdue_document_count(ledger_db):
    await ledger_db.folios.insert_one({"tenant_id": "A", "id": "f", "folio_type": "company", "status": "open", "due_date": "2026-10-01"})
    await ledger_db.folio_charges.insert_many([{"tenant_id": "A", "folio_id": "f", "total": 100, "currency": code} for code in ("TRY", "EUR")])
    snapshot = await reports.get_finance_snapshot.__wrapped__(USER)
    assert snapshot["pending_ar"]["overdue_invoices_count"] == 1
    assert snapshot["pending_ar"]["mixed_ledger_folio_ids"] == ["f"]
    assert snapshot["pending_ar"]["total"] is None


async def test_invalid_ledger_record_cannot_be_presented_or_exported_as_a_complete_total(ledger_db):
    await ledger_db.folios.insert_many([{"tenant_id": "A", "id": name, "folio_type": "company", "status": "open", "currency": "EUR"} for name in ("good", "bad")])
    await ledger_db.folio_charges.insert_many([{"tenant_id": "A", "folio_id": name, "total": value} for name, value in [("good", 25), ("bad", "invalid-legacy-amount")]])
    aging = await reports._compute_company_aging("A")
    snapshot = await reports.get_finance_snapshot.__wrapped__(USER)
    assert aging["total_ar_by_currency"] == {"EUR": 25}
    for result in (aging, snapshot["pending_ar"]):
        assert result["complete"] is False
        assert result["failed_folio_ids"] == ["bad"]
    assert snapshot["pending_ar"]["total"] is None
    with pytest.raises(HTTPException) as error:
        await reports.export_company_aging_excel(USER)
    assert error.value.status_code == 503


async def test_company_ledger_outage_fails_closed_without_per_folio_database_retries(monkeypatch):
    source = AsyncMock(side_effect=RuntimeError("isolated unavailable ledger"))
    monkeypatch.setattr(reports, "folio_snapshots", source)
    positions, failed, mixed = await reports._company_ledger_positions("A", [{"id": str(i)} for i in range(100)])
    source.assert_awaited_once()
    assert not positions and not mixed and len(failed) == 100


async def test_market_segment_includes_iso_and_bson_arrivals_in_screen_and_excel(ledger_db):
    await ledger_db.bookings.insert_many(
        [
            {"tenant_id": "A", "check_in": check_in, "check_out": "2026-10-08", "total_amount": 100, "currency": "EUR", "status": "confirmed", "market_segment": "corporate", "rate_type": "bar"}
            for check_in in ["2026-10-07", datetime(2026, 10, 7, tzinfo=UTC)]
        ]
        + [{"tenant_id": "B", "check_in": "2026-10-07", "check_out": "2026-10-08", "total_amount": 999, "status": "confirmed"}]
    )
    data = await reports.get_market_segment_report.__wrapped__("2026-10-07", "2026-10-07", USER)
    assert data["total_bookings"] == 2
    assert data["market_segments"]["corporate"]["revenue_by_currency"] == {"EUR": 200}
    sheet = (await workbook(await reports.export_market_segment_excel("2026-10-07", "2026-10-07", USER))).active
    assert list(sheet.values)[2][1:5] == ("EUR", 2, 2, 200)


async def test_market_segment_counts_only_stays_that_contribute_to_its_groups(ledger_db):
    await ledger_db.bookings.insert_one({"tenant_id": "A", "check_in": "2026-10-07", "check_out": "2026-10-07", "total_amount": 100, "status": "confirmed"})
    data = await reports.get_market_segment_report.__wrapped__("2026-10-07", "2026-10-07", USER)
    assert data["total_bookings"] == sum(row["bookings"] for row in data["market_segments"].values()) == 0
    assert data["excluded_invalid_stays"] == 1


async def test_channel_export_matches_bson_arrivals_complimentary_policy_and_cent_rounding(ledger_db):
    await ledger_db.bookings.insert_many(
        [
            {"tenant_id": "A", "check_in": datetime(2026, 10, 7, tzinfo=UTC), "check_out": "2026-10-08", "total_amount": 2.665, "currency": "EUR", "status": "confirmed", "booking_source": "DIRECT"},
            {
                "tenant_id": "A",
                "check_in": "2026-10-07",
                "check_out": "2026-10-08",
                "total_amount": 999,
                "is_complimentary": True,
                "currency": "EUR",
                "status": "confirmed",
                "booking_source": "DIRECT",
            },
        ]
    )
    sheet = (await workbook(await reports.export_channel_distribution_excel("2026-10-07", "2026-10-07", USER))).active
    assert list(sheet.values)[2][1:] == ("EUR", 2, 2.67, 100)


async def test_transfer_date_filter_selects_the_whole_document_by_its_first_leg(ledger_db):
    await ledger_db.stock_movements.insert_many(
        [
            {"tenant_id": "A", "transfer_id": "midnight", "movement_type": kind, "item_id": source, "counterpart_item_id": target, "created_at": stamp, "quantity": 2, "unit_cost": 10}
            for kind, source, target, stamp in [("transfer_out", "a", "b", "2026-10-07T23:59:59Z"), ("transfer_in", "b", "a", datetime(2026, 10, 8, tzinfo=UTC))]
        ]
    )
    first = await accounting.get_transfer_history(start_date="2026-10-07", end_date="2026-10-07", current_user=USER)
    next_day = await accounting.get_transfer_history(start_date="2026-10-08", end_date="2026-10-08", current_user=USER)
    assert first["count"] == 1 and first["transfers"][0]["balanced"] is True
    assert next_day["count"] == 0


async def test_transfer_pagination_counts_documents_not_legs_and_keeps_tenant_scope(ledger_db):
    await ledger_db.stock_movements.insert_many(
        [
            {
                "tenant_id": tenant,
                "transfer_id": identity,
                "movement_type": kind,
                "item_id": "a" if kind == "transfer_out" else "b",
                "counterpart_item_id": "b" if kind == "transfer_out" else "a",
                "created_at": stamp,
                "quantity": 1,
                "unit_cost": 10,
            }
            for tenant, identity, stamp in [("A", "old", "2026-10-06"), ("A", "selected", "2026-10-07"), ("A", "outside", "2026-10-08"), ("B", "foreign", "2026-10-07"), ("A", "", "2026-10-07")]
            for kind in ("transfer_out", "transfer_in")
        ]
    )
    result = await accounting.get_transfer_history(start_date="2026-10-06", end_date="2026-10-07", limit=1, current_user=USER)
    assert result["count"] == 1 and result["total_count"] == 2 and result["has_more"]
    assert result["transfers"][0]["transfer_id"] == "selected"
    assert result["transfers"][0]["balanced"] is True


@pytest.mark.parametrize("amount,expected", [(2.675, 2.68), (2.665, 2.67)])
async def test_cash_flow_uses_the_same_half_up_rule_as_report_money(ledger_db, amount, expected):
    await ledger_db.cash_flow.insert_one({"tenant_id": "A", "date": "2026-10-07", "transaction_type": "income", "amount": amount, "currency": "EUR"})
    cash = await accounting.get_cash_flow(start_date="2026-10-07", end_date="2026-10-07", current_user=USER)
    assert cash["total_income_by_currency"] == cash["net_cash_flow_by_currency"] == {"EUR": expected}
