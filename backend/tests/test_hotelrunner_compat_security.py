import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, HTTPException

import routers.hotelrunner_compat as compat


class _FakeQueryParams:
    def __init__(self, values=None):
        self._values = values or {}

    def get(self, key, default=None):
        return self._values.get(key, default)


class _FakeRequest:
    def __init__(self, *, body=None, headers=None, query_params=None, tenant_id=""):
        self._body = json.dumps(body or {}).encode()
        self.headers = headers or {}
        self.query_params = _FakeQueryParams(query_params)
        self.path_params = {}
        self.scope = {"type": "http", "req_id": "compat-security-test"}
        self.client = SimpleNamespace(host="127.0.0.1")
        self.state = SimpleNamespace()
        if tenant_id:
            self.state.hr_webhook_tenant_id = tenant_id

    async def body(self):
        return self._body


def _clear_compat_environment(monkeypatch):
    for name in (
        "APP_ENV",
        "ENVIRONMENT",
        "NODE_ENV",
        "HOTELRUNNER_COMPAT_WEBHOOK_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)


def test_compatibility_webhook_defaults_disabled_in_production(monkeypatch):
    _clear_compat_environment(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")

    assert compat._compatibility_webhook_enabled() is False


def test_compatibility_webhook_can_be_explicitly_enabled_in_production(monkeypatch):
    _clear_compat_environment(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("HOTELRUNNER_COMPAT_WEBHOOK_ENABLED", "true")

    assert compat._compatibility_webhook_enabled() is True


def test_compatibility_webhook_stays_available_by_default_outside_production(monkeypatch):
    _clear_compat_environment(monkeypatch)

    assert compat._compatibility_webhook_enabled() is True


def test_compatibility_webhook_route_mounts_security_dependency():
    webhook_route = next(route for route in compat.router.routes if route.path.endswith("/webhook") and "POST" in route.methods)

    dependency_calls = [dependency.call for dependency in webhook_route.dependant.dependencies]
    assert compat._verify_compatibility_webhook in dependency_calls


@pytest.mark.asyncio
async def test_disabled_compatibility_webhook_fails_before_verification(monkeypatch):
    _clear_compat_environment(monkeypatch)
    monkeypatch.setenv("NODE_ENV", "production")
    verifier = AsyncMock()
    monkeypatch.setattr(compat, "_verify_hotelrunner_callback", verifier)

    with pytest.raises(HTTPException) as exc_info:
        await compat._verify_compatibility_webhook(_FakeRequest())

    assert exc_info.value.status_code == 404
    verifier.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsigned_compatibility_webhook_never_reaches_canonical_verifier(monkeypatch):
    _clear_compat_environment(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("HOTELRUNNER_COMPAT_WEBHOOK_ENABLED", "true")
    verifier = AsyncMock()
    monkeypatch.setattr(compat, "_verify_hotelrunner_callback", verifier)

    with pytest.raises(HTTPException) as exc_info:
        await compat._verify_compatibility_webhook(_FakeRequest())

    assert exc_info.value.status_code == 401
    verifier.assert_not_awaited()


@pytest.mark.asyncio
async def test_compatibility_webhook_requires_verified_tenant_binding(monkeypatch):
    _clear_compat_environment(monkeypatch)
    verifier = AsyncMock()
    monkeypatch.setattr(compat, "_verify_hotelrunner_callback", verifier)
    request = _FakeRequest(headers={"X-HotelRunner-Signature": "signed"})

    with pytest.raises(HTTPException) as exc_info:
        await compat._verify_compatibility_webhook(request)

    assert exc_info.value.status_code == 401
    verifier.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_compatibility_webhook_accepts_canonical_tenant_binding(monkeypatch):
    _clear_compat_environment(monkeypatch)

    async def _bind_tenant(request):
        request.state.hr_webhook_tenant_id = "verified-tenant"

    monkeypatch.setattr(compat, "_verify_hotelrunner_callback", _bind_tenant)
    request = _FakeRequest(headers={"X-HotelRunner-Signature": "signed"})

    await compat._verify_compatibility_webhook(request)

    assert compat._verified_tenant(request) == "verified-tenant"


@pytest.mark.asyncio
async def test_spoofed_tenant_inputs_cannot_override_verified_tenant(monkeypatch):
    persisted = AsyncMock()
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner_shared._persist_and_process",
        persisted,
    )
    request = _FakeRequest(
        body={
            "tenant_id": "body-tenant",
            "property_id": "property-A",
            "hr_number": "test-reservation",
        },
        headers={"X-Tenant-ID": "header-tenant"},
        query_params={"tenant_id": "query-tenant"},
        tenant_id="verified-tenant",
    )
    tasks = BackgroundTasks()

    response = await compat.hotelrunner_webhook(request, tasks)
    await tasks()

    assert response["status"] == "accepted"
    persisted.assert_awaited_once()
    assert persisted.await_args.args[0] == "verified-tenant"


@pytest.mark.asyncio
async def test_route_cannot_ack_without_verified_tenant_binding():
    request = _FakeRequest(
        body={"tenant_id": "untrusted", "hr_number": "test-reservation"},
        headers={"X-Tenant-ID": "untrusted"},
        query_params={"tenant_id": "untrusted"},
    )
    tasks = BackgroundTasks()

    with pytest.raises(HTTPException) as exc_info:
        await compat.hotelrunner_webhook(request, tasks)

    assert exc_info.value.status_code == 401
    assert tasks.tasks == []
