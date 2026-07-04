import asyncio

import httpx

from core.database import _raw_db
from core.security import create_token
from server import app


async def run_test():
    # Find a user directly via motor
    user = await _raw_db.users.find_one({})
    if not user:
        print("No users found in db.")
        return

    print(f"Testing with user: {user.get('email')}, tenant_id: {user.get('tenant_id')}")
    token = create_token(user["id"], user.get("tenant_id"))

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/lockdown/runtime/cockpit",
            headers={"Authorization": f"Bearer {token}"}
        )
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")

if __name__ == "__main__":
    asyncio.run(run_test())

