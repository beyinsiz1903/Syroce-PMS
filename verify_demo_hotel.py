import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        print("ERROR: Lütfen MONGO_URL ortam değişkenini ayarlayın (production connection string).")
        sys.exit(1)
        
    client = AsyncIOMotorClient(mongo_url)
    db = client.get_database() # Varsayılan DB'yi alır (bağlantı stringinden)
    
    tenant = await db.tenants.find_one({"name": "Syroce Demo Hotel"})
    if not tenant:
        print("Syroce Demo Hotel bulunamadı!")
        sys.exit(1)
        
    tenant_id = tenant.get("id")
    print(f"Tenant bulundu: {tenant.get('name')} (ID: {tenant_id})")
    
    users = await db.users.find({"tenant_id": tenant_id}).to_list(1000)
    
    print(f"\nToplam Kullanıcı Sayısı: {len(users)}\n")
    
    super_admins = [u for u in users if u.get("role") == "super_admin"]
    others = [u for u in users if u.get("role") != "super_admin"]
    
    print("--- Super Admin'ler ---")
    for sa in super_admins:
        print(f" Email: {sa.get('email', 'N/A'):<25} | Rol: {sa.get('role')} | Username: {sa.get('username', 'N/A')}")
        
    print(f"\n--- Diğer Kullanıcılar ({len(others)} adet) ---")
    for o in others[:15]: # İlk 15'i göster
        print(f" Email: {o.get('email', 'N/A'):<25} | Rol: {o.get('role')} | Username: {o.get('username', 'N/A')}")
        
    if len(others) > 15:
        print(f" ... ve {len(others) - 15} kullanıcı daha.")

if __name__ == "__main__":
    asyncio.run(main())
