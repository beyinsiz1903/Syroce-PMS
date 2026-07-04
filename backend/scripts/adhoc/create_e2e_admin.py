import asyncio
from core.database import _raw_db
from core.security import hash_password
from security.encrypted_lookup import encrypt_user_doc
import uuid

async def create_user():
    user_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": "syroce_demo_pilot",
        "email": "admin@syrocedemo.com",
        "username": "admin",
        "name": "E2E Admin",
        "phone": "+1000000000",
        "role": "admin",
        "status": "active",
        "hashed_password": hash_password("demo")
    }
    encrypted = encrypt_user_doc(user_doc)
    await _raw_db.users.insert_one(encrypted)
    print("User created")

asyncio.run(create_user())
