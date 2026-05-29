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

import pytest
from fastapi import HTTPException

from domains.channel_manager.providers.hotelrunner_webhook import (
    _verify_hotelrunner_signature,
)


class _FakeRequest:
    def __init__(self, headers=None, body=b"{}"):
        self.headers = headers or {}
        self._body = body

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
