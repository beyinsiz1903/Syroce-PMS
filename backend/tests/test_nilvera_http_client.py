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

def test_loader_defaults_to_test_when_env_missing(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.delenv("NILVERA_ENV", raising=False)
    assert get_nilvera_config().env == "test"

def test_loader_accepts_test(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_ENV", "TeSt ")
    assert get_nilvera_config().env == "test"

def test_loader_accepts_production(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_ENV", " PRODUCTION")
    assert get_nilvera_config().env == "production"

def test_loader_rejects_invalid_environment(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_ENV", "invalid")
    with pytest.raises(ValidationError):
        get_nilvera_config()

def test_loader_rejects_typo_in_production_environment(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_ENV", "prodution")
    with pytest.raises(ValidationError):
        get_nilvera_config()

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

# --- NEW EDGE CASE TESTS ---

def test_error_repr_does_not_expose_detail():
    err = NilveraApiError("Test", detail="SECRET_DETAIL_123")
    r = repr(err)
    assert "SECRET_DETAIL_123" not in r

def test_error_str_does_not_expose_description():
    err = NilveraApiError("Test", description="SECRET_DESC_456")
    s = str(err)
    assert "SECRET_DESC_456" not in s

def test_error_preview_redacts_authorization_case_insensitive():
    err = NilveraApiError("Test", raw_response={"aUtHoRiZaTiOn": "Bearer secret", "safe_key": "val"})
    assert err.sanitized_preview == '{"safe_key": "val"}'

def test_error_preview_redacts_vkn_tckn_like_values():
    err = NilveraApiError("Test", raw_response='{"vkn": "1234567890", "tckn":"12345678901", "other": "1"}')
    preview = err.sanitized_preview
    assert "1234567890" not in preview
    assert "12345678901" not in preview
    assert "[REDACTED]" in preview

@pytest.mark.asyncio
async def test_problem_json_is_accepted(config_override):
    def handler(request):
        return httpx.Response(200, content=b'{"ok": true}', headers={"Content-Type": "application/problem+json"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        res = await http_client.get("/test")
        assert res == {"ok": True}

@pytest.mark.asyncio
async def test_vendor_json_is_accepted(config_override):
    def handler(request):
        return httpx.Response(200, content=b'{"ok": true}', headers={"Content-Type": "application/vnd.api+json"})
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        res = await http_client.get("/test")
        assert res == {"ok": True}

@pytest.mark.asyncio
async def test_oversized_error_body_without_content_length_rejected(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_MAX_RESPONSE_SIZE_BYTES", "10")

    def handler(request):
        # No content length, large body
        return httpx.Response(500, content=b"12345678901234567890")

    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraResponseSizeError):
            await http_client.get("/test", retryable=False)

@pytest.mark.asyncio
async def test_oversized_error_content_length_rejected_before_full_read(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_MAX_RESPONSE_SIZE_BYTES", "10")

    def handler(request):
        # Has content length exceeding limit
        return httpx.Response(500, headers={"Content-Length": "200"}, content=b"fake")

    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraResponseSizeError):
            await http_client.get("/test", retryable=False)

@pytest.mark.asyncio
async def test_small_json_error_is_parsed(config_override):
    def handler(request):
        return httpx.Response(400, headers={"Content-Type": "application/json"}, content=b'{"Message": "Bad"}')
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraValidationError) as exc:
            await http_client.get("/test")
        assert "Bad" in exc.value.sanitized_preview
        assert exc.value.args == ("E-Belge entegratörü ile iletişimde bir sorun oluştu.",)

@pytest.mark.asyncio
async def test_small_html_error_returns_safe_typed_error(config_override):
    def handler(request):
        return httpx.Response(502, headers={"Content-Type": "text/html"}, content=b'<html>bad gateway</html>')
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraServerError) as exc:
            await http_client.get("/test", retryable=False)
        assert exc.value.http_status == 502

@pytest.mark.asyncio
async def test_error_response_is_closed_after_size_rejection(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_MAX_RESPONSE_SIZE_BYTES", "5")

    response_closed = False
    class CustomTransport(httpx.MockTransport):
        async def handle_async_request(self, request):
            res = httpx.Response(500, content=b"1234567890")
            original_aclose = res.aclose
            async def mock_aclose():
                nonlocal response_closed
                response_closed = True
                await original_aclose()
            res.aclose = mock_aclose
            return res

    async with NilveraHttpClient("key", client=httpx.AsyncClient(transport=CustomTransport(lambda req: None), base_url="https://test")) as http_client:
        with pytest.raises(NilveraResponseSizeError):
            await http_client.get("/test", retryable=False)

    assert response_closed

@pytest.mark.asyncio
async def test_retry_max_3_performs_4_attempts(monkeypatch, mock_sleeper):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_RETRY_MAX", "3")

    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(502)

    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraServerError):
            await http_client.get("/test", _sleeper=mock_sleeper)
        assert calls == 4

# --- NEW REDACTION AND SECURITY TESTS ---

def test_provider_message_not_used_as_exception_message():
    err = NilveraApiError(message="Nilvera provider request failed", raw_response={"Message": "SECRET_MSG"})
    assert str(err).startswith("Nilvera provider request failed")
    assert "SECRET_MSG" not in str(err)
    assert "SECRET_MSG" not in err.args

def test_provider_message_vkn_is_redacted():
    err = NilveraApiError("Test", raw_response={"Message": "VKN 12345678901"})
    assert "12345678901" not in err.sanitized_preview

def test_provider_message_tckn_is_redacted():
    err = NilveraApiError("Test", raw_response={"Message": "TCKN 12345678901"})
    assert "12345678901" not in err.sanitized_preview

def test_provider_message_email_is_redacted():
    err = NilveraApiError("Test", raw_response={"Message": "Contact test@example.com"})
    assert "test@example.com" not in err.sanitized_preview
    assert "[REDACTED_EMAIL]" in err.sanitized_preview

def test_provider_message_bearer_token_is_redacted():
    err = NilveraApiError("Test", raw_response={"Message": "Bearer abcdef123456"})
    assert "abcdef123456" not in err.sanitized_preview
    assert "[REDACTED_POTENTIAL_SECRETS]" in err.sanitized_preview

def test_description_and_detail_are_not_raw():
    err = NilveraApiError("Test", description="Desc with 12345678901", detail="Detail with user@example.com")
    assert not hasattr(err, "description")
    assert not hasattr(err, "detail")
    assert err.sanitized_description is not None
    assert err.sanitized_detail is not None
    assert "12345678901" not in err.sanitized_description
    assert "user@example.com" not in err.sanitized_detail

def test_str_never_contains_provider_message():
    err = NilveraApiError("Test", raw_response={"Message": "SECRET_PROVIDER_MESSAGE"})
    assert "SECRET_PROVIDER_MESSAGE" not in str(err)

def test_repr_never_contains_provider_message():
    err = NilveraApiError("Test", raw_response={"Message": "SECRET_PROVIDER_MESSAGE"})
    assert "SECRET_PROVIDER_MESSAGE" not in repr(err)

def test_exception_args_contain_only_safe_static_message():
    err = NilveraApiError("Nilvera provider request failed", raw_response={"Message": "SECRET"})
    assert err.args == ("E-Belge entegratörü ile iletişimde bir sorun oluştu.",)

@pytest.mark.asyncio
async def test_client_parses_safe_message_for_exception(config_override):
    def handler(request):
        return httpx.Response(400, headers={"Content-Type": "application/json"}, content=b'{"Message": "SECRET_PROVIDER_MESSAGE"}')
    async with NilveraHttpClient("key", client=get_mock_client(handler)) as http_client:
        with pytest.raises(NilveraValidationError) as exc:
            await http_client.get("/test")
        assert "SECRET_PROVIDER_MESSAGE" not in str(exc.value)
        assert exc.value.args == ("E-Belge entegratörü ile iletişimde bir sorun oluştu.",)

# --- EGRESS ALLOWLIST & RESTRICTION TESTS ---

def test_config_rejects_arbitrary_base_url(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_BASE_URL", "https://hacker.com")
    cfg = get_nilvera_config()
    assert cfg.base_url == "https://apitest.nilvera.com"

def test_config_rejects_http_base_url(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_BASE_URL", "http://api.nilvera.com")
    cfg = get_nilvera_config()
    assert cfg.base_url.startswith("https://")

def test_config_rejects_localhost(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_BASE_URL", "http://localhost:8080")
    cfg = get_nilvera_config()
    assert "localhost" not in cfg.base_url

def test_config_rejects_ip_literal(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_BASE_URL", "https://127.0.0.1")
    cfg = get_nilvera_config()
    assert "127.0.0.1" not in cfg.base_url

def test_config_rejects_embedded_credentials(monkeypatch):
    import core.integrations.nilvera.config as mod
    mod._config = None
    monkeypatch.setenv("NILVERA_BASE_URL", "https://user:pass@api.nilvera.com")
    cfg = get_nilvera_config()
    assert "user:pass" not in cfg.base_url

def test_config_only_uses_official_nilvera_hosts():
    import core.integrations.nilvera.config as mod
    cfg_test = mod.NilveraSettings(env="test")
    cfg_prod = mod.NilveraSettings(env="production")

    assert cfg_test.base_url == "https://apitest.nilvera.com"
    assert cfg_prod.base_url == "https://api.nilvera.com"
    assert not hasattr(cfg_test, "base_url_override")
