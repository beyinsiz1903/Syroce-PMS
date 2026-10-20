"""Current physical room occupancy, not forecast/booked stay-night occupancy.

An overdue checked-in stay remains in house until checkout. Keep this mobile
snapshot aligned with the room list (including independent housekeeping state).
"""

from modules.pms_core.operational_snapshot_service import active_room_filter


def _key(value):
    return str(value if value is not None else "").strip()


def current_room_occupancy(rooms, bookings):
    checked_in = [b for b in bookings if b.get("status") == "checked_in"]
    assigned_ids = {_key(b.get("room_id")) for b in checked_in if _key(b.get("room_id"))}
    assigned_numbers = {_key(b.get("room_number")) for b in checked_in if not _key(b.get("room_id")) and _key(b.get("room_number"))}
    occupied = 0
    for room in rooms:
        statuses = {_key(room.get(field)).lower() for field in ("status", "room_status", "housekeeping_status", "hk_status")}
        # Same priority as mobile roomPresentation: blocked rooms are not
        # labelled occupied, even when a stale assignment still exists.
        if statuses.intersection({"maintenance", "out_of_order"}):
            continue
        if _key(room.get("id")) in assigned_ids or _key(room.get("room_number")) in assigned_numbers or _key(room.get("current_booking_id")) or _key(room.get("status")).lower() == "occupied":
            occupied += 1
    total = len(rooms)
    return {
        "occupied_rooms": occupied,
        "total_rooms": total,
        "occupancy_pct": round(occupied / total * 100, 1) if total else 0,
        "occupancy_basis": "current_room_state",
    }


async def load_current_room_occupancy(database, tenant_id):
    rooms = await database.rooms.find(
        active_room_filter(tenant_id),
        {"_id": 0, "id": 1, "room_number": 1, "status": 1, "room_status": 1, "housekeeping_status": 1, "hk_status": 1, "current_booking_id": 1},
    ).to_list(None)
    bookings = await database.bookings.find(
        {"tenant_id": tenant_id, "status": "checked_in"},
        {"_id": 0, "room_id": 1, "room_number": 1, "status": 1},
    ).to_list(None)
    return current_room_occupancy(rooms, bookings)
