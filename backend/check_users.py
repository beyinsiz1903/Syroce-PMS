import asyncio
from pymongo import MongoClient

async def main():
    client = MongoClient("mongodb://localhost:27017")
    db = client["syroce_platform"]
    users = db["users"].find({})
    for u in users:
        print(f"User: {u.get('name')} Email: {u.get('email')} Role: {u.get('role')} Roles: {u.get('roles')}")

if __name__ == "__main__":
    asyncio.run(main())
