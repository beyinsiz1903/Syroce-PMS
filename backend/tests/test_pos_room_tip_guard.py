from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms.pos_fnb.checkout_benefits import quote_checkout
from domains.pms.pos_fnb.folio_lines import checkout_lines


def database():
    return SimpleNamespace(hotel_settings=SimpleNamespace(find_one=AsyncMock(return_value={"currency": "TRY"})),
        bookings=SimpleNamespace(find_one=AsyncMock(return_value={"id": "booking", "status": "checked_in"})))


@pytest.mark.asyncio
@pytest.mark.parametrize("tip", [.01, 1.01, 10])
async def test_room_quote_rejects_tip_that_folio_lines_cannot_represent(tip):
    with pytest.raises(HTTPException) as exc:
        await quote_checkout(database(), "hotel", {"id": "order", "grand_total": 110, "tax_amount": 10},
            {"booking_id": "booking", "post_to_folio": True, "tip_amount": tip})
    assert exc.value.status_code == 422
    assert "bahşiş" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_zero_tip_room_quote_still_equals_exact_folio_total():
    quote = await quote_checkout(database(), "hotel", {"id": "order", "grand_total": 110, "tax_amount": 10},
        {"booking_id": "booking", "post_to_folio": True, "tip_amount": 0})
    assert quote["payable"] == sum(line["total"] for line in checkout_lines({"total_amount": 110, "tax_amount": 10})) == 110


@pytest.mark.asyncio
async def test_cash_tip_quote_remains_available():
    quote = await quote_checkout(database(), "hotel", {"id": "order", "grand_total": 110, "tax_amount": 10}, {"tip_amount": 1.01})
    assert quote["payable"] == 111.01
    assert quote["tax_amount"] == 10
