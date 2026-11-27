from datetime import date

from modules.pms_core.property_report_projections import property_income_report, property_revenue_kpis
from modules.pms_core.property_reporting_currency import HistoricalRates

DAY = date(2026, 11, 12)

def source(code, gross, net, vat, category="room"):
    return {"id": code + category, "business_date": str(DAY), "currency": code, "total": gross, "amount": net,
        "report_source": "folio", "vat_amount": vat, "tax_amount": 0, "charge_category": category}

def rates(base="TRY"):
    return HistoricalRates(base, [{"from_currency": "USD", "to_currency": "TRY", "effective_date": str(DAY), "rate": 50}])

def test_income_headline_is_property_currency_and_original_fx_is_drilldown():
    data = property_income_report([source("TRY", 120, 100, 20), source("USD", 30, 25, 5, "spa")], DAY, DAY, rates())
    assert data["totals_by_currency"]["TRY"]["total"] == 1620
    assert data["totals"]["net"] == 1350
    assert data["totals"]["vat"] == 270
    assert set(data["totals_by_currency"]) == {"TRY"}
    assert data["original_currency_breakdown"]["USD"]["total"] == 30
    assert data["currency_policy"]["complete"]

def test_single_native_source_has_no_foreign_drilldown():
    data = property_income_report([source("TRY", 120, 100, 20)], DAY, DAY, rates())
    assert "original_currency_breakdown" not in data

def test_net_adr_uses_all_paid_nights_once_not_sum_of_native_adrs():
    data = property_revenue_kpis([source("TRY", 120, 100, 20), source("USD", 30, 25, 5)],
        [{"sold_rooms": 2, "sold_rooms_by_currency": {"TRY": 1, "USD": 1}, "total_rooms": 10}], DAY, DAY, rates())
    assert data["room_revenue_net"] == 1350
    assert data["adr_by_currency"] == {"TRY": 675}
    assert data["rev_par_by_currency"] == {"TRY": 135}

def test_missing_rate_is_not_a_native_amount_or_complete_partial_total():
    data = property_income_report([source("TRY", 120, 100, 20), source("EUR", 60, 50, 10)], DAY, DAY, rates())
    assert data["totals"]["total"] is None
    assert data["currency_policy"]["missing_rate_count"] == 1
    assert data["rows"][0]["by_currency"]["TRY"]["total"] is None

def test_property_eur_inverse_and_original_sources_remain_unchanged():
    rows = [source("USD", 30, 25, 5)]
    book = HistoricalRates("EUR", [{"from_currency": "EUR", "to_currency": "USD", "rate": 2, "effective_date": str(DAY)}])
    data = property_income_report(rows, DAY, DAY, book)
    assert data["totals_by_currency"]["EUR"]["total"] == 15
    assert rows[0]["currency"] == "USD" and rows[0]["total"] == 30

def test_unknown_source_tax_never_becomes_zero_net_adr():
    row = {"id": "legacy", "business_date": str(DAY), "currency": "TRY", "total": 120, "charge_category": "room"}
    data = property_revenue_kpis([row], [{"sold_rooms": 1, "total_rooms": 10}], DAY, DAY, rates())
    assert data["adr"] is None
    assert data["room_revenue"] == 120

def test_gl_rounding_identity_derives_net_after_gross_and_aggregate_tax():
    row = source("USD", .02, .01, .01)
    book = HistoricalRates("TRY", [{"from_currency": "USD", "to_currency": "TRY", "effective_date": str(DAY), "rate": "1.333333"}])
    report = property_income_report([row], DAY, DAY, book)
    assert report["totals"]["total"] == .03
    assert report["totals"]["vat"] == .01
    assert report["totals"]["verified_net"] == .02
    kpis = property_revenue_kpis([row], [{"sold_rooms": 1, "total_rooms": 1}], DAY, DAY, book)
    assert kpis["adr"] == .02


def test_unposted_paid_room_currency_is_pending_not_a_complete_zero_or_partial_adr():
    metrics = [{"date": str(DAY), "sold_rooms": 2, "sold_rooms_by_currency": {"TRY": 1, "USD": 1}, "total_rooms": 10}]
    result = property_revenue_kpis([source("TRY", 120, 100, 20)], metrics, DAY, DAY, rates())
    assert result["posting_pending"] and result["adr_by_currency"] == {"TRY": None}
    assert result["total_revenue"] == 120
    result = property_revenue_kpis([source("TRY", 0, 0, 0), source("USD", 0, 0, 0)], metrics, DAY, DAY, rates())
    assert not result["posting_pending"] and result["adr"] == 0
