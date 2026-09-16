import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def get_conns():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    dbs = await client.list_database_names()
    for db_name in dbs:
        if db_name in ("admin", "local", "config"): continue
        db = client[db_name]
        for coll in await db.list_collection_names():
            if "exely" in coll or "connection" in coll or "credential" in coll:
                async for doc in db[coll].find():
                    if "501694" in str(doc):
                        print(f"FOUND IN {db_name}.{coll}: {doc}")
