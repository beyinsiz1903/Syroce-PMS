"""Central entitlement check: same decision as get_tenant_modules (plan
name included) and no per-module bypass."""

from types import SimpleNamespace

import pytest

from core import entitlement


def _tenants(monkeypatch, doc):
    import core.subscriptions as subs

    seen = {}

    class Tenants:
        async def find_one(self, query, projection=None, *_a, **_k):
            seen["projection"] = projection
            return {k: v for k, v in doc.items() if projection is None or projection.get(k)} | {"id": query["id"]}

    async def none(*_a, **_k):
        return set()

    async def no(*_a, **_k):
        return False

    monkeypatch.setattr(entitlement, "db", SimpleNamespace(tenants=Tenants()))
    monkeypatch.setattr(subs, "subscribed_tenant_ids", none)
    monkeypatch.setattr(subs, "tenant_has_module", no)
    return seen


@pytest.mark.asyncio
async def test_pms_lite_plan_name_is_read_by_the_middleware_check(monkeypatch):
    """A PMS Lite hotel whose tier field says basic: the menu (get_tenant_modules)
    hides the channel manager; the central check must agree."""
    seen = _tenants(monkeypatch, {"subscription_plan": "pms_lite", "subscription_tier": "basic"})
    assert await entitlement._check_module_access("t1", "channel_manager") is False
    assert seen["projection"].get("subscription_plan") and seen["projection"].get("plan")
    _tenants(monkeypatch, {"subscription_tier": "basic"})
    assert await entitlement._check_module_access("t1", "channel_manager") is True


async def _academy_status(monkeypatch, licensed):
    async def access(_tenant_id, module):
        return licensed and module == "academy"

    async def not_admin(_user):
        return False

    async def no_usage(*_a, **_k):
        return None

    monkeypatch.setattr(entitlement, "_check_module_access", access)
    monkeypatch.setattr(entitlement, "_is_super_admin_user", not_admin)
    monkeypatch.setattr(entitlement, "record_usage", no_usage)
    monkeypatch.setattr(entitlement, "_get_token_from_headers", lambda _h: "t")
    monkeypatch.setattr(entitlement, "_decode_token_payload", lambda _t: {"tenant_id": "t1", "user_id": "u1"})
    sent = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request"}

    await entitlement.EntitlementMiddleware(app)({"type": "http", "path": "/api/academy/courses", "method": "GET", "headers": []}, receive, send)
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


@pytest.mark.asyncio
async def test_academy_has_no_bypass(monkeypatch):
    assert await _academy_status(monkeypatch, licensed=False) == 403
    assert await _academy_status(monkeypatch, licensed=True) == 200


@pytest.mark.asyncio
async def test_observe_mode_guard_counts_modules_that_come_with_the_plan(monkeypatch):
    """Switching ENTITLEMENT_ENFORCEMENT_MODE to enforce must not refuse a
    module the plan includes just because the hotel has no explicit flag."""
    import core.subscriptions as subs
    from core.entitlements import enforcement
    from domains.admin.subscription_models import get_plan_default_modules

    included = next(key for key in ("spa", "hr", "mice", "housekeeping") if get_plan_default_modules("enterprise").get(key))

    class Tenants:
        async def find_one(self, *_a, **_k):
            return {"subscription_tier": "enterprise", "modules": {}}

    async def no(*_a, **_k):
        return False

    async def none(*_a, **_k):
        return set()

    monkeypatch.setattr(subs, "_db", lambda: SimpleNamespace(tenants=Tenants()))
    monkeypatch.setattr(enforcement, "tenant_has_module", no)
    monkeypatch.setattr(subs, "subscribed_tenant_ids", none)
    assert await enforcement._module_enabled("t1", included) is True
    assert await enforcement._module_enabled("t1", "not_a_module") is False
