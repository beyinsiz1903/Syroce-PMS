import sys, os, asyncio
sys.path.insert(0, os.path.abspath('backend'))
from models.schemas import User
from core.database import get_system_db

async def main():
    db = get_system_db()
    users = await db["users"].find({}).to_list(10)
    for u in users:
        print(f"User: {u.get('email')} Role: {u.get('role')} Roles: {u.get('roles')}")

if __name__ == "__main__":
    asyncio.run(main())
