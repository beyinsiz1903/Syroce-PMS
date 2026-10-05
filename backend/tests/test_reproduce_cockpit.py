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
        assert login_resp.status_code == 200, f"Login failed: {login_resp.status_code} {login_resp.text}"
        token = login_resp.json()["access_token"]
        
        # 2. Call cockpit
        resp = await client.get(
            "/api/lockdown/runtime/cockpit",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200, f"Cockpit failed: {resp.status_code} {resp.text}"
