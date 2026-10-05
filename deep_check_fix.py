import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def run():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    dbs = await client.list_database_names()
    
    print("=== Global ID Trace (ACK/Outbox/Logs) ===")
    for db_name in dbs:
        if db_name in ("admin", "local", "config"): continue
        db = client[db_name]
        colls = await db.list_collection_names()
        
        for coll in colls:
            if coll in ["exely_connections", "channel_connections"]:
                continue
                
            try:
                # Basic string match on fields where it typically appears
                async for doc in db[coll].find({"$or": [
                    {"provider_reservation_id": {"$regex": "1200418077"}},
                    {"external_id": {"$regex": "1200418077"}},
                    {"id": {"$regex": "1200418077"}},
                    {"pms_booking_id": {"$regex": "1200418077"}},
                ]}):
                    print(f"[{db_name}.{coll}] Trace found! Keys: {list(doc.keys())}")
            except Exception as e:
                pass
                
    print("Search complete.")

if __name__ == "__main__":
    asyncio.run(run())
