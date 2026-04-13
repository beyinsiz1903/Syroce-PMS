"""
Auto Seed Data - Creates demo data on startup if database is empty
Generates: demo user, tenant, rooms, guests, bookings, folios, housekeeping tasks
"""

import random
import uuid
from datetime import UTC, datetime, timedelta

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEMO_EMAIL = "demo@hotel.com"
DEMO_PASSWORD = "demo123"
DEMO_HOTEL_NAME = "Syroce Demo Hotel"


def _now():
    return datetime.now(UTC)


def _uuid():
    return str(uuid.uuid4())


def _encrypt_doc(doc: dict, collection: str) -> dict:
    """Encrypt PII fields if field encryption service is available."""
    try:
        from security.field_encryption import get_field_encryption_service
        svc = get_field_encryption_service()
        return svc.encrypt_document(doc, collection=collection)
    except Exception:
        return doc



async def _ensure_hr_legacy_connection(db):
    """Ensure hotelrunner_connections exists even when full seed is skipped."""
    user = await db.users.find_one({})
    if not user:
        return
    tid = user.get("tenant_id")
    if not tid:
        return
    existing = await db.hotelrunner_connections.find_one({"tenant_id": tid})
    if existing:
        return
    pc = await db.provider_connections.find_one(
        {"tenant_id": tid, "provider": "hotelrunner", "status": "active"}
    )
    if not pc:
        return
    creds = pc.get("credentials", {})
    hr_legacy = {
        "tenant_id": tid,
        "hr_id": creds.get("hr_id", ""),
        "token": creds.get("token", creds.get("hr_token", "")),
        "property_name": pc.get("display_name", "HotelRunner Connection"),
        "environment": pc.get("environment", "live"),
        "is_active": True,
        "channels": ["booking.com", "expedia", "airbnb"],
        "auto_sync_reservations": True,
        "connected_at": _now().isoformat(),
        "last_sync_at": None,
        "created_by": "auto_ensure",
    }
    await db.hotelrunner_connections.insert_one(hr_legacy)
    print("✅ hotelrunner_connections legacy doc created from provider_connections")


async def auto_seed_if_empty(db):
    """Main entry point: seeds demo data only when users collection is empty."""
    user_count = await db.users.count_documents({})
    if user_count > 0:
        print("ℹ️  Database already has users — skipping auto-seed.")
        await _ensure_hr_legacy_connection(db)
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
    admin_user = _encrypt_doc(admin_user, "users")
    await db.users.insert_one(admin_user)

    # Extra staff users
    staff_users = [
        {"name": "Front Desk Agent", "email": "frontdesk@hotel.com", "role": "front_desk"},
        {"name": "Housekeeping Mgr", "email": "housekeeping@hotel.com", "role": "housekeeping"},
        {"name": "Finance Manager", "email": "finance@hotel.com", "role": "finance"},
        {"name": "Sales Manager", "email": "sales@hotel.com", "role": "sales"},
    ]
    for su in staff_users:
        staff_doc = {
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
        }
        staff_doc = _encrypt_doc(staff_doc, "users")
        await db.users.insert_one(staff_doc)

    # ── 3. Rooms (30 oda) ─────────────────────────────────
    room_configs = [
        # (type, count, floor_start, base_price_TRY, capacity, view, bed_type)
        ("Standard",  8, 1, 4500, 2, "city",     "twin"),
        ("Deluxe",    8, 2, 6800, 2, "garden",   "queen"),
        ("Superior",  6, 3, 9200, 3, "sea",      "king"),
        ("Suite",     4, 4, 14000, 4, "sea",      "king"),
        ("Junior Suite", 2, 5, 10500, 3, "pool",  "queen"),
        ("Family",    2, 1, 7800, 5, "garden",   "twin"),
    ]
    rooms = []
    room_num = 101
    for rtype, count, floor_start, price, cap, view, bed in room_configs:
        for i in range(count):
            floor = floor_start + (i // 4)
            room = {
                "id": _uuid(),
                "tenant_id": tenant_id,
                "property_id": "prop-001",
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

    guests = [_encrypt_doc(g, "guests") for g in guests]
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
            "room_type": room["room_type"],
            "check_in": ci.isoformat(),
            "check_out": co.isoformat(),
            "nights": nights,
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
            "room_type": room["room_type"],
            "check_in": ci.isoformat(),
            "check_out": co.isoformat(),
            "nights": nights,
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
            "room_type": room["room_type"],
            "check_in": ci.isoformat(),
            "check_out": co.isoformat(),
            "nights": nights,
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

    bookings = [_encrypt_doc(b, "bookings") for b in bookings]
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
        "credentials_ref": "vault:exely:501694",
        "endpoint_url": "https://supply-xml.booking.com/hotels/xml/availability",
        "username": "syroce_demo",
        "password": "demo_sandbox_2026",
        "property_name": "Syroce Demo Hotel (Exely)",
        "auto_sync_reservations": True,
        "sync_interval_minutes": 15,
        "mode": "sandbox",
        "currency": "TRY",
        "is_active": True,
        "room_types": [
            {"code": "STD", "name": "Standart", "max_occupancy": 2},
            {"code": "DLX", "name": "Deluxe", "max_occupancy": 5},
            {"code": "SUI", "name": "Suite", "max_occupancy": 5},
        ],
        "rate_plans": [
            {"code": "BAR", "name": "Best Available Rate"},
            {"code": "RACK", "name": "Rack Rate"},
            {"code": "PROMO", "name": "Promotional Rate"},
        ],
        "connected_at": _now().isoformat(),
        "last_sync_at": None,
        "created_by": "auto_seed",
    }
    await db.exely_connections.update_one(
        {"hotel_code": "501694"},
        {"$set": exely_conn},
        upsert=True,
    )

    # ── 9. Channel Manager: Provider Connections (9-collection model) ──
    now_iso = _now().isoformat()
    hr_conn = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "hotelrunner",
        "status": "active",
        "display_name": "HotelRunner Connection",
        "credentials": {"hr_token": "A9cM3IZjr3iSOZASwK7D30mUNVqM3BtULpEHrf05", "token": "A9cM3IZjr3iSOZASwK7D30mUNVqM3BtULpEHrf05", "hr_id": "373816343"},
        "sync_inventory": True,
        "sync_rates": True,
        "sync_reservations": True,
        "sync_restrictions": True,
        "max_requests_per_minute": 60,
        "max_requests_per_hour": 1000,
        "consecutive_failures": 0,
        "total_syncs": 0,
        "total_errors": 0,
        "created_at": now_iso,
        "created_by": "auto_seed",
    }
    ex_conn = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "exely",
        "status": "active",
        "display_name": "Exely Connection",
        "credentials": {"username": "syroce_demo", "password": "demo_sandbox_2026", "hotel_code": "501694"},
        "sync_inventory": True,
        "sync_rates": True,
        "sync_reservations": True,
        "sync_restrictions": True,
        "max_requests_per_minute": 60,
        "max_requests_per_hour": 1000,
        "consecutive_failures": 0,
        "total_syncs": 0,
        "total_errors": 0,
        "created_at": now_iso,
        "created_by": "auto_seed",
    }
    await db.provider_connections.insert_many([hr_conn, ex_conn])

    # ── 9b. hotelrunner_connections (legacy format for overview) ──
    hr_legacy = {
        "tenant_id": tenant_id,
        "hr_id": "373816343",
        "token": "A9cM3IZjr3iSOZASwK7D30mUNVqM3BtULpEHrf05",
        "property_name": "Syroce Demo Hotel",
        "environment": "live",
        "is_active": True,
        "channels": ["booking.com", "expedia", "airbnb"],
        "auto_sync_reservations": True,
        "connected_at": now_iso,
        "last_sync_at": None,
        "created_by": "auto_seed",
        "cached_rooms": [
            {"inv_code": "HR:1271568", "name": "Standart Oda", "id": 1271568, "pms_code": "STD"},
            {"inv_code": "HR:1271569", "name": "Deluxe Oda", "id": 1271569, "pms_code": "DLX"},
            {"inv_code": "HR:1271567", "name": "Corner Süit", "id": 1271567, "pms_code": "SUI"},
        ],
    }
    await db.hotelrunner_connections.update_one(
        {"tenant_id": tenant_id},
        {"$set": hr_legacy},
        upsert=True,
    )

    # ── 10. Channel Manager: Room Mappings ───────────────────
    hr_room = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "hotelrunner",
        "pms_room_type_id": "std-001",
        "pms_room_type_name": "Standard Room",
        "provider_room_code": "STD",
        "provider_room_id": "hr-std-001",
        "occupancy_offset": 0,
        "is_active": True,
        "validation_status": "valid",
        "created_at": now_iso,
    }
    ex_room = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "exely",
        "pms_room_type_id": "dlx-001",
        "pms_room_type_name": "Deluxe Room",
        "provider_room_code": "DLX",
        "provider_room_id": "ex-dlx-001",
        "occupancy_offset": 0,
        "is_active": True,
        "validation_status": "valid",
        "created_at": now_iso,
    }
    await db.room_mappings.insert_many([hr_room, ex_room])

    # ── 11. Channel Manager: Rate Plan Mappings ──────────────
    hr_rate = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "hotelrunner",
        "pms_rate_plan_id": "bar-001",
        "pms_rate_plan_name": "Best Available Rate",
        "provider_rate_code": "BAR",
        "provider_rate_id": "hr-bar-001",
        "is_active": True,
        "created_at": now_iso,
    }
    ex_rate = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "exely",
        "pms_rate_plan_id": "rack-001",
        "pms_rate_plan_name": "Rack Rate",
        "provider_rate_code": "RACK",
        "provider_rate_id": "ex-rack-001",
        "is_active": True,
        "created_at": now_iso,
    }
    await db.rate_plan_mappings.insert_many([hr_rate, ex_rate])

    # ── 11b. Connector Flags (LIVE mode for both providers) ──
    for prov in ["hotelrunner", "exely"]:
        await db.connector_flags.update_one(
            {"tenant_id": tenant_id, "provider": prov},
            {"$set": {
                "tenant_id": tenant_id,
                "provider": prov,
                "connector_enabled": True,
                "shadow_mode": False,
                "write_enabled": True,
                "updated_at": now_iso,
                "updated_by": "auto_seed",
            }},
            upsert=True,
        )

    # ── 11c. CM v2 Connectors + External Data + Mappings ────
    hr_connector_id = "conn-hr-001"
    ex_connector_id = "conn-ex-001"

    hr_connector = {
        "id": hr_connector_id,
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "hotelrunner",
        "display_name": "HotelRunner - Syroce Demo",
        "status": "active",
        "credentials": {"hr_token": "A9cM3IZjr3iSOZASwK7D30mUNVqM3BtULpEHrf05", "token": "A9cM3IZjr3iSOZASwK7D30mUNVqM3BtULpEHrf05", "hr_id": "373816343"},
        "credentials_encrypted": False,
        "sync_enabled": True,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    ex_connector = {
        "id": ex_connector_id,
        "tenant_id": tenant_id,
        "property_id": "prop-001",
        "provider": "exely",
        "display_name": "Exely - Syroce Demo",
        "status": "active",
        "credentials": {"username": "syroce_demo", "password": "demo_sandbox_2026", "hotel_code": "501694"},
        "credentials_encrypted": False,
        "sync_enabled": True,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.cm_connectors.insert_many([hr_connector, ex_connector])

    pms_room_defs = [
        {"id": "std-001", "name": "Standard", "code": "STD", "capacity": 2, "base_price": 4500},
        {"id": "dlx-001", "name": "Deluxe", "code": "DLX", "capacity": 2, "base_price": 6800},
        {"id": "sup-001", "name": "Superior", "code": "SUP", "capacity": 3, "base_price": 9200},
        {"id": "sui-001", "name": "Suite", "code": "SUI", "capacity": 4, "base_price": 14000},
        {"id": "jsu-001", "name": "Junior Suite", "code": "JSU", "capacity": 3, "base_price": 10500},
        {"id": "fam-001", "name": "Family", "code": "FAM", "capacity": 5, "base_price": 7800},
    ]
    pms_rate_defs = [
        {"id": "bar-001", "name": "Best Available Rate", "code": "BAR"},
        {"id": "rack-001", "name": "Rack Rate", "code": "RACK"},
        {"id": "promo-001", "name": "Promotional Rate", "code": "PROMO"},
    ]

    hr_ext_room_defs = [
        {"id": "std-001", "name": "Standart Oda", "code": "STD", "capacity": 2, "base_price": 4500},
        {"id": "dlx-001", "name": "Deluxe Oda", "code": "DLX", "capacity": 2, "base_price": 6800},
        {"id": "sui-001", "name": "Corner Süit", "code": "SUI", "capacity": 4, "base_price": 14000},
    ]
    ex_ext_room_defs = [
        {"id": "std-001", "name": "Standart", "code": "STD", "capacity": 2, "base_price": 4500},
        {"id": "dlx-001", "name": "Deluxe", "code": "DLX", "capacity": 2, "base_price": 6800},
        {"id": "sui-001", "name": "Suite", "code": "SUI", "capacity": 4, "base_price": 14000},
    ]

    hr_pms_to_ext = [
        ("Standard", "std-001", "Standart Oda"),
        ("Deluxe", "dlx-001", "Deluxe Oda"),
        ("Suite", "sui-001", "Corner Süit"),
    ]
    ex_pms_to_ext = [
        ("Standard", "std-001", "Standart"),
        ("Deluxe", "dlx-001", "Deluxe"),
        ("Suite", "sui-001", "Suite"),
    ]

    provider_ext_defs = {
        hr_connector_id: ("hotelrunner", hr_ext_room_defs, hr_pms_to_ext),
        ex_connector_id: ("exely", ex_ext_room_defs, ex_pms_to_ext),
    }

    for cid, (prov, ext_room_defs, pms_to_ext) in provider_ext_defs.items():
        prefix = prov[:2]
        ext_rooms = []
        for r in ext_room_defs:
            ext_rooms.append({
                "id": f"ext-room-{prefix}-{r['code'].lower()}",
                "tenant_id": tenant_id,
                "connector_id": cid,
                "provider": prov,
                "external_id": f"{prefix}-{r['code'].lower()}-001",
                "name": r["name"],
                "code": r["code"],
                "max_occupancy": r["capacity"],
                "base_price": r["base_price"],
                "is_active": True,
                "created_at": now_iso,
            })
        if ext_rooms:
            await db.cm_external_room_types.insert_many(ext_rooms)

        ext_rates = []
        for rp in pms_rate_defs:
            ext_rates.append({
                "id": f"ext-rate-{prefix}-{rp['code'].lower()}",
                "tenant_id": tenant_id,
                "connector_id": cid,
                "provider": prov,
                "external_id": f"{prefix}-{rp['code'].lower()}-001",
                "name": rp["name"],
                "code": rp["code"],
                "is_active": True,
                "created_at": now_iso,
            })
        if ext_rates:
            await db.cm_external_rate_plans.insert_many(ext_rates)

        room_mappings_v2 = []
        for pms_name, ext_id, ext_name in pms_to_ext:
            room_mappings_v2.append({
                "id": f"map-room-{prefix}-{ext_id}",
                "tenant_id": tenant_id,
                "connector_id": cid,
                "entity_type": "room_type",
                "pms_entity_id": pms_name,
                "pms_entity_name": pms_name,
                "external_entity_id": f"{prefix}-{ext_id.split('-')[0]}-001",
                "external_entity_name": ext_name,
                "status": "active",
                "validation_status": "valid",
                "confidence_score": 100,
                "created_by": "auto_seed",
                "created_at": now_iso,
                "updated_at": now_iso,
            })
        if room_mappings_v2:
            await db.cm_mappings.insert_many(room_mappings_v2)

        rate_mappings_v2 = []
        for rp in pms_rate_defs:
            rate_mappings_v2.append({
                "id": f"map-rate-{prefix}-{rp['code'].lower()}",
                "tenant_id": tenant_id,
                "connector_id": cid,
                "entity_type": "rate_plan",
                "pms_entity_id": rp["id"],
                "pms_entity_name": rp["name"],
                "external_entity_id": f"{prefix}-{rp['code'].lower()}-001",
                "external_entity_name": rp["name"],
                "status": "active",
                "validation_status": "valid",
                "confidence_score": 100,
                "created_by": "auto_seed",
                "created_at": now_iso,
                "updated_at": now_iso,
            })
        if rate_mappings_v2:
            await db.cm_mappings.insert_many(rate_mappings_v2)

    # ── 12. Room Types (for RMS) ─────────────────────────────
    room_type_data = [
        {"name": "Standard", "base_rate": 4500, "max_rate": 9000, "min_rate": 2500, "capacity": 2, "total_rooms": 8},
        {"name": "Deluxe", "base_rate": 6800, "max_rate": 13000, "min_rate": 3800, "capacity": 2, "total_rooms": 8},
        {"name": "Superior", "base_rate": 9200, "max_rate": 18000, "min_rate": 5500, "capacity": 3, "total_rooms": 6},
        {"name": "Suite", "base_rate": 14000, "max_rate": 28000, "min_rate": 8000, "capacity": 4, "total_rooms": 4},
        {"name": "Junior Suite", "base_rate": 10500, "max_rate": 20000, "min_rate": 6000, "capacity": 3, "total_rooms": 2},
        {"name": "Family", "base_rate": 7800, "max_rate": 15000, "min_rate": 4500, "capacity": 5, "total_rooms": 2},
    ]
    room_types_docs = []
    for rtd in room_type_data:
        room_types_docs.append({
            "id": _uuid(),
            "tenant_id": tenant_id,
            "name": rtd["name"],
            "base_rate": rtd["base_rate"],
            "max_rate": rtd["max_rate"],
            "min_rate": rtd["min_rate"],
            "capacity": rtd["capacity"],
            "total_rooms": rtd["total_rooms"],
            "currency": "TRY",
            "created_at": _now().isoformat(),
        })
    await db.room_types.insert_many(room_types_docs)

    # ── 13. Extended Historical Bookings (6 months, for RMS) ──
    extended_bookings = []
    channels_weighted = (
        ["direct"] * 35 + ["booking_com"] * 25 + ["expedia"] * 20 +
        ["airbnb"] * 10 + ["own_website"] * 10
    )
    statuses_past = ["checked_out"] * 80 + ["cancelled"] * 15 + ["no_show"] * 5

    for month_offset in range(6):
        month_start = _now() - timedelta(days=(month_offset + 1) * 30)
        bookings_this_month = random.randint(25, 45)
        for _ in range(bookings_this_month):
            guest = random.choice(guests)
            room = random.choice(rooms)
            ci = month_start + timedelta(days=random.randint(0, 29))
            nights = random.randint(1, 7)
            co = ci + timedelta(days=nights)
            status = random.choice(statuses_past)
            channel = random.choice(channels_weighted)

            season_mult = 1.0
            m = ci.month
            if m in [6, 7, 8]:
                season_mult = 1.3
            elif m in [12, 1]:
                season_mult = 1.15
            elif m in [3, 4, 5]:
                season_mult = 1.05
            else:
                season_mult = 0.9

            dow_mult = 1.15 if ci.weekday() in [4, 5] else 1.0
            rate = round(room["base_price"] * season_mult * dow_mult * random.uniform(0.85, 1.15))
            total = rate * nights

            paid = total if status == "checked_out" else 0
            if status == "cancelled":
                paid = round(total * random.uniform(0, 0.3), 2)

            extended_bookings.append({
                "id": _uuid(),
                "tenant_id": tenant_id,
                "guest_id": guest["id"],
                "room_id": room["id"],
                "guest_name": guest.get("name", "Guest"),
                "room_number": room["room_number"],
                "room_type": room["room_type"],
                "check_in": ci.isoformat(),
                "check_out": co.isoformat(),
                "nights": nights,
                "adults": random.randint(1, 2),
                "children": random.randint(0, 2),
                "children_ages": [],
                "guests_count": random.randint(1, 3),
                "total_amount": total,
                "base_rate": rate,
                "paid_amount": paid,
                "status": status,
                "channel": channel,
                "source_channel": channel,
                "origin": "channel" if channel != "direct" else "ui",
                "hold_status": "none",
                "allocation_source": "channel" if channel != "direct" else "manual",
                "rate_plan": random.choice(rate_plans),
                "special_requests": None,
                "group_booking_id": None,
                "company_id": None,
                "created_at": (ci - timedelta(days=random.randint(1, 45))).isoformat(),
                "cancelled_at": ci.isoformat() if status == "cancelled" else None,
                "cancellation_reason": random.choice([
                    "Planlar degisti", "Baska otel buldum", "Seyahat iptal",
                    "Fiyat cok yuksek", "Kisisel nedenler"
                ]) if status == "cancelled" else None,
            })

    if extended_bookings:
        extended_bookings = [_encrypt_doc(b, "bookings") for b in extended_bookings]
        await db.bookings.insert_many(extended_bookings)

    # ── 14. Yield Rules ───────────────────────────────────────
    yield_rules = [
        {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "name": "Yuksek Doluluk Artisi",
            "description": "Doluluk %80 ustune cikinca fiyati %15 artir",
            "condition_type": "occupancy_above",
            "condition_value": 80,
            "action_type": "increase_percent",
            "action_value": 15,
            "is_active": True,
            "priority": 1,
            "room_types": [],
            "created_at": _now().isoformat(),
        },
        {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "name": "Dusuk Doluluk Indirimi",
            "description": "Doluluk %30 altina dusunce fiyati %10 indir",
            "condition_type": "occupancy_below",
            "condition_value": 30,
            "action_type": "decrease_percent",
            "action_value": 10,
            "is_active": True,
            "priority": 2,
            "room_types": [],
            "created_at": _now().isoformat(),
        },
        {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "name": "Son Dakika Indirimi",
            "description": "Varisa 3 gun kala bos oda varsa %10 indir",
            "condition_type": "lead_time_below",
            "condition_value": 3,
            "action_type": "decrease_percent",
            "action_value": 10,
            "is_active": True,
            "priority": 3,
            "room_types": [],
            "created_at": _now().isoformat(),
        },
        {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "name": "Erken Rezervasyon",
            "description": "60+ gun onceden rezervasyona %8 indirim",
            "condition_type": "lead_time_above",
            "condition_value": 60,
            "action_type": "decrease_percent",
            "action_value": 8,
            "is_active": True,
            "priority": 4,
            "room_types": [],
            "created_at": _now().isoformat(),
        },
        {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "name": "Hafta Sonu Primi",
            "description": "Cuma-Cumartesi geceleri %12 artis",
            "condition_type": "day_of_week",
            "condition_value": "friday,saturday",
            "action_type": "increase_percent",
            "action_value": 12,
            "is_active": True,
            "priority": 5,
            "room_types": [],
            "created_at": _now().isoformat(),
        },
    ]
    await db.yield_rules.insert_many(yield_rules)

    # ── 15. Seasonal Calendar ─────────────────────────────────
    current_year = _now().year
    seasonal_entries = [
        {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "name": "Yaz Sezonu",
            "season_type": "high",
            "start_date": f"{current_year}-06-01",
            "end_date": f"{current_year}-09-15",
            "rate_multiplier": 1.30,
            "min_stay": 2,
            "color": "#ef4444",
            "is_active": True,
            "created_at": _now().isoformat(),
        },
        {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "name": "Kis Sezonu",
            "season_type": "low",
            "start_date": f"{current_year}-11-01",
            "end_date": f"{current_year + 1}-03-01",
            "rate_multiplier": 0.85,
            "min_stay": 1,
            "color": "#3b82f6",
            "is_active": True,
            "created_at": _now().isoformat(),
        },
        {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "name": "Bayram Donemi",
            "season_type": "peak",
            "start_date": f"{current_year}-06-28",
            "end_date": f"{current_year}-07-08",
            "rate_multiplier": 1.50,
            "min_stay": 3,
            "color": "#f59e0b",
            "is_active": True,
            "created_at": _now().isoformat(),
        },
        {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "name": "Ara Sezon (Ilkbahar)",
            "season_type": "mid",
            "start_date": f"{current_year}-03-01",
            "end_date": f"{current_year}-05-31",
            "rate_multiplier": 1.05,
            "min_stay": 1,
            "color": "#22c55e",
            "is_active": True,
            "created_at": _now().isoformat(),
        },
        {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "name": "Ara Sezon (Sonbahar)",
            "season_type": "mid",
            "start_date": f"{current_year}-09-16",
            "end_date": f"{current_year}-10-31",
            "rate_multiplier": 1.0,
            "min_stay": 1,
            "color": "#a855f7",
            "is_active": True,
            "created_at": _now().isoformat(),
        },
        {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "name": "Yilbasi",
            "season_type": "peak",
            "start_date": f"{current_year}-12-25",
            "end_date": f"{current_year + 1}-01-05",
            "rate_multiplier": 1.45,
            "min_stay": 3,
            "color": "#f59e0b",
            "is_active": True,
            "created_at": _now().isoformat(),
        },
    ]
    await db.seasonal_calendar.insert_many(seasonal_entries)

    # ── Summary ─────────────────────────────────────────
    total_bookings = len(bookings) + len(extended_bookings)
    print("Demo data seeded successfully!")
    print(f"   Users: {1 + len(staff_users)} (admin: {DEMO_EMAIL} / {DEMO_PASSWORD})")
    print(f"   Tenant: {DEMO_HOTEL_NAME} (tier: enterprise)")
    print(f"   Rooms: {len(rooms)}")
    print(f"   Room Types: {len(room_types_docs)}")
    print(f"   Guests: {len(guests)}")
    print(f"   Bookings: {total_bookings} (incl. 6-month history)")
    print(f"   Yield Rules: {len(yield_rules)}")
    print(f"   Seasonal Calendar: {len(seasonal_entries)}")
    print(f"   Folios: {len(folios)}")
    print(f"   HK Tasks: {len(tasks)}")
    return True
