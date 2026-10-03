"""Module-access regression checks for mobile notification summaries."""

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.mobile_router import notifications


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "unauthorized_role"),
    [
        (notifications.get_frontdesk_notifications_mobile, "housekeeping"),
        (notifications.get_housekeeping_notifications_mobile, "front_desk"),
        (notifications.get_maintenance_notifications_mobile, "staff"),
        (notifications.get_fnb_notifications_mobile, "housekeeping"),
    ],
)
async def test_department_notification_summaries_reject_other_modules(endpoint, unauthorized_role):
    dependency = inspect.signature(endpoint).parameters["_perm"].default.dependency

    with pytest.raises(HTTPException) as error:
        await dependency(SimpleNamespace(role=unauthorized_role))

    assert error.value.status_code == 403
