"""Module-access regression checks for housekeeping mobile read endpoints."""

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.mobile_router import housekeeping


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [
        housekeeping.get_sla_delayed_rooms_mobile,
        housekeeping.get_team_assignments_mobile,
        housekeeping.get_inspection_checklist_template,
        housekeeping.get_lost_found_items,
        housekeeping.get_staff_assignments,
        housekeeping.get_hk_daily_report,
    ],
)
async def test_housekeeping_read_endpoints_reject_other_modules(endpoint):
    dependency = inspect.signature(endpoint).parameters["_perm"].default.dependency

    with pytest.raises(HTTPException) as error:
        await dependency(SimpleNamespace(role="front_desk"))

    assert error.value.status_code == 403
