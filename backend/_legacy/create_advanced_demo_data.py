"""
Advanced Demo Data Generator
- Guest preferences & history
- Special requests
- Booking sources
- Multi-room bookings
- Message automation flows
- Room assignments with timing
- POS orders
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime, timedelta
import random
import uuid

async def create_advanced_demo_data():
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    client = AsyncIOMotorClient(mongo_url)
    db = client['hotel_pms']
    
    print("🚀 Creating Advanced Demo Data...")
    
    # 1. GUEST PREFERENCES
    print("\n1️⃣ Creating Guest Preferences...")
    preferences = []
    pref_categories = [
        {'category': 'Room', 'options': ['High floor', 'Low floor', 'Away from elevator', 'Near elevator']},
        {'category': 'Pillow', 'options': ['Soft pillow', 'Firm pillow', 'Feather pillow', 'Memory foam']},
        {'category': 'Temperature', 'options': ['Warm', 'Cool', 'Standard']},
        {'category': 'Minibar', 'options': ['Stocked', 'Empty', 'No alcohol']},
        {'category': 'Newspaper', 'options': ['Daily', 'Weekend only', 'None']}
    ]
    
    for i in range(20):
        guest_id = f"guest_{i+1}"
        # 2-3 preferences per guest
        for _ in range(random.randint(2, 3)):
            cat = random.choice(pref_categories)
            preferences.append({
                'id': str(uuid.uuid4()),
                'guest_id': guest_id,
                'category': cat['category'],
                'preference': random.choice(cat['options']),
                'notes': random.choice(['', '', 'Very important', 'If available']),
                'tenant_id': 'demo_hotel'
            })
    
    await db.guest_preferences.delete_many({'tenant_id': 'demo_hotel'})
    if preferences:
        await db.guest_preferences.insert_many(preferences)
    print(f"   ✅ {len(preferences)} preferences created")
    
    # 2. SPECIAL REQUESTS
    print("\n2️⃣ Creating Special Requests...")
    requests = []
    request_types = [
        {'type': 'Room Setup', 'desc': 'Extra bed required'},
        {'type': 'Room Setup', 'desc': 'Baby cot needed'},
        {'type': 'Dietary', 'desc': 'Vegetarian meals only'},
        {'type': 'Accessibility', 'desc': 'Wheelchair accessible room'},
        {'type': 'Celebration', 'desc': 'Anniversary - flowers and cake'},
        {'type': 'Transportation', 'desc': 'Airport pickup requested'},
        {'type': 'Early Check-in', 'desc': 'Arrival at 10 AM'},
        {'type': 'Late Checkout', 'desc': 'Departure at 3 PM'}
    ]
    
    for i in range(15):
        booking_id = f"booking_{i+1}"
        req = random.choice(request_types)
        requests.append({
            'id': str(uuid.uuid4()),
            'booking_id': booking_id,
            'request_type': req['type'],
            'description': req['desc'],
            'priority': random.choice(['normal', 'high', 'urgent']),
            'status': random.choice(['pending', 'confirmed', 'completed']),
            'created_at': datetime.now() - timedelta(days=random.randint(0, 10)),
            'tenant_id': 'demo_hotel'
        })
    
    await db.special_requests.delete_many({'tenant_id': 'demo_hotel'})
    if requests:
        await db.special_requests.insert_many(requests)
    print(f"   ✅ {len(requests)} special requests created")
    
    # 3. BOOKING SOURCES
    print("\n3️⃣ Creating Booking Sources...")
    sources = []
    source_types = [
        {'type': 'OTA', 'names': ['Booking.com', 'Expedia', 'Airbnb', 'Hotels.com'], 'commission': 15-20},
        {'type': 'Website', 'names': ['Direct Website'], 'commission': 0},
        {'type': 'Corporate', 'names': ['Acme Corp', 'Tech Inc', 'Finance Ltd'], 'commission': 10},
        {'type': 'Walk-in', 'names': ['Walk-in'], 'commission': 0}
    ]
    
    for i in range(30):
        source_cat = random.choice(source_types)
        sources.append({
            'id': str(uuid.uuid4()),
            'booking_id': f"booking_{i+1}",
            'source_type': source_cat['type'],
            'source_name': random.choice(source_cat['names']),
            'commission_rate': random.uniform(source_cat['commission'][0], source_cat['commission'][1]) if isinstance(source_cat['commission'], tuple) else source_cat['commission'],
            'reference_number': f"REF-{random.randint(1000, 9999)}",
            'tenant_id': 'demo_hotel'
        })
    
    await db.booking_sources.delete_many({'tenant_id': 'demo_hotel'})
    if sources:
        await db.booking_sources.insert_many(sources)
    print(f"   ✅ {len(sources)} booking sources created")
    
    # 4. MESSAGE AUTOMATION FLOWS
    print("\n4️⃣ Creating Message Automation Flows...")
    flows = [
        {
            'id': str(uuid.uuid4()),
            'name': 'Pre Check-in Reminder',
            'trigger': 'pre_checkin',
            'template_id': 'welcome_template',
            'delay_hours': -24,
            'channel': 'whatsapp',
            'active': True,
            'description': 'Send 24 hours before check-in',
            'tenant_id': 'demo_hotel'
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Post Checkout Survey',
            'trigger': 'post_checkout',
            'template_id': 'feedback_template',
            'delay_hours': 2,
            'channel': 'email',
            'active': True,
            'description': 'Send 2 hours after checkout',
            'tenant_id': 'demo_hotel'
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Late Checkout Reminder',
            'trigger': 'checkout_day',
            'template_id': 'checkout_template',
            'delay_hours': -2,
            'channel': 'sms',
            'active': True,
            'description': 'Send 2 hours before checkout',
            'tenant_id': 'demo_hotel'
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Welcome Message',
            'trigger': 'checkin_complete',
            'template_id': 'welcome_template',
            'delay_hours': 0,
            'channel': 'whatsapp',
            'active': True,
            'description': 'Send immediately after check-in',
            'tenant_id': 'demo_hotel'
        }
    ]
    
    await db.message_flows.delete_many({'tenant_id': 'demo_hotel'})
    await db.message_flows.insert_many(flows)
    print(f"   ✅ {len(flows)} automation flows created")
    
    # 5. ROOM ASSIGNMENTS WITH CLEANING TIMES
    print("\n5️⃣ Creating Room Assignments...")
    assignments = []
    staff_ids = [f"staff_{i+1}" for i in range(6)]
    
    for day_offset in range(7):  # Last 7 days
        date = datetime.now() - timedelta(days=day_offset)
        for room_num in range(1, 21):  # 20 rooms
            staff_id = random.choice(staff_ids)
            cleaning_time = random.randint(18, 45)  # minutes
            
            assignments.append({
                'id': str(uuid.uuid4()),
                'staff_id': staff_id,
                'room_id': f"room_{room_num}",
                'room_number': str(100 + room_num),
                'date': date.isoformat(),
                'start_time': (date + timedelta(hours=9, minutes=random.randint(0, 180))).isoformat(),
                'end_time': None if day_offset == 0 else (date + timedelta(hours=9, minutes=cleaning_time)).isoformat(),
                'cleaning_duration': None if day_offset == 0 else cleaning_time,
                'status': 'pending' if day_offset == 0 else 'completed',
                'tenant_id': 'demo_hotel'
            })
    
    await db.room_assignments.delete_many({'tenant_id': 'demo_hotel'})
    await db.room_assignments.insert_many(assignments)
    print(f"   ✅ {len(assignments)} room assignments created")
    
    # 6. POS ORDERS
    print("\n6️⃣ Creating POS Orders...")
    orders = []
    menu_items = [
        {'name': 'Caesar Salad', 'price': 12.00, 'category': 'Appetizer'},
        {'name': 'Grilled Salmon', 'price': 28.00, 'category': 'Main'},
        {'name': 'Beef Tenderloin', 'price': 35.00, 'category': 'Main'},
        {'name': 'Tiramisu', 'price': 9.00, 'category': 'Dessert'},
        {'name': 'House Wine', 'price': 8.00, 'category': 'Beverage'}
    ]
    
    for i in range(50):  # 50 orders
        items = []
        for _ in range(random.randint(2, 5)):
            item = random.choice(menu_items)
            qty = random.randint(1, 3)
            items.append({
                'item_name': item['name'],
                'category': item['category'],
                'quantity': qty,
                'price': item['price'],
                'subtotal': item['price'] * qty
            })
        
        subtotal = sum(item['subtotal'] for item in items)
        tax = subtotal * 0.1
        total = subtotal + tax
        
        orders.append({
            'id': str(uuid.uuid4()),
            'order_number': f"ORD-{1000 + i}",
            'table_id': f"table_{random.randint(1, 20)}",
            'items': items,
            'subtotal': round(subtotal, 2),
            'tax': round(tax, 2),
            'total': round(total, 2),
            'status': random.choice(['pending', 'preparing', 'served', 'completed']),
            'created_at': datetime.now() - timedelta(hours=random.randint(0, 48)),
            'tenant_id': 'demo_hotel'
        })
    
    await db.pos_orders.delete_many({'tenant_id': 'demo_hotel'})
    await db.pos_orders.insert_many(orders)
    print(f"   ✅ {len(orders)} POS orders created")
    
    # 7. GUEST TAGS & VIP/BLACKLIST
    print("\n7️⃣ Updating Guest Tags...")
    guest_updates = [
        {'id': 'guest_1', 'tags': ['VIP', 'Repeat Guest'], 'vip': True, 'blacklisted': False},
        {'id': 'guest_2', 'tags': ['Corporate'], 'vip': False, 'blacklisted': False},
        {'id': 'guest_3', 'tags': ['Blacklist', 'Payment Issues'], 'vip': False, 'blacklisted': True},
        {'id': 'guest_4', 'tags': ['VIP', 'Anniversary'], 'vip': True, 'blacklisted': False},
        {'id': 'guest_5', 'tags': ['Loyalty Member'], 'vip': False, 'blacklisted': False}
    ]
    
    for guest in guest_updates:
        await db.guests.update_one(
            {'id': guest['id']},
            {'$set': {
                'tags': guest['tags'],
                'vip': guest['vip'],
                'blacklisted': guest['blacklisted'],
                'updated_at': datetime.now()
            }},
            upsert=True
        )
    
    print(f"   ✅ {len(guest_updates)} guests tagged")
    
    print("\n" + "="*60)
    print("✅ ALL ADVANCED DEMO DATA CREATED!")
    print("="*60)
    print(f"""
    📊 Summary:
    - Guest Preferences: {len(preferences)}
    - Special Requests: {len(requests)}
    - Booking Sources: {len(sources)}
    - Automation Flows: {len(flows)}
    - Room Assignments: {len(assignments)} (7 days)
    - POS Orders: {len(orders)}
    - Tagged Guests: {len(guest_updates)}
    """)

if __name__ == "__main__":
    asyncio.run(create_advanced_demo_data())
