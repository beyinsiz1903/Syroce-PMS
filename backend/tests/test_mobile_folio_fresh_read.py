"""Cache-boundary regressions only; no live database, money or access changes."""
import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from starlette.requests import Request

import cache_manager
from routers.finance import folio as router


async def test_mobile_preflight_can_bypass_stale_folio_balance_and_status(monkeypatch):
    stale = {"folio": {"id": "F1", "status": "open", "currency": "EUR"}, "balance": 100}
    fresh = {"folio": {"id": "F1", "status": "closed", "currency": "EUR"}, "balance": 0}
    get_cached = Mock(return_value=stale)
    monkeypatch.setattr(cache_manager.cache, "enabled", True)
    monkeypatch.setattr(cache_manager.cache, "get", get_cached)
    monkeypatch.setattr(cache_manager.cache, "set", Mock())
    read = AsyncMock(return_value=fresh)
    monkeypatch.setattr(router.folio_balance_read_service, "get_folio_details", read)
    monkeypatch.setattr(router, "run_shadow_compare", AsyncMock())
    request = Request({"type": "http", "method": "GET", "path": "/api/folio/F1", "headers": []})
    user = SimpleNamespace(tenant_id="isolated-mobile-tenant", role="finance")
    assert await router.get_folio_details("F1", request, user, None) == stale
    read.assert_not_awaited()
    get_cached.reset_mock()
    assert await router.get_folio_details("F1", request, user, None, _nocache=True) == fresh
    get_cached.assert_not_called()
    read.assert_awaited_once_with(tenant_id=user.tenant_id, folio_id="F1")
    await asyncio.sleep(0)


def test_folio_read_exposes_normal_fresh_query_without_removing_read_permission():
    parameters = inspect.signature(router.get_folio_details).parameters
    assert parameters["_nocache"].default.alias == "nocache"
    assert parameters["_nocache"].default.default is False
    assert parameters["_perm"].default.dependency is not None
