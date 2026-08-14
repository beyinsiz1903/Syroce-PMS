from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from domains.channel_manager import unified_rate_manager_router as rate_router


@pytest.mark.asyncio
async def test_runtime_kill_switch_blocks_before_local_or_provider_write(monkeypatch):
    hotelrunner_connections = SimpleNamespace(
        find_one=AsyncMock(return_value={"tenant_id": "tenant-test", "is_active": True}),
    )
    exely_connections = SimpleNamespace(find_one=AsyncMock(return_value=None))
    fake_db = SimpleNamespace(
        hotelrunner_connections=hotelrunner_connections,
        exely_connections=exely_connections,
    )
    monkeypatch.setattr(rate_router, "db", fake_db)
    monkeypatch.setattr(rate_router, "_tenant_configured_provider", AsyncMock(return_value="hotelrunner"))
    monkeypatch.setattr(
        rate_router,
        "hotelrunner_ari_write_block_reason",
        MagicMock(return_value="HOTELRUNNER_ARI_WRITE_KILL_SWITCH_ACTIVE"),
    )

    request = rate_router.UnifiedBulkUpdateRequest(
        provider="hotelrunner",
        selections=[rate_router.RoomTypeSelection(room_type_code="room-test", rate_plan_codes=["plan-test"])],
        start_date="2026-08-14",
        end_date="2026-08-14",
        availability=1,
        update_fields=["availability"],
    )

    with pytest.raises(HTTPException) as exc_info:
        await rate_router.unified_bulk_grid_update(
            request,
            current_user=SimpleNamespace(tenant_id="tenant-test", id="user-test"),
            _perm=None,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "error_code": "HOTELRUNNER_ARI_WRITE_KILL_SWITCH_ACTIVE",
        "delivery_state": "BLOCKED",
        "provider_status_class": "NOT_SENT",
        "provider_write_count": 0,
    }
    assert not hasattr(fake_db, "hr_rate_calendar")


def test_scheduled_delivery_is_not_provider_verified():
    summary = rate_router._provider_delivery_summary([{"provider": "hotelrunner", "delivery_state": "SCHEDULED", "task_count": 1}])

    assert summary == {
        "provider_verified": False,
        "provider_delivery_state": "SCHEDULED",
        "provider_write_count": None,
    }
