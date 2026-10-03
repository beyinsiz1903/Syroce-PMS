"""Regression coverage for executive data in the mobile personal hub."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.pms.mobile_router import hub


class _Counter:
    async def count_documents(self, _query):
        return 0


@pytest.mark.asyncio
async def test_today_digest_hides_hotel_kpis_from_non_executive_staff(monkeypatch):
    """A personal task digest must not leak or calculate hotel-wide metrics."""
    user = SimpleNamespace(
        id="staff-1",
        tenant_id="tenant-1",
        name="Ada",
        username="ada",
        role="housekeeping",
    )
    monkeypatch.setattr(hub, "get_current_user", AsyncMock(return_value=user))
    monkeypatch.setattr(
        hub,
        "_collect_my_tasks",
        AsyncMock(return_value=[{"id": "task-1", "priority": "high"}]),
    )
    monkeypatch.setattr(hub, "_can", lambda _user, _operation: False)
    monkeypatch.setattr(hub, "_can_procurement", lambda _user: False)
    monkeypatch.setattr(
        hub,
        "db",
        SimpleNamespace(notifications=_Counter(), alerts=_Counter()),
    )

    response = await hub.get_today_digest(credentials=None)

    assert response["open_tasks"] == 1
    assert response["urgent_tasks"] == 1
    assert response["tasks_preview"] == [{"id": "task-1", "priority": "high"}]
    assert not {
        "occupancy_pct",
        "occupied_rooms",
        "total_rooms",
        "check_ins",
        "check_outs",
        "open_faults",
        "hotel_name",
    }.intersection(response)
