import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.channel_manager.providers.hotelrunner import router_connection
from domains.channel_manager.providers.hotelrunner.schemas import ProviderResult


class _Collections:
    def __init__(self) -> None:
        self.hotelrunner_connections = SimpleNamespace(find_one=AsyncMock(return_value={"environment": "production"}))
        self.provider_connections = SimpleNamespace(find_one=AsyncMock(return_value=None))


@pytest.mark.asyncio
async def test_connection_flattens_successful_provider_result(monkeypatch):
    provider = SimpleNamespace(
        test_connection=AsyncMock(
            return_value=ProviderResult(
                success=True,
                data={"connected": True, "channels": ["redacted"]},
                duration_ms=17,
            )
        )
    )
    monkeypatch.setattr(router_connection, "db", _Collections())
    monkeypatch.setattr(
        router_connection,
        "get_provider",
        AsyncMock(return_value=(provider, {"credentials_ref": "not-returned"})),
    )

    result = await router_connection.test_connection(current_user=SimpleNamespace(tenant_id="tenant-test"))

    assert result == {
        "success": True,
        "connected": True,
        "duration_ms": 17,
        "error": "",
        "error_type": "",
    }


@pytest.mark.asyncio
async def test_connection_failure_has_nonempty_safe_reason(monkeypatch):
    provider = SimpleNamespace(test_connection=AsyncMock(return_value=ProviderResult(success=False, error="", duration_ms=23)))
    monkeypatch.setattr(router_connection, "db", _Collections())
    monkeypatch.setattr(
        router_connection,
        "get_provider",
        AsyncMock(return_value=(provider, {})),
    )

    result = await router_connection.test_connection(current_user=SimpleNamespace(tenant_id="tenant-test"))

    assert result["success"] is False
    assert result["connected"] is False
    assert result["error"] == "ProviderConnectionError"
    assert "data" not in result


@pytest.mark.asyncio
async def test_callback_readiness_reports_official_auth_without_exposing_secrets(monkeypatch):
    credentials = {
        "token": "synthetic-provider-token",
        "hr_id": "hotel-123",
        "callback_secret": "synthetic-legacy-path-secret",
    }
    fake_db = SimpleNamespace(
        hotelrunner_connections=SimpleNamespace(
            find_one=AsyncMock(return_value={"hr_id": "hotel-123"})
        )
    )
    secrets_manager = SimpleNamespace(
        get_provider_credentials=AsyncMock(return_value=credentials)
    )
    monkeypatch.setattr(router_connection, "db", fake_db)
    monkeypatch.setattr(router_connection, "get_secrets_manager", lambda: secrets_manager)
    monkeypatch.setenv("PUBLIC_APP_URL", "https://pms.syroce.com/")
    monkeypatch.delenv("HOTELRUNNER_CALLBACK_SECRET", raising=False)

    result = await router_connection.get_callback_readiness(
        current_user=SimpleNamespace(tenant_id="tenant-test", name="Admin")
    )

    assert result == {
        "ready": True,
        "official_auth": "token_plus_hr_id",
        "callback_url": "https://pms.syroce.com/api/channel-manager/hotelrunner/callback",
        "credentials_configured": True,
        "legacy_path_secret_configured": True,
        "legacy_path_secret_blocks_official_url": False,
        "registration_requires_provider_confirmation": True,
        "blockers": [],
    }
    rendered = json.dumps(result)
    assert credentials["token"] not in rendered
    assert credentials["callback_secret"] not in rendered


@pytest.mark.asyncio
async def test_callback_readiness_fails_closed_when_encrypted_credentials_are_missing(monkeypatch):
    fake_db = SimpleNamespace(
        hotelrunner_connections=SimpleNamespace(
            find_one=AsyncMock(return_value={"hr_id": "hotel-123"})
        )
    )
    secrets_manager = SimpleNamespace(
        get_provider_credentials=AsyncMock(return_value=None)
    )
    monkeypatch.setattr(router_connection, "db", fake_db)
    monkeypatch.setattr(router_connection, "get_secrets_manager", lambda: secrets_manager)
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    monkeypatch.delenv("HOTELRUNNER_CALLBACK_SECRET", raising=False)

    result = await router_connection.get_callback_readiness(
        current_user=SimpleNamespace(tenant_id="tenant-test", name="Admin")
    )

    assert result["ready"] is False
    assert result["callback_url"] == "/api/channel-manager/hotelrunner/callback"
    assert result["blockers"] == ["HOTELRUNNER_ENCRYPTED_CREDENTIALS_MISSING"]
