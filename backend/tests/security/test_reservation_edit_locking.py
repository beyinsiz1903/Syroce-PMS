"""Regression coverage for reservation-detail pessimistic edit locking."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import DuplicateKeyError

import core.reservation_edit_lock as locking


class _FakeDB:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == locking.LOCK_COLLECTION
        return self.collection


def _lease_doc(*, now, owner="user-a", lock_id="lock-a"):
    return {
        "tenant_id": "tenant-a",
        "booking_id": "booking-a",
        "owner_user_id": owner,
        "lock_id": lock_id,
        "acquired_at": now,
        "heartbeat_at": now,
        "expires_at": now + timedelta(seconds=locking.LEASE_SECONDS),
    }


def test_lock_timing_contract_is_120_second_lease_and_30_second_heartbeat():
    assert locking.LEASE_SECONDS == 120
    assert locking.HEARTBEAT_SECONDS == 30


@pytest.mark.asyncio
async def test_acquire_is_atomic_expired_or_exact_same_view_upsert(monkeypatch):
    now = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    collection = SimpleNamespace(
        find_one_and_update=AsyncMock(return_value=_lease_doc(now=now)),
    )
    db = _FakeDB(collection)
    monkeypatch.setattr(locking, "ensure_reservation_edit_lock_indexes", AsyncMock())

    lease = await locking.acquire_reservation_edit_lock(
        db,
        tenant_id="tenant-a",
        booking_id="booking-a",
        owner_user_id="user-a",
        lock_id="lock-a",
        now=now,
    )

    assert lease.lock_id == "lock-a"
    assert lease.expires_at == now + timedelta(seconds=120)

    call = collection.find_one_and_update.await_args
    query = call.args[0]
    update = call.args[1]
    assert query["tenant_id"] == "tenant-a"
    assert query["booking_id"] == "booking-a"
    assert {"expires_at": {"$lte": now}} in query["$or"]
    assert {"owner_user_id": "user-a", "lock_id": "lock-a"} in query["$or"]
    assert call.kwargs["upsert"] is True
    assert update["$set"]["acquired_at"] == now
    assert update["$set"]["heartbeat_at"] == now
    assert update["$set"]["expires_at"] == now + timedelta(seconds=120)


@pytest.mark.asyncio
async def test_competing_acquire_duplicate_key_becomes_lock_conflict(monkeypatch):
    collection = SimpleNamespace(
        find_one_and_update=AsyncMock(side_effect=DuplicateKeyError("duplicate")),
    )
    db = _FakeDB(collection)
    monkeypatch.setattr(locking, "ensure_reservation_edit_lock_indexes", AsyncMock())

    with pytest.raises(locking.ReservationEditLockConflict, match="another active view"):
        await locking.acquire_reservation_edit_lock(
            db,
            tenant_id="tenant-a",
            booking_id="booking-a",
            owner_user_id="user-b",
            lock_id="lock-b",
        )


@pytest.mark.asyncio
async def test_renew_requires_exact_owner_view_and_unexpired_lease(monkeypatch):
    now = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    collection = SimpleNamespace(
        find_one_and_update=AsyncMock(return_value=_lease_doc(now=now)),
    )
    db = _FakeDB(collection)
    monkeypatch.setattr(locking, "ensure_reservation_edit_lock_indexes", AsyncMock())

    await locking.renew_reservation_edit_lock(
        db,
        tenant_id="tenant-a",
        booking_id="booking-a",
        owner_user_id="user-a",
        lock_id="lock-a",
        now=now,
    )

    query = collection.find_one_and_update.await_args.args[0]
    assert query == {
        "tenant_id": "tenant-a",
        "booking_id": "booking-a",
        "owner_user_id": "user-a",
        "lock_id": "lock-a",
        "expires_at": {"$gt": now},
    }


@pytest.mark.asyncio
async def test_renew_fails_closed_after_expiry_or_ownership_change(monkeypatch):
    collection = SimpleNamespace(find_one_and_update=AsyncMock(return_value=None))
    db = _FakeDB(collection)
    monkeypatch.setattr(locking, "ensure_reservation_edit_lock_indexes", AsyncMock())

    with pytest.raises(locking.ReservationEditLockLost):
        await locking.renew_reservation_edit_lock(
            db,
            tenant_id="tenant-a",
            booking_id="booking-a",
            owner_user_id="user-a",
            lock_id="lock-a",
        )


@pytest.mark.asyncio
async def test_assert_active_lock_requires_exact_owner_and_view():
    now = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    collection = SimpleNamespace(find_one=AsyncMock(return_value=_lease_doc(now=now)))
    db = _FakeDB(collection)

    await locking.assert_reservation_edit_lock(
        db,
        tenant_id="tenant-a",
        booking_id="booking-a",
        owner_user_id="user-a",
        lock_id="lock-a",
        now=now,
    )

    query = collection.find_one.await_args.args[0]
    assert query["owner_user_id"] == "user-a"
    assert query["lock_id"] == "lock-a"
    assert query["expires_at"] == {"$gt": now}


@pytest.mark.asyncio
async def test_owner_only_unlock_rejects_different_view():
    collection = SimpleNamespace(
        find_one=AsyncMock(
            return_value={"owner_user_id": "user-a", "lock_id": "lock-a"}
        ),
        delete_one=AsyncMock(),
    )
    db = _FakeDB(collection)

    with pytest.raises(locking.ReservationEditLockConflict, match="only the current"):
        await locking.release_reservation_edit_lock(
            db,
            tenant_id="tenant-a",
            booking_id="booking-a",
            owner_user_id="user-a",
            lock_id="different-view",
        )

    collection.delete_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_unlock_deletes_exact_lease():
    collection = SimpleNamespace(
        find_one=AsyncMock(
            return_value={"owner_user_id": "user-a", "lock_id": "lock-a"}
        ),
        delete_one=AsyncMock(return_value=SimpleNamespace(deleted_count=1)),
    )
    db = _FakeDB(collection)

    released = await locking.release_reservation_edit_lock(
        db,
        tenant_id="tenant-a",
        booking_id="booking-a",
        owner_user_id="user-a",
        lock_id="lock-a",
    )

    assert released is True
    assert collection.delete_one.await_args.args[0] == {
        "tenant_id": "tenant-a",
        "booking_id": "booking-a",
        "owner_user_id": "user-a",
        "lock_id": "lock-a",
    }


def test_backend_mutation_path_classifier_protects_reservation_detail_and_frontdesk(monkeypatch):
    # Delay this import until after the lock-service tests so JWT/security module
    # setup remains isolated from the pure locking contract above.
    import os

    os.environ.setdefault("JWT_SECRET", "test-reservation-edit-lock-secret-0123456789abcdef")
    from middleware.reservation_edit_lock_guard import reservation_id_for_mutation

    assert reservation_id_for_mutation(
        "/api/pms/reservations/booking-a/notes", "POST"
    ) == "booking-a"
    assert reservation_id_for_mutation(
        "/frontdesk/checkin/booking-a", "POST"
    ) == "booking-a"
    assert reservation_id_for_mutation(
        "/api/frontdesk/checkout/booking-a", "POST"
    ) == "booking-a"

    # Reads and lock-management calls must stay outside mutation enforcement.
    assert reservation_id_for_mutation(
        "/api/pms/reservations/booking-a/full-detail", "GET"
    ) is None
    assert reservation_id_for_mutation(
        "/api/pms/reservations/booking-a/edit-lock/acquire", "POST"
    ) is None
    assert reservation_id_for_mutation(
        "/api/pms/reservations/booking-a/transfer-to-cari", "POST"
    ) is None
