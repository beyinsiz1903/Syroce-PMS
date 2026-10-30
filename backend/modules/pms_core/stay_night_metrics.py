"""Canonical room-night metrics used by PMS dashboards and reports."""

from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from modules.pms_core.report_money import add_amount, currency_code, money, rounded, rounded_totals, single_amount

OCCUPYING_STATUSES = frozenset({"confirmed", "guaranteed", "checked_in", "in_house", "checked_out"})
ACTUAL_OCCUPANCY_STATUSES = frozenset({"checked_in", "in_house", "checked_out"})
NON_COMMERCIAL_STATUSES = frozenset({"cancelled", "canceled", "no_show", "noshow"})


def is_physical_room(room: dict) -> bool:
    """Virtual accounting/paymaster rooms are not sellable physical inventory."""
    return room.get("is_active") is not False and not room.get("is_virtual", False)


def reservation_party_counts(bookings):
    """Count declared people once per stay, not once per registered profile.

    Children includes the reservation's child/infant party; never add a second
    age-derived count. Missing or invalid counts remain unknown, not zero.
    """
    adults = children = unknown = 0
    seen = set()
    for booking in bookings:
        key = booking.get("id")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        values = [booking.get(field) for field in ("adults", "children")]
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
            unknown += 1
            continue
        adults += values[0]
        children += values[1]
    return {"adults": adults, "children": children, "known_total": adults + children,
            "total": None if unknown else adults + children, "unknown_booking_count": unknown,
            "basis": "reservation_party"}


async def with_checkin_business_date_evidence(database, tenant_id, bookings):
    """Read-only recovery from completed audit presence, never planned rates.

    A delayed wall-clock check-in can fall *inside* a long stay. Completed
    audit room candidates prove the booking was already in house that night,
    including complimentary candidates that legitimately posted no charge.
    Dry runs, pending/failed runs and unrelated tenants are not evidence.
    """
    candidates = {}
    for booking in bookings:
        ci, co, actual = (as_date(booking.get(key)) for key in ("check_in", "check_out", "checked_in_at"))
        if booking.get("id") and not booking.get("checked_in_business_date") and ci and co and actual and ci < actual < co:
            candidates[str(booking["id"])] = (ci, co, actual)
    if not candidates:
        return bookings
    items = await database.night_audit_run_items.find({"tenant_id": tenant_id, "booking_id": {"$in": sorted(candidates)},
        "posting_type": "room_charge", "$or": [{"status": "posted"}, {"status": "skipped", "reason": "complimentary_accommodation"}]},
        {"_id": 0, "booking_id": 1, "run_id": 1, "posting_date": 1}).to_list(None)
    run_ids = sorted({str(item["run_id"]) for item in items if item.get("run_id")})
    runs = await database.night_audit_runs.find({"tenant_id": tenant_id, "id": {"$in": run_ids},
        "status": {"$in": ["completed", "completed_with_exceptions"]}}, {"_id": 0, "id": 1, "business_date": 1}).to_list(None) if run_ids else []
    completed = {str(run["id"]): as_date(run.get("business_date")) for run in runs}
    earliest = {}
    for item in items:
        bid, day = str(item.get("booking_id")), as_date(item.get("posting_date"))
        if bid not in candidates or not day or completed.get(str(item.get("run_id"))) != day:
            continue
        ci, co, actual = candidates[bid]
        if ci <= day < min(co, actual):
            earliest[bid] = min(earliest.get(bid, day), day)
    return [{**booking, "checked_in_business_date": earliest[str(booking["id"])].isoformat()}
            if str(booking.get("id")) in earliest else booking for booking in bookings]


def as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


# Backward-compatible private alias for existing callers.
_as_date = as_date


def stay_overlap_match(first: date, last: date) -> dict:
    """Select overlapping nights with independent ISO/BSON storage on each edge."""
    start_dt = datetime.combine(first, datetime.min.time(), UTC)
    stop = last + timedelta(days=1)
    stop_dt = datetime.combine(stop, datetime.min.time(), UTC)
    return {"$or": [
        {"check_out": {"$gt": lower}, "check_in": {"$lt": upper}}
        for lower in (first.isoformat(), start_dt)
        for upper in (stop.isoformat(), stop_dt)
    ]}


def stay_day_match(day: date, *, include_stayovers=True) -> dict:
    """Mongo selection for ISO/BSON arrival, departure and overlapping stays."""
    start = datetime.combine(day, datetime.min.time(), UTC)
    end = start + timedelta(days=1)
    clauses = []
    for field in ("check_in", "check_out"):
        clauses.extend([{field: {"$gte": day.isoformat(), "$lt": end.date().isoformat()}}, {field: {"$gte": start, "$lt": end}}])
    if include_stayovers:
        clauses.append({"$and": [
            {"$or": [{"check_in": {"$lte": day.isoformat()}}, {"check_in": {"$lt": end}}]},
            {"$or": [{"check_out": {"$gt": day.isoformat()}}, {"check_out": {"$gt": start}}]},
        ]})
    return {"$or": clauses}


def room_block_overlap_match(first: date, last: date) -> dict:
    """Allow independent ISO/BSON edges and open-ended room blocks."""
    lower = (first.isoformat(), datetime.combine(first, datetime.min.time(), UTC))
    stop = last + timedelta(days=1)
    upper = (stop.isoformat(), datetime.combine(stop, datetime.min.time(), UTC))
    return {"$or": [
        *[{"start_date": {"$lt": end}, "end_date": {"$gt": start}} for start in lower for end in upper],
        *[{"start_date": {"$lt": end}, "end_date": None} for end in upper],
    ]}


def booking_occupies_night(booking: dict, day: date, *, actual_only: bool = False) -> bool:
    """Return whether one booking occupies ``day`` as a hotel room-night.

    Hotel stays are half-open intervals: arrival is included and departure is
    excluded.  ``actual_only`` additionally requires an actual in-house status
    and respects early check-out / late check-in timestamps.  This prevents a
    historical confirmed/no-show reservation from becoming realised occupancy.
    """
    status = str(booking.get("status") or "").strip().lower()
    allowed = ACTUAL_OCCUPANCY_STATUSES if actual_only else OCCUPYING_STATUSES
    if status not in allowed:
        return False
    check_in = as_date(booking.get("check_in"))
    check_out = as_date(booking.get("check_out"))
    if not check_in or not check_out or not (check_in <= day < check_out):
        return False
    if actual_only:
        actual_in = as_date(booking.get("checked_in_business_date")) or as_date(booking.get("checked_in_at"))
        actual_out = as_date(booking.get("checked_out_business_date")) or as_date(booking.get("checked_out_at"))
        # A wall-clock audit timestamp outside the stay can reflect a lagging
        # PMS business day. It must not erase that business-day occupancy.
        if actual_in and check_in <= actual_in < check_out and day < actual_in:
            return False
        if actual_out and day >= actual_out:
            return False
    return True


def booking_nights(booking: dict) -> int:
    check_in = as_date(booking.get("check_in"))
    check_out = as_date(booking.get("check_out"))
    if not check_in or not check_out or check_out <= check_in:
        return 0
    return (check_out - check_in).days


def allocated_revenue_for_night(booking: dict, day: date, daily_rates: dict | None = None) -> Decimal:
    """Use an explicit nightly plan first; allocate the stay only without one.

    Ambiguous, negative or foreign-currency plans cannot become a plausible
    average. Callers must expose the source error instead of inventing a price.
    """
    nights = booking_nights(booking)
    if not nights or not booking_occupies_night(booking, day) or booking.get("is_complimentary"):
        return Decimal("0")
    choices = (daily_rates or {}).get((str(booking.get("id")), day.isoformat()), [])
    if len(choices) > 1:
        raise ValueError("Ambiguous daily room price")
    if choices:
        plan = choices[0]
        if plan.get("currency") and currency_code(plan["currency"]) != currency_code(booking.get("currency")):
            raise ValueError("Daily room price currency mismatch")
        amount = Decimal(0) if plan.get("is_complimentary") else money(plan["rate"])
        if amount < 0:
            raise ValueError("Negative daily room price")
        return amount
    return _allocated_nightly(_money(booking.get("total_amount")) / nights, (day - as_date(booking.get("check_in"))).days)


async def load_daily_rate_index(database, tenant_id, bookings, first, last):
    booking_ids = [str(row["id"]) for row in bookings if row.get("id")]
    if not booking_ids:
        return {}
    rows = await database.daily_rates.find({"tenant_id": tenant_id, "booking_id": {"$in": booking_ids}},
        {"_id": 0, "booking_id": 1, "date": 1, "rate": 1, "currency": 1, "is_complimentary": 1}).to_list(None)
    result = {}
    for row in rows:
        day = as_date(row.get("date"))
        if day and first <= day <= last:
            result.setdefault((str(row["booking_id"]), day.isoformat()), []).append(row)
    return result


def _allocated_nightly(nightly: Decimal, offset: int) -> Decimal:
    cent = Decimal("0.01")
    return (nightly * (offset + 1)).quantize(cent, rounding=ROUND_HALF_UP) - (nightly * offset).quantize(cent, rounding=ROUND_HALF_UP)


def _money(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _room_key(booking: dict) -> str | None:
    room_id = booking.get("room_id")
    if room_id:
        return f"id:{room_id}"
    room_number = booking.get("room_number")
    if room_number:
        return f"number:{room_number}"
    return None


def calculate_stay_night_metrics(
    bookings: list[dict],
    rooms: list[dict],
    start_date: date,
    end_date: date,
    *,
    actual_only: bool = False,
    room_blocks: list[dict] | None = None,
    fallback_currency: str = "TRY",
    daily_rates: dict | None = None,
) -> list[dict]:
    """Return inclusive daily metrics using ``check_in <= day < check_out``.

    Occupancy is the number of unique assigned rooms. Explicit daily plans take
    precedence over stay-total allocation. Inactive rooms are excluded.
    """
    active_rooms = [room for room in rooms if is_physical_room(room)]
    active_room_keys = {
        f"id:{room.get('id')}" if room.get("id") else f"number:{room.get('room_number')}"
        for room in active_rooms
        if room.get("id") or room.get("room_number")
    }
    room_number_keys = {
        str(room.get("room_number")).strip(): f"id:{room.get('id')}"
        for room in active_rooms
        if room.get("id") and room.get("room_number") not in (None, "")
    }
    days = (end_date - start_date).days + 1
    result = []

    parsed = []
    for booking in bookings:
        status = str(booking.get("status") or "").strip().lower()
        allowed = ACTUAL_OCCUPANCY_STATUSES if actual_only else OCCUPYING_STATUSES
        if status not in allowed:
            continue
        check_in = as_date(booking.get("check_in"))
        check_out = as_date(booking.get("check_out"))
        room_key = _room_key(booking)
        if room_key and room_key.startswith("number:"):
            room_key = room_number_keys.get(room_key.removeprefix("number:"), room_key)
        # Unknown/deactivated room references must not inflate occupied rooms or
        # divide ADR by inventory that is absent from the denominator.
        if room_key not in active_room_keys:
            room_key = None
        if not check_in or not check_out or check_out <= check_in or not room_key:
            continue
        parsed.append(
            (
                check_in,
                check_out,
                as_date(booking.get("checked_in_business_date")) or as_date(booking.get("checked_in_at")),
                as_date(booking.get("checked_out_business_date")) or as_date(booking.get("checked_out_at")),
                room_key,
                booking,
                currency_code(booking.get("currency"), fallback_currency),
            )
        )

    for offset in range(max(days, 0)):
        day = start_date + timedelta(days=offset)
        blocked_room_keys = set()
        for block in room_blocks or []:
            if block.get("allow_sell", False) or str(block.get("status") or "active").lower() != "active":
                continue
            block_start = as_date(block.get("start_date"))
            block_end = as_date(block.get("end_date"))
            if block_start and block_start <= day and (not block_end or day < block_end):
                room_id = block.get("room_id")
                if room_id:
                    blocked_room_keys.add(f"id:{room_id}")
        total_rooms = len(active_room_keys - blocked_room_keys)
        occupied_rooms: set[str] = set()
        sold_rooms: set[str] = set()
        sold_by_currency = {}
        revenue_by_currency = {}
        for check_in, check_out, actual_in, actual_out, room_key, booking, currency in parsed:
            actual_window_ok = not actual_only or ((not actual_in or not check_in <= actual_in < check_out or actual_in <= day) and (not actual_out or day < actual_out))
            if check_in <= day < check_out and actual_window_ok:
                occupied_rooms.add(room_key)
                nightly_revenue = allocated_revenue_for_night({**booking, "currency": currency}, day, daily_rates)
                add_amount(revenue_by_currency, currency, nightly_revenue)
                if nightly_revenue > 0:
                    sold_rooms.add(room_key)
                    sold_by_currency.setdefault(currency, set()).add(room_key)
        occupied = len(occupied_rooms)
        sold = len(sold_rooms)
        revenue_by_currency = rounded_totals(revenue_by_currency)
        revenue_value = single_amount(revenue_by_currency)
        occupancy_rate = round(min((occupied / total_rooms * 100), 100.0), 2) if total_rooms else 0
        # Complimentary rooms contribute to occupancy but are not sold rooms;
        # including them in ADR understated the achieved selling price.
        sold_counts = {code: len(keys) for code, keys in sold_by_currency.items()}
        adr_by_currency = {code: rounded(money(amount) / sold_counts[code]) if sold_counts.get(code) else 0 for code, amount in revenue_by_currency.items()}
        revpar_by_currency = {code: rounded(money(amount) / total_rooms) if total_rooms else 0 for code, amount in revenue_by_currency.items()}
        adr = single_amount(adr_by_currency)
        revpar = single_amount(revpar_by_currency)
        result.append(
            {
                "date": day.isoformat(),
                "occupied_rooms": occupied,
                "sold_rooms": sold,
                "sold_rooms_by_currency": sold_counts,
                "total_rooms": total_rooms,
                "occupancy_rate": occupancy_rate,
                "revenue": revenue_value,
                "adr": adr,
                "revpar": revpar,
                "revenue_by_currency": revenue_by_currency,
                "adr_by_currency": adr_by_currency,
                "revpar_by_currency": revpar_by_currency,
                "mixed_currency": revenue_value is None,
            }
        )
    return result


async def load_stay_night_metrics(db, tenant_id: str, start_date: date, end_date: date, *, actual_only: bool = False, include_performance: bool = False) -> list[dict]:
    """Load the minimum shared dataset and calculate canonical metrics."""
    rooms = await db.rooms.find(
        {"tenant_id": tenant_id, "is_active": {"$ne": False}, "is_virtual": {"$ne": True}},
        {"_id": 0, "id": 1, "room_number": 1, "is_active": 1, "is_virtual": 1},
    ).to_list(None)
    bookings = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": list(OCCUPYING_STATUSES)},
            **stay_overlap_match(start_date, end_date),
        },
        {
            "_id": 0,
            "id": 1,
            "room_id": 1,
            "room_number": 1,
            "check_in": 1,
            "check_out": 1,
            "status": 1,
            "total_amount": 1,
            "currency": 1,
            "is_complimentary": 1,
            "checked_in_at": 1,
            "checked_in_business_date": 1,
            "checked_out_at": 1,
            "checked_out_business_date": 1,
            **(dict.fromkeys(("ota_channel", "source_channel", "channel", "booking_source", "source"), 1) if include_performance else {}),
        },
    ).to_list(None)
    if actual_only:
        bookings = await with_checkin_business_date_evidence(db, tenant_id, bookings)
    room_blocks = await db.room_blocks.find(
        {
            "tenant_id": tenant_id,
            "status": "active",
            "allow_sell": {"$ne": True},
            **room_block_overlap_match(start_date, end_date),
        },
        {"_id": 0, "room_id": 1, "start_date": 1, "end_date": 1, "status": 1, "allow_sell": 1},
    ).to_list(None)
    fallback_currency = "TRY"
    if any(not str(booking.get("currency") or "").strip() for booking in bookings):
        from core.tenant_currency import get_tenant_currency

        fallback_currency = (await get_tenant_currency(tenant_id))[0]
    daily_rates = await load_daily_rate_index(db, tenant_id, bookings, start_date, end_date)
    metrics = calculate_stay_night_metrics(bookings, rooms, start_date, end_date, actual_only=actual_only, room_blocks=room_blocks, fallback_currency=fallback_currency, daily_rates=daily_rates)
    if include_performance:
        from modules.pms_core.daily_stay_performance import daily_stay_performance

        for metric in metrics:
            metric["performance"] = daily_stay_performance(bookings, rooms, as_date(metric["date"]))
    return metrics
