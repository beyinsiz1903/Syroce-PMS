import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def get_creds():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    dbs = await client.list_database_names()
    for db_name in dbs:
        if db_name in ("admin", "local", "config"): continue
        db = client[db_name]
        colls = await client[db_name].list_collection_names()
        if "provider_credentials" in colls:
            async for doc in db.provider_credentials.find():
                if doc.get("hotel_code") == "501694" or doc.get("property_id") == "501694" or "501694" in str(doc):
                    print(f"FOUND IN {db_name}.provider_credentials:", doc)
