"""Security contracts for the public Meta WhatsApp webhook."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import whatsapp_webhook as webhook


def test_webhook_route_replaces_the_legacy_messaging_center_path():
    paths = {route.path for route in webhook.router.routes}
    assert "/api/messaging-center/whatsapp/webhook" in paths
    assert "/api/whatsapp/webhook" not in paths


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
