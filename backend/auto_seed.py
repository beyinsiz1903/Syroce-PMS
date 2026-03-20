"""
Auto Seed Data - Creates demo data on startup if database is empty
Generates: demo user, tenant, rooms, guests, bookings, folios, housekeeping tasks
"""

import uuid
import random
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEMO_EMAIL = "demo@hotel.com"
DEMO_PASSWORD = "demo123"
DEMO_HOTEL_NAME = "Syroce Demo Hotel"


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


async def auto_seed_if_empty(db):
    """Main entry point: seeds demo data only when users collection is empty."""
    user_count = await db.users.count_documents({})
    if user_count > 0:
        print("ℹ️  Database already has users — skipping auto-seed.")
        return False

    print("🌱 Empty database detected — seeding demo data...")

    tenant_id = _uuid()
    admin_user_id = _uuid()

    # ── 1. Tenant ──────────────────────────────────────────
    tenant = {
        "id": tenant_id,
        "property_name": DEMO_HOTEL_NAME,
        "property_type": "hotel",
        "contact_email": DEMO_EMAIL,
        "contact_phone": "+905551234567",
        "address": "Antalya, Türkiye",
        "total_rooms": 30,
        "subscription_status": "active",
        "subscription_start_date": None,
        "subscription_end_date": None,
        "subscription_tier": "enterprise",
        "plan": "enterprise",
        "subscription_plan": None,
        "location": "Antalya",
        "amenities": ["Pool", "Spa", "Restaurant", "Bar", "Gym", "WiFi", "Parking"],
        "created_at": _now().isoformat(),
        "modules": {
            "pms": True,
            "reports": True,
            "invoices": True,
            "ai": True,
            "channel_manager": True,
            "rms": True,
            "housekeeping": True,
            "reservation_calendar": True,
            "loyalty": True,
            "marketplace": True,
            "maintenance": True,
            "night_audit": True,
            "folio_management": True,
            "cost_management": True,
            "sales_crm": True,
            "group_sales": True,
            "gm_dashboards": True,
            "mobile_housekeeping": True,
            "rate_management": True,
            "basic_reporting": True,
            "revenue_management": True,
            "advanced_analytics": True,
        },
        "features": {
            "hidden_rms": True,
            "hidden_channel_manager": True,
        },
    }
    await db.tenants.insert_one(tenant)

    # ── 2. Admin user ──────────────────────────────────────
    admin_user = {
        "id": admin_user_id,
        "tenant_id": tenant_id,
        "agency_id": None,
        "email": DEMO_EMAIL,
        "name": "Demo Admin",
        "role": "super_admin",
        "phone": "+905551234567",
        "is_active": True,
        "email_verified": True,
        "email_verified_at": _now().isoformat(),
        "hashed_password": pwd_context.hash(DEMO_PASSWORD),
        "created_at": _now().isoformat(),
    }
    await db.users.insert_one(admin_user)

    # Extra staff users
    staff_users = [
        {"name": "Front Desk Agent", "email": "frontdesk@hotel.com", "role": "front_desk"},
        {"name": "Housekeeping Mgr", "email": "housekeeping@hotel.com", "role": "housekeeping"},
        {"name": "Finance Manager", "email": "finance@hotel.com", "role": "finance"},
        {"name": "Sales Manager", "email": "sales@hotel.com", "role": "sales"},
    ]
    for su in staff_users:
        await db.users.insert_one({
            "id": _uuid(),
            "tenant_id": tenant_id,
            "agency_id": None,
            "email": su["email"],
            "name": su["name"],
            "role": su["role"],
            "phone": f"+90555{random.randint(1000000,9999999)}",
            "is_active": True,
            "email_verified": True,
            "email_verified_at": _now().isoformat(),
            "hashed_password": pwd_context.hash("staff123"),
            "created_at": _now().isoformat(),
        })

    # ── 3. Rooms (30 oda) ─────────────────────────────────
    room_configs = [
        # (type, count, floor_start, base_price, capacity, view, bed_type)
        ("Standard",  8, 1, 120, 2, "city",     "twin"),
        ("Deluxe",    8, 2, 180, 2, "garden",   "queen"),
        ("Superior",  6, 3, 240, 3, "sea",      "king"),
        ("Suite",     4, 4, 350, 4, "sea",      "king"),
        ("Junior Suite", 2, 5, 280, 3, "pool",  "queen"),
        ("Family",    2, 1, 200, 5, "garden",   "twin"),
    ]
    rooms = []
    room_num = 101
    for rtype, count, floor_start, price, cap, view, bed in room_configs:
        for i in range(count):
            floor = floor_start + (i // 4)
            room = {
                "id": _uuid(),
                "tenant_id": tenant_id,
                "room_number": str(room_num),
                "room_type": rtype,
                "floor": floor,
                "capacity": cap,
                "base_price": price,
                "price_per_night": price,
                "status": "available",
                "amenities": ["WiFi", "TV", "AC", "Safe"],
                "view": view,
                "bed_type": bed,
                "images": [],
                "is_active": True,
                "deleted_at": None,
                "current_booking_id": None,
                "last_cleaned": _now().isoformat(),
                "notes": None,
                "created_at": _now().isoformat(),
            }
            # Add extra amenities for higher categories
            if rtype in ("Suite", "Junior Suite", "Superior"):
                room["amenities"].extend(["Minibar", "Bathrobe", "Balcony"])
            if rtype == "Suite":
                room["amenities"].append("Jacuzzi")
            rooms.append(room)
            room_num += 1

    await db.rooms.insert_many(rooms)

    # ── 4. Guests (50 misafir) ─────────────────────────────
    first_names_m = ["Ahmet", "Mehmet", "Ali", "Murat", "Emre", "Can", "Burak", "Serkan", "Oğuz", "Kerem",
                     "John", "Michael", "David", "James", "Robert", "William", "Thomas", "Daniel", "Hans", "Pierre"]
    first_names_f = ["Ayşe", "Fatma", "Elif", "Zeynep", "Selin", "Merve", "Deniz", "Ece", "İrem", "Başak",
                     "Emma", "Sophia", "Olivia", "Anna", "Maria", "Sophie", "Lisa", "Julia", "Elena", "Laura"]
    last_names = ["Yılmaz", "Kaya", "Demir", "Çelik", "Şahin", "Öztürk", "Aydın", "Arslan", "Doğan", "Kılıç",
                  "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Müller", "Dubois", "Rossi"]
    nationalities = ["TR", "TR", "TR", "TR", "DE", "GB", "US", "FR", "RU", "IT", "NL", "JP"]

    guests = []
    for i in range(50):
        if i % 2 == 0:
            first = random.choice(first_names_m)
        else:
            first = random.choice(first_names_f)
        last = random.choice(last_names)
        nat = random.choice(nationalities)

        guest = {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "name": f"{first} {last}",
            "email": f"{first.lower()}.{last.lower()}{i}@email.com",
            "phone": f"+{random.choice(['90','49','44','1','33','7','39'])}{random.randint(1000000000,9999999999)}",
            "id_number": f"{random.randint(10000000000,99999999999)}",
            "nationality": nat,
            "address": None,
            "vip_status": random.random() < 0.1,
            "loyalty_points": random.randint(0, 5000),
            "total_stays": random.randint(0, 15),
            "total_spend": round(random.uniform(0, 15000), 2),
            "notes": None,
            "created_at": (_now() - timedelta(days=random.randint(1, 365))).isoformat(),
        }
        guests.append(guest)

    await db.guests.insert_many(guests)

    # ── 5. Bookings (45 booking) ──────────────────────────
    channels = ["direct", "booking_com", "expedia", "airbnb", "own_website"]
    rate_plans = ["Standard", "Best Available", "Non-Refundable", "Early Bird", "Last Minute"]
    bookings = []

    # Past bookings (15) - checked_out
    for _ in range(15):
        guest = random.choice(guests)
        room = random.choice(rooms)
        ci = _now() - timedelta(days=random.randint(5, 90))
        nights = random.randint(1, 7)
        co = ci + timedelta(days=nights)
        total = room["base_price"] * nights

        bookings.append({
            "id": _uuid(),
            "tenant_id": tenant_id,
            "guest_id": guest["id"],
            "room_id": room["id"],
            "guest_name": guest["name"],
            "room_number": room["room_number"],
            "check_in": ci.isoformat(),
            "check_out": co.isoformat(),
            "adults": random.randint(1, 2),
            "children": random.randint(0, 2),
            "children_ages": [],
            "guests_count": random.randint(1, 3),
            "total_amount": total,
            "base_rate": room["base_price"],
            "paid_amount": total,
            "status": "checked_out",
            "channel": random.choice(channels),
            "source_channel": "direct",
            "origin": "ui",
            "hold_status": "none",
            "allocation_source": "manual",
            "rate_plan": random.choice(rate_plans),
            "special_requests": None,
            "group_booking_id": None,
            "company_id": None,
            "created_at": (ci - timedelta(days=random.randint(1, 30))).isoformat(),
        })

    # Current bookings (10) - checked_in → mark rooms as occupied
    occupied_rooms = random.sample(rooms, min(10, len(rooms)))
    for idx, room in enumerate(occupied_rooms):
        guest = random.choice(guests)
        ci = _now() - timedelta(days=random.randint(0, 3))
        nights = random.randint(2, 7)
        co = ci + timedelta(days=nights)
        total = room["base_price"] * nights
        bid = _uuid()

        room["status"] = "occupied"
        room["current_booking_id"] = bid

        bookings.append({
            "id": bid,
            "tenant_id": tenant_id,
            "guest_id": guest["id"],
            "room_id": room["id"],
            "guest_name": guest["name"],
            "room_number": room["room_number"],
            "check_in": ci.isoformat(),
            "check_out": co.isoformat(),
            "adults": random.randint(1, 2),
            "children": random.randint(0, 1),
            "children_ages": [],
            "guests_count": random.randint(1, 3),
            "total_amount": total,
            "base_rate": room["base_price"],
            "paid_amount": round(total * random.uniform(0.5, 1.0), 2),
            "status": "checked_in",
            "channel": random.choice(channels),
            "source_channel": "direct",
            "origin": "ui",
            "hold_status": "none",
            "allocation_source": "manual",
            "rate_plan": random.choice(rate_plans),
            "special_requests": random.choice([None, "High floor", "Extra pillows", "Late check-out"]),
            "group_booking_id": None,
            "company_id": None,
            "created_at": (ci - timedelta(days=random.randint(1, 60))).isoformat(),
        })

    # Future bookings (20) - confirmed
    for _ in range(20):
        guest = random.choice(guests)
        room = random.choice(rooms)
        ci = _now() + timedelta(days=random.randint(1, 90))
        nights = random.randint(1, 7)
        co = ci + timedelta(days=nights)
        total = room["base_price"] * nights

        bookings.append({
            "id": _uuid(),
            "tenant_id": tenant_id,
            "guest_id": guest["id"],
            "room_id": room["id"],
            "guest_name": guest["name"],
            "room_number": room["room_number"],
            "check_in": ci.isoformat(),
            "check_out": co.isoformat(),
            "adults": random.randint(1, 2),
            "children": random.randint(0, 2),
            "children_ages": [],
            "guests_count": random.randint(1, 3),
            "total_amount": total,
            "base_rate": room["base_price"],
            "paid_amount": round(total * random.uniform(0, 0.5), 2),
            "status": "confirmed",
            "channel": random.choice(channels),
            "source_channel": "direct",
            "origin": "ui",
            "hold_status": "none",
            "allocation_source": "manual",
            "rate_plan": random.choice(rate_plans),
            "special_requests": None,
            "group_booking_id": None,
            "company_id": None,
            "created_at": (_now() - timedelta(days=random.randint(0, 30))).isoformat(),
        })

    await db.bookings.insert_many(bookings)

    # Update occupied room statuses in DB
    for room in occupied_rooms:
        await db.rooms.update_one(
            {"id": room["id"]},
            {"$set": {"status": "occupied", "current_booking_id": room["current_booking_id"]}}
        )

    # Mark a few rooms as dirty/cleaning
    dirty_rooms = random.sample([r for r in rooms if r["status"] == "available"], min(4, len(rooms)))
    for room in dirty_rooms:
        new_status = random.choice(["dirty", "cleaning"])
        await db.rooms.update_one({"id": room["id"]}, {"$set": {"status": new_status}})
        room["status"] = new_status

    # ── 6. Folios (for checked-in bookings) ───────────────
    folio_counter = 1
    folios = []
    checked_in_bookings = [b for b in bookings if b["status"] == "checked_in"]
    for b in checked_in_bookings:
        folio = {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "booking_id": b["id"],
            "folio_number": f"F-{_now().year}-{folio_counter:04d}",
            "folio_type": "guest",
            "status": "open",
            "guest_id": b["guest_id"],
            "company_id": None,
            "balance": round(b["total_amount"] - b["paid_amount"], 2),
            "notes": None,
            "created_at": b["created_at"],
            "closed_at": None,
        }
        folios.append(folio)
        folio_counter += 1

    # Folios for past bookings (closed)
    past_bookings = [b for b in bookings if b["status"] == "checked_out"]
    for b in past_bookings[:10]:
        folio = {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "booking_id": b["id"],
            "folio_number": f"F-{_now().year}-{folio_counter:04d}",
            "folio_type": "guest",
            "status": "closed",
            "guest_id": b["guest_id"],
            "company_id": None,
            "balance": 0.0,
            "notes": None,
            "created_at": b["created_at"],
            "closed_at": b["check_out"],
        }
        folios.append(folio)
        folio_counter += 1

    if folios:
        await db.folios.insert_many(folios)

    # ── 7. Housekeeping Tasks ──────────────────────────────
    task_types = ["cleaning", "inspection", "deep_cleaning", "turndown"]
    priorities = ["low", "normal", "high", "urgent"]
    hk_staff = ["Maria H.", "Ana K.", "Carlos M.", "Elif Y.", "Fatma D."]
    tasks = []

    # Tasks for dirty/cleaning rooms
    for room in rooms:
        if room["status"] in ("dirty", "cleaning"):
            tasks.append({
                "id": _uuid(),
                "tenant_id": tenant_id,
                "room_id": room["id"],
                "task_type": "cleaning",
                "assigned_to": random.choice(hk_staff),
                "status": "in_progress" if room["status"] == "cleaning" else "pending",
                "priority": random.choice(["normal", "high"]),
                "notes": None,
                "started_at": _now().isoformat() if room["status"] == "cleaning" else None,
                "completed_at": None,
                "created_at": _now().isoformat(),
            })

    # Additional random completed tasks (history)
    for _ in range(15):
        room = random.choice(rooms)
        completed_at = _now() - timedelta(hours=random.randint(1, 72))
        tasks.append({
            "id": _uuid(),
            "tenant_id": tenant_id,
            "room_id": room["id"],
            "task_type": random.choice(task_types),
            "assigned_to": random.choice(hk_staff),
            "status": "completed",
            "priority": random.choice(priorities),
            "notes": random.choice([None, "Extra towels placed", "Minibar restocked", "Guest requested late checkout"]),
            "started_at": (completed_at - timedelta(minutes=random.randint(15, 60))).isoformat(),
            "completed_at": completed_at.isoformat(),
            "created_at": (completed_at - timedelta(minutes=random.randint(60, 180))).isoformat(),
        })

    if tasks:
        await db.housekeeping_tasks.insert_many(tasks)

    # ── 8. Exely Connection (for webhook tests) ──────────
    exely_conn = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "hotel_code": "501694",
        "credentials_ref": "",
        "endpoint_url": "",
        "property_name": "Syroce Demo Hotel (Exely)",
        "auto_sync_reservations": True,
        "sync_interval_minutes": 15,
        "mode": "sandbox",
        "currency": "TRY",
        "is_active": True,
        "room_types": [],
        "rate_plans": [],
        "connected_at": _now().isoformat(),
        "last_sync_at": None,
        "created_by": "auto_seed",
    }
    await db.exely_connections.update_one(
        {"hotel_code": "501694"},
        {"$set": exely_conn},
        upsert=True,
    )

    # ── 9. Summary ─────────────────────────────────────────
    print("✅ Demo data seeded successfully!")
    print(f"   👤 Users: {1 + len(staff_users)} (admin: {DEMO_EMAIL} / {DEMO_PASSWORD})")
    print(f"   🏨 Tenant: {DEMO_HOTEL_NAME} (tier: enterprise)")
    print(f"   🛏️  Rooms: {len(rooms)}")
    print(f"   👥 Guests: {len(guests)}")
    print(f"   📋 Bookings: {len(bookings)} (past:{15}, active:{len(occupied_rooms)}, future:20)")
    print(f"   💳 Folios: {len(folios)}")
    print(f"   🧹 HK Tasks: {len(tasks)}")
    return True
