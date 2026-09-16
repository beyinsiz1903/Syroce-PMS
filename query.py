import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.syroce_pms
    docs = await db.hr_pricing_settings.find({}).to_list(10)
    for doc in docs:
        doc.pop("_id", None)
        print(json.dumps(doc, default=str))

asyncio.run(main())
