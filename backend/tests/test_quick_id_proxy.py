import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from routers.quick_id_proxy import public_router

app = FastAPI()
app.include_router(public_router)
client = TestClient(app)

def test_quick_id_token_validation():
    # Geçerli UUID/token → upstream çağrılabilir (503 if QUICKID_SERVICE_KEY not configured, but NOT 422)
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

from unittest.mock import patch

def test_quickid_disabled_precedence():
    valid_uuid = "123e4567-e89b-12d3-a456-426614174000"
    
    # 1. Missing QUICKID_URL -> returns 503 QUICKID_DISABLED (0 upstream calls)
    with patch("routers.quick_id_proxy.QUICKID_URL", ""), patch("routers.quick_id_proxy.QUICKID_SERVICE_KEY", "key"):
        resp = client.get(f"/api/quick-id/precheckin/{valid_uuid}/info")
        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "QUICKID_DISABLED"
        
        # Also works when both URL and KEY are missing, URL check should win!
        with patch("routers.quick_id_proxy.QUICKID_SERVICE_KEY", ""):
            resp = client.get(f"/api/quick-id/precheckin/{valid_uuid}/info")
            assert resp.status_code == 503
            assert resp.json()["detail"]["code"] == "QUICKID_DISABLED"

    # 2. Garbage token -> returns 422 BEFORE disabled checks
    with patch("routers.quick_id_proxy.QUICKID_URL", ""), patch("routers.quick_id_proxy.QUICKID_SERVICE_KEY", ""):
        resp = client.get("/api/quick-id/precheckin/invalid token 123/info")
        assert resp.status_code == 422
