"""
HotelRunner Reservation Ingest Pipeline
Enterprise-grade reservation processing: Raw Store → Idempotency → Normalize → Decision → PMS Import

Architecture:
  Webhook/Pull → Raw Event Store → Ingest Queue → Idempotency Guard →
  Schema Normalizer → Decision Engine → PMS ReservationService →
  Folio/Allocation/Availability → Audit Log
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Literal

from core.database import db

logger = logging.getLogger(__name__)


# ── Canonical Reservation Model ──────────────────────────────────────

def normalize_reservation(raw: Dict[str, Any], source: str = "webhook") -> Dict[str, Any]:
    """
    Convert HotelRunner reservation payload to canonical PMS format.
    PMS should never see HotelRunner-specific field names.
    """
    address = raw.get("address", {}) or {}
    rooms = raw.get("rooms", []) or []

    room_details = []
    for room in rooms:
        room_details.append({
            "room_type_code": room.get("room_code", ""),
            "rate_plan_code": room.get("rate_code", ""),
            "room_name": room.get("room_name", ""),
            "adults": room.get("adults", 1),
            "children": room.get("children", 0),
            "amount": room.get("total"),
            "daily_rates": room.get("daily_rates", []),
            "guest_name": room.get("guest", ""),
        })

    # Map HotelRunner status to canonical status
    hr_state = (raw.get("state") or "").lower()
    status_map = {
        "confirmed": "confirmed",
        "modified": "modified",
        "canceled": "cancelled",
        "cancelled": "cancelled",
        "no_show": "no_show",
        "pending": "pending",
    }
    canonical_status = status_map.get(hr_state, "pending")

    return {
        "external_id": raw.get("hr_number", ""),
        "provider_reservation_id": raw.get("reservation_id", ""),
        "channel": raw.get("channel", "direct"),
        "channel_display": raw.get("channel_display", raw.get("channel", "")),
        "guest": {
            "name": raw.get("guest", f"{raw.get('firstname', '')} {raw.get('lastname', '')}".strip()),
            "first_name": raw.get("firstname", ""),
            "last_name": raw.get("lastname", ""),
            "email": address.get("email", ""),
            "phone": address.get("phone", ""),
            "country": raw.get("country", ""),
            "address": {
                "line1": address.get("address_line", ""),
                "city": address.get("city", ""),
                "zip": address.get("zipcode", ""),
                "country": address.get("country_code", ""),
            },
        },
        "stay": {
            "check_in": raw.get("checkin_date", ""),
            "check_out": raw.get("checkout_date", ""),
            "nights": _calc_nights(raw.get("checkin_date"), raw.get("checkout_date")),
        },
        "financial": {
            "total_amount": _parse_float(raw.get("total")),
            "currency": raw.get("currency", "TRY"),
            "payment_method": raw.get("payment", ""),
            "commission": _parse_float(raw.get("commission")),
        },
        "rooms": room_details,
        "total_rooms": raw.get("total_rooms", len(rooms)),
        "total_guests": raw.get("total_guests", 1),
        "status": canonical_status,
        "notes": raw.get("note", ""),
        "source_system": "HOTELRUNNER",
        "ingested_via": source,
        "message_uid": raw.get("message_uid", ""),
    }


def _calc_nights(checkin: Optional[str], checkout: Optional[str]) -> int:
    if not checkin or not checkout:
        return 0
    try:
        ci = datetime.strptime(checkin[:10], "%Y-%m-%d")
        co = datetime.strptime(checkout[:10], "%Y-%m-%d")
        return max((co - ci).days, 0)
    except (ValueError, TypeError):
        return 0


def _parse_float(val) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


# ── Raw Event Store ──────────────────────────────────────────────────

async def store_raw_event(
    tenant_id: str,
    event_type: str,
    hr_number: str,
    channel: str,
    payload: Dict[str, Any],
    source: str = "webhook",
) -> str:
    """Store raw event for replay, audit, and debugging."""
    event_id = str(uuid.uuid4())
    await db.hotelrunner_raw_events.insert_one({
        "id": event_id,
        "tenant_id": tenant_id,
        "provider": "hotelrunner",
        "event_type": event_type,
        "hr_number": hr_number,
        "channel": channel,
        "source": source,
        "payload": payload,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "processed_at": None,
        "status": "pending",
        "error_message": None,
        "retry_count": 0,
    })
    return event_id


async def mark_event_processed(event_id: str, status: str = "processed", error: Optional[str] = None):
    await db.hotelrunner_raw_events.update_one(
        {"id": event_id},
        {"$set": {
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "error_message": error,
        }},
    )


# ── Idempotency Guard ────────────────────────────────────────────────

async def check_idempotency(tenant_id: str, hr_number: str, channel: str, event_type: str) -> Dict[str, Any]:
    """
    Two-layer idempotency:
    1. Reservation identity: provider + hr_number + channel
    2. Event identity: same event_type for same reservation = skip if unchanged
    """
    existing = await db.hotelrunner_reservations.find_one(
        {"tenant_id": tenant_id, "hr_number": hr_number},
        {"_id": 0, "state": 1, "synced_at": 1, "pms_status": 1, "delivery_confirmed": 1},
    )

    if not existing:
        return {"action": "create", "existing": None}

    if event_type == "cancellation":
        if existing.get("state") == "cancelled":
            return {"action": "skip", "reason": "already_cancelled", "existing": existing}
        return {"action": "cancel", "existing": existing}

    if event_type == "modification":
        return {"action": "update", "existing": existing}

    if event_type in ("new", "reservation"):
        if existing.get("pms_status") in ("imported", "confirmed"):
            return {"action": "skip", "reason": "already_imported", "existing": existing}
        return {"action": "update", "existing": existing}

    return {"action": "update", "existing": existing}


# ── Reservation Decision Engine ──────────────────────────────────────

async def process_reservation(
    tenant_id: str,
    canonical: Dict[str, Any],
    event_type: str,
    event_id: str,
) -> Dict[str, Any]:
    """
    Decision engine: create / update / cancel / skip / pending_mapping
    """
    hr_number = canonical["external_id"]
    channel = canonical["channel"]

    # 1. Idempotency check
    idem = await check_idempotency(tenant_id, hr_number, channel, event_type)
    action = idem["action"]

    if action == "skip":
        await mark_event_processed(event_id, "skipped", idem.get("reason"))
        logger.info(f"[INGEST] Skip {hr_number}: {idem.get('reason')}")
        return {"action": "skip", "reason": idem.get("reason"), "hr_number": hr_number}

    # 2. Mapping check - do we have room mappings?
    has_mapping = await _check_room_mapping(tenant_id, canonical["rooms"])

    # 3. Build reservation document
    now = datetime.now(timezone.utc).isoformat()
    res_doc = {
        "tenant_id": tenant_id,
        "hr_number": hr_number,
        "hr_reservation_id": canonical["provider_reservation_id"],
        "channel": channel,
        "channel_display": canonical["channel_display"],
        "state": canonical["status"],
        "guest_name": canonical["guest"]["name"],
        "guest_firstname": canonical["guest"]["first_name"],
        "guest_lastname": canonical["guest"]["last_name"],
        "guest_email": canonical["guest"]["email"],
        "guest_phone": canonical["guest"]["phone"],
        "guest_country": canonical["guest"]["country"],
        "checkin_date": canonical["stay"]["check_in"],
        "checkout_date": canonical["stay"]["check_out"],
        "nights": canonical["stay"]["nights"],
        "total": canonical["financial"]["total_amount"],
        "currency": canonical["financial"]["currency"],
        "payment_method": canonical["financial"]["payment_method"],
        "total_rooms": canonical["total_rooms"],
        "total_guests": canonical["total_guests"],
        "rooms": canonical["rooms"],
        "note": canonical["notes"],
        "message_uid": canonical["message_uid"],
        "source_system": "HOTELRUNNER",
        "ingested_via": canonical["ingested_via"],
        "external_write_protected": True,
        "synced_at": now,
        "raw_event_id": event_id,
    }

    # 4. Execute decision
    if action == "create":
        res_doc["id"] = str(uuid.uuid4())
        res_doc["created_at"] = now
        res_doc["pms_status"] = "pending_mapping" if not has_mapping else "pending"
        res_doc["pms_booking_id"] = None
        res_doc["delivery_confirmed"] = False

        await db.hotelrunner_reservations.insert_one(res_doc)
        await mark_event_processed(event_id, "processed")

        logger.info(f"[INGEST] Created {hr_number} from {channel} (mapping: {has_mapping})")
        return {"action": "created", "hr_number": hr_number, "pms_status": res_doc["pms_status"]}

    elif action == "update":
        res_doc["pms_status"] = "updated" if has_mapping else "pending_mapping"
        await db.hotelrunner_reservations.update_one(
            {"tenant_id": tenant_id, "hr_number": hr_number},
            {"$set": res_doc},
        )
        await mark_event_processed(event_id, "processed")

        logger.info(f"[INGEST] Updated {hr_number} from {channel}")
        return {"action": "updated", "hr_number": hr_number}

    elif action == "cancel":
        await db.hotelrunner_reservations.update_one(
            {"tenant_id": tenant_id, "hr_number": hr_number},
            {"$set": {
                "state": "cancelled",
                "pms_status": "cancellation_pending",
                "cancelled_at": now,
                "synced_at": now,
                "raw_event_id": event_id,
            }},
        )
        await mark_event_processed(event_id, "processed")

        logger.info(f"[INGEST] Cancelled {hr_number} from {channel}")
        return {"action": "cancelled", "hr_number": hr_number}

    await mark_event_processed(event_id, "error", f"Unknown action: {action}")
    return {"action": "error", "error": f"Unknown action: {action}"}


async def _check_room_mapping(tenant_id: str, rooms: list) -> bool:
    """Check if all room types in the reservation have PMS mappings."""
    if not rooms:
        return True
    for room in rooms:
        hr_code = room.get("room_type_code", "")
        if not hr_code:
            continue
        mapping = await db.hotelrunner_room_mappings.find_one({
            "tenant_id": tenant_id,
            "hr_inv_code": hr_code,
        })
        if not mapping:
            return False
    return True


# ── Full Ingest Pipeline (Entry Point) ───────────────────────────────

async def ingest_reservation(
    tenant_id: str,
    raw_payload: Dict[str, Any],
    event_type: str = "reservation",
    source: str = "webhook",
) -> Dict[str, Any]:
    """
    Full ingest pipeline entry point.
    Raw Store → Normalize → Idempotency → Decision → Import
    """
    hr_number = raw_payload.get("hr_number", "unknown")
    channel = raw_payload.get("channel", "unknown")

    # Step 1: Raw Event Store
    event_id = await store_raw_event(
        tenant_id=tenant_id,
        event_type=event_type,
        hr_number=hr_number,
        channel=channel,
        payload=raw_payload,
        source=source,
    )

    try:
        # Step 2: Normalize
        canonical = normalize_reservation(raw_payload, source=source)

        # Step 3+4: Idempotency + Decision + Import
        result = await process_reservation(tenant_id, canonical, event_type, event_id)
        return {"success": True, "event_id": event_id, **result}

    except Exception as e:
        await mark_event_processed(event_id, "error", str(e))
        logger.error(f"[INGEST] Error processing {hr_number}: {e}")
        return {"success": False, "event_id": event_id, "error": str(e)}
