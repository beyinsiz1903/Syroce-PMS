import logging

import httpx
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from server import app


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.log_records = []
    def emit(self, record):
        self.log_records.append(record.getMessage())

@pytest.fixture
def capture_logs():
    logger_hr = logging.getLogger("domains.channel_manager.providers.hotelrunner_security")
    logger_hw = logging.getLogger("domains.channel_manager.providers.hotelrunner_webhook")
    logger_qid = logging.getLogger("quick_id_proxy")

    handler = ListHandler()
    logger_hr.addHandler(handler)
    logger_hw.addHandler(handler)
    logger_qid.addHandler(handler)
    logger_hr.setLevel(logging.INFO)
    logger_hw.setLevel(logging.INFO)
    logger_qid.setLevel(logging.INFO)

    yield handler

    logger_hr.removeHandler(handler)
    logger_hw.removeHandler(handler)
    logger_qid.removeHandler(handler)

@pytest.fixture
def client():
    return TestClient(app)

def test_request_id_valid(client, capture_logs, monkeypatch):
    import domains.channel_manager.providers.hotelrunner_security as hsec
    async def fake_lookup(hint):
        return None
    monkeypatch.setattr(hsec, "_lookup_signing_connection", fake_lookup)

    headers = {
        "X-Request-ID": "valid.id_123-abc"
    }

    response = client.post("/api/channel-manager/hotelrunner/callback", headers=headers, json={})

    assert response.headers.get("X-Request-ID") == "valid.id_123-abc"
    logs = "\n".join(capture_logs.log_records)
    assert "[DIAG] [valid.id_123-abc]" in logs

def test_request_id_invalid(client, capture_logs, monkeypatch):
    import domains.channel_manager.providers.hotelrunner_security as hsec
    async def fake_lookup(hint):
        return None
    monkeypatch.setattr(hsec, "_lookup_signing_connection", fake_lookup)

    # invalid characters
    headers = {
        "X-Request-ID": "invalid!@#$%"
    }

    response = client.post("/api/channel-manager/hotelrunner/callback", headers=headers, json={})

    req_id = response.headers.get("X-Request-ID")
    assert req_id != "invalid!@#$%"
    assert req_id.startswith("req-")

    # over 64 characters
    headers2 = {
        "X-Request-ID": "A" * 65
    }
    response2 = client.post("/api/channel-manager/hotelrunner/callback", headers=headers2, json={})
    assert response2.headers.get("X-Request-ID") != "A" * 65
    assert response2.headers.get("X-Request-ID").startswith("req-")

def test_hr_diagnostics_no_secrets(client, capture_logs, monkeypatch):
    import domains.channel_manager.providers.hotelrunner_security as hsec

    monkeypatch.setenv("HOTELRUNNER_WEBHOOK_SECRET", "super-secret-hr-webhook")

    headers = {
        "X-HotelRunner-Signature": "sha256=invalid-signature-12345",
        "X-HotelRunner-Timestamp": "1234567890",
        "X-Tenant-ID": "tenant-id-full-uuid-123",
        "X-Request-ID": "test-req-hr-1"
    }

    async def fake_lookup(hint):
        return {"hr_id": "hr-123", "tenant_id": "tenant-id-full-uuid-123"}

    monkeypatch.setattr(hsec, "_lookup_signing_connection", fake_lookup)

    response = client.post("/api/channel-manager/hotelrunner/callback", headers=headers, json={"hotel_id": "hr-123"})

    assert response.headers.get("X-Request-ID") == "test-req-hr-1"

    logs = "\n".join(capture_logs.log_records)

    assert "super-secret-hr-webhook" not in logs
    assert "invalid-signature-12345" not in logs
    assert "tenant-id-full-uuid-123" not in logs
    # Should use fingerprint
    from core.masking import fingerprint_id
    assert fingerprint_id("tenant-id-full-uuid-123") in logs
    assert fingerprint_id("hr-123") in logs

def test_qid_diagnostics_no_secrets(client, capture_logs, monkeypatch):
    import routers.quick_id_proxy as qid
    monkeypatch.setattr(qid, "QUICKID_SERVICE_KEY", "super-secret-qid-key")

    token = "long-token-1234567890abcdef"

    class MockResponse:
        status_code = 200
        def json(self): return {}
    async def mock_get(*args, **kwargs):
        return MockResponse()
    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    _ = client.get(f"/api/quick-id/precheckin/{token}/info", headers={"X-Request-ID": "test-req-qid-1"})

    logs = "\n".join(capture_logs.log_records)

    assert "super-secret-qid-key" not in logs
    assert token not in logs

def test_hr_successful_callback_no_tenant_id_leak(client, capture_logs, monkeypatch):
    import domains.channel_manager.providers.hotelrunner_security as hsec

    headers = {
        "X-Request-ID": "test-req-hr-2"
    }

    async def fake_verify(request: Request):
        request.state.hr_diag = {}
        request.state.req_id = "test-req-hr-2"
        return None
    app.dependency_overrides[hsec._verify_hotelrunner_callback] = fake_verify

    async def fake_resolve(body: dict, request: Request):
        return "tenant-id-full-uuid-123"

    import domains.channel_manager.providers.hotelrunner_webhook as hw
    monkeypatch.setattr(hw, "_resolve_tenant_from_callback", fake_resolve)

    payload = {
        "state": "new",
        "hotel_id": "hr-123",
        "reservations": [{"hr_number": "SECRET-HR-NUMBER-LEAK-SENTINEL"}]
    }

    _ = client.post("/api/channel-manager/hotelrunner/callback", headers=headers, json=payload)

    logs = "\n".join(capture_logs.log_records)
    assert "tenant-id-full-uuid-123" not in logs
    from core.masking import fingerprint_id
    assert fingerprint_id("tenant-id-full-uuid-123") in logs

    app.dependency_overrides.pop(hsec._verify_hotelrunner_callback, None)


def test_request_id_crlf_and_control_chars(client):
    headers = [
        {"X-Request-ID": "abc\r\nforged-log"},
        {"X-Request-ID": "\r"},
        {"X-Request-ID": "\n"},
        {"X-Request-ID": "A" * 65},
        {"X-Request-ID": "invalid\x00char"}
    ]
    for h in headers:
        response = client.post("/api/channel-manager/hotelrunner/callback", headers=h, json={})
        req_id = response.headers.get("X-Request-ID")
        assert req_id != h["X-Request-ID"]
        assert req_id.startswith("req-")

def test_hr_dependency_generated_503(client, capture_logs, monkeypatch):
    import domains.channel_manager.providers.hotelrunner_security as hsec

    async def fake_verify(request: Request):
        from fastapi import HTTPException
        request.state.hr_diag = {}
        request.state.req_id = "test-req-hr-503"
        raise HTTPException(status_code=503, detail="Simulated 503")

    app.dependency_overrides[hsec._verify_hotelrunner_callback] = fake_verify

    headers = {
        "X-Request-ID": "test-req-hr-503"
    }

    response = client.post("/api/channel-manager/hotelrunner/callback", headers=headers, json={"hotel_id": "hr-123"})

    assert response.status_code == 503
    assert response.headers.get("X-Request-ID") == "test-req-hr-503"

    logs = "\n".join(capture_logs.log_records)
    # Check that it didn't leak anything
    assert "hr-123" not in logs

    app.dependency_overrides.pop(hsec._verify_hotelrunner_callback, None)

def test_middleware_registration():
    from modules.observability.request_tracing_middleware import RequestTracingMiddleware

    has_tracing = False
    duplicate_count = 0
    for middleware in app.user_middleware:
        # User middleware holds the cls in `middleware.cls`
        if getattr(middleware, "cls", None) == RequestTracingMiddleware:
            has_tracing = True
            duplicate_count += 1
        elif "RequestIdMiddleware" in str(middleware.cls):
            duplicate_count += 1

    assert has_tracing, "RequestTracingMiddleware is not registered in the app stack"
    assert duplicate_count == 1, "Duplicate request ID middleware found"

def test_hr_background_persistence_failure(client, capture_logs, monkeypatch):
    import domains.channel_manager.providers.hotelrunner_security as hsec
    import domains.channel_manager.providers.hotelrunner_webhook as hw

    headers = {
        "X-Request-ID": "test-req-hr-fail"
    }

    async def fake_verify(request: Request):
        request.state.hr_diag = {}
        request.state.req_id = "test-req-hr-fail"
        return None
    app.dependency_overrides[hsec._verify_hotelrunner_callback] = fake_verify

    async def fake_resolve(body: dict, request: Request):
        return "tenant-id-full-uuid-123"

    monkeypatch.setattr(hw, "_resolve_tenant_from_callback", fake_resolve)

    async def fake_persist(*args, **kwargs):
        raise ValueError("Simulated persistence error")

    monkeypatch.setattr(hw, "_persist_and_process", fake_persist)

    payload = {
        "state": "new",
        "hotel_id": "hr-123",
        "reservations": [{"hr_number": "SECRET-HR-NUMBER-LEAK-SENTINEL"}]
    }

    _ = client.post("/api/channel-manager/hotelrunner/callback", headers=headers, json=payload)

    # Wait for background tasks to finish. TestClient executes background tasks implicitly in some versions,
    # but to be safe, Starlette TestClient runs them after the response is returned.

    logs = "\n".join(capture_logs.log_records)

    assert "persistence_failure" in logs
    assert "ValueError" in logs
    assert "elapsed_ms" in logs

    assert "Simulated persistence error" not in logs
    # hr_number is "SECRET-HR-NUMBER-LEAK-SENTINEL" in this test
    assert "SECRET-HR-NUMBER-LEAK-SENTINEL" not in logs
    assert "hr-123" not in logs
    assert "tenant-id-full-uuid-123" not in logs

    app.dependency_overrides.pop(hsec._verify_hotelrunner_callback, None)

def test_quick_id_upstream_exceptions(client, capture_logs, monkeypatch):
    import routers.quick_id_proxy as qid
    monkeypatch.setattr(qid, "QUICKID_SERVICE_KEY", "super-secret-qid-key")

    token = "long-token-1234567890abcdef"

    class MockResponse:
        status_code = 502
        def json(self): return {}
        def raise_for_status(self): raise httpx.HTTPStatusError("502", request=None, response=self)

    async def mock_get_502(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_502)

    response1 = client.get(f"/api/quick-id/precheckin/{token}/info", headers={"X-Request-ID": "test-req-qid-502"})
    assert response1.status_code == 503

    logs1 = "\n".join(capture_logs.log_records)
    assert "upstream request attempted: true" in logs1
    assert "host: " in logs1
    assert "QID final response status 503" in logs1
    assert "upstream_duration=" in logs1
    assert "super-secret-qid-key" not in logs1
    assert token not in logs1

    capture_logs.log_records.clear()

    async def mock_get_req_error(*args, **kwargs):
        raise httpx.RequestError("Connection timeout")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_req_error)

    response2 = client.get(f"/api/quick-id/precheckin/{token}/info", headers={"X-Request-ID": "test-req-qid-reqerr"})
    assert response2.status_code == 503

    logs2 = "\n".join(capture_logs.log_records)
    assert "upstream request attempted: true" in logs2
    assert "RequestError" in logs2
    assert "QID final response status 503" in logs2
    assert "super-secret-qid-key" not in logs2
    assert token not in logs2
