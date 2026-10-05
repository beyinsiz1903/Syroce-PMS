import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json

async def run():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    dbs = await client.list_database_names()
    
    for db_name in dbs:
        if db_name in ("admin", "local", "config"): continue
        db = client[db_name]
        colls = await db.list_collection_names()
        
        if "exely_pull_cursors" in colls:
            async for doc in db.exely_pull_cursors.find():
                if '_id' in doc: doc['_id'] = str(doc['_id'])
                print(f"[{db_name}.exely_pull_cursors] {json.dumps(doc)}")
        
        if "system_logs" in colls or "provider_api_logs" in colls:
            # check if there's any log table we can look at
            pass

if __name__ == "__main__":
    asyncio.run(run())
