"""PII-free daily occupancy: realised room nights versus on-the-books demand.

Deliberately does not change accounting/ADR metrics. Unassigned confirmed
reservations are demand, not evidence of a physically occupied room.
"""
from datetime import date, timedelta

from modules.pms_core.stay_night_metrics import as_date, booking_occupies_night, is_physical_room


def _calendar_scope(rooms, bookings, blocks, first: date, last: date, business_day: date, room_type=None):
    active = {str(r["id"]): r for r in rooms if r.get("id") and is_physical_room(r)}
    virtual_ids = {str(r["id"]) for r in rooms if r.get("id") and r.get("is_virtual")}
    virtual_numbers = {str(r["room_number"]) for r in rooms if r.get("room_number") and r.get("is_virtual")}
    by_number = {str(r["room_number"]): rid for rid, r in active.items() if r.get("room_number")}
    types = sorted({str(r["room_type"]) for r in active.values() if r.get("room_type")})
    selected = {rid for rid, r in active.items() if not room_type or r.get("room_type") == room_type}
    # Canonical PMS data has one booking per room. Repeated source rows must
    # not count twice; distinct reservations on one room are flagged below.
    unique = {str(b["id"]): b for b in bookings if b.get("id")}
    rows = []
    for offset in range((last - first).days + 1):
        day = first + timedelta(days=offset)
        blocked = {str(b.get("room_id")) for b in blocks
                   if str(b.get("status") or "active").strip().lower() == "active" and not b.get("allow_sell")
                   and as_date(b.get("start_date")) and as_date(b["start_date"]) <= day
                   and (not b.get("end_date") or (as_date(b["end_date"]) and day < as_date(b["end_date"])))} & selected
        occupied, assigned, stayovers, arrivals = set(), set(), set(), set()
        unassigned = conflicts = unknown = 0
        for bid, b in unique.items():
            if str(b.get("room_id")) in virtual_ids or (not b.get("room_id") and str(b.get("room_number")) in virtual_numbers):
                continue
            if not booking_occupies_night(b, day):
                continue
            if str(b.get('status') or '').strip().lower() == 'checked_out' and not booking_occupies_night(b, day, actual_only=True):
                continue
            rid = str(b.get("room_id") or by_number.get(str(b.get("room_number")), ""))
            kind = active[rid].get("room_type") if rid in active else b.get("room_type")
            if room_type and kind != room_type:
                continue
            if rid in selected:
                if rid in assigned:
                    conflicts += 1
                assigned.add(rid)
                # Distinct reservations are distinct inventory commitments, even
                # when wrongly assigned to the same room. Realised occupancy
                # still counts the unique physical room, not duplicate rows.
                key = f"booking:{bid}"
                if booking_occupies_night(b, day, actual_only=True):
                    occupied.add(rid)
            elif not rid and kind in types:
                unassigned += 1
                key = f"booking:{bid}"
            else:
                unknown += 1
                continue
            if as_date(b.get("check_in")) == day:
                arrivals.add(key)
            else:
                stayovers.add(key)
        capacity = len(selected) - len(blocked)
        expected = len(assigned) + unassigned + conflicts
        actual = len(occupied) if day <= business_day else None
        expected = expected if day >= business_day else None
        ratio = lambda value: round(value * 100 / capacity, 2) if capacity else None
        rows.append({
            "date": day.isoformat(), "physical_rooms": len(selected), "blocked_rooms": len(blocked),
            "available_rooms": capacity, "actual_rooms": actual, "expected_rooms": expected,
            "actual_occupancy": ratio(actual) if actual is not None else None,
            "expected_occupancy": ratio(expected) if expected is not None else None,
            "arrivals": len(arrivals) if expected is not None else None,
            "stayovers": len(stayovers) if expected is not None else None,
            "unassigned_rooms": unassigned if expected is not None else None,
            "overbooked_rooms": max(0, expected - capacity) if expected is not None else 0,
            "assignment_conflicts": conflicts, "unknown_room_references": unknown,
            "occupied_blocked_rooms": len(occupied & blocked),
        })
    totals = {}
    for prefix in ("actual", "expected"):
        relevant = [r for r in rows if r[f"{prefix}_rooms"] is not None]
        nights = sum(r[f"{prefix}_rooms"] for r in relevant)
        capacity = sum(r["available_rooms"] for r in relevant)
        totals[prefix] = {"room_nights": nights, "available_room_nights": capacity,
                          "occupancy": round(nights * 100 / capacity, 2) if capacity else None}
    return {"start_date": first.isoformat(), "end_date": last.isoformat(),
            "business_date": business_day.isoformat(), "room_type": room_type,
            "room_types": types, "rows": rows, "totals": totals}


def occupancy_calendar(rooms, bookings, blocks, first: date, last: date, business_day: date, room_type=None):
    """House and room-type rows from one tenant-scoped, consistent input set.

    Bucket inputs before calculating type rows: each booking/block participates
    in at most one type calculation, rather than scanning every booking for
    every room type. Rooms without a type get an explicit inventory bucket.
    """
    # Deduplicate before partitioning, otherwise two versions of the same
    # booking with different room types could appear in two matrix rows.
    bookings = list({str(booking["id"]): booking for booking in bookings if booking.get("id")}.values())
    data = _calendar_scope(rooms, bookings, blocks, first, last, business_day, room_type)
    active = {str(room["id"]): room for room in rooms if room.get("id") and is_physical_room(room)}
    by_number = {str(room["room_number"]): rid for rid, room in active.items() if room.get("room_number")}
    room_groups = {}
    for room in active.values():
        kind = str(room["room_type"]) if room.get("room_type") else None
        if not room_type or kind == room_type:
            room_groups.setdefault(kind, []).append(room)
    booking_groups = {kind: [] for kind in room_groups}
    for booking in bookings:
        rid = str(booking.get("room_id") or by_number.get(str(booking.get("room_number")), ""))
        kind = active[rid].get("room_type") if rid in active else booking.get("room_type")
        kind = str(kind) if kind else None
        if kind in booking_groups:
            booking_groups[kind].append(booking)
    block_groups = {kind: [] for kind in room_groups}
    for block in blocks:
        room = active.get(str(block.get("room_id")))
        if room:
            kind = str(room["room_type"]) if room.get("room_type") else None
            if kind in block_groups:
                block_groups[kind].append(block)
    groups = []
    for kind in sorted(room_groups, key=lambda value: (value is None, value or "")):
        scope = _calendar_scope(room_groups[kind], booking_groups[kind], block_groups[kind], first, last, business_day)
        groups.append({"room_type": kind, "label": kind or "Tipi tanımsız odalar", "physical_rooms": len(room_groups[kind]),
                       "rows": scope["rows"], "totals": scope["totals"]})
    data["room_type_groups"] = groups
    return data
