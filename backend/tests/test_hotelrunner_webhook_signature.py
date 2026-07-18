"""F8 § 50 (Wave 3) — HotelRunner inbound webhook HMAC signature gate.

Locks the fail-closed signature verification + dev test-mode escape so the
CM webhook auth mode the stress spec classifies stays stable:
  - secret unset + no escape  → 503 (fail-closed)
  - secret unset + escape=1    → allowed (dev test mode)
  - valid HMAC-SHA256          → allowed
  - bad signature / stale ts / missing headers → 401
"""

import hashlib
import hmac
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import domains.channel_manager.providers.hotelrunner_security as hs
from domains.channel_manager.providers.hotelrunner_security import (
    _verify_hotelrunner_callback,
    _verified_tenant,
)


class _FakeQueryParams:
    def __init__(self, data=None):
        self._data = data or {}

    def get(self, key, default=None):
        return self._data.get(key, default)


class _FakeRequest:
    def __init__(self, headers=None, body_bytes=b"{}", query_params=None, client_host=None):
        self.headers = headers or {}
        self._body = body_bytes
        self.query_params = _FakeQueryParams(query_params or {})
        self.path_params = {}
        self.client = SimpleNamespace(host=client_host or "127.0.0.1")
        # request.state always available so tenant binding can be asserted.
        self.state = SimpleNamespace()

    async def body(self):
        return self._body


def _sign(secret, ts, raw):
    return hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_secret_unset_fail_closed(monkeypatch):
    monkeypatch.delenv("HOTELRUNNER_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK", raising=False)
    
    async def _fake_lookup(hr_id_hint):
        return {"tenant_id": "tenant-A", "hr_id": "mock-hr-id"}
    monkeypatch.setattr(hs, "_lookup_signing_connection", _fake_lookup)
    
    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_callback(_FakeRequest({"X-HotelRunner-Signature": "invalid", "X-HotelRunner-Timestamp": str(int(time.time()))}, b'{"hr_id": "mock-hr-id"}'))
    assert ei.value.status_code == 503



@pytest.mark.asyncio
async def test_valid_signature_allows(monkeypatch):
    secret = "s3cr3t"
    monkeypatch.setenv("HOTELRUNNER_WEBHOOK_SECRET", secret)
    raw = b'{"event":"new","hr_id":"mock-hr-id"}'
    ts = str(int(time.time()))
    
    async def _fake_lookup(hr_id_hint):
        return {"tenant_id": "tenant-A", "hr_id": "mock-hr-id"}
    monkeypatch.setattr(hs, "_lookup_signing_connection", _fake_lookup)
    
    headers = {
        "X-HotelRunner-Signature": f"sha256={_sign(secret, ts, raw)}",
        "X-HotelRunner-Timestamp": ts,
    }
    await _verify_hotelrunner_callback(_FakeRequest(headers, raw))


@pytest.mark.asyncio
async def test_bad_signature_rejected(monkeypatch):
    monkeypatch.setenv("HOTELRUNNER_WEBHOOK_SECRET", "s3cr3t")
    ts = str(int(time.time()))
    headers = {
        "X-HotelRunner-Signature": "sha256=deadbeef",
        "X-HotelRunner-Timestamp": ts,
    }
    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_callback(_FakeRequest(headers, b"{}"))
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_stale_timestamp_rejected(monkeypatch):
    secret = "s3cr3t"
    monkeypatch.setenv("HOTELRUNNER_WEBHOOK_SECRET", secret)
    raw = b"{}"
    ts = str(int(time.time()) - 1000)
    headers = {
        "X-HotelRunner-Signature": f"sha256={_sign(secret, ts, raw)}",
        "X-HotelRunner-Timestamp": ts,
    }
    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_callback(_FakeRequest(headers, raw))
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_headers_rejected(monkeypatch):
    monkeypatch.setenv("HOTELRUNNER_WEBHOOK_SECRET", "s3cr3t")
    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_callback(_FakeRequest({"X-HotelRunner-Signature": "invalid"}, b'{"hr_id": "mock-hr-id"}'))
    assert ei.value.status_code == 401


# ── Task #397: per-property secret + cryptographic tenant binding ─────


@pytest.mark.asyncio
async def test_per_property_secret_binds_tenant(monkeypatch):
    """A per-property secret verifies the HMAC AND binds the owning tenant
    onto request.state, regardless of any client-supplied tenant hint."""
    monkeypatch.delenv("HOTELRUNNER_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK", raising=False)

    secret = "per-property-secret"
    conn = {"tenant_id": "tenant-A", "hr_id": "hotel-A"}

    async def _fake_lookup(hr_id_hint):
        return conn

    async def _fake_load(c):
        return secret

    monkeypatch.setattr(hs, "_lookup_signing_connection", _fake_lookup)
    monkeypatch.setattr(hs, "_load_webhook_secret", _fake_load)

    raw = b'{"event":"new","hr_id":"hotel-A"}'
    ts = str(int(time.time()))
    headers = {
        "X-HotelRunner-Signature": f"sha256={_sign(secret, ts, raw)}",
        "X-HotelRunner-Timestamp": ts,
        # Attacker-supplied tenant hint that must NOT win.
        "X-Tenant-ID": "tenant-EVIL",
    }
    req = _FakeRequest(headers, raw)
    await _verify_hotelrunner_callback(req)
    # Bound tenant is the secret owner, not the client-supplied header.
    assert _verified_tenant(req) == "tenant-A"


@pytest.mark.asyncio
async def test_wrong_property_secret_rejected(monkeypatch):
    """A request signed with the WRONG secret for the resolved property is
    rejected (401) even though a per-property secret exists."""
    monkeypatch.delenv("HOTELRUNNER_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK", raising=False)

    conn = {"tenant_id": "tenant-A", "hr_id": "hotel-A"}

    async def _fake_lookup(hr_id_hint):
        return conn

    async def _fake_load(c):
        return "correct-secret"

    monkeypatch.setattr(hs, "_lookup_signing_connection", _fake_lookup)
    monkeypatch.setattr(hs, "_load_webhook_secret", _fake_load)

    raw = b'{"event":"new","hr_id":"hotel-A"}'
    ts = str(int(time.time()))
    headers = {
        "X-HotelRunner-Signature": f"sha256={_sign('attacker-secret', ts, raw)}",
        "X-HotelRunner-Timestamp": ts,
    }
    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_callback(_FakeRequest(headers, raw))
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_global_secret_fallback_when_no_per_property(monkeypatch):
    """When the resolved connection has no per-property secret, the global
    env secret is used as a backward-compat fallback."""
    secret = "global-secret"
    monkeypatch.setenv("HOTELRUNNER_WEBHOOK_SECRET", secret)
    monkeypatch.delenv("ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK", raising=False)

    conn = {"tenant_id": "tenant-A", "hr_id": "hotel-A"}

    async def _fake_lookup(hr_id_hint):
        return conn

    async def _fake_load(c):
        return None  # no per-property secret configured

    monkeypatch.setattr(hs, "_lookup_signing_connection", _fake_lookup)
    monkeypatch.setattr(hs, "_load_webhook_secret", _fake_load)

    raw = b'{"event":"new","hr_id":"hotel-A"}'
    ts = str(int(time.time()))
    headers = {
        "X-HotelRunner-Signature": f"sha256={_sign(secret, ts, raw)}",
        "X-HotelRunner-Timestamp": ts,
    }
    req = _FakeRequest(headers, raw)
    await _verify_hotelrunner_callback(req)
    # Global fallback still binds the resolved connection's tenant.
    assert _verified_tenant(req) == "tenant-A"


@pytest.mark.asyncio
async def test_cross_tenant_forge_with_other_secret_rejected(monkeypatch):
    """Per-property exclusivity: an attacker who knows tenant-B's secret
    cannot forge an event for tenant-A. The resolved connection (A) loads
    A's secret, so a B-signed payload fails verification (401)."""
    monkeypatch.delenv("HOTELRUNNER_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK", raising=False)

    secrets_by_tenant = {"tenant-A": "secret-A", "tenant-B": "secret-B"}

    async def _fake_lookup(hr_id_hint):
        # Hint resolves to tenant-A (the victim).
        return {"tenant_id": "tenant-A", "hr_id": "hotel-A"}

    async def _fake_load(c):
        return secrets_by_tenant.get(c["tenant_id"])

    monkeypatch.setattr(hs, "_lookup_signing_connection", _fake_lookup)
    monkeypatch.setattr(hs, "_load_webhook_secret", _fake_load)

    raw = b'{"event":"new","hr_id":"hotel-A","tenant_id":"tenant-A"}'
    ts = str(int(time.time()))
    # Signed with tenant-B's secret — must be rejected against A's secret.
    headers = {
        "X-HotelRunner-Signature": f"sha256={_sign(secrets_by_tenant['tenant-B'], ts, raw)}",
        "X-HotelRunner-Timestamp": ts,
    }
    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_callback(_FakeRequest(headers, raw))
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_webhook_official_production_secrets_manager_path(monkeypatch):
    """Production path test: APP_ENV=production, connection.token is absent, token is loaded from SecretsManager"""
    monkeypatch.setenv("APP_ENV", "production")
    conn = {"tenant_id": "tenant-prod", "hr_id": "hotel-prod"}
    
    async def _fake_lookup(hr_id_hint):
        return conn if hr_id_hint == "hotel-prod" else None
        
    class FakeSecretsManager:
        async def get_provider_credentials(self, tenant_id, provider, property_id, actor="system"):
            if tenant_id == "tenant-prod":
                return {"token": "prod-sm-token", "callback_secret": "prod-callback-secret"}
            return None
            
    monkeypatch.setattr(hs, "_lookup_signing_connection", _fake_lookup)
    monkeypatch.setattr(hs, "get_secrets_manager", lambda: FakeSecretsManager())
    
    # Test 1: Success with correct token and secret
    raw = b'{"hr_id": "hotel-prod"}'
    headers = {"Content-Type": "application/json"}
    req = _FakeRequest(headers, raw, query_params={"token": "prod-sm-token"})
    # Need to simulate the URL path matching the secret
    req.path_params = {"secret": "prod-callback-secret"}
    req.url = SimpleNamespace(path="/api/channel-manager/hotelrunner/webhooks/reservations/prod-callback-secret")
    
    await _verify_hotelrunner_callback(req)
    assert _verified_tenant(req) == "tenant-prod"
    
    # Test 2: Invalid token -> 401
    req_bad_token = _FakeRequest(headers, raw, query_params={"token": "wrong-token"})
    req_bad_token.path_params = {"secret": "prod-callback-secret"}
    req_bad_token.url = SimpleNamespace(path="/api/channel-manager/hotelrunner/webhooks/reservations/prod-callback-secret")
    
    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_callback(req_bad_token)
    assert ei.value.status_code == 401
    
    # Test 3: Missing or wrong callback path secret -> 401
    req_no_secret = _FakeRequest(headers, raw, query_params={"token": "prod-sm-token"})
    req_no_secret.path_params = {}
    req_no_secret.url = SimpleNamespace(path="/api/channel-manager/hotelrunner/webhooks/reservations/")
    
    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_callback(req_no_secret)
    assert ei.value.status_code == 401

    # Test 4: SecretsManager credential missing -> 503
    class FakeEmptySecretsManager:
        async def get_provider_credentials(self, *args, **kwargs):
            return None
    monkeypatch.setattr(hs, "get_secrets_manager", lambda: FakeEmptySecretsManager())
    
    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_callback(req)
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_hotelrunner_webhook_csrf_exemption(monkeypatch):
    """Ensure HotelRunner webhook endpoints bypass CSRF check."""
    from security.csrf_guard import csrf_guard_middleware
    
    # Simulate a POST request without Origin/Referer (which would normally trigger 403 CSRF)
    headers = {}
    
    # 1. Test unified callback path
    req_callback = _FakeRequest(headers, b"{}")
    req_callback.method = "POST"
    req_callback.url = SimpleNamespace(path="/api/channel-manager/hotelrunner/callback/secret123")
    
    # Mock call_next to just return 200 (meaning it bypassed CSRF)
    async def mock_call_next(req):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=200, content={"success": True})
        
    resp_callback = await csrf_guard_middleware(req_callback, mock_call_next)
    assert resp_callback.status_code == 200, "CSRF guard blocked the unified callback path"
    
    # 2. Test specific webhook path
    req_webhook = _FakeRequest(headers, b"{}")
    req_webhook.method = "POST"
    req_webhook.url = SimpleNamespace(path="/api/channel-manager/hotelrunner/webhooks/reservations/secret123")
    
    resp_webhook = await csrf_guard_middleware(req_webhook, mock_call_next)
    assert resp_webhook.status_code == 200, "CSRF guard blocked the specific webhook path"
