"""Ownership checks for the mobile housekeeping cleaning timer."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms.mobile_router import housekeeping


def _timer():
    return {
        "id": "timer-1",
        "staff_id": "attendant-1",
        "staff_name": "attendant",
        "room_number": "101",
        "started_at": datetime.now(UTC) - timedelta(minutes=10),
    }


@pytest.mark.asyncio
async def test_attendant_cannot_stop_another_attendants_timer(monkeypatch):
    cleaning_timers = SimpleNamespace(find_one=AsyncMock(return_value=_timer()))
    monkeypatch.setattr(
        housekeeping,
        "get_current_user",
        AsyncMock(return_value=SimpleNamespace(id="attendant-2", username="other", tenant_id="tenant-1", role="housekeeping")),
    )
    monkeypatch.setattr(housekeeping, "db", SimpleNamespace(cleaning_timers=cleaning_timers))

    with pytest.raises(HTTPException) as error:
        await housekeeping.stop_cleaning_timer("room-101", credentials=None)

    assert error.value.status_code == 403
    assert not hasattr(cleaning_timers, "update_one")


@pytest.mark.asyncio
async def test_supervisor_can_stop_stranded_timer_with_audit_marker(monkeypatch):
    cleaning_timers = SimpleNamespace(find_one=AsyncMock(return_value=_timer()), update_one=AsyncMock())
    rooms = SimpleNamespace(update_one=AsyncMock())
    monkeypatch.setattr(
        housekeeping,
        "get_current_user",
        AsyncMock(return_value=SimpleNamespace(id="supervisor-1", username="lead", tenant_id="tenant-1", role="supervisor")),
    )
    monkeypatch.setattr(housekeeping, "db", SimpleNamespace(cleaning_timers=cleaning_timers, rooms=rooms))

    await housekeeping.stop_cleaning_timer("room-101", credentials=None)

    values = cleaning_timers.update_one.await_args.args[1]["$set"]
    assert values["completed_by"] == "supervisor-1"
    assert values["supervisor_override"] is True
