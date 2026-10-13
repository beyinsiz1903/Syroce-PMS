from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from modules.messaging import zoho_mail
from modules.messaging.providers import SMTPEmailProvider


@pytest.fixture
def creds():
    zoho_mail._tokens.clear()
    return {"email_transport": "zoho_api", "zoho_region": "eu", "zoho_account_id": "123",
            "zoho_client_id": "client", "zoho_client_secret": "secret", "zoho_refresh_token": "refresh",
            "from_email": "info@example.com"}


def mock_api(monkeypatch, handler):
    async def safe_request(method, url, **kwargs):
        request = httpx.Request(method, url, headers=kwargs.get("headers"), content=kwargs.get("content"),
                                data=kwargs.get("data"), json=kwargs.get("json"))
        return handler(request)

    monkeypatch.setattr(zoho_mail, "safe_request_async", safe_request)


def preflight(request):
    if request.url.path.endswith("/token"):
        assert b"refresh_token=refresh" in request.content
        return httpx.Response(200, json={"access_token": "access", "expires_in": 3600})
    if request.url.path.endswith("/accounts"):
        assert request.headers["Authorization"] == "Zoho-oauthtoken access"
        return httpx.Response(200, json={"status": {"code": 200}, "data": [{
            "accountId": "123", "emailAddress": [{"mailId": "info@example.com", "isConfirmed": True}],
        }]})


@pytest.mark.asyncio
async def test_send_uses_https_and_cache(monkeypatch, creds):
    requests = []

    def handler(req):
        requests.append(req)
        assert req.url.scheme == "https"
        response = preflight(req)
        if response is not None:
            return response
        assert req.url.host == "mail.zoho.eu"
        assert req.url.path == "/api/accounts/123/messages"
        assert b'"fromAddress":"info@example.com"' in req.content
        return httpx.Response(200, json={"status": {"code": 200}, "data": {"messageId": "sent-1"}})

    mock_api(monkeypatch, handler)
    provider = SMTPEmailProvider()
    for _ in range(2):
        result = await provider.send("recipient@example.com", "test", "subject", creds)
        assert result["success"] and result["provider_message_id"] == "sent-1"
    assert sum(r.url.path.endswith("/token") for r in requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["timeout", "server_error", "malformed", "missing_id"])
async def test_uncertain_submission_is_never_retried(monkeypatch, creds, kind):
    def handler(req):
        response = preflight(req)
        if response is not None:
            return response
        if kind == "timeout":
            raise httpx.ReadTimeout("private response")
        if kind == "malformed":
            return httpx.Response(200, json=[])
        return httpx.Response(503 if kind == "server_error" else 200, json={})

    mock_api(monkeypatch, handler)
    result = await zoho_mail.send("recipient@example.com", "test", None, creds)
    assert result["outcome_unknown"] and not result["success"]
    assert "private response" not in str(result)


@pytest.mark.asyncio
async def test_account_mismatch_prevents_send(monkeypatch, creds):
    requests = []

    def handler(req):
        requests.append(req)
        return preflight(req)

    mock_api(monkeypatch, handler)
    creds["from_email"] = "other@example.com"
    result = await zoho_mail.send("recipient@example.com", "test", None, creds)
    assert not result["success"] and not result["outcome_unknown"]
    assert not any(r.url.path.endswith("/messages") for r in requests)


@pytest.mark.asyncio
async def test_health_is_read_only_and_sandbox_never_calls_network(monkeypatch, creds):
    mock_api(monkeypatch, preflight)
    assert (await zoho_mail.check_health(creds))["status"] == "healthy"
    monkeypatch.setattr(zoho_mail, "safe_request_async", MagicMock(side_effect=AssertionError("network forbidden")))
    result = await SMTPEmailProvider().send("recipient@example.com", "test", credentials=creds, mode="sandbox")
    assert result["success"] and result["mode"] == "sandbox"


@pytest.mark.parametrize("key,value", [("zoho_region", "evil.test"), ("zoho_account_id", "../other"), ("zoho_refresh_token", "")])
def test_invalid_credentials(creds, key, value):
    creds[key] = value
    with pytest.raises(ValueError):
        zoho_mail.validate_credentials(creds)


@pytest.mark.asyncio
async def test_retry_persists_unknown_without_next_retry(monkeypatch):
    from modules.messaging.service import MessagingService

    db = MagicMock()
    db.messaging_delivery_logs.find_one = AsyncMock(return_value={
        "id": "delivery", "tenant_id": "tenant", "provider_type": "smtp_email", "status": "failed",
        "body": "test", "recipient": "recipient@example.com", "channel": "email",
    })
    db.messaging_delivery_logs.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    service = MessagingService(db)
    service._get_provider_config = AsyncMock(return_value={"is_sandbox": False})
    service._load_credentials = AsyncMock(return_value={})
    service._check_consent = AsyncMock(return_value=True)
    monkeypatch.setattr(SMTPEmailProvider, "send", AsyncMock(return_value={"success": False, "outcome_unknown": True}))
    assert (await service.retry_failed("tenant", "delivery"))["outcome_unknown"]
    update = db.messaging_delivery_logs.update_one.call_args.args[1]["$set"]
    assert update["status"] == "unknown" and update["next_retry_at"] is None


@pytest.mark.asyncio
async def test_settings_switch_is_sandbox_and_preserves_secrets(monkeypatch, creds):
    from types import SimpleNamespace

    from routers import messaging

    db = MagicMock()
    db.messaging_provider_configs.find_one = AsyncMock(return_value={
        "id": "config", "credentials_encrypted": {"smtp_username": "existing@example.com"},
    })
    db.messaging_provider_configs.update_one = AsyncMock()
    monkeypatch.setattr(messaging, "_get_db", lambda: db)
    encryption = MagicMock()
    encryption.encrypt_value.side_effect = lambda value: "sealed:" + value
    encryption.decrypt_value.side_effect = lambda value: value.removeprefix("sealed:")
    monkeypatch.setattr(messaging, "get_field_encryption_service", lambda: encryption)
    request = messaging.SMTPSettingsReq(**creds, is_sandbox=False)
    await messaging.save_email_settings(request, SimpleNamespace(tenant_id="tenant"), None)
    query, update = db.messaging_provider_configs.update_one.call_args.args
    assert query["tenant_id"] == "tenant"
    assert update["$set"]["is_sandbox"] is True
    stored = update["$set"]["credentials_encrypted"]
    assert stored["zoho_refresh_token"] == "sealed:refresh"
    assert stored["smtp_username"] == "existing@example.com"
    db.messaging_provider_configs.find_one.return_value = {"id": "config", "credentials_encrypted": stored}
    request.zoho_refresh_token = ""
    request.zoho_client_secret = "********"
    await messaging.save_email_settings(request, SimpleNamespace(tenant_id="tenant"), None)
    stored_again = db.messaging_provider_configs.update_one.call_args.args[1]["$set"]
    assert stored_again["credentials_encrypted"]["zoho_refresh_token"] == "sealed:refresh"
    assert stored_again["credentials_encrypted"]["zoho_client_secret"] == "sealed:secret"
    assert stored_again["is_sandbox"] is False


def test_zoho_encryption_fails_closed(monkeypatch, creds):
    from fastapi import HTTPException

    from routers import messaging

    monkeypatch.setattr(messaging, "get_field_encryption_service", MagicMock(side_effect=RuntimeError("unavailable")))
    with pytest.raises(HTTPException) as exc:
        messaging._encrypt_secrets(creds, messaging._SMTP_SECRET_KEYS)
    assert exc.value.status_code == 503
