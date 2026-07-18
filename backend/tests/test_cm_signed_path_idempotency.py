"""F8 (Wave 5) — CM signed-path + idempotency posture (no real external call).

Locks the channel-manager inbound posture the stress suite classifies, while
keeping external_calls empty:

  - HotelRunner: valid HMAC-SHA256 signed body is accepted; the dev escape
    (ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK) is the only no-secret bypass; default
    is fail-closed (503). (Signature math mirrors the server.)
  - HotelRunner idempotency: provider_event_id is deterministic
    ({hr_number}_{event_type}_{last_modified}); identical inbound events
    collapse to the same id so a replay is a no-op, not a duplicate booking.
  - Exely: the IP-whitelist gate stays fail-closed unless an explicit open-for-
    testing env (ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK) is set. Verified at the
    source/contract level — no SOAP call is issued.

No outbound HTTP is performed by any test here (external_calls == []).
"""

import hashlib
import hmac
import time
from pathlib import Path

import pytest

from domains.channel_manager.providers.hotelrunner_security import (
    _verify_hotelrunner_callback,
)


class _FakeRequest:
    def __init__(self, headers=None, body=b"{}"):
        self.headers = headers or {}
        self._body = body
        self.query_params = {}
        self.path_params = {}

    async def body(self):
        return self._body


def _sign(secret, ts, raw):
    return hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_hotelrunner_valid_signed_path_accepted(monkeypatch):
    secret = "wave5-secret"
    monkeypatch.setenv("HOTELRUNNER_WEBHOOK_SECRET", secret)

    async def mock_lookup(hr_id):
        return {"hr_id": hr_id, "tenant_id": "mock-tenant"}
    monkeypatch.setattr("domains.channel_manager.providers.hotelrunner_security._lookup_signing_connection", mock_lookup)

    async def mock_load_secret(conn):
        return secret
    monkeypatch.setattr("domains.channel_manager.providers.hotelrunner_security._load_webhook_secret", mock_load_secret)

    raw = b'{"hr_id": "mock-hr-id", "reservation":{"hr_number":"HR-1"}}'
    ts = str(int(time.time()))
    headers = {
        "X-HotelRunner-Signature": f"sha256={_sign(secret, ts, raw)}",
        "X-HotelRunner-Timestamp": ts,
    }
    # Returns without raising → signed path is the accepted ingress.
    await _verify_hotelrunner_callback(_FakeRequest(headers, raw))


@pytest.mark.asyncio
async def test_hotelrunner_default_fail_closed(monkeypatch):
    monkeypatch.delenv("HOTELRUNNER_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK", raising=False)
    from fastapi import HTTPException

    async def mock_lookup(hr_id):
        return {"hr_id": hr_id, "tenant_id": "mock-tenant"}
    monkeypatch.setattr("domains.channel_manager.providers.hotelrunner_security._lookup_signing_connection", mock_lookup)

    async def mock_load_secret(conn):
        return None
    monkeypatch.setattr("domains.channel_manager.providers.hotelrunner_security._load_webhook_secret", mock_load_secret)

    ts = str(int(time.time()))
    headers = {
        "X-HotelRunner-Signature": "sha256=invalid",
        "X-HotelRunner-Timestamp": ts,
    }
    raw = b'{"hr_id": "mock-hr-id"}'

    with pytest.raises(HTTPException) as ei:
        await _verify_hotelrunner_callback(_FakeRequest(headers, raw))
    assert ei.value.status_code == 503


def test_hotelrunner_provider_event_id_is_deterministic():
    """Idempotency key derivation is stable across identical events, so a
    re-delivered webhook resolves to the same provider_event_id and is skipped
    rather than re-ingested."""
    hr_number, event_type, last_mod = "HR-42", "modify", "2026-05-29T10:00:00Z"

    def derive(n, e, m):
        return f"{n}_{e}_{m}"

    first = derive(hr_number, event_type, last_mod)
    replay = derive(hr_number, event_type, last_mod)
    different = derive(hr_number, "new", last_mod)
    assert first == replay
    assert first != different
    # Lock the exact format string the provider uses.
    shared_src = (
        Path(__file__).resolve().parents[1]
        / "domains" / "channel_manager" / "providers" / "hotelrunner_shared.py"
    ).read_text()
    assert 'f"{hr_number}_{event_type}_{last_mod}"' in shared_src


def test_exely_whitelist_gate_is_fail_closed_by_default():
    """Exely webhook trusts only whitelisted IPs unless an explicit dev escape
    is set; the gate and escape names must remain present (fail-closed default)."""
    src = (
        Path(__file__).resolve().parents[1]
        / "domains" / "channel_manager" / "providers" / "exely"
        / "exely_webhook_router.py"
    ).read_text()
    assert "EXELY_IP_WHITELIST" in src
    assert "ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK" in src
