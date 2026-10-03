"""Access and lifecycle regression checks for mobile front-desk actions."""

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.pms.mobile_router import frontdesk


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [frontdesk.get_early_checkin_requests_mobile, frontdesk.get_late_checkout_requests_mobile],
)
async def test_frontdesk_request_lists_reject_other_modules(endpoint):
    dependency = inspect.signature(endpoint).parameters["_perm"].default.dependency

    with pytest.raises(HTTPException) as error:
        await dependency(SimpleNamespace(role="housekeeping"))

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_no_show_rejects_checked_in_booking_without_writing(monkeypatch):
    bookings = SimpleNamespace(find_one=AsyncMock(return_value={"id": "booking-1", "status": "checked_in"}))
    monkeypatch.setattr(
        frontdesk,
        "get_current_user",
        AsyncMock(return_value=SimpleNamespace(tenant_id="tenant-1", username="reception")),
    )
    monkeypatch.setattr(frontdesk, "db", SimpleNamespace(bookings=bookings))

    with pytest.raises(HTTPException) as error:
        await frontdesk.process_no_show_mobile(frontdesk.ProcessNoShowRequest(booking_id="booking-1"), credentials=None)

    assert error.value.status_code == 409
    assert not hasattr(bookings, "update_one")
