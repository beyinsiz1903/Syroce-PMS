"""
Channel Manager Conflict Queue Router (CM-Hardening Turu #1b, May 2026)
========================================================================

Front-desk facing API for resolving OTA-driven `pending_assignment` bookings —
i.e. reservations that were imported from a channel partner (Exely / HotelRunner /
agency portals / B2B / celery import paths) but could not claim a specific
room atomically because the originally requested room (or any room of the
requested type) had a colliding `room_night_locks` entry. They were persisted
to `db.bookings` with `room_id=None` and `allocation_source="pending_assignment"`
so guest data is not lost, and Turu #1a now emits a `db.notifications`
'overbooking_risk' alert at the moment of the conflict.

This router closes the operational loop by giving front-desk:
  - GET  /api/channel-manager/conflict-queue           → list pending bookings
  - POST /api/channel-manager/conflict-queue/{id}/resolve {"room_id": "..."}

The resolve endpoint reuses the same room-night-locking primitives as
`core.atomic_booking.create_booking_atomic` so INV-1 / INV-2 are preserved:
the lock insert is the source of truth for "is this room actually free", not
a calendar query.

Out of scope (sonraki turlarda):
  - Conflict Queue UI (Turu #1c)
  - Auto-suggest free room of same type (analytics)
  - Bulk resolve
"""
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from core.atomic_booking import _night_dates, _timeline_event
from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger("cm.conflict_queue")
router = APIRouter(prefix="/api/channel-manager/conflict-queue", tags=["channel-manager"])

PENDING_QUERY: dict[str, Any] = {
    "allocation_source": "pending_assignment",
    "room_id": None,
    "status": {"$in": ["confirmed", "guaranteed", "pending"]},
}


class ResolveRequest(BaseModel):
    room_id: str = Field(..., min_length=1, description="Target room id to assign")


# ─── Helpers ────────────────────────────────────────────────────────────

async def _serialize_pending_booking(booking: dict[str, Any]) -> dict[str, Any]:
    """Lightweight projection for the queue view."""
    return {
        "id": booking.get("id"),
        "guest_id": booking.get("guest_id"),
        "guest_name": booking.get("guest_name") or "Misafir",
        "check_in": booking.get("check_in"),
        "check_out": booking.get("check_out"),
        "room_type": booking.get("room_type"),
        "channel": booking.get("channel") or booking.get("source"),
        "external_confirmation": booking.get("external_confirmation"),
        "total_amount": booking.get("total_amount"),
        "currency": booking.get("currency"),
        "status": booking.get("status"),
        "adults": booking.get("adults"),
        "children": booking.get("children"),
        "special_requests": booking.get("special_requests"),
        "created_at": booking.get("created_at"),
    }


async def _claim_room_for_pending_booking(
    *, tenant_id: str, booking: dict[str, Any], room_id: str, resolved_by: str,
) -> tuple[bool, dict[str, Any]]:
    """Atomically claim `room_id` for an already-persisted pending booking.

    Reuses the same `room_night_locks` (tenant_id, room_id, night_date) unique
    index that `create_booking_atomic` relies on, so this path inherits INV-1
    (no negative inventory) and INV-2 (full-stay all-or-nothing) guarantees.

    Returns (True, {}) on success.
    Returns (False, {"reason": ..., "conflict_night": ..., "conflicting_booking_id": ...})
    on conflict — caller maps to HTTP 409.
    """
    booking_id = booking["id"]
    check_in = booking.get("check_in") or ""
    check_out = booking.get("check_out") or ""
    if not check_in or not check_out:
        return False, {"reason": "missing_dates"}

    nights = _night_dates(check_in, check_out)
    if not nights:
        return False, {"reason": "zero_night_stay"}

    correlation_id = booking.get("correlation_id") or booking_id
    claimed: list[str] = []
    now_iso = datetime.now(UTC).isoformat()

    for night in nights:
        lock_doc = {
            "tenant_id": tenant_id,
            "room_id": room_id,
            "night_date": night,
            "booking_id": booking_id,
            "lock_type": "booking",
            "created_at": now_iso,
        }
        try:
            await db.room_night_locks.insert_one(lock_doc)
            claimed.append(night)
        except DuplicateKeyError:
            existing = await db.room_night_locks.find_one(
                {"tenant_id": tenant_id, "room_id": room_id, "night_date": night},
                {"_id": 0, "booking_id": 1, "lock_type": 1},
            )
            conflicting_id = existing.get("booking_id") if existing else None

            # Compensation — release any nights we managed to claim
            if claimed:
                await db.room_night_locks.delete_many({
                    "tenant_id": tenant_id,
                    "room_id": room_id,
                    "night_date": {"$in": claimed},
                    "booking_id": booking_id,
                })

            await _timeline_event(
                tenant_id=tenant_id,
                stage="conflict_resolve_failed",
                status="rejected",
                booking_id=booking_id,
                room_id=room_id,
                correlation_id=correlation_id,
                metadata={
                    "conflict_night": night,
                    "conflicting_booking_id": conflicting_id,
                    "claimed_before_conflict": claimed,
                    "resolved_by": resolved_by,
                },
            )
            return False, {
                "reason": "room_not_available",
                "conflict_night": night,
                "conflicting_booking_id": conflicting_id,
            }

    # All nights claimed — promote the booking out of pending_assignment
    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tenant_id},
        {
            "$set": {
                "room_id": room_id,
                "allocation_source": "front_desk_resolve",
                "updated_at": now_iso,
                "updated_by": resolved_by,
            },
        },
    )

    await _timeline_event(
        tenant_id=tenant_id,
        stage="conflict_resolved",
        status="success",
        booking_id=booking_id,
        room_id=room_id,
        correlation_id=correlation_id,
        metadata={"resolved_by": resolved_by, "nights_claimed": nights},
    )

    # Best-effort notification (mirror Turu #1a / cancel-flow pattern)
    try:
        room_doc = await db.rooms.find_one({"id": room_id}, {"_id": 0, "room_number": 1})
        room_label = room_doc.get("room_number", room_id) if room_doc else room_id
        guest_name = booking.get("guest_name") or "Misafir"
        await db.notifications.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "type": "overbooking_resolved",
            "severity": "info",
            "title": f"Pending Booking Atandı - Oda {room_label}",
            "message": (
                f"{guest_name} adlı misafirin {(check_in or '')[:10]} - "
                f"{(check_out or '')[:10]} tarihli OTA rezervasyonu Oda {room_label}'e atandı."
            ),
            "related_entity": "booking",
            "related_id": booking_id,
            "read": False,
            "created_at": now_iso,
            "metadata": {
                "resolved_by": resolved_by,
                "assigned_room_id": room_id,
            },
        })
    except Exception as exc:
        logger.warning("Resolve notification insert failed (booking=%s): %s", booking_id, exc)

    return True, {}


# ─── Endpoints ──────────────────────────────────────────────────────────

@router.get("")
async def list_conflict_queue(
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("edit_booking")),
):
    """List bookings awaiting room assignment (OTA conflict fallbacks)."""
    q = {**PENDING_QUERY, "tenant_id": current_user.tenant_id}
    cursor = db.bookings.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    rows = [await _serialize_pending_booking(b) for b in await cursor.to_list(limit)]
    total = await db.bookings.count_documents(q)
    return {"items": rows, "total": total, "limit": limit, "skip": skip}


@router.get("/count")
async def conflict_queue_count(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("edit_booking")),
):
    """Lightweight count for KPI badges."""
    q = {**PENDING_QUERY, "tenant_id": current_user.tenant_id}
    total = await db.bookings.count_documents(q)
    return {"count": total}


@router.post("/{booking_id}/resolve")
async def resolve_pending_booking(
    booking_id: str,
    payload: ResolveRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("edit_booking")),
):
    """Assign a specific room to a pending_assignment booking, atomically.

    Returns 404 if the booking is not in `pending_assignment` state for this
    tenant (covers: wrong tenant, already resolved, never existed).
    Returns 409 if the requested room is no longer available for any of the
    requested nights — error body carries `conflict_night` and the existing
    `conflicting_booking_id` for operator context.
    """
    tenant_id = current_user.tenant_id
    booking = await db.bookings.find_one(
        {**PENDING_QUERY, "id": booking_id, "tenant_id": tenant_id},
        {"_id": 0},
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Pending booking not found")

    # Validate target room belongs to this tenant
    room = await db.rooms.find_one(
        {"id": payload.room_id, "tenant_id": tenant_id},
        {"_id": 0, "id": 1, "status": 1},
    )
    if not room:
        raise HTTPException(status_code=404, detail="Room not found for this tenant")

    resolved_by = getattr(current_user, "username", None) or getattr(current_user, "id", "front_desk")

    ok, err = await _claim_room_for_pending_booking(
        tenant_id=tenant_id,
        booking=booking,
        room_id=payload.room_id,
        resolved_by=resolved_by,
    )
    if not ok:
        if err.get("reason") == "room_not_available":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "room_not_available",
                    "message": f"Room {payload.room_id} is not free for night {err.get('conflict_night')}",
                    "conflict_night": err.get("conflict_night"),
                    "conflicting_booking_id": err.get("conflicting_booking_id"),
                },
            )
        raise HTTPException(status_code=400, detail={"error": err.get("reason", "resolve_failed")})

    return {
        "ok": True,
        "booking_id": booking_id,
        "room_id": payload.room_id,
        "resolved_by": resolved_by,
    }
