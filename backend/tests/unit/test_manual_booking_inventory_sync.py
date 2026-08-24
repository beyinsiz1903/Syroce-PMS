from unittest.mock import AsyncMock, patch

import pytest

from channel_manager.application.event_sync_service import EventSyncService
from domains.channel_manager import availability_auto_sync


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return self.rows


class _RoomsCollection:
    async def find_one(self, _query, _projection):
        return {"room_type": "standard"}

    def find(self, _query, _projection):
        return _Cursor([{"id": "r1"}, {"id": "r2"}, {"id": "r3"}])


class _BookingsCollection:
    def find(self, _query, _projection):
        return _Cursor(
            [
                {
                    "room_id": "r1",
                    "check_in": "2026-08-26T14:00:00+00:00",
                    "check_out": "2026-08-28T12:00:00+00:00",
                }
            ]
        )


@pytest.mark.asyncio
async def test_manual_booking_recalculates_room_type_inventory_without_provider_write(monkeypatch):
    """A two-night manual booking lowers that room type from three to two."""
    fake_db = type(
        "FakeDb",
        (),
        {
            "rooms": _RoomsCollection(),
            "bookings": _BookingsCollection(),
        },
    )()
    hotelrunner_push = AsyncMock()
    exely_push = AsyncMock()
    monkeypatch.setattr(availability_auto_sync, "db", fake_db)
    monkeypatch.setattr(availability_auto_sync, "_push_to_hotelrunner", hotelrunner_push)
    monkeypatch.setattr(availability_auto_sync, "_push_to_exely", exely_push)

    await availability_auto_sync._do_sync(
        "tenant-1",
        "r1",
        "2026-08-26T14:00:00+00:00",
        "2026-08-28T12:00:00+00:00",
    )

    expected = {"2026-08-26": 2, "2026-08-27": 2}
    hotelrunner_push.assert_awaited_once_with("tenant-1", "standard", expected)
    exely_push.assert_awaited_once_with("tenant-1", "standard", expected)


@pytest.mark.asyncio
async def test_durable_booking_event_routes_to_hotelrunner_inventory_job():
    """The durable booking.created outbox path creates an inventory sync job."""
    repo = AsyncMock()
    repo.get_active_connectors = AsyncMock(
        return_value=[
            {"id": "hotelrunner-connector-1", "provider": "hotelrunner"},
        ]
    )
    repo.create_audit_log = AsyncMock()
    service = EventSyncService(repo)

    with patch(
        "channel_manager.application.inventory_sync_service.InventorySyncService.trigger_inventory_sync",
        new=AsyncMock(return_value={"job_id": "inventory-job-1", "status": "succeeded"}),
    ) as trigger:
        result = await service.handle_event(
            "tenant-1",
            "booking_created",
            {
                "property_id": "tenant-1",
                "room_id": "r1",
                "check_in": "2026-08-26T14:00:00+00:00",
                "check_out": "2026-08-28T12:00:00+00:00",
                "origin": "ui",
                "source_channel": "direct",
            },
        )

    assert result["handled"] is True
    assert result["sync_jobs_created"] == 1
    trigger.assert_awaited_once()
    kwargs = trigger.await_args.kwargs
    assert kwargs["tenant_id"] == "tenant-1"
    assert kwargs["connector_id"] == "hotelrunner-connector-1"
    assert kwargs["date_start"] == "2026-08-26T14:00:00+00:00"
    assert kwargs["date_end"] == "2026-08-28T12:00:00+00:00"
    assert "booking_created" in kwargs["trigger_reason"]
