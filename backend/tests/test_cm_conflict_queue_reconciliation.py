from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers import cm_conflict_queue as queue


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args):
        return self

    def limit(self, *_args):
        return self

    async def to_list(self, length):
        return self.rows[:length]


class _Bookings:
    def __init__(self, pending, authoritative):
        self.pending = pending
        self.authoritative = authoritative
        self.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=1))

    def find(self, query, *_args):
        return _Cursor([self.authoritative] if "$or" in query else [self.pending])


@pytest.mark.asyncio
async def test_reconcile_retires_exact_external_id_duplicate(monkeypatch):
    pending = {
        "id": "pending-1",
        "tenant_id": "tenant-1",
        "room_id": None,
        "status": "confirmed",
        "allocation_source": "pending_assignment",
        "external_reservation_id": "R370795907",
    }
    authoritative = {"id": "stay-1", "room_id": "room-208", "status": "checked_out"}
    bookings = _Bookings(pending, authoritative)
    fake_db = SimpleNamespace(
        bookings=bookings,
        room_night_locks=SimpleNamespace(delete_many=AsyncMock()),
    )
    audit = AsyncMock()
    monkeypatch.setattr(queue, "db", fake_db)
    monkeypatch.setattr(queue, "create_audit_log", audit)
    user = SimpleNamespace(id="user-1", name="Admin", role="admin", tenant_id="tenant-1")

    result = await queue.reconcile_legacy_duplicates(current_user=user)

    assert result == {
        "ok": True,
        "reconciled": [{"booking_id": "pending-1", "duplicate_of_booking_id": "stay-1"}],
        "count": 1,
    }
    update = bookings.update_one.await_args.args[1]["$set"]
    assert update["status"] == "cancelled"
    assert update["allocation_source"] == "legacy_duplicate_reconciled"
    assert update["duplicate_of_booking_id"] == "stay-1"
    fake_db.room_night_locks.delete_many.assert_awaited_once()
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconcile_keeps_pending_row_without_completed_match(monkeypatch):
    pending = {
        "id": "pending-1",
        "tenant_id": "tenant-1",
        "room_id": None,
        "status": "confirmed",
        "allocation_source": "pending_assignment",
        "external_reservation_id": "ONLY-PENDING",
    }
    bookings = _Bookings(pending, None)
    fake_db = SimpleNamespace(
        bookings=bookings,
        room_night_locks=SimpleNamespace(delete_many=AsyncMock()),
    )
    monkeypatch.setattr(queue, "db", fake_db)
    monkeypatch.setattr(queue, "create_audit_log", AsyncMock())
    user = SimpleNamespace(id="user-1", name="Admin", role="admin", tenant_id="tenant-1")

    result = await queue.reconcile_legacy_duplicates(current_user=user)

    assert result["count"] == 0
    bookings.update_one.assert_not_awaited()
    fake_db.room_night_locks.delete_many.assert_not_awaited()
