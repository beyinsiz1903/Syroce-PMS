"""Regression for live ARI panel IDs differing from discovery API aliases."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from domains.channel_manager import unified_rate_manager_router as router


@pytest.mark.asyncio
async def test_writable_exely_rooms_use_tenant_mappings_not_discovery_aliases(monkeypatch):
    cursor = SimpleNamespace(to_list=AsyncMock(return_value=[
        {"exely_room_code": "5003299", "exely_rate_plan_code": "10009740"},
        {"exely_room_code": "5003300", "exely_rate_plan_code": "10009740"},
        {"exely_room_code": "5003299", "exely_rate_plan_code": "10009738"},
        {"exely_room_code": "incomplete"},
    ]))
    mappings = SimpleNamespace(find=MagicMock(return_value=cursor))
    monkeypatch.setattr(router, "db", SimpleNamespace(exely_room_mappings=mappings))
    detection = {"provider": "exely", "connection": {"room_types": [
        {"code": "500157400"}, {"code": "5001575"}, {"code": "unmapped-api-room"},
    ]}}

    assert await router._writable_provider_room_codes("tenant-a", detection) == {"5003299", "5003300"}
    assert mappings.find.call_args.args[0] == {"tenant_id": "tenant-a"}


@pytest.mark.asyncio
async def test_discovery_without_mapping_does_not_enable_exely_writes(monkeypatch):
    mappings = SimpleNamespace(find=MagicMock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=[]))))
    monkeypatch.setattr(router, "db", SimpleNamespace(exely_room_mappings=mappings))
    assert await router._writable_provider_room_codes("tenant-b", {
        "provider": "exely", "connection": {"room_types": [{"code": "5001575"}]},
    }) == set()


@pytest.mark.asyncio
async def test_hotelrunner_keeps_verified_inventory_codes_without_exely_lookup(monkeypatch):
    monkeypatch.setattr(router, "db", SimpleNamespace())
    assert await router._writable_provider_room_codes("tenant-a", {
        "provider": "hotelrunner", "connection": {"cached_rooms": [{"inv_code": "HR-STD"}]},
    }) == {"HR-STD"}


@pytest.mark.asyncio
@pytest.mark.parametrize("selected_code,allowed", [("5003299", True), ("unmapped", False), ("500157400", False)])
async def test_bulk_availability_accepts_grid_mapping_but_blocks_unmapped_alias(monkeypatch, selected_code, allowed):
    calendar = SimpleNamespace(bulk_write=AsyncMock())
    database = MagicMock()
    database.exely_room_mappings.find.return_value.to_list = AsyncMock(return_value=[
        {"exely_room_code": "5003299", "exely_rate_plan_code": "10009740"},
    ])
    database.__getitem__.return_value = calendar
    monkeypatch.setattr(router, "db", database)
    monkeypatch.setattr(router, "_detect_active_provider", AsyncMock(return_value={
        "provider": "exely", "connection": {"room_types": [{"code": "500157400"}]},
    }))
    monkeypatch.setattr(router, "require_tenant_module", AsyncMock())
    monkeypatch.setattr(router, "_ari_write_block_for_targets", lambda *_args: "")
    push = AsyncMock(return_value={"task_count": 0, "delivery_state": "NOT_SENT"})
    monkeypatch.setattr(router, "_push_to_exely", push)
    request = router.UnifiedBulkUpdateRequest(
        room_type_codes=[selected_code], rate_plan_codes=["10009740"],
        start_date="2026-11-10", end_date="2026-11-10",
        availability=5, update_fields=["availability"],
    )
    user = SimpleNamespace(tenant_id="tenant-a", id="operator-a")
    if allowed:
        result = await router.unified_bulk_grid_update(request, user, None)
        assert result["saved"] == 1
        calendar.bulk_write.assert_awaited_once()
        assert push.await_args.args[3] == [("5003299", "10009740")]
        assert result["agency_push_count"] == 0
    else:
        with pytest.raises(HTTPException) as error:
            await router.unified_bulk_grid_update(request, user, None)
        assert error.value.status_code == 422
        calendar.bulk_write.assert_not_awaited()
        push.assert_not_awaited()
