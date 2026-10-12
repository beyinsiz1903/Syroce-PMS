"""Health diagnostics must be actionable without reflecting provider secrets."""
from unittest.mock import AsyncMock

import httpx
import pytest

from modules.messaging.providers import ProviderMode, WhatsAppProvider

CREDS = {"access_token": "private-token", "phone_number_id": "123"}


@pytest.fixture
def mock_get(monkeypatch):
    get = AsyncMock()
    client = AsyncMock()
    client.get = get
    client.__aenter__.return_value = client
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    return get


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code,expected", [
    (400, 190, "Erişim anahtarı"),
    (403, 10, "Erişim izni"),
    (400, 100, "Telefon numarası"),
    (429, 130429, "istek sınırına"),
    (503, 2, "geçici hata"),
    (400, 999, "isteğini reddetti"),
])
async def test_meta_errors_are_safe_and_actionable(mock_get, status, code, expected):
    mock_get.return_value = httpx.Response(status, json={"error": {
        "message": "private-token confidential", "code": code, "error_subcode": 463,
        "error_data": {"details": "private-token"},
    }})
    result = await WhatsAppProvider().check_health(CREDS)
    assert result["status"] == "unhealthy"
    assert expected in result["error"]
    assert f"HTTP {status}" in result["error"]
    assert result["meta_code"] == code
    assert result["meta_subcode"] == 463
    assert "private-token" not in str(result)
    assert "confidential" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [[], None, {"error": "private-token"},
    {"error": {"code": "private-token", "error_subcode": "private-token"}},
    {"error": {"code": True, "error_subcode": -1}},
])
async def test_malformed_response_does_not_leak_or_crash(mock_get, body):
    mock_get.return_value = httpx.Response(400, json=body)
    result = await WhatsAppProvider().check_health(CREDS)
    assert result["status"] == "unhealthy"
    assert result["meta_code"] is None
    assert result["meta_subcode"] is None
    assert "private-token" not in str(result)


@pytest.mark.asyncio
async def test_html_error_is_not_reflected(mock_get):
    mock_get.return_value = httpx.Response(502, text="<html>private-token</html>")
    result = await WhatsAppProvider().check_health(CREDS)
    assert "HTTP 502" in result["error"]
    assert "private-token" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("exception,expected", [
    (httpx.ConnectError("private-token"), "bağlantı kurulamadı"),
    (httpx.ReadTimeout("private-token"), "zaman aşımına"),
    (RuntimeError("private-token"), "tamamlanamadı"),
])
async def test_network_errors_do_not_leak(mock_get, exception, expected):
    mock_get.side_effect = exception
    result = await WhatsAppProvider().check_health(CREDS)
    assert result["status"] == "unhealthy"
    assert expected in result["error"]
    assert "private-token" not in str(result)


@pytest.mark.asyncio
async def test_success(mock_get):
    mock_get.return_value = httpx.Response(200, json={"id": "123"})
    result = await WhatsAppProvider().check_health(CREDS)
    assert result["status"] == "healthy"
    assert "error" not in result
    mock_get.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ProviderMode.SANDBOX, ProviderMode.TEST])
async def test_simulation_makes_no_network_call(mock_get, mode):
    assert (await WhatsAppProvider().check_health({}, mode))["status"] == "healthy"
    mock_get.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_credentials_make_no_network_call(mock_get):
    assert (await WhatsAppProvider().check_health({}))["status"] == "unhealthy"
    mock_get.assert_not_awaited()
