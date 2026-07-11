import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient

PROD_URL = os.environ.get("PROD_MONGO_URL") or os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
PROD_DB = os.environ.get("PROD_DB_NAME") or os.environ.get("DB_NAME") or "hotel_pms"

async def main():
    print(f"Connecting to DB: {PROD_DB}")
    client = AsyncIOMotorClient(PROD_URL)
    db = client[PROD_DB]

    docs = await db.hotelrunner_connections.find({"is_active": True}).to_list(10)
    for doc in docs:
        print(f"Found tenant: {doc.get('tenant_id')}, hr_id: {doc.get('hr_id')}, has_token: {'token' in doc or 'credentials_ref' in doc}, env: {doc.get('environment')}")

if __name__ == "__main__":
    asyncio.run(main())
