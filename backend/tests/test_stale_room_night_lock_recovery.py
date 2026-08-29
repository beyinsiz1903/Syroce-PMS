"""Fail-closed inline recovery for lone stale room-night locks."""

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import DuplicateKeyError

from core import atomic_booking

pytestmark = pytest.mark.asyncio

TENANT = "tenant-stale-lock"
ROOM = "room-103"
NIGHT = "2026-08-29"
OWNER = "ghost-booking"
REQUESTED = "new-booking"


def _old_lock(**overrides):
    lock = {
        "tenant_id": TENANT,
        "room_id": ROOM,
        "night_date": NIGHT,
        "booking_id": OWNER,
        "lock_type": "booking",
        "created_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
    }
    lock.update(overrides)
    return lock


def _fake_db(*, owner=None, delete_count=1, insert_side_effect=None):
    locks = SimpleNamespace(
        insert_one=AsyncMock(side_effect=insert_side_effect),
        find_one=AsyncMock(return_value=_old_lock()),
        delete_one=AsyncMock(return_value=SimpleNamespace(deleted_count=delete_count)),
    )
    bookings = SimpleNamespace(find_one=AsyncMock(return_value=owner))
    return SimpleNamespace(room_night_locks=locks, bookings=bookings)


@pytest.fixture(autouse=True)
def _tenant_and_timeline(monkeypatch):
    monkeypatch.setattr(atomic_booking, "tenant_context", lambda _tenant: nullcontext())
    monkeypatch.setattr(atomic_booking, "_timeline_event", AsyncMock())


async def test_missing_owner_is_retired_by_exact_identity(monkeypatch):
    fake = _fake_db(owner=None)
    monkeypatch.setattr(atomic_booking, "db", fake)
    existing = _old_lock()

    recovered = await atomic_booking._retire_stale_booking_lock(
        tenant_id=TENANT,
        room_id=ROOM,
        night=NIGHT,
        existing=existing,
        requested_booking_id=REQUESTED,
        correlation_id="corr-1",
    )

    assert recovered is True
    fake.room_night_locks.delete_one.assert_awaited_once_with(
        {
            "tenant_id": TENANT,
            "room_id": ROOM,
            "night_date": NIGHT,
            "booking_id": OWNER,
            "lock_type": "booking",
            "created_at": existing["created_at"],
        }
    )
    atomic_booking._timeline_event.assert_awaited_once()


async def test_fresh_missing_owner_is_kept_for_inflight_create(monkeypatch):
    fake = _fake_db(owner=None)
    monkeypatch.setattr(atomic_booking, "db", fake)
    fresh = _old_lock(created_at=datetime.now(UTC).isoformat())

    recovered = await atomic_booking._retire_stale_booking_lock(
        tenant_id=TENANT,
        room_id=ROOM,
        night=NIGHT,
        existing=fresh,
        requested_booking_id=REQUESTED,
        correlation_id=None,
    )

    assert recovered is False
    fake.bookings.find_one.assert_not_awaited()
    fake.room_night_locks.delete_one.assert_not_awaited()


@pytest.mark.parametrize(
    "owner",
    [
        {
            "id": OWNER,
            "status": "confirmed",
            "room_id": ROOM,
            "check_in": "2026-08-29T14:00:00",
            "check_out": "2026-08-30T12:00:00",
        },
        {
            "id": OWNER,
            "status": "checked_in",
            "room_id": ROOM,
            "check_in": "2026-08-28T14:00:00",
            "check_out": "2026-08-31T12:00:00",
        },
    ],
)
async def test_valid_active_owner_is_never_retired(monkeypatch, owner):
    fake = _fake_db(owner=owner)
    monkeypatch.setattr(atomic_booking, "db", fake)

    recovered = await atomic_booking._retire_stale_booking_lock(
        tenant_id=TENANT,
        room_id=ROOM,
        night=NIGHT,
        existing=_old_lock(),
        requested_booking_id=REQUESTED,
        correlation_id=None,
    )

    assert recovered is False
    fake.room_night_locks.delete_one.assert_not_awaited()


async def test_room_mismatch_owner_is_retired(monkeypatch):
    owner = {
        "id": OWNER,
        "status": "confirmed",
        "room_id": "room-104",
        "check_in": "2026-08-29T14:00:00",
        "check_out": "2026-08-30T12:00:00",
    }
    fake = _fake_db(owner=owner)
    monkeypatch.setattr(atomic_booking, "db", fake)

    recovered = await atomic_booking._retire_stale_booking_lock(
        tenant_id=TENANT,
        room_id=ROOM,
        night=NIGHT,
        existing=_old_lock(),
        requested_booking_id=REQUESTED,
        correlation_id=None,
    )

    assert recovered is True


async def test_inventory_block_is_never_retired(monkeypatch):
    fake = _fake_db(owner=None)
    monkeypatch.setattr(atomic_booking, "db", fake)

    recovered = await atomic_booking._retire_stale_booking_lock(
        tenant_id=TENANT,
        room_id=ROOM,
        night=NIGHT,
        existing=_old_lock(booking_id="OOO:room-103", lock_type="ooo"),
        requested_booking_id=REQUESTED,
        correlation_id=None,
    )

    assert recovered is False
    fake.bookings.find_one.assert_not_awaited()
    fake.room_night_locks.delete_one.assert_not_awaited()


async def test_claim_retries_once_after_stale_owner_recovery(monkeypatch):
    fake = _fake_db(
        owner=None,
        insert_side_effect=[DuplicateKeyError("duplicate"), None],
    )
    monkeypatch.setattr(atomic_booking, "db", fake)
    lock_doc = _old_lock(booking_id=REQUESTED, created_at=datetime.now(UTC).isoformat())

    claimed, existing = await atomic_booking._claim_night_or_get_owner(
        lock_doc,
        correlation_id="corr-2",
    )

    assert claimed is True
    assert existing is None
    assert fake.room_night_locks.insert_one.await_count == 2
    fake.room_night_locks.delete_one.assert_awaited_once()


async def test_assignment_releases_old_room_and_old_same_room_nights(monkeypatch):
    locks = SimpleNamespace(delete_many=AsyncMock())
    fake = SimpleNamespace(room_night_locks=locks)
    monkeypatch.setattr(atomic_booking, "db", fake)
    monkeypatch.setattr(atomic_booking, "_find_overlapping_active_booking", AsyncMock(return_value=None))
    monkeypatch.setattr(atomic_booking, "_claim_night_or_get_owner", AsyncMock(return_value=(True, None)))

    await atomic_booking.assign_room_atomic(
        tenant_id=TENANT,
        booking_id=REQUESTED,
        room_id=ROOM,
        check_in="2026-08-29T14:00:00",
        check_out="2026-08-31T12:00:00",
    )

    locks.delete_many.assert_awaited_once_with(
        {
            "tenant_id": TENANT,
            "booking_id": REQUESTED,
            "$or": [
                {"room_id": {"$ne": ROOM}},
                {"room_id": ROOM, "night_date": {"$nin": ["2026-08-29", "2026-08-30"]}},
            ],
        }
    )
