"""
Comprehensive Demo Data Seeding Script
Creates realistic hotel PMS data for testing all features
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
import random
import uuid

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# MongoDB connection
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'hotel_pms')
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Demo data constants
DEMO_TENANT_ID = "demo-tenant-001"
DEMO_TENANT_NAME = "Grand Hotel Demo"
DEMO_PASSWORD = "demo123"  # Will be hashed

# Demo users
DEMO_USERS = [
    {"email": "demo@hotel.com", "name": "Demo User", "role": "admin"},
    {"email": "admin@demo.com", "name": "Admin Demo", "role": "admin"},
    {"email": "manager@demo.com", "name": "Manager Demo", "role": "supervisor"},
    {"email": "frontdesk@demo.com", "name": "Front Desk Demo", "role": "front_desk"},
    {"email": "housekeeping@demo.com", "name": "Housekeeping Demo", "role": "housekeeping"},
]

# Room types and prices
ROOM_TYPES = [
    {"type": "Standard", "base_price": 100, "count": 20},
    {"type": "Deluxe", "base_price": 150, "count": 20},
    {"type": "Suite", "base_price": 250, "count": 10},
]

# Guest names pool
FIRST_NAMES = ["John", "Jane", "Michael", "Sarah", "David", "Emma", "Robert", "Lisa", "James", "Maria",
               "William", "Anna", "Richard", "Laura", "Thomas", "Sophie", "Charles", "Emily", "Daniel", "Olivia"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
              "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]

# Companies
COMPANIES = [
    {"name": "ABC Travel Agency", "code": "ABC001", "rate": 90, "payment_terms": "Net 30"},
    {"name": "XYZ Corporate", "code": "XYZ001", "rate": 95, "payment_terms": "Net 15"},
    {"name": "Global Tours Ltd", "code": "GLB001", "rate": 85, "payment_terms": "Net 45"},
    {"name": "Business Travel Co", "code": "BTC001", "rate": 100, "payment_terms": "Net 30"},
    {"name": "Vacation Planners", "code": "VCP001", "rate": 80, "payment_terms": "Net 60"},
]


def generate_id():
    """Generate unique ID"""
    return str(uuid.uuid4())


async def clear_demo_data():
    """Clear existing demo data"""
    print("🗑️  Clearing existing demo data...")
    
    # Delete demo tenant data
    await db.tenants.delete_many({"id": DEMO_TENANT_ID})
    await db.users.delete_many({"tenant_id": DEMO_TENANT_ID})
    await db.companies.delete_many({"tenant_id": DEMO_TENANT_ID})
    await db.rooms.delete_many({"tenant_id": DEMO_TENANT_ID})
    await db.guests.delete_many({"tenant_id": DEMO_TENANT_ID})
    await db.bookings.delete_many({"tenant_id": DEMO_TENANT_ID})
    await db.folios.delete_many({"tenant_id": DEMO_TENANT_ID})
    await db.folio_charges.delete_many({"tenant_id": DEMO_TENANT_ID})
    await db.payments.delete_many({"tenant_id": DEMO_TENANT_ID})
    await db.housekeeping_tasks.delete_many({"tenant_id": DEMO_TENANT_ID})
    await db.accounting_invoices.delete_many({"tenant_id": DEMO_TENANT_ID})
    await db.reviews.delete_many({"tenant_id": DEMO_TENANT_ID})
    await db.loyalty_programs.delete_many({"tenant_id": DEMO_TENANT_ID})
    await db.rms_competitors.delete_many({"tenant_id": DEMO_TENANT_ID})
    await db.linen_inventory.delete_many({"tenant_id": DEMO_TENANT_ID})
    
    print("✅ Demo data cleared")


async def create_demo_tenant():
    """Create demo tenant"""
    print("🏨 Creating demo tenant...")
    
    tenant = {
        "id": DEMO_TENANT_ID,
        "property_name": DEMO_TENANT_NAME,
        "property_type": "hotel",
        "contact_email": "info@grandhoteldemo.com",
        "contact_phone": "+1-555-0100",
        "address": "123 Hotel Street, New York, NY 10001",
        "total_rooms": 50,
        "subscription_status": "active",
        "location": "New York, NY",
        "amenities": ["WiFi", "Pool", "Gym", "Restaurant", "Spa"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.tenants.insert_one(tenant)
    print(f"✅ Tenant created: {DEMO_TENANT_NAME}")
    return tenant


async def create_demo_users():
    """Create demo users"""
    print("👥 Creating demo users...")
    
    hashed_password = pwd_context.hash(DEMO_PASSWORD)
    users = []
    
    for user_data in DEMO_USERS:
        user = {
            "id": generate_id(),
            "tenant_id": DEMO_TENANT_ID,
            "email": user_data["email"],
            "name": user_data["name"],
            "role": user_data["role"],
            "hashed_password": hashed_password,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_active": True
        }
        await db.users.insert_one(user)
        users.append(user)
        print(f"  ✓ User created: {user_data['email']} ({user_data['role']})")
    
    return users


async def create_companies():
    """Create demo companies"""
    print("🏢 Creating companies...")
    
    companies = []
    for company_data in COMPANIES:
        company = {
            "id": generate_id(),
            "tenant_id": DEMO_TENANT_ID,
            "name": company_data["name"],
            "corporate_code": company_data["code"],
            "tax_number": f"TAX-{random.randint(100000, 999999)}",
            "billing_address": f"{random.randint(100, 999)} Business Ave, NY",
            "contact_person": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
            "contact_email": f"contact@{company_data['code'].lower()}.com",
            "contact_phone": f"+1-555-{random.randint(1000, 9999)}",
            "contracted_rate": company_data["rate"],
            "default_rate_type": "corporate",
            "default_market_segment": "corporate",
            "payment_terms": company_data["payment_terms"],
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.companies.insert_one(company)
        companies.append(company)
        print(f"  ✓ Company: {company_data['name']}")
    
    return companies


async def create_rooms():
    """Create demo rooms"""
    print("🚪 Creating rooms...")
    
    rooms = []
    room_number = 101
    
    for room_type_data in ROOM_TYPES:
        for i in range(room_type_data["count"]):
            # Distribute statuses realistically
            if i < room_type_data["count"] * 0.6:  # 60% available
                status = "available"
            elif i < room_type_data["count"] * 0.7:  # 10% occupied
                status = "occupied"
            elif i < room_type_data["count"] * 0.8:  # 10% dirty
                status = "dirty"
            elif i < room_type_data["count"] * 0.9:  # 10% cleaning
                status = "cleaning"
            else:  # 10% inspected
                status = "inspected"
            
            room = {
                "id": generate_id(),
                "tenant_id": DEMO_TENANT_ID,
                "room_number": str(room_number),
                "room_type": room_type_data["type"],
                "floor": str(room_number // 100),
                "status": status,
                "base_price": room_type_data["base_price"],
                "max_occupancy": 2 if room_type_data["type"] == "Standard" else (3 if room_type_data["type"] == "Deluxe" else 4),
                "amenities": ["WiFi", "TV", "AC", "Minibar"] + (["Balcony"] if room_type_data["type"] in ["Deluxe", "Suite"] else []),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.rooms.insert_one(room)
            rooms.append(room)
            room_number += 1
    
    print(f"✅ Created {len(rooms)} rooms")
    return rooms


async def create_guests():
    """Create demo guests"""
    print("👤 Creating guests...")
    
    guests = []
    for i in range(120):
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        
        # Create loyalty tier distribution
        if i < 100:
            loyalty_tier = "bronze"
            loyalty_points = random.randint(0, 499)
        elif i < 115:
            loyalty_tier = "silver"
            loyalty_points = random.randint(500, 1499)
        elif i < 119:
            loyalty_tier = "gold"
            loyalty_points = random.randint(1500, 2999)
        else:
            loyalty_tier = "platinum"
            loyalty_points = random.randint(3000, 5000)
        
        guest = {
            "id": generate_id(),
            "tenant_id": DEMO_TENANT_ID,
            "first_name": first_name,
            "last_name": last_name,
            "email": f"{first_name.lower()}.{last_name.lower()}@email.com",
            "phone": f"+1-555-{random.randint(1000, 9999)}",
            "nationality": random.choice(["US", "UK", "CA", "AU", "DE", "FR", "ES", "IT"]),
            "passport_number": f"P{random.randint(10000000, 99999999)}",
            "date_of_birth": f"{random.randint(1960, 2000)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
            "address": f"{random.randint(100, 999)} Main St, City",
            "loyalty_tier": loyalty_tier,
            "loyalty_points": loyalty_points,
            "total_stays": random.randint(1, 20),
            "total_spend": random.randint(500, 10000),
            "preferences": {
                "room_type": random.choice(["high_floor", "low_floor", "quiet"]),
                "pillow_type": random.choice(["soft", "firm"]),
                "smoking": random.choice([True, False])
            },
            "tags": ["VIP"] if loyalty_tier in ["gold", "platinum"] else [],
            "created_at": (datetime.now(timezone.utc) - timedelta(days=random.randint(30, 730))).isoformat()
        }
        await db.guests.insert_one(guest)
        guests.append(guest)
    
    print(f"✅ Created {len(guests)} guests")
    return guests


async def create_bookings_and_folios(rooms, guests, companies, users):
    """Create comprehensive bookings with folios, charges, and payments"""
    print("📅 Creating bookings with folios...")
    
    users[0]
    bookings_created = 0
    
    # 1. Historical bookings (2024) - checked out
    print("  📊 Creating 2024 historical data...")
    for month in range(1, 13):  # All of 2024
        num_bookings = random.randint(15, 25)  # 15-25 bookings per month
        for _ in range(num_bookings):
            guest = random.choice(guests)
            room = random.choice([r for r in rooms if r["status"] != "maintenance"])
            
            check_in_date = datetime(2024, month, random.randint(1, 28), 14, 0, tzinfo=timezone.utc)
            nights = random.randint(1, 7)
            check_out_date = check_in_date + timedelta(days=nights)
            
            # Some are company bookings
            is_company = random.random() < 0.3
            company = random.choice(companies) if is_company else None
            
            booking_id = generate_id()
            booking = {
                "id": booking_id,
                "tenant_id": DEMO_TENANT_ID,
                "guest_id": guest["id"],
                "room_id": room["id"],
                "company_id": company["id"] if company else None,
                "check_in": check_in_date.isoformat(),
                "check_out": check_out_date.isoformat(),
                "status": "checked_out",
                "adults": random.randint(1, 2),
                "children": random.randint(0, 2),
                "guests_count": random.randint(1, 4),
                "rate_type": "corporate" if company else random.choice(["bar", "advance_purchase", "member"]),
                "market_segment": "corporate" if company else random.choice(["leisure", "business"]),
                "total_amount": (company["contracted_rate"] if company else room["base_price"]) * nights,
                "created_at": (check_in_date - timedelta(days=random.randint(7, 60))).isoformat(),
                "checked_in_at": check_in_date.isoformat(),
                "checked_out_at": check_out_date.isoformat()
            }
            await db.bookings.insert_one(booking)
            
            # Create guest folio
            guest_folio_id = generate_id()
            guest_folio = {
                "id": guest_folio_id,
                "tenant_id": DEMO_TENANT_ID,
                "booking_id": booking_id,
                "guest_id": guest["id"],
                "folio_number": f"F-2024-{bookings_created:05d}",
                "folio_type": "guest",
                "status": "closed",
                "created_at": check_in_date.isoformat(),
                "closed_at": check_out_date.isoformat()
            }
            await db.folios.insert_one(guest_folio)
            
            # Add room charges
            charge_id = generate_id()
            room_charge = {
                "id": charge_id,
                "tenant_id": DEMO_TENANT_ID,
                "folio_id": guest_folio_id,
                "charge_category": "room",
                "description": f"Room {room['room_number']} - {nights} nights",
                "quantity": nights,
                "unit_price": booking["total_amount"] / nights,
                "amount": booking["total_amount"],
                "tax_rate": 0.18,
                "tax_amount": booking["total_amount"] * 0.18,
                "total": booking["total_amount"] * 1.18,
                "posted_at": check_in_date.isoformat(),
                "voided": False
            }
            await db.folio_charges.insert_one(room_charge)
            
            # Add random F&B and minibar charges
            extra_charges = random.randint(0, 5)
            total_extra = 0
            for _ in range(extra_charges):
                charge_type = random.choice(["food_beverage", "minibar", "laundry", "spa"])
                charge_amount = random.uniform(10, 100)
                total_extra += charge_amount
                
                extra_charge_id = generate_id()
                extra_charge = {
                    "id": extra_charge_id,
                    "tenant_id": DEMO_TENANT_ID,
                    "folio_id": guest_folio_id,
                    "charge_category": charge_type,
                    "description": f"{charge_type.replace('_', ' ').title()} service",
                    "quantity": 1,
                    "unit_price": charge_amount,
                    "amount": charge_amount,
                    "tax_rate": 0.18,
                    "tax_amount": charge_amount * 0.18,
                    "total": charge_amount * 1.18,
                    "posted_at": (check_in_date + timedelta(days=random.randint(0, nights-1 if nights > 1 else 0))).isoformat(),
                    "voided": False
                }
                await db.folio_charges.insert_one(extra_charge)
            
            # Add payment
            total_charges = (booking["total_amount"] + total_extra) * 1.18
            payment_id = generate_id()
            payment = {
                "id": payment_id,
                "tenant_id": DEMO_TENANT_ID,
                "folio_id": guest_folio_id,
                "payment_method": random.choice(["card", "cash", "bank_transfer"]),
                "payment_type": "final",
                "amount": total_charges,
                "processed_at": check_out_date.isoformat(),
                "reference_number": f"PAY-{random.randint(100000, 999999)}"
            }
            await db.payments.insert_one(payment)
            
            # Company folio if applicable
            if company:
                company_folio_id = generate_id()
                company_folio = {
                    "id": company_folio_id,
                    "tenant_id": DEMO_TENANT_ID,
                    "booking_id": booking_id,
                    "company_id": company["id"],
                    "folio_number": f"F-2024-C-{bookings_created:05d}",
                    "folio_type": "company",
                    "status": "closed" if random.random() < 0.8 else "open",  # 20% still open
                    "created_at": check_in_date.isoformat(),
                    "closed_at": check_out_date.isoformat() if random.random() < 0.8 else None
                }
                await db.folios.insert_one(company_folio)
                
                # If open, create outstanding balance
                if company_folio["status"] == "open":
                    company_charge_id = generate_id()
                    company_charge = {
                        "id": company_charge_id,
                        "tenant_id": DEMO_TENANT_ID,
                        "folio_id": company_folio_id,
                        "charge_category": "room",
                        "description": f"Corporate booking - Room {room['room_number']}",
                        "quantity": nights,
                        "unit_price": company["contracted_rate"],
                        "amount": company["contracted_rate"] * nights,
                        "tax_rate": 0.18,
                        "tax_amount": company["contracted_rate"] * nights * 0.18,
                        "total": company["contracted_rate"] * nights * 1.18,
                        "posted_at": check_in_date.isoformat(),
                        "voided": False
                    }
                    await db.folio_charges.insert_one(company_charge)
            
            bookings_created += 1
    
    print(f"  ✓ Created {bookings_created} historical bookings (2024)")
    
    # 2. Current year bookings (2025) - mix of statuses
    print("  📊 Creating 2025 current year data...")
    current_bookings = 0
    
    # Past checked-out (Jan-Feb 2025)
    for month in range(1, 3):
        num_bookings = random.randint(10, 15)
        for _ in range(num_bookings):
            guest = random.choice(guests)
            room = random.choice(rooms)
            
            check_in_date = datetime(2025, month, random.randint(1, 28), 14, 0, tzinfo=timezone.utc)
            nights = random.randint(1, 5)
            check_out_date = check_in_date + timedelta(days=nights)
            
            booking_id = generate_id()
            booking = {
                "id": booking_id,
                "tenant_id": DEMO_TENANT_ID,
                "guest_id": guest["id"],
                "room_id": room["id"],
                "check_in": check_in_date.isoformat(),
                "check_out": check_out_date.isoformat(),
                "status": "checked_out",
                "adults": random.randint(1, 2),
                "children": 0,
                "guests_count": random.randint(1, 2),
                "rate_type": random.choice(["bar", "advance_purchase"]),
                "market_segment": "leisure",
                "total_amount": room["base_price"] * nights,
                "created_at": (check_in_date - timedelta(days=random.randint(7, 30))).isoformat(),
                "checked_in_at": check_in_date.isoformat(),
                "checked_out_at": check_out_date.isoformat()
            }
            await db.bookings.insert_one(booking)
            
            # Create closed folio with charges and payments
            guest_folio_id = generate_id()
            guest_folio = {
                "id": guest_folio_id,
                "tenant_id": DEMO_TENANT_ID,
                "booking_id": booking_id,
                "guest_id": guest["id"],
                "folio_number": f"F-2025-{current_bookings:05d}",
                "folio_type": "guest",
                "status": "closed",
                "created_at": check_in_date.isoformat(),
                "closed_at": check_out_date.isoformat()
            }
            await db.folios.insert_one(guest_folio)
            
            # Room charge
            charge_id = generate_id()
            room_charge = {
                "id": charge_id,
                "tenant_id": DEMO_TENANT_ID,
                "folio_id": guest_folio_id,
                "charge_category": "room",
                "description": f"Room {room['room_number']} - {nights} nights",
                "quantity": nights,
                "unit_price": room["base_price"],
                "amount": room["base_price"] * nights,
                "tax_rate": 0.18,
                "tax_amount": room["base_price"] * nights * 0.18,
                "total": room["base_price"] * nights * 1.18,
                "posted_at": check_in_date.isoformat(),
                "voided": False
            }
            await db.folio_charges.insert_one(room_charge)
            
            # Payment
            payment_id = generate_id()
            payment = {
                "id": payment_id,
                "tenant_id": DEMO_TENANT_ID,
                "folio_id": guest_folio_id,
                "payment_method": "card",
                "payment_type": "final",
                "amount": room["base_price"] * nights * 1.18,
                "processed_at": check_out_date.isoformat(),
                "reference_number": f"PAY-{random.randint(100000, 999999)}"
            }
            await db.payments.insert_one(payment)
            
            current_bookings += 1
    
    # Currently checked-in (use occupied rooms)
    occupied_rooms = [r for r in rooms if r["status"] == "occupied"]
    for room in occupied_rooms[:10]:  # 10 current guests
        guest = random.choice(guests)
        check_in_date = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 3))
        nights = random.randint(2, 7)
        check_out_date = check_in_date + timedelta(days=nights)
        
        booking_id = generate_id()
        booking = {
            "id": booking_id,
            "tenant_id": DEMO_TENANT_ID,
            "guest_id": guest["id"],
            "room_id": room["id"],
            "check_in": check_in_date.isoformat(),
            "check_out": check_out_date.isoformat(),
            "status": "checked_in",
            "adults": 2,
            "children": 0,
            "guests_count": 2,
            "rate_type": "bar",
            "market_segment": "leisure",
            "total_amount": room["base_price"] * nights,
            "created_at": (check_in_date - timedelta(days=10)).isoformat(),
            "checked_in_at": check_in_date.isoformat()
        }
        await db.bookings.insert_one(booking)
        
        # Create open folio with charges
        guest_folio_id = generate_id()
        guest_folio = {
            "id": guest_folio_id,
            "tenant_id": DEMO_TENANT_ID,
            "booking_id": booking_id,
            "guest_id": guest["id"],
            "folio_number": f"F-2025-{current_bookings:05d}",
            "folio_type": "guest",
            "status": "open",
            "created_at": check_in_date.isoformat()
        }
        await db.folios.insert_one(guest_folio)
        
        # Add room charges for nights stayed so far
        nights_so_far = (datetime.now(timezone.utc) - check_in_date).days + 1
        if nights_so_far > 0:
            charge_id = generate_id()
            room_charge = {
                "id": charge_id,
                "tenant_id": DEMO_TENANT_ID,
                "folio_id": guest_folio_id,
                "charge_category": "room",
                "description": f"Room {room['room_number']}",
                "quantity": nights_so_far,
                "unit_price": room["base_price"],
                "amount": room["base_price"] * nights_so_far,
                "tax_rate": 0.18,
                "tax_amount": room["base_price"] * nights_so_far * 0.18,
                "total": room["base_price"] * nights_so_far * 1.18,
                "posted_at": check_in_date.isoformat(),
                "voided": False
            }
            await db.folio_charges.insert_one(room_charge)
            
            # Add some F&B charges
            if random.random() < 0.7:
                fb_charge_id = generate_id()
                fb_amount = random.uniform(20, 80)
                fb_charge = {
                    "id": fb_charge_id,
                    "tenant_id": DEMO_TENANT_ID,
                    "folio_id": guest_folio_id,
                    "charge_category": "food_beverage",
                    "description": "Restaurant charges",
                    "quantity": 1,
                    "unit_price": fb_amount,
                    "amount": fb_amount,
                    "tax_rate": 0.18,
                    "tax_amount": fb_amount * 0.18,
                    "total": fb_amount * 1.18,
                    "posted_at": datetime.now(timezone.utc).isoformat(),
                    "voided": False
                }
                await db.folio_charges.insert_one(fb_charge)
        
        current_bookings += 1
    
    # Future confirmed bookings
    for i in range(20):
        guest = random.choice(guests)
        room = random.choice(rooms)
        check_in_date = datetime.now(timezone.utc) + timedelta(days=random.randint(1, 60))
        nights = random.randint(1, 5)
        check_out_date = check_in_date + timedelta(days=nights)
        
        booking_id = generate_id()
        booking = {
            "id": booking_id,
            "tenant_id": DEMO_TENANT_ID,
            "guest_id": guest["id"],
            "room_id": room["id"],
            "check_in": check_in_date.isoformat(),
            "check_out": check_out_date.isoformat(),
            "status": random.choice(["confirmed", "guaranteed"]),
            "adults": random.randint(1, 2),
            "children": random.randint(0, 1),
            "guests_count": random.randint(1, 3),
            "rate_type": random.choice(["bar", "advance_purchase", "member"]),
            "market_segment": random.choice(["leisure", "business"]),
            "total_amount": room["base_price"] * nights,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.bookings.insert_one(booking)
        current_bookings += 1
    
    print(f"  ✓ Created {current_bookings} current year bookings (2025)")
    print(f"✅ Total bookings: {bookings_created + current_bookings}")


async def create_housekeeping_data(rooms, users):
    """Create housekeeping tasks and linen inventory"""
    print("🧹 Creating housekeeping data...")
    
    hk_user = [u for u in users if u["role"] == "housekeeping"][0]
    
    # Create tasks for dirty and cleaning rooms
    tasks_created = 0
    for room in rooms:
        if room["status"] in ["dirty", "cleaning"]:
            task_id = generate_id()
            task = {
                "id": task_id,
                "tenant_id": DEMO_TENANT_ID,
                "room_id": room["id"],
                "task_type": "cleaning",
                "priority": "high" if room["status"] == "dirty" else "normal",
                "status": "in_progress" if room["status"] == "cleaning" else "pending",
                "assigned_to": hk_user["name"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "notes": f"Clean room {room['room_number']}"
            }
            await db.housekeeping_tasks.insert_one(task)
            tasks_created += 1
    
    # Linen inventory
    linen_items = [
        {"item_type": "bed_sheet", "in_stock": 200, "in_use": 150, "in_laundry": 30, "damaged": 5, "par_level": 180},
        {"item_type": "pillow_case", "in_stock": 300, "in_use": 250, "in_laundry": 40, "damaged": 8, "par_level": 280},
        {"item_type": "towel", "in_stock": 400, "in_use": 300, "in_laundry": 80, "damaged": 15, "par_level": 350},
        {"item_type": "bath_mat", "in_stock": 100, "in_use": 80, "in_laundry": 15, "damaged": 3, "par_level": 90},
        {"item_type": "duvet", "in_stock": 80, "in_use": 60, "in_laundry": 10, "damaged": 2, "par_level": 70},
    ]
    
    for item in linen_items:
        linen_id = generate_id()
        linen = {
            "id": linen_id,
            "tenant_id": DEMO_TENANT_ID,
            **item,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db.linen_inventory.insert_one(linen)
    
    print(f"✅ Created {tasks_created} housekeeping tasks and {len(linen_items)} linen items")


async def create_reviews(guests):
    """Create guest reviews"""
    print("⭐ Creating guest reviews...")
    
    reviews_created = 0
    for i in range(50):
        guest = random.choice(guests)
        rating = random.randint(3, 5)  # Mostly positive
        
        review_id = generate_id()
        review = {
            "id": review_id,
            "tenant_id": DEMO_TENANT_ID,
            "guest_id": guest["id"],
            "rating": rating,
            "comment": f"{'Excellent' if rating == 5 else 'Good' if rating == 4 else 'Average'} stay at the hotel.",
            "source": random.choice(["booking_com", "tripadvisor", "google", "direct"]),
            "sentiment_score": rating / 5,
            "created_at": (datetime.now(timezone.utc) - timedelta(days=random.randint(1, 365))).isoformat()
        }
        await db.reviews.insert_one(review)
        reviews_created += 1
    
    print(f"✅ Created {reviews_created} reviews")


async def create_loyalty_program():
    """Create loyalty program"""
    print("🎁 Creating loyalty program...")
    
    program_id = generate_id()
    program = {
        "id": program_id,
        "tenant_id": DEMO_TENANT_ID,
        "name": "Grand Hotel Rewards",
        "tiers": [
            {"name": "bronze", "min_points": 0, "benefits": ["Free WiFi", "10% F&B discount"]},
            {"name": "silver", "min_points": 500, "benefits": ["Free WiFi", "15% F&B discount", "Late checkout"]},
            {"name": "gold", "min_points": 1500, "benefits": ["Free WiFi", "20% F&B discount", "Room upgrade", "Late checkout"]},
            {"name": "platinum", "min_points": 3000, "benefits": ["Free WiFi", "25% F&B discount", "Suite upgrade", "Late checkout", "Spa access"]}
        ],
        "points_per_dollar": 10,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.loyalty_programs.insert_one(program)
    
    print("✅ Loyalty program created")


async def create_rms_data():
    """Create RMS competitor data"""
    print("📈 Creating RMS data...")
    
    competitors = [
        {"name": "Luxury Hotel Next Door", "property_type": "hotel", "stars": 5},
        {"name": "Budget Inn Nearby", "property_type": "hotel", "stars": 3},
        {"name": "Business Center Hotel", "property_type": "hotel", "stars": 4},
    ]
    
    for competitor in competitors:
        comp_id = generate_id()
        comp_data = {
            "id": comp_id,
            "tenant_id": DEMO_TENANT_ID,
            "name": competitor["name"],
            "property_type": competitor["property_type"],
            "stars": competitor["stars"],
            "address": f"{random.randint(100, 999)} Competitor St",
            "distance_km": round(random.uniform(0.5, 5), 1),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.rms_competitors.insert_one(comp_data)
    
    print(f"✅ Created {len(competitors)} competitors")


async def main():
    """Main seeding function"""
    print("\n" + "="*60)
    print("🚀 STARTING DEMO DATA SEEDING")
    print("="*60 + "\n")
    
    try:
        # Step 1: Clear existing demo data
        await clear_demo_data()
        
        # Step 2: Create tenant
        await create_demo_tenant()
        
        # Step 3: Create users
        users = await create_demo_users()
        
        # Step 4: Create companies
        companies = await create_companies()
        
        # Step 5: Create rooms
        rooms = await create_rooms()
        
        # Step 6: Create guests
        guests = await create_guests()
        
        # Step 7: Create bookings and folios (most complex)
        await create_bookings_and_folios(rooms, guests, companies, users)
        
        # Step 8: Create housekeeping data
        await create_housekeeping_data(rooms, users)
        
        # Step 9: Create reviews
        await create_reviews(guests)
        
        # Step 10: Create loyalty program
        await create_loyalty_program()
        
        # Step 11: Create RMS data
        await create_rms_data()
        
        print("\n" + "="*60)
        print("✅ DEMO DATA SEEDING COMPLETED SUCCESSFULLY!")
        print("="*60)
        print("\n📋 DEMO LOGIN CREDENTIALS:")
        print("-" * 60)
        for user in DEMO_USERS:
            print(f"  Email: {user['email']}")
            print(f"  Role: {user['role']}")
            print(f"  Password: {DEMO_PASSWORD}")
            print("-" * 60)
        print("\n")
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
