"""Tenant-scoped, isolated database acceptance of historical reporting views."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

from modules.pms_core.property_financial_summary import property_financial_summary
from modules.pms_core.property_reporting_currency import load_historical_rates
from routers.reports_pkg import standard_reports

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
DAY = "2026-11-12"

async def seed(db):
    await db.hotel_settings.insert_one({"tenant_id": "A", "currency": "TRY"})
    await db.currency_rates.insert_many([
        {"tenant_id": "A", "id": "old", "effective_date": DAY, "from_currency": "USD", "to_currency": "TRY", "rate": 50},
        {"tenant_id": "A", "id": "future", "effective_date": "2026-11-27", "from_currency": "USD", "to_currency": "TRY", "rate": 70},
        {"tenant_id": "B", "id": "other", "effective_date": DAY, "from_currency": "EUR", "to_currency": "TRY", "rate": 99},
    ])
    await db.folios.insert_one({"tenant_id": "A", "id": "f", "status": "open", "currency": "USD"})
    await db.folio_charges.insert_one({"tenant_id": "A", "id": "sale", "folio_id": "f", "business_date": DAY,
        "charge_category": "room", "currency": "USD", "total": 30, "amount": 25, "vat_amount": 5, "tax_amount": 0})
    await db.payments.insert_one({"tenant_id": "A", "id": "paid", "folio_id": "f", "business_date": DAY,
        "currency": "USD", "amount": 10, "method": "cash", "reporting_currency": "TRY", "reporting_amount": 500})

async def test_property_rate_loader_does_not_use_other_tenant_or_future_day(ledger_db):
    await seed(ledger_db)
    book = await load_historical_rates(ledger_db, "A", date.fromisoformat(DAY), date.fromisoformat(DAY))
    assert book.currency == "TRY" and book.quote("USD", DAY)[0] == 50
    assert book.quote("EUR", DAY) is None

async def test_financial_summary_and_open_receivable_use_original_sources_without_mutation(ledger_db):
    await seed(ledger_db)
    payload = {"revenue": {}, "tax": {}, "payments": {"by_method": {"cash": {"count": 1}}}, "open_folios": {"count": 1}}
    before = await ledger_db.folio_charges.find_one({"id": "sale"})
    result = await property_financial_summary(ledger_db, "A", payload, DAY)
    assert result["revenue"]["total_by_currency"] == {"TRY": 1250}
    assert result["revenue"]["total_with_tax_by_currency"] == {"TRY": 1500}
    assert result["tax"]["total_by_currency"] == {"TRY": 250}
    assert result["payments"]["total_by_currency"] == {"TRY": 500}
    assert result["open_folios"]["balance_by_currency"] == {"TRY": {"total": 1000, "receivable": 1000, "overpayment": 0}}
    assert result["net_position_by_currency"] == {"TRY": 1000}
    assert await ledger_db.folio_charges.find_one({"id": "sale"}) == before
    assert payload["revenue"] == {}

async def test_missing_foreign_opening_balance_rate_is_unavailable_not_zero(ledger_db):
    await seed(ledger_db)
    await ledger_db.folios.insert_one({"tenant_id": "A", "id": "legacy", "status": "open", "currency": "EUR", "opening_balance": 100})
    result = await property_financial_summary(ledger_db, "A",
        {"revenue": {}, "tax": {}, "payments": {"by_method": {}}, "open_folios": {}}, DAY)
    assert result["open_folios"]["balance"]["total"] is None
    assert result["currency_policy"]["missing_rate_count"] == 1

async def test_mobile_revenue_route_uses_tax_exclusive_adr_and_all_paid_nights(ledger_db, monkeypatch):
    await seed(ledger_db)
    monkeypatch.setattr(standard_reports, "db", ledger_db)
    monkeypatch.setattr(standard_reports, "load_stay_night_metrics", AsyncMock(return_value=[{"sold_rooms": 2, "total_rooms": 10}]))
    result = await standard_reports.get_revenue_report.__wrapped__(DAY, DAY, SimpleNamespace(tenant_id="A"))
    assert result["total_revenue_by_currency"] == {"TRY": 1500}
    assert result["adr_by_currency"] == {"TRY": 625}
    assert result["rev_par_by_currency"] == {"TRY": 125}
    assert result["original_currency_breakdown"]["USD"]["total"] == 30

async def test_settled_foreign_folio_is_zero_even_when_cash_uses_a_later_rate(ledger_db):
    await seed(ledger_db)
    await ledger_db.payments.insert_one({"tenant_id": "A", "id": "later", "folio_id": "f", "business_date": "2026-11-13",
        "currency": "USD", "amount": 20, "method": "cash", "reporting_currency": "TRY", "reporting_amount": 1200})
    result = await property_financial_summary(ledger_db, "A",
        {"revenue": {}, "tax": {}, "payments": {"by_method": {}}, "open_folios": {}}, DAY)
    assert result["open_folios"]["balance"]["total"] == 0

async def test_partially_settled_foreign_ar_is_not_reduced_by_cash_fx_gain(ledger_db):
    await seed(ledger_db)
    await ledger_db.payments.update_one({"id": "paid"}, {"$set": {"reporting_amount": 600}})
    result = await property_financial_summary(ledger_db, "A",
        {"revenue": {}, "tax": {}, "payments": {"by_method": {}}, "open_folios": {}}, DAY)
    assert result["payments"]["total"] == 600
    assert result["open_folios"]["balance"]["total"] == 1000  # 20 USD still due, carrying rate 50


async def test_base_net_zero_does_not_hide_unsettled_debt_and_credit_in_different_currencies(ledger_db):
    await seed(ledger_db)
    await ledger_db.payments.insert_one({"tenant_id": "A", "id": "credit", "folio_id": "f", "business_date": DAY,
        "currency": "EUR", "amount": 20, "method": "cash", "reporting_currency": "TRY", "reporting_amount": 1000})
    result = await property_financial_summary(ledger_db, "A",
        {"revenue": {}, "tax": {}, "payments": {"by_method": {}}, "open_folios": {}}, DAY)
    assert result["open_folios"]["balance"] == {"total": 0, "receivable": 1000, "overpayment": -1000}


async def test_multiple_ar_carrying_rates_require_allocation_evidence_not_a_guess(ledger_db):
    await seed(ledger_db)
    await ledger_db.currency_rates.insert_one({"tenant_id": "A", "effective_date": "2026-11-13", "from_currency": "USD", "to_currency": "TRY", "rate": 60})
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "id": "next-sale", "folio_id": "f", "business_date": "2026-11-13",
        "charge_category": "room", "currency": "USD", "total": 10, "amount": 10, "vat_amount": 0, "tax_amount": 0})
    result = await property_financial_summary(ledger_db, "A",
        {"revenue": {}, "tax": {}, "payments": {"by_method": {}}, "open_folios": {}}, DAY)
    assert result["open_folios"]["balance"]["total"] is None
    assert result["currency_policy"]["missing_rate_count"] == 0
    assert result["currency_policy"]["unverified_valuation_count"] == 1
