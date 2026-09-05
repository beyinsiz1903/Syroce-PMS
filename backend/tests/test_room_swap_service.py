"""Regression coverage for the atomic reservation room-swap path."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.reservations.services import room_swap_service as room_swap_module


TENANT = "tenant-room-swap"


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return self.rows


def _booking(booking_id, room_id, guest_name):
    return {
        "id": booking_id,
        "tenant_id": TENANT,
        "status": "confirmed",
        "room_id": room_id,
        "guest_name": guest_name,
        "check_in": "2026-09-05T14:00:00+03:00",
        "check_out": "2026-09-07T12:00:00+03:00",
        "_version": 4,
    }


@pytest.mark.asyncio
async def test_swap_replaces_both_room_assignments_and_locks_together(monkeypatch):
    source = _booking("booking-101", "room-101", "Ali")
    target = _booking("booking-102", "room-102", "Ayse")

    async def find_booking(query, *args, **kwargs):
        if query.get("id") == "booking-101":
            return source
        if query.get("id") == "booking-102":
            return target
        return None  # no third-party booking conflict

    bookings = SimpleNamespace(
        find_one=AsyncMock(side_effect=find_booking),
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
    )
    rooms = SimpleNamespace(
        find=lambda *args, **kwargs: _Cursor([
            {"id": "room-101", "room_number": "101"},
            {"id": "room-102", "room_number": "102"},
        ]),
    )
    locks = SimpleNamespace(
        find=lambda *args, **kwargs: _Cursor([]),
        delete_many=AsyncMock(),
        insert_many=AsyncMock(),
    )
    history = SimpleNamespace(insert_many=AsyncMock())
    fake_db = SimpleNamespace(
        bookings=bookings,
        rooms=rooms,
        room_night_locks=locks,
        room_move_history=history,
    )
    monkeypatch.setattr(room_swap_module, "db", fake_db)
    monkeypatch.setenv("MONGO_DISABLE_TRANSACTIONS", "1")

    result = await room_swap_module.room_swap_service.swap(
        tenant_id=TENANT,
        booking_id="booking-101",
        target_booking_id="booking-102",
        reason="Misafir talebi",
        moved_by="Operatör",
    )

    assert result["source_room"] == "102"
    assert result["target_room"] == "101"
    locks.delete_many.assert_awaited_once_with(
        {"tenant_id": TENANT, "booking_id": {"$in": ["booking-101", "booking-102"]}},
        session=None,
    )
    inserted = locks.insert_many.await_args.args[0]
    assert {(row["room_id"], row["booking_id"]) for row in inserted} == {
        ("room-102", "booking-101"),
        ("room-101", "booking-102"),
    }
    assert bookings.update_one.await_count == 2
    history.insert_many.assert_awaited_once()


@pytest.mark.asyncio
async def test_swap_rejects_a_third_party_target_lock(monkeypatch):
    source = _booking("booking-101", "room-101", "Ali")
    target = _booking("booking-102", "room-102", "Ayse")

    async def find_booking(query, *args, **kwargs):
        if query.get("id") == "booking-101":
            return source
        if query.get("id") == "booking-102":
            return target
        return None

    fake_db = SimpleNamespace(
        bookings=SimpleNamespace(find_one=AsyncMock(side_effect=find_booking), update_one=AsyncMock()),
        rooms=SimpleNamespace(find=lambda *args, **kwargs: _Cursor([
            {"id": "room-101", "room_number": "101"},
            {"id": "room-102", "room_number": "102"},
        ])),
        room_night_locks=SimpleNamespace(
            find=lambda *args, **kwargs: _Cursor([
                {"room_id": "room-102", "night_date": "2026-09-05", "booking_id": "booking-999"},
            ]),
            delete_many=AsyncMock(),
            insert_many=AsyncMock(),
        ),
        room_move_history=SimpleNamespace(insert_many=AsyncMock()),
    )
    monkeypatch.setattr(room_swap_module, "db", fake_db)
    monkeypatch.setenv("MONGO_DISABLE_TRANSACTIONS", "1")

    with pytest.raises(room_swap_module.RoomSwapError) as exc:
        await room_swap_module.room_swap_service.swap(
            tenant_id=TENANT,
            booking_id="booking-101",
            target_booking_id="booking-102",
            reason="Misafir talebi",
            moved_by="Operatör",
        )

    assert exc.value.code == "TARGET_LOCK_CONFLICT"
    fake_db.room_night_locks.delete_many.assert_not_awaited()
