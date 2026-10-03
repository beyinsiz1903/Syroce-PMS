"""Contracts for the WhatsApp setup surface.

These checks keep operator-visible setup state truthful while ensuring that
saved Meta credentials never travel back to a browser.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.ai.router import whatsapp


class _Tenants:
    def __init__(self, tenant):
        self.tenant = tenant

    async def find_one(self, query):
        return self.tenant if query["id"] == self.tenant["id"] else None

    async def update_one(self, query, update):
        self.tenant.update(update["$set"])


def _run(coro):
    return asyncio.run(coro)


def test_get_config_never_returns_saved_credentials(monkeypatch):
    tenant = {
        "id": "tenant-1",
        "whatsapp_config": {"phone_number_id": "sender-1", "access_token": "secret-token", "verify_token": "secret-verify"},
    }
    monkeypatch.setattr(whatsapp, "db", SimpleNamespace(tenants=_Tenants(tenant)))

    result = _run(whatsapp.get_whatsapp_config(SimpleNamespace(tenant_id="tenant-1")))

    assert result["config"]["configured"] is True
    assert result["config"]["phone_number_id"] == "sender-1"
    assert "access_token" not in result["config"]
    assert "verify_token" not in result["config"]


def test_partial_save_preserves_existing_credentials(monkeypatch):
    tenant = {
        "id": "tenant-1",
        "whatsapp_config": {"phone_number_id": "sender-1", "access_token": "secret-token", "verify_token": "secret-verify"},
    }
    monkeypatch.setattr(whatsapp, "db", SimpleNamespace(tenants=_Tenants(tenant)))

    _run(
        whatsapp.save_whatsapp_config(
            whatsapp.WhatsAppConfig(phone_number_id="sender-2"), SimpleNamespace(tenant_id="tenant-1")
        )
    )

    assert tenant["whatsapp_config"] == {
        "phone_number_id": "sender-2",
        "access_token": "secret-token",
        "verify_token": "secret-verify",
    }


def test_oauth_without_server_credentials_fails_closed(monkeypatch):
    monkeypatch.delenv("FACEBOOK_APP_ID", raising=False)
    monkeypatch.delenv("FACEBOOK_APP_SECRET", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        _run(
            whatsapp.whatsapp_oauth_exchange(
                whatsapp.WhatsAppOAuthRequest(access_token="browser-token"), SimpleNamespace(tenant_id="tenant-1")
            )
        )

    assert exc_info.value.status_code == 503
