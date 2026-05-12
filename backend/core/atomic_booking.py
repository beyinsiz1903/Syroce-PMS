"""
Atomic Booking Creation — Overbooking Prevention v2
=====================================================
Single entry point for ALL booking inserts.

Strategy: Room-Night Locking with Full Audit Trail
  1. Parse check-in/check-out into a list of "night dates"
  2. Insert one lock document per night into `room_night_locks` (unique index)
  3. If any insert fails (DuplicateKeyError), the room is already booked → 409
  4. Insert the booking document
  5. On cancellation, remove the lock documents
  6. Every lock/conflict/release event writes to event_timeline (fire-and-forget)

Invariants enforced (see ADR-001):
  INV-1: Sellable inventory never goes negative (unique index)
  INV-2: Full-stay is all-or-nothing (compensation on partial failure)
  INV-5: OOO/OOS uses same lock table (booking_id prefix "OOO:" / "OOS:")
  INV-6: Every conflict/release appears in event_timeline

The unique compound index on (tenant_id, room_id, night_date) makes
double-booking physically impossible, even under high concurrency.

Overlap rule:
  A booking for check_in=Jan 10 14:00, check_out=Jan 12 11:00
  claims nights: Jan 10, Jan 11 (NOT Jan 12 — guest departs that morning).

If room_id is None (unassigned OTA import), lock is skipped.
"""
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.errors import DuplicateKeyError

from core.database import db

logger = logging.getLogger("core.atomic_booking")

ACTIVE_BOOKING_STATUSES = ["confirmed", "checked_in", "guaranteed"]

# OOO/OOS lock prefixes — these participate in the same uniqueness constraint
OOO_PREFIX = "OOO:"
OOS_PREFIX = "OOS:"
MAINTENANCE_PREFIX = "MAINT:"


class BookingConflictError(Exception):
    """Raised when a booking conflicts with an existing reservation."""

    def __init__(self, message: str, conflicting_booking_id: str | None = None,
                 conflict_type: str = "booking", conflicting_nights: list[str] | None = None):
        super().__init__(message)
        self.conflicting_booking_id = conflicting_booking_id
        self.conflict_type = conflict_type
        self.conflicting_nights = conflicting_nights or []


def _night_dates(check_in: str, check_out: str) -> list[str]:
    """Return list of night dates (YYYY-MM-DD) that a booking occupies."""
    ci = datetime.fromisoformat(check_in.replace("Z", "+00:00"))
    co = datetime.fromisoformat(check_out.replace("Z", "+00:00"))
    ci_date = ci.date()
    co_date = co.date()
    nights = []
    current = ci_date
    while current < co_date:
        nights.append(current.isoformat())
        current += timedelta(days=1)
    return nights


async def _timeline_event(tenant_id: str, stage: str, status: str,
                          booking_id: str, room_id: str,
                          metadata: dict[str, Any] | None = None,
                          correlation_id: str | None = None):
    """Fire-and-forget timeline event for booking lock operations."""
    try:
        from controlplane.timeline_writer import get_timeline_writer
        writer = get_timeline_writer()
        await writer.append(
            tenant_id=tenant_id,
            correlation_id=correlation_id or booking_id or "unknown",
            entity_type="booking",
            entity_id=booking_id or "",
            stage=stage,
            status=status,
            source="atomic_booking",
            metadata=metadata or {},
        )
    except Exception as exc:
        logger.error("Timeline write failed for %s/%s (booking=%s): %s", stage, status, booking_id, exc)


async def _emit_overbooking_alert(
    *,
    tenant_id: str,
    booking_id: str,
    room_id: str,
    conflict_type: str,
    conflict_msg: str,
    conflict_night: str,
    conflicting_booking_id: str | None,
    correlation_id: str | None,
) -> None:
    """Best-effort overbooking alert emission for the front-desk signal channel.

    CM-Hardening Turu #1a (May 2026) — closes the silent `lock_conflict` gap
    surfaced in the CM Sandbox Discovery report. Until now `lock_conflict`
    events were only persisted to `event_timeline` with no downstream consumer,
    so OTA-driven conflicts that fell back to `pending_assignment` reached
    front-desk only via manual queue inspection.

    This helper is invoked once per `BookingConflictError` raise inside
    `create_booking_atomic` — i.e. exactly when an overbooking is physically
    blocked by the unique room-night lock. It writes:
      1. A `db.notifications` row of type `overbooking_risk` (severity=warning)
         so the existing front-desk notification panel surfaces it without any
         polling/push wiring change.
      2. A best-effort `AlertDeliveryService.deliver_alert(...)` dispatch so
         tenants with email/Slack/Teams/webhook channels configured get an
         out-of-band ping.

    Both writes are wrapped in a broad try/except so a notification failure
    can NEVER block the booking flow itself (which already raised
    `BookingConflictError` to the caller). Mirrors the cancel-flow pattern in
    `reservation_state_machine.handle_cancellation` (notifications insert
    inside its own try/except, comment: "Non-critical").
    """
    try:
        import uuid as _uuid

        room_number = ""
        try:
            room_doc = await db.rooms.find_one({"id": room_id}, {"_id": 0, "room_number": 1})
            if room_doc:
                room_number = room_doc.get("room_number", "") or ""
        except Exception:
            pass

        title_room = f"Oda {room_number}" if room_number else f"Oda {room_id}"
        type_label = {
            "ooo": "Arıza Bloğu (OOO)",
            "oos": "Servis Dışı Bloğu (OOS)",
            "maintenance": "Bakım Bloğu",
            "booking": "Mevcut Rezervasyon",
        }.get(conflict_type, "Çakışma")

        await db.notifications.insert_one({
            "id": str(_uuid.uuid4()),
            "tenant_id": tenant_id,
            "type": "overbooking_risk",
            "severity": "warning",
            "title": f"Overbooking Engellendi - {title_room}",
            "message": (
                f"{conflict_night} gecesi için {title_room} talebi reddedildi "
                f"(çakışma kaynağı: {type_label}"
                + (f", booking {conflicting_booking_id}" if conflicting_booking_id else "")
                + "). "
                "OTA kaynaklı bookingler 'pending_assignment' kuyruğuna düşmüş olabilir — kontrol edin."
            ),
            "related_entity": "booking",
            "related_id": booking_id or "",
            "read": False,
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": {
                "conflict_type": conflict_type,
                "conflict_night": conflict_night,
                "conflicting_booking_id": conflicting_booking_id,
                "correlation_id": correlation_id,
                "rejected_room_id": room_id,
                "rejected_booking_id": booking_id,
            },
        })
    except Exception as exc:
        logger.warning(
            "Overbooking notification insert failed (booking=%s, room=%s): %s",
            booking_id, room_id, exc,
        )

    # Best-effort out-of-band delivery (email/Slack/Teams/webhook).
    # Skipped silently when no channels are configured for the tenant.
    try:
        from channel_manager.application.alert_delivery_service import AlertDeliveryService

        alert = {
            "id": f"overbooking-{booking_id or 'unknown'}-{conflict_night}",
            "trigger": "overbooking_blocked",
            "severity": "warning",
            "connector_id": "*",  # cross-connector signal (PMS-internal source)
            "description": conflict_msg,
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": {
                "conflict_type": conflict_type,
                "conflict_night": conflict_night,
                "conflicting_booking_id": conflicting_booking_id,
                "rejected_room_id": room_id,
                "rejected_booking_id": booking_id,
                "correlation_id": correlation_id,
            },
        }
        await AlertDeliveryService().deliver_alert(tenant_id, alert)
    except Exception as exc:
        logger.warning(
            "AlertDeliveryService dispatch failed (booking=%s, room=%s): %s",
            booking_id, room_id, exc,
        )


def assert_pending_assignment(booking: dict[str, Any]) -> None:
    """Defensive guard for OTA fallback paths.

    When `create_booking_atomic()` raises `BookingConflictError`, callers fall
    back to inserting the booking with `room_id=None` + `allocation_source="pending_assignment"`.
    This guard asserts that contract right before `db.bookings.insert_one(...)`.

    Uses an explicit `raise RuntimeError` (not `assert`) so the check survives
    Python `-O` (optimized) runs. Catches future regressions where a developer
    accidentally removes the `room_id=None` reset and re-introduces the
    atomic-guard bypass that caused Bug DAE.
    """
    if booking.get("room_id") is not None:
        raise RuntimeError(
            "pending_assignment fallback must have room_id=None to avoid atomic guard bypass"
        )


async def create_booking_atomic(booking_doc: dict[str, Any]) -> dict[str, Any]:
    """
    Atomically create a booking with room-night locking.

    INV-2: All-or-nothing. If any night fails, all claimed nights are released.
    INV-6: Every lock acquisition, conflict, and compensation is audited.

    1. Claim each night via unique-index insert into room_night_locks.
    2. If any night is already claimed → BookingConflictError (409).
    3. Insert the booking document.
    4. If booking insert fails → release all claimed nights.
    """
    # Encrypt PII fields before persistence
    try:
        from security.encrypted_lookup import encrypt_booking_doc
        booking_doc = encrypt_booking_doc(booking_doc)
    except ImportError:
        logger.warning(
            "PII encryption module not available — booking %s stored without field-level encryption",
            booking_doc.get("id", "unknown"),
        )
    except Exception as enc_err:
        logger.error(
            "PII encryption failed for booking %s — aborting to prevent unencrypted storage: %s",
            booking_doc.get("id", "unknown"), enc_err,
        )
        raise RuntimeError(f"PII encryption failed, booking not saved: {enc_err}") from enc_err
    tenant_id = booking_doc.get("tenant_id")
    room_id = booking_doc.get("room_id")
    check_in = booking_doc.get("check_in") or booking_doc.get("check_in_date")
    check_out = booking_doc.get("check_out") or booking_doc.get("check_out_date")
    booking_status = booking_doc.get("status", "confirmed")
    booking_id = booking_doc.get("id")
    correlation_id = booking_doc.get("correlation_id") or booking_id

    # Cancelled/no-show bookings don't need conflict check
    if booking_status in ("cancelled", "no_show"):
        await db.bookings.insert_one(booking_doc)
        booking_doc.pop("_id", None)
        return booking_doc

    # Unassigned bookings (no room_id) skip conflict check
    if not room_id or not check_in or not check_out:
        await db.bookings.insert_one(booking_doc)
        booking_doc.pop("_id", None)
        return booking_doc

    nights = _night_dates(check_in, check_out)
    if not nights:
        await db.bookings.insert_one(booking_doc)
        booking_doc.pop("_id", None)
        return booking_doc

    # Phase 1: Claim each night (INV-1, INV-2)
    claimed_nights: list[str] = []
    try:
        for night in nights:
            lock_doc = {
                "tenant_id": tenant_id,
                "room_id": room_id,
                "night_date": night,
                "booking_id": booking_id,
                "lock_type": "booking",
                "created_at": datetime.now(UTC).isoformat(),
            }
            try:
                await db.room_night_locks.insert_one(lock_doc)
                claimed_nights.append(night)
            except DuplicateKeyError:
                # Find which booking/hold owns this night
                existing = await db.room_night_locks.find_one(
                    {"tenant_id": tenant_id, "room_id": room_id, "night_date": night},
                    {"_id": 0, "booking_id": 1, "lock_type": 1},
                )
                conflicting_id = existing.get("booking_id") if existing else None
                lock_type = existing.get("lock_type", "booking") if existing else "booking"

                # Determine conflict type for clear error messages
                if conflicting_id and conflicting_id.startswith(OOO_PREFIX):
                    conflict_type = "ooo"
                    conflict_msg = f"Room {room_id} is Out of Order for {night}"
                elif conflicting_id and conflicting_id.startswith(OOS_PREFIX):
                    conflict_type = "oos"
                    conflict_msg = f"Room {room_id} is Out of Service for {night}"
                elif conflicting_id and conflicting_id.startswith(MAINTENANCE_PREFIX):
                    conflict_type = "maintenance"
                    conflict_msg = f"Room {room_id} is under Maintenance for {night}"
                else:
                    conflict_type = "booking"
                    conflict_msg = (
                        f"Room not available for {check_in} to {check_out}. "
                        f"Night {night} already booked"
                        + (f" by {conflicting_id}" if conflicting_id else "")
                    )

                # INV-6: Log the conflict
                await _timeline_event(
                    tenant_id=tenant_id,
                    stage="lock_conflict",
                    status="rejected",
                    booking_id=booking_id,
                    room_id=room_id,
                    correlation_id=correlation_id,
                    metadata={
                        "conflict_night": night,
                        "conflict_type": conflict_type,
                        "conflicting_booking_id": conflicting_id,
                        "conflicting_lock_type": lock_type,
                        "requested_nights": nights,
                        "claimed_before_conflict": claimed_nights,
                    },
                )

                # INV-2: Full compensation — release all claimed nights
                if claimed_nights:
                    await db.room_night_locks.delete_many({
                        "tenant_id": tenant_id,
                        "room_id": room_id,
                        "night_date": {"$in": claimed_nights},
                        "booking_id": booking_id,
                    })

                    # INV-6: Log the compensation
                    await _timeline_event(
                        tenant_id=tenant_id,
                        stage="lock_compensation",
                        status="rolled_back",
                        booking_id=booking_id,
                        room_id=room_id,
                        correlation_id=correlation_id,
                        metadata={
                            "released_nights": claimed_nights,
                            "failed_night": night,
                            "total_requested": len(nights),
                            "total_claimed_before_rollback": len(claimed_nights),
                        },
                    )

                # CM-Hardening Turu #1a (May 2026): emit front-desk signal
                # so OTA-driven conflicts no longer fail silently. Best-effort,
                # never blocks the BookingConflictError raise that follows.
                await _emit_overbooking_alert(
                    tenant_id=tenant_id,
                    booking_id=booking_id,
                    room_id=room_id,
                    conflict_type=conflict_type,
                    conflict_msg=conflict_msg,
                    conflict_night=night,
                    conflicting_booking_id=conflicting_id,
                    correlation_id=correlation_id,
                )

                raise BookingConflictError(
                    conflict_msg,
                    conflicting_booking_id=conflicting_id,
                    conflict_type=conflict_type,
                    conflicting_nights=[night],
                )

        # INV-6: Log successful lock acquisition
        await _timeline_event(
            tenant_id=tenant_id,
            stage="lock_acquired",
            status="success",
            booking_id=booking_id,
            room_id=room_id,
            correlation_id=correlation_id,
            metadata={
                "nights_locked": nights,
                "night_count": len(nights),
                "room_id": room_id,
                "check_in": check_in,
                "check_out": check_out,
            },
        )

        # Phase 2: Insert the booking
        await db.bookings.insert_one(booking_doc)

    except BookingConflictError:
        raise
    except Exception:
        # Rollback: release claimed nights on any failure
        if claimed_nights:
            await db.room_night_locks.delete_many({
                "tenant_id": tenant_id,
                "room_id": room_id,
                "night_date": {"$in": claimed_nights},
                "booking_id": booking_id,
            })
            # INV-6: Log the compensation
            await _timeline_event(
                tenant_id=tenant_id,
                stage="lock_compensation",
                status="error_rollback",
                booking_id=booking_id,
                room_id=room_id,
                correlation_id=correlation_id,
                metadata={
                    "released_nights": claimed_nights,
                    "reason": "booking_insert_failed",
                },
            )
        raise

    booking_doc.pop("_id", None)
    logger.info(
        "Atomic booking created: %s room=%s %s->%s (%d nights locked)",
        booking_id, room_id, check_in, check_out, len(nights),
    )
    return booking_doc


async def release_booking_nights(tenant_id: str, booking_id: str,
                                 reason: str = "cancelled",
                                 correlation_id: str | None = None) -> int:
    """Release room-night locks when a booking is cancelled/no-show.

    INV-6: Logs the release event to timeline.
    """
    # Capture lock details before deletion for audit
    locks = await db.room_night_locks.find(
        {"tenant_id": tenant_id, "booking_id": booking_id},
        {"_id": 0, "room_id": 1, "night_date": 1},
    ).to_list(365)

    result = await db.room_night_locks.delete_many({
        "tenant_id": tenant_id,
        "booking_id": booking_id,
    })
    deleted = result.deleted_count

    if deleted > 0:
        room_id = locks[0]["room_id"] if locks else "unknown"
        released_nights = [l["night_date"] for l in locks]

        # INV-6: Audit the release
        await _timeline_event(
            tenant_id=tenant_id,
            stage="lock_released",
            status="success",
            booking_id=booking_id,
            room_id=room_id,
            correlation_id=correlation_id or booking_id,
            metadata={
                "released_nights": released_nights,
                "night_count": deleted,
                "reason": reason,
            },
        )
        logger.info("Released %d night locks for booking %s (reason=%s)", deleted, booking_id, reason)

    return deleted


# ── OOO / OOS / Maintenance Lock Management (INV-5) ─────────────────

async def apply_room_block(tenant_id: str, room_id: str,
                           block_type: str, start_date: str, end_date: str,
                           reason: str = "", actor: str = "system") -> dict[str, Any]:
    """Block a room for OOO/OOS/maintenance by inserting night locks.

    INV-5: Uses the same room_night_locks collection as bookings.
    This ensures the booking engine cannot sell blocked rooms.

    Args:
        block_type: "ooo", "oos", or "maintenance"
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD (exclusive, like check_out)

    Returns:
        {"success": True, "nights_blocked": [...], "conflicts": [...]}
    """
    prefix_map = {"ooo": OOO_PREFIX, "oos": OOS_PREFIX, "maintenance": MAINTENANCE_PREFIX}
    prefix = prefix_map.get(block_type, OOO_PREFIX)
    lock_booking_id = f"{prefix}{room_id}"

    nights = _night_dates(f"{start_date}T00:00:00+00:00", f"{end_date}T00:00:00+00:00")
    if not nights:
        return {"success": False, "error": "No nights in range"}

    blocked = []
    conflicts = []
    now = datetime.now(UTC).isoformat()

    for night in nights:
        lock_doc = {
            "tenant_id": tenant_id,
            "room_id": room_id,
            "night_date": night,
            "booking_id": lock_booking_id,
            "lock_type": block_type,
            "reason": reason,
            "created_by": actor,
            "created_at": now,
        }
        try:
            await db.room_night_locks.insert_one(lock_doc)
            blocked.append(night)
        except DuplicateKeyError:
            existing = await db.room_night_locks.find_one(
                {"tenant_id": tenant_id, "room_id": room_id, "night_date": night},
                {"_id": 0, "booking_id": 1, "lock_type": 1},
            )
            conflicts.append({
                "night": night,
                "held_by": existing.get("booking_id") if existing else "unknown",
                "lock_type": existing.get("lock_type", "unknown") if existing else "unknown",
            })

    # INV-6: Audit
    if blocked:
        await _timeline_event(
            tenant_id=tenant_id,
            stage="ooo_applied" if block_type == "ooo" else f"{block_type}_applied",
            status="success",
            booking_id=lock_booking_id,
            room_id=room_id,
            metadata={
                "block_type": block_type,
                "nights_blocked": blocked,
                "conflicts": conflicts,
                "reason": reason,
                "actor": actor,
            },
        )

    return {
        "success": len(blocked) > 0,
        "nights_blocked": blocked,
        "conflicts": conflicts,
        "block_id": lock_booking_id,
    }


async def release_room_block(tenant_id: str, room_id: str,
                              block_type: str, start_date: str | None = None,
                              end_date: str | None = None,
                              actor: str = "system") -> dict[str, Any]:
    """Remove OOO/OOS/maintenance locks for a room.

    If start_date/end_date provided, only release those nights.
    Otherwise, release all locks for this block type on this room.
    """
    prefix_map = {"ooo": OOO_PREFIX, "oos": OOS_PREFIX, "maintenance": MAINTENANCE_PREFIX}
    prefix = prefix_map.get(block_type, OOO_PREFIX)
    lock_booking_id = f"{prefix}{room_id}"

    query = {
        "tenant_id": tenant_id,
        "room_id": room_id,
        "booking_id": lock_booking_id,
    }

    if start_date and end_date:
        nights = _night_dates(f"{start_date}T00:00:00+00:00", f"{end_date}T00:00:00+00:00")
        if nights:
            query["night_date"] = {"$in": nights}

    # Capture before delete for audit
    locks = await db.room_night_locks.find(query, {"_id": 0, "night_date": 1}).to_list(365)
    released_nights = [l["night_date"] for l in locks]

    result = await db.room_night_locks.delete_many(query)

    if result.deleted_count > 0:
        await _timeline_event(
            tenant_id=tenant_id,
            stage="ooo_released" if block_type == "ooo" else f"{block_type}_released",
            status="success",
            booking_id=lock_booking_id,
            room_id=room_id,
            metadata={
                "block_type": block_type,
                "released_nights": released_nights,
                "actor": actor,
            },
        )

    return {
        "success": True,
        "released_count": result.deleted_count,
        "released_nights": released_nights,
    }


async def get_room_blocks(tenant_id: str, room_id: str | None = None,
                           block_type: str | None = None) -> list[dict[str, Any]]:
    """Get active OOO/OOS/maintenance blocks."""
    query: dict[str, Any] = {"tenant_id": tenant_id}

    if room_id:
        query["room_id"] = room_id

    # Filter by block type prefix
    if block_type:
        prefix_map = {"ooo": OOO_PREFIX, "oos": OOS_PREFIX, "maintenance": MAINTENANCE_PREFIX}
        prefix = prefix_map.get(block_type)
        if prefix:
            query["booking_id"] = {"$regex": f"^{prefix}"}
    else:
        # All operational blocks (not regular bookings)
        query["booking_id"] = {"$regex": f"^({OOO_PREFIX}|{OOS_PREFIX}|{MAINTENANCE_PREFIX})"}

    locks = await db.room_night_locks.find(query, {"_id": 0}).to_list(1000)
    return locks


async def ensure_booking_indexes() -> None:
    """Create indexes for room-night locking and fast overlap detection."""
    indexes_to_create = [
        {
            "collection": "room_night_locks",
            "keys": [("tenant_id", 1), ("room_id", 1), ("night_date", 1)],
            "name": "ux_room_night",
            "unique": True,
        },
        {
            "collection": "room_night_locks",
            "keys": [("tenant_id", 1), ("booking_id", 1)],
            "name": "idx_lock_booking",
            "unique": False,
        },
        {
            "collection": "bookings",
            "keys": [("tenant_id", 1), ("room_id", 1), ("status", 1), ("check_in", 1), ("check_out", 1)],
            "name": "idx_booking_overlap_check",
            "unique": False,
        },
        # idx_booking_tenant_guest: REDUNDANT — Atlas Advisor (Mayıs 2026):
        # `idx_booking_guest_status` (tenant_id, guest_id, status) prefix'i
        # tarafından kapsanıyor (perf_indexes.py). Listeden kaldırıldı.
    ]
    for idx_def in indexes_to_create:
        coll = getattr(db, idx_def["collection"])
        try:
            await coll.create_index(
                idx_def["keys"],
                name=idx_def["name"],
                unique=idx_def.get("unique", False),
                background=True,
            )
        except Exception as e:
            if "IndexOptionsConflict" in str(e) or "already exists" in str(e):
                logger.info("Index %s already exists, skipping", idx_def["name"])
            else:
                logger.warning("Index creation failed for %s: %s", idx_def["name"], e)
    logger.info("Booking indexes ensured (room-night locking + OOO/OOS enabled)")
