from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.atomic_booking import BookingConflictError
from core.room_auto_assignment import (
    create_booking_with_auto_assignment,
    find_auto_assignment_candidates,
    normalize_room_type,
)


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    async def to_list(self, _length):
        return list(self._docs)


class _Collection:
    def __init__(self, docs):
        self._docs = docs
        self.calls = []

    def find(self, query, projection):
        self.calls.append((query, projection))
        return _Cursor(self._docs)


def _database(*, rooms=(), bookings=(), blocks=(), locks=()):
    return SimpleNamespace(
        rooms=_Collection(rooms),
        bookings=_Collection(bookings),
        room_blocks=_Collection(blocks),
        room_night_locks=_Collection(locks),
    )


def _booking():
    return {
        "id": "booking-1",
        "tenant_id": "tenant-1",
        "property_id": "property-1",
        "room_type": "Jakuzili Ağaç Ev",
        "check_in": "2026-08-22",
        "check_out": "2026-08-24",
        "status": "confirmed",
    }


def test_room_type_normalization_handles_turkish_labels():
    assert normalize_room_type("  JAKUZİLİ   Ağaç Ev ") == normalize_room_type("jakuzili ağaç ev")


@pytest.mark.asyncio
async def test_candidates_exclude_booked_blocked_locked_and_unsellable_rooms():
    database = _database(
        rooms=[
            {"id": "r101", "room_number": "101", "room_type": "Jakuzili Ağaç Ev"},
            {"id": "r102", "room_number": "102", "room_type": "Jakuzili Ağaç Ev", "status": "maintenance"},
            {"id": "r103", "room_number": "103", "room_type": "Jakuzili Ağaç Ev"},
            {"id": "r104", "room_number": "104", "room_type": "Jakuzili Ağaç Ev"},
            {"id": "r105", "room_number": "105", "room_type": "Jakuzili Ağaç Ev"},
            {"id": "r10", "room_number": "10", "room_type": "JAKUZİLİ AĞAÇ EV"},
            {"id": "other", "room_number": "1", "room_type": "Standart"},
            {"id": "other-property", "room_number": "2", "room_type": "Jakuzili Ağaç Ev", "property_id": "property-2"},
        ],
        bookings=[{"room_id": "r101"}],
        blocks=[{"room_id": "r103", "allow_sell": False}],
        locks=[{"room_id": "r105"}],
    )

    candidates = await find_auto_assignment_candidates(
        database=database,
        tenant_id="tenant-1",
        property_id="property-1",
        room_type="jakuzili agac ev",
        check_in="2026-08-22",
        check_out="2026-08-24",
    )

    assert [room["id"] for room in candidates] == ["r10", "r104"]
    booking_query = database.bookings.calls[0][0]
    assert booking_query["check_in"] == {"$lt": "2026-08-24"}
    assert booking_query["check_out"] == {"$gt": "2026-08-22"}
    lock_query = database.room_night_locks.calls[0][0]
    assert lock_query["night_date"] == {"$gte": "2026-08-22", "$lt": "2026-08-24"}


@pytest.mark.asyncio
async def test_atomic_conflict_tries_next_available_room(monkeypatch):
    candidates = [
        {"id": "room-101", "room_number": "101"},
        {"id": "room-102", "room_number": "102"},
    ]
    monkeypatch.setattr(
        "core.room_auto_assignment.find_auto_assignment_candidates",
        AsyncMock(return_value=candidates),
    )
    creator = AsyncMock(side_effect=[BookingConflictError("claimed concurrently"), {"id": "booking-1"}])

    created, room = await create_booking_with_auto_assignment(
        database=SimpleNamespace(),
        tenant_id="tenant-1",
        booking_doc=_booking(),
        create_booking=creator,
    )

    assert created == {"id": "booking-1"}
    assert room["id"] == "room-102"
    assert creator.await_count == 2
    assert creator.await_args_list[0].kwargs["booking_doc"]["room_id"] == "room-101"
    second_doc = creator.await_args_list[1].kwargs["booking_doc"]
    assert second_doc["room_id"] == "room-102"
    assert second_doc["allocation_source"] == "ota_auto_assignment"


@pytest.mark.asyncio
async def test_validated_provider_room_number_is_preferred(monkeypatch):
    candidates = [
        {"id": "room-201", "room_number": "201"},
        {"id": "room-202", "room_number": "202"},
    ]
    monkeypatch.setattr(
        "core.room_auto_assignment.find_auto_assignment_candidates",
        AsyncMock(return_value=candidates),
    )
    creator = AsyncMock(return_value={"id": "booking-1"})
    booking = {**_booking(), "preferred_room_number": "202"}

    _, room = await create_booking_with_auto_assignment(
        database=SimpleNamespace(),
        tenant_id="tenant-1",
        booking_doc=booking,
        create_booking=creator,
    )

    assert room["room_number"] == "202"
    created_doc = creator.await_args.kwargs["booking_doc"]
    assert created_doc["room_id"] == "room-202"
    assert created_doc["room_number"] == "202"
    assert "preferred_room_number" not in created_doc


@pytest.mark.asyncio
async def test_unavailable_provider_room_falls_back_to_safe_candidate(monkeypatch):
    monkeypatch.setattr(
        "core.room_auto_assignment.find_auto_assignment_candidates",
        AsyncMock(return_value=[{"id": "room-201", "room_number": "201"}]),
    )
    creator = AsyncMock(return_value={"id": "booking-1"})
    booking = {**_booking(), "preferred_room_number": "202"}

    _, room = await create_booking_with_auto_assignment(
        database=SimpleNamespace(),
        tenant_id="tenant-1",
        booking_doc=booking,
        create_booking=creator,
    )

    assert room["room_number"] == "201"


@pytest.mark.asyncio
async def test_no_available_room_keeps_reservation_pending(monkeypatch):
    monkeypatch.setattr(
        "core.room_auto_assignment.find_auto_assignment_candidates",
        AsyncMock(return_value=[]),
    )
    creator = AsyncMock(return_value={"id": "booking-1", "room_id": None})

    _, room = await create_booking_with_auto_assignment(
        database=SimpleNamespace(),
        tenant_id="tenant-1",
        booking_doc=_booking(),
        create_booking=creator,
    )

    assert room is None
    pending = creator.await_args.kwargs["booking_doc"]
    assert pending["room_id"] is None
    assert pending["allocation_source"] == "pending_assignment"
    assert pending["auto_assignment_reason"] == "no_available_room"
