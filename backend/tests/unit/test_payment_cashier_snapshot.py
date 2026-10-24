import pytest
from fastapi import HTTPException

from modules.pms_core.payment_cashier_snapshot import cashier_values


@pytest.mark.parametrize("payment,expected", [
    ({"amount": 100}, (100, "TRY", 100, 1)),
    ({"amount": 5000, "currency": "TRY", "received_currency": "USD", "received_amount": 100, "exchange_rate": .02}, (5000, "USD", 100, 50)),
    ({"amount": 5500, "currency": "TRY", "received_currency": "EUR", "received_amount": 100, "exchange_rate": 100 / 5500}, (5500, "EUR", 100, 55)),
    ({"amount": 100, "currency": "USD", "received_currency": "TRY", "received_amount": 5000, "exchange_rate": 50}, (5000, "TRY", 5000, 1)),
    ({"amount": 100, "currency": "USD", "received_amount": 100, "received_to_try_rate": 50}, (5000, "USD", 100, 50)),
    ({"amount": 100, "currency": "USD", "received_currency": "EUR", "received_amount": 90, "exchange_rate": .9, "received_to_try_rate": 55}, (4950, "EUR", 90, 55)),
    ({"amount": -5000, "currency": "TRY", "payment_type": "refund", "received_currency": "USD", "received_amount": 100, "exchange_rate": .02}, (5000, "USD", 100, 50)),
    ({"amount": 100, "currency": "USD", "reporting_currency": "TRY", "reporting_amount": 5000}, (5000, "USD", 100, 50)),
])
def test_preserves_received_money_and_verified_try_drawer_value(payment, expected):
    result = cashier_values(payment)
    assert (result["amount"], result["currency"], result["original_amount"], result["fx_rate"]) == expected
    assert payment["reporting_amount"] == expected[0]
    assert payment["reporting_currency"] == "TRY"


@pytest.mark.parametrize("payment", [
    {"amount": 100, "currency": "USD"},
    {"amount": 100, "currency": "EUR", "received_to_try_rate": 0},
    {"amount": 5000, "currency": "TRY", "received_currency": "USD", "received_amount": 100},
    {"amount": 5000, "currency": "TRY", "received_currency": "USD", "received_amount": 100, "exchange_rate": 50},
    {"amount": 100, "received_amount": 99},
    {"amount": .001}, {"amount": "NaN"}, {"amount": 0},
])
def test_missing_or_mismatched_fx_cannot_create_an_invented_try_amount(payment):
    with pytest.raises(HTTPException) as error:
        cashier_values(payment)
    assert error.value.status_code == 422
