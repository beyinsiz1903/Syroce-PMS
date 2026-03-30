"""
HotelRunner v2 — Mapper (Bi-directional)
==========================================

HotelRunner REST payload ↔ Canonical data model.

Inbound:  raw HR reservation → CanonicalReservation dict
Outbound: ARI delta → HR push payload

No side effects. Pure transformations. Fully testable.
"""
import hashlib
import json
from typing import Any


def _s(v: Any) -> str:
    return str(v) if v is not None else ""


# ── Status mapping ──────────────────────────────────────────────────

HR_STATUS_TO_CANONICAL = {
    "confirmed": "confirmed",
    "reserved": "confirmed",
    "new": "confirmed",
    "modified": "modified",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "no_show": "cancelled",
    "pending": "pending",
}

CANONICAL_STATUS_TO_EVENT = {
    "confirmed": "new",
    "modified": "modification",
    "cancelled": "cancellation",
    "pending": "new",
}


# ══════════════════════════════════════════════════════════════════════
# INBOUND: HR reservation → canonical dict
# ══════════════════════════════════════════════════════════════════════

def reservation_to_canonical(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Convert HotelRunner REST reservation JSON to canonical format.

    Handles both real HR API structure and simplified test payloads.
    """
    guest_raw = raw.get("guest", {})
    guest = guest_raw if isinstance(guest_raw, dict) else {}
    address = raw.get("address", {}) or {}
    rooms = raw.get("rooms", []) or []
    first_room = rooms[0] if rooms and isinstance(rooms[0], dict) else {}

    # Name
    first = _s(raw.get("firstname") or guest.get("first_name") or guest.get("firstname", ""))
    last = _s(raw.get("lastname") or guest.get("last_name") or guest.get("lastname", ""))
    if not first and not last and isinstance(guest_raw, str):
        parts = guest_raw.strip().split(" ", 1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else ""

    # Contact
    email = _s(address.get("email") or guest.get("email", ""))
    phone = _s(address.get("phone") or guest.get("phone", ""))

    # Dates
    check_in = _s(raw.get("checkin_date") or raw.get("check_in", ""))
    check_out = _s(raw.get("checkout_date") or raw.get("check_out", ""))

    # Room / rate
    room_type = _s(first_room.get("room_code") or first_room.get("inv_code") or raw.get("room_type", ""))
    rate_plan = _s(first_room.get("rate_code") or first_room.get("rate_plan_code") or raw.get("rate_plan", ""))

    # Occupancy
    adults = int(first_room.get("adults") or raw.get("adults", 1) or 1)
    children = int(first_room.get("children") or raw.get("children", 0) or 0)

    # Status
    hr_status = _s(raw.get("state") or raw.get("status", "confirmed")).lower()
    status = HR_STATUS_TO_CANONICAL.get(hr_status, "confirmed")

    # Modified flag override
    if raw.get("modified") and status == "confirmed":
        status = "modified"

    # Last modified
    last_mod = _s(raw.get("updated_at") or raw.get("modified_at") or raw.get("last_modified", ""))

    return {
        "external_reservation_id": _s(raw.get("hr_number", "")),
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
        "currency": _s(raw.get("currency", "TRY")),
        "total_amount": float(raw.get("total", 0.0) or 0.0),
        "status": status,
        "provider_last_modified_at": last_mod,
        "source_system": _s(raw.get("channel") or raw.get("channel_display", "")),
        "source_payload_ref": _s(raw.get("hr_number", "")),
        "message_uid": _s(raw.get("message_uid", "")),
    }


def extract_identity(raw: dict[str, Any]) -> dict[str, str]:
    """Extract identity fields for dedup / event tracking."""
    hr_number = _s(raw.get("hr_number", ""))
    event_type = _s(raw.get("event_type", "reservation_create"))
    last_modified = _s(raw.get("updated_at") or raw.get("modified_at") or raw.get("last_modified", ""))
    return {
        "external_reservation_id": hr_number,
        "provider_event_id": f"{hr_number}_{event_type}_{last_modified}",
        "provider_version": last_modified,
    }


def compute_idempotency_key(external_id: str, updated_at: str) -> str:
    """Idempotency key = hash(external_id + updated_at)."""
    raw = f"{external_id}:{updated_at}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def compute_payload_hash(canonical: dict[str, Any]) -> str:
    """Hash of canonical fields for change detection."""
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


def detect_event_type(canonical: dict[str, Any]) -> str:
    """Classify incoming reservation event type."""
    status = canonical.get("status", "confirmed")
    return CANONICAL_STATUS_TO_EVENT.get(status, "new")


# ══════════════════════════════════════════════════════════════════════
# OUTBOUND: ARI delta → HR push payload
# ══════════════════════════════════════════════════════════════════════

def ari_to_daily_payload(
    room_code: str,
    date: str,
    *,
    availability: int | None = None,
    price: float | None = None,
    stop_sale: bool | None = None,
    min_stay: int | None = None,
    max_stay: int | None = None,
    cta: bool | None = None,
    ctd: bool | None = None,
) -> dict[str, Any]:
    """Build daily ARI push payload for HR /rooms/daily."""
    payload: dict[str, Any] = {
        "inv_code": room_code,
        "date": date,
    }
    if availability is not None:
        payload["availability"] = str(availability)
    if price is not None:
        payload["price"] = str(price)
    if stop_sale is not None:
        payload["stop_sale"] = "1" if stop_sale else "0"
    if min_stay is not None:
        payload["min_stay"] = str(min_stay)
    if max_stay is not None:
        payload["max_stay"] = str(max_stay)
    if cta is not None:
        payload["cta"] = "1" if cta else "0"
    if ctd is not None:
        payload["ctd"] = "1" if ctd else "0"
    return payload


def ari_to_daterange_payload(
    room_code: str,
    start_date: str,
    end_date: str,
    *,
    availability: int | None = None,
    price: float | None = None,
    stop_sale: bool | None = None,
    min_stay: int | None = None,
    max_stay: int | None = None,
    cta: bool | None = None,
    ctd: bool | None = None,
) -> dict[str, Any]:
    """Build date-range ARI push payload for HR /rooms/~."""
    payload: dict[str, Any] = {
        "inv_code": room_code,
        "start_date": start_date,
        "end_date": end_date,
    }
    if availability is not None:
        payload["availability"] = str(availability)
    if price is not None:
        payload["price"] = str(price)
    if stop_sale is not None:
        payload["stop_sale"] = "1" if stop_sale else "0"
    if min_stay is not None:
        payload["min_stay"] = str(min_stay)
    if max_stay is not None:
        payload["max_stay"] = str(max_stay)
    if cta is not None:
        payload["cta"] = "1" if cta else "0"
    if ctd is not None:
        payload["ctd"] = "1" if ctd else "0"
    return payload
