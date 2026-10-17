"""Agency Extranet is its own module, separate from the OTA channel manager."""

import pytest

from core import entitlement
from core.helpers import get_tenant_modules


@pytest.mark.parametrize("modules,expected", [
    ({"channel_manager": True}, True),             # existing hotels keep access
    ({"channel_manager": False}, False),
    ({"channel_manager": False, "agency_extranet": True}, True),   # agency extranet without OTA
    ({"channel_manager": True, "agency_extranet": False}, False),  # OTA without agency extranet
])
def test_agency_extranet_follows_the_channel_manager_until_set(modules, expected):
    assert get_tenant_modules({"subscription_tier": "basic", "modules": modules})["agency_extranet"] is expected


def test_without_explicit_modules_it_follows_the_plan_channel_manager():
    for tier in ("mini", "basic", "professional", "enterprise"):
        merged = get_tenant_modules({"subscription_tier": tier})
        assert merged["agency_extranet"] == merged.get("channel_manager", False)


@pytest.mark.parametrize("path,module", [
    ("/api/marketplace/v1/extranet/profile", "agency_extranet"),
    ("/api/marketplace/hotel/statements/s1", "agency_extranet"),
    ("/api/marketplace/hotel/agency-readiness", "agency_extranet"),
    ("/api/marketplace/incoming-requests/c1/approve", "agency_extranet"),
    ("/api/marketplace/products", "channel_manager"),  # hotel supplies market: unchanged here
    ("/api/channel-manager/unified-rate-manager/agency-rates", ("channel_manager", "agency_extranet")),
    ("/api/channel-manager/connections", "channel_manager"),
])
def test_route_modules(path, module):
    assert entitlement._match_route_module(path) == module


async def _status(monkeypatch, path, granted):
    async def access(tenant_id, module):
        return module in granted

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

    await entitlement.EntitlementMiddleware(app)({"type": "http", "path": path, "method": "GET", "headers": []}, receive, send)
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


@pytest.mark.asyncio
async def test_agency_only_hotel_shares_rates_but_has_no_ota(monkeypatch):
    granted = {"agency_extranet"}
    assert await _status(monkeypatch, "/api/marketplace/hotel/statements", granted) == 200
    assert await _status(monkeypatch, "/api/channel-manager/unified-rate-manager/agency-rates", granted) == 200
    assert await _status(monkeypatch, "/api/channel-manager/connections", granted) == 403


@pytest.mark.asyncio
async def test_ota_only_hotel_has_no_agency_extranet(monkeypatch):
    granted = {"channel_manager"}
    assert await _status(monkeypatch, "/api/marketplace/incoming-requests", granted) == 403
    assert await _status(monkeypatch, "/api/channel-manager/unified-rate-manager/grid", granted) == 200
