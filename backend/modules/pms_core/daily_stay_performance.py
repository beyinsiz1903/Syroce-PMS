"""Daily, actual in-house reservation metrics; unknown channels are not direct.

Shares use reservations (not people or revenue). Length of stay is the full
booked stay of the same actual-night cohort, not elapsed nights or arrivals.
"""
import re

from modules.pms_core.stay_night_metrics import booking_nights, booking_occupies_night, is_physical_room

_OTA = {"ota", "booking", "bookingcom", "expedia", "airbnb", "agoda", "hotelscom", "tripcom", "etstur", "otelz"}
_DIRECT = {"direct", "phone", "walkin", "website", "web", "websitesi", "telephone", "telefon", "resepsiyon"}
_AGENCY = {"agency", "agent", "travelagent", "acente", "corporate", "company"}


def channel_group(booking):
    # A concrete OTA wins over generic/default direct values written by imports.
    values = [re.sub(r"[^a-z0-9]", "", str(booking.get(key) or "").casefold())
              for key in ("ota_channel", "source_channel", "channel", "booking_source", "source")]
    if any(value in _OTA for value in values):
        return "ota"
    if any(value in _AGENCY for value in values):
        return "agency"
    for value in values:
        if value in _DIRECT:
            return "direct"
        if value:
            return "unknown"
    return "unknown"


def daily_stay_performance(bookings, rooms, day):
    physical = [room for room in rooms if is_physical_room(room)]
    ids = {str(room["id"]) for room in physical if room.get("id")}
    numbers = {str(room["room_number"]) for room in physical if room.get("room_number") is not None}
    counts = dict.fromkeys(("ota", "direct", "agency", "unknown"), 0)
    nights = count = 0
    seen = set()
    for booking in bookings:
        if not booking_occupies_night(booking, day, actual_only=True):
            continue
        room_id = booking.get("room_id")
        assigned_physical = str(room_id) in ids if room_id else str(booking.get("room_number")) in numbers
        if not assigned_physical:
            continue
        identity = booking.get("id")
        if identity and identity in seen:
            continue
        if identity:
            seen.add(identity)
        count += 1
        nights += booking_nights(booking)
        counts[channel_group(booking)] += 1
    return {
        "date": day.isoformat(),
        "basis": "actual_in_house_reservations_on_business_date",
        "length_of_stay_basis": "full_booked_stay_nights_per_reservation",
        "reservation_count": count,
        "booked_stay_nights": nights,
        "average_stay_nights": round(nights / count, 2) if count else None,
        "channel_counts": counts,
        "channel_share_pct": {key: round(value / count * 100, 2) if count else None for key, value in counts.items()},
        "channel_classification_complete": counts["unknown"] == 0,
    }
