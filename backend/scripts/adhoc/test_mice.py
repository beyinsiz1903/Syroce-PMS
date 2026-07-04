import asyncio
import json

from motor.motor_asyncio import AsyncIOMotorClient


async def run():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.syroce_pms
    cur = db.mice_events.find({}, {"_id": 0})
    events = [d async for d in cur]
    print(json.dumps(events, indent=2))

asyncio.run(run())
