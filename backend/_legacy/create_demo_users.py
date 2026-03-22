import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
import os
from datetime import datetime

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_demo_users():
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    client = AsyncIOMotorClient(mongo_url)
    db = client['hotel_pms']
    
    # Clear existing users
    await db.users.delete_many({})
    print("🗑️  Mevcut kullanıcılar temizlendi")
    
    # Demo users
    demo_users = [
        {
            "email": "admin@hotel.com",
            "password": pwd_context.hash("admin123"),
            "name": "Admin User",
            "role": "admin",
            "tenant_id": "demo_hotel",
            "created_at": datetime.utcnow(),
            "is_active": True
        },
        {
            "email": "supervisor@hotel.com",
            "password": pwd_context.hash("super123"),
            "name": "Supervisor Manager",
            "role": "supervisor",
            "tenant_id": "demo_hotel",
            "created_at": datetime.utcnow(),
            "is_active": True
        },
        {
            "email": "housekeeping@hotel.com",
            "password": pwd_context.hash("hk123"),
            "name": "Temizlik Müdürü",
            "role": "housekeeping",
            "tenant_id": "demo_hotel",
            "created_at": datetime.utcnow(),
            "is_active": True
        },
        {
            "email": "frontdesk@hotel.com",
            "password": pwd_context.hash("fd123"),
            "name": "Ön Büro Müdürü",
            "role": "front_desk",
            "tenant_id": "demo_hotel",
            "created_at": datetime.utcnow(),
            "is_active": True
        },
        {
            "email": "fnb@hotel.com",
            "password": pwd_context.hash("fnb123"),
            "name": "F&B Müdürü",
            "role": "fnb",
            "tenant_id": "demo_hotel",
            "created_at": datetime.utcnow(),
            "is_active": True
        },
        {
            "email": "maintenance@hotel.com",
            "password": pwd_context.hash("tech123"),
            "name": "Teknik Müdür",
            "role": "maintenance",
            "tenant_id": "demo_hotel",
            "created_at": datetime.utcnow(),
            "is_active": True
        },
        {
            "email": "finance@hotel.com",
            "password": pwd_context.hash("fin123"),
            "name": "Finans Müdürü",
            "role": "finance",
            "tenant_id": "demo_hotel",
            "created_at": datetime.utcnow(),
            "is_active": True
        },
        {
            "email": "gm@hotel.com",
            "password": pwd_context.hash("gm123"),
            "name": "Genel Müdür",
            "role": "admin",
            "tenant_id": "demo_hotel",
            "created_at": datetime.utcnow(),
            "is_active": True
        }
    ]
    
    # Insert users
    result = await db.users.insert_many(demo_users)
    print(f"✅ {len(result.inserted_ids)} demo kullanıcı oluşturuldu\n")
    
    # Print credentials
    print("=" * 80)
    print("📋 DEMO KULLANICI BİLGİLERİ")
    print("=" * 80)
    print("\n1. 👑 ADMIN - Tüm Departmanlara Erişim")
    print("   Email: admin@hotel.com")
    print("   Şifre: admin123")
    print()
    print("2. 👔 SUPERVISOR - Tüm Departmanlara Erişim")
    print("   Email: supervisor@hotel.com")
    print("   Şifre: super123")
    print()
    print("3. 🛏️  TEMİZLİK MÜDÜRÜ - Housekeeping")
    print("   Email: housekeeping@hotel.com")
    print("   Şifre: hk123")
    print()
    print("4. 👥 ÖN BÜRO MÜDÜRÜ - Front Desk")
    print("   Email: frontdesk@hotel.com")
    print("   Şifre: fd123")
    print()
    print("5. 🍽️  F&B MÜDÜRÜ - Food & Beverage")
    print("   Email: fnb@hotel.com")
    print("   Şifre: fnb123")
    print()
    print("6. 🔧 TEKNİK MÜDÜR - Maintenance")
    print("   Email: maintenance@hotel.com")
    print("   Şifre: tech123")
    print()
    print("7. 💰 FİNANS MÜDÜRÜ - Finance")
    print("   Email: finance@hotel.com")
    print("   Şifre: fin123")
    print()
    print("8. 📊 GENEL MÜDÜR - General Manager (Admin Yetkisi)")
    print("   Email: gm@hotel.com")
    print("   Şifre: gm123")
    print()
    print("=" * 80)
    print("\n✅ Tüm kullanıcılar başarıyla oluşturuldu!")
    print("🔐 Şifreler kalıcı olarak kaydedildi ve silinmeyecektir.")
    print()

if __name__ == "__main__":
    asyncio.run(create_demo_users())
