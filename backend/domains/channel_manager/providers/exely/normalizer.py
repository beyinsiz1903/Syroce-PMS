"""
Exely Reservation Normalizer
Converts Exely-specific reservation format to the canonical PMS format
used by the common ingest pipeline.
"""
from datetime import datetime
from typing import Any


def normalize_reservation(raw: dict[str, Any], source: str = "pull") -> dict[str, Any]:
    """
    Convert Exely reservation payload (from response_parser) to canonical PMS format.
    """
    rooms = raw.get("rooms", [])
    room_details = []
    for room in rooms:
        room_details.append({
            "room_type_code": room.get("room_type_code", ""),
            "rate_plan_code": room.get("rate_plan_code", ""),
            "room_name": room.get("room_name", ""),
            "adults": room.get("adults", 1),
            "children": room.get("children", 0),
            "amount": room.get("amount", 0),
            "daily_rates": room.get("daily_rates", []),
            "guest_name": raw.get("guest_name", ""),
        })

    # Map Exely status to canonical
    exely_status = (raw.get("status") or "").lower()
    status_map = {
        "commit": "confirmed",
        "confirmed": "confirmed",
        "modify": "modified",
        "modified": "modified",
        "cancel": "cancelled",
        "cancelled": "cancelled",
        "pending": "pending",
    }
    canonical_status = status_map.get(exely_status, "pending")

    checkin = raw.get("checkin_date", "")
    checkout = raw.get("checkout_date", "")

    return {
        "external_id": raw.get("reservation_id", ""),
        "provider_reservation_id": raw.get("reservation_id", ""),
        "channel": raw.get("channel", "exely"),
        "channel_display": raw.get("channel", "Exely"),
        "provider_last_modified_at": raw.get("last_modify", ""),
        "provider_created_at": raw.get("create_date", ""),
        "provider_version": 1,
        "guest": {
            "name": raw.get("guest_name", ""),
            "first_name": raw.get("guest_firstname", ""),
            "last_name": raw.get("guest_lastname", ""),
            "email": raw.get("guest_email", ""),
            "phone": raw.get("guest_phone", ""),
            "country": raw.get("guest_country", ""),
            "address": {
                "line1": "",
                "city": raw.get("guest_city", ""),
                "zip": "",
                "country": raw.get("guest_country", ""),
            },
        },
        "stay": {
            "check_in": checkin,
            "check_out": checkout,
            "nights": _calc_nights(checkin, checkout),
        },
        "financial": {
            "total_amount": float(raw.get("total", 0)),
            "currency": raw.get("currency", "TRY"),
            "payment_method": raw.get("payment_method", ""),
            "commission": 0.0,
        },
        "rooms": room_details,
        "total_rooms": raw.get("total_rooms", len(rooms)),
        "total_guests": raw.get("total_guests", 1),
        "status": canonical_status,
        "notes": raw.get("notes", ""),
        "source_system": "EXELY",
        "ingested_via": source,
        "message_uid": raw.get("reservation_id", ""),
    }


def _calc_nights(checkin: str | None, checkout: str | None) -> int:
    if not checkin or not checkout:
        return 0
    try:
        ci = datetime.strptime(checkin[:10], "%Y-%m-%d")
        co = datetime.strptime(checkout[:10], "%Y-%m-%d")
        return max((co - ci).days, 0)
    except (ValueError, TypeError):
        return 0
