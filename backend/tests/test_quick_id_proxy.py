from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.quick_id_proxy import public_router

app = FastAPI()
app.include_router(public_router)
client = TestClient(app)

def test_quick_id_token_validation():
    # Geçerli UUID/token → upstream çağrılabilir (503 if service is disabled, but NOT 422)
    valid_uuid = "123e4567-e89b-12d3-a456-426614174000"
    resp = client.get(f"/api/quick-id/precheckin/{valid_uuid}/info")
    assert resp.status_code != 422

    valid_token = "abcdef0123456789abcdef0123456789"
    resp = client.get(f"/api/quick-id/precheckin/{valid_token}/info")
    assert resp.status_code != 422

    # 15 karakter → 422, upstream çağrılmaz
    resp = client.get("/api/quick-id/precheckin/123456789012345/info")
    assert resp.status_code == 422

    # 129 karakter → 422, upstream çağrılmaz
    too_long = "a" * 129
    resp = client.get(f"/api/quick-id/precheckin/{too_long}/info")
    assert resp.status_code == 422

    # slash içeren token → 404 (FastAPI routing fail before path validation)
    resp = client.get("/api/quick-id/precheckin/invalid/token/info")
    assert resp.status_code == 404

    # nokta içeren token → 422
    resp = client.get("/api/quick-id/precheckin/invalid.token.123/info")
    assert resp.status_code == 422

    # boşluk içeren token → 422
    resp = client.get("/api/quick-id/precheckin/invalid token 123/info")
    assert resp.status_code == 422

    # Aynı doğrulama /scan için geçerli
    resp = client.post("/api/quick-id/precheckin/123456789012345/scan", json={"kvkk_consent": True})
    assert resp.status_code == 422

def test_quickid_disabled_precedence():
    valid_uuid = "123e4567-e89b-12d3-a456-426614174000"

    # 1. Missing QUICKID_URL -> returns 503 QUICKID_DISABLED (0 upstream calls)
    with patch("routers.quick_id_proxy.QUICKID_URL", ""), patch("routers.quick_id_proxy.QUICKID_SERVICE_KEY", "key"), patch("routers.quick_id_proxy.httpx.AsyncClient") as mock_client:
        resp = client.get(f"/api/quick-id/precheckin/{valid_uuid}/info")
        assert not mock_client.called, "AsyncClient should not even be instantiated"
        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "QUICKID_DISABLED"

        # Also works when both URL and KEY are missing, URL check should win!
        with patch("routers.quick_id_proxy.QUICKID_SERVICE_KEY", ""):
            resp = client.get(f"/api/quick-id/precheckin/{valid_uuid}/info")
            assert not mock_client.called, "AsyncClient should not even be instantiated"
            assert resp.status_code == 503
            assert resp.json()["detail"]["code"] == "QUICKID_DISABLED"

    # 2. Garbage token -> returns 422 BEFORE disabled checks
    with patch("routers.quick_id_proxy.QUICKID_URL", ""), patch("routers.quick_id_proxy.QUICKID_SERVICE_KEY", ""), patch("routers.quick_id_proxy.httpx.AsyncClient") as mock_client:
        resp = client.get("/api/quick-id/precheckin/invalid token 123/info")
        assert not mock_client.called, "AsyncClient should not even be instantiated"
        assert resp.status_code == 422


def test_quickid_invalid_token_never_calls_upstream():
    with patch("routers.quick_id_proxy.QUICKID_URL", "https://quick-id.invalid"), \
         patch("routers.quick_id_proxy.QUICKID_SERVICE_KEY", "key"), \
         patch("routers.quick_id_proxy.httpx.AsyncClient") as mock_client:
        resp = client.get(f"/api/quick-id/precheckin/{'a' * 129}/info")

    assert resp.status_code == 422
    mock_client.assert_not_called()


def test_quickid_request_error_returns_safe_unavailable_metadata(monkeypatch):
    valid_uuid = "123e4567-e89b-12d3-a456-426614174000"

    async def fail_get(*_args, **_kwargs):
        raise httpx.ReadTimeout("sensitive upstream detail")

    monkeypatch.setattr("routers.quick_id_proxy.QUICKID_URL", "https://quick-id.invalid")
    monkeypatch.setattr("routers.quick_id_proxy.QUICKID_SERVICE_KEY", "secret-key")
    monkeypatch.setattr(httpx.AsyncClient, "get", fail_get)

    resp = client.get(f"/api/quick-id/precheckin/{valid_uuid}/info")

    assert resp.status_code == 503
    assert resp.json() == {
        "detail": {
            "code": "QUICKID_UNAVAILABLE",
            "message": "Quick-ID servisine ulaşılamıyor.",
        }
    }
    assert "sensitive upstream detail" not in resp.text
