"""
Provider-agnostic Reservation Ingest Pipeline.
Shared by HotelRunner, Exely, and any future provider.

Raw Event Store → Idempotency Guard → Versioned Decision Engine → PMS Import
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.database import db

logger = logging.getLogger(__name__)


def _compute_payload_hash(payload: Dict[str, Any]) -> str:
    """Deterministic hash of payload for change detection."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]

PROVIDER_COLLECTIONS = {
    "hotelrunner": {
        "reservations": "hotelrunner_reservations",
        "raw_events": "hotelrunner_raw_events",
        "room_mappings": "hotelrunner_room_mappings",
        "sync_logs": "hotelrunner_sync_logs",
    },
    "exely": {
        "reservations": "exely_reservations",
        "raw_events": "exely_raw_events",
        "room_mappings": "exely_room_mappings",
        "sync_logs": "exely_sync_logs",
    },
}


def _col(provider: str, key: str):
    """Get the MongoDB collection for a provider."""
    return db[PROVIDER_COLLECTIONS[provider][key]]


async def store_raw_event(
    provider: str, tenant_id: str, event_type: str,
    external_id: str, channel: str, payload: Dict[str, Any], source: str = "webhook",
) -> str:
    event_id = str(uuid.uuid4())
    await _col(provider, "raw_events").insert_one({
        "id": event_id,
        "tenant_id": tenant_id,
        "provider": provider,
        "event_type": event_type,
        "external_id": external_id,
        "channel": channel,
        "source": source,
        "payload": payload,
        "payload_hash": _compute_payload_hash(payload),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "processed_at": None,
        "status": "pending",
        "error_message": None,
        "retry_count": 0,
    })
    return event_id


async def mark_event_processed(provider: str, event_id: str, status: str = "processed", error: Optional[str] = None):
    await _col(provider, "raw_events").update_one(
        {"id": event_id},
        {"$set": {"processed_at": datetime.now(timezone.utc).isoformat(), "status": status, "error_message": error}},
    )


async def check_idempotency(
    provider: str, tenant_id: str, external_id: str,
    event_type: str, provider_last_modified: str = "", payload_hash: str = "",
) -> Dict[str, Any]:
    """
    Versioned idempotency guard:
      same UniqueID + newer LastModifyDateTime → update
      same UniqueID + same LastModifyDateTime + same hash → ignore (stale duplicate)
      same UniqueID + cancelled status → cancel
      older LastModifyDateTime → discard as stale
    """
    existing = await _col(provider, "reservations").find_one(
        {"tenant_id": tenant_id, "external_id": external_id},
        {"_id": 0, "state": 1, "pms_status": 1, "delivery_confirmed": 1,
         "provider_last_modified_at": 1, "provider_payload_hash": 1},
    )

    if not existing:
        return {"action": "create", "existing": None}

    # Cancellation always wins regardless of timestamp
    if event_type == "cancellation":
        if existing.get("state") == "cancelled":
            return {"action": "skip", "reason": "already_cancelled", "existing": existing}
        return {"action": "cancel", "existing": existing}

    # Timestamp-based version comparison
    existing_modified = existing.get("provider_last_modified_at", "")
    if provider_last_modified and existing_modified:
        if provider_last_modified < existing_modified:
            return {"action": "skip", "reason": "stale_event", "existing": existing}
        if provider_last_modified == existing_modified:
            # Same timestamp — check payload hash for actual data change
            existing_hash = existing.get("provider_payload_hash", "")
            if payload_hash and existing_hash and payload_hash == existing_hash:
                return {"action": "skip", "reason": "duplicate_payload", "existing": existing}

    if event_type == "modification":
        return {"action": "update", "existing": existing}

    if event_type in ("new", "reservation"):
        if existing.get("pms_status") in ("imported", "confirmed"):
            return {"action": "skip", "reason": "already_imported", "existing": existing}
        return {"action": "update", "existing": existing}

    return {"action": "update", "existing": existing}


async def check_room_mapping(provider: str, tenant_id: str, rooms: list) -> bool:
    if not rooms:
        return True
    for room in rooms:
        code = room.get("room_type_code", "")
        if not code:
            continue
        field = "hr_inv_code" if provider == "hotelrunner" else "exely_room_code"
        mapping = await _col(provider, "room_mappings").find_one({"tenant_id": tenant_id, field: code})
        if not mapping:
            return False
    return True


async def process_reservation(
    provider: str, tenant_id: str, canonical: Dict[str, Any],
    event_type: str, event_id: str, payload_hash: str = "",
) -> Dict[str, Any]:
    external_id = canonical["external_id"]
    channel = canonical["channel"]
    provider_last_modified = canonical.get("provider_last_modified_at", "")

    idem = await check_idempotency(
        provider, tenant_id, external_id, event_type,
        provider_last_modified=provider_last_modified,
        payload_hash=payload_hash,
    )
    action = idem["action"]

    if action == "skip":
        await mark_event_processed(provider, event_id, "skipped", idem.get("reason"))
        return {"action": "skip", "reason": idem.get("reason"), "external_id": external_id}

    has_mapping = await check_room_mapping(provider, tenant_id, canonical["rooms"])
    now = datetime.now(timezone.utc).isoformat()

    res_doc = {
        "tenant_id": tenant_id,
        "external_id": external_id,
        "provider": provider,
        "source_provider": provider,
        "provider_reservation_id": canonical["provider_reservation_id"],
        "provider_event_id": event_id,
        "provider_version": canonical.get("provider_version", 1),
        "provider_last_modified_at": provider_last_modified,
        "provider_payload_hash": payload_hash,
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
        "message_uid": canonical.get("message_uid", ""),
        "source_system": provider.upper(),
        "ingested_via": canonical["ingested_via"],
        "external_write_protected": True,
        "synced_at": now,
        "raw_event_id": event_id,
        "confidence_score": None,
    }

    col = _col(provider, "reservations")

    if action == "create":
        res_doc["id"] = str(uuid.uuid4())
        res_doc["created_at"] = now
        res_doc["pms_status"] = "pending_mapping" if not has_mapping else "pending"
        res_doc["pms_booking_id"] = None
        res_doc["delivery_confirmed"] = False
        await col.insert_one(res_doc)
        await mark_event_processed(provider, event_id, "processed")
        logger.info(f"[{provider.upper()}] Created {external_id} from {channel}")
        return {"action": "created", "external_id": external_id, "pms_status": res_doc["pms_status"]}

    elif action == "update":
        res_doc["pms_status"] = "updated" if has_mapping else "pending_mapping"
        # Remove provider_version from $set to avoid conflict with $inc
        res_doc.pop("provider_version", None)
        await col.update_one({"tenant_id": tenant_id, "external_id": external_id}, {
            "$set": res_doc,
            "$inc": {"provider_version": 1},
        })
        await mark_event_processed(provider, event_id, "processed")
        logger.info(f"[{provider.upper()}] Updated {external_id} from {channel}")
        return {"action": "updated", "external_id": external_id}

    elif action == "cancel":
        await col.update_one(
            {"tenant_id": tenant_id, "external_id": external_id},
            {"$set": {
                "state": "cancelled", "pms_status": "cancellation_pending",
                "cancelled_at": now, "synced_at": now, "raw_event_id": event_id,
                "provider_event_id": event_id,
                "provider_last_modified_at": provider_last_modified,
                "provider_payload_hash": payload_hash,
            }},
        )
        await mark_event_processed(provider, event_id, "processed")
        logger.info(f"[{provider.upper()}] Cancelled {external_id} from {channel}")
        return {"action": "cancelled", "external_id": external_id}

    await mark_event_processed(provider, event_id, "error", f"Unknown action: {action}")
    return {"action": "error", "error": f"Unknown action: {action}"}


async def ingest_reservation(
    provider: str, tenant_id: str, raw_payload: Dict[str, Any],
    normalizer, event_type: str = "reservation", source: str = "pull",
) -> Dict[str, Any]:
    """
    Full pipeline entry point. Provider passes its own normalizer function.
    normalizer(raw_payload, source) -> canonical dict
    """
    external_id = raw_payload.get("external_id") or raw_payload.get("hr_number") or raw_payload.get("reservation_id", "unknown")
    channel = raw_payload.get("channel", "direct")
    payload_hash = _compute_payload_hash(raw_payload)

    event_id = await store_raw_event(provider, tenant_id, event_type, external_id, channel, raw_payload, source)
    try:
        canonical = normalizer(raw_payload, source)
        result = await process_reservation(provider, tenant_id, canonical, event_type, event_id, payload_hash)
        return {"success": True, "event_id": event_id, **result}
    except Exception as e:
        await mark_event_processed(provider, event_id, "error", str(e))
        logger.error(f"[{provider.upper()}] Ingest error for {external_id}: {e}")
        return {"success": False, "event_id": event_id, "error": str(e)}


async def log_sync(provider: str, tenant_id: str, sync_type: str, status: str,
                    duration_ms: int = 0, records: int = 0, error: Optional[str] = None, user_name: str = "system"):
    await _col(provider, "sync_logs").insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "provider": provider,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sync_type": sync_type,
        "status": status,
        "duration_ms": duration_ms,
        "records_synced": records,
        "error_message": error,
        "initiator": user_name,
    })
