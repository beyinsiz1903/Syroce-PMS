"""
HotelRunner Provider — Data Mapper
====================================

Bidirectional mapping between HotelRunner models and canonical models.

Inbound:  HotelRunner reservation → canonical reservation dict
Outbound: PMS ARI delta → HotelRunner inventory payload
"""

import logging
from typing import Any

from .schemas import HotelRunnerReservation

logger = logging.getLogger("hotelrunner.mapper")

# ── Status mapping (HotelRunner → canonical) ──────────────────────────
_STATUS_MAP = {
    "reserved": "confirmed",
    "confirmed": "confirmed",
    "new": "confirmed",
    "modified": "modified",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "no_show": "cancelled",
}


def map_reservation_to_canonical(res: HotelRunnerReservation) -> dict[str, Any]:
    """
    Convert a parsed HotelRunnerReservation into the canonical format
    used by the reconciliation engine and ingest pipeline.
    """
    hr_status = res.status.lower() if res.status else "confirmed"
    canonical_status = _STATUS_MAP.get(hr_status, "confirmed")

    return {
        "external_reservation_id": res.hr_number or res.reservation_id,
        "provider": "hotelrunner",
        "guest_name": f"{res.guest_firstname} {res.guest_lastname}".strip(),
        "guest_email": res.guest_email,
        "guest_phone": res.guest_phone,
        "check_in": res.check_in,
        "check_out": res.check_out,
        "adults": res.adults,
        "children": res.children,
        "room_type_code": res.room_type_code,
        "rate_plan_code": res.rate_plan_code,
        "currency": res.currency,
        "total_amount": res.total_amount,
        "status": canonical_status,
        "provider_last_modified_at": res.last_modified,
        "source_system": res.channel,
        "source_payload_ref": res.hr_number or res.reservation_id,
        "message_uid": res.message_uid,
        "requires_response": res.requires_response,
    }


def map_raw_payload_to_canonical(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a raw HotelRunner reservation dict (directly from API)
    into the canonical format. Used when we have raw dicts rather than
    parsed HotelRunnerReservation objects.
    """
    guest = raw.get("guest", raw.get("address", {})) or {}
    rooms = raw.get("rooms", [])
    first_room = rooms[0] if rooms else {}

    first_name = str(raw.get("firstname", guest.get("first_name", "")))
    last_name = str(raw.get("lastname", guest.get("last_name", "")))

    hr_status = str(raw.get("state", raw.get("status", "confirmed"))).lower()
    canonical_status = _STATUS_MAP.get(hr_status, "confirmed")
    if raw.get("modified") and canonical_status != "cancelled":
        canonical_status = "modified"

    return {
        "external_reservation_id": str(raw.get("hr_number", raw.get("reservation_id", ""))),
        "provider": "hotelrunner",
        "guest_name": f"{first_name} {last_name}".strip(),
        "guest_email": str((raw.get("address") or {}).get("email", guest.get("email", ""))),
        "guest_phone": str((raw.get("address") or {}).get("phone", guest.get("phone", ""))),
        "check_in": str(raw.get("checkin_date", raw.get("check_in", ""))),
        "check_out": str(raw.get("checkout_date", raw.get("check_out", ""))),
        "adults": int(first_room.get("total_adult", raw.get("adults", 1)) or 1),
        "children": len(first_room.get("child_ages", [])) or int(raw.get("children", 0)),
        "room_type_code": str(first_room.get("inv_code", raw.get("room_type", ""))),
        "rate_plan_code": str(first_room.get("rate_plan_code", raw.get("rate_plan", ""))),
        "currency": str(raw.get("currency", "TRY")),
        "total_amount": float(raw.get("total", 0) or 0),
        "status": canonical_status,
        "provider_last_modified_at": str(raw.get("updated_at", raw.get("last_modified", ""))),
        "source_system": str(raw.get("channel_display", raw.get("channel", ""))),
        "source_payload_ref": str(raw.get("hr_number", raw.get("reservation_id", ""))),
        "message_uid": str(raw.get("message_uid", "")),
    }


# ── Outbound Mapping: ARI Push ────────────────────────────────────────


def map_ari_delta_to_daily_payload(
    delta: dict[str, Any],
    room_mapping: dict[str, Any],
) -> dict[str, str]:
    """
    Convert a PMS ARI delta to HotelRunner daily inventory form data.
    Returns a dict suitable for PUT /rooms/daily form-encoded payload.
    """
    inv_code = room_mapping.get("external_code", "")
    data: dict[str, str] = {
        "inv_code": inv_code,
        "date": str(delta.get("date", "")),
    }
    if "availability" in delta:
        data["availability"] = str(delta["availability"])
    if "price" in delta:
        data["price"] = str(delta["price"])
    if "stop_sale" in delta:
        data["stop_sale"] = str(delta["stop_sale"])
    if "min_stay" in delta:
        data["min_stay"] = str(delta["min_stay"])
    if "cta" in delta:
        data["cta"] = str(delta["cta"])
    if "ctd" in delta:
        data["ctd"] = str(delta["ctd"])
    return data


def map_ari_delta_to_daterange_payload(
    delta: dict[str, Any],
    room_mapping: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert a PMS ARI delta to HotelRunner date range inventory form data.
    Returns a dict suitable for PUT /rooms/~ form-encoded payload.
    """
    inv_code = room_mapping.get("external_code", "")
    data: dict[str, Any] = {
        "inv_code": inv_code,
        "start_date": str(delta.get("start_date", delta.get("date_from", ""))),
        "end_date": str(delta.get("end_date", delta.get("date_to", ""))),
    }
    if "availability" in delta:
        data["availability"] = str(delta["availability"])
    if "price" in delta:
        data["price"] = str(delta["price"])
    if "stop_sale" in delta:
        data["stop_sale"] = str(delta["stop_sale"])
    if "min_stay" in delta:
        data["min_stay"] = str(delta["min_stay"])
    if "cta" in delta:
        data["cta"] = str(delta["cta"])
    if "ctd" in delta:
        data["ctd"] = str(delta["ctd"])
    if "days" in delta:
        data["days[]"] = [str(d) for d in delta["days"]]
    if "channel_codes" in delta:
        data["channel_codes[]"] = delta["channel_codes"]
    return data
