from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
import domains.hr.router as hr


def payload(**overrides):
    return hr.OvertimeRequestPayload(**dict(
        {"staff_id": "qa", "work_date": "2026-09-11", "hours": 1.5, "reason": "QA overtime"}, **overrides))


@pytest.mark.parametrize("overrides", [
    {"work_date": "2026-02-30"}, {"hours": 0}, {"hours": 13}, {"reason": "   "},
])
def test_invalid_request(overrides):
    with pytest.raises(ValidationError):
        payload(**overrides)


@pytest.mark.asyncio
@pytest.mark.parametrize("role,staff,expected", [
    ("super_admin", {"name": "QA"}, 200),
    ("front_desk", {"name": "QA"}, 403),
    ("front_desk", {"name": "QA", "email": "qa@example.test"}, 200),
    ("super_admin", None, 404),
])
async def test_creation_permissions(monkeypatch, role, staff, expected):
    verify = AsyncMock(return_value=staff)
    insert = AsyncMock()
    monkeypatch.setattr(hr, "_verify_staff_in_tenant", verify)
    monkeypatch.setattr(hr, "db", SimpleNamespace(overtime_requests=SimpleNamespace(insert_one=insert)))
    monkeypatch.setattr(hr, "_notify_hr_managers", AsyncMock())
    user = SimpleNamespace(id="user", tenant_id="tenant", role=role, email="qa@example.test", granted_permissions=[])
    if expected == 200:
        result = await hr.create_overtime_request(payload(), user)
        assert result["overtime_request"]["status"] == "pending"
        insert.assert_awaited_once()
    else:
        with pytest.raises(HTTPException) as exc:
            await hr.create_overtime_request(payload(), user)
        assert exc.value.status_code == expected
        insert.assert_not_awaited()
    verify.assert_awaited_once_with("qa", "tenant")
