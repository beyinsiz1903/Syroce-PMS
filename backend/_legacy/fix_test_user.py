"""
Fix test user - ensure proper setup
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime, timezone
import uuid
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def fix_test_user():
    # Connect to MongoDB
    mongo_url = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
    client = AsyncIOMotorClient(mongo_url)
    db = client['pms_db']
    
    tenant_id = "test-hotel-001"
    
    print("🔍 Checking existing users...")
    
    # Check all users in database
    all_users = await db.users.find({}).to_list(100)
    print(f"Found {len(all_users)} total users in database")
    
    for user in all_users:
        print(f"  - {user.get('username')} | {user.get('email')} | tenant: {user.get('tenant_id')}")
    
    print("\n🗑️  Deleting old test user if exists...")
    
    # Delete any existing test user
    result = await db.users.delete_many({
        '$or': [
            {'username': 'testuser'},
            {'username': 'test@hotel.com'},
            {'email': 'test@hotel.com'}
        ]
    })
    print(f"Deleted {result.deleted_count} old test user(s)")
    
    print("\n✨ Creating fresh test user...")
    
    # Create test user with proper structure
    test_user = {
        'id': str(uuid.uuid4()),
        'tenant_id': tenant_id,
        'username': 'test@hotel.com',
        'email': 'test@hotel.com',
        'password': pwd_context.hash('test123'),
        'name': 'Test Manager',
        'role': 'admin',  # Changed to admin for full access
        'permissions': ['all'],
        'active': True,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.users.insert_one(test_user)
    
    # Verify user was created
    created_user = await db.users.find_one({'username': 'test@hotel.com'})
    
    print("\n" + "="*70)
    print("✅ TEST USER CREATED SUCCESSFULLY!")
    print("="*70)
    print("\n🔐 Login Credentials:")
    print("   Email: test@hotel.com")
    print("   Password: test123")
    print("\n📋 User Details:")
    print(f"   User ID: {created_user['id']}")
    print(f"   Tenant ID: {created_user['tenant_id']}")
    print(f"   Name: {created_user['name']}")
    print(f"   Role: {created_user['role']}")
    print(f"   Active: {created_user['active']}")
    print("\n" + "="*70)
    print("\n✨ Try logging in now!")
    print("   1. Go to login page")
    print("   2. Email: test@hotel.com")
    print("   3. Password: test123")
    print("   4. Click Login")
    print("\n" + "="*70)
    
    # Also check if tenant has data
    rooms_count = await db.rooms.count_documents({'tenant_id': tenant_id})
    guests_count = await db.guests.count_documents({'tenant_id': tenant_id})
    bookings_count = await db.bookings.count_documents({'tenant_id': tenant_id})
    
    print("\n📊 Test Hotel Data Check:")
    print(f"   Rooms: {rooms_count}")
    print(f"   Guests: {guests_count}")
    print(f"   Bookings: {bookings_count}")
    
    if rooms_count == 0:
        print("\n⚠️  Warning: No test data found! Run: python create_test_data.py")
    else:
        print("\n✅ Test hotel data is present!")

if __name__ == "__main__":
    asyncio.run(fix_test_user())
