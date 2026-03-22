"""
Comprehensive Demo Data Generator for Desktop Features
- Revenue breakdown data
- AI Upsell products
- Cost management entries
- POS menu items and tables
- Housekeeping staff assignments
- Messaging templates
- Folio split/segment data
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime, timedelta
import random
import uuid

async def create_comprehensive_demo_data():
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    client = AsyncIOMotorClient(mongo_url)
    db = client['hotel_pms']
    
    print("🚀 Creating Comprehensive Demo Data...")
    
    # 1. REVENUE BREAKDOWN DATA
    print("\n1️⃣ Creating Revenue Breakdown Data...")
    revenue_categories = []
    categories = [
        {'name': 'Room Revenue', 'amount': 125000, 'percentage': 65},
        {'name': 'F&B Revenue', 'amount': 35000, 'percentage': 18},
        {'name': 'Spa & Wellness', 'amount': 15000, 'percentage': 8},
        {'name': 'Laundry', 'amount': 8000, 'percentage': 4},
        {'name': 'Minibar', 'amount': 6000, 'percentage': 3},
        {'name': 'Other Services', 'amount': 4000, 'percentage': 2}
    ]
    
    for cat in categories:
        revenue_categories.append({
            'id': str(uuid.uuid4()),
            'category': cat['name'],
            'amount': cat['amount'],
            'percentage': cat['percentage'],
            'month': datetime.now().strftime('%Y-%m'),
            'tenant_id': 'demo_hotel'
        })
    
    await db.revenue_breakdown.delete_many({'tenant_id': 'demo_hotel'})
    if revenue_categories:
        await db.revenue_breakdown.insert_many(revenue_categories)
    print(f"   ✅ {len(revenue_categories)} revenue categories created")
    
    # 2. AI UPSELL PRODUCTS
    print("\n2️⃣ Creating AI Upsell Products...")
    upsell_products = [
        {
            'id': str(uuid.uuid4()),
            'name': 'Late Checkout (2pm)',
            'description': 'Extend your stay until 2pm without rushing',
            'price': 35.00,
            'category': 'room_upgrade',
            'image_url': 'https://images.unsplash.com/photo-1582719508461-905c673771fd?w=400',
            'popular': True,
            'ai_score': 0.92,
            'tenant_id': 'demo_hotel'
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Room Upgrade - Deluxe',
            'description': 'Upgrade to our spacious Deluxe room with city view',
            'price': 55.00,
            'category': 'room_upgrade',
            'image_url': 'https://images.unsplash.com/photo-1590490360182-c33d57733427?w=400',
            'popular': True,
            'ai_score': 0.88,
            'tenant_id': 'demo_hotel'
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Spa Treatment Package',
            'description': '60-min massage + sauna access',
            'price': 85.00,
            'category': 'spa',
            'image_url': 'https://images.unsplash.com/photo-1544161515-4ab6ce6db874?w=400',
            'popular': True,
            'ai_score': 0.85,
            'tenant_id': 'demo_hotel'
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Breakfast Package (2 days)',
            'description': 'Continental breakfast for 2 guests, 2 days',
            'price': 45.00,
            'category': 'food',
            'image_url': 'https://images.unsplash.com/photo-1533089860892-a7c6f0a88666?w=400',
            'popular': False,
            'ai_score': 0.78,
            'tenant_id': 'demo_hotel'
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Airport Transfer',
            'description': 'Private car transfer to/from airport',
            'price': 65.00,
            'category': 'transport',
            'image_url': 'https://images.unsplash.com/photo-1449965408869-eaa3f722e40d?w=400',
            'popular': False,
            'ai_score': 0.72,
            'tenant_id': 'demo_hotel'
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Wine & Cheese Platter',
            'description': 'Premium selection delivered to your room',
            'price': 38.00,
            'category': 'food',
            'image_url': 'https://images.unsplash.com/photo-1452195100486-9cc805987862?w=400',
            'popular': False,
            'ai_score': 0.68,
            'tenant_id': 'demo_hotel'
        }
    ]
    
    await db.upsell_products.delete_many({'tenant_id': 'demo_hotel'})
    await db.upsell_products.insert_many(upsell_products)
    print(f"   ✅ {len(upsell_products)} upsell products created")
    
    # 3. COST MANAGEMENT ENTRIES
    print("\n3️⃣ Creating Cost Management Data...")
    cost_entries = []
    cost_categories = [
        {'name': 'Housekeeping Supplies', 'monthly': 8500},
        {'name': 'F&B Ingredients', 'monthly': 12000},
        {'name': 'Utilities', 'monthly': 15000},
        {'name': 'Staff Salaries', 'monthly': 45000},
        {'name': 'Maintenance & Repairs', 'monthly': 6500},
        {'name': 'Marketing', 'monthly': 5000},
        {'name': 'IT & Software', 'monthly': 3500},
        {'name': 'Insurance', 'monthly': 4000}
    ]
    
    for i in range(30):
        date = datetime.now() - timedelta(days=i)
        for cat in random.sample(cost_categories, random.randint(3, 6)):
            daily_cost = (cat['monthly'] / 30) * random.uniform(0.8, 1.2)
            cost_entries.append({
                'id': str(uuid.uuid4()),
                'date': date,
                'category': cat['name'],
                'amount': round(daily_cost, 2),
                'description': f"Daily {cat['name'].lower()} expenses",
                'tenant_id': 'demo_hotel',
                'created_at': datetime.now()
            })
    
    await db.cost_entries.delete_many({'tenant_id': 'demo_hotel'})
    await db.cost_entries.insert_many(cost_entries)
    print(f"   ✅ {len(cost_entries)} cost entries created")
    
    # 4. POS MENU ITEMS & TABLES
    print("\n4️⃣ Creating POS Menu & Tables...")
    
    # Menu items
    menu_items = [
        # Appetizers
        {'name': 'Caesar Salad', 'category': 'Appetizer', 'price': 12.00, 'cost': 4.50},
        {'name': 'Bruschetta', 'category': 'Appetizer', 'price': 10.00, 'cost': 3.50},
        {'name': 'Soup of the Day', 'category': 'Appetizer', 'price': 8.00, 'cost': 2.50},
        # Mains
        {'name': 'Grilled Salmon', 'category': 'Main Course', 'price': 28.00, 'cost': 12.00},
        {'name': 'Beef Tenderloin', 'category': 'Main Course', 'price': 35.00, 'cost': 15.00},
        {'name': 'Chicken Parmesan', 'category': 'Main Course', 'price': 22.00, 'cost': 9.00},
        {'name': 'Vegetarian Pasta', 'category': 'Main Course', 'price': 18.00, 'cost': 6.00},
        # Desserts
        {'name': 'Tiramisu', 'category': 'Dessert', 'price': 9.00, 'cost': 3.00},
        {'name': 'Chocolate Lava Cake', 'category': 'Dessert', 'price': 10.00, 'cost': 3.50},
        # Drinks
        {'name': 'House Wine (Glass)', 'category': 'Beverage', 'price': 8.00, 'cost': 2.50},
        {'name': 'Craft Beer', 'category': 'Beverage', 'price': 7.00, 'cost': 2.00},
        {'name': 'Soft Drink', 'category': 'Beverage', 'price': 4.00, 'cost': 0.80},
        {'name': 'Fresh Juice', 'category': 'Beverage', 'price': 6.00, 'cost': 1.50}
    ]
    
    menu_items_with_id = []
    for item in menu_items:
        menu_items_with_id.append({
            'id': str(uuid.uuid4()),
            'outlet_id': 'main_restaurant',
            'available': True,
            'tenant_id': 'demo_hotel',
            **item
        })
    
    await db.menu_items.delete_many({'tenant_id': 'demo_hotel'})
    await db.menu_items.insert_many(menu_items_with_id)
    print(f"   ✅ {len(menu_items_with_id)} menu items created")
    
    # Restaurant tables
    tables = []
    for i in range(1, 21):
        tables.append({
            'id': str(uuid.uuid4()),
            'table_number': i,
            'capacity': random.choice([2, 4, 6, 8]),
            'status': random.choice(['available', 'occupied', 'reserved']),
            'outlet_id': 'main_restaurant',
            'tenant_id': 'demo_hotel'
        })
    
    await db.restaurant_tables.delete_many({'tenant_id': 'demo_hotel'})
    await db.restaurant_tables.insert_many(tables)
    print(f"   ✅ {len(tables)} restaurant tables created")
    
    # 5. HOUSEKEEPING STAFF
    print("\n5️⃣ Creating Housekeeping Staff Data...")
    hk_staff = [
        {'name': 'Maria Garcia', 'role': 'Room Attendant', 'shift': 'morning', 'efficiency': 92},
        {'name': 'John Smith', 'role': 'Room Attendant', 'shift': 'morning', 'efficiency': 88},
        {'name': 'Sarah Johnson', 'role': 'Room Attendant', 'shift': 'afternoon', 'efficiency': 90},
        {'name': 'Ahmed Hassan', 'role': 'Room Attendant', 'shift': 'afternoon', 'efficiency': 85},
        {'name': 'Lisa Chen', 'role': 'Supervisor', 'shift': 'morning', 'efficiency': 95},
        {'name': 'Carlos Rodriguez', 'role': 'Room Attendant', 'shift': 'morning', 'efficiency': 87}
    ]
    
    staff_with_id = []
    for staff in hk_staff:
        staff_with_id.append({
            'id': str(uuid.uuid4()),
            'email': f"{staff['name'].lower().replace(' ', '.')}@hotel.com",
            'active': True,
            'assigned_rooms': random.randint(10, 15),
            'tenant_id': 'demo_hotel',
            **staff
        })
    
    await db.housekeeping_staff.delete_many({'tenant_id': 'demo_hotel'})
    await db.housekeeping_staff.insert_many(staff_with_id)
    print(f"   ✅ {len(staff_with_id)} housekeeping staff created")
    
    # 6. MESSAGING TEMPLATES
    print("\n6️⃣ Creating Messaging Templates...")
    templates = [
        {
            'id': str(uuid.uuid4()),
            'name': 'Welcome Message',
            'type': 'whatsapp',
            'content': 'Welcome to our hotel! Your room {room_number} is ready. Check-in time: {checkin_time}',
            'variables': ['room_number', 'checkin_time'],
            'tenant_id': 'demo_hotel'
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Checkout Reminder',
            'type': 'sms',
            'content': 'Reminder: Checkout today at 12pm. Need late checkout? Reply YES.',
            'variables': [],
            'tenant_id': 'demo_hotel'
        },
        {
            'id': str(uuid.uuid4()),
            'name': 'Booking Confirmation',
            'type': 'email',
            'content': 'Your booking is confirmed for {dates}. Confirmation: {conf_number}',
            'variables': ['dates', 'conf_number'],
            'tenant_id': 'demo_hotel'
        }
    ]
    
    await db.messaging_templates.delete_many({'tenant_id': 'demo_hotel'})
    await db.messaging_templates.insert_many(templates)
    print(f"   ✅ {len(templates)} messaging templates created")
    
    print("\n" + "="*60)
    print("✅ ALL DEMO DATA CREATED SUCCESSFULLY!")
    print("="*60)
    print(f"""
    📊 Summary:
    - Revenue Breakdown: {len(revenue_categories)} categories
    - AI Upsell Products: {len(upsell_products)} products
    - Cost Entries: {len(cost_entries)} entries (30 days)
    - Menu Items: {len(menu_items_with_id)} items
    - Restaurant Tables: {len(tables)} tables
    - Housekeeping Staff: {len(staff_with_id)} staff members
    - Messaging Templates: {len(templates)} templates
    """)

if __name__ == "__main__":
    asyncio.run(create_comprehensive_demo_data())
