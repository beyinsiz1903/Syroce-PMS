from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers import pms_services


def _user():
    return SimpleNamespace(
        id="user-1",
        name="Ayşe Resepsiyon",
        email="ayse@example.com",
        tenant_id="tenant-1",
    )


@pytest.mark.asyncio
async def test_guest_request_completion_requires_resolution_note(monkeypatch):
    task = {
        "id": "guest-qr:request-1",
        "tenant_id": "tenant-1",
        "source": "guest_qr",
        "source_request_id": "request-1",
    }
    staff_tasks = SimpleNamespace(find_one=AsyncMock(return_value=task))
    monkeypatch.setattr(pms_services, "db", SimpleNamespace(staff_tasks=staff_tasks))

    with pytest.raises(HTTPException) as exc:
        await pms_services.update_staff_task(
            task["id"],
            {"status": "completed"},
            current_user=_user(),
        )

    assert exc.value.status_code == 400
    assert "çözüm bilgisi" in exc.value.detail


@pytest.mark.asyncio
async def test_manual_task_update_drops_unapproved_fields(monkeypatch):
    before = {
        "id": "task-1",
        "tenant_id": "tenant-1",
        "source": "manual",
        "status": "pending",
    }
    after = {**before, "status": "in_progress"}
    staff_tasks = SimpleNamespace(
        find_one=AsyncMock(side_effect=[before, after]),
        update_one=AsyncMock(),
    )
    monkeypatch.setattr(pms_services, "db", SimpleNamespace(staff_tasks=staff_tasks))

    result = await pms_services.update_staff_task(
        "task-1",
        {"status": "in_progress", "tenant_id": "other-tenant", "source": "guest_qr"},
        current_user=_user(),
    )

    assert result == after
    query, update = staff_tasks.update_one.await_args.args
    assert query == {"id": "task-1", "tenant_id": "tenant-1"}
    assert update["$set"]["status"] == "in_progress"
    assert "tenant_id" not in update["$set"]
    assert "source" not in update["$set"]
