from datetime import date

from modules.pms_core.property_cost_report import property_cost_report
from modules.pms_core.property_reporting_currency import HistoricalRates

DAY = "2026-11-12"
FIRST = date.fromisoformat(DAY)


def test_cost_and_income_use_the_same_original_day_rate_and_room_revpar_is_net():
    rates = HistoricalRates("TRY", [{"effective_date": DAY, "from_currency": "USD", "to_currency": "TRY", "rate": 50},
        {"effective_date": "2026-11-27", "from_currency": "USD", "to_currency": "TRY", "rate": 70}])
    orders = [{"currency": "USD", "total_amount": 10, "created_at": DAY, "category": "food"}]
    charges = [{"currency": "USD", "amount": 25, "total": 30, "vat_amount": 5, "tax_amount": 0, "business_date": DAY, "charge_category": "room"}]
    metrics = [{"date": DAY, "occupied_rooms": 2, "sold_rooms": 2, "total_rooms": 10}]
    result = property_cost_report(orders, charges, metrics, FIRST, FIRST, rates)
    assert result["currency"] == "TRY" and result["total_mtd_costs_by_currency"] == {"TRY": 500}
    assert result["financial_metrics"]["mtd_revenue"] == 1500
    assert result["financial_metrics"]["gross_profit"] == 1000
    assert result["per_room_metrics"]["mtd_revpar_by_currency"] == {"TRY": 125}
    assert result["cost_categories"]["fnb"] == 500
    assert orders[0]["currency"] == "USD"  # Source records stay immutable.


def test_missing_cost_fx_does_not_produce_known_profit_or_partial_ranking():
    result = property_cost_report([{"currency": "EUR", "total_amount": 10, "created_at": DAY}],
        [], [], FIRST, FIRST, HistoricalRates("TRY"))
    assert result["total_mtd_costs"] is None
    assert result["financial_metrics"]["gross_profit"] is None
    assert result["per_room_metrics"]["cost_to_revpar_ratio"] is None
    assert result["top_3_categories"] == []


def test_property_currency_is_not_assumed_to_be_try():
    result = property_cost_report([{"currency": "EUR", "total_amount": 10, "created_at": DAY}],
        [], [], FIRST, FIRST, HistoricalRates("EUR"))
    assert result["total_mtd_costs_by_currency"] == {"EUR": 10}
    assert result["financial_metrics"]["by_currency"]["EUR"]["gross_profit"] == -10
