from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance


def _user():
    return SimpleNamespace(
        id="operator",
        tenant_id="tenant-a",
        email="operator@example.test",
        name="Operator",
        role="admin",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["confirmed", "checked_out", "cancelled", "no_show"])
async def test_late_checkout_requires_checked_in_status(monkeypatch, status):
    import routers.reservation_detail as module

    bookings = SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "booking-a", "tenant_id": "tenant-a", "status": status}),
        update_one=AsyncMock(),
    )
    monkeypatch.setattr(module, "db", SimpleNamespace(bookings=bookings))
    monkeypatch.setattr(module, "_enforce_perm", lambda *_: None)

    with pytest.raises(HTTPException) as exc_info:
        await module.late_checkout(
            "booking-a",
            module.LateCheckoutRequest(extra_charge=0),
            current_user=_user(),
            _perm=None,
        )

    assert exc_info.value.status_code == 409
    bookings.update_one.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["checked_in", "checked_out", "cancelled", "no_show"])
async def test_mark_noshow_rejects_ineligible_status_without_mutation(monkeypatch, status):
    import routers.reservation_detail as module

    bookings = SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "booking-a", "tenant_id": "tenant-a", "status": status}),
        update_one=AsyncMock(),
    )
    monkeypatch.setattr(module, "db", SimpleNamespace(bookings=bookings))
    monkeypatch.setattr(module, "_enforce_perm", lambda *_: None)

    with pytest.raises(HTTPException) as exc_info:
        await module.mark_noshow(
            "booking-a",
            current_user=_user(),
            _perm=None,
        )

    assert exc_info.value.status_code == 409
    bookings.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_historical_noshow_does_not_release_room_owned_by_a_new_booking(monkeypatch):
    import routers.reservation_detail as module

    bookings = SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "historic-booking", "tenant_id": "tenant-a", "status": "confirmed", "room_id": "room-a"}),
        update_one=AsyncMock(),
    )
    rooms = SimpleNamespace(update_one=AsyncMock())
    monkeypatch.setattr(module, "db", SimpleNamespace(bookings=bookings, rooms=rooms))
    monkeypatch.setattr(module, "_enforce_perm", lambda *_: None)
    monkeypatch.setattr(module, "_ensure_hotel_context", lambda *_: None)
    monkeypatch.setattr(module, "_log_activity", AsyncMock())

    from core import atomic_booking

    release = AsyncMock()
    monkeypatch.setattr(atomic_booking, "release_booking_nights", release)

    await module.mark_noshow("historic-booking", current_user=_user(), _perm=None)

    rooms.update_one.assert_awaited_once_with(
        {"id": "room-a", "tenant_id": "tenant-a", "current_booking_id": "historic-booking"},
        {"$set": {"status": "available", "current_booking_id": None}},
    )
    release.assert_awaited_once_with("tenant-a", "historic-booking", reason="no_show")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["checked_out", "cancelled", "no_show"])
async def test_room_change_rejects_terminal_status_without_mutation(monkeypatch, status):
    import routers.reservation_detail as module

    bookings = SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "booking-a", "tenant_id": "tenant-a", "status": status}),
        update_one=AsyncMock(),
    )
    rooms = SimpleNamespace(find_one=AsyncMock(), update_one=AsyncMock())
    monkeypatch.setattr(module, "db", SimpleNamespace(bookings=bookings, rooms=rooms))
    monkeypatch.setattr(module, "_enforce_perm", lambda *_: None)

    with pytest.raises(HTTPException) as exc_info:
        await module.room_change(
            "booking-a",
            module.RoomChangeRequest(new_room_id="room-b", reason="test"),
            current_user=_user(),
            _perm=None,
        )

    assert exc_info.value.status_code == 409
    bookings.update_one.assert_not_awaited()
    rooms.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_room_change_posts_upgrade_difference_as_reportable_room_revenue(acceptance):
    a = acceptance
    await a.db.rooms.insert_one({"id": "room-b", "tenant_id": "qa", "room_number": "201", "status": "available", "capacity": 2})
    response = await a.api.post("/api/pms/reservations/synthetic-stay/room-change", json={
        "new_room_id": "room-b", "reason": "Upgrade", "extra_charge": 2000})
    assert response.status_code == 200, response.text
    charge = await a.db.folio_charges.find_one({"charge_type": "room_upgrade"})
    assert charge["folio_id"] == "synthetic-folio"
    assert charge["charge_category"] == "room"
    assert charge["charge_type"] == "room_upgrade"
    assert charge["total"] == 2000
    assert charge["business_date"] == "2026-10-26"
    assert charge["currency"] == "USD"
    assert response.json()["extra_charge"] == 2000
    from modules.pms_core.reporting_ledger import charge_category
    assert charge_category(charge) == "room"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["checked_in", "checked_out", "cancelled", "no_show"])
async def test_cancel_rejects_ineligible_status_without_mutation(monkeypatch, status):
    import routers.hotel_services_pkg.reservations_misc as module

    bookings = SimpleNamespace(
        find_one=AsyncMock(return_value={"id": "booking-a", "tenant_id": "tenant-a", "status": status}),
        update_one=AsyncMock(),
    )
    monkeypatch.setattr(module, "db", SimpleNamespace(bookings=bookings))
    monkeypatch.setattr(module._role_permissions, "enforce_permission", lambda *_: None)

    with pytest.raises(HTTPException) as exc_info:
        await module.cancel_reservation(
            "booking-a",
            module.CancelReservationRequest(reason="test", cancel_type="guest_request"),
            current_user=_user(),
            _perm=None,
        )

    assert exc_info.value.status_code == 409
    bookings.update_one.assert_not_awaited()
