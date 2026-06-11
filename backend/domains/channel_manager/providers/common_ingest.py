"""
Provider-agnostic Reservation Ingest Pipeline.
Shared by HotelRunner, Exely, and any future provider.

Raw Event Store → Idempotency Guard → Versioned Decision Engine → PMS Import
"""
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core.database import db

logger = logging.getLogger(__name__)


def _compute_payload_hash(payload: dict[str, Any]) -> str:
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


async def _create_unmatched_hold_for_reservation(
    provider: str, tenant_id: str, external_id: str,
    channel: str, res_doc: dict[str, Any], col,
) -> None:
    """Eslestirilemeyen (pending_mapping) rezervasyon icin tutma + alarm.

    Idempotent: shared helper ayni external_id icin tekrar cagrilirsa yeni
    tutma/alarm uretmez. Tutma kimligi provider rezervasyonuna baglanir.
    """
    from .unmatched_hold import create_unmatched_reservation_hold

    rooms = res_doc.get("rooms") or []
    first = rooms[0] if rooms else {}
    guest_name = (
        f"{res_doc.get('guest_firstname', '')} {res_doc.get('guest_lastname', '')}"
    ).strip()
    try:
        hold = await create_unmatched_reservation_hold(
            provider=provider,
            tenant_id=tenant_id,
            external_id=external_id,
            check_in=res_doc.get("checkin_date", ""),
            check_out=res_doc.get("checkout_date", ""),
            guest_name=guest_name,
            room_type_code=first.get("room_type_code", ""),
            rate_plan_code=first.get("rate_plan_code", ""),
            total_amount=float(res_doc.get("total", 0) or 0),
            currency=res_doc.get("currency", "TRY"),
            adults=first.get("adults", 1) or 1,
            children=first.get("children", 0) or 0,
            channel=channel,
            property_id=tenant_id,
        )
        if hold.get("booking_id"):
            await col.update_one(
                {"tenant_id": tenant_id, "external_id": external_id},
                {"$set": {"pms_booking_id": hold["booking_id"]}},
            )
    except Exception as e:  # noqa: BLE001 - tutma asla ingest'i kirmamali
        logger.exception(
            f"[{provider.upper()}] unmatched hold olusturma hatasi {external_id}: {e}"
        )


async def _release_unmatched_hold_for_reservation(
    provider: str, tenant_id: str, external_id: str,
    reason: str, delete_hold: bool = False,
) -> None:
    """Tutmayi serbest birak (rebind icin delete_hold=True, iptal icin False)."""
    from .unmatched_hold import release_unmatched_reservation_hold

    try:
        await release_unmatched_reservation_hold(
            tenant_id=tenant_id,
            external_id=external_id,
            reason=reason,
            delete_hold=delete_hold,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[{provider.upper()}] unmatched hold release hatasi {external_id}: {e}"
        )


async def store_raw_event(
    provider: str, tenant_id: str, event_type: str,
    external_id: str, channel: str, payload: dict[str, Any], source: str = "webhook",
    provider_event_id: str | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    doc: dict[str, Any] = {
        "id": event_id,
        "tenant_id": tenant_id,
        "provider": provider,
        "event_type": event_type,
        "external_id": external_id,
        "channel": channel,
        "source": source,
        "payload": payload,
        "payload_hash": _compute_payload_hash(payload),
        "received_at": datetime.now(UTC).isoformat(),
        "processed_at": None,
        "status": "pending",
        "error_message": None,
        "retry_count": 0,
    }
    # Optional deterministic dedup key. Used by `ingest_reservation` to
    # short-circuit catchup re-fetches of the same provider event.
    if provider_event_id:
        doc["provider_event_id"] = provider_event_id
    await _col(provider, "raw_events").insert_one(doc)
    return event_id


def _build_provider_event_id(
    raw_payload: dict[str, Any], external_id: str, event_type: str,
    payload_hash: str,
) -> str:
    """Deterministic ID for the pre-insert catchup dedup guard.

    Format mirrors HotelRunner's ``{external_id}_{event_type}_{version}``
    where ``version`` is the provider's last-modified timestamp when
    available. When the payload carries no timestamp (rare but possible
    for ad-hoc replay tools) we fall back to the payload hash so the
    same byte-identical payload still dedupes.
    """
    last_modified = (
        raw_payload.get("last_modify")
        or raw_payload.get("updated_at")
        or raw_payload.get("modified_at")
        or raw_payload.get("LastModifyDateTime")
        or ""
    )
    version_key = str(last_modified) if last_modified else f"hash:{payload_hash}"
    return f"{external_id}_{event_type}_{version_key}"


async def _check_provider_event_recorded(
    provider: str, tenant_id: str, provider_event_id: str,
) -> dict | None:
    """Provider-scoped pre-insert guard.

    Mirrors `unified_repository.check_provider_event_recorded` but
    targets the per-provider ``{provider}_raw_events`` collection used
    by the common ingest pipeline (Exely today, future providers
    tomorrow). HotelRunner has its own equivalent in
    ``hotelrunner_shared._persist_and_process``.

    Returns the existing event document (or None) regardless of
    processing status — failed events also have to short-circuit, since
    that is exactly the catchup re-ingest case the guard exists to
    prevent.
    """
    return await _col(provider, "raw_events").find_one(
        {
            "tenant_id": tenant_id,
            "provider_event_id": provider_event_id,
        },
        {"_id": 0, "id": 1, "status": 1},
    )


async def mark_event_processed(provider: str, event_id: str, status: str = "processed", error: str | None = None):
    await _col(provider, "raw_events").update_one(
        {"id": event_id},
        {"$set": {"processed_at": datetime.now(UTC).isoformat(), "status": status, "error_message": error}},
    )


async def check_idempotency(
    provider: str, tenant_id: str, external_id: str,
    event_type: str, provider_last_modified: str = "", payload_hash: str = "",
) -> dict[str, Any]:
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
    provider: str, tenant_id: str, canonical: dict[str, Any],
    event_type: str, event_id: str, payload_hash: str = "",
) -> dict[str, Any]:
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
    now = datetime.now(UTC).isoformat()

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
        if not has_mapping:
            await _create_unmatched_hold_for_reservation(
                provider, tenant_id, external_id, channel, res_doc, col,
            )
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
        if not has_mapping:
            await _create_unmatched_hold_for_reservation(
                provider, tenant_id, external_id, channel, res_doc, col,
            )
        else:
            # Eslestirme cozulmus olabilir -> varsa tutmayi rebind ile serbest birak.
            await _release_unmatched_hold_for_reservation(
                provider, tenant_id, external_id, "mapping_resolved", delete_hold=True,
            )
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
        # Iptal: varsa eslesmeyen-tutmanin sentinel kilitlerini serbest birak.
        await _release_unmatched_hold_for_reservation(
            provider, tenant_id, external_id, "ota_cancelled", delete_hold=False,
        )
        await mark_event_processed(provider, event_id, "processed")
        logger.info(f"[{provider.upper()}] Cancelled {external_id} from {channel}")
        return {"action": "cancelled", "external_id": external_id}

    await mark_event_processed(provider, event_id, "error", f"Unknown action: {action}")
    return {"action": "error", "error": f"Unknown action: {action}"}


async def ingest_reservation(
    provider: str, tenant_id: str, raw_payload: dict[str, Any],
    normalizer, event_type: str = "reservation", source: str = "pull",
) -> dict[str, Any]:
    """
    Full pipeline entry point. Provider passes its own normalizer function.
    normalizer(raw_payload, source) -> canonical dict

    Pre-insert dedup guard
    ----------------------
    Catchup loops (e.g. ``ExelyPullScheduler`` with its 5-minute safety
    window) re-fetch the same provider events at every cycle boundary.
    Without a guard, ``store_raw_event`` would create a fresh document
    in ``{provider}_raw_events`` for every re-fetched event, bloating
    the collection and tripping monitoring alerts. We compute a
    deterministic ``provider_event_id`` and short-circuit before the
    insert when an event with that ID already exists for the tenant.
    A skip is reported to the catchup dedup counter so the
    ``/monitoring/catchup-dedup`` endpoint surfaces it.
    """
    external_id = raw_payload.get("external_id") or raw_payload.get("hr_number") or raw_payload.get("reservation_id", "unknown")
    channel = raw_payload.get("channel", "direct")
    payload_hash = _compute_payload_hash(raw_payload)
    provider_event_id = _build_provider_event_id(
        raw_payload, external_id, event_type, payload_hash,
    )

    # Pre-insert dedup guard: short-circuit re-fetched catchup events.
    try:
        existing = await _check_provider_event_recorded(
            provider, tenant_id, provider_event_id,
        )
    except Exception as e:
        # The check is a best-effort optimisation. If it fails we fall
        # through to the normal insert + downstream idempotency path,
        # which still protects correctness via `check_idempotency`.
        logger.warning(
            f"[{provider.upper()}] pre-insert dedup check failed for "
            f"{provider_event_id}: {e}"
        )
        existing = None
    if existing is not None:
        try:
            from domains.channel_manager.monitoring.dedup_counter import (
                record_skip,
            )
            await record_skip(tenant_id, provider)
        except Exception as e:
            logger.warning(
                f"[{provider.upper()}] dedup_counter.record_skip failed: {e}"
            )
        logger.info(
            f"[CATCHUP-DEDUP] [{provider.upper()}] skipping already-recorded "
            f"event provider_event_id={provider_event_id} "
            f"existing_event_id={existing.get('id')!r} "
            f"existing_status={existing.get('status')!r}"
        )
        return {
            "success": True,
            "event_id": existing.get("id"),
            "action": "duplicate",
            "reason": "already_recorded",
            "provider_event_id": provider_event_id,
        }

    event_id = await store_raw_event(
        provider, tenant_id, event_type, external_id, channel, raw_payload,
        source, provider_event_id=provider_event_id,
    )
    try:
        canonical = normalizer(raw_payload, source)
        result = await process_reservation(provider, tenant_id, canonical, event_type, event_id, payload_hash)
        return {"success": True, "event_id": event_id, **result}
    except Exception as e:
        await mark_event_processed(provider, event_id, "error", str(e))
        logger.error(f"[{provider.upper()}] Ingest error for {external_id}: {e}")
        return {"success": False, "event_id": event_id, "error": str(e)}


async def log_sync(provider: str, tenant_id: str, sync_type: str, status: str,
                    duration_ms: int = 0, records: int = 0, error: str | None = None, user_name: str = "system"):
    await _col(provider, "sync_logs").insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "provider": provider,
        "timestamp": datetime.now(UTC).isoformat(),
        "sync_type": sync_type,
        "status": status,
        "duration_ms": duration_ms,
        "records_synced": records,
        "error_message": error,
        "initiator": user_name,
    })
