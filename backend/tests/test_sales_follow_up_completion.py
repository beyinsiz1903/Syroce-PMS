"""Regression coverage for the Sales CRM follow-up completion lifecycle."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.sales import router as sales_router


def test_open_follow_up_query_excludes_completed_tasks_and_stays_tenant_scoped():
    query = sales_router._open_follow_up_query("tenant-a", "activity-a")

    assert query["tenant_id"] == "tenant-a"
    assert query["id"] == "activity-a"
    assert query["follow_up_at"] == {"$nin": [None, ""]}
    assert query["follow_up_completed_at"] == {"$exists": False}


@pytest.mark.asyncio
async def test_complete_follow_up_is_tenant_scoped_and_audited(monkeypatch):
    collection = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
        find_one=AsyncMock(return_value={"lead_id": "lead-a"}),
    )
    audit = AsyncMock()
    monkeypatch.setattr(sales_router, "db", SimpleNamespace(mice_opportunity_activities=collection))
    monkeypatch.setattr(sales_router, "create_audit_log", audit)
    monkeypatch.setattr(sales_router, "_now", lambda: "2026-10-02T10:00:00+00:00")

    result = await sales_router.complete_sales_follow_up(
        "activity-a",
        current_user=SimpleNamespace(tenant_id="tenant-a", id="operator-a"),
    )

    assert result == {
        "success": True,
        "activity_id": "activity-a",
        "completed_at": "2026-10-02T10:00:00+00:00",
        "idempotent": False,
    }
    selector = collection.update_one.await_args.args[0]
    assert selector["tenant_id"] == "tenant-a"
    assert selector["id"] == "activity-a"
    assert selector["follow_up_completed_at"] == {"$exists": False}
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_replayed_completion_returns_existing_timestamp_without_new_audit(monkeypatch):
    collection = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=0)),
        find_one=AsyncMock(return_value={"follow_up_at": "2026-10-01T10:00:00+00:00", "follow_up_completed_at": "2026-10-02T10:00:00+00:00"}),
    )
    audit = AsyncMock()
    monkeypatch.setattr(sales_router, "db", SimpleNamespace(mice_opportunity_activities=collection))
    monkeypatch.setattr(sales_router, "create_audit_log", audit)

    result = await sales_router.complete_sales_follow_up(
        "activity-a",
        current_user=SimpleNamespace(tenant_id="tenant-a", id="operator-b"),
    )

    assert result["idempotent"] is True
    assert result["completed_at"] == "2026-10-02T10:00:00+00:00"
    audit.assert_not_awaited()
