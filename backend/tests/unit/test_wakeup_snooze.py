from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers.hotel_services_pkg import wakeup_lostfound
from routers.hotel_services_pkg._common import WakeUpCallUpdate


@pytest.mark.asyncio
async def test_snooze_clears_previous_alarm_and_notification(monkeypatch):
    wake_up_calls = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
        find_one=AsyncMock(
            return_value={
                "id": "call-1",
                "tenant_id": "tenant-a",
                "wake_date": "2026-08-31",
                "wake_time": "00:03",
                "status": "pending",
            }
        ),
    )
    notifications = SimpleNamespace(delete_many=AsyncMock())
    monkeypatch.setattr(
        wakeup_lostfound,
        "db",
        SimpleNamespace(wake_up_calls=wake_up_calls, notifications=notifications),
    )

    result = await wakeup_lostfound.update_wake_up_call(
        "call-1",
        WakeUpCallUpdate(
            wake_date="2026-08-31",
            wake_time="00:03",
            status="pending",
            attempt_count=1,
        ),
        SimpleNamespace(tenant_id="tenant-a", name="Reception"),
        _perm=None,
    )

    update_operation = wake_up_calls.update_one.await_args.args[1]
    assert update_operation["$set"]["wake_time"] == "00:03"
    assert update_operation["$set"]["attempt_count"] == 1
    assert update_operation["$unset"] == {"alert_fired_at": ""}
    notifications.delete_many.assert_awaited_once_with(
        {
            "tenant_id": "tenant-a",
            "source_type": "wake_up_call",
            "source_id": "call-1",
        }
    )
    assert result["call"]["wake_time"] == "00:03"
