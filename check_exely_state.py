import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from bson import json_util
import json

async def run():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    dbs = await client.list_database_names()
    
    print("=== Connections ===")
    for db_name in dbs:
        if db_name in ("admin", "local", "config"): continue
        db = client[db_name]
        colls = await db.list_collection_names()
        
        # Check connections
        for coll in ["exely_connections", "channel_connections"]:
            if coll in colls:
                async for doc in db[coll].find({"hotel_code": "501694"}):
                    print(f"[{db_name}.{coll}] Tenant: {doc.get('tenant_id')}, Active: {doc.get('is_active')}, Mode: {doc.get('mode')}, Endpoint: {doc.get('endpoint_url')}")

    print("\n=== Reservations ===")
    for db_name in dbs:
        if db_name in ("admin", "local", "config"): continue
        db = client[db_name]
        colls = await db.list_collection_names()
        
        # Check reservations
        for coll in ["exely_reservations", "reservations"]:
            if coll in colls:
                # search by ID substring
                async for doc in db[coll].find({"$or": [
                    {"provider_reservation_id": {"$regex": "1200418077"}},
                    {"external_id": {"$regex": "1200418077"}},
                    {"id": {"$regex": "1200418077"}}
                ]}):
                    print(f"[{db_name}.{coll}] Tenant: {doc.get('tenant_id')}, State: {doc.get('delivery_state', doc.get('status'))}")

if __name__ == "__main__":
    asyncio.run(run())
