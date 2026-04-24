"""
Booking Hold / TTL Service
===========================
Implements a time-based hold mechanism for pending bookings.

When a booking is in a "pending" or "hold" state (e.g., awaiting payment),
the room-night locks are tagged with an expiry timestamp. A background
sweeper periodically checks for expired holds and releases the inventory
automatically.

This ensures that unconfirmed bookings don't permanently block rooms.

Design:
  - hold_expires_at: UTC ISO timestamp stored on room_night_lock documents
  - Default TTL: 15 minutes (configurable via BOOKING_HOLD_TTL_MINUTES env var)
  - Sweeper runs every 60 seconds as an asyncio background task
  - On expiry: locks deleted, booking status set to "hold_expired", timeline event logged

INV-1: Releasing expired holds ensures sellable inventory is never falsely negative.
INV-6: Every hold creation and expiry is logged to event_timeline.
"""
import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

# v42 round-3: cross-tenant sweeper runs without per-request tenant_context.
# All queries below carry manual `tenant_id` filters, so use the raw system
# DB to bypass STRICT_TENANT_MODE without weakening isolation.
from core.tenant_db import get_system_db as _get_system_db
db = _get_system_db()

logger = logging.getLogger("core.booking_hold")

DEFAULT_HOLD_TTL_MINUTES = 15
SWEEPER_INTERVAL_SECONDS = 60


def _get_hold_ttl_minutes() -> int:
    return int(os.environ.get("BOOKING_HOLD_TTL_MINUTES", DEFAULT_HOLD_TTL_MINUTES))


async def _timeline_event(tenant_id: str, stage: str, status: str,
                          booking_id: str, room_id: str,
                          metadata: dict[str, Any] | None = None):
    """Fire-and-forget timeline event for hold operations."""
    try:
        from controlplane.timeline_writer import get_timeline_writer
        writer = get_timeline_writer()
        await writer.append(
            tenant_id=tenant_id,
            correlation_id=booking_id or "unknown",
            entity_type="booking",
            entity_id=booking_id or "",
            stage=stage,
            status=status,
            source="booking_hold_service",
            metadata=metadata or {},
        )
    except Exception as exc:
        logger.debug("Timeline write failed for %s: %s", stage, exc)


async def create_booking_hold(
    tenant_id: str,
    booking_id: str,
    room_id: str,
    check_in: str,
    check_out: str,
    ttl_minutes: int | None = None,
) -> dict[str, Any]:
    """
    Create a booking hold by claiming room-night locks with an expiry.

    This is used when a booking is created in "pending" status (e.g., awaiting
    payment confirmation). The locks will be automatically released if the
    booking is not confirmed within the TTL.

    Returns:
        {"success": True, "hold_expires_at": "...", "nights_held": [...]}
    """
    from core.atomic_booking import _night_dates

    ttl = ttl_minutes or _get_hold_ttl_minutes()
    expires_at = (datetime.now(UTC) + timedelta(minutes=ttl)).isoformat()
    nights = _night_dates(check_in, check_out)

    if not nights:
        return {"success": False, "error": "No nights in range"}

    from pymongo.errors import DuplicateKeyError

    claimed = []
    now = datetime.now(UTC).isoformat()

    for night in nights:
        lock_doc = {
            "tenant_id": tenant_id,
            "room_id": room_id,
            "night_date": night,
            "booking_id": booking_id,
            "lock_type": "hold",
            "hold_expires_at": expires_at,
            "created_at": now,
        }
        try:
            await db.room_night_locks.insert_one(lock_doc)
            claimed.append(night)
        except DuplicateKeyError:
            # Conflict — rollback all claimed
            if claimed:
                await db.room_night_locks.delete_many({
                    "tenant_id": tenant_id,
                    "room_id": room_id,
                    "night_date": {"$in": claimed},
                    "booking_id": booking_id,
                })
            return {
                "success": False,
                "error": f"Room {room_id} not available for {night}",
                "conflict_night": night,
            }

    # INV-6: Audit
    await _timeline_event(
        tenant_id=tenant_id,
        stage="hold_created",
        status="success",
        booking_id=booking_id,
        room_id=room_id,
        metadata={
            "nights_held": claimed,
            "hold_expires_at": expires_at,
            "ttl_minutes": ttl,
            "check_in": check_in,
            "check_out": check_out,
        },
    )

    logger.info(
        "Hold created: booking=%s room=%s expires=%s (%d nights)",
        booking_id, room_id, expires_at, len(claimed),
    )

    return {
        "success": True,
        "hold_expires_at": expires_at,
        "nights_held": claimed,
        "ttl_minutes": ttl,
    }


async def confirm_hold(tenant_id: str, booking_id: str) -> dict[str, Any]:
    """
    Convert a hold into a confirmed booking lock by removing the expiry.

    Called when payment is confirmed or the booking transitions to "confirmed".
    """
    result = await db.room_night_locks.update_many(
        {
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "lock_type": "hold",
        },
        {
            "$set": {"lock_type": "booking"},
            "$unset": {"hold_expires_at": ""},
        },
    )

    if result.modified_count > 0:
        await _timeline_event(
            tenant_id=tenant_id,
            stage="hold_confirmed",
            status="success",
            booking_id=booking_id,
            room_id="*",
            metadata={
                "nights_confirmed": result.modified_count,
            },
        )
        logger.info("Hold confirmed: booking=%s (%d locks upgraded)", booking_id, result.modified_count)

    return {
        "success": True,
        "confirmed_count": result.modified_count,
    }


async def release_hold(tenant_id: str, booking_id: str, reason: str = "manual") -> dict[str, Any]:
    """Manually release a hold (e.g., user cancelled before payment)."""
    locks = await db.room_night_locks.find(
        {"tenant_id": tenant_id, "booking_id": booking_id, "lock_type": "hold"},
        {"_id": 0, "night_date": 1, "room_id": 1},
    ).to_list(365)

    result = await db.room_night_locks.delete_many({
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "lock_type": "hold",
    })

    if result.deleted_count > 0:
        room_id = locks[0]["room_id"] if locks else "unknown"
        released_nights = [l["night_date"] for l in locks]

        await _timeline_event(
            tenant_id=tenant_id,
            stage="hold_released",
            status="success",
            booking_id=booking_id,
            room_id=room_id,
            metadata={
                "released_nights": released_nights,
                "reason": reason,
            },
        )
        logger.info("Hold released: booking=%s (%d nights, reason=%s)", booking_id, result.deleted_count, reason)

    return {
        "success": True,
        "released_count": result.deleted_count,
    }


async def sweep_expired_holds() -> dict[str, Any]:
    """
    Find and release all expired holds across all tenants.

    This is the core of the TTL mechanism. Called periodically by the
    background sweeper task.

    Returns summary of what was cleaned up.
    """
    now = datetime.now(UTC).isoformat()

    # Find all expired hold locks
    expired_locks = await db.room_night_locks.find(
        {
            "lock_type": "hold",
            "hold_expires_at": {"$lte": now},
        },
        {"_id": 0, "tenant_id": 1, "room_id": 1, "booking_id": 1, "night_date": 1},
    ).to_list(10000)

    if not expired_locks:
        return {"expired_count": 0, "bookings_affected": 0}

    # Group by booking_id for batch processing
    bookings_map: dict[str, list] = {}
    for lock in expired_locks:
        bid = lock["booking_id"]
        if bid not in bookings_map:
            bookings_map[bid] = []
        bookings_map[bid].append(lock)

    total_released = 0
    bookings_expired = []

    for booking_id, locks in bookings_map.items():
        tenant_id = locks[0]["tenant_id"]
        room_id = locks[0]["room_id"]
        nights = [l["night_date"] for l in locks]

        # Delete the expired locks
        del_result = await db.room_night_locks.delete_many({
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "lock_type": "hold",
            "hold_expires_at": {"$lte": now},
        })
        total_released += del_result.deleted_count

        # Update booking status to hold_expired
        await db.bookings.update_one(
            {"id": booking_id, "tenant_id": tenant_id, "status": {"$in": ["pending", "hold"]}},
            {"$set": {
                "status": "hold_expired",
                "hold_expired_at": now,
            }},
        )

        # INV-6: Audit
        await _timeline_event(
            tenant_id=tenant_id,
            stage="hold_expired",
            status="expired",
            booking_id=booking_id,
            room_id=room_id,
            metadata={
                "released_nights": nights,
                "night_count": len(nights),
                "reason": "ttl_expired",
            },
        )

        bookings_expired.append(booking_id)
        logger.info(
            "Hold expired: booking=%s room=%s (%d nights released)",
            booking_id, room_id, del_result.deleted_count,
        )

    return {
        "expired_count": total_released,
        "bookings_affected": len(bookings_expired),
        "booking_ids": bookings_expired,
    }


# ── Background Sweeper Task ─────────────────────────────────────────

_sweeper_task: asyncio.Task | None = None


async def _sweeper_loop():
    """Background loop that periodically sweeps expired holds."""
    logger.info("Booking hold sweeper started (interval=%ds)", SWEEPER_INTERVAL_SECONDS)
    while True:
        try:
            await asyncio.sleep(SWEEPER_INTERVAL_SECONDS)
            result = await sweep_expired_holds()
            if result["expired_count"] > 0:
                logger.info(
                    "Sweeper: released %d expired holds (%d bookings)",
                    result["expired_count"], result["bookings_affected"],
                )
        except asyncio.CancelledError:
            logger.info("Booking hold sweeper stopped")
            break
        except Exception as exc:
            logger.error("Sweeper error: %s", exc)


def start_hold_sweeper():
    """Start the background hold sweeper task."""
    global _sweeper_task
    if _sweeper_task is None or _sweeper_task.done():
        _sweeper_task = asyncio.create_task(_sweeper_loop())
        logger.info("Booking hold sweeper task created")


def stop_hold_sweeper():
    """Stop the background hold sweeper task."""
    global _sweeper_task
    if _sweeper_task and not _sweeper_task.done():
        _sweeper_task.cancel()
        _sweeper_task = None
