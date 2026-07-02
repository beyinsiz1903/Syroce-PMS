import asyncio
from backend.core.security import create_token
from backend.core.database import db

async def run():
    token = create_token("superadmin123", "tenant1")
    import requests
    r = requests.get("http://localhost:8000/api/mice/diary?date_from=2026-07-01&date_to=2026-07-31", headers={"Authorization": f"Bearer {token}"})
    print("STATUS:", r.status_code)
    print("BODY:", r.text)

if __name__ == "__main__":
    asyncio.run(run())
