from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import marketplace_b2b


class _Collection:
    def __init__(self, document=None):
        self.document = document
        self.queries = []

    async def find_one(self, query, *_args, **_kwargs):
        self.queries.append(query)
        return self.document


@pytest.mark.asyncio
async def test_voucher_uses_authorized_pms_booking_while_projection_is_pending(monkeypatch):
    marketplace = _Collection()
    canonical = _Collection(
        {
            "id": "booking-1",
            "tenant_id": "hotel-1",
            "agency_id": "agency-1",
            "agency_completion": {"kind": "marketplace", "status": "pending"},
            "confirmation_code": "MKT-BOOKING",
            "hotel_name": "Canyon Hotel",
            "guest_name": "Murat Sutay",
            "check_in": "2026-10-15T14:00:00",
            "check_out": "2026-10-18T11:00:00",
            "total_amount": 4500,
            "currency": "TRY",
        }
    )
    monkeypatch.setattr(
        marketplace_b2b,
        "get_system_db",
        lambda: SimpleNamespace(marketplace_bookings=marketplace, bookings=canonical),
    )

    voucher = await marketplace_b2b._agency_voucher_booking("booking-1", "agency-1")

    assert voucher["confirmation_code"] == "MKT-BOOKING"
    assert voucher["guest_name"] == "Murat Sutay"
    assert canonical.queries == [
        {
            "id": "booking-1",
            "agency_id": "agency-1",
            "agency_completion.kind": "marketplace",
        }
    ]


@pytest.mark.asyncio
async def test_voucher_does_not_expose_a_booking_outside_the_agency_scope(monkeypatch):
    marketplace = _Collection()
    canonical = _Collection()
    monkeypatch.setattr(
        marketplace_b2b,
        "get_system_db",
        lambda: SimpleNamespace(marketplace_bookings=marketplace, bookings=canonical),
    )

    with pytest.raises(HTTPException) as error:
        await marketplace_b2b._agency_voucher_booking("other-agency-booking", "agency-1")

    assert error.value.status_code == 404
