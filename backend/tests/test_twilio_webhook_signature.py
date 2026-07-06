import pytest
import os
import hmac
import hashlib
import base64
from fastapi import Request
from domains.contact_center.voice_provider import TwilioVoiceProvider
from domains.contact_center.voice_router import _public_url
from domains.contact_center.voice_config import TwilioVoiceConfig

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
