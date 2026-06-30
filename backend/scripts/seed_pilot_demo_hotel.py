"""
Pilot Demo Hotel Seed Data Script (Sprint 5 Task 1)
---------------------------------------------------
Generates a realistic "Clean State" demo hotel environment for a pilot demo.
Features:
- Idempotent: Drops existing tenant data and recreates it.
- ENV check: Exits immediately if ENV=production.
- Generates Rooms, Users, Guests, Bookings, Folios, Payments, Housekeeping Tasks.
"""
import asyncio
import os
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta

# Import paths setup
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import _raw_db
from core.security import hash_password

# ================= Configuration =================
TENANT_ID = "syroce_demo_pilot"
HOTEL_NAME = "Syroce Demo Hotel"
DEFAULT_PASSWORD = "demo"

ROOM_TYPES = {
    "Standard": {"count": 20, "rate": 120, "occupancy": 2},
    "Deluxe": {"count": 15, "rate": 180, "occupancy": 2},
    "Family": {"count": 5, "rate": 250, "occupancy": 4},
    "Suite": {"count": 2, "rate": 450, "occupancy": 2},
}

USERS = [
    {"email": "gm@hotel.com", "role": "admin", "name": "General Manager"},
    {"email": "frontdesk@hotel.com", "role": "front_desk", "name": "Receptionist"},
    {"email": "housekeeping@hotel.com", "role": "housekeeping", "name": "Housekeeping Supervisor"},
    {"email": "finance@hotel.com", "role": "finance", "name": "Cashier"},
]

GUEST_NAMES = [
    ("John", "Doe"), ("Emma", "Smith"), ("Oliver", "Brown"), ("Sophia", "Davis"),
    ("Lucas", "Miller"), ("Mia", "Wilson"), ("Ethan", "Moore"), ("Isabella", "Taylor"),
    ("James", "Anderson"), ("Charlotte", "Thomas")
]
# =================================================


async def clear_existing_tenant():
    print(f"Cleaning up existing data for tenant '{TENANT_ID}'...")
    collections_to_clean = [
        "tenants", "users", "rooms", "guests", "bookings", 
        "folios", "payments", "housekeeping_tasks"
    ]
    for coll_name in collections_to_clean:
        if coll_name == "tenants":
            await _raw_db[coll_name].delete_many({"_id": TENANT_ID})
        else:
            await _raw_db[coll_name].delete_many({"tenant_id": TENANT_ID})


async def seed_tenant_and_users():
    print("Seeding tenant and users...")
    now = datetime.now(UTC)
    
    await _raw_db.tenants.insert_one({
        "_id": TENANT_ID,
        "name": HOTEL_NAME,
        "status": "active",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    })
    
    hashed_pwd = hash_password(DEFAULT_PASSWORD)
    user_docs = []
    for u in USERS:
        user_docs.append({
            "_id": str(uuid.uuid4()),
            "tenant_id": TENANT_ID,
            "email": u["email"],
            "password_hash": hashed_pwd,
            "full_name": u["name"],
            "role": u["role"],
            "is_active": True,
            "created_at": now.isoformat()
        })
    await _raw_db.users.insert_many(user_docs)


async def seed_rooms():
    print("Seeding rooms...")
    rooms = []
    floor = 1
    number = 1
    
    for r_type, info in ROOM_TYPES.items():
        for _ in range(info["count"]):
            if number > 15:
                floor += 1
                number = 1
                
            room_num = f"{floor}{number:02d}"
            
            # 80% Clean, 10% Dirty, 5% Inspected, 5% Out of Order
            status_roll = random.random()
            if status_roll < 0.8:
                status = "clean"
            elif status_roll < 0.9:
                status = "dirty"
            elif status_roll < 0.95:
                status = "inspected"
            else:
                status = "out_of_order"
                
            rooms.append({
                "_id": str(uuid.uuid4()),
                "tenant_id": TENANT_ID,
                "room_number": room_num,
                "room_type": r_type,
                "floor": floor,
                "status": status,
                "base_rate": info["rate"],
                "max_occupancy": info["occupancy"],
                "features": ["WiFi", "TV", "AC"]
            })
            number += 1
            
    await _raw_db.rooms.insert_many(rooms)
    return rooms


async def seed_guests():
    print("Seeding guests...")
    guests = []
    now = datetime.now(UTC)
    
    for i in range(20):
        first, last = random.choice(GUEST_NAMES)
        guests.append({
            "_id": str(uuid.uuid4()),
            "tenant_id": TENANT_ID,
            "first_name": first,
            "last_name": last,
            "email": f"{first.lower()}.{last.lower()}{i}@example.com",
            "phone": f"+1555{random.randint(100000, 999999)}",
            "nationality": "US",
            "created_at": now.isoformat()
        })
    await _raw_db.guests.insert_many(guests)
    return guests


async def seed_bookings_and_folios(rooms, guests):
    print("Seeding bookings, folios, payments...")
    now = datetime.now(UTC)
    today = now.replace(hour=14, minute=0, second=0, microsecond=0)
    
    bookings = []
    folios = []
    payments = []
    
    # Let's create specific scenarios:
    scenarios = [
        # Today Check-in
        {"days_offset": 0, "length": 3, "status": "confirmed", "payment": "partial"},
        # Today Check-out
        {"days_offset": -3, "length": 3, "status": "checked_in", "payment": "full"},
        # In-House
        {"days_offset": -1, "length": 4, "status": "checked_in", "payment": "unpaid"},
        # Future
        {"days_offset": 5, "length": 2, "status": "confirmed", "payment": "unpaid"},
        # No-show candidate
        {"days_offset": -1, "length": 2, "status": "confirmed", "payment": "unpaid"},
        # Cancelled
        {"days_offset": 2, "length": 3, "status": "cancelled", "payment": "unpaid"},
        # Group booking (3 rooms)
        {"days_offset": 1, "length": 2, "status": "confirmed", "payment": "full", "group": True},
        {"days_offset": 1, "length": 2, "status": "confirmed", "payment": "full", "group": True},
        {"days_offset": 1, "length": 2, "status": "confirmed", "payment": "full", "group": True},
    ]
    
    for scenario in scenarios:
        guest = random.choice(guests)
        room = random.choice(rooms)
        
        check_in = today + timedelta(days=scenario["days_offset"])
        check_out = check_in + timedelta(days=scenario["length"])
        
        total_amount = room["base_rate"] * scenario["length"]
        
        booking_id = str(uuid.uuid4())
        folio_id = str(uuid.uuid4())
        
        bookings.append({
            "_id": booking_id,
            "tenant_id": TENANT_ID,
            "guest_id": guest["_id"],
            "room_id": room["_id"],
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
            "adults": random.randint(1, room["max_occupancy"]),
            "status": scenario["status"],
            "total_amount": total_amount,
            "source": random.choice(["direct", "ota", "corporate"]),
            "created_at": (check_in - timedelta(days=random.randint(1, 10))).isoformat()
        })
        
        folio_balance = total_amount
        charges = [
            {"amount": total_amount, "description": "Room Rate", "type": "room"}
        ]
        
        # Add random extra charges for in-house
        if scenario["status"] == "checked_in":
            extra = random.choice([50, 100, 15])
            charges.append({"amount": extra, "description": "Minibar/Spa", "type": "extra"})
            folio_balance += extra
            
        paid_amount = 0
        if scenario["payment"] == "full":
            paid_amount = folio_balance
        elif scenario["payment"] == "partial":
            paid_amount = folio_balance / 2
            
        folios.append({
            "_id": folio_id,
            "tenant_id": TENANT_ID,
            "booking_id": booking_id,
            "guest_id": guest["_id"],
            "balance": folio_balance - paid_amount,
            "total_charges": folio_balance,
            "charges": charges,
            "created_at": now.isoformat()
        })
        
        if paid_amount > 0:
            payments.append({
                "_id": str(uuid.uuid4()),
                "tenant_id": TENANT_ID,
                "folio_id": folio_id,
                "amount": paid_amount,
                "method": random.choice(["credit_card", "cash", "bank_transfer"]),
                "status": "completed",
                "created_at": now.isoformat()
            })
            
    await _raw_db.bookings.insert_many(bookings)
    await _raw_db.folios.insert_many(folios)
    if payments:
        await _raw_db.payments.insert_many(payments)


async def seed_housekeeping_tasks(rooms):
    print("Seeding housekeeping tasks...")
    now = datetime.now(UTC)
    tasks = []
    
    for room in rooms:
        if room["status"] == "dirty":
            tasks.append({
                "_id": str(uuid.uuid4()),
                "tenant_id": TENANT_ID,
                "room_id": room["_id"],
                "task_type": "cleaning",
                "priority": "high",
                "status": "pending",
                "created_at": now.isoformat()
            })
        elif room["status"] == "out_of_order":
            tasks.append({
                "_id": str(uuid.uuid4()),
                "tenant_id": TENANT_ID,
                "room_id": room["_id"],
                "task_type": "maintenance",
                "priority": "urgent",
                "status": "in_progress",
                "description": "Leaking faucet",
                "created_at": now.isoformat()
            })
            
    if tasks:
        await _raw_db.housekeeping_tasks.insert_many(tasks)


async def run_seed():
    if os.environ.get("ENV") == "production":
        print("ERROR: Cannot run seed script in production environment.")
        sys.exit(1)

    print("========================================")
    print("Starting Pilot Demo Hotel Seed Process")
    print("========================================")

    await clear_existing_tenant()
    await seed_tenant_and_users()
    rooms = await seed_rooms()
    guests = await seed_guests()
    await seed_bookings_and_folios(rooms, guests)
    await seed_housekeeping_tasks(rooms)
    
    print("\n✅ Seed process completed successfully!")
    print("Login Credentials:")
    for u in USERS:
        print(f" - {u['role'].capitalize()}: {u['email']} / {DEFAULT_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(run_seed())
