from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.context import OperationContext
from domains.pms import frontdesk_router, frontdesk_service


@pytest.mark.asyncio
@pytest.mark.parametrize("method,field", [("get_arrivals", "check_in"), ("get_departures", "check_out")])
async def test_frontdesk_defaults_to_tenant_business_day_and_includes_date_only_rows(monkeypatch, method, field):
    collection = MagicMock()
    collection.find.return_value.to_list = AsyncMock(return_value=[])
    service = frontdesk_service.FrontdeskService.__new__(frontdesk_service.FrontdeskService)
    service._db = SimpleNamespace(bookings=collection)
    initialize = AsyncMock(return_value={"business_date": "2026-10-26"})
    monkeypatch.setattr(frontdesk_service, "ensure_business_date_initialized", initialize)
    await getattr(service, method)(OperationContext(tenant_id="tenant-a", actor_id="qa"))
    query = collection.find.call_args.args[0]
    assert query["tenant_id"] == "tenant-a"
    assert query[field] == {"$gte": "2026-10-26", "$lt": "2026-10-27"}
    initialize.assert_awaited_once_with(service._db, "tenant-a")


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get_arrivals", "get_departures"])
async def test_explicit_day_is_respected_without_reading_another_operational_day(monkeypatch, method):
    service = frontdesk_service.FrontdeskService.__new__(frontdesk_service.FrontdeskService)
    service._db = SimpleNamespace(bookings=MagicMock())
    service._db.bookings.find.return_value.to_list = AsyncMock(return_value=[])
    initialize = AsyncMock()
    monkeypatch.setattr(frontdesk_service, "ensure_business_date_initialized", initialize)
    await getattr(service, method)(OperationContext(tenant_id="t", actor_id="qa"), "2026-11-10")
    initialize.assert_not_awaited()
    with pytest.raises(ValueError):
        await getattr(service, method)(OperationContext(tenant_id="t", actor_id="qa"), "2026-02-30")


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get_arrivals", "get_departures"])
async def test_router_returns_bad_request_for_invalid_calendar_date(monkeypatch, method):
    from fastapi import HTTPException
    monkeypatch.setattr(frontdesk_router.frontdesk_service, method, AsyncMock(side_effect=ValueError("invalid")))
    with pytest.raises(HTTPException) as exc:
        await getattr(frontdesk_router, method)(date="invalid", current_user=SimpleNamespace(tenant_id="t", id="qa"))
    assert exc.value.status_code == 400
