from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core.agency_credit import assert_credit_capacity, booking_net_exposure
from routers.agency_contracts import ApproveRequest


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _length):
        return self.rows


# No period statements in these scenarios (and no database connection).
NO_STATEMENTS = SimpleNamespace(agency_statements=SimpleNamespace(find=lambda *_a, **_k: _Cursor([])))


class _Bookings:
    def __init__(self, rows):
        self.rows = rows

    def find(self, *_args, **_kwargs):
        return _Cursor(self.rows)


@pytest.mark.asyncio
async def test_credit_limit_uses_net_hotel_exposure_in_one_contract_currency():
    database = SimpleNamespace(bookings=_Bookings([
        {"currency": "TRY", "net_to_hotel": 700},
        {"currency": "TRY", "total_amount": 500, "agency_commission_amount": 50},
    ]))
    await assert_credit_capacity(
        database, tenant_id="hotel", agency_id="agency",
        contract={"credit_limit": 1200, "credit_currency": "TRY"},
        booking_currency="TRY", new_net_exposure=50, statements_db=NO_STATEMENTS,
    )


@pytest.mark.asyncio
async def test_credit_limit_rejects_mixed_open_debt_currency_without_fx_guess():
    database = SimpleNamespace(bookings=_Bookings([{"currency": "EUR", "net_to_hotel": 100}]))
    with pytest.raises(HTTPException, match="EUR"):
        await assert_credit_capacity(
            database, tenant_id="hotel", agency_id="agency",
            contract={"credit_limit": 1000, "credit_currency": "TRY"},
            booking_currency="TRY", new_net_exposure=100, statements_db=NO_STATEMENTS,
        )


@pytest.mark.asyncio
async def test_credit_limit_rejects_sale_currency_that_differs_from_contract_currency():
    database = SimpleNamespace(bookings=_Bookings([]))
    with pytest.raises(HTTPException, match="farklı"):
        await assert_credit_capacity(
            database, tenant_id="hotel", agency_id="agency",
            contract={"credit_limit": 1000, "credit_currency": "TRY"},
            booking_currency="EUR", new_net_exposure=100, statements_db=NO_STATEMENTS,
        )


def test_historical_booking_net_exposure_is_reconstructed_only_from_stored_commission():
    assert booking_net_exposure({"total_amount": 1000, "agency_commission_amount": 150}) == 850
    with pytest.raises(HTTPException, match="net kredi"):
        booking_net_exposure({"total_amount": 1000})


def test_contract_approval_requires_explicit_currency_when_credit_is_enabled():
    with pytest.raises(ValueError, match="para birimi"):
        ApproveRequest(credit_limit=1000)
    assert ApproveRequest(credit_limit=1000, credit_currency="TRY").credit_currency == "TRY"
