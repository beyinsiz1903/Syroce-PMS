import asyncio

from pymongo import MongoClient

async def main():
    client = MongoClient("mongodb://localhost:27017")
    db = client["hotel_pms"]
    users = db["users"].find({})
    for user in users:
        print(f"Email: {user.get('email')} Role: {user.get('role')} Roles: {user.get('roles')}")

if __name__ == "__main__":
    asyncio.run(main())
