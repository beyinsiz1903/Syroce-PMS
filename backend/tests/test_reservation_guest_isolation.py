"""Reservation detail guest edits must not mutate another booking's guest."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from routers.reservation_detail import GuestUpdate, update_reservation_guest


@pytest.mark.asyncio
async def test_shared_guest_edit_isolated_to_the_current_reservation():
    """Two bookings sharing a legacy guest record are separated on edit."""
    bookings = SimpleNamespace(
        find_one=AsyncMock(
            side_effect=[
                {
                    "id": "booking-current",
                    "tenant_id": "tenant-1",
                    "guest_id": "guest-shared",
                    "status": "confirmed",
                },
                {"id": "booking-other"},
            ]
        ),
        update_one=AsyncMock(),
    )
    guests = SimpleNamespace(
        find_one=AsyncMock(
            return_value={
                "id": "guest-shared",
                "tenant_id": "tenant-1",
                "name": "Aynı İsim",
                "email": "same@example.test",
            }
        ),
        insert_one=AsyncMock(),
        update_one=AsyncMock(),
    )
    fake_db = SimpleNamespace(bookings=bookings, guests=guests)
    user = SimpleNamespace(role="admin", tenant_id="tenant-1", name="Operatör")

    with (
        patch("routers.reservation_detail.db", fake_db),
        patch("routers.reservation_detail._enforce_perm"),
        patch("routers.reservation_detail._ensure_hotel_context"),
        patch("routers.reservation_detail.ensure_reservation_mutable", new=AsyncMock()),
        patch("routers.reservation_detail._log_activity", new=AsyncMock()),
        patch("routers.pms_guests._encrypt_guest", side_effect=lambda payload: payload),
    ):
        result = await update_reservation_guest(
            "booking-current",
            GuestUpdate(name="Düzeltilen Misafir"),
            user,
        )

    assert result == {"success": True}
    guests.update_one.assert_not_awaited()
    inserted_guest = guests.insert_one.await_args.args[0]
    assert inserted_guest["id"] != "guest-shared"
    assert inserted_guest["name"] == "Düzeltilen Misafir"
    assert inserted_guest["email"] == "same@example.test"

    booking_update = bookings.update_one.await_args
    assert booking_update.args[0] == {"id": "booking-current", "tenant_id": "tenant-1"}
    assert booking_update.args[1]["$set"]["guest_id"] == inserted_guest["id"]
    assert booking_update.args[1]["$set"]["guest_name"] == "Düzeltilen Misafir"
