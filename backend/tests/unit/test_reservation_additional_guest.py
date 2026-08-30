from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_additional_guest_reuses_canonical_identity_and_links_once(monkeypatch):
    from routers import reservation_detail

    bookings = SimpleNamespace(
        find_one=AsyncMock(
            return_value={
                "id": "booking-1",
                "tenant_id": "tenant-1",
                "guest_id": "primary-guest",
                "status": "checked_in",
                "check_out": "2026-08-31T12:00:00",
            }
        )
    )
    guests = SimpleNamespace(insert_one=AsyncMock())
    booking_guests = SimpleNamespace(
        find_one=AsyncMock(return_value=None),
        insert_one=AsyncMock(),
    )
    monkeypatch.setattr(
        reservation_detail,
        "db",
        SimpleNamespace(bookings=bookings, guests=guests, booking_guests=booking_guests),
    )
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "_ensure_hotel_context", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "ensure_reservation_mutable", AsyncMock())
    monkeypatch.setattr(
        reservation_detail,
        "find_existing_guest_by_identity",
        AsyncMock(return_value={"id": "existing-guest", "id_number": "12345678901"}),
    )

    result = await reservation_detail.add_reservation_guest(
        "booking-1",
        reservation_detail.ReservationGuestCreate(
            name="  Ayşe Yılmaz  ",
            id_number="12345678901",
            nationality="TR",
        ),
        current_user=SimpleNamespace(tenant_id="tenant-1", role="admin", id="user-1", name="Resepsiyon"),
        _perm=None,
    )

    assert result == {
        "status": "ok",
        "guest_id": "existing-guest",
        "created": False,
        "linked": True,
        "already_linked": False,
    }
    guests.insert_one.assert_not_awaited()
    booking_guests.insert_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_additional_guest_link_is_idempotent(monkeypatch):
    from routers import reservation_detail

    monkeypatch.setattr(
        reservation_detail,
        "db",
        SimpleNamespace(
            bookings=SimpleNamespace(
                find_one=AsyncMock(
                    return_value={
                        "id": "booking-1",
                        "guest_id": "primary-guest",
                        "status": "checked_in",
                        "check_out": "2026-08-31T12:00:00",
                    }
                )
            ),
            guests=SimpleNamespace(insert_one=AsyncMock()),
            booking_guests=SimpleNamespace(
                find_one=AsyncMock(return_value={"id": "link-1"}),
                insert_one=AsyncMock(),
            ),
        ),
    )
    monkeypatch.setattr(reservation_detail, "_enforce_perm", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "_ensure_hotel_context", lambda *_args: None)
    monkeypatch.setattr(reservation_detail, "ensure_reservation_mutable", AsyncMock())
    monkeypatch.setattr(
        reservation_detail,
        "find_existing_guest_by_identity",
        AsyncMock(return_value={"id": "existing-guest"}),
    )

    result = await reservation_detail.add_reservation_guest(
        "booking-1",
        reservation_detail.ReservationGuestCreate(name="Ayşe Yılmaz", id_number="12345678901", nationality="TR"),
        current_user=SimpleNamespace(tenant_id="tenant-1", role="admin", id="user-1", name="Resepsiyon"),
        _perm=None,
    )

    assert result["already_linked"] is True
    assert result["linked"] is False
    reservation_detail.db.booking_guests.insert_one.assert_not_awaited()
