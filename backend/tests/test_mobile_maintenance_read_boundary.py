"""Module-access regression checks for maintenance mobile read endpoints."""

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.mobile_router import maintenance


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [
        maintenance.get_pm_schedule_mobile,
        maintenance.get_sla_configurations,
        maintenance.get_spare_parts_mobile,
        maintenance.get_asset_history_mobile,
        maintenance.get_planned_maintenance_mobile,
        maintenance.get_filtered_tasks_mobile,
    ],
)
async def test_maintenance_read_endpoints_reject_other_modules(endpoint):
    dependency = inspect.signature(endpoint).parameters["_perm"].default.dependency

    with pytest.raises(HTTPException) as error:
        await dependency(SimpleNamespace(role="front_desk"))

    assert error.value.status_code == 403
