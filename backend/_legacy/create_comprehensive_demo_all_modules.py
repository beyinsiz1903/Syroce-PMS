"""
Comprehensive Demo Data Generator for All Modules
Creates realistic demo data for all hotel PMS modules including last year's data
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime, timedelta, timezone
import random
import uuid
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Database connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Sample data
FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Thompson", "White",
    "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young"
]

NATIONALITIES = ["USA", "UK", "Germany", "France", "Spain", "Italy", "Japan", "China", "Canada", "Australia"]

ROOM_TYPES = ["Standard", "Deluxe", "Suite", "Executive Suite", "Presidential Suite"]

OTA_CHANNELS = ["booking_com", "expedia", "airbnb", "agoda", "hotels_com"]

SPECIAL_REQUESTS = [
    "Late check-in requested",
    "Early check-out needed",
    "High floor room preferred",
    "Quiet room away from elevator",
    "Extra pillows needed",
    "Hypoallergenic bedding required",
    "Connecting rooms for family",
    "Airport transfer needed",
    "Baby cot required",
    "Vegetarian breakfast preference"
]

MENU_ITEMS = [
    {"name": "Breakfast Buffet", "category": "food", "price": 25.0},
    {"name": "Club Sandwich", "category": "food", "price": 15.0},
    {"name": "Caesar Salad", "category": "food", "price": 12.0},
    {"name": "Grilled Salmon", "category": "food", "price": 28.0},
    {"name": "Beef Burger", "category": "food", "price": 18.0},
    {"name": "Pasta Carbonara", "category": "food", "price": 16.0},
    {"name": "Margherita Pizza", "category": "food", "price": 14.0},
    {"name": "Chicken Tikka", "category": "food", "price": 20.0},
    {"name": "Coffee", "category": "beverage", "price": 5.0},
    {"name": "Tea", "category": "beverage", "price": 4.0},
    {"name": "Orange Juice", "category": "beverage", "price": 6.0},
    {"name": "Coca Cola", "category": "beverage", "price": 4.0},
    {"name": "Mineral Water", "category": "beverage", "price": 3.0},
    {"name": "Beer", "category": "alcohol", "price": 8.0},
    {"name": "Wine Glass", "category": "alcohol", "price": 12.0},
    {"name": "Whiskey", "category": "alcohol", "price": 15.0},
    {"name": "Cocktail", "category": "alcohol", "price": 14.0},
    {"name": "Cheesecake", "category": "dessert", "price": 8.0},
    {"name": "Tiramisu", "category": "dessert", "price": 9.0},
    {"name": "Ice Cream", "category": "dessert", "price": 6.0},
    {"name": "Bruschetta", "category": "appetizer", "price": 10.0},
    {"name": "Spring Rolls", "category": "appetizer", "price": 9.0},
    {"name": "Soup of the Day", "category": "appetizer", "price": 7.0}
]

HOUSEKEEPING_STAFF = ["Sarah Johnson", "Maria Garcia", "Emma Wilson", "Lisa Chen", "Anna Martinez"]

COMPETITOR_HOTELS = [
    {
        "name": "Grand Hotel Downtown",
        "avg_rate": 150.0,
        "occupancy_estimate": 78.0,
        "rating": 4.3,
        "features": ["Free WiFi", "Breakfast", "Pool", "Spa", "Gym", "Restaurant"]
    },
    {
        "name": "City Plaza Hotel",
        "avg_rate": 130.0,
        "occupancy_estimate": 82.0,
        "rating": 4.5,
        "features": ["Free WiFi", "Breakfast", "Pool", "Business Center", "Parking"]
    },
    {
        "name": "Seaside Resort",
        "avg_rate": 180.0,
        "occupancy_estimate": 70.0,
        "rating": 4.2,
        "features": ["Free WiFi", "Breakfast", "Pool", "Spa", "Beach Access", "Restaurant"]
    },
    {
        "name": "Business Inn Express",
        "avg_rate": 110.0,
        "occupancy_estimate": 85.0,
        "rating": 4.0,
        "features": ["Free WiFi", "Breakfast", "Business Center", "Gym", "Parking"]
    },
    {
        "name": "Luxury Suites Hotel",
        "avg_rate": 220.0,
        "occupancy_estimate": 65.0,
        "rating": 4.6,
        "features": ["Free WiFi", "Breakfast", "Pool", "Spa", "Gym", "Restaurant", "Concierge"]
    }
]

async def get_tenant_id():
    """Get the first tenant from database"""
    tenant = await db.tenants.find_one()
    if not tenant:
        # Create a tenant if none exists
        tenant_id = str(uuid.uuid4())
        await db.tenants.insert_one({
            'id': tenant_id,
            'property_name': 'Demo Grand Hotel',
            'property_type': 'hotel',
            'total_rooms': 50,
            'subscription_status': 'active',
            'created_at': datetime.now(timezone.utc)
        })
        return tenant_id
    return tenant['id']

async def create_rooms(tenant_id):
    """Create hotel rooms"""
    print("Creating rooms...")
    
    # Check if rooms already exist
    existing_count = await db.rooms.count_documents({'tenant_id': tenant_id})
    if existing_count > 0:
        print(f"Rooms already exist ({existing_count}). Skipping...")
        return
    
    rooms = []
    room_num = 101
    
    for floor in range(1, 6):  # 5 floors
        for room in range(1, 11):  # 10 rooms per floor
            room_type = random.choice(ROOM_TYPES)
            base_prices = {
                "Standard": 100,
                "Deluxe": 150,
                "Suite": 250,
                "Executive Suite": 350,
                "Presidential Suite": 500
            }
            
            rooms.append({
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'room_number': str(room_num),
                'room_type': room_type,
                'floor': floor,
                'capacity': 2 if room_type == "Standard" else 4,
                'base_price': base_prices[room_type],
                'status': random.choice(['available', 'available', 'available', 'occupied', 'dirty']),
                'amenities': ['WiFi', 'TV', 'AC', 'Mini Bar'],
                'created_at': datetime.now(timezone.utc)
            })
            room_num += 1
    
    await db.rooms.insert_many(rooms)
    print(f"Created {len(rooms)} rooms")

async def create_guests(tenant_id, count=100):
    """Create guest profiles"""
    print(f"Creating {count} guests...")
    
    # Check existing
    existing_count = await db.guests.count_documents({'tenant_id': tenant_id})
    if existing_count >= count:
        print(f"Guests already exist ({existing_count}). Skipping...")
        return
    
    guests = []
    for i in range(count):
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        
        guests.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': f"{first_name} {last_name}",
            'email': f"{first_name.lower()}.{last_name.lower()}@email.com",
            'phone': f"+1-555-{random.randint(1000, 9999)}",
            'id_number': f"ID{random.randint(100000, 999999)}",
            'nationality': random.choice(NATIONALITIES),
            'vip_status': random.choice([True, False, False, False, False]),
            'loyalty_points': random.randint(0, 5000),
            'total_stays': random.randint(0, 20),
            'total_spend': random.uniform(500, 15000),
            'created_at': datetime.now(timezone.utc) - timedelta(days=random.randint(1, 730))
        })
    
    await db.guests.insert_many(guests)
    print(f"Created {len(guests)} guests")

async def create_guest_preferences_and_tags(tenant_id):
    """Create guest preferences and tags"""
    print("Creating guest preferences and tags...")
    
    guests = await db.guests.find({'tenant_id': tenant_id}).to_list(length=1000)
    
    preferences = []
    tags = []
    
    for guest in guests[:50]:  # Add preferences for 50 guests
        preferences.append({
            'guest_id': guest['id'],
            'tenant_id': tenant_id,
            'pillow_type': random.choice(['soft', 'firm', 'extra_firm', None]),
            'floor_preference': random.choice(['low', 'middle', 'high', 'no_preference']),
            'room_temperature': random.choice(['cool', 'moderate', 'warm']),
            'smoking': random.choice([True, False, False, False]),
            'special_needs': random.choice([None, 'Wheelchair accessible', 'Extra towels', 'Quiet room']),
            'dietary_restrictions': random.choice([None, 'Vegetarian', 'Vegan', 'Gluten-free', 'Halal']),
            'newspaper_preference': random.choice([None, 'Wall Street Journal', 'Financial Times', 'Local Paper'])
        })
        
        # Add tags
        possible_tags = ['vip', 'blacklist', 'honeymoon', 'anniversary', 'business_traveler', 'frequent_guest', 'high_spender']
        guest_tags = random.sample(possible_tags, k=random.randint(0, 3))
        
        if guest_tags:
            tags.append({
                'guest_id': guest['id'],
                'tenant_id': tenant_id,
                'tags': guest_tags
            })
    
    if preferences:
        await db.guest_preferences.insert_many(preferences)
        print(f"Created {len(preferences)} guest preferences")
    
    if tags:
        await db.guest_tags.insert_many(tags)
        print(f"Created {len(tags)} guest tags")

async def create_historical_bookings(tenant_id):
    """Create bookings for the last year"""
    print("Creating historical bookings (last year)...")
    
    guests = await db.guests.find({'tenant_id': tenant_id}).to_list(length=1000)
    rooms = await db.rooms.find({'tenant_id': tenant_id}).to_list(length=1000)
    
    if not guests or not rooms:
        print("No guests or rooms found. Skipping bookings...")
        return
    
    bookings = []
    
    # Create bookings for the past year
    start_date = datetime.now(timezone.utc) - timedelta(days=365)
    
    for day_offset in range(0, 365, 3):  # Every 3 days
        booking_date = start_date + timedelta(days=day_offset)
        
        # Create 5-15 bookings per day
        num_bookings = random.randint(5, 15)
        
        for _ in range(num_bookings):
            guest = random.choice(guests)
            room = random.choice(rooms)
            
            check_in = booking_date
            nights = random.randint(1, 7)
            check_out = check_in + timedelta(days=nights)
            
            # Determine status based on date
            if check_out < datetime.now(timezone.utc):
                status = 'checked_out'
            elif check_in < datetime.now(timezone.utc) < check_out:
                status = 'checked_in'
            else:
                status = random.choice(['confirmed', 'guaranteed'])
            
            # OTA or direct
            is_ota = random.choice([True, False, False])
            ota_channel = random.choice(OTA_CHANNELS) if is_ota else None
            
            booking_id = str(uuid.uuid4())
            
            bookings.append({
                'id': booking_id,
                'tenant_id': tenant_id,
                'guest_id': guest['id'],
                'room_id': room['id'],
                'check_in': check_in,
                'check_out': check_out,
                'adults': random.randint(1, 3),
                'children': random.randint(0, 2),
                'children_ages': [],
                'guests_count': random.randint(1, 4),
                'total_amount': room['base_price'] * nights,
                'base_rate': room['base_price'],
                'paid_amount': 0 if status in ['confirmed', 'guaranteed'] else room['base_price'] * nights,
                'status': status,
                'channel': 'direct' if not is_ota else ota_channel,
                'special_requests': random.choice(SPECIAL_REQUESTS + [None, None, None]),
                'ota_channel': ota_channel,
                'ota_confirmation': f"OTA{random.randint(100000, 999999)}" if is_ota else None,
                'commission_pct': random.uniform(15, 25) if is_ota else None,
                'payment_model': random.choice(['agency', 'hotel_collect']) if is_ota else None,
                'checked_in_at': check_in if status in ['checked_in', 'checked_out'] else None,
                'checked_out_at': check_out if status == 'checked_out' else None,
                'created_at': check_in - timedelta(days=random.randint(1, 30))
            })
    
    if bookings:
        # Insert in batches
        batch_size = 100
        for i in range(0, len(bookings), batch_size):
            batch = bookings[i:i+batch_size]
            await db.bookings.insert_many(batch)
        print(f"Created {len(bookings)} historical bookings")

async def create_future_bookings(tenant_id):
    """Create bookings for the next 90 days"""
    print("Creating future bookings (next 90 days)...")
    
    guests = await db.guests.find({'tenant_id': tenant_id}).to_list(length=1000)
    rooms = await db.rooms.find({'tenant_id': tenant_id}).to_list(length=1000)
    
    bookings = []
    
    # Create bookings for next 90 days
    for day_offset in range(1, 91):
        booking_date = datetime.now(timezone.utc) + timedelta(days=day_offset)
        
        # Create 3-12 bookings per day
        num_bookings = random.randint(3, 12)
        
        for _ in range(num_bookings):
            guest = random.choice(guests)
            room = random.choice(rooms)
            
            check_in = booking_date
            nights = random.randint(1, 7)
            check_out = check_in + timedelta(days=nights)
            
            is_ota = random.choice([True, False, False])
            ota_channel = random.choice(OTA_CHANNELS) if is_ota else None
            
            bookings.append({
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'guest_id': guest['id'],
                'room_id': room['id'],
                'check_in': check_in,
                'check_out': check_out,
                'adults': random.randint(1, 3),
                'children': random.randint(0, 2),
                'children_ages': [],
                'guests_count': random.randint(1, 4),
                'total_amount': room['base_price'] * nights,
                'base_rate': room['base_price'],
                'paid_amount': 0,
                'status': 'confirmed',
                'channel': 'direct' if not is_ota else ota_channel,
                'special_requests': random.choice(SPECIAL_REQUESTS + [None, None]),
                'ota_channel': ota_channel,
                'ota_confirmation': f"OTA{random.randint(100000, 999999)}" if is_ota else None,
                'commission_pct': random.uniform(15, 25) if is_ota else None,
                'payment_model': random.choice(['agency', 'hotel_collect']) if is_ota else None,
                'created_at': datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30))
            })
    
    if bookings:
        batch_size = 100
        for i in range(0, len(bookings), batch_size):
            batch = bookings[i:i+batch_size]
            await db.bookings.insert_many(batch)
        print(f"Created {len(bookings)} future bookings")

async def create_folios_and_charges(tenant_id):
    """Create folios and charges for checked-in and checked-out bookings"""
    print("Creating folios and charges...")
    
    bookings = await db.bookings.find({
        'tenant_id': tenant_id,
        'status': {'$in': ['checked_in', 'checked_out']}
    }).to_list(length=5000)
    
    folios = []
    charges = []
    payments = []
    
    folio_counter = 1
    
    for booking in bookings:
        # Create guest folio
        folio_id = str(uuid.uuid4())
        folio_number = f"F-2024-{folio_counter:05d}"
        folio_counter += 1
        
        folios.append({
            'id': folio_id,
            'tenant_id': tenant_id,
            'booking_id': booking['id'],
            'folio_number': folio_number,
            'folio_type': 'guest',
            'status': 'closed' if booking['status'] == 'checked_out' else 'open',
            'guest_id': booking['guest_id'],
            'balance': 0.0,
            'created_at': booking['checked_in_at'] or booking['check_in'],
            'closed_at': booking['checked_out_at'] if booking['status'] == 'checked_out' else None
        })
        
        # Add room charges (one per night)
        nights = (booking['check_out'] - booking['check_in']).days
        for night in range(nights):
            charges.append({
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'folio_id': folio_id,
                'charge_category': 'room',
                'description': f"Room charge - Night {night + 1}",
                'quantity': 1,
                'unit_price': booking['base_rate'],
                'amount': booking['base_rate'],
                'tax_amount': booking['base_rate'] * 0.18,
                'total': booking['base_rate'] * 1.18,
                'voided': False,
                'posted_at': booking['check_in'] + timedelta(days=night),
                'posted_by': 'system'
            })
        
        # Add random F&B charges
        num_fb_charges = random.randint(0, 5)
        for _ in range(num_fb_charges):
            item = random.choice(MENU_ITEMS)
            quantity = random.randint(1, 3)
            amount = item['price'] * quantity
            
            charges.append({
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'folio_id': folio_id,
                'charge_category': item['category'] if item['category'] != 'appetizer' else 'food',
                'description': f"{item['name']} x {quantity}",
                'quantity': quantity,
                'unit_price': item['price'],
                'amount': amount,
                'tax_amount': amount * 0.18,
                'total': amount * 1.18,
                'voided': False,
                'posted_at': booking['check_in'] + timedelta(hours=random.randint(1, 48)),
                'posted_by': 'pos_system'
            })
        
        # Add payment if checked out
        if booking['status'] == 'checked_out':
            total_charges = sum(c['total'] for c in charges if c['folio_id'] == folio_id)
            
            payments.append({
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'folio_id': folio_id,
                'payment_type': 'final',
                'payment_method': random.choice(['cash', 'card', 'bank_transfer']),
                'amount': total_charges,
                'currency': 'USD',
                'reference': f"PAY{random.randint(100000, 999999)}",
                'posted_at': booking['checked_out_at'],
                'posted_by': 'front_desk'
            })
    
    if folios:
        await db.folios.insert_many(folios)
        print(f"Created {len(folios)} folios")
    
    if charges:
        batch_size = 500
        for i in range(0, len(charges), batch_size):
            batch = charges[i:i+batch_size]
            await db.folio_charges.insert_many(batch)
        print(f"Created {len(charges)} folio charges")
    
    if payments:
        await db.payments.insert_many(payments)
        print(f"Created {len(payments)} payments")

async def create_extra_charges(tenant_id):
    """Create extra charges for some bookings"""
    print("Creating extra charges...")
    
    bookings = await db.bookings.find({
        'tenant_id': tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
    }).limit(30).to_list(length=30)
    
    extra_charges = []
    
    charge_types = [
        ("Airport Transfer", 50.0),
        ("Late Checkout", 30.0),
        ("Extra Bed", 25.0),
        ("Pet Fee", 20.0),
        ("Parking", 15.0),
        ("Early Checkin", 20.0),
        ("Room Upgrade", 50.0)
    ]
    
    for booking in bookings:
        if random.choice([True, False]):
            charge_name, amount = random.choice(charge_types)
            extra_charges.append({
                'id': str(uuid.uuid4()),
                'booking_id': booking['id'],
                'tenant_id': tenant_id,
                'charge_name': charge_name,
                'charge_amount': amount,
                'notes': random.choice([None, 'Requested at booking', 'Added at check-in']),
                'charge_date': datetime.now(timezone.utc)
            })
    
    if extra_charges:
        await db.extra_charges.insert_many(extra_charges)
        print(f"Created {len(extra_charges)} extra charges")

async def create_multi_room_reservations(tenant_id):
    """Create multi-room reservations"""
    print("Creating multi-room reservations...")
    
    # Get confirmed bookings for same dates
    bookings = await db.bookings.find({
        'tenant_id': tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed']}
    }).limit(50).to_list(length=50)
    
    multi_rooms = []
    
    # Group bookings by similar check-in dates
    date_groups = {}
    for booking in bookings:
        date_key = booking['check_in'].date()
        if date_key not in date_groups:
            date_groups[date_key] = []
        date_groups[date_key].append(booking)
    
    # Create multi-room reservations for groups with 2+ bookings
    for date_key, group_bookings in date_groups.items():
        if len(group_bookings) >= 2:
            num_rooms = min(len(group_bookings), random.randint(2, 5))
            selected_bookings = random.sample(group_bookings, num_rooms)
            
            multi_rooms.append({
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'group_name': random.choice([
                    'Johnson Family Reunion',
                    'Corporate Training Group',
                    'Wedding Party',
                    'Sports Team',
                    'Conference Attendees'
                ]),
                'primary_booking_id': selected_bookings[0]['id'],
                'related_booking_ids': [b['id'] for b in selected_bookings[1:]],
                'total_rooms': num_rooms,
                'created_at': datetime.now(timezone.utc)
            })
    
    if multi_rooms:
        await db.multi_room_bookings.insert_many(multi_rooms)
        print(f"Created {len(multi_rooms)} multi-room reservations")

async def create_housekeeping_tasks(tenant_id):
    """Create housekeeping tasks and history"""
    print("Creating housekeeping tasks...")
    
    rooms = await db.rooms.find({'tenant_id': tenant_id}).to_list(length=1000)
    
    tasks = []
    
    # Create current tasks (pending/in_progress)
    for _ in range(20):
        room = random.choice(rooms)
        staff = random.choice(HOUSEKEEPING_STAFF)
        status = random.choice(['pending', 'pending', 'in_progress'])
        
        started_at = datetime.now(timezone.utc) - timedelta(minutes=random.randint(10, 60)) if status == 'in_progress' else None
        
        tasks.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'room_id': room['id'],
            'task_type': random.choice(['cleaning', 'inspection', 'deep_cleaning']),
            'assigned_to': staff,
            'status': status,
            'priority': random.choice(['normal', 'normal', 'high', 'urgent']),
            'notes': random.choice([None, 'VIP guest', 'Extra attention needed', 'Quick turnover']),
            'started_at': started_at,
            'completed_at': None,
            'created_at': datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 24))
        })
    
    # Create completed tasks (last 60 days)
    for day_offset in range(60):
        task_date = datetime.now(timezone.utc) - timedelta(days=day_offset)
        
        # 10-20 completed tasks per day
        num_tasks = random.randint(10, 20)
        
        for _ in range(num_tasks):
            room = random.choice(rooms)
            staff = random.choice(HOUSEKEEPING_STAFF)
            
            # Random duration between 15-45 minutes
            duration = random.randint(15, 45)
            started_at = task_date - timedelta(minutes=duration)
            completed_at = task_date
            
            tasks.append({
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'room_id': room['id'],
                'task_type': random.choice(['cleaning', 'cleaning', 'cleaning', 'inspection', 'maintenance']),
                'assigned_to': staff,
                'status': 'completed',
                'priority': random.choice(['normal', 'normal', 'high']),
                'notes': None,
                'started_at': started_at,
                'completed_at': completed_at,
                'created_at': started_at - timedelta(hours=1)
            })
    
    if tasks:
        batch_size = 500
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            await db.housekeeping_tasks.insert_many(batch)
        print(f"Created {len(tasks)} housekeeping tasks")

async def create_pos_menu_and_orders(tenant_id):
    """Create POS menu items and orders"""
    print("Creating POS menu items and orders...")
    
    # Create menu items
    menu_items = []
    for item in MENU_ITEMS:
        menu_items.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'item_name': item['name'],
            'category': item['category'],
            'unit_price': item['price'],
            'available': True
        })
    
    await db.pos_menu_items.insert_many(menu_items)
    print(f"Created {len(menu_items)} menu items")
    
    # Create orders
    bookings = await db.bookings.find({
        'tenant_id': tenant_id,
        'status': {'$in': ['checked_in', 'checked_out']}
    }).limit(100).to_list(length=100)
    
    orders = []
    
    for booking in bookings:
        # 0-3 orders per booking
        num_orders = random.randint(0, 3)
        
        for _ in range(num_orders):
            # 1-5 items per order
            num_items = random.randint(1, 5)
            order_items = []
            subtotal = 0
            
            for _ in range(num_items):
                item = random.choice(menu_items)
                quantity = random.randint(1, 3)
                total_price = item['unit_price'] * quantity
                subtotal += total_price
                
                order_items.append({
                    'item_id': item['id'],
                    'item_name': item['item_name'],
                    'category': item['category'],
                    'quantity': quantity,
                    'unit_price': item['unit_price'],
                    'total_price': total_price
                })
            
            tax = subtotal * 0.18
            total = subtotal + tax
            
            orders.append({
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'booking_id': booking['id'],
                'guest_id': booking['guest_id'],
                'folio_id': None,
                'order_items': order_items,
                'subtotal': subtotal,
                'tax_amount': tax,
                'total_amount': total,
                'status': 'completed',
                'created_at': booking['check_in'] + timedelta(hours=random.randint(1, 48))
            })
    
    if orders:
        await db.pos_orders.insert_many(orders)
        print(f"Created {len(orders)} POS orders")

async def create_message_templates(tenant_id):
    """Create message templates"""
    print("Creating message templates...")
    
    templates = [
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'template_name': 'Pre-Arrival Welcome',
            'message_type': 'whatsapp',
            'trigger': 'pre_arrival',
            'message_content': 'Hello {guest_name}! We are excited to welcome you tomorrow. Your room {room_number} will be ready for you at 2 PM. See you soon!',
            'variables': ['{guest_name}', '{room_number}'],
            'active': True
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'template_name': 'Check-in Reminder',
            'message_type': 'sms',
            'trigger': 'check_in_reminder',
            'message_content': 'Good morning {guest_name}! Your room {room_number} is ready. Check-in time is 2 PM. We look forward to your arrival!',
            'variables': ['{guest_name}', '{room_number}'],
            'active': True
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'template_name': 'Post-Checkout Thank You',
            'message_type': 'email',
            'trigger': 'post_checkout',
            'message_content': 'Thank you for staying with us, {guest_name}! We hope you enjoyed your stay. We would love to welcome you back soon.',
            'variables': ['{guest_name}'],
            'active': True
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'template_name': 'Birthday Greeting',
            'message_type': 'whatsapp',
            'trigger': 'birthday',
            'message_content': 'Happy Birthday {guest_name}! 🎉 We wish you a wonderful day and hope to see you soon at our hotel!',
            'variables': ['{guest_name}'],
            'active': True
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'template_name': 'Anniversary Wishes',
            'message_type': 'email',
            'trigger': 'anniversary',
            'message_content': 'Happy Anniversary {guest_name}! 💕 Wishing you many more happy years together. We would be honored to host you for a special celebration!',
            'variables': ['{guest_name}'],
            'active': True
        }
    ]
    
    await db.message_templates.insert_many(templates)
    print(f"Created {len(templates)} message templates")

async def create_competitors(tenant_id):
    """Create competitor data"""
    print("Creating competitor data...")
    
    competitors = []
    for comp in COMPETITOR_HOTELS:
        competitors.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': comp['name'],
            'avg_rate': comp['avg_rate'],
            'occupancy_estimate': comp['occupancy_estimate'],
            'rating': comp['rating'],
            'features': comp['features']
        })
    
    await db.competitors.insert_many(competitors)
    print(f"Created {len(competitors)} competitors")

async def main():
    """Main function to create all demo data"""
    print("=" * 80)
    print("COMPREHENSIVE DEMO DATA GENERATOR")
    print("Creating demo data for ALL modules including last year's data...")
    print("=" * 80)
    
    tenant_id = await get_tenant_id()
    print(f"\nUsing tenant_id: {tenant_id}")
    
    # Create all data
    await create_rooms(tenant_id)
    await create_guests(tenant_id, count=150)
    await create_guest_preferences_and_tags(tenant_id)
    await create_historical_bookings(tenant_id)
    await create_future_bookings(tenant_id)
    await create_folios_and_charges(tenant_id)
    await create_extra_charges(tenant_id)
    await create_multi_room_reservations(tenant_id)
    await create_housekeeping_tasks(tenant_id)
    await create_pos_menu_and_orders(tenant_id)
    await create_message_templates(tenant_id)
    await create_competitors(tenant_id)
    
    # Print summary
    print("\n" + "=" * 80)
    print("DEMO DATA CREATION SUMMARY")
    print("=" * 80)
    
    counts = {
        'rooms': await db.rooms.count_documents({'tenant_id': tenant_id}),
        'guests': await db.guests.count_documents({'tenant_id': tenant_id}),
        'bookings': await db.bookings.count_documents({'tenant_id': tenant_id}),
        'folios': await db.folios.count_documents({'tenant_id': tenant_id}),
        'charges': await db.folio_charges.count_documents({'tenant_id': tenant_id}),
        'payments': await db.payments.count_documents({'tenant_id': tenant_id}),
        'extra_charges': await db.extra_charges.count_documents({'tenant_id': tenant_id}),
        'multi_rooms': await db.multi_room_bookings.count_documents({'tenant_id': tenant_id}),
        'hk_tasks': await db.housekeeping_tasks.count_documents({'tenant_id': tenant_id}),
        'guest_preferences': await db.guest_preferences.count_documents({'tenant_id': tenant_id}),
        'guest_tags': await db.guest_tags.count_documents({'tenant_id': tenant_id}),
        'pos_menu_items': await db.pos_menu_items.count_documents({'tenant_id': tenant_id}),
        'pos_orders': await db.pos_orders.count_documents({'tenant_id': tenant_id}),
        'message_templates': await db.message_templates.count_documents({'tenant_id': tenant_id}),
        'competitors': await db.competitors.count_documents({'tenant_id': tenant_id})
    }
    
    for key, value in counts.items():
        print(f"{key.replace('_', ' ').title()}: {value}")
    
    print("\n✅ ALL DEMO DATA CREATED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
