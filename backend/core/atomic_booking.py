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

# F8N (2026-05) — Statuses that do NOT participate in oversell conflict checks
# (a cancelled / no-show / checked-out booking releases its room nights and
# must not block a fresh reservation on the same room/dates).
TERMINAL_BOOKING_STATUSES = ("cancelled", "no_show", "checked_out")

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


async def _find_overlapping_active_booking(
    *,
    tenant_id: str,
    room_id: str,
    check_in: str,
    check_out: str,
    exclude_booking_id: str | None = None,
) -> dict[str, Any] | None:
    """F8N — Return one active booking on (tenant_id, room_id) whose date
    window overlaps [check_in, check_out), or None.

    Overlap rule (half-open intervals, mirrors `_night_dates`):
        existing.check_in < new.check_out  AND  existing.check_out > new.check_in

    Terminal-state bookings (cancelled / no_show / checked_out) are excluded.
    """
    query: dict[str, Any] = {
        "tenant_id": tenant_id,
        "room_id": room_id,
        "status": {"$nin": list(TERMINAL_BOOKING_STATUSES)},
        "check_in": {"$lt": check_out},
        "check_out": {"$gt": check_in},
    }
    if exclude_booking_id:
        query["id"] = {"$ne": exclude_booking_id}
    return await db.bookings.find_one(
        query, {"_id": 0, "id": 1, "room_id": 1, "check_in": 1, "check_out": 1, "status": 1}
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

    # F8N (2026-05) — Defense-in-depth oversell guard.
    # The room-night-lock unique index (`ux_room_night`) is the PRIMARY atomic
    # guarantee. This bookings-level overlap query is a safety net for cases
    # where the lock table has stale/missing rows (legacy data, seed inserts
    # that bypassed `create_booking_atomic`, or a partially-deployed unique
    # index). It runs BEFORE we claim any locks so we fail fast without
    # creating compensation churn. The query is tenant + room scoped and
    # excludes terminal-state bookings.
    if room_id and check_in and check_out:
        overlap = await _find_overlapping_active_booking(
            tenant_id=tenant_id,
            room_id=room_id,
            check_in=check_in,
            check_out=check_out,
            exclude_booking_id=booking_id,
        )
        if overlap is not None:
            conflict_msg = (
                f"Room {room_id} already booked for {check_in}..{check_out} "
                f"by {overlap.get('id')}"
            )
            await _emit_overbooking_alert(
                tenant_id=tenant_id,
                booking_id=booking_id,
                room_id=room_id,
                conflict_type="booking",
                conflict_msg=conflict_msg,
                conflict_night=str(check_in)[:10],
                conflicting_booking_id=overlap.get("id"),
                correlation_id=correlation_id,
            )
            raise BookingConflictError(
                conflict_msg,
                conflicting_booking_id=overlap.get("id"),
                conflict_type="booking",
                conflicting_nights=[],
            )

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


async def scan_room_night_lock_duplicates(limit: int = 100) -> list[dict[str, Any]]:
    """F8N — Detect duplicate (tenant_id, room_id, night_date) groups in
    `room_night_locks`. Returns up to `limit` duplicate groups for operator
    reporting. Per task guard rules these rows are NEVER deleted by the
    bootstrap pipeline — only logged so operators can adjudicate.
    """
    try:
        pipeline = [
            {"$group": {
                "_id": {"tenant_id": "$tenant_id", "room_id": "$room_id", "night_date": "$night_date"},
                "count": {"$sum": 1},
                "booking_ids": {"$addToSet": "$booking_id"},
            }},
            {"$match": {"count": {"$gt": 1}}},
            {"$limit": limit},
        ]
        return await db.room_night_locks.aggregate(pipeline, allowDiskUse=True).to_list(limit)
    except Exception as exc:
        logger.warning("F8N duplicate scan failed: %s", exc)
        return []


async def _classify_lock_owner(tenant_id: str, booking_id: str) -> dict[str, Any]:
    """Classify a lock owner (booking_id) for the auto-resolver.

    Returns dict with keys:
      kind:    "block" | "active" | "terminal" | "missing" | "unknown"
      status:  bookings.status if applicable
      created_at, check_in, check_out: when available
    """
    if not booking_id:
        return {"kind": "missing", "status": None, "created_at": None}
    if booking_id.startswith((OOO_PREFIX, OOS_PREFIX, MAINTENANCE_PREFIX)):
        return {"kind": "block", "status": "block", "created_at": None}
    try:
        doc = await db.bookings.find_one(
            {"tenant_id": tenant_id, "id": booking_id},
            {"_id": 0, "id": 1, "status": 1, "created_at": 1,
             "check_in": 1, "check_out": 1},
        )
    except Exception as exc:
        logger.warning("F8N classify lookup failed for %s: %s", booking_id, exc)
        return {"kind": "unknown", "status": None, "created_at": None}
    if not doc:
        return {"kind": "missing", "status": None, "created_at": None}
    status_val = (doc.get("status") or "").lower()
    if status_val in TERMINAL_BOOKING_STATUSES:
        kind = "terminal"
    elif status_val in ACTIVE_BOOKING_STATUSES:
        kind = "active"
    else:
        # Anything else (pending_assignment, on_hold, etc.) — treat as
        # non-terminal so we never auto-retire it.
        kind = "active"
    return {
        "kind": kind,
        "status": status_val,
        "created_at": doc.get("created_at"),
        "check_in": doc.get("check_in"),
        "check_out": doc.get("check_out"),
    }


async def list_room_night_lock_duplicate_groups(
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return duplicate (tenant, room, night) groups annotated with each
    owner's classification and an auto-resolution recommendation.

    Recommendation rules (read-only; never mutates):
      * Exactly one owner classified as `block` or `active`, all others
        `terminal` or `missing` → `auto_safe`. Keeper is the active/block
        row; the others are listed for retire.
      * Two or more `active`/`block` owners → `manual_required` (operator
        must adjudicate which booking to cancel).
      * All owners `terminal`/`missing` → `auto_safe_all_inactive`. Keeper
        is the most recently created lock so the audit trail is preserved;
        the remainder are listed for retire.
      * `unknown` (lookup error) anywhere → `manual_required` to avoid
        deleting data we could not classify.
    """
    groups = await scan_room_night_lock_duplicates(limit=limit)
    annotated: list[dict[str, Any]] = []
    for grp in groups:
        gid = grp.get("_id", {}) or {}
        tenant_id = gid.get("tenant_id")
        room_id = gid.get("room_id")
        night = gid.get("night_date")
        booking_ids = grp.get("booking_ids") or []

        try:
            owner_locks = await db.room_night_locks.find(
                {"tenant_id": tenant_id, "room_id": room_id, "night_date": night},
                {"_id": 0, "booking_id": 1, "lock_type": 1, "created_at": 1},
            ).to_list(100)
        except Exception as exc:
            logger.warning("F8N owner-lock fetch failed (%s/%s/%s): %s",
                           tenant_id, room_id, night, exc)
            owner_locks = []

        owners: list[dict[str, Any]] = []
        for lk in owner_locks:
            bid = lk.get("booking_id")
            cls = await _classify_lock_owner(tenant_id, bid)
            owners.append({
                "booking_id": bid,
                "lock_type": lk.get("lock_type"),
                "lock_created_at": lk.get("created_at"),
                **cls,
            })

        keepers = [o for o in owners if o["kind"] in ("block", "active")]
        unknowns = [o for o in owners if o["kind"] == "unknown"]
        inactive = [o for o in owners if o["kind"] in ("terminal", "missing")]

        if unknowns:
            recommendation = "manual_required"
            reason = "owner classification failed for one or more locks"
            keep_booking_id = None
            retire_booking_ids: list[str] = []
        elif len(keepers) == 1 and inactive:
            recommendation = "auto_safe"
            reason = "single active keeper, remainder terminal/missing"
            keep_booking_id = keepers[0]["booking_id"]
            retire_booking_ids = [o["booking_id"] for o in inactive]
        elif len(keepers) >= 2:
            recommendation = "manual_required"
            reason = "two or more active bookings on the same night"
            keep_booking_id = None
            retire_booking_ids = []
        elif not keepers and inactive:
            inactive_sorted = sorted(
                inactive,
                key=lambda o: (o.get("lock_created_at") or "", o.get("created_at") or ""),
                reverse=True,
            )
            recommendation = "auto_safe_all_inactive"
            reason = "all owners terminal/missing; keep most recent for audit"
            keep_booking_id = inactive_sorted[0]["booking_id"]
            retire_booking_ids = [o["booking_id"] for o in inactive_sorted[1:]]
        else:
            recommendation = "manual_required"
            reason = "no resolvable pattern"
            keep_booking_id = None
            retire_booking_ids = []

        annotated.append({
            "tenant_id": tenant_id,
            "room_id": room_id,
            "night_date": night,
            "count": grp.get("count"),
            "booking_ids": booking_ids,
            "owners": owners,
            "recommendation": recommendation,
            "reason": reason,
            "keep_booking_id": keep_booking_id,
            "retire_booking_ids": retire_booking_ids,
        })
    return annotated


async def resolve_room_night_lock_duplicates(
    *,
    apply: bool = False,
    limit: int = 100,
    actor_id: str = "system",
    actor_name: str = "system",
    actor_role: str = "super_admin",
) -> dict[str, Any]:
    """Auto-resolve duplicate room-night locks when the resolution is safe.

    Safe groups are the ones flagged `auto_safe` or `auto_safe_all_inactive`
    by `list_room_night_lock_duplicate_groups`. `manual_required` groups are
    always skipped (returned in the response so operators can review).

    When `apply=False` this returns the plan only — nothing is deleted.

    When `apply=True`:
      * Deletes only the lock rows whose `booking_id` is in
        `retire_booking_ids` for safe groups (and only on the matching
        tenant/room/night triple — never wider).
      * Re-checks the post-delete row count for that triple; if more than
        one row remains (concurrent insert race) the action is rolled back
        for that group and the group is flagged `skipped_post_check`.
      * Writes an `audit_logs` row per resolved group with
        `action=AUTO_RESOLVE_RNL_DUPLICATE`.
      * Writes a timeline event (`lock_duplicate_resolved`).
    """
    plan = await list_room_night_lock_duplicate_groups(limit=limit)
    now_iso = datetime.now(UTC).isoformat()
    resolved: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for grp in plan:
        if grp["recommendation"] not in ("auto_safe", "auto_safe_all_inactive"):
            skipped.append({**grp, "skip_reason": grp["reason"]})
            continue
        if not grp["retire_booking_ids"]:
            skipped.append({**grp, "skip_reason": "nothing to retire"})
            continue
        if not apply:
            resolved.append({**grp, "applied": False})
            continue

        tenant_id = grp["tenant_id"]
        room_id = grp["room_id"]
        night = grp["night_date"]

        try:
            del_res = await db.room_night_locks.delete_many({
                "tenant_id": tenant_id,
                "room_id": room_id,
                "night_date": night,
                "booking_id": {"$in": grp["retire_booking_ids"]},
            })
            remaining = await db.room_night_locks.count_documents({
                "tenant_id": tenant_id,
                "room_id": room_id,
                "night_date": night,
            })
        except Exception as exc:
            logger.warning(
                "F8N auto-resolve delete failed (%s/%s/%s): %s",
                tenant_id, room_id, night, exc,
            )
            skipped.append({**grp, "skip_reason": f"delete error: {exc}"})
            continue

        if remaining != 1:
            logger.warning(
                "F8N auto-resolve post-check: %s rows remain on %s/%s/%s — "
                "skipping audit (expected 1)",
                remaining, tenant_id, room_id, night,
            )
            skipped.append({**grp, "skip_reason": f"post_check rows={remaining}"})
            continue

        try:
            await db.audit_logs.insert_one({
                "id": f"rnl-resolve-{tenant_id}-{room_id}-{night}-{int(datetime.now(UTC).timestamp())}",
                "tenant_id": tenant_id,
                "user_id": actor_id,
                "user_name": actor_name,
                "user_role": actor_role,
                "action": "AUTO_RESOLVE_RNL_DUPLICATE",
                "entity_type": "room_night_lock",
                "entity_id": f"{tenant_id}:{room_id}:{night}",
                "changes": {
                    "recommendation": grp["recommendation"],
                    "reason": grp["reason"],
                    "keep_booking_id": grp["keep_booking_id"],
                    "retire_booking_ids": grp["retire_booking_ids"],
                    "owners": grp["owners"],
                    "deleted_count": del_res.deleted_count,
                },
                "timestamp": now_iso,
            })
        except Exception as exc:
            logger.warning("F8N auto-resolve audit_log insert failed: %s", exc)

        await _timeline_event(
            tenant_id=tenant_id,
            stage="lock_duplicate_resolved",
            status="success",
            booking_id=grp["keep_booking_id"] or "",
            room_id=room_id or "",
            metadata={
                "night_date": night,
                "recommendation": grp["recommendation"],
                "keep_booking_id": grp["keep_booking_id"],
                "retired_booking_ids": grp["retire_booking_ids"],
                "deleted_count": del_res.deleted_count,
                "actor_id": actor_id,
            },
        )

        resolved.append({
            **grp,
            "applied": True,
            "deleted_count": del_res.deleted_count,
        })

    return {
        "applied": apply,
        "scanned": len(plan),
        "resolved_count": len(resolved),
        "skipped_count": len(skipped),
        "resolved": resolved,
        "skipped": skipped,
    }


async def manual_resolve_room_night_lock_duplicate(
    *,
    tenant_id: str,
    room_id: str,
    night_date: str,
    keep_booking_id: str,
    retire_booking_ids: list[str],
    actor_id: str = "system",
    actor_name: str = "system",
    actor_role: str = "super_admin",
) -> dict[str, Any]:
    """Operator-driven resolve for a single duplicate room-night-lock group.

    Counterpart to the safe-only `resolve_room_night_lock_duplicates` flow,
    intended for the groups flagged `manual_required` (two or more active
    bookings on the same night, or owner classification failures).

    Guards:
      * `keep_booking_id` and every entry in `retire_booking_ids` must
        currently own a lock row on the exact (tenant, room, night) triple.
      * `retire_booking_ids` must not contain the keeper.
      * Delete is scoped strictly to (tenant_id, room_id, night_date,
        booking_id $in retire_booking_ids) — never wider.
      * Post-delete the remaining lock count for the triple must be == 1
        (the keeper). Anything else → no audit/timeline + skip.

    Writes an `audit_logs` row (`MANUAL_RESOLVE_RNL_DUPLICATE`) and a
    timeline event (`lock_duplicate_resolved`, status=manual) on success.
    """
    if not (tenant_id and room_id and night_date and keep_booking_id):
        return {
            "applied": False,
            "skip_reason": "tenant_id/room_id/night_date/keep_booking_id required",
        }
    retire_ids = [b for b in (retire_booking_ids or []) if b]
    if not retire_ids:
        return {"applied": False, "skip_reason": "retire_booking_ids empty"}
    if keep_booking_id in retire_ids:
        return {
            "applied": False,
            "skip_reason": "keep_booking_id cannot also be retired",
        }

    try:
        existing_locks = await db.room_night_locks.find(
            {"tenant_id": tenant_id, "room_id": room_id, "night_date": night_date},
            {"_id": 0, "booking_id": 1, "lock_type": 1, "created_at": 1},
        ).to_list(100)
    except Exception as exc:
        logger.warning(
            "F8N manual-resolve lock fetch failed (%s/%s/%s): %s",
            tenant_id, room_id, night_date, exc,
        )
        return {"applied": False, "skip_reason": f"lock fetch error: {exc}"}

    existing_booking_ids = {lk.get("booking_id") for lk in existing_locks}
    if keep_booking_id not in existing_booking_ids:
        return {
            "applied": False,
            "skip_reason": "keep_booking_id has no lock on this triple",
        }
    missing = [b for b in retire_ids if b not in existing_booking_ids]
    if missing:
        return {
            "applied": False,
            "skip_reason": f"retire_booking_ids not present on triple: {missing}",
        }

    try:
        del_res = await db.room_night_locks.delete_many({
            "tenant_id": tenant_id,
            "room_id": room_id,
            "night_date": night_date,
            "booking_id": {"$in": retire_ids},
        })
        remaining = await db.room_night_locks.count_documents({
            "tenant_id": tenant_id,
            "room_id": room_id,
            "night_date": night_date,
        })
    except Exception as exc:
        logger.warning(
            "F8N manual-resolve delete failed (%s/%s/%s): %s",
            tenant_id, room_id, night_date, exc,
        )
        return {"applied": False, "skip_reason": f"delete error: {exc}"}

    if remaining != 1:
        logger.warning(
            "F8N manual-resolve post-check: %s rows remain on %s/%s/%s — "
            "expected 1; skipping audit",
            remaining, tenant_id, room_id, night_date,
        )
        return {
            "applied": False,
            "deleted_count": del_res.deleted_count,
            "skip_reason": f"post_check rows={remaining}",
        }

    now_iso = datetime.now(UTC).isoformat()
    try:
        await db.audit_logs.insert_one({
            "id": (
                f"rnl-manual-{tenant_id}-{room_id}-{night_date}-"
                f"{int(datetime.now(UTC).timestamp())}"
            ),
            "tenant_id": tenant_id,
            "user_id": actor_id,
            "user_name": actor_name,
            "user_role": actor_role,
            "action": "MANUAL_RESOLVE_RNL_DUPLICATE",
            "entity_type": "room_night_lock",
            "entity_id": f"{tenant_id}:{room_id}:{night_date}",
            "changes": {
                "keep_booking_id": keep_booking_id,
                "retire_booking_ids": retire_ids,
                "owners_before": existing_locks,
                "deleted_count": del_res.deleted_count,
                "decision": "manual",
            },
            "timestamp": now_iso,
        })
    except Exception as exc:
        logger.warning("F8N manual-resolve audit_log insert failed: %s", exc)

    await _timeline_event(
        tenant_id=tenant_id,
        stage="lock_duplicate_resolved",
        status="manual",
        booking_id=keep_booking_id,
        room_id=room_id,
        metadata={
            "night_date": night_date,
            "decision": "manual",
            "keep_booking_id": keep_booking_id,
            "retired_booking_ids": retire_ids,
            "deleted_count": del_res.deleted_count,
            "actor_id": actor_id,
        },
    )

    return {
        "applied": True,
        "deleted_count": del_res.deleted_count,
        "remaining": remaining,
        "tenant_id": tenant_id,
        "room_id": room_id,
        "night_date": night_date,
        "keep_booking_id": keep_booking_id,
        "retire_booking_ids": retire_ids,
    }


async def ensure_booking_indexes() -> None:
    """Create indexes for room-night locking and fast overlap detection.

    F8N (2026-05) — Hardened:
      * Pre-scans `room_night_locks` for duplicate (tenant, room, night)
        groups and logs them at WARNING (operators must adjudicate; rows
        are never deleted automatically per task guard rules).
      * Drops any non-unique pre-existing `ux_room_night` (e.g. an older
        deployment where the index was created without `unique=True`) so
        the unique index can be re-created without `IndexOptionsConflict`.
      * After creation, verifies the unique index actually exists with the
        expected key set + `unique=True` flag. If verification fails the
        function logs CRITICAL — production deployments rely on this index
        as their primary oversell barrier.
    """
    # Pre-flight duplicate scan (informational; never mutates).
    dupes = await scan_room_night_lock_duplicates(limit=50)
    if dupes:
        logger.warning(
            "F8N: %d duplicate (tenant,room,night_date) groups in room_night_locks; "
            "unique index creation may fail until operator resolves. Sample: %s",
            len(dupes), dupes[:5],
        )

    # F8N: drop existing ux_room_night if it isn't unique — name collision
    # with create_index() blocks recreating it as unique otherwise.
    try:
        info = await db.room_night_locks.index_information()
        existing = info.get("ux_room_night")
        if existing is not None and not existing.get("unique"):
            logger.warning("F8N: dropping non-unique ux_room_night to re-create as UNIQUE")
            await db.room_night_locks.drop_index("ux_room_night")
    except Exception as exc:
        logger.warning("F8N: ux_room_night pre-drop probe failed: %s", exc)

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

    # F8N — Post-create verification: the unique room-night index IS the
    # oversell barrier. If it is missing/non-unique after this phase, log
    # CRITICAL so monitoring can alert. We deliberately do not raise — the
    # bookings-level defense-in-depth overlap check in `create_booking_atomic`
    # still protects new inserts; the CRITICAL log is the operator signal.
    try:
        info = await db.room_night_locks.index_information()
        ux = info.get("ux_room_night")
        if ux is None or not ux.get("unique"):
            logger.critical(
                "F8N: ux_room_night UNIQUE index missing on room_night_locks; "
                "primary oversell barrier degraded. defense-in-depth bookings "
                "overlap check is the only remaining guard. info=%s", ux,
            )
    except Exception as exc:
        logger.warning("F8N: ux_room_night post-create verification failed: %s", exc)

    logger.info("Booking indexes ensured (room-night locking + OOO/OOS enabled)")
