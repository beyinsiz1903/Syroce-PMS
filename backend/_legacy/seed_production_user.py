#!/usr/bin/env python3
"""
Seed production database with demo user
"""
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
from passlib.context import CryptContext
import uuid
import os

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

async def seed_user():
    # Use MONGO_URL from environment
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    print(f'Connecting to: {mongo_url}')
    
    client = AsyncIOMotorClient(mongo_url)
    db = client['hotel_pms']
    
    # Check if user exists
    existing = await db.users.find_one({'email': 'demo@hotel.com'})
    if existing:
        print('✅ Demo user already exists')
        print(f'   Email: {existing.get("email")}')
        print(f'   Has id: {"id" in existing}')
        if 'id' not in existing:
            # Add id field
            user_id = str(uuid.uuid4())
            await db.users.update_one(
                {'_id': existing['_id']},
                {'$set': {'id': user_id, 'user_id': user_id}}
            )
            print(f'   Added id field: {user_id}')
        return
    
    # Create tenant first
    tenant_id = str(uuid.uuid4())
    tenant = {
        'id': tenant_id,
        'property_name': 'Demo Hotel',
        'address': 'Demo Address, Istanbul, Turkey',
        'phone': '+90 555 123 4567',
        'email': 'demo@hotel.com',
        'subscription_plan': 'professional',
        'room_count': 50,
        'amenities': [],
        'created_at': '2025-11-23T21:25:03.406765Z'
    }
    tenant_result = await db.tenants.insert_one(tenant)
    print(f'✅ Tenant created: {tenant["property_name"]} (id: {tenant_id})')
    
    # Create user
    user_id = str(uuid.uuid4())
    user = {
        'id': user_id,
        'user_id': user_id,
        'name': 'Demo User',
        'email': 'demo@hotel.com',
        'password': pwd_context.hash('demo123'),
        'role': 'admin',
        'tenant_id': str(tenant_result.inserted_id),
        'is_active': True,
        'created_at': '2025-11-23T21:53:28.455209Z'
    }
    await db.users.insert_one(user)
    print(f'✅ User created: {user["email"]} (id: {user_id})')
    print('   Password: demo123')
    print('   Role: admin')
    print(f'   Tenant ID: {user["tenant_id"]}')
    
    # Update tenant with correct id in user's tenant_id
    await db.users.update_one(
        {'_id': user['_id']},
        {'$set': {'tenant_id': str(tenant_result.inserted_id)}}
    )
    
    print('\n✅ Database seeding complete!')
    print('   You can now login with:')
    print('   Email: demo@hotel.com')
    print('   Password: demo123')

if __name__ == '__main__':
    asyncio.run(seed_user())
