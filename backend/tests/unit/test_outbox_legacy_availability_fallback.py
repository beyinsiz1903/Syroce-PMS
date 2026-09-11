from unittest.mock import AsyncMock, patch

import pytest

from core.outbox_dispatcher import dispatch_outbox_event


def _booking_event() -> dict:
    return {
        "id": "event-1",
        "tenant_id": "tenant-1",
        "property_id": "tenant-1",
        "event_type": "booking.created.v1",
        "payload": {
            "room_id": "room-101",
            "check_in": "2026-11-10",
            "check_out": "2026-11-12",
            "property_id": "tenant-1",
        },
    }


@pytest.mark.asyncio
async def test_booking_event_falls_back_to_legacy_provider_connections():
    cm_result = {
        "handled": True,
        "sync_jobs_created": 0,
        "reason": "No active connectors",
        "jobs": [],
    }
    legacy_result = {
        "configured_providers": 1,
        "queued_operations": 1,
        "errors": [],
    }

    with (
        patch(
            "channel_manager.application.event_sync_service.EventSyncService.handle_event",
            new=AsyncMock(return_value=cm_result),
        ),
        patch(
            "domains.channel_manager.availability_auto_sync.sync_availability_from_durable_event",
            new=AsyncMock(return_value=legacy_result),
        ) as legacy_sync,
        patch("core.agency_fanout.fan_out_agency_events", new=AsyncMock()),
    ):
        success, message = await dispatch_outbox_event(_booking_event())

    assert success is True
    assert message == "Dispatched: 1 legacy availability operations queued"
    legacy_sync.assert_awaited_once_with(
        tenant_id="tenant-1",
        room_id="room-101",
        check_in="2026-11-10",
        check_out="2026-11-12",
    )


@pytest.mark.asyncio
async def test_booking_event_retries_when_legacy_provider_accepts_no_work():
    cm_result = {
        "handled": True,
        "sync_jobs_created": 0,
        "reason": "No active connectors",
        "jobs": [],
    }
    legacy_result = {
        "configured_providers": 1,
        "queued_operations": 0,
        "errors": ["exely_room_mapping_missing"],
    }

    with (
        patch(
            "channel_manager.application.event_sync_service.EventSyncService.handle_event",
            new=AsyncMock(return_value=cm_result),
        ),
        patch(
            "domains.channel_manager.availability_auto_sync.sync_availability_from_durable_event",
            new=AsyncMock(return_value=legacy_result),
        ),
        patch("core.agency_fanout.fan_out_agency_events", new=AsyncMock()),
    ):
        success, message = await dispatch_outbox_event(_booking_event())

    assert success is False
    assert message.startswith("retryable: legacy channel availability sync failed")
    assert "exely_room_mapping_missing" in message


@pytest.mark.asyncio
async def test_booking_event_does_not_replay_successful_provider_for_other_provider_error():
    cm_result = {"handled": True, "sync_jobs_created": 0, "reason": "No active connectors", "jobs": []}
    legacy_result = {
        "configured_providers": 2,
        "queued_operations": 1,
        "errors": ["hotelrunner_room_mapping_missing"],
    }

    with (
        patch("channel_manager.application.event_sync_service.EventSyncService.handle_event", new=AsyncMock(return_value=cm_result)),
        patch("domains.channel_manager.availability_auto_sync.sync_availability_from_durable_event", new=AsyncMock(return_value=legacy_result)),
        patch("core.agency_fanout.fan_out_agency_events", new=AsyncMock()),
    ):
        success, message = await dispatch_outbox_event(_booking_event())

    assert success is True
    assert message.startswith("Dispatched: 1 legacy availability operations queued; partial:")


@pytest.mark.asyncio
async def test_booking_event_without_any_provider_remains_a_noop_success():
    cm_result = {
        "handled": True,
        "sync_jobs_created": 0,
        "reason": "No active connectors",
        "jobs": [],
    }
    legacy_result = {
        "configured_providers": 0,
        "queued_operations": 0,
        "errors": [],
    }

    with (
        patch(
            "channel_manager.application.event_sync_service.EventSyncService.handle_event",
            new=AsyncMock(return_value=cm_result),
        ),
        patch(
            "domains.channel_manager.availability_auto_sync.sync_availability_from_durable_event",
            new=AsyncMock(return_value=legacy_result),
        ),
        patch("core.agency_fanout.fan_out_agency_events", new=AsyncMock()),
    ):
        success, message = await dispatch_outbox_event(_booking_event())

    assert success is True
    assert message == "Dispatched: 0 sync jobs created"
