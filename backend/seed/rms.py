"""Seed sections 12 + 13 + 14 + 15: RMS room types, extended history, yield, seasons.

Reads ctx['guests'], ctx['rooms']. Writes ctx['room_types_docs'],
ctx['extended_bookings'], ctx['yield_rules'], ctx['seasonal_entries'].
"""

import random
from datetime import timedelta

from seed._helpers import _encrypt_doc, _now, _uuid
from seed.bookings import RATE_PLANS


async def seed_rms(db, ctx):
    tenant_id = ctx["tenant_id"]
    rooms = ctx["rooms"]
    guests = ctx["guests"]

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
        room_types_docs.append(
            {
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
            }
        )
    await db.room_types.insert_many(room_types_docs)
    ctx["room_types_docs"] = room_types_docs

    # ── 13. Extended Historical Bookings (6 months, for RMS) ──
    extended_bookings = []
    channels_weighted = ["direct"] * 35 + ["booking_com"] * 25 + ["expedia"] * 20 + ["airbnb"] * 10 + ["own_website"] * 10
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

            extended_bookings.append(
                {
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
                    "rate_plan": random.choice(RATE_PLANS),
                    "special_requests": None,
                    "group_booking_id": None,
                    "company_id": None,
                    "created_at": (ci - timedelta(days=random.randint(1, 45))).isoformat(),
                    "cancelled_at": ci.isoformat() if status == "cancelled" else None,
                    "cancellation_reason": random.choice(["Planlar degisti", "Baska otel buldum", "Seyahat iptal", "Fiyat cok yuksek", "Kisisel nedenler"]) if status == "cancelled" else None,
                }
            )

    if extended_bookings:
        extended_bookings = [_encrypt_doc(b, "bookings") for b in extended_bookings]
        await db.bookings.insert_many(extended_bookings)
    ctx["extended_bookings"] = extended_bookings

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
    ctx["yield_rules"] = yield_rules

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
    ctx["seasonal_entries"] = seasonal_entries
