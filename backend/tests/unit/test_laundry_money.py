import pytest
from fastapi import HTTPException

from core.laundry_money import laundry_currency, laundry_delivery_money, laundry_money_snapshot


def test_fx_half_up_rounding_and_same_currency_identity():
    assert laundry_money_snapshot(150, "TRY", "USD", 0.0067)["folio_total"] == 1.01
    same = laundry_money_snapshot(150, "TL", "TRY", 99)
    assert same["exchange_rate"] == 1 and same["folio_total"] == 150
    assert laundry_currency(" usd ") == "USD"


@pytest.mark.parametrize("rate", [None, True, 0, -1, "NaN", "Infinity", 1e10])
def test_missing_or_invalid_fx_is_never_defaulted_to_one(rate):
    with pytest.raises(HTTPException):
        laundry_money_snapshot(150, "TRY", "USD", rate)


def test_zero_rounded_or_overflowed_folio_amount_is_rejected():
    for amount, rate in ((0.01, 0.00001), (1e9, 10)):
        with pytest.raises(HTTPException):
            laundry_money_snapshot(amount, "TRY", "USD", rate)


@pytest.mark.parametrize("changes", [{"folio_currency": "EUR"}, {"folio_total": 99}, {"folio_total": None}])
def test_persisted_snapshot_cannot_be_reinterpreted(changes):
    order = {"total": 150, "currency": "TRY", "folio_currency": "USD", "folio_total": 3, "exchange_rate": 0.02, **changes}
    with pytest.raises(HTTPException) as failure:
        laundry_delivery_money(order, "USD")
    assert failure.value.status_code == 409
