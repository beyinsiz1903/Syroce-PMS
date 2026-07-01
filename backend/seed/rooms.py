"""Seed section 3: rooms (30 rooms across 6 categories).

Writes ctx['rooms'] (mutable list — bookings.py + housekeeping.py mutate status).
"""

from seed._helpers import _now, _uuid


async def seed_rooms(db, ctx):
    tenant_id = ctx["tenant_id"]
    room_configs = [
        # (type, count, floor_start, base_price_TRY, capacity, view, bed_type)
        ("Standard", 8, 1, 4500, 2, "city", "twin"),
        ("Deluxe", 8, 2, 6800, 2, "garden", "queen"),
        ("Superior", 6, 3, 9200, 3, "sea", "king"),
        ("Suite", 4, 4, 14000, 4, "sea", "king"),
        ("Junior Suite", 2, 5, 10500, 3, "pool", "queen"),
        ("Family", 2, 1, 7800, 5, "garden", "twin"),
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
    ctx["rooms"] = rooms
