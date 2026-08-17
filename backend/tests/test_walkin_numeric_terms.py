import math

import pytest
from fastapi import HTTPException

from domains.pms.frontdesk_router import _normalize_walk_in_terms
from domains.pms.schemas import WalkInBookingRequest


def _request() -> WalkInBookingRequest:
    return WalkInBookingRequest(
        guest_name="Test Guest",
        guest_phone="",
        room_id="room-1",
        nights=1,
        rate_per_night=1,
    )


def test_walk_in_terms_normalize_serialized_numbers():
    request = _request()
    request.nights = "2"
    request.rate_per_night = "12.50"

    assert _normalize_walk_in_terms(request, {}) == (2, 12.5, 25.0)


@pytest.mark.parametrize(
    ("nights", "rate"),
    [
        ("not-a-number", 10),
        (0, 10),
        (366, 10),
        (1, 0),
        (1, math.inf),
    ],
)
def test_walk_in_terms_reject_invalid_values(nights, rate):
    request = _request()
    request.nights = nights
    request.rate_per_night = rate

    with pytest.raises(HTTPException) as exc_info:
        _normalize_walk_in_terms(request, {})

    assert exc_info.value.status_code == 400


def test_walk_in_terms_normalize_legacy_room_rate():
    request = _request()
    request.rate_per_night = None

    assert _normalize_walk_in_terms(request, {"base_price": "99.90"}) == (
        1,
        99.9,
        99.9,
    )
