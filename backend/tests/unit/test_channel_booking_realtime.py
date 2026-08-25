from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.channel_manager.ingest import pipeline
from domains.channel_manager.providers import sync_engine


def _collection(**methods):
    defaults = {
        "find_one": AsyncMock(return_value=None),
        "update_one": AsyncMock(return_value=SimpleNamespace(matched_count=1, modified_count=1)),
        "insert_one": AsyncMock(return_value=SimpleNamespace(inserted_id="id")),
    }
    defaults.update(methods)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_webhook_cancellation_publishes_calendar_invalidation(monkeypatch):
    booking_before = {
        "id": "booking-1",
        "guest_name": "Guest",
        "check_in": "2030-01-01",
        "check_out": "2030-01-02",
        "status": "confirmed",
    }
    bookings = _collection(
        find_one=AsyncMock(side_effect=[booking_before, {"id": "booking-1"}]),
    )
    notifications = _collection(find_one=AsyncMock(return_value=None))
    fake_db = SimpleNamespace(
        bookings=bookings,
        notifications=notifications,
        imported_reservations=_collection(),
    )
    publish = AsyncMock(return_value=True)
    monkeypatch.setattr(pipeline, "db", fake_db)
    monkeypatch.setattr(pipeline, "publish_booking_change", publish)
    monkeypatch.setattr(
        "domains.channel_manager.providers.unmatched_hold.release_unmatched_reservation_hold",
        AsyncMock(return_value={"released": False}),
    )

    durable = await pipeline._propagate_cancellation_to_booking("tenant-a", "hr-1")

    assert durable is True
    publish.assert_awaited_once_with(
        tenant_id="tenant-a",
        booking_id="booking-1",
        event_type="cancel",
        status="cancelled",
        source="channel_manager_ingest",
        external_reservation_id="hr-1",
    )


@pytest.mark.asyncio
async def test_hotelrunner_pull_cancellation_publishes_calendar_invalidation(monkeypatch):
    booking = {
        "id": "booking-2",
        "guest_name": "Guest",
        "check_in": "2030-01-01",
        "check_out": "2030-01-02",
        "status": "confirmed",
        "total_amount": 100,
    }
    fake_db = SimpleNamespace(
        bookings=_collection(find_one=AsyncMock(return_value=booking)),
        imported_reservations=_collection(),
        notifications=_collection(find_one=AsyncMock(return_value=None)),
        guests=_collection(),
        room_mappings=_collection(),
    )
    publish = AsyncMock(return_value=True)
    monkeypatch.setattr(sync_engine, "db", fake_db)
    monkeypatch.setattr(sync_engine, "publish_booking_change", publish)
    monkeypatch.setattr(sync_engine, "_timeline_append", AsyncMock())

    updated = await sync_engine.sync_reservation_update(
        "tenant-a",
        "hr-2",
        {"state": "cancelled", "cancel_reason": "Guest cancelled"},
        "cancelled",
        "2030-01-01T12:00:00Z",
    )

    assert updated is True
    publish.assert_awaited_once_with(
        tenant_id="tenant-a",
        booking_id="booking-2",
        event_type="cancel",
        status="cancelled",
        source="hotelrunner_pull",
        external_reservation_id="hr-2",
    )
