from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pymongo.errors import AutoReconnect

from routers import pms_dashboard


class _FailingCursor:
    async def to_list(self, _limit):
        raise AutoReconnect("primary election")


class _FailingRooms:
    def aggregate(self, _pipeline):
        return _FailingCursor()


@pytest.mark.asyncio
async def test_dashboard_resolves_the_authoritative_open_business_date(monkeypatch):
    resolver = AsyncMock(return_value={"business_date": "2026-09-05"})
    monkeypatch.setattr(pms_dashboard, "ensure_business_date_initialized", resolver)

    assert await pms_dashboard._open_business_date("tenant-a") == "2026-09-05"
    resolver.assert_awaited_once_with(pms_dashboard.db, "tenant-a")


@pytest.mark.asyncio
async def test_dashboard_returns_retryable_503_for_transient_atlas_failure(monkeypatch):
    monkeypatch.setattr(pms_dashboard.db, "rooms", _FailingRooms())
    monkeypatch.setattr(pms_dashboard, "cache_warmer", None, raising=False)
    monkeypatch.setattr(
        pms_dashboard,
        "ensure_business_date_initialized",
        AsyncMock(return_value={"business_date": "2026-10-03"}),
    )

    with pytest.raises(HTTPException) as error:
        await pms_dashboard.get_pms_dashboard(SimpleNamespace(tenant_id="tenant-a"))

    assert error.value.status_code == 503
    assert error.value.headers == {"Retry-After": "3"}
    assert error.value.detail["code"] == "DATABASE_TRANSIENT_UNAVAILABLE"


@pytest.mark.asyncio
async def test_dashboard_rethrows_non_transient_programming_error(monkeypatch):
    class BrokenRooms:
        def aggregate(self, _pipeline):
            raise ValueError("bad aggregation")

    monkeypatch.setattr(pms_dashboard.db, "rooms", BrokenRooms())
    monkeypatch.setattr(pms_dashboard, "cache_warmer", None, raising=False)
    monkeypatch.setattr(
        pms_dashboard,
        "ensure_business_date_initialized",
        AsyncMock(return_value={"business_date": "2026-10-03"}),
    )

    with pytest.raises(ValueError, match="bad aggregation"):
        await pms_dashboard.get_pms_dashboard(SimpleNamespace(tenant_id="tenant-a"))
