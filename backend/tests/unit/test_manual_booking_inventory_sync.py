from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from channel_manager.application.event_sync_service import EventSyncService
from domains.channel_manager import availability_auto_sync


class _RoomsCollection:
    async def find_one(self, _query, _projection):
        return {"room_type": "standard"}


class _Cursor:
    def __init__(self, values):
        self.values = values

    async def to_list(self, _length):
        return self.values


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
    hotelrunner_push = AsyncMock(
        return_value={"configured": False, "queued_operations": 0, "errors": []}
    )
    exely_push = AsyncMock(
        return_value={"configured": True, "queued_operations": 1, "errors": []}
    )
    authoritative_inventory = AsyncMock(
        return_value={"2026-08-26": 0, "2026-08-27": 0}
    )
    monkeypatch.setattr(availability_auto_sync, "db", fake_db)
    monkeypatch.setattr(availability_auto_sync, "_push_to_hotelrunner", hotelrunner_push)
    monkeypatch.setattr(availability_auto_sync, "_push_to_exely", exely_push)
    monkeypatch.setattr(availability_auto_sync, "_load_authoritative_availability", authoritative_inventory)

    result = await availability_auto_sync._do_sync(
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
    assert result == {
        "configured_providers": 1,
        "queued_operations": 1,
        "errors": [],
    }


@pytest.mark.asyncio
async def test_exely_booking_sync_uses_only_explicit_mapping_rate_plan(monkeypatch):
    mapping = {
        "exely_room_code": "5003299",
        "exely_rate_plan_code": "10009740",
        "sync_availability": True,
    }
    database = type(
        "FakeDb",
        (),
        {
            "exely_connections": type(
                "Connections",
                (),
                {"find_one": AsyncMock(return_value={"hotel_code": "501694", "rate_plans": [{"code": "wrong"}]})},
            )(),
            "exely_room_mappings": type(
                "Mappings",
                (),
                {"find": lambda self, *_args, **_kwargs: _Cursor([mapping])},
            )(),
        },
    )()
    enqueue = AsyncMock(return_value={"accepted": True})
    monkeypatch.setattr(availability_auto_sync, "db", database)
    monkeypatch.setattr(
        "domains.channel_manager.providers.exely.ari_publish.enqueue_exely_ari_update",
        enqueue,
    )

    result = await availability_auto_sync._push_to_exely(
        "tenant-1",
        "standard",
        {"2026-11-10": 7, "2026-11-11": 7},
    )

    assert result == {"configured": True, "queued_operations": 1, "errors": []}
    enqueue.assert_awaited_once_with(
        "tenant-1",
        "501694",
        room_type_code="5003299",
        rate_plan_code="10009740",
        start_date="2026-11-10",
        end_date="2026-11-11",
        source_service="availability_auto_sync",
        availability=7,
    )


@pytest.mark.asyncio
async def test_exely_booking_sync_uses_complete_pms_api_pair_when_configured(monkeypatch):
    mapping = {
        "exely_room_code": "5003299",
        "exely_rate_plan_code": "10009740",
        "pms_api_room_code": "5001574",
        "pms_api_rate_plan_code": "10003870",
        "sync_availability": True,
    }
    database = type("FakeDb", (), {
        "exely_connections": type("Connections", (), {"find_one": AsyncMock(return_value={"hotel_code": "501694"})})(),
        "exely_room_mappings": type("Mappings", (), {"find": lambda self, *_args, **_kwargs: _Cursor([mapping])})(),
    })()
    enqueue = AsyncMock(return_value={"accepted": True})
    monkeypatch.setattr(availability_auto_sync, "db", database)
    monkeypatch.setattr(
        "domains.channel_manager.providers.exely.ari_publish.enqueue_exely_ari_update", enqueue,
    )

    result = await availability_auto_sync._push_to_exely(
        "tenant-1", "standard", {"2026-11-10": 7, "2026-11-11": 7},
    )

    assert result == {"configured": True, "queued_operations": 1, "errors": []}
    enqueue.assert_awaited_once_with(
        "tenant-1", "501694", room_type_code="5001574",
        rate_plan_code="10003870", start_date="2026-11-10",
        end_date="2026-11-11", source_service="availability_auto_sync",
        availability=7,
    )


@pytest.mark.asyncio
async def test_exely_booking_sync_refuses_multiple_availability_rate_plans(monkeypatch):
    mappings = [
        {"exely_room_code": "5003299", "exely_rate_plan_code": "10009740"},
        {"exely_room_code": "5003299", "exely_rate_plan_code": "10009741"},
    ]
    database = type("FakeDb", (), {
        "exely_connections": type("Connections", (), {"find_one": AsyncMock(return_value={"hotel_code": "501694"})})(),
        "exely_room_mappings": type("Mappings", (), {"find": lambda self, *_args, **_kwargs: _Cursor(mappings)})(),
    })()
    enqueue = AsyncMock()
    monkeypatch.setattr(availability_auto_sync, "db", database)
    monkeypatch.setattr("domains.channel_manager.providers.exely.ari_publish.enqueue_exely_ari_update", enqueue)

    result = await availability_auto_sync._push_to_exely("tenant-1", "Standard", {"2026-11-10": 7})

    assert result["queued_operations"] == 0
    assert result["errors"] == ["exely_multiple_availability_mappings"]
    enqueue.assert_not_awaited()


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
