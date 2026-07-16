from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.config import NilveraSettings, get_nilvera_config
from core.integrations.nilvera.errors import (
    NilveraApiError,
    NilveraAuthError,
    NilveraBusinessRuleError,
    NilveraDuplicateError,
    NilveraNotFoundError,
    NilveraRateLimitError,
    NilveraResponseSizeError,
    NilveraServerError,
    NilveraValidationError,
)


@pytest.fixture
def mock_sleeper():
    return AsyncMock()


@pytest.fixture
def config_override(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_ENV", "test")
    monkeypatch.setenv("NILVERA_RETRY_MAX", "2")
    monkeypatch.setenv("NILVERA_RETRY_BASE_DELAY_MS", "1")
    yield
    mod._config = None


def get_mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://testserver")

# --- CONFIG TESTS ---

def test_config_selects_test_base_url():
    cfg = NilveraSettings(env="test")
    assert cfg.base_url == "https://apitest.nilvera.com"

def test_config_selects_production_base_url():
    cfg = NilveraSettings(env="production")
    assert cfg.base_url == "https://api.nilvera.com"

def test_config_rejects_invalid_environment():
    with pytest.raises(ValidationError):
        NilveraSettings(env="invalid")

def test_config_rejects_non_positive_timeout():
    with pytest.raises(ValidationError):
        NilveraSettings(timeout_ms=0)
    with pytest.raises(ValidationError):
        NilveraSettings(timeout_ms=-1)

def test_config_rejects_negative_retry_count():
    with pytest.raises(ValidationError):
        NilveraSettings(retry_max=-1)

def test_config_rejects_invalid_response_size():
    with pytest.raises(ValidationError):
        NilveraSettings(max_response_size_bytes=0)

def test_config_has_no_api_key_field():
    assert "api_key" not in NilveraSettings.model_fields

def test_config_import_is_lazy_and_does_not_require_env(monkeypatch):
    monkeypatch.delenv("NILVERA_ENV", raising=False)
    # The import should not fail and the object should be lazy
    assert get_nilvera_config().env == "test"

# --- ERROR REDACTION TESTS ---

def test_error_does_not_store_raw_headers():
    err = NilveraApiError("Test")
    assert not hasattr(err, "headers")

def test_error_does_not_store_raw_body_by_default():
    err = NilveraApiError("Test")
    assert not hasattr(err, "raw_response") or getattr(err, "raw_response", None) is None

def test_error_string_redacts_api_key():
    err = NilveraApiError(
        message="Test",
        raw_response={"Authorization": "Bearer super-secret", "api_key": "123"}
    )
    assert "super-secret" not in str(err)
    assert "123" not in str(err)
    assert err.sanitized_preview == "[REDACTED_POTENTIAL_SECRETS]"

def test_error_preview_is_bounded():
    long_string = "a" * 1000
    err = NilveraApiError(message="Test", raw_response=long_string)
    assert err.sanitized_preview is not None
    assert len(err.sanitized_preview) <= 512

# --- CONTENT-TYPE AND BODY TESTS ---

@pytest.mark.asyncio
async def test_pdf_accepts_application_pdf(config_override):
    def handler(request):
        return httpx.Response(200, content=b"%PDF-1.4", headers={"Content-Type": "application/pdf"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        res = await http_client.get_binary("/test", expected_content_types=["application/pdf"])
        assert res == b"%PDF-1.4"

@pytest.mark.asyncio
async def test_pdf_rejects_html_content_type(config_override):
    def handler(request):
        return httpx.Response(200, content=b"<html></html>", headers={"Content-Type": "text/html"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraValidationError):
            await http_client.get_binary("/test", expected_content_types=["application/pdf"])

@pytest.mark.asyncio
async def test_xml_accepts_application_xml(config_override):
    def handler(request):
        return httpx.Response(200, content=b"<xml></xml>", headers={"Content-Type": "application/xml"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        res = await http_client.get_binary("/test", expected_content_types=["application/xml", "text/xml"])
        assert res == b"<xml></xml>"

@pytest.mark.asyncio
async def test_xml_accepts_text_xml(config_override):
    def handler(request):
        return httpx.Response(200, content=b"<xml></xml>", headers={"Content-Type": "text/xml"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        res = await http_client.get_binary("/test", expected_content_types=["application/xml", "text/xml"])
        assert res == b"<xml></xml>"

@pytest.mark.asyncio
async def test_xml_rejects_json_content_type(config_override):
    def handler(request):
        return httpx.Response(200, content=b'{"xml": false}', headers={"Content-Type": "application/json"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraValidationError):
            await http_client.get_binary("/test", expected_content_types=["application/xml"])

@pytest.mark.asyncio
async def test_empty_binary_response_rejected(config_override):
    def handler(request):
        return httpx.Response(200, content=b"", headers={"Content-Type": "application/pdf"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraValidationError):
            await http_client.get_binary("/test", expected_content_types=["application/pdf"])

@pytest.mark.asyncio
async def test_malformed_json_returns_typed_error(config_override):
    def handler(request):
        return httpx.Response(200, content=b"invalid{json", headers={"Content-Type": "application/json"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraApiError):
            await http_client.get("/test")

@pytest.mark.asyncio
async def test_json_endpoint_rejects_html_success_response(config_override):
    def handler(request):
        return httpx.Response(200, content=b"<html>ok</html>", headers={"Content-Type": "text/html"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraValidationError):
            await http_client.get("/test")

@pytest.mark.asyncio
async def test_oversized_content_length_rejected(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_MAX_RESPONSE_SIZE_BYTES", "100")
    def handler(request):
        return httpx.Response(200, headers={"Content-Length": "200"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraResponseSizeError):
            await http_client.get("/test")

@pytest.mark.asyncio
async def test_oversized_actual_body_rejected(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_MAX_RESPONSE_SIZE_BYTES", "10")
    def handler(request):
        return httpx.Response(200, content=b"12345678901234567890")
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraResponseSizeError):
            await http_client.get("/test")

# --- RETRY MATRIX TESTS ---

@pytest.mark.parametrize("status_code,exc_class", [
    (400, NilveraValidationError),
    (401, NilveraAuthError),
    (403, NilveraAuthError),
    (404, NilveraNotFoundError),
    (409, NilveraDuplicateError),
    (422, NilveraBusinessRuleError),
])
@pytest.mark.asyncio
async def test_no_retry_for_client_errors(config_override, mock_sleeper, status_code, exc_class):
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, json={"Message": "Error"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(exc_class):
            await http_client.get("/test", _sleeper=mock_sleeper)
        assert calls == 1

@pytest.mark.parametrize("status_code", [502, 503, 504])
@pytest.mark.asyncio
async def test_get_5xx_retries(config_override, mock_sleeper, status_code):
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(status_code, json={"Message": "Error"})
        return httpx.Response(200, json={"ok": True}, headers={"Content-Type": "application/json"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        await http_client.get("/test", _sleeper=mock_sleeper)
        assert calls == 3

@pytest.mark.parametrize("status_code,method_name", [
    (502, "post"),
    (503, "post"),
    (504, "put"),
])
@pytest.mark.asyncio
async def test_mutation_no_retry_by_default(config_override, mock_sleeper, status_code, method_name):
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, json={"Message": "Error"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        method = getattr(http_client, method_name)
        with pytest.raises(NilveraServerError):
            await method("/test", json={"data": 1}, _sleeper=mock_sleeper)
        assert calls == 1

@pytest.mark.asyncio
async def test_get_429_honors_bounded_retry_after(config_override, mock_sleeper):
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "5"})
        return httpx.Response(200, json={"ok": True}, headers={"Content-Type": "application/json"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        await http_client.get("/test", _sleeper=mock_sleeper)
        mock_sleeper.assert_called_once_with(5.0)

@pytest.mark.asyncio
async def test_post_429_no_retry_by_default(config_override, mock_sleeper):
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "5"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraRateLimitError):
            await http_client.post("/test", json={}, _sleeper=mock_sleeper)
        assert calls == 1

@pytest.mark.asyncio
async def test_invalid_retry_after_does_not_crash(config_override, mock_sleeper):
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "invalid-date"})
        return httpx.Response(200, json={"ok": True}, headers={"Content-Type": "application/json"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        await http_client.get("/test", _sleeper=mock_sleeper)
        mock_sleeper.assert_called_once()
        assert calls == 2

@pytest.mark.asyncio
async def test_retry_max_zero_performs_single_attempt(monkeypatch, mock_sleeper):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_RETRY_MAX", "0")
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(502)
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraServerError):
            await http_client.get("/test", _sleeper=mock_sleeper)
        assert calls == 1

# --- CLIENT LIFECYCLE TESTS ---

@pytest.mark.asyncio
async def test_internally_created_client_closes():
    async with NilveraHttpClient("key") as http_client:
        assert http_client._owned_client is not None
        assert not http_client._owned_client.is_closed
        client_ref = http_client._owned_client
    assert client_ref.is_closed

@pytest.mark.asyncio
async def test_externally_injected_client_is_not_closed():
    client = httpx.AsyncClient(base_url="https://testserver")
    async with NilveraHttpClient("key", client=client) as http_client:
        assert http_client._injected_client is not None
        assert not http_client._injected_client.is_closed
    # Should remain open
    assert not client.is_closed
    await client.aclose()

@pytest.mark.asyncio
async def test_request_after_close_gives_error():
    http_client = NilveraHttpClient("key")
    async with http_client:
        pass
    with pytest.raises(RuntimeError):
        await http_client.get("/test")

@pytest.mark.asyncio
async def test_base_url_path_joining_does_not_double_slash():
    request_url = ""
    def handler(request):
        nonlocal request_url
        request_url = str(request.url)
        return httpx.Response(200, json={"ok": True}, headers={"Content-Type": "application/json"})

    # Notice base_url has trailing slash
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://testserver/")
    async with NilveraHttpClient("key", client=client) as http_client:
        # User provides leading slash
        await http_client.get("/api/test")

    assert request_url == "https://testserver/api/test"

def test_api_key_does_not_appear_in_repr():
    client = NilveraHttpClient("secret_key_999")
    assert "secret_key_999" not in repr(client)
