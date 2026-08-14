from datetime import datetime

from models.enums import BookingStatus, ChannelType
from models.schemas.bookings import Booking, BookingExtended


def test_booking_model_preserves_identity_lifecycle_and_financial_fields():
    booking = Booking(
        tenant_id="tenant-test",
        guest_id="guest-test",
        room_id="room-test",
        check_in="2026-08-15T14:00:00+00:00",
        check_out="2026-08-16T11:00:00+00:00",
        adults=1,
        children=0,
        total_amount=1000,
        status=BookingStatus.CONFIRMED,
        channel=ChannelType.DIRECT,
    )

    dumped = booking.model_dump()
    assert dumped["tenant_id"] == "tenant-test"
    assert dumped["guest_id"] == "guest-test"
    assert dumped["room_id"] == "room-test"
    assert dumped["total_amount"] == 1000
    assert dumped["status"] == BookingStatus.CONFIRMED
    assert isinstance(dumped["check_in"], datetime)
    assert isinstance(dumped["check_out"], datetime)
    assert isinstance(dumped["created_at"], datetime)


def test_booking_extended_remains_a_compatible_alias():
    assert BookingExtended is Booking
