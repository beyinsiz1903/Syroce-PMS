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

    # slash/boşluk/nokta içeren token → 422, upstream çağrılmaz
    # Note: / in path parameters without path converters results in 404
    resp = client.get("/api/quick-id/precheckin/invalid/token/info")
    assert resp.status_code == 404

    resp = client.get("/api/quick-id/precheckin/invalid.token.123/info")
    assert resp.status_code == 422
    
    resp = client.get("/api/quick-id/precheckin/invalid token 123/info")
    assert resp.status_code == 422

    # Aynı doğrulama /scan için geçerli
    resp = client.post("/api/quick-id/precheckin/123456789012345/scan", json={"kvkk_consent": True})
    assert resp.status_code == 422
