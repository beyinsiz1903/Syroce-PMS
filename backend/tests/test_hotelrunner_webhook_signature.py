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

import domains.channel_manager.providers.hotelrunner_webhook as hw
from domains.channel_manager.providers.hotelrunner_webhook import (
    _verify_hotelrunner_signature,
    _verified_tenant,
)


class _FakeQueryParams:
    def __init__(self, data=None):
        self._data = data or {}

    def get(self, key, default=None):
        return self._data.get(key, default)


class _FakeRequest:
    def __init__(self, headers=None, body=b"{}", query_params=None, client_host=None):
        self.headers = headers or {}
        self._body = body
        if query_params is not None:
            self.query_params = _FakeQueryParams(query_params)
        if client_host is not None:
            self.client = SimpleNamespace(host=client_host)
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
    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_signature(_FakeRequest())
    assert ei.value.status_code == 503


@pytest.mark.asyncio
async def test_secret_unset_escape_allows(monkeypatch):
    monkeypatch.delenv("HOTELRUNNER_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK", "1")
    # Should not raise.
    await _verify_hotelrunner_signature(_FakeRequest())


@pytest.mark.asyncio
async def test_valid_signature_allows(monkeypatch):
    secret = "s3cr3t"
    monkeypatch.setenv("HOTELRUNNER_WEBHOOK_SECRET", secret)
    raw = b'{"event":"new"}'
    ts = str(int(time.time()))
    headers = {
        "X-HotelRunner-Signature": f"sha256={_sign(secret, ts, raw)}",
        "X-HotelRunner-Timestamp": ts,
    }
    await _verify_hotelrunner_signature(_FakeRequest(headers, raw))


@pytest.mark.asyncio
async def test_bad_signature_rejected(monkeypatch):
    monkeypatch.setenv("HOTELRUNNER_WEBHOOK_SECRET", "s3cr3t")
    ts = str(int(time.time()))
    headers = {
        "X-HotelRunner-Signature": "sha256=deadbeef",
        "X-HotelRunner-Timestamp": ts,
    }
    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_signature(_FakeRequest(headers, b"{}"))
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
        await _verify_hotelrunner_signature(_FakeRequest(headers, raw))
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_headers_rejected(monkeypatch):
    monkeypatch.setenv("HOTELRUNNER_WEBHOOK_SECRET", "s3cr3t")
    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_signature(_FakeRequest({}, b"{}"))
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

    async def _fake_lookup(tenant_hint, hr_id_hint):
        return conn

    async def _fake_load(c):
        return secret

    monkeypatch.setattr(hw, "_lookup_signing_connection", _fake_lookup)
    monkeypatch.setattr(hw, "_load_webhook_secret", _fake_load)

    raw = b'{"event":"new","hr_id":"hotel-A"}'
    ts = str(int(time.time()))
    headers = {
        "X-HotelRunner-Signature": f"sha256={_sign(secret, ts, raw)}",
        "X-HotelRunner-Timestamp": ts,
        # Attacker-supplied tenant hint that must NOT win.
        "X-Tenant-ID": "tenant-EVIL",
    }
    req = _FakeRequest(headers, raw)
    await _verify_hotelrunner_signature(req)
    # Bound tenant is the secret owner, not the client-supplied header.
    assert _verified_tenant(req) == "tenant-A"


@pytest.mark.asyncio
async def test_wrong_property_secret_rejected(monkeypatch):
    """A request signed with the WRONG secret for the resolved property is
    rejected (401) even though a per-property secret exists."""
    monkeypatch.delenv("HOTELRUNNER_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK", raising=False)

    conn = {"tenant_id": "tenant-A", "hr_id": "hotel-A"}

    async def _fake_lookup(tenant_hint, hr_id_hint):
        return conn

    async def _fake_load(c):
        return "correct-secret"

    monkeypatch.setattr(hw, "_lookup_signing_connection", _fake_lookup)
    monkeypatch.setattr(hw, "_load_webhook_secret", _fake_load)

    raw = b'{"event":"new","hr_id":"hotel-A"}'
    ts = str(int(time.time()))
    headers = {
        "X-HotelRunner-Signature": f"sha256={_sign('attacker-secret', ts, raw)}",
        "X-HotelRunner-Timestamp": ts,
    }
    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_signature(_FakeRequest(headers, raw))
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_global_secret_fallback_when_no_per_property(monkeypatch):
    """When the resolved connection has no per-property secret, the global
    env secret is used as a backward-compat fallback."""
    secret = "global-secret"
    monkeypatch.setenv("HOTELRUNNER_WEBHOOK_SECRET", secret)
    monkeypatch.delenv("ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK", raising=False)

    conn = {"tenant_id": "tenant-A", "hr_id": "hotel-A"}

    async def _fake_lookup(tenant_hint, hr_id_hint):
        return conn

    async def _fake_load(c):
        return None  # no per-property secret configured

    monkeypatch.setattr(hw, "_lookup_signing_connection", _fake_lookup)
    monkeypatch.setattr(hw, "_load_webhook_secret", _fake_load)

    raw = b'{"event":"new","hr_id":"hotel-A"}'
    ts = str(int(time.time()))
    headers = {
        "X-HotelRunner-Signature": f"sha256={_sign(secret, ts, raw)}",
        "X-HotelRunner-Timestamp": ts,
    }
    req = _FakeRequest(headers, raw)
    await _verify_hotelrunner_signature(req)
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

    async def _fake_lookup(tenant_hint, hr_id_hint):
        # Hint resolves to tenant-A (the victim).
        return {"tenant_id": "tenant-A", "hr_id": "hotel-A"}

    async def _fake_load(c):
        return secrets_by_tenant.get(c["tenant_id"])

    monkeypatch.setattr(hw, "_lookup_signing_connection", _fake_lookup)
    monkeypatch.setattr(hw, "_load_webhook_secret", _fake_load)

    raw = b'{"event":"new","hr_id":"hotel-A","tenant_id":"tenant-A"}'
    ts = str(int(time.time()))
    # Signed with tenant-B's secret — must be rejected against A's secret.
    headers = {
        "X-HotelRunner-Signature": f"sha256={_sign(secrets_by_tenant['tenant-B'], ts, raw)}",
        "X-HotelRunner-Timestamp": ts,
    }
    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_signature(_FakeRequest(headers, raw))
    assert ei.value.status_code == 401
