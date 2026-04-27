"""
HotelRunner Shared Utilities

Common functions used by both the webhook ingestion module and the sync/polling module:
- Multi-room reservation explosion
- Timeline logging
- Raw payload storage
- Persist & process pipeline entry point
"""
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core.database import db
from domains.channel_manager import unified_repository as repo
from domains.channel_manager.data_model import (
    ConnectorProvider,
    ProcessingStatus,
    RawChannelEvent,
    RawEventSource,
)
from domains.channel_manager.ingest.normalizer import extract_hotelrunner_identity
from domains.channel_manager.ingest.pipeline import process_event

logger = logging.getLogger(__name__)


# ── Timeline Helper ───────────────────────────────────────────────────

def _timeline_append(**kwargs):
    """Fire-and-forget timeline write. Returns a coroutine."""
    try:
        from controlplane.timeline_writer import get_timeline_writer
        return get_timeline_writer().append(**kwargs)
    except Exception:
        async def _noop():
            return None
        return _noop()


# ── Raw Payload Storage ──────────────────────────────────────────────

async def _store_raw_payload(
    tenant_id: str, correlation_id: str, provider: str,
    external_id: str, event_type: str, payload: dict,
    source_ip: str,
) -> str:
    """Store raw webhook JSON payload for debugging. Returns payload_id."""
    payload_id = str(uuid.uuid4())
    try:
        raw_str = json.dumps(payload, default=str, ensure_ascii=False)
        await db.webhook_raw_payloads.insert_one({
            "id": payload_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "provider": provider,
            "external_id": external_id,
            "event_type": event_type,
            "content_type": "application/json",
            "raw_payload": raw_str,
            "payload_size_bytes": len(raw_str.encode("utf-8")),
            "source_ip": source_ip,
            "received_at": datetime.now(UTC).isoformat(),
        })
    except Exception as e:
        logger.warning("Raw payload storage failed (non-blocking): %s", e)
    return payload_id


# ── Property ID Resolver ─────────────────────────────────────────────

def _resolve_property_id(body: dict[str, Any]) -> str:
    """Extract property_id from payload."""
    return body.get("property_id", "prop-001")


# ── Multi-room Reservation Exploder ──────────────────────────────────

def explode_multi_room_reservation(raw_reservation: dict[str, Any]) -> list[dict[str, Any]]:
    """Explode a HotelRunner reservation with multiple rooms into per-room payloads.

    HotelRunner sends multi-room bookings as one reservation object with a `rooms` array.
    Each room becomes a separate PMS booking. Sub-reservation numbering follows HR convention:
      rooms[0] -> hr_number (original)
      rooms[1] -> hr_number-1
      rooms[2] -> hr_number-2
      ...

    Per-room state: Each room may have its own cancellation status.
    The room-level state overrides the top-level state for that specific sub-reservation.

    If the reservation has 0 or 1 rooms, returns it as-is (list of 1).
    """
    rooms = raw_reservation.get("rooms", [])
    if not rooms or not isinstance(rooms, list) or len(rooms) <= 1:
        return [raw_reservation]

    hr_number = str(raw_reservation.get("hr_number", ""))
    exploded = []

    for idx, room in enumerate(rooms):
        if not isinstance(room, dict):
            continue

        sub_hr = hr_number if idx == 0 else f"{hr_number}-{idx}"

        sub_payload = {
            **raw_reservation,
            "hr_number": sub_hr,
            "rooms": [room],
            "total": float(room.get("price", 0) or 0),
            "_exploded_from": hr_number,
            "_room_index": idx,
        }

        # Use room-level dates if available, fallback to reservation-level
        if room.get("checkin_date"):
            sub_payload["checkin_date"] = room["checkin_date"]
        if room.get("checkout_date"):
            sub_payload["checkout_date"] = room["checkout_date"]

        # Per-room state override: if the room has its own state, use it
        # This is critical for multi-room reservations where only some rooms are cancelled
        room_state = (room.get("state") or "").lower()
        room_status = (room.get("status") or "").lower()
        room_cancel_reason = room.get("cancel_reason") or ""

        if room_state in ("cancelled", "canceled"):
            sub_payload["state"] = "cancelled"
            sub_payload["_room_cancelled"] = True
        elif room_status in ("cancelled", "canceled"):
            sub_payload["state"] = "cancelled"
            sub_payload["_room_cancelled"] = True
        elif room_cancel_reason:
            # Only use cancel_reason for cancellation detection.
            # next_states=['cancel'] means "cancel is an available ACTION", NOT that
            # the room IS cancelled. HR sends this for ALL confirmed rooms.
            sub_payload["state"] = "cancelled"
            sub_payload["_room_cancelled"] = True
            sub_payload["cancel_reason"] = room_cancel_reason
        else:
            # Room is NOT cancelled — CRITICAL: clear top-level cancel markers
            # that leaked via {**raw_reservation}. When ONE room in a multi-room
            # reservation is cancelled, HR may set top-level state/cancel_reason.
            # Without this cleanup, ALL rooms would be incorrectly marked as cancelled.
            sub_payload["_room_cancelled"] = False
            top_state = (sub_payload.get("state") or "").lower()
            if top_state in ("cancelled", "canceled"):
                sub_payload["state"] = room_state if room_state else "confirmed"
            # Clear top-level cancel_reason leak (room has no cancel_reason of its own)
            sub_payload.pop("cancel_reason", None)

        exploded.append(sub_payload)

    return exploded if exploded else [raw_reservation]


# ── Persist & Process Pipeline Entry ─────────────────────────────────

async def _persist_and_process(
    tenant_id: str, property_id: str, payload: dict[str, Any], event_type: str,
    source_ip: str = "system",
):
    """Persist raw event and process through the unified ingest pipeline.

    Timeline stages written:
      1. webhook_received — raw payload stored
      2. (normalized, deduplicated, validated — written by pipeline.process_event)
    """
    from core.tenant_db import set_tenant_context
    set_tenant_context(tenant_id)

    t_start = datetime.now(UTC)
    correlation_id = str(uuid.uuid4())
    identity = extract_hotelrunner_identity(payload)
    hr_number = identity.get("external_reservation_id", "")
    last_mod = identity.get("provider_last_modified_at", "")
    identity["provider_event_id"] = f"{hr_number}_{event_type}_{last_mod}"

    # ── Pre-insert idempotency guard ─────────────────────────────────
    # provider_event_id is deterministic ({hr_number}_{event_type}_{last_modified}).
    # If a raw_channel_events row already exists for it (in any status —
    # including failed/pending_mapping), do NOT create a second row. The
    # downstream pipeline's `check_provider_event_exists` only catches
    # processed/duplicate, so without this guard catchup loops re-insert the
    # same failed event on every cycle and the collection grows unbounded.
    if hr_number and last_mod:
        existing = await repo.check_provider_event_recorded(
            tenant_id, "hotelrunner", identity["provider_event_id"],
        )
        if existing:
            logger.info(
                f"[CATCHUP-DEDUP] skip insert: provider_event_id="
                f"{identity['provider_event_id']} already recorded "
                f"(status={existing.get('processing_status')}, "
                f"decision={existing.get('decision_result')})"
            )
            try:
                from domains.channel_manager.monitoring.dedup_counter import record_skip
                await record_skip(tenant_id, "hotelrunner")
            except Exception as e:
                logger.warning(f"[CATCHUP-DEDUP] counter record failed (non-blocking): {e}")
            from domains.channel_manager.ingest.pipeline import PipelineResult, IngestDecision
            result = PipelineResult(existing.get("id", ""))
            result.decision = IngestDecision.SKIP
            result.reason = "Pre-insert duplicate (provider_event_id already recorded)"
            result.status = "duplicate"
            return result

    # Store raw payload
    raw_payload_id = await _store_raw_payload(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        provider="hotelrunner",
        external_id=hr_number,
        event_type=event_type,
        payload=payload,
        source_ip=source_ip,
    )

    # Timeline: webhook_received
    t_received = datetime.now(UTC)
    recv_duration_ms = int((t_received - t_start).total_seconds() * 1000)
    await _timeline_append(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        entity_type="reservation",
        external_id=hr_number,
        stage="webhook_received",
        status="success",
        source="hotelrunner_webhook",
        provider="hotelrunner",
        duration_ms=recv_duration_ms,
        metadata={
            "raw_payload_id": raw_payload_id,
            "event_type": event_type,
            "hr_number": hr_number,
            "source_ip": source_ip,
            "content_type": "application/json",
        },
    )

    payload_hash = RawChannelEvent.compute_payload_hash(payload)

    event = RawChannelEvent(
        tenant_id=tenant_id,
        property_id=property_id,
        provider=ConnectorProvider.HOTELRUNNER,
        event_type=event_type,
        provider_event_id=identity["provider_event_id"],
        external_reservation_id=identity["external_reservation_id"],
        provider_version=identity["provider_version"],
        provider_last_modified_at=identity["provider_last_modified_at"],
        raw_payload=payload,
        payload_hash=payload_hash,
        received_via=RawEventSource.WEBHOOK,
        processing_status=ProcessingStatus.PENDING,
        correlation_id=correlation_id,
    )
    event_doc = event.to_doc()
    event_id = await repo.insert_raw_event(event_doc)
    event_doc["id"] = event_id

    result = await process_event(event_doc)
    logger.info(f"[WEBHOOK] {event_type}: {event_id} -> {result.decision} ({result.reason})")
    return result
