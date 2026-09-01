from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable


def calculate_ktb_stays(
    bookings: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    normalize_country: Callable[[str | None], str],
) -> dict[str, Any]:
    """Calculate Ministry monthly arrivals and nights from overlapping stays."""
    result: dict[str, Any] = {
        "room_nights_sold": 0,
        "arrivals_total": 0,
        "arrivals_domestic": 0,
        "arrivals_foreign": 0,
        "arrivals_unspecified": 0,
        "carried_in_guests": 0,
        "person_nights_domestic": 0,
        "person_nights_foreign": 0,
        "person_nights_unspecified": 0,
        "nights_by_country": {},
        "missing_nationality": [],
        "missing_nationality_total": 0,
        "adults_fallback_count": 0,
        "valid_booking_count": 0,
    }
    for booking in bookings:
        try:
            check_in = datetime.fromisoformat(str(booking["check_in"]).replace("Z", "+00:00"))
            check_out = datetime.fromisoformat(str(booking["check_out"]).replace("Z", "+00:00"))
            if check_in.tzinfo is None:
                check_in = check_in.replace(tzinfo=UTC)
            if check_out.tzinfo is None:
                check_out = check_out.replace(tzinfo=UTC)
        except (KeyError, TypeError, ValueError):
            continue

        # PMS stay intervals are business dates, not elapsed 24-hour blocks.
        # 1 Sep 14:00 -> 3 Sep 11:00 is therefore two nights, not one.
        effective_check_in = max(check_in.date(), start.date())
        effective_check_out = min(check_out.date(), end.date())
        nights = max(0, (effective_check_out - effective_check_in).days)
        if nights == 0:
            continue
        result["valid_booking_count"] += 1
        if booking.get("adults") in (None, 0):
            result["adults_fallback_count"] += 1
        guests = int(booking.get("adults") or 1) + int(booking.get("children") or 0)
        country = normalize_country(
            booking.get("nationality") or booking.get("guest_country") or booking.get("country")
        )
        person_nights = nights * guests
        result["room_nights_sold"] += nights
        result["arrivals_total"] += guests
        if check_in.date() < start.date():
            # Ministry rule: guests already in-house are a new arrival on day 1.
            result["carried_in_guests"] += guests
        country_nights = result["nights_by_country"]
        country_nights[country] = country_nights.get(country, 0) + person_nights
        if country == "Türkiye":
            result["arrivals_domestic"] += guests
            result["person_nights_domestic"] += person_nights
        elif country == "Belirtilmemiş":
            result["arrivals_unspecified"] += guests
            result["person_nights_unspecified"] += person_nights
            result["missing_nationality_total"] += 1
            if len(result["missing_nationality"]) < 50:
                result["missing_nationality"].append(
                    {
                        "id": booking.get("id") or booking.get("booking_id"),
                        "confirmation_number": booking.get("confirmation_number"),
                        "guest_name": booking.get("primary_guest_name") or booking.get("guest_name"),
                        "check_in": str(booking.get("check_in") or "")[:10],
                        "check_out": str(booking.get("check_out") or "")[:10],
                    }
                )
        else:
            result["arrivals_foreign"] += guests
            result["person_nights_foreign"] += person_nights

    result["person_nights_total"] = (
        result["person_nights_domestic"]
        + result["person_nights_foreign"]
        + result["person_nights_unspecified"]
    )
    return result
