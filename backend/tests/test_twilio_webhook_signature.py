import base64
import hashlib
import hmac

from fastapi import Request

from domains.contact_center.voice_provider import TwilioVoiceProvider
from domains.contact_center.voice_router import _public_url


def calculate_signature(token: str, url: str, params: dict) -> str:
    data = url
    for k in sorted(params.keys()):
        data += k + params[k]
    mac = hmac.new(token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode("utf-8")

def _make_mock_request(url_str: str, headers_dict: dict) -> Request:
    from urllib.parse import urlparse
    parsed = urlparse(url_str)

    scope = {
        "type": "http",
        "method": "POST",
        "scheme": parsed.scheme,
        "server": (parsed.hostname or "localhost", parsed.port or (80 if parsed.scheme == "http" else 443)),
        "path": parsed.path,
        "query_string": parsed.query.encode("utf-8"),
        "headers": [(k.lower().encode("utf-8"), v.encode("utf-8")) for k, v in headers_dict.items()],
    }
    return Request(scope)

def test_validate_public_https_url(monkeypatch):
    token = "test_auth_token_123456"
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", token)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_MOCK_ACCOUNT_SID_FOR_TESTS")

    provider = TwilioVoiceProvider()

    url = "https://pms.syroce.com/api/voice/outbound"
    params = {"CallSid": "CA123", "From": "client:test"}
    signature = calculate_signature(token, url, params)

    assert provider.validate_signature(url=url, params=params, signature=signature) is True

def test_validate_internal_http_url_fails(monkeypatch):
    token = "test_auth_token_123456"
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", token)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_MOCK_ACCOUNT_SID_FOR_TESTS")

    provider = TwilioVoiceProvider()

    public_url = "https://pms.syroce.com/api/voice/outbound"
    params = {"CallSid": "CA123", "From": "client:test"}
    signature = calculate_signature(token, public_url, params)

    internal_url = "http://localhost:8001/api/voice/outbound"
    assert provider.validate_signature(url=internal_url, params=params, signature=signature) is False

def test_reconstruct_public_url_from_headers():
    headers = {
        "x-forwarded-proto": "https",
        "x-forwarded-host": "pms.syroce.com",
        "host": "localhost:8001"
    }
    req = _make_mock_request("http://localhost:8001/api/voice/outbound?tenant_id=t1", headers)

    reconstructed = _public_url(req)
    assert reconstructed == "https://pms.syroce.com/api/voice/outbound?tenant_id=t1"

def test_reconstruct_public_url_using_public_app_url(monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://pms.syroce.com")
    headers = {
        "host": "localhost:8001"
    }
    req = _make_mock_request("http://localhost:8001/api/voice/outbound?tenant_id=t1", headers)

    reconstructed = _public_url(req)
    assert reconstructed == "https://pms.syroce.com/api/voice/outbound?tenant_id=t1"

def test_wrong_auth_token_fails(monkeypatch):
    correct_token = "test_auth_token_123456"
    wrong_token = "wrong_auth_token_987654"
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", wrong_token)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_MOCK_ACCOUNT_SID_FOR_TESTS")

    provider = TwilioVoiceProvider()

    url = "https://pms.syroce.com/api/voice/outbound"
    params = {"CallSid": "CA123", "From": "client:test"}
    signature = calculate_signature(correct_token, url, params)

    assert provider.validate_signature(url=url, params=params, signature=signature) is False

def test_outbound_and_status_webhook_both_validate_correctly(monkeypatch):
    token = "test_auth_token_123456"
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", token)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_MOCK_ACCOUNT_SID_FOR_TESTS")

    provider = TwilioVoiceProvider()

    # Outbound webhook validation
    outbound_url = "https://pms.syroce.com/api/voice/outbound"
    outbound_params = {"CallSid": "CA123", "From": "client:test"}
    outbound_signature = calculate_signature(token, outbound_url, outbound_params)
    assert provider.validate_signature(url=outbound_url, params=outbound_params, signature=outbound_signature) is True

    # Status webhook validation
    status_url = "https://pms.syroce.com/api/voice/status?tenant_id=t1"
    status_params = {"CallSid": "CA123", "CallStatus": "completed"}
    status_signature = calculate_signature(token, status_url, status_params)
    assert provider.validate_signature(url=status_url, params=status_params, signature=status_signature) is True

def test_public_app_url_priority_over_forwarded_headers(monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://pms.syroce.com")
    headers = {
        "x-forwarded-proto": "http",
        "x-forwarded-host": "attacker.com",
    }
    req = _make_mock_request("http://localhost:8001/api/voice/outbound", headers)
    reconstructed = _public_url(req)
    assert reconstructed == "https://pms.syroce.com/api/voice/outbound"

def test_raw_query_encoding_and_order_preserved():
    headers = {
        "x-forwarded-proto": "https",
        "x-forwarded-host": "pms.syroce.com",
    }
    req = _make_mock_request("http://localhost:8001/api/voice/status?b=2&a=1&c=%20space", headers)
    reconstructed = _public_url(req)
    assert reconstructed == "https://pms.syroce.com/api/voice/status?b=2&a=1&c=%20space"

def test_repeated_query_parameters_preserved():
    headers = {
        "x-forwarded-proto": "https",
        "x-forwarded-host": "pms.syroce.com",
    }
    req = _make_mock_request("http://localhost:8001/api/voice/status?foo=bar&foo=baz", headers)
    reconstructed = _public_url(req)
    assert reconstructed == "https://pms.syroce.com/api/voice/status?foo=bar&foo=baz"

def test_missing_public_app_url_in_production_explicitly_fails_safe(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    req = _make_mock_request("http://localhost:8001/api/voice/outbound", {})
    reconstructed = _public_url(req)
    assert "missing-public-app-url-in-production" in reconstructed

def test_no_secret_derived_value_appears_in_logs(monkeypatch, caplog):
    import logging
    token = "test_auth_token_123456"
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", token)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_MOCK_ACCOUNT_SID_FOR_TESTS")
    provider = TwilioVoiceProvider()

    url = "https://pms.syroce.com/api/voice/outbound"
    params = {"CallSid": "CA123"}

    with caplog.at_level(logging.INFO):
        provider.validate_signature(url=url, params=params, signature="invalid")

    log_text = caplog.text
    assert "auth_token_hash_prefix" not in log_text
    assert token[:6] not in log_text

def test_validate_with_starlette_form_data(monkeypatch):
    from starlette.datastructures import FormData
    token = "test_auth_token_123456"
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", token)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_MOCK_ACCOUNT_SID_FOR_TESTS")

    provider = TwilioVoiceProvider()
    url = "https://pms.syroce.com/api/voice/outbound"

    # Twilio Voice SDK fields
    params_dict = {
        "AccountSid": "AC_MOCK_ACCOUNT_SID_FOR_TESTS",
        "ApplicationSid": "AP123",
        "ApiVersion": "2010-04-01",
        "CallSid": "CA123",
        "CallStatus": "ringing",
        "Called": "+905555555555",
        "Caller": "client:agent",
        "Direction": "outbound-api",
        "From": "client:agent",
        "To": "+905555555555",
    }

    signature = calculate_signature(token, url, params_dict)
    form_data = FormData(list(params_dict.items()))

    assert provider.validate_signature(url=url, params=form_data, signature=signature) is True

def test_validate_form_data_with_duplicate_keys(monkeypatch):
    from starlette.datastructures import FormData
    token = "test_auth_token_123456"
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", token)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC_MOCK_ACCOUNT_SID_FOR_TESTS")

    provider = TwilioVoiceProvider()
    url = "https://pms.syroce.com/api/voice/outbound"

    raw_items = [
        ("AccountSid", "AC_MOCK_ACCOUNT_SID_FOR_TESTS"),
        ("CallSid", "CA123"),
        ("To", "+905555555555"),
        ("To", "+906666666666"),
    ]
    form_data = FormData(raw_items)

    # Compute signature manually matching sorted set values
    s = url
    s += "AccountSid" + "AC_MOCK_ACCOUNT_SID_FOR_TESTS"
    s += "CallSid" + "CA123"
    s += "To" + "+905555555555"
    s += "To" + "+906666666666"

    mac = hmac.new(token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1)
    expected_sig = base64.b64encode(mac.digest()).decode("utf-8")

    assert provider.validate_signature(url=url, params=form_data, signature=expected_sig) is True
