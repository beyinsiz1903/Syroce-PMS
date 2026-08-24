import pytest
from pydantic import ValidationError

from domains.pms.activity_scheduler_router import Activity, ActivityBookingCreate


def test_activity_rejects_invalid_capacity_duration_and_price():
    with pytest.raises(ValidationError):
        Activity(name="Yoga", capacity=0)
    with pytest.raises(ValidationError):
        Activity(name="Yoga", duration_min=5)
    with pytest.raises(ValidationError):
        Activity(name="Yoga", price=-1)


def test_activity_booking_requires_timezone_and_valid_duration():
    with pytest.raises(ValidationError):
        ActivityBookingCreate(
            activity_id="a1",
            resource_id="r1",
            guest_id="g1",
            starts_at="2026-08-24T10:00:00",
        )
    booking = ActivityBookingCreate(
        activity_id="a1",
        resource_id="r1",
        guest_id="g1",
        starts_at="2026-08-24T10:00:00+03:00",
        duration_min=60,
    )
    assert booking.starts_at.endswith("+03:00")

