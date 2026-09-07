"""Leave creation authorization regression tests; all persistence is mocked."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import domains.hr.router as hr


@pytest.fixture
def persistence(monkeypatch):
    verify = AsyncMock(return_value={"id": "staff-qa", "name": "QA"})
    insert = AsyncMock()
    monkeypatch.setattr(hr, "_verify_staff_in_tenant", verify)
    monkeypatch.setattr(hr, "db", SimpleNamespace(leave_requests=SimpleNamespace(insert_one=insert)))
    monkeypatch.setattr(hr, "_notify_hr_managers", AsyncMock())
    return verify, insert


def user(role, **kwargs):
    return SimpleNamespace(id="user-qa", tenant_id="tenant-qa", role=role, granted_permissions=[], **kwargs)


def payload(staff_id="staff-qa"):
    return hr.LeaveRequestPayload(staff_id=staff_id, start_date="2026-09-08", end_date="2026-09-09")


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["super_admin", "admin", "supervisor", "finance"])
async def test_manager_can_create_for_tenant_staff(persistence, role):
    result = await hr.create_leave_request(payload(), user(role))
    assert result["success"] is True
    persistence[0].assert_awaited_once_with("staff-qa", "tenant-qa")
    persistence[1].assert_awaited_once()


@pytest.mark.asyncio
async def test_ordinary_user_cannot_create_for_other_staff(persistence):
    with pytest.raises(HTTPException) as exc:
        await hr.create_leave_request(payload(), user("front_desk"))
    assert exc.value.status_code == 403
    persistence[1].assert_not_awaited()


@pytest.mark.asyncio
async def test_self_service_still_allowed(persistence):
    result = await hr.create_leave_request(payload("user-qa"), user("front_desk"))
    assert result["success"] is True


@pytest.mark.asyncio
async def test_super_admin_cannot_bypass_tenant_check(persistence):
    persistence[0].return_value = None
    with pytest.raises(HTTPException) as exc:
        await hr.create_leave_request(payload(), user("super_admin"))
    assert exc.value.status_code == 404
    persistence[1].assert_not_awaited()
