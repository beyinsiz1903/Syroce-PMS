import pytest
from fastapi import HTTPException

from domains.pms.cashier_router import _cashier_number


@pytest.mark.parametrize("value", [None, "", "wrong", True, -1, "NaN", "Infinity", "-Infinity", "0.001", "1000000001"])
def test_cashier_money_rejects_invalid_values_without_coercion(value):
    with pytest.raises(HTTPException) as error:
        _cashier_number(value, "Tutar")
    assert error.value.status_code == 400


@pytest.mark.parametrize("value", [None, "", 0, -1, "NaN", "Infinity", True])
def test_foreign_rate_must_be_explicit_positive_and_finite(value):
    with pytest.raises(HTTPException):
        _cashier_number(value, "Kur", positive=True, money=False)


def test_cashier_accepts_zero_opening_exact_cents_and_explicit_rate():
    assert _cashier_number(0, "Açılış") == 0
    assert _cashier_number("12.30", "Tutar", positive=True) == 12.3
    assert _cashier_number("40.123456", "Kur", positive=True, money=False) == 40.123456
