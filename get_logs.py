import asyncio
from backend.core.database import db

async def run():
    logs = await db._collection.database.system_logs.find().sort("_id", -1).limit(5).to_list(None)
    for log in logs:
        print(log)

if __name__ == "__main__":
    asyncio.run(run())
