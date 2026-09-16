import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json

async def run():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    dbs = await client.list_database_names()
    
    print("=== Connection Deep Dive ===")
    for db_name in dbs:
        if db_name in ("admin", "local", "config"): continue
        db = client[db_name]
        colls = await db.list_collection_names()
        
        for coll in ["exely_connections", "channel_connections"]:
            if coll in colls:
                async for doc in db[coll].find({"hotel_code": "501694"}):
                    # Remove ObjectId for printing
                    if '_id' in doc: doc['_id'] = str(doc['_id'])
                    print(f"[{db_name}.{coll}] Tenant: {doc.get('tenant_id')} | CreatedBy: {doc.get('created_by')} | Name: {doc.get('property_name')}")

    print("\n=== Global ID Trace (ACK/Outbox/Logs) ===")
    for db_name in dbs:
        if db_name in ("admin", "local", "config"): continue
        db = client[db_name]
        colls = await db.list_collection_names()
        
        for coll in colls:
            if coll in ["exely_connections", "channel_connections"]:
                continue # Skip connections
                
            # Search for the reservation ID anywhere in the document
            async for doc in db[coll].find({"$text": {"$search": "1200418077"}}):
                print(f"[{db_name}.{coll}] (Text Match) Found trace!")
                
            async for doc in db[coll].find({"$or": [
                {"provider_reservation_id": {"$regex": "1200418077"}},
                {"external_id": {"$regex": "1200418077"}},
                {"id": {"$regex": "1200418077"}},
                {"pms_booking_id": {"$regex": "1200418077"}},
                {"payload": {"$regex": "1200418077"}}, # Common outbox/log field
                {"response": {"$regex": "1200418077"}}
            ]}):
                print(f"[{db_name}.{coll}] Trace found! Keys: {list(doc.keys())}")

if __name__ == "__main__":
    asyncio.run(run())
