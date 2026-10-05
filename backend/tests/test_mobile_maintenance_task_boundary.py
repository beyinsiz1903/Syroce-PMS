"""Authorization and data-integrity boundaries for mobile maintenance tasks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms.mobile_router import maintenance


@pytest.mark.asyncio
async def test_status_update_rejects_unknown_status_before_writing(monkeypatch):
    monkeypatch.setattr(
        maintenance,
        "get_current_user",
        AsyncMock(return_value=SimpleNamespace(tenant_id="tenant-1", username="tech")),
    )

    with pytest.raises(HTTPException) as error:
        await maintenance.update_task_status_mobile("task-1", "paid", credentials=None)

    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_status_update_only_queries_maintenance_tasks(monkeypatch):
    captured = []

    async def find_one(query):
        captured.append(query)
        return None

    monkeypatch.setattr(
        maintenance,
        "get_current_user",
        AsyncMock(return_value=SimpleNamespace(tenant_id="tenant-1", username="tech")),
    )
    monkeypatch.setattr(maintenance, "db", SimpleNamespace(tasks=SimpleNamespace(find_one=find_one)))

    with pytest.raises(HTTPException) as error:
        await maintenance.update_task_status_mobile("task-1", "completed", credentials=None)

    assert error.value.status_code == 404
    assert captured == [{"tenant_id": "tenant-1", "department": "maintenance", "id": "task-1"}]
