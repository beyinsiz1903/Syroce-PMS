from modules.pms_core.reporting_financials import (
    effective_collection,
    effective_revenue_adjustment,
    reporting_collection_amount,
    reporting_collection_summary,
    stamp_reporting_values,
)


def test_rate_correction_reduces_revenue_but_is_not_a_collection():
    payment = {"amount": 2500, "method": "discount", "payment_type": "rate_correction", "status": "paid"}
    assert effective_collection(payment) == 0
    assert effective_revenue_adjustment(payment) == 2500


def test_real_payment_and_refund_remain_cash_movements():
    assert effective_collection({"amount": 1000, "method": "card", "status": "paid"}) == 1000
    assert effective_collection({"amount": 1000, "method": "card", "payment_type": "refund", "status": "paid"}) == -1000


def test_reporting_uses_immutable_try_ledger_amount_and_keeps_received_fx_out_of_total():
    payment = {
        "id": "usd-receipt",
        "amount": 4000,
        "currency": "TRY",
        "received_amount": 100,
        "received_currency": "USD",
        "exchange_rate": 0.025,
        "exchange_rate_date": "2026-10-06",
        "method": "cash",
        "status": "paid",
    }
    assert reporting_collection_amount(payment) == 4000
    assert reporting_collection_summary([payment])["amount"] == 4000


def test_reporting_uses_try_received_amount_for_foreign_ledger_and_refund_sign():
    payment = {
        "amount": 100,
        "currency": "EUR",
        "received_amount": 4500,
        "received_currency": "TRY",
        "payment_type": "refund",
        "method": "card",
        "status": "paid",
    }
    assert reporting_collection_amount(payment) == -4500


def test_reporting_excludes_unconvertible_historical_fx_instead_of_using_today_rate():
    payment = {
        "id": "missing-rate",
        "amount": 100,
        "currency": "USD",
        "received_amount": 90,
        "received_currency": "EUR",
        "method": "cash",
        "status": "paid",
    }
    summary = reporting_collection_summary([payment])
    assert summary["amount"] == 0
    assert summary["payment_count"] == 0
    assert summary["conversion_issue_count"] == 1
    assert summary["conversion_issues"][0]["reason"] == "historical_exchange_rate_missing"


def test_explicit_historical_reporting_amount_is_not_revalued():
    payment = {
        "amount": 100,
        "currency": "USD",
        "reporting_amount": 4100,
        "reporting_currency": "TRY",
        "exchange_rate_date": "2025-01-02",
        "method": "bank_transfer",
        "status": "paid",
    }
    assert reporting_collection_amount(payment) == 4100


def test_new_fx_payment_stores_transaction_day_try_value_and_rate_date():
    payment = {
        "amount": 4000,
        "currency": "TRY",
        "received_amount": 100,
        "received_currency": "USD",
        "exchange_rate": 0.025,
        "business_date": "2026-10-06",
    }
    stamp_reporting_values(payment)
    assert payment["reporting_amount"] == 4000
    assert payment["reporting_currency"] == "TRY"
    assert payment["exchange_rate_date"] == "2026-10-06"
