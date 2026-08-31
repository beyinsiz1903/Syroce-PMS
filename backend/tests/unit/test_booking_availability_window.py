from datetime import datetime

import pytest
from fastapi import HTTPException

from routers.departments.bookings import _resolve_availability_window


def test_attempted_window_overrides_blocking_booking_dates():
    booking = {
        "check_in": "2026-08-28T14:00:00+00:00",
        "check_out": "2026-08-31T11:00:00+00:00",
    }

    check_in, check_out = _resolve_availability_window(
        booking,
        "2026-08-31T14:00:00+00:00",
        "2026-09-01T11:00:00+00:00",
    )

    assert check_in == datetime.fromisoformat("2026-08-31T14:00:00+00:00")
    assert check_out == datetime.fromisoformat("2026-09-01T11:00:00+00:00")


def test_invalid_or_zero_length_window_is_rejected():
    booking = {"check_in": "2026-08-31", "check_out": "2026-09-01"}

    with pytest.raises(HTTPException) as exc_info:
        _resolve_availability_window(booking, "2026-08-31", "2026-08-31")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "check_out must be after check_in"
