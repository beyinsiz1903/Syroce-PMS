import asyncio
from backend.core.database import db

async def run():
    result = await db._collection.database.users.update_many(
        {"requires_password_change": True},
        {"$set": {"requires_password_change": False}}
    )
    print(f"Updated {result.modified_count} users")

if __name__ == "__main__":
    asyncio.run(run())
