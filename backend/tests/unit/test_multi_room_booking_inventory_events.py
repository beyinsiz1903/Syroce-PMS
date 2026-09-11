from unittest.mock import AsyncMock, Mock, patch

import pytest

from routers.pms_bookings import _publish_multi_room_booking_created_events


@pytest.mark.asyncio
async def test_multi_room_booking_emits_durable_and_immediate_inventory_events():
    booking = {
        "id": "booking-1",
        "guest_id": "guest-1",
        "room_id": "room-106",
        "check_in": "2026-11-10T00:00:00",
        "check_out": "2026-11-12T00:00:00",
        "status": "pending",
        "channel": "direct",
    }
    enqueue = AsyncMock()
    sync = AsyncMock()
    scheduled = []

    def create_task(coro):
        scheduled.append(coro)
        coro.close()
        return Mock()

    with (
        patch("core.outbox_service.enqueue_outbox_event", new=enqueue),
        patch(
            "domains.channel_manager.availability_auto_sync.sync_availability_after_booking",
            new=sync,
        ),
        patch("routers.pms_bookings.asyncio.create_task", side_effect=create_task),
    ):
        await _publish_multi_room_booking_created_events(
            "tenant-1",
            "property-501694",
            [booking],
        )

    enqueue.assert_awaited_once()
    kwargs = enqueue.await_args.kwargs
    assert kwargs["event_type"] == "booking.created.v1"
    assert kwargs["entity_id"] == "booking-1"
    assert kwargs["property_id"] == "property-501694"
    assert kwargs["payload"] == {
        "booking_id": "booking-1",
        "guest_id": "guest-1",
        "room_id": "room-106",
        "check_in": "2026-11-10T00:00:00",
        "check_out": "2026-11-12T00:00:00",
        "status": "pending",
        "property_id": "property-501694",
        "source_channel": "direct",
        "origin": "ui",
    }
    assert len(scheduled) == 1
    sync.assert_called_once_with(
        tenant_id="tenant-1",
        room_id="room-106",
        check_in="2026-11-10T00:00:00",
        check_out="2026-11-12T00:00:00",
    )


@pytest.mark.asyncio
async def test_immediate_sync_still_runs_when_outbox_enqueue_fails():
    booking = {
        "id": "booking-1",
        "guest_id": "guest-1",
        "room_id": "room-106",
        "check_in": "2026-11-10T00:00:00",
        "check_out": "2026-11-12T00:00:00",
    }
    sync = AsyncMock()

    def create_task(coro):
        coro.close()
        return Mock()

    with (
        patch(
            "core.outbox_service.enqueue_outbox_event",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ),
        patch(
            "domains.channel_manager.availability_auto_sync.sync_availability_after_booking",
            new=sync,
        ),
        patch("routers.pms_bookings.asyncio.create_task", side_effect=create_task) as schedule,
    ):
        await _publish_multi_room_booking_created_events(
            "tenant-1",
            "property-501694",
            [booking],
        )

    schedule.assert_called_once()
    sync.assert_called_once()
