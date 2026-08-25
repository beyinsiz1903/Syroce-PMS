from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.pms_core import reservation_state_machine as state_module


@pytest.fixture
def machine():
    return state_module.ReservationStateMachine()


def _collection(**overrides):
    defaults = {
        "find_one": AsyncMock(return_value=None),
        "update_one": AsyncMock(),
        "update_many": AsyncMock(),
        "insert_one": AsyncMock(),
        "count_documents": AsyncMock(return_value=0),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _db(**overrides):
    defaults = {
        "bookings": _collection(),
        "rooms": _collection(),
        "exely_room_mappings": _collection(),
        "rate_calendar": _collection(),
        "guests": _collection(),
        "notifications": _collection(),
        "pms_audit_trail": _collection(),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_overbooking_excludes_booking_being_modified(machine, monkeypatch):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[])
    bookings = _collection()
    bookings.find = MagicMock(return_value=cursor)
    fake_db = _db(bookings=bookings)
    monkeypatch.setattr(state_module, "db", fake_db)

    has_conflict, conflicts = await machine.check_overbooking(
        "tenant-1",
        "room-1",
        "2026-09-01",
        "2026-09-03",
        exclude_booking_id="booking-1",
    )

    assert has_conflict is False
    assert conflicts == []
    query = bookings.find.call_args.args[0]
    assert query["id"] == {"$ne": "booking-1"}


@pytest.mark.parametrize("status", sorted(state_module.NON_CANCELLABLE_STATES))
@pytest.mark.asyncio
async def test_cancellation_rejects_terminal_or_occupied_states(machine, monkeypatch, status):
    fake_db = _db()
    monkeypatch.setattr(state_module, "db", fake_db)

    result = await machine.handle_cancellation(
        "tenant-1", {"id": "booking-1", "status": status}, "user-1"
    )

    assert result == {
        "success": False,
        "error": f"Cannot cancel reservation in '{status}' state",
    }
    fake_db.bookings.update_one.assert_not_awaited()
    fake_db.pms_audit_trail.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_releases_inventory_notifies_audits_and_enqueues(machine, monkeypatch):
    rooms = _collection(
        find_one=AsyncMock(
            side_effect=[
                {"status": "clean"},
                {"room_type": "Deluxe"},
                {"room_number": "204"},
            ]
        )
    )
    mappings = _collection(find_one=AsyncMock(return_value={"exely_room_code": "DLX"}))
    guests = _collection(find_one=AsyncMock(return_value={"name": "Ada Lovelace"}))
    fake_db = _db(rooms=rooms, exely_room_mappings=mappings, guests=guests)
    monkeypatch.setattr(state_module, "db", fake_db)
    booking = {
        "id": "booking-1",
        "status": "confirmed",
        "guest_id": "guest-1",
        "room_id": "room-1",
        "check_in": "2026-09-01T14:00:00Z",
        "check_out": "2026-09-03T12:00:00Z",
        "correlation_id": "corr-1",
    }

    with (
        patch("core.atomic_booking.release_booking_nights", new=AsyncMock()) as release,
        patch("core.outbox_service.enqueue_outbox_event", new=AsyncMock()) as enqueue,
    ):
        result = await machine.handle_cancellation(
            "tenant-1", booking, "user-1", "Guest request"
        )

    assert result == {
        "success": True,
        "booking_id": "booking-1",
        "previous_status": "confirmed",
    }
    fake_db.bookings.update_one.assert_awaited_once()
    assert fake_db.bookings.update_one.await_args.args[1]["$set"]["status"] == "cancelled"
    release.assert_awaited_once_with(
        "tenant-1",
        "booking-1",
        reason="cancelled:Guest request",
        correlation_id="corr-1",
    )
    fake_db.rate_calendar.update_many.assert_awaited_once()
    availability_query = fake_db.rate_calendar.update_many.await_args.args[0]
    assert availability_query["room_type_code"] == "DLX"
    assert availability_query["date"] == {"$gte": "2026-09-01", "$lt": "2026-09-03"}
    notification = fake_db.notifications.insert_one.await_args.args[0]
    assert notification["title"].endswith("Oda 204")
    assert "Ada Lovelace" in notification["message"]
    fake_db.pms_audit_trail.insert_one.assert_awaited_once()
    enqueue.assert_awaited_once()
    assert enqueue.await_args.kwargs["payload"]["cancellation_reason"] == "Guest request"


@pytest.mark.asyncio
async def test_cancellation_survives_noncritical_side_effect_failures(machine, monkeypatch):
    rooms = _collection(
        find_one=AsyncMock(side_effect=[{"status": "clean"}, RuntimeError("calendar unavailable")])
    )
    guests = _collection(find_one=AsyncMock(side_effect=RuntimeError("guest lookup failed")))
    fake_db = _db(rooms=rooms, guests=guests)
    monkeypatch.setattr(state_module, "db", fake_db)
    booking = {
        "id": "booking-1",
        "status": "pending",
        "guest_id": "guest-1",
        "room_id": "room-1",
        "check_in": "2026-09-01",
        "check_out": "2026-09-03",
    }

    with (
        patch(
            "core.atomic_booking.release_booking_nights",
            new=AsyncMock(side_effect=RuntimeError("lock service unavailable")),
        ),
        patch(
            "core.outbox_service.enqueue_outbox_event",
            new=AsyncMock(side_effect=RuntimeError("outbox unavailable")),
        ),
    ):
        result = await machine.handle_cancellation("tenant-1", booking, "user-1")

    assert result["success"] is True
    fake_db.bookings.update_one.assert_awaited_once()
    fake_db.pms_audit_trail.insert_one.assert_awaited_once()


@pytest.mark.parametrize("status", sorted(state_module.NON_NOSHOWABLE_STATES))
@pytest.mark.asyncio
async def test_no_show_rejects_terminal_or_occupied_states(machine, monkeypatch, status):
    fake_db = _db()
    monkeypatch.setattr(state_module, "db", fake_db)

    result = await machine.handle_no_show(
        "tenant-1", {"id": "booking-1", "status": status}, "user-1"
    )

    assert result["success"] is False
    assert status in result["error"]
    fake_db.bookings.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_show_rejects_invalid_pending_transition(machine, monkeypatch):
    fake_db = _db()
    monkeypatch.setattr(state_module, "db", fake_db)

    result = await machine.handle_no_show(
        "tenant-1", {"id": "booking-1", "status": "pending"}, "user-1"
    )

    assert result["success"] is False
    assert "not allowed" in result["error"]
    fake_db.bookings.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_show_updates_releases_audits_and_enqueues(machine, monkeypatch):
    fake_db = _db()
    monkeypatch.setattr(state_module, "db", fake_db)
    booking = {
        "id": "booking-1",
        "status": "guaranteed",
        "guest_id": "guest-1",
        "room_id": "room-1",
        "check_in": "2026-09-01",
        "check_out": "2026-09-03",
        "correlation_id": "corr-1",
    }

    with (
        patch("core.atomic_booking.release_booking_nights", new=AsyncMock()) as release,
        patch("core.outbox_service.enqueue_outbox_event", new=AsyncMock()) as enqueue,
    ):
        result = await machine.handle_no_show("tenant-1", booking, "user-1")

    assert result == {"success": True, "booking_id": "booking-1"}
    assert fake_db.bookings.update_one.await_args.args[1]["$set"]["status"] == "no_show"
    release.assert_awaited_once_with(
        "tenant-1",
        "booking-1",
        reason="no_show:user-1",
        correlation_id="corr-1",
    )
    audit = fake_db.pms_audit_trail.insert_one.await_args.args[0]
    assert audit["previous_status"] == "guaranteed"
    assert audit["new_status"] == "no_show"
    enqueue.assert_awaited_once()
    assert enqueue.await_args.kwargs["payload"]["inventory_released"] is True


@pytest.mark.asyncio
async def test_no_show_survives_lock_and_outbox_failures(machine, monkeypatch):
    fake_db = _db()
    monkeypatch.setattr(state_module, "db", fake_db)

    with (
        patch(
            "core.atomic_booking.release_booking_nights",
            new=AsyncMock(side_effect=RuntimeError("lock service unavailable")),
        ),
        patch(
            "core.outbox_service.enqueue_outbox_event",
            new=AsyncMock(side_effect=RuntimeError("outbox unavailable")),
        ),
    ):
        result = await machine.handle_no_show(
            "tenant-1", {"id": "booking-1", "status": "confirmed"}, "user-1"
        )

    assert result["success"] is True
    fake_db.pms_audit_trail.insert_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_recalculate_marks_vacated_occupied_room_dirty(machine, monkeypatch):
    bookings = _collection(count_documents=AsyncMock(return_value=0))
    rooms = _collection(find_one=AsyncMock(return_value={"status": "occupied"}))
    fake_db = _db(bookings=bookings, rooms=rooms)
    monkeypatch.setattr(state_module, "db", fake_db)

    await machine.recalculate_availability_after_modification(
        "tenant-1", "room-old", "room-new", "booking-1"
    )

    rooms.update_one.assert_awaited_once_with(
        {"id": "room-old", "tenant_id": "tenant-1"},
        {"$set": {"status": "dirty", "current_booking_id": None}},
    )


@pytest.mark.parametrize(
    ("old_room_id", "new_room_id", "active_count", "room", "expected_count_calls"),
    [
        ("room-1", "room-1", 0, {"status": "occupied"}, 0),
        ("room-old", "room-new", 1, {"status": "occupied"}, 1),
        ("room-old", "room-new", 0, {"status": "clean"}, 1),
    ],
)
@pytest.mark.asyncio
async def test_recalculate_preserves_room_when_cleanup_is_not_needed(
    machine,
    monkeypatch,
    old_room_id,
    new_room_id,
    active_count,
    room,
    expected_count_calls,
):
    bookings = _collection(count_documents=AsyncMock(return_value=active_count))
    rooms = _collection(find_one=AsyncMock(return_value=room))
    fake_db = _db(bookings=bookings, rooms=rooms)
    monkeypatch.setattr(state_module, "db", fake_db)

    await machine.recalculate_availability_after_modification(
        "tenant-1", old_room_id, new_room_id, "booking-1"
    )

    assert bookings.count_documents.await_count == expected_count_calls
    rooms.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_audit_trail_uses_newest_first_order(machine, monkeypatch):
    expected = [{"action": "no_show"}, {"action": "creation"}]
    cursor = MagicMock()
    sorted_cursor = MagicMock()
    sorted_cursor.to_list = AsyncMock(return_value=expected)
    cursor.sort = MagicMock(return_value=sorted_cursor)
    audit = _collection()
    audit.find = MagicMock(return_value=cursor)
    fake_db = _db(pms_audit_trail=audit)
    monkeypatch.setattr(state_module, "db", fake_db)

    result = await machine.get_audit_trail("tenant-1", "booking-1")

    assert result == expected
    cursor.sort.assert_called_once_with("timestamp", -1)
    sorted_cursor.to_list.assert_awaited_once_with(100)
