from decimal import Decimal

from modules.pms_core.property_reporting_currency import HistoricalRates, PropertyAccumulator


def rate(day, value, source="USD", target="TRY"):
    return {"id": day + source + target, "from_currency": source, "to_currency": target, "effective_date": day, "rate": value}


def test_posted_day_never_uses_current_or_future_rate():
    book = HistoricalRates("TRY", [rate("2026-11-12", 50), rate("2026-11-27", 70)])
    assert book.quote("USD", "2026-11-12")[0] == Decimal(50)
    assert book.quote("USD", "2026-11-11") is None


def test_property_currency_is_not_hardcoded_and_inverse_is_explicit():
    book = HistoricalRates("EUR", [rate("2026-11-12", 2, "EUR", "USD")])
    assert book.quote("USD", "2026-11-12")[0] == Decimal("0.5")
    assert book.quote("EUR", "2026-11-12")[0] == 1
    assert book.quote("GBP", "2026-11-12") is None


def test_recorded_reporting_value_outranks_later_backdated_configuration():
    book = HistoricalRates("TRY", [rate("2026-11-12", 70)])
    source = {"id": "payment", "amount": 30, "reporting_amount": 1500, "reporting_currency": "TRY", "exchange_rate_date": "2026-11-12"}
    assert book.quote("USD", "2026-11-13", source)[0] == 50


def test_missing_rate_makes_metric_unavailable_not_a_partial_sum():
    acc = PropertyAccumulator(HistoricalRates("TRY", []))
    acc.add("revenue", 100, {"id": "try", "currency": "TRY", "business_date": "2026-11-12"})
    acc.add("revenue", 30, {"id": "usd", "currency": "USD", "business_date": "2026-11-12"})
    assert acc.total("revenue") is None
    assert acc.total("room") == 0
    assert acc.issues[0]["id"] == "usd"


def test_each_business_day_is_valued_before_period_sum_and_adr_uses_all_rooms():
    acc = PropertyAccumulator(HistoricalRates("TRY", [rate("2026-11-12", 50), rate("2026-11-13", 60)]))
    acc.add("room", 1000, {"currency": "TRY", "business_date": "2026-11-12"})
    acc.add("room", 30, {"currency": "USD", "business_date": "2026-11-12"})
    acc.add("room", 30, {"currency": "USD", "business_date": "2026-11-13"})
    assert acc.total("room") == 4300
    assert acc.average("room", 4) == 1075
    assert acc.average("room", 10) == 430


def test_refund_uses_same_recorded_value_and_zero_does_not_require_fx():
    book = HistoricalRates("TRY", [])
    acc = PropertyAccumulator(book)
    acc.add("collection", 30, {"currency": "USD", "business_date": "2026-11-12", "amount": 30, "reporting_amount": 1500, "reporting_currency": "TRY"})
    acc.add("collection", -30, {"currency": "USD", "business_date": "2026-11-13", "amount": -30, "reporting_amount": -1500, "reporting_currency": "TRY"})
    acc.add("comp", 0, {"currency": "GBP", "business_date": "2026-11-13"})
    assert acc.total("collection") == 0
    assert acc.total("comp") == 0
    assert not acc.issues


def test_round_each_day_currency_group_before_summing_period():
    acc = PropertyAccumulator(HistoricalRates("TRY", [rate("2026-11-12", "1.333333")]))
    for _ in range(3):
        acc.add("vat", "0.01", {"currency": "USD", "business_date": "2026-11-12"})
    assert acc.total("vat") == 0.04


def test_unknown_tax_and_original_concession_are_not_zero():
    acc = PropertyAccumulator(HistoricalRates("TRY", []))
    acc.add("discount", None, {"currency": "TRY", "business_date": "2026-11-12"})
    acc.add("net", 0, {"currency": "TRY", "business_date": "2026-11-12"})
    assert acc.total("discount") is None
    assert acc.total("net") == 0


def test_invalid_or_missing_base_currency_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        HistoricalRates("", [])


def test_cross_rate_requires_two_historical_legs_and_keeps_future_rates_out():
    book = HistoricalRates("EUR", [rate("2026-11-12", 50), rate("2026-11-12", 55, "EUR"),
        rate("2026-11-27", 80, "EUR")])
    value, evidence = book.quote("USD", "2026-11-12")
    assert value == Decimal(50) / Decimal(55)
    assert evidence["kind"] == "dated_property_cross_rate" and evidence["via"] == "TRY"
    assert HistoricalRates("EUR", [rate("2026-11-12", 50)]).quote("USD", "2026-11-12") is None


def test_legacy_recorded_cash_value_is_preserved_when_property_currency_differs():
    book = HistoricalRates("EUR", [rate("2026-11-12", 60, "EUR"), rate("2026-11-12", 55)])
    value, evidence = book.quote("USD", "2026-11-13", {"id": "receipt", "amount": 30,
        "reporting_amount": 1500, "reporting_currency": "TRY", "exchange_rate_date": "2026-11-12"})
    assert value * 30 == Decimal(25)  # actual 1500 TRY cash, not a new USD valuation
    assert evidence["kind"] == "recorded_reporting_value_cross"
