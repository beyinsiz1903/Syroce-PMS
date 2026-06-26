"""
OTA-002: Outbox Service — Guaranteed Delivery for PMS → OTA Sync
================================================================
Provides the write-side of the outbox pattern.

Every critical PMS event (booking CRUD, room block, inventory change)
is durably written to `outbox_events` INSIDE the business transaction.

A background worker picks them up asynchronously and dispatches to providers.

Usage inside a business transaction:
    await enqueue_outbox_event(
        db, session=session,
        tenant_id=tenant_id,
        event_type="booking.created.v1",
        entity_type="booking",
        entity_id=booking_id,
        payload={...},
    )
"""
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger("core.outbox_service")


# ── Event Type Constants ─────────────────────────────────────────────

BOOKING_CREATED = "booking.created.v1"
BOOKING_CANCELLED = "booking.cancelled.v1"
BOOKING_MODIFIED = "booking.modified.v1"
# CM-Hardening Turu #3a (May 2026): no-show outbox parity with cancel.
# Provider handler is deferred (Turu #3b/#3c); dispatcher routes this
# to a graceful no-op until HotelRunner/Exely adapters land.
BOOKING_NOSHOW = "booking.no_show.v1"
INVENTORY_AVAILABILITY_UPDATED = "inventory.availability.updated.v1"
INVENTORY_BLOCKED = "inventory.blocked.v1"
INVENTORY_RELEASED = "inventory.released.v1"
RESTRICTION_UPDATED = "restriction.updated.v1"
RATE_UPDATED = "rate.updated.v1"

# ── Internal-Consistency (IC) event types — Task #389 ────────────────
# These NEVER reach the channel manager / OTA / EventSyncService. They drive
# the async, guaranteed, idempotent POS -> folio posting (Outbox/Compensation)
# entirely inside this system. The dispatcher routes them to the local folio
# consumer BEFORE the CM mapping, so external_calls stays []. They are
# deliberately NOT added to OTA_OUTBOX_EVENT_TYPES.
POS_CHARGE_POSTED = "pos.charge.posted.v1"
POS_CHARGE_REVERSED = "pos.charge.reversed.v1"

IC_OUTBOX_EVENT_TYPES = {
    POS_CHARGE_POSTED,
    POS_CHARGE_REVERSED,
}

OTA_OUTBOX_EVENT_TYPES = {
    BOOKING_CREATED,
    BOOKING_CANCELLED,
    BOOKING_NOSHOW,
    BOOKING_MODIFIED,
    INVENTORY_AVAILABILITY_UPDATED,
    INVENTORY_BLOCKED,
    INVENTORY_RELEASED,
    RESTRICTION_UPDATED,
    RATE_UPDATED,
}

# Map legacy event types to OTA outbox types
LEGACY_EVENT_MAP = {
    "reservation.created.v1": BOOKING_CREATED,
    "reservation.cancelled.v1": BOOKING_CANCELLED,
    "reservation.modified.v1": BOOKING_MODIFIED,
    "inventory.blocked.v1": INVENTORY_BLOCKED,
    "inventory.released.v1": INVENTORY_RELEASED,
}

# ── Status Constants ─────────────────────────────────────────────────

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_PROCESSED = "processed"
STATUS_RETRY = "retry"
STATUS_FAILED = "failed"

DEFAULT_MAX_ATTEMPTS = 5

# ── Retry backoff schedule (seconds) ────────────────────────────────
RETRY_BACKOFF = {
    1: 0,     # attempt 1 → immediate
    2: 30,    # attempt 2 → +30s
    3: 120,   # attempt 3 → +2min
    4: 600,   # attempt 4 → +10min
    5: 1800,  # attempt 5 → +30min
    # Agency webhook tail (max_attempts=8, ADR Karar 6). OTA events cap at 5 and
    # NEVER reach attempts 6-8, so keys 1-5 above stay untouched. This stretches
    # the final 3 agency retries so a multi-hour partner outage isn't prematurely
    # dead-lettered (total span ~24h before DLQ).
    6: 14400,   # attempt 6 → +4h
    7: 28800,   # attempt 7 → +8h
    8: 43200,   # attempt 8 → +12h
}

# ── Retryable vs permanent errors ───────────────────────────────────
RETRYABLE_ERROR_KEYWORDS = [
    "timeout", "timed out", "connection refused", "connection reset",
    "502", "503", "504", "429", "rate limit",
    "temporary", "unavailable", "network",
]

PERMANENT_ERROR_KEYWORDS = [
    "mapping error", "invalid payload", "invalid_xml",
    "authentication failed", "401", "403", "permanent",
    "unsupported", "schema_mismatch",
]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _build_idempotency_key(
    tenant_id: str,
    event_type: str,
    entity_id: str,
    payload: dict[str, Any],
) -> str:
    payload_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    return f"{tenant_id}:{event_type}:{entity_id}:{payload_hash}"


def is_retryable_error(error_message: str) -> bool:
    msg_lower = error_message.lower()
    for kw in PERMANENT_ERROR_KEYWORDS:
        if kw in msg_lower:
            return False
    for kw in RETRYABLE_ERROR_KEYWORDS:
        if kw in msg_lower:
            return True
    # Default: retryable (safer to retry than to lose)
    return True


def compute_next_available_at(attempt_count: int) -> str:
    backoff_seconds = RETRY_BACKOFF.get(attempt_count, 1800)
    from datetime import timedelta
    return (datetime.now(UTC) + timedelta(seconds=backoff_seconds)).isoformat()


async def enqueue_outbox_event(
    db,
    session=None,
    *,
    tenant_id: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    provider: str | None = None,
    connector_id: str | None = None,
    property_id: str | None = None,
    correlation_id: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """
    Enqueue an outbox event for guaranteed OTA delivery.

    MUST be called inside the same transaction as the business state change.

    Args:
        db: Motor database instance
        session: MongoDB session (for transaction support)
        tenant_id: Tenant identifier
        event_type: One of OTA_OUTBOX_EVENT_TYPES
        entity_type: "booking", "room_block", "inventory", etc.
        entity_id: ID of the affected entity
        payload: Event-specific data for the provider adapter
        provider: Target provider ("exely", "hotelrunner", or None for fan-out)
        connector_id: Target connector ID (or None for fan-out)
        property_id: Property ID (defaults to tenant_id)
        correlation_id: Request correlation ID for tracing
        max_attempts: Maximum delivery attempts (default 5)
        idempotency_key: Optional explicit, payload-independent dedup key. When
            given, it overrides the default (tenant, type, entity, payload) hash —
            used by agency fan-out so retries dedupe even if the payload drifts.

    Returns:
        The inserted outbox event document (without _id).
    """
    now = _utc_now()
    event_id = str(uuid.uuid4())

    # Caller may supply an explicit, payload-independent dedup key (e.g. agency
    # fan-out: stable across worker retries even if the derived payload drifts).
    # Default: hash of (tenant, type, entity, payload).
    idempotency_key = idempotency_key or _build_idempotency_key(
        tenant_id, event_type, entity_id, payload
    )

    doc = {
        "id": event_id,
        "tenant_id": tenant_id,
        "property_id": property_id or tenant_id,
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "provider": provider,
        "connector_id": connector_id,
        "payload": payload,
        "status": STATUS_PENDING,
        "attempt_count": 0,
        "max_attempts": max_attempts,
        "available_at": now,
        "last_error": None,
        "last_attempt_at": None,
        "processed_at": None,
        "idempotency_key": idempotency_key,
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "created_at": now,
        "updated_at": now,
    }

    try:
        if session:
            await db.outbox_events.insert_one(doc, session=session)
        else:
            await db.outbox_events.insert_one(doc)
    except DuplicateKeyError:
        logger.info(
            "Outbox event already enqueued (idempotent): %s %s %s",
            event_type, entity_type, entity_id,
        )

    doc.pop("_id", None)
    logger.info(
        "Outbox event enqueued: id=%s type=%s entity=%s/%s provider=%s",
        event_id, event_type, entity_type, entity_id, provider or "fan-out",
    )
    return doc


async def ensure_outbox_indexes(db) -> None:
    """Create required indexes for efficient worker claiming and ops visibility."""
    indexes = [
        {
            "keys": [("tenant_id", 1), ("status", 1), ("available_at", 1), ("created_at", 1)],
            "name": "idx_outbox_worker_claim",
        },
        {
            "keys": [("tenant_id", 1), ("provider", 1), ("status", 1), ("created_at", -1)],
            "name": "idx_outbox_provider_status",
        },
        {
            "keys": [("idempotency_key", 1)],
            "name": "idx_outbox_idempotency",
            "kwargs": {
                "unique": True,
                "partialFilterExpression": {"idempotency_key": {"$type": "string"}},
            },
        },
        {
            "keys": [("correlation_id", 1)],
            "name": "idx_outbox_correlation",
        },
        {
            "keys": [("entity_type", 1), ("entity_id", 1), ("event_type", 1)],
            "name": "idx_outbox_entity_event",
        },
    ]
    for idx in indexes:
        try:
            await db.outbox_events.create_index(
                idx["keys"],
                name=idx["name"],
                background=True,
                **idx.get("kwargs", {}),
            )
        except Exception as e:
            if "already exists" in str(e) or "IndexOptionsConflict" in str(e):
                pass
            else:
                logger.warning("Outbox index %s failed: %s", idx["name"], e)
    logger.info("OTA outbox indexes ensured")
