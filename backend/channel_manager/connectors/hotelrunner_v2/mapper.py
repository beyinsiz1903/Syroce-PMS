"""
HotelRunner v2 — Mapper (Bi-directional)
==========================================

HotelRunner REST payload <-> Canonical data model.
Based on official docs: https://developers.hotelrunner.com/custom-apps/rest-api

Inbound:  raw HR reservation → CanonicalReservation dict
Outbound: ARI delta → HR push payload

No side effects. Pure transformations. Fully testable.
"""

import hashlib
import json
from typing import Any


def _s(v: Any) -> str:
    return str(v) if v is not None else ""


def _f(v: Any) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def _i(v: Any) -> int:
    try:
        return int(v) if v is not None else 0
    except (ValueError, TypeError):
        return 0


# ── Status mapping ──────────────────────────────────────────────────

HR_STATUS_TO_CANONICAL = {
    "reserved": "confirmed",
    "confirmed": "confirmed",
    "canceled": "cancelled",
    "cancelled": "cancelled",
    "no_show": "cancelled",
}

CANONICAL_STATUS_TO_EVENT = {
    "confirmed": "new",
    "modified": "modification",
    "cancelled": "cancellation",
}


# ══════════════════════════════════════════════════════════════════════
# INBOUND: HR reservation → canonical dict
# ══════════════════════════════════════════════════════════════════════


def reservation_to_canonical(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Convert HotelRunner REST reservation JSON to canonical format.
    Handles the full HR API response structure from:
    GET /api/v2/apps/reservations

    Key HR fields: hr_number, firstname, lastname, guest, address,
    rooms[].inv_code, rooms[].rate_plan_code, rooms[].daily_prices, etc.
    """
    # ── Guest Info ────────────────────────────────────────────────
    first = _s(raw.get("firstname", ""))
    last = _s(raw.get("lastname", ""))

    # Fallback: guest field (can be string "John Doe" or dict)
    guest_raw = raw.get("guest", "")
    if not first and not last:
        if isinstance(guest_raw, dict):
            first = _s(guest_raw.get("first_name") or guest_raw.get("firstname", ""))
            last = _s(guest_raw.get("last_name") or guest_raw.get("lastname", ""))
        elif isinstance(guest_raw, str) and guest_raw.strip():
            parts = guest_raw.strip().split(" ", 1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else ""

    # ── Contact Info ──────────────────────────────────────────────
    address = raw.get("address") or {}
    if not isinstance(address, dict):
        address = {}
    email = _s(address.get("email", ""))
    phone = _s(address.get("phone", ""))
    country = _s(raw.get("country") or address.get("country_code", ""))

    # ── Dates ─────────────────────────────────────────────────────
    check_in = _s(raw.get("checkin_date") or raw.get("check_in", ""))
    check_out = _s(raw.get("checkout_date") or raw.get("check_out", ""))

    # ── Rooms (first room primary — multi-room in rooms_detail) ──
    rooms = raw.get("rooms") or []
    first_room = rooms[0] if rooms and isinstance(rooms[0], dict) else {}

    room_type_code = _s(first_room.get("inv_code") or first_room.get("code") or first_room.get("room_code") or raw.get("room_type", ""))
    rate_plan_code = _s(first_room.get("rate_plan_code") or first_room.get("rate_code") or raw.get("rate_plan", ""))

    # Occupancy
    adults = _i(first_room.get("total_adult") or raw.get("adults", 1)) or 1
    total_guests = _i(first_room.get("total_guest") or raw.get("total_guests", adults))
    child_ages = first_room.get("child_ages") or []
    children = len(child_ages) if child_ages else max(0, total_guests - adults)

    # Room details
    nights = _i(first_room.get("nights", 0))
    meal_plan = _s(first_room.get("meal_plan", ""))
    non_refundable = bool(first_room.get("non_refundable", False))

    # ── Status ────────────────────────────────────────────────────
    hr_status = _s(raw.get("state") or raw.get("status", "reserved")).lower()
    status = HR_STATUS_TO_CANONICAL.get(hr_status, "confirmed")

    # Modified flag override (HR sets modified=true on updates)
    if raw.get("modified") and status == "confirmed":
        status = "modified"

    # ── Financial ─────────────────────────────────────────────────
    total = _f(raw.get("total", 0.0))
    sub_total = _f(raw.get("sub_total", 0.0))
    tax_total = _f(raw.get("tax_total", 0.0))
    currency = _s(raw.get("currency", "TRY"))
    paid_amount = _f(raw.get("paid_amount", 0.0))
    payment_method = _s(raw.get("payment", ""))

    # ── Timestamps ────────────────────────────────────────────────
    completed_at = _s(raw.get("completed_at", ""))
    updated_at = _s(raw.get("updated_at") or raw.get("modified_at") or raw.get("last_modified", ""))

    # ── Channel / Source ──────────────────────────────────────────
    channel = _s(raw.get("channel", ""))
    channel_display = _s(raw.get("channel_display", ""))
    provider_number = _s(raw.get("provider_number", ""))
    hr_number = _s(raw.get("hr_number", ""))

    # ── Daily prices extraction ───────────────────────────────────
    daily_prices = []
    for dp in first_room.get("daily_prices") or []:
        if isinstance(dp, dict):
            daily_prices.append(
                {
                    "date": _s(dp.get("date", "")),
                    "price": _f(dp.get("price", 0)),
                    "original_price": _f(dp.get("original_price", 0)),
                    "discount": _f(dp.get("discount", 0)),
                }
            )

    # ── Rooms detail (multi-room support) ─────────────────────────
    rooms_detail = []
    for r in rooms:
        if not isinstance(r, dict):
            continue
        rooms_detail.append(
            {
                "room_id": _i(r.get("id", 0)),
                "inv_code": _s(r.get("inv_code", "")),
                "rate_code": _s(r.get("rate_code", "")),
                "rate_plan_code": _s(r.get("rate_plan_code", "")),
                "name": _s(r.get("name", "")),
                "state": _s(r.get("state", "")),
                "adults": _i(r.get("total_adult", 1)),
                "total_guest": _i(r.get("total_guest", 1)),
                "child_ages": r.get("child_ages") or [],
                "nights": _i(r.get("nights", 0)),
                "meal_plan": _s(r.get("meal_plan", "")),
                "price": _f(r.get("price", 0)),
                "total": _f(r.get("total", 0)),
                "non_refundable": bool(r.get("non_refundable", False)),
                "checkin_date": _s(r.get("checkin_date", "")),
                "checkout_date": _s(r.get("checkout_date", "")),
            }
        )

    # ── Payments ──────────────────────────────────────────────────
    payments_detail = []
    for p in raw.get("payments") or []:
        if not isinstance(p, dict):
            continue
        payments_detail.append(
            {
                "id": _i(p.get("id", 0)),
                "state": _s(p.get("state", "")),
                "amount": _f(p.get("amount", 0)),
                "currency": _s(p.get("currency", "")),
                "payment_method": _s(p.get("payment_method", "")),
                "paid_at": _s(p.get("paid_at", "")),
            }
        )

    return {
        "external_reservation_id": hr_number,
        "provider": "hotelrunner",
        "provider_reservation_id": _i(raw.get("reservation_id", 0)),
        "provider_number": provider_number,
        "guest_name": f"{first} {last}".strip(),
        "guest_first_name": first,
        "guest_last_name": last,
        "guest_email": email,
        "guest_phone": phone,
        "guest_country": country,
        "check_in": check_in,
        "check_out": check_out,
        "nights": nights,
        "adults": adults,
        "children": children,
        "child_ages": child_ages,
        "total_rooms": _i(raw.get("total_rooms", 1)),
        "room_type_code": room_type_code,
        "rate_plan_code": rate_plan_code,
        "meal_plan": meal_plan,
        "non_refundable": non_refundable,
        "currency": currency,
        "sub_total": sub_total,
        "tax_total": tax_total,
        "total_amount": total,
        "paid_amount": paid_amount,
        "payment_method": payment_method,
        "status": status,
        "provider_last_modified_at": updated_at,
        "completed_at": completed_at,
        "source_system": channel_display or channel,
        "channel_code": channel,
        "source_payload_ref": hr_number,
        "message_uid": _s(raw.get("message_uid", "")),
        "cancel_reason": _s(raw.get("cancel_reason", "")),
        "note": _s(raw.get("note", "")),
        "requires_response": bool(raw.get("requires_response", False)),
        "daily_prices": daily_prices,
        "rooms_detail": rooms_detail,
        "payments_detail": payments_detail,
    }


def extract_identity(raw: dict[str, Any]) -> dict[str, str]:
    """Extract identity fields for dedup / event tracking."""
    hr_number = _s(raw.get("hr_number", ""))
    updated_at = _s(raw.get("updated_at") or raw.get("modified_at") or raw.get("last_modified", ""))
    state = _s(raw.get("state", "reserved"))
    modified = raw.get("modified", False)

    event_type = "reservation_create"
    if state == "canceled":
        event_type = "reservation_cancel"
    elif modified:
        event_type = "reservation_modify"

    return {
        "external_reservation_id": hr_number,
        "provider_event_id": f"{hr_number}_{event_type}_{updated_at}",
        "provider_version": updated_at,
        "event_type": event_type,
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


def ari_to_update_payload(
    inv_code: str,
    start_date: str,
    end_date: str,
    *,
    availability: int | None = None,
    price: float | None = None,
    stop_sale: bool | None = None,
    min_stay: int | None = None,
    cta: bool | None = None,
    ctd: bool | None = None,
    days: list[int] | None = None,
    channel_codes: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build ARI push payload for PUT /api/v2/apps/rooms/~

    From HR docs:
    - inv_code: required (update by inv_code, NOT rate_code)
    - start_date, end_date: required (YYYY-MM-DD)
    - availability, price, stop_sale, cta, ctd, min_stay: optional
    - days: optional array [0-6] for specific weekdays (Sunday=0)
    - channel_codes: optional array to target specific channels
    """
    payload: dict[str, Any] = {
        "inv_code": inv_code,
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
    if cta is not None:
        payload["cta"] = "1" if cta else "0"
    if ctd is not None:
        payload["ctd"] = "1" if ctd else "0"
    if days is not None:
        payload["days[]"] = [str(d) for d in days]
    if channel_codes is not None:
        payload["channel_codes[]"] = channel_codes
    return payload


# Legacy aliases for backward compat with tests
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
    return ari_to_update_payload(
        room_code,
        start_date,
        end_date,
        availability=availability,
        price=price,
        stop_sale=stop_sale,
        min_stay=min_stay,
        cta=cta,
        ctd=ctd,
    )


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
    return ari_to_update_payload(
        room_code,
        date,
        date,
        availability=availability,
        price=price,
        stop_sale=stop_sale,
        min_stay=min_stay,
        cta=cta,
        ctd=ctd,
    )
