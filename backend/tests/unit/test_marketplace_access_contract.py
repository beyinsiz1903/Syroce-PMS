from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routers import marketplace_b2b
from routers.marketplace_b2b import MarketplaceReservationCreate, _last_occupied_date, _require_hotel_admin


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return self.rows


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, *_args, **_kwargs):
        return _Cursor(self.rows)


def test_marketplace_listing_management_rejects_guest_and_staff_roles():
    for role in ("guest", "staff", "front_desk", "agency_admin"):
        with pytest.raises(HTTPException) as error:
            _require_hotel_admin(SimpleNamespace(role=role, tenant_id="hotel-1"))
        assert error.value.status_code == 403


def test_marketplace_listing_management_allows_hotel_management():
    assert _require_hotel_admin(SimpleNamespace(role="admin", tenant_id="hotel-1")) == "hotel-1"
    assert _require_hotel_admin(SimpleNamespace(role="supervisor", tenant_id="hotel-1")) == "hotel-1"


def test_marketplace_stay_authorization_uses_final_occupied_night():
    assert _last_occupied_date("2026-09-25", "2026-09-26") == "2026-09-25"
    assert _last_occupied_date("2026-09-25", "2026-09-29") == "2026-09-28"


def test_marketplace_booking_payload_rejects_invalid_capacity_and_identity():
    with pytest.raises(ValidationError):
        MarketplaceReservationCreate(
            tenant_id="hotel-1",
            room_type="Standard",
            check_in="2026-09-25",
            check_out="2026-09-26",
            guest_name="X",
            adults=0,
            children=99,
        )


@pytest.mark.asyncio
async def test_marketplace_price_prefers_shared_agency_calendar(monkeypatch):
    fake_db = SimpleNamespace(
        agency_rate_calendar=_Collection([
            {"date": "2026-09-25", "rate": 900},
            {"date": "2026-09-26", "rate": 1100},
        ]),
        hr_rate_calendar=_Collection([{"date": "2026-09-25", "rate": 1500}]),
        rate_calendar=_Collection([]),
    )
    monkeypatch.setattr(marketplace_b2b, "db", fake_db)

    result = await marketplace_b2b._marketplace_stay_price(
        tenant_id="hotel-1",
        agency_id="agency-1",
        room_type="Standard",
        check_in="2026-09-25",
        check_out="2026-09-27",
        fallback_rate=2000,
    )

    assert result["sellable"] is True
    assert result["total_price"] == 2000
    assert result["nightly_rates"] == [
        {"date": "2026-09-25", "rate": 900.0},
        {"date": "2026-09-26", "rate": 1100.0},
    ]


@pytest.mark.asyncio
async def test_marketplace_price_honors_agency_stop_sell(monkeypatch):
    fake_db = SimpleNamespace(
        agency_rate_calendar=_Collection([{"date": "2026-09-25", "rate": 900, "stop_sell": True}]),
        hr_rate_calendar=_Collection([]),
        rate_calendar=_Collection([]),
    )
    monkeypatch.setattr(marketplace_b2b, "db", fake_db)

    result = await marketplace_b2b._marketplace_stay_price(
        tenant_id="hotel-1",
        agency_id="agency-1",
        room_type="Standard",
        check_in="2026-09-25",
        check_out="2026-09-26",
        fallback_rate=2000,
    )

    assert result == {"sellable": False, "nightly_rates": [], "total_price": 0.0}
