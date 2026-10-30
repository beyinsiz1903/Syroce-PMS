"""Internal commercial-contract usage; never an ARI/inventory mutation."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from math import isfinite

from fastapi import HTTPException

from modules.pms_core.stay_night_metrics import as_date

ACTIVE = frozenset({"pending", "confirmed", "guaranteed", "checked_in", "in_house"})
OPERATOR_FIELDS = ("agency_name", "channel_display", "channel", "source_channel", "ota_channel")


def contract_usage(contract, bookings):
    start, end = as_date(contract.get("start_date")), as_date(contract.get("end_date"))
    if not start or not end or end <= start:
        raise HTTPException(409, "Contract date range is invalid; review source before release")
    events = defaultdict(int)
    revenues = defaultdict(Decimal)
    count = unknown_currency = 0
    operator = str(contract.get("tour_operator") or "").strip().casefold()
    for row in bookings:
        if row.get("status") not in ACTIVE:
            continue
        linked = row.get("allotment_contract_id") == contract.get("id")
        named = operator and any(operator in str(row.get(field) or "").casefold() for field in OPERATOR_FIELDS)
        if not (linked or named):
            continue
        checkin, checkout = as_date(row.get("check_in")), as_date(row.get("check_out"))
        if not checkin or not checkout or checkout <= checkin:
            raise HTTPException(409, "Matched booking dates are invalid; review source before release")
        left, right = max(start, checkin), min(end, checkout)
        if right <= left:
            continue
        count += 1
        events[left] += 1
        events[right] -= 1
        code = str(row.get("currency") or "").strip().upper()
        if code == "TL":
            code = "TRY"
        try:
            amount = Decimal(str(row.get("total_amount")))
            if not amount.is_finite():
                raise InvalidOperation
        except (InvalidOperation, ValueError, TypeError):
            raise HTTPException(409, "Matched booking amount is invalid") from None
        if len(code) != 3 or not code.isalpha():
            unknown_currency += 1
        else:
            revenues[code] += amount
    peak = current = 0
    for day in sorted(events):
        current += events[day]
        peak = max(peak, current)
    try:
        amounts = {code: float(value.quantize(Decimal('0.01'))) for code, value in sorted(revenues.items())}
        if not all(isfinite(value) for value in amounts.values()):
            raise InvalidOperation
    except (InvalidOperation, OverflowError):
        raise HTTPException(409, "Matched booking amount cannot be represented safely") from None
    scalar = next(iter(amounts.values())) if len(amounts) == 1 and not unknown_currency else None
    return {"used_rooms": peak, "bookings_count": count, "total_revenue": scalar,
            "total_revenue_by_currency": amounts, "unknown_currency_bookings": unknown_currency,
            "usage_basis": "peak_concurrent_bookings", "revenue_basis": "matched_booking_totals_not_nightly_allocation"}


def available_rooms(contract, used):
    try:
        raw_allocated, raw_released = contract["allocated_rooms"], contract.get("released_rooms") or 0
        allocated, released = int(raw_allocated), int(raw_released)
        if isinstance(raw_allocated, bool) or isinstance(raw_released, bool) or Decimal(str(raw_allocated)) != allocated or Decimal(str(raw_released)) != released:
            raise ValueError
    except (ValueError, TypeError, KeyError, InvalidOperation, OverflowError):
        raise HTTPException(409, "Invalid contract room quantities") from None
    if allocated < 0 or released < 0:
        raise HTTPException(409, "Invalid contract room quantities")
    return max(0, allocated - used - released)
