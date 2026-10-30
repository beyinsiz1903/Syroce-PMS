"""Completing a cleaning task agrees with reservation room readiness."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,owner,expected", [("dirty", None, "inspected"), ("occupied", "guest", "occupied"), ("maintenance", None, "maintenance")])
async def test_cleaning_clears_stale_hk_flags_without_releasing_occupied_or_blocked_room(ledger_db, monkeypatch, status, owner, expected):
    from routers import housekeeping
    monkeypatch.setattr(housekeeping, "db", ledger_db)
    monkeypatch.setattr(housekeeping, "release_quota", AsyncMock())
    monkeypatch.setattr(housekeeping, "_invalidate_hk_caches", lambda *_: None)
    await ledger_db.rooms.insert_many([
        {"tenant_id": "qa", "id": "r", "status": status, "current_booking_id": owner, "housekeeping_status": "dirty"},
        {"tenant_id": "other", "id": "r", "status": "dirty", "housekeeping_status": "dirty"},
    ])
    await ledger_db.housekeeping_tasks.insert_one({"tenant_id": "qa", "id": "task", "room_id": "r", "task_type": "cleaning", "status": "in_progress"})
    await housekeeping.update_housekeeping_task("task", status="completed", assigned_to=None, assigned_to_user_id=None,
        current_user=SimpleNamespace(tenant_id="qa"), _perm=None)
    room = await ledger_db.rooms.find_one({"tenant_id": "qa"})
    assert (room["status"], room["housekeeping_status"], room["current_booking_id"]) == (expected, "clean", owner)
    assert (await ledger_db.rooms.find_one({"tenant_id": "other"}))["housekeeping_status"] == "dirty"
