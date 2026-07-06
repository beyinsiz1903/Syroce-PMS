import pytest
import httpx
from httpx import ASGITransport
from server import app

@pytest.mark.anyio
async def test_reproduce_cockpit_401():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Login to get token
        login_resp = await client.post(
            "/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"}
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        
        # 2. Call cockpit
        resp = await client.get(
            "/api/lockdown/runtime/cockpit",
            headers={"Authorization": f"Bearer {token}"}
        )
        print("STATUS:", resp.status_code)
        print("BODY:", resp.text)
        assert resp.status_code == 200
