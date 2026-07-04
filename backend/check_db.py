import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.syroce_db # Check the DB name from your env
    collections = await db.list_collection_names()
    print("Collections:", collections)

    for coll in ['maintenance_tasks', 'users', 'invoices', 'rooms']:
        if coll in collections:
            count = await db[coll].count_documents({})
            print(f"{coll} count:", count)

asyncio.run(main())
