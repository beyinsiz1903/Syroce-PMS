from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routers.marketplace_b2b import MarketplaceReservationCreate, _last_occupied_date, _require_hotel_admin


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
