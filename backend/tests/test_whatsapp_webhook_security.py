"""Security contracts for the public Meta WhatsApp webhook."""

from __future__ import annotations

import hashlib
import hmac
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import whatsapp_webhook as webhook


def test_webhook_keeps_both_secure_callback_paths():
    paths = {route.path for route in webhook.router.routes}
    assert "/api/messaging-center/whatsapp/webhook" in paths
    assert "/api/whatsapp/webhook" in paths


def test_meta_signature_requires_exact_prefix_digest_and_secret():
    body = b'{"object":"whatsapp_business_account"}'
    secret = "app-secret"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert webhook._verify_signature(body, f"sha256={digest}", secret)
    assert not webhook._verify_signature(body, digest, secret)
    assert not webhook._verify_signature(body, "sha256=" + "0" * 64, secret)
    assert not webhook._verify_signature(body, f"sha256={digest}", "")


class _Cursor:
    def __init__(self, values):
        self.values = values

    def __aiter__(self):
        async def rows():
            for value in self.values:
                yield value
        return rows()

    async def to_list(self, _limit):
        return self.values


class _Configs:
    def __init__(self, values):
        self.values = values

    def find(self, *_args, **_kwargs):
        return _Cursor(self.values)


@pytest.mark.asyncio
async def test_verify_token_is_compared_after_credentials_are_decrypted(monkeypatch):
    config = {
        "tenant_id": "tenant-1",
        "credentials_encrypted": {"webhook_verify_token": "ciphertext"},
    }
    monkeypatch.setattr(webhook, "_get_db", lambda: SimpleNamespace(messaging_provider_configs=_Configs([config])))

    import modules.messaging.service as messaging_service

    monkeypatch.setattr(
        messaging_service,
        "_decrypt_provider_creds",
        lambda _creds, _provider: {"webhook_verify_token": "actual-secret"},
    )

    response = await webhook.verify_webhook("subscribe", "challenge", "actual-secret")
    assert response.body == b"challenge"

    with pytest.raises(HTTPException) as exc:
        await webhook.verify_webhook("subscribe", "challenge", "wrong-secret")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_invalid_signature_rejected_before_any_write(monkeypatch):
    from unittest.mock import AsyncMock
    payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "phone"}}}]}]}
    request = SimpleNamespace(body=AsyncMock(return_value=b"raw"), json=AsyncMock(return_value=payload), headers={})
    monkeypatch.setattr(webhook, "_find_config_by_phone_id", AsyncMock(return_value={"tenant_id": "tenant"}))
    monkeypatch.setattr(webhook, "_credentials", lambda _: {"app_secret": "secret"})
    monkeypatch.setattr(webhook, "_get_db", lambda: None)
    with pytest.raises(HTTPException) as exc:
        await webhook.receive_webhook(request)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_webhook_retries_bridge_without_overwriting_optout(monkeypatch):
    import json
    from unittest.mock import AsyncMock
    message = {"id": "wamid", "from": "905551234567", "timestamp": "1700000000", "type": "text", "text": {"body": "hello"}}
    payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "phone"}, "messages": [message]}}]}]}
    raw = json.dumps(payload).encode()
    request = SimpleNamespace(body=AsyncMock(return_value=raw), json=AsyncMock(return_value=payload),
                              headers={"x-hub-signature-256": "sha256=" + hmac.new(b"secret", raw, hashlib.sha256).hexdigest()})
    db = SimpleNamespace(
        wa_inbound_messages=SimpleNamespace(update_one=AsyncMock(return_value=SimpleNamespace(upserted_id=None))),
        messaging_consents=SimpleNamespace(update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1))),
    )
    bridge = AsyncMock(side_effect=[RuntimeError("temporary outage"), None])
    monkeypatch.setattr(webhook, "_find_config_by_phone_id", AsyncMock(return_value={"tenant_id": "tenant"}))
    monkeypatch.setattr(webhook, "_credentials", lambda _: {"app_secret": "secret"})
    monkeypatch.setattr(webhook, "_get_db", lambda: db)
    monkeypatch.setattr(webhook, "ingest_whatsapp_inbound", bridge)
    with pytest.raises(HTTPException) as exc:
        await webhook.receive_webhook(request)
    assert exc.value.status_code == 503
    await webhook.receive_webhook(request)
    assert bridge.await_count == 2
    update = db.messaging_consents.update_one.call_args.args[1]
    assert "status" not in update["$set"]
    assert "source" not in update["$set"]
    assert update["$max"]["last_inbound_at"].startswith("2023-")
