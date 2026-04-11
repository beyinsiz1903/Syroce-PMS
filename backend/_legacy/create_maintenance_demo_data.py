#!/usr/bin/env python3
"""
Demo Data Generator for Technical Maintenance Features
Creates sample data for testing maintenance and technical service features
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta
import uuid

# MongoDB connection
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "hotel_pms"

async def create_demo_data():
    """Create demo data for maintenance features"""
    
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    print("🔧 Creating Maintenance Demo Data...")
    
    # Get first tenant
    tenant = await db.tenants.find_one()
    if not tenant:
        print("❌ No tenant found. Please register a tenant first.")
        return
    
    tenant_id = tenant['id']
    print(f"✅ Using tenant: {tenant.get('hotel_name', 'Unknown')}")
    
    # 1. Create SLA Configurations
    print("\n⏱️ Creating SLA Configurations...")
    
    sla_configs = [
        {'priority': 'emergency', 'response_time_minutes': 15, 'resolution_time_minutes': 120},
        {'priority': 'urgent', 'response_time_minutes': 30, 'resolution_time_minutes': 240},
        {'priority': 'high', 'response_time_minutes': 60, 'resolution_time_minutes': 480},
        {'priority': 'normal', 'response_time_minutes': 120, 'resolution_time_minutes': 1440},
        {'priority': 'low', 'response_time_minutes': 240, 'resolution_time_minutes': 2880}
    ]
    
    await db.sla_configurations.delete_many({'tenant_id': tenant_id})
    
    for config in sla_configs:
        await db.sla_configurations.insert_one({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'priority': config['priority'],
            'response_time_minutes': config['response_time_minutes'],
            'resolution_time_minutes': config['resolution_time_minutes'],
            'is_active': True,
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        })
    
    print(f"✅ Created {len(sla_configs)} SLA configurations")
    
    # 2. Create Spare Parts
    print("\n🔩 Creating Spare Parts Inventory...")
    
    spare_parts = [
        {
            'part_number': 'PLB-001',
            'part_name': 'Musluk Kartuşu',
            'description': 'Banyo lavabo musluğu kartuşu',
            'category': 'Plumbing',
            'warehouse_location': 'main_warehouse',
            'current_stock': 25,
            'minimum_stock': 10,
            'unit_price': 45.00,
            'supplier': 'Vitra',
            'qr_code': 'QR-PLB-001'
        },
        {
            'part_number': 'ELC-001',
            'part_name': 'LED Ampul 12W',
            'description': 'E27 duylu LED ampul',
            'category': 'Electrical',
            'warehouse_location': 'floor_storage',
            'current_stock': 8,  # Low stock
            'minimum_stock': 15,
            'unit_price': 25.00,
            'supplier': 'Philips',
            'qr_code': 'QR-ELC-001'
        },
        {
            'part_number': 'HVAC-001',
            'part_name': 'AC Filtresi',
            'description': 'Klima hava filtresi',
            'category': 'HVAC',
            'warehouse_location': 'workshop',
            'current_stock': 30,
            'minimum_stock': 12,
            'unit_price': 75.00,
            'supplier': 'Daikin',
            'qr_code': 'QR-HVAC-001'
        },
        {
            'part_number': 'PLB-002',
            'part_name': 'Sifon Contası',
            'description': 'Lavabo sifon contası',
            'category': 'Plumbing',
            'warehouse_location': 'main_warehouse',
            'current_stock': 5,  # Low stock
            'minimum_stock': 20,
            'unit_price': 15.00,
            'supplier': 'VitrA',
            'qr_code': 'QR-PLB-002'
        },
        {
            'part_number': 'ELC-002',
            'part_name': 'Priz Modülü',
            'description': 'Duvar prizi modülü',
            'category': 'Electrical',
            'warehouse_location': 'floor_storage',
            'current_stock': 40,
            'minimum_stock': 15,
            'unit_price': 35.00,
            'supplier': 'Schneider',
            'qr_code': 'QR-ELC-002'
        },
        {
            'part_number': 'HVAC-002',
            'part_name': 'Klima Kumandası',
            'description': 'Oda kliması kumandası',
            'category': 'HVAC',
            'warehouse_location': 'workshop',
            'current_stock': 12,
            'minimum_stock': 8,
            'unit_price': 120.00,
            'supplier': 'Mitsubishi',
            'qr_code': 'QR-HVAC-002'
        }
    ]
    
    await db.spare_parts.delete_many({'tenant_id': tenant_id})
    
    for part in spare_parts:
        part['id'] = str(uuid.uuid4())
        part['tenant_id'] = tenant_id
        part['last_restocked'] = datetime.now(timezone.utc) - timedelta(days=15)
        part['created_at'] = datetime.now(timezone.utc)
        part['updated_at'] = datetime.now(timezone.utc)
        await db.spare_parts.insert_one(part)
    
    print(f"✅ Created {len(spare_parts)} spare parts")
    
    # 3. Create Sample Assets/Equipment
    print("\n🏢 Creating Assets...")
    
    assets = [
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': 'Klima - Oda 101',
            'asset_type': 'HVAC',
            'location': 'Room 101',
            'model': 'Daikin VRV',
            'serial_number': 'DKN-2023-001',
            'installation_date': datetime.now(timezone.utc) - timedelta(days=365),
            'warranty_expiry': datetime.now(timezone.utc) + timedelta(days=365),
            'created_at': datetime.now(timezone.utc)
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': 'Elektrik Panosu - Kat 1',
            'asset_type': 'Electrical',
            'location': 'Floor 1',
            'model': 'Schneider Electric Panel',
            'serial_number': 'SCH-2023-001',
            'installation_date': datetime.now(timezone.utc) - timedelta(days=730),
            'warranty_expiry': datetime.now(timezone.utc) - timedelta(days=365),
            'created_at': datetime.now(timezone.utc)
        }
    ]
    
    await db.assets.delete_many({'tenant_id': tenant_id})
    
    for asset in assets:
        await db.assets.insert_one(asset)
    
    print(f"✅ Created {len(assets)} assets")
    
    # 4. Create Maintenance History
    print("\n📊 Creating Maintenance History...")
    
    histories = []
    for i in range(10):
        asset = assets[i % len(assets)]
        days_ago = 30 + (i * 15)
        
        histories.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'asset_id': asset['id'],
            'asset_name': asset['name'],
            'task_id': str(uuid.uuid4()),
            'maintenance_type': 'corrective' if i % 3 == 0 else 'preventive',
            'description': f'Bakım işlemi {i + 1} - {asset["name"]}',
            'parts_cost': 50.0 + (i * 10),
            'labor_cost': 100.0 + (i * 20),
            'total_cost': 150.0 + (i * 30),
            'technician': 'Ahmet Yılmaz' if i % 2 == 0 else 'Mehmet Kaya',
            'completed_at': datetime.now(timezone.utc) - timedelta(days=days_ago),
            'downtime_minutes': 30 + (i * 5),
            'notes': f'Demo bakım kaydı {i + 1}',
            'created_at': datetime.now(timezone.utc) - timedelta(days=days_ago)
        })
    
    await db.asset_maintenance_history.delete_many({'tenant_id': tenant_id})
    
    for history in histories:
        await db.asset_maintenance_history.insert_one(history)
    
    print(f"✅ Created {len(histories)} maintenance history records")
    
    # 5. Create Planned Maintenance
    print("\n📅 Creating Planned Maintenance...")
    
    planned = []
    for i, asset in enumerate(assets):
        # Some overdue, some upcoming
        days_offset = -5 if i % 2 == 0 else 7
        
        planned.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'asset_id': asset['id'],
            'asset_name': asset['name'],
            'maintenance_type': 'preventive',
            'frequency_days': 90,
            'last_maintenance': datetime.now(timezone.utc) - timedelta(days=85),
            'next_maintenance': datetime.now(timezone.utc) + timedelta(days=days_offset),
            'estimated_duration_minutes': 120,
            'assigned_to': 'Ahmet Yılmaz',
            'is_active': True,
            'notes': f'Periyodik bakım - {asset["name"]}',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        })
    
    await db.planned_maintenance.delete_many({'tenant_id': tenant_id})
    
    for plan in planned:
        await db.planned_maintenance.insert_one(plan)
    
    print(f"✅ Created {len(planned)} planned maintenance items")
    
    print("\n✅ Demo data creation complete!")
    print("\n📊 Summary:")
    print(f"   - SLA Configurations: {len(sla_configs)}")
    print(f"   - Spare Parts: {len(spare_parts)} (2 low stock)")
    print(f"   - Assets: {len(assets)}")
    print(f"   - Maintenance History: {len(histories)}")
    print(f"   - Planned Maintenance: {len(planned)}")
    print("\n🎉 You can now test the Technical Maintenance features!")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(create_demo_data())
