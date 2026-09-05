from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from channel_manager.application.event_sync_service import EventSyncService
from domains.channel_manager import availability_auto_sync


class _RoomsCollection:
    async def find_one(self, _query, _projection):
        return {"room_type": "standard"}


@pytest.mark.asyncio
async def test_authoritative_availability_reconciles_then_reads_each_stay_night(monkeypatch):
    reconcile = AsyncMock(return_value={"drift_detected": 0})
    inventory = AsyncMock(
        side_effect=[
            [{"room_type": "standard", "sellable": 0}],
            [{"room_type": "standard", "sellable": 0}],
        ]
    )
    monkeypatch.setattr(availability_auto_sync, "reconcile_date_range", reconcile)
    monkeypatch.setattr(availability_auto_sync, "get_room_type_inventory", inventory)

    result = await availability_auto_sync._load_authoritative_availability(
        "tenant-1", "standard", date(2026, 8, 26), date(2026, 8, 28)
    )

    assert result == {"2026-08-26": 0, "2026-08-27": 0}
    reconcile.assert_awaited_once_with("tenant-1", "2026-08-26", "2026-08-27")
    assert inventory.await_args_list == [
        (("tenant-1", "2026-08-26", "standard"),),
        (("tenant-1", "2026-08-27", "standard"),),
    ]


@pytest.mark.asyncio
async def test_manual_booking_uses_canonical_room_night_inventory(monkeypatch):
    """A calendar-full room type must push zero, never a raw booking recount."""
    fake_db = type(
        "FakeDb",
        (),
        {
            "rooms": _RoomsCollection(),
        },
    )()
    hotelrunner_push = AsyncMock()
    exely_push = AsyncMock()
    authoritative_inventory = AsyncMock(
        return_value={"2026-08-26": 0, "2026-08-27": 0}
    )
    monkeypatch.setattr(availability_auto_sync, "db", fake_db)
    monkeypatch.setattr(availability_auto_sync, "_push_to_hotelrunner", hotelrunner_push)
    monkeypatch.setattr(availability_auto_sync, "_push_to_exely", exely_push)
    monkeypatch.setattr(availability_auto_sync, "_load_authoritative_availability", authoritative_inventory)

    await availability_auto_sync._do_sync(
        "tenant-1",
        "r1",
        "2026-08-26T14:00:00+00:00",
        "2026-08-28T12:00:00+00:00",
    )

    authoritative_inventory.assert_awaited_once_with(
        "tenant-1", "standard", date(2026, 8, 26), date(2026, 8, 28)
    )
    expected = {"2026-08-26": 0, "2026-08-27": 0}
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
