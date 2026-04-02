"""
Reservation Ingest — Provider Normalizers
==========================================

Convert HotelRunner / Exely payloads into canonical reservation format.
"""
import hashlib
import json
from typing import Any


def _safe_str(v: Any) -> str:
    return str(v) if v is not None else ""


# ══════════════════════════════════════════════════════════════════════
# Canonical Reservation Schema
# ══════════════════════════════════════════════════════════════════════

def empty_canonical() -> dict[str, Any]:
    return {
        "external_reservation_id": "",
        "provider": "",
        "guest_name": "",
        "guest_email": "",
        "guest_phone": "",
        "check_in": "",
        "check_out": "",
        "adults": 1,
        "children": 0,
        "room_type_code": "",
        "rate_plan_code": "",
        "currency": "TRY",
        "total_amount": 0.0,
        "status": "confirmed",
        "provider_last_modified_at": "",
        "source_system": "",
        "source_payload_ref": "",
    }


# ══════════════════════════════════════════════════════════════════════
# HotelRunner Normalizer
# ══════════════════════════════════════════════════════════════════════

def normalize_hotelrunner(payload: dict[str, Any]) -> dict[str, Any]:
    """
    HotelRunner reservation payload → canonical format.

    Handles both the actual HotelRunner API format and simplified format:
    - API format: firstname/lastname, checkin_date, address.email, rooms[].room_code, state
    - Simplified: guest.first_name, check_in, guest.email, room_type
    """
    # Guest info: handle string, dict, or address-based formats
    guest_raw = payload.get("guest", {})
    guest = guest_raw if isinstance(guest_raw, dict) else {}
    address = payload.get("address", {}) or {}
    rooms = payload.get("rooms", []) or []
    first_room = rooms[0] if rooms and isinstance(rooms[0], dict) else {}

    # Name: try multiple field patterns
    first = _safe_str(
        payload.get("firstname")
        or guest.get("first_name")
        or guest.get("firstname", "")
    )
    last = _safe_str(
        payload.get("lastname")
        or guest.get("last_name")
        or guest.get("lastname", "")
    )
    # Fallback: if guest is a string, use it as full name
    if not first and not last and isinstance(guest_raw, str):
        parts = guest_raw.strip().split(" ", 1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else ""

    # Email/phone: address > guest dict
    email = _safe_str(address.get("email") or guest.get("email", ""))
    phone = _safe_str(address.get("phone") or guest.get("phone", ""))

    # Dates: checkin_date > check_in
    check_in = _safe_str(payload.get("checkin_date") or payload.get("check_in", ""))
    check_out = _safe_str(payload.get("checkout_date") or payload.get("check_out", ""))

    # Room/rate: from rooms array or direct fields
    room_type = _safe_str(
        first_room.get("inv_code")
        or first_room.get("room_code")
        or payload.get("room_type", "")
    )
    rate_plan = _safe_str(
        first_room.get("rate_code")
        or first_room.get("rate_plan_code")
        or payload.get("rate_plan", "")
    )

    # Occupancy: from first room or direct fields
    adults = int(first_room.get("total_adult") or first_room.get("adults") or payload.get("adults", 1) or 1)
    children = len(first_room.get("child_ages", [])) or int(first_room.get("children") or payload.get("children", 0) or 0)

    # Total: prefer room-level price for exploded sub-reservations, then reservation total
    room_price = float(first_room.get("price", 0) or 0)
    reservation_total = float(payload.get("total", 0.0) or 0.0)
    # If this payload was exploded from a multi-room reservation (has _exploded_from),
    # use the per-room price. Otherwise use the reservation total.
    if payload.get("_exploded_from") and room_price > 0:
        total_amount = room_price
    elif room_price > 0 and len(rooms) == 1:
        # Single room after explosion — use room price
        total_amount = room_price
    else:
        total_amount = reservation_total

    # Status: state > status
    hr_status = _safe_str(payload.get("state") or payload.get("status", "confirmed")).lower()
    status_map = {
        "confirmed": "confirmed",
        "new": "confirmed",
        "modified": "modified",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "no_show": "cancelled",
        "pending": "pending",
    }
    canonical_status = status_map.get(hr_status, "confirmed")

    # Last modified
    last_mod = _safe_str(
        payload.get("updated_at")
        or payload.get("modified_at")
        or payload.get("last_modified", "")
    )

    return {
        "external_reservation_id": _safe_str(payload.get("hr_number", "")),
        "provider": "hotelrunner",
        "guest_name": f"{first} {last}".strip(),
        "guest_email": email,
        "guest_phone": phone,
        "check_in": check_in,
        "check_out": check_out,
        "adults": adults,
        "children": children,
        "room_type_code": room_type,
        "rate_plan_code": rate_plan,
        "currency": _safe_str(payload.get("currency", "TRY")),
        "total_amount": total_amount,
        "status": canonical_status,
        "provider_last_modified_at": last_mod,
        "source_system": _safe_str(payload.get("channel") or payload.get("channel_display", "")),
        "source_payload_ref": _safe_str(payload.get("hr_number", "")),
    }


def extract_hotelrunner_identity(payload: dict[str, Any]) -> dict[str, str]:
    """Extract HotelRunner identity fields for raw event."""
    hr_number = _safe_str(payload.get("hr_number", ""))
    event_type = _safe_str(payload.get("event_type", "reservation_create"))
    last_modified = _safe_str(
        payload.get("updated_at")
        or payload.get("modified_at")
        or payload.get("last_modified", "")
    )
    return {
        "external_reservation_id": hr_number,
        "provider_event_id": f"{hr_number}_{event_type}_{last_modified}",
        "provider_version": last_modified,
        "provider_last_modified_at": last_modified,
    }


# ══════════════════════════════════════════════════════════════════════
# Exely Normalizer
# ══════════════════════════════════════════════════════════════════════

def normalize_exely(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Exely (OTA_ReadRQ) reservation payload → canonical format.

    Exely SOAP parsed to dict typically looks like:
    {
      "UniqueID": "EX-67890",
      "ResStatus": "Commit",
      "LastModifyDateTime": "2026-03-13T10:30:00Z",
      "RoomStay": {
        "RoomTypeCode": "DLX",
        "RatePlanCode": "RACK",
        "StartDate": "2026-04-12",
        "EndDate": "2026-04-16"
      },
      "GuestCount": {"adults": 2, "children": 0},
      "ResGuest": {"GivenName": "...", "Surname": "...", "Email": "...", "Phone": "..."},
      "Total": {"Amount": 7200.00, "CurrencyCode": "TRY"},
      "Source": "expedia"
    }
    """
    guest = payload.get("ResGuest", {})
    room = payload.get("RoomStay", {})
    guests = payload.get("GuestCount", {})
    total_obj = payload.get("Total", {})

    # Exely status mapping
    res_status = _safe_str(payload.get("ResStatus", "Commit")).lower()
    status_map = {
        "commit": "confirmed",
        "modify": "modified",
        "cancel": "cancelled",
        "book": "confirmed",
    }
    canonical_status = status_map.get(res_status, "confirmed")

    given = _safe_str(guest.get("GivenName", ""))
    surname = _safe_str(guest.get("Surname", ""))

    return {
        "external_reservation_id": _safe_str(payload.get("UniqueID", "")),
        "provider": "exely",
        "guest_name": f"{given} {surname}".strip(),
        "guest_email": _safe_str(guest.get("Email", "")),
        "guest_phone": _safe_str(guest.get("Phone", "")),
        "check_in": _safe_str(room.get("StartDate", "")),
        "check_out": _safe_str(room.get("EndDate", "")),
        "adults": int(guests.get("adults", 1)),
        "children": int(guests.get("children", 0)),
        "room_type_code": _safe_str(room.get("RoomTypeCode", "")),
        "rate_plan_code": _safe_str(room.get("RatePlanCode", "")),
        "currency": _safe_str(total_obj.get("CurrencyCode", "TRY")),
        "total_amount": float(total_obj.get("Amount", 0.0)),
        "status": canonical_status,
        "provider_last_modified_at": _safe_str(payload.get("LastModifyDateTime", "")),
        "source_system": _safe_str(payload.get("Source", "")),
        "source_payload_ref": _safe_str(payload.get("UniqueID", "")),
    }


def extract_exely_identity(payload: dict[str, Any]) -> dict[str, str]:
    """Extract Exely identity fields for raw event."""
    unique_id = _safe_str(payload.get("UniqueID", ""))
    res_status = _safe_str(payload.get("ResStatus", ""))
    last_modified = _safe_str(payload.get("LastModifyDateTime", ""))
    return {
        "external_reservation_id": unique_id,
        "provider_event_id": f"{unique_id}_{res_status}_{last_modified}",
        "provider_version": last_modified,
        "provider_last_modified_at": last_modified,
    }


# ══════════════════════════════════════════════════════════════════════
# Dispatcher
# ══════════════════════════════════════════════════════════════════════

NORMALIZERS = {
    "hotelrunner": normalize_hotelrunner,
    "exely": normalize_exely,
}

IDENTITY_EXTRACTORS = {
    "hotelrunner": extract_hotelrunner_identity,
    "exely": extract_exely_identity,
}


def normalize(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    fn = NORMALIZERS.get(provider)
    if not fn:
        raise ValueError(f"No normalizer for provider: {provider}")
    return fn(payload)


def extract_identity(provider: str, payload: dict[str, Any]) -> dict[str, str]:
    fn = IDENTITY_EXTRACTORS.get(provider)
    if not fn:
        raise ValueError(f"No identity extractor for provider: {provider}")
    return fn(payload)


def compute_canonical_hash(canonical: dict[str, Any]) -> str:
    """Hash of canonical reservation data for change detection."""
    key_fields = {
        "check_in": canonical.get("check_in", ""),
        "check_out": canonical.get("check_out", ""),
        "room_type_code": canonical.get("room_type_code", ""),
        "rate_plan_code": canonical.get("rate_plan_code", ""),
        "adults": canonical.get("adults", 1),
        "children": canonical.get("children", 0),
        "total_amount": canonical.get("total_amount", 0.0),
        "status": canonical.get("status", ""),
        "guest_email": canonical.get("guest_email", ""),
    }
    raw = json.dumps(key_fields, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
