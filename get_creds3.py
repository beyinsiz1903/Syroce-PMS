import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def get_creds():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    dbs = await client.list_database_names()
    for db_name in dbs:
        if db_name in ("admin", "local", "config"): continue
        db = client[db_name]
        colls = await db.list_collection_names()
        if "_dev_secrets" in colls:
            async for doc in db._dev_secrets.find():
                if "501694" in str(doc):
                    print(f"FOUND IN {db_name}._dev_secrets:", doc)
