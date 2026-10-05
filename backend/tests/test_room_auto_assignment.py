from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.atomic_booking import BookingConflictError
from core.room_auto_assignment import (
    assign_pending_booking_with_auto_assignment,
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

    async def update_one(self, query, update):
        self.calls.append((query, update))
        return SimpleNamespace(matched_count=1, modified_count=1)

    async def find_one(self, query, projection=None):
        del projection
        return next(
            (
                doc
                for doc in self._docs
                if all(doc.get(key) == value for key, value in query.items() if not key.startswith("$"))
            ),
            None,
        )


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


@pytest.mark.asyncio
async def test_pending_booking_is_reassigned_after_legacy_hold_release(monkeypatch):
    candidates = [
        {"id": "room-201", "room_number": "201"},
        {"id": "room-208", "room_number": "208"},
    ]
    monkeypatch.setattr(
        "core.room_auto_assignment.find_auto_assignment_candidates",
        AsyncMock(return_value=candidates),
    )
    assign = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("core.room_auto_assignment.assign_room_atomic", assign)
    database = _database()
    booking = {
        **_booking(),
        "room_id": None,
        "preferred_room_number": "208",
        "allocation_source": "pending_assignment",
        "auto_assignment_reason": "no_available_room",
    }

    updated, room = await assign_pending_booking_with_auto_assignment(
        database=database,
        tenant_id="tenant-1",
        booking_doc=booking,
    )

    assert room == {"id": "room-208", "room_number": "208"}
    assert updated["room_id"] == "room-208"
    assert updated["room_number"] == "208"
    assert updated["allocation_source"] == "ota_auto_assignment_after_hold_release"
    assert "auto_assignment_reason" not in updated
    assert assign.await_args.kwargs["room_id"] == "room-208"
    claim_query, claim_update = database.bookings.calls[0]
    claim_id = claim_update["$set"]["auto_assignment_claim_id"]
    assert claim_query["room_id"] is None
    assert "$or" in claim_query
    query, update = database.bookings.calls[-1]
    assert query == {
        "tenant_id": "tenant-1",
        "id": "booking-1",
        "room_id": None,
        "auto_assignment_claim_id": claim_id,
    }
    assert update["$set"]["room_id"] == "room-208"
    assert update["$unset"] == {
        "auto_assignment_reason": "",
        "auto_assignment_claim_id": "",
        "auto_assignment_claimed_at": "",
    }


@pytest.mark.asyncio
async def test_pending_assignment_stops_when_another_worker_owns_claim(monkeypatch):
    database = _database()
    database.bookings.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=0, modified_count=0))
    find_candidates = AsyncMock()
    assign = AsyncMock()
    monkeypatch.setattr("core.room_auto_assignment.find_auto_assignment_candidates", find_candidates)
    monkeypatch.setattr("core.room_auto_assignment.assign_room_atomic", assign)
    booking = {**_booking(), "room_id": None}

    updated, room = await assign_pending_booking_with_auto_assignment(
        database=database,
        tenant_id="tenant-1",
        booking_doc=booking,
    )

    assert updated == booking
    assert room is None
    find_candidates.assert_not_awaited()
    assign.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_assignment_lost_cas_releases_only_attempted_room(monkeypatch):
    candidate = {"id": "room-208", "room_number": "208"}
    monkeypatch.setattr(
        "core.room_auto_assignment.find_auto_assignment_candidates",
        AsyncMock(return_value=[candidate]),
    )
    monkeypatch.setattr("core.room_auto_assignment.assign_room_atomic", AsyncMock(return_value={"success": True}))
    release = AsyncMock()
    monkeypatch.setattr("core.room_auto_assignment.release_booking_room_nights", release)
    database = _database()
    database.bookings.update_one = AsyncMock(
        side_effect=[
            SimpleNamespace(matched_count=1, modified_count=1),
            SimpleNamespace(matched_count=0, modified_count=0),
            SimpleNamespace(matched_count=1, modified_count=1),
        ]
    )
    database.bookings.find_one = AsyncMock(return_value={**_booking(), "room_id": "room-999"})

    updated, room = await assign_pending_booking_with_auto_assignment(
        database=database,
        tenant_id="tenant-1",
        booking_doc={**_booking(), "room_id": None},
    )

    assert updated["room_id"] is None
    assert room is None
    release.assert_awaited_once_with(
        "tenant-1",
        "booking-1",
        "room-208",
        "2026-08-22",
        "2026-08-24",
        reason="pending_booking_assignment_lost",
    )


@pytest.mark.asyncio
async def test_pending_assignment_ambiguous_cas_keeps_winning_locks(monkeypatch):
    candidate = {"id": "room-208", "room_number": "208"}
    monkeypatch.setattr(
        "core.room_auto_assignment.find_auto_assignment_candidates",
        AsyncMock(return_value=[candidate]),
    )
    monkeypatch.setattr("core.room_auto_assignment.assign_room_atomic", AsyncMock(return_value={"success": True}))
    release = AsyncMock()
    monkeypatch.setattr("core.room_auto_assignment.release_booking_room_nights", release)
    database = _database()
    database.bookings.update_one = AsyncMock(
        side_effect=[
            SimpleNamespace(matched_count=1, modified_count=1),
            SimpleNamespace(matched_count=0, modified_count=0),
        ]
    )
    database.bookings.find_one = AsyncMock(
        return_value={**_booking(), "room_id": "room-208", "room_number": "208"}
    )

    updated, room = await assign_pending_booking_with_auto_assignment(
        database=database,
        tenant_id="tenant-1",
        booking_doc={**_booking(), "room_id": None},
    )

    assert updated["room_id"] == "room-208"
    assert room == candidate
    release.assert_not_awaited()
