"""Shared, read-only physical/category occupancy projection for channel calendars.

The caller supplies its tenant-aware database. No provider call or inventory
write belongs here; canonical room-night locks remain a separate upper bound.
"""
from datetime import datetime, timedelta


async def get_room_counts(database, tenant_id):
    rooms = await database.rooms.find(
        {'tenant_id': tenant_id, 'is_active': {'$ne': False}, 'is_virtual': {'$ne': True}},
        {'_id': 0, 'id': 1, 'room_type': 1, 'status': 1},
    ).to_list(500)
    counts, ids = {}, {}
    for room in rooms:
        room_type = room.get('room_type', '')
        counts.setdefault(room_type, {'total': 0, 'available': 0})
        counts[room_type]['total'] += 1
        if room.get('status') == 'available':
            counts[room_type]['available'] += 1
        ids.setdefault(room_type, []).append(room['id'])
    return counts, ids


async def get_active_bookings(database, tenant_id, start_date, end_date):
    # Inclusive last sellable night, checkout exclusive, including timestamps.
    end_exclusive = (datetime.strptime(end_date, '%Y-%m-%d').date() + timedelta(days=1)).isoformat()
    return await database.bookings.find(
        {'tenant_id': tenant_id,
         'status': {'$in': ['pending', 'confirmed', 'guaranteed', 'checked_in']},
         'check_in': {'$lt': end_exclusive}, 'check_out': {'$gt': start_date}},
        {'_id': 0, 'room_id': 1, 'room_type': 1, 'check_in': 1, 'check_out': 1},
    ).to_list(10000)


def booking_room_type(booking, room_type_by_id, known_room_types):
    # A real physical assignment wins after a move. Unassigned bookings consume
    # their exact mapped category; never merge similarly named room types.
    assigned_type = room_type_by_id.get(booking.get('room_id'))
    if assigned_type:
        return assigned_type
    mapped_type = booking.get('room_type')
    return mapped_type if isinstance(mapped_type, str) and mapped_type in known_room_types else None


def build_sold_count_index(room_ids_by_type, active_bookings, start_date, end_date):
    room_type_by_id = {room_id: room_type for room_type, ids in room_ids_by_type.items() for room_id in ids}
    if not room_ids_by_type:
        return {}
    start = datetime.strptime(start_date, '%Y-%m-%d').date()
    end = datetime.strptime(end_date, '%Y-%m-%d').date()
    sold = {}
    for booking in active_bookings:
        room_type = booking_room_type(booking, room_type_by_id, room_ids_by_type)
        if not room_type:
            continue
        try:
            check_in = datetime.strptime((booking.get('check_in') or '')[:10], '%Y-%m-%d').date()
            check_out = datetime.strptime((booking.get('check_out') or '')[:10], '%Y-%m-%d').date()
        except ValueError:
            continue
        day, last = max(start, check_in), min(end, check_out - timedelta(days=1))
        while day <= last:
            key = (room_type, day.isoformat())
            sold[key] = sold.get(key, 0) + 1
            day += timedelta(days=1)
    return sold


async def exely_publishable_availability(database, tenant_id, room_type, mapping, canonical):
    """Respect the availability owner's calendar allotment AND physical locks.

    Calendar keys are panel IDs, not wire aliases. A cap is a base allotment:
    subtract current active category bookings once (the calendar's rule), then
    take the minimum with lock-based sellable inventory. Never subtract those
    bookings again from canonical sellable or replace zero with a fallback.
    """
    dates = sorted(canonical)
    if not dates:
        return {}
    if any(type(value) is not int or value < 0 for value in canonical.values()):
        raise ValueError('Invalid canonical availability')
    room_code, rate_code = mapping.get('exely_room_code'), mapping.get('exely_rate_plan_code')
    if not room_code or not rate_code:
        raise ValueError('Missing calendar owner identifiers')
    counts, ids = await get_room_counts(database, tenant_id)
    bookings = await get_active_bookings(database, tenant_id, dates[0], dates[-1])
    if sum(row['total'] for row in counts.values()) >= 500 or len(bookings) >= 10000:
        raise ValueError('Incomplete calendar projection')
    sold = build_sold_count_index(ids, bookings, dates[0], dates[-1])
    rows = await database.rate_calendar.find(
        {'tenant_id': tenant_id, 'room_type_code': room_code, 'rate_plan_code': rate_code,
         'date': {'$in': dates}},
        {'_id': 0, 'date': 1, 'availability': 1},
    ).to_list(len(dates) + 1)
    caps = {}
    for row in rows:
        day, cap = row['date'], row.get('availability')
        if day not in canonical or day in caps or (cap is not None and (type(cap) is not int or cap < 0)):
            raise ValueError('Ambiguous or invalid calendar allotment')
        caps[day] = cap
    physical_total = counts.get(room_type, {}).get('total', 0)
    return {day: min(value, max((caps.get(day) if caps.get(day) is not None else physical_total)
                               - sold.get((room_type, day), 0), 0))
            for day, value in canonical.items()}
