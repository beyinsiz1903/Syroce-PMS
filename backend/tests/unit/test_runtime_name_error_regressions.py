"""Regressions for names that were undefined at runtime (F821 was ignored)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core import helpers
from routers.hotel_services_pkg import _common


@pytest.mark.asyncio
async def test_disabled_module_returns_403_not_500(monkeypatch):
    monkeypatch.setattr(helpers, "_is_super_admin", lambda user: False)
    monkeypatch.setattr(helpers, "_tenant_doc_cache_get", lambda tenant_id: {"id": tenant_id})
    monkeypatch.setattr(helpers, "get_tenant_modules", lambda doc: {})
    import core.subscriptions as subscriptions

    seen = {}

    async def has_module(tenant_id, module_name):
        seen["tenant_id"] = tenant_id
        return False

    monkeypatch.setattr(subscriptions, "tenant_has_module", has_module)
    dependency = helpers.require_module("spa")

    with pytest.raises(HTTPException) as exc:
        await dependency(current_user=SimpleNamespace(tenant_id="t1", role="admin", roles=[]))

    assert exc.value.status_code == 403
    assert seen["tenant_id"] == "t1"


@pytest.mark.asyncio
async def test_due_wake_up_call_creates_bell_notification(monkeypatch):
    notifications = SimpleNamespace(update_one=AsyncMock())
    wake_up_calls = SimpleNamespace(update_one=AsyncMock())
    monkeypatch.setattr(_common, "db", SimpleNamespace(notifications=notifications, wake_up_calls=wake_up_calls))
    call = {"id": "w1", "status": "pending", "wake_date": "2000-01-01", "wake_time": "07:00", "room_number": "101"}

    await _common._fire_due_wake_up_alerts("t1", [call])

    notifications.update_one.assert_awaited_once()
    wake_up_calls.update_one.assert_awaited_once()
    assert call["alert_fired_at"]
