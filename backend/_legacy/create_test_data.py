"""
Create comprehensive test data for PMS system
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime, timedelta, timezone
import uuid

async def create_test_data():
    # Connect to MongoDB
    mongo_url = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
    client = AsyncIOMotorClient(mongo_url)
    db = client['pms_db']
    
    tenant_id = "test-hotel-001"
    
    print("🏨 Creating Test Hotel Data...")
    
    # 1. Create Test Hotel
    {
        'id': tenant_id,
        'name': 'Grand Emerald Hotel',
        'address': '123 Luxury Avenue',
        'city': 'New York',
        'country': 'USA',
        'phone': '+1-555-0100',
        'email': 'info@grandemerald.com',
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    # 2. Create Rooms (30 rooms, multiple types)
    rooms = []
    room_types = {
        'Standard': {'price': 150, 'count': 10, 'floor_start': 1},
        'Deluxe': {'price': 220, 'count': 10, 'floor_start': 2},
        'Suite': {'price': 350, 'count': 8, 'floor_start': 3},
        'Presidential': {'price': 650, 'count': 2, 'floor_start': 4}
    }
    
    room_number = 101
    for room_type, config in room_types.items():
        for i in range(config['count']):
            floor = config['floor_start'] + (i // 4)
            rooms.append({
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'room_number': str(room_number),
                'room_type': room_type,
                'floor': floor,
                'capacity': 2 if room_type == 'Standard' else 3 if room_type == 'Deluxe' else 4,
                'base_price': config['price'],
                'status': 'available',
                'amenities': ['WiFi', 'TV', 'AC', 'Mini Bar'] + (['Balcony'] if room_type != 'Standard' else []),
                'view': 'city' if i % 2 == 0 else 'ocean',
                'smoking': False,
                'created_at': datetime.now(timezone.utc).isoformat()
            })
            room_number += 1
    
    print(f"✅ Created {len(rooms)} rooms")
    
    # 3. Create Test Guests (different loyalty tiers)
    guests = [
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': 'John Smith',
            'email': 'john.smith@email.com',
            'phone': '+1-555-0101',
            'country': 'USA',
            'id_number': 'PASS123456',
            'loyalty_tier': 'vip',
            'loyalty_points': 5000,
            'tags': ['VIP', 'High-value', 'Repeat-guest'],
            'notes': [],
            'created_at': datetime.now(timezone.utc).isoformat()
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': 'Emma Johnson',
            'email': 'emma.johnson@email.com',
            'phone': '+1-555-0102',
            'country': 'UK',
            'id_number': 'PASS789012',
            'loyalty_tier': 'gold',
            'loyalty_points': 2500,
            'tags': ['Gold', 'Business-traveler'],
            'notes': [],
            'created_at': datetime.now(timezone.utc).isoformat()
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': 'Michael Chen',
            'email': 'michael.chen@email.com',
            'phone': '+1-555-0103',
            'country': 'China',
            'id_number': 'PASS345678',
            'loyalty_tier': 'silver',
            'loyalty_points': 1200,
            'tags': ['Silver', 'Leisure'],
            'notes': [],
            'created_at': datetime.now(timezone.utc).isoformat()
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': 'Sarah Williams',
            'email': 'sarah.williams@email.com',
            'phone': '+1-555-0104',
            'country': 'USA',
            'id_number': 'PASS901234',
            'loyalty_tier': 'standard',
            'loyalty_points': 300,
            'tags': ['First-time'],
            'notes': [],
            'created_at': datetime.now(timezone.utc).isoformat()
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': 'David Martinez',
            'email': 'david.martinez@email.com',
            'phone': '+1-555-0105',
            'country': 'Spain',
            'id_number': 'PASS567890',
            'loyalty_tier': 'platinum',
            'loyalty_points': 8000,
            'tags': ['Platinum', 'Long-stay', 'High-value'],
            'notes': [],
            'created_at': datetime.now(timezone.utc).isoformat()
        }
    ]
    
    print(f"✅ Created {len(guests)} test guests with different loyalty tiers")
    
    # 4. Create Companies for Corporate Bookings
    companies = [
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': 'Tech Corp International',
            'email': 'bookings@techcorp.com',
            'phone': '+1-555-0201',
            'address': '456 Corporate Plaza',
            'tax_number': 'TAX123456',
            'contracted_rate': 'corporate_rate',
            'discount_pct': 15,
            'status': 'active',
            'created_at': datetime.now(timezone.utc).isoformat()
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': 'Global Consulting Group',
            'email': 'travel@globalconsult.com',
            'phone': '+1-555-0202',
            'address': '789 Business Center',
            'tax_number': 'TAX789012',
            'contracted_rate': 'negotiated_rate',
            'discount_pct': 20,
            'status': 'active',
            'created_at': datetime.now(timezone.utc).isoformat()
        }
    ]
    
    print(f"✅ Created {len(companies)} companies")
    
    # 5. Create Bookings (past, current, future)
    today = datetime.now(timezone.utc).date()
    bookings = []
    
    # Past bookings for loyalty guests (to build history)
    past_dates = [
        (today - timedelta(days=90), 3),
        (today - timedelta(days=60), 2),
        (today - timedelta(days=30), 4),
    ]
    
    for guest_idx, guest in enumerate(guests[:3]):  # First 3 guests have history
        for past_date, nights in past_dates:
            check_in = datetime.combine(past_date, datetime.min.time())
            check_out = check_in + timedelta(days=nights)
            room = rooms[guest_idx * 3]
            
            bookings.append({
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'guest_id': guest['id'],
                'guest_name': guest['name'],
                'room_id': room['id'],
                'room_number': room['room_number'],
                'check_in': check_in.isoformat(),
                'check_out': check_out.isoformat(),
                'adults': 2,
                'children': 0,
                'children_ages': [],
                'guests_count': 2,
                'total_amount': room['base_price'] * nights,
                'paid_amount': room['base_price'] * nights,
                'base_rate': room['base_price'],
                'status': 'checked_out',
                'channel': 'direct',
                'rate_plan': 'Standard',
                'market_segment': 'leisure',
                'ota_channel': None,
                'created_at': (check_in - timedelta(days=15)).isoformat()
            })
    
    # Current bookings (checked in)
    for guest in guests[:2]:
        check_in = datetime.combine(today - timedelta(days=1), datetime.min.time())
        check_out = check_in + timedelta(days=3)
        room = rooms[10]
        
        bookings.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'guest_id': guest['id'],
            'guest_name': guest['name'],
            'room_id': room['id'],
            'room_number': room['room_number'],
            'check_in': check_in.isoformat(),
            'check_out': check_out.isoformat(),
            'adults': 2,
            'children': 0,
            'children_ages': [],
            'guests_count': 2,
            'total_amount': room['base_price'] * 3,
            'paid_amount': 0,
            'base_rate': room['base_price'],
            'status': 'checked_in',
            'channel': 'direct',
            'rate_plan': 'Standard',
            'market_segment': 'business',
            'ota_channel': None,
            'created_at': (check_in - timedelta(days=10)).isoformat()
        })
    
    # Future bookings (confirmed)
    future_dates = [
        (today + timedelta(days=2), 2, 'booking_com'),
        (today + timedelta(days=5), 3, 'expedia'),
        (today + timedelta(days=7), 4, None),
        (today + timedelta(days=10), 2, 'airbnb'),
    ]
    
    for idx, (future_date, nights, ota) in enumerate(future_dates):
        guest = guests[idx % len(guests)]
        check_in = datetime.combine(future_date, datetime.min.time())
        check_out = check_in + timedelta(days=nights)
        room = rooms[15 + idx]
        
        commission_pct = 15 if ota else 0
        
        bookings.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'guest_id': guest['id'],
            'guest_name': guest['name'],
            'room_id': room['id'],
            'room_number': room['room_number'],
            'check_in': check_in.isoformat(),
            'check_out': check_out.isoformat(),
            'adults': 2,
            'children': 1 if idx % 2 == 0 else 0,
            'children_ages': [5] if idx % 2 == 0 else [],
            'guests_count': 3 if idx % 2 == 0 else 2,
            'total_amount': room['base_price'] * nights,
            'paid_amount': 0,
            'base_rate': room['base_price'],
            'status': 'confirmed',
            'channel': 'ota' if ota else 'direct',
            'rate_plan': 'Standard',
            'market_segment': 'leisure',
            'ota_channel': ota,
            'commission_pct': commission_pct,
            'payment_model': 'agency' if ota else None,
            'virtual_card_provided': False,
            'created_at': (check_in - timedelta(days=20)).isoformat()
        })
    
    # Group booking (5+ rooms)
    group_check_in = datetime.combine(today + timedelta(days=15), datetime.min.time())
    group_check_out = group_check_in + timedelta(days=3)
    company = companies[0]
    
    for i in range(6):
        guest = guests[i % len(guests)]
        room = rooms[20 + i]
        
        bookings.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'guest_id': guest['id'],
            'guest_name': guest['name'],
            'room_id': room['id'],
            'room_number': room['room_number'],
            'check_in': group_check_in.isoformat(),
            'check_out': group_check_out.isoformat(),
            'adults': 1,
            'children': 0,
            'children_ages': [],
            'guests_count': 1,
            'total_amount': room['base_price'] * 3 * 0.85,  # 15% corporate discount
            'paid_amount': 0,
            'base_rate': room['base_price'],
            'status': 'confirmed',
            'channel': 'direct',
            'rate_plan': 'Corporate',
            'market_segment': 'corporate',
            'company_id': company['id'],
            'contracted_rate': 'corporate_rate',
            'rate_type': 'negotiated',
            'ota_channel': None,
            'created_at': (group_check_in - timedelta(days=30)).isoformat()
        })
    
    print(f"✅ Created {len(bookings)} bookings (past, current, future, group)")
    
    # 6. Create Housekeeping Tasks
    tasks = []
    for room in rooms[:5]:
        tasks.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'room_id': room['id'],
            'room_number': room['room_number'],
            'task_type': 'cleaning',
            'priority': 'normal',
            'status': 'pending',
            'assigned_to': 'Housekeeping Staff',
            'notes': 'Standard cleaning',
            'created_at': datetime.now(timezone.utc).isoformat()
        })
    
    print(f"✅ Created {len(tasks)} housekeeping tasks")
    
    # 7. Create Room Blocks
    room_blocks = [
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'room_id': rooms[5]['id'],
            'type': 'maintenance',
            'reason': 'AC Repair',
            'details': 'Scheduled maintenance for air conditioning unit',
            'start_date': (today + timedelta(days=3)).isoformat(),
            'end_date': (today + timedelta(days=5)).isoformat(),
            'allow_sell': False,
            'created_by': 'admin',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'status': 'active'
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'room_id': rooms[6]['id'],
            'type': 'out_of_order',
            'reason': 'Plumbing Issue',
            'details': 'Major plumbing repair required',
            'start_date': today.isoformat(),
            'end_date': (today + timedelta(days=7)).isoformat(),
            'allow_sell': False,
            'created_by': 'admin',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'status': 'active'
        }
    ]
    
    print(f"✅ Created {len(room_blocks)} room blocks")
    
    # Insert all data
    print("\n📝 Inserting data into MongoDB...")
    
    try:
        # Clear existing test data
        await db.rooms.delete_many({'tenant_id': tenant_id})
        await db.guests.delete_many({'tenant_id': tenant_id})
        await db.bookings.delete_many({'tenant_id': tenant_id})
        await db.companies.delete_many({'tenant_id': tenant_id})
        await db.housekeeping_tasks.delete_many({'tenant_id': tenant_id})
        await db.room_blocks.delete_many({'tenant_id': tenant_id})
        
        # Insert new data
        await db.rooms.insert_many(rooms)
        await db.guests.insert_many(guests)
        await db.bookings.insert_many(bookings)
        await db.companies.insert_many(companies)
        await db.housekeeping_tasks.insert_many(tasks)
        await db.room_blocks.insert_many(room_blocks)
        
        print("\n✅ All test data created successfully!")
        print("\n" + "="*60)
        print("🎉 TEST HOTEL READY!")
        print("="*60)
        print("\n🏨 Hotel: Grand Emerald Hotel")
        print(f"📍 Tenant ID: {tenant_id}")
        print("\n📊 Data Summary:")
        print(f"   • Rooms: {len(rooms)} (Standard, Deluxe, Suite, Presidential)")
        print(f"   • Guests: {len(guests)} (VIP, Platinum, Gold, Silver, Standard)")
        print(f"   • Bookings: {len(bookings)} (Past, Current, Future, Group)")
        print(f"   • Companies: {len(companies)} (Corporate clients)")
        print(f"   • Housekeeping Tasks: {len(tasks)}")
        print(f"   • Room Blocks: {len(room_blocks)}")
        
        print("\n👥 Test Guests (for 360° Profile & Loyalty Testing):")
        for guest in guests:
            print(f"   • {guest['name']} - {guest['loyalty_tier'].upper()} - {guest['email']}")
        
        print("\n🔑 Login Credentials:")
        print(f"   Create a user with tenant_id: {tenant_id}")
        print("   Or use existing admin account")
        
        print("\n🧪 Test Features:")
        print("   ✅ Guest 360° Profile (check LTV, booking history)")
        print("   ✅ Loyalty Tiers (VIP to Standard)")
        print("   ✅ Upsell AI (generate offers for confirmed bookings)")
        print("   ✅ Room Blocks (Maintenance & Out of Order)")
        print("   ✅ Group Bookings (6-room corporate group)")
        print("   ✅ OTA Channel Distribution (Booking.com, Expedia, Airbnb)")
        print("   ✅ Housekeeping Management")
        print("   ✅ Calendar View (past, present, future bookings)")
        
        print("\n" + "="*60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(create_test_data())
