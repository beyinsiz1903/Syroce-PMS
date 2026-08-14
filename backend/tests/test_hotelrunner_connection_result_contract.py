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
