from routers.travel_agent_arap import (
    CreatePaymentPlanRequest,
    RecordPaymentRequest,
    _currency_code,
    _oldest_date,
    _round_currency_map,
    _single_currency_amount,
    _sum_currency_maps,
)


def test_currency_helpers_preserve_separate_ledgers():
    rows = [
        {"balance_by_currency": {"TRY": 125.5, "EUR": 20}},
        {"balance_by_currency": {"try": -25.5, "USD": 10}},
    ]

    assert _sum_currency_maps(rows, "balance_by_currency") == {
        "TRY": 100.0,
        "EUR": 20.0,
        "USD": 10.0,
    }
    assert _round_currency_map({"EUR": 12.345, "TRY": 0}) == {"EUR": 12.35}
    assert _single_currency_amount({"EUR": 12.35}) == 12.35
    assert _single_currency_amount({"EUR": 12.35, "TRY": 100}) == 0


def test_currency_code_uses_valid_fallback_for_legacy_rows():
    assert _currency_code("eur") == "EUR"
    assert _currency_code(None, "USD") == "USD"
    assert _currency_code("not-a-code", "TRY") == "TRY"


def test_payment_and_plan_contracts_accept_currency():
    payment = RecordPaymentRequest(agency_id="agency-1", amount=50, currency="EUR")
    plan = CreatePaymentPlanRequest(
        agency_id="agency-1",
        total_amount=300,
        installments=3,
        start_date="2026-09-28",
        currency="USD",
    )

    assert payment.currency == "EUR"
    assert plan.currency == "USD"


def test_oldest_date_accepts_mixed_legacy_types():
    from datetime import UTC, datetime

    oldest = _oldest_date([datetime(2026, 9, 20, tzinfo=UTC), "2026-09-19T10:00:00Z", "invalid"])

    assert oldest == "2026-09-19T10:00:00Z"
