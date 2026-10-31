"""Read-only manager cohort, sharing actual-night and physical-room rules."""
from modules.pms_core.stay_night_metrics import (
    NON_COMMERCIAL_STATUSES,
    as_date,
    booking_nights,
    booking_occupies_night,
    calculate_stay_night_metrics,
    is_physical_room,
    room_block_overlap_match,
    stay_day_match,
    with_checkin_business_date_evidence,
)


async def manager_daily_operations(database, tenant_id, day):
    rooms = await database.rooms.find({"tenant_id": tenant_id}, {"_id": 0, "id": 1, "room_number": 1, "is_active": 1, "is_virtual": 1}).to_list(None)
    rooms = [room for room in rooms if is_physical_room(room)]
    ids = {"id:" + str(room["id"]) if room.get("id") else "number:" + str(room.get("room_number")) for room in rooms}
    numbers = {str(room.get("room_number")): "id:" + str(room["id"]) if room.get("id") else "number:" + str(room.get("room_number")) for room in rooms if room.get("room_number") is not None}
    fields = ("id", "room_id", "room_number", "status", "check_in", "check_out", "checked_in_at", "checked_out_at", "checked_in_business_date", "checked_out_business_date", "vip", "guest_vip", "group_id", "is_group", "source", "channel", "booking_source", "guest_nationality", "nationality")
    rows = await database.bookings.find({"tenant_id": tenant_id, **stay_day_match(day)}, {"_id": 0, **dict.fromkeys(fields, 1)}).to_list(None)
    rows = await with_checkin_business_date_evidence(database, tenant_id, rows)
    blocks = await database.room_blocks.find({"tenant_id": tenant_id, "status": "active", "allow_sell": {"$ne": True}, **room_block_overlap_match(day, day)}, {"_id": 0}).to_list(None)
    metric = calculate_stay_night_metrics(rows, rooms, day, day, actual_only=True, room_blocks=blocks)[0]
    seen, cohort = set(), []
    for row in rows:
        room_id = "id:" + str(row["room_id"]) if row.get("room_id") else numbers.get(str(row.get("room_number")))
        identity = row.get("id")
        if room_id not in ids or not booking_occupies_night(row, day, actual_only=True) or identity in seen:
            continue
        if identity:
            seen.add(identity)
        cohort.append(row)
    nationality, lengths = {}, {"1": 0, "2-3": 0, "4-7": 0, "7+": 0}
    for row in cohort:
        country = row.get("guest_nationality") or row.get("nationality") or "Belirtilmemiş"
        nationality[country] = nationality.get(country, 0) + 1
        nights = booking_nights(row)
        lengths["1" if nights <= 1 else "2-3" if nights <= 3 else "4-7" if nights <= 7 else "7+"] += 1
    commercial = [row for row in rows if str(row.get("status") or "").lower() not in NON_COMMERCIAL_STATUSES]
    return {"date": day.isoformat(), "basis": "actual_in_house_reservations_on_business_date",
        "totalRooms": len(rooms), "availableRooms": metric["total_rooms"],
        "oooRooms": len(rooms) - metric["total_rooms"], "occupiedRooms": metric["occupied_rooms"],
        "emptyRooms": max(0, metric["total_rooms"] - metric["occupied_rooms"]), "occupancy": metric["occupancy_rate"],
        "inhouseReservations": len(cohort), "vipGuests": sum(bool(row.get("vip") or row.get("guest_vip")) for row in cohort),
        "groupBookings": sum(bool(row.get("group_id") or row.get("is_group")) for row in cohort),
        "arrivals": sum(as_date(row.get("check_in")) == day for row in commercial),
        "departures": sum(as_date(row.get("check_out")) == day for row in commercial),
        "noShows": sum(str(row.get("status") or "").lower() in {"no_show", "noshow"} and as_date(row.get("check_in")) == day for row in rows),
        "walkIns": sum(as_date(row.get("check_in")) == day and str(row.get("source") or row.get("channel") or row.get("booking_source") or "").lower() in {"walk_in", "walkin"} for row in commercial),
        "nationality": nationality, "losDistribution": lengths}
