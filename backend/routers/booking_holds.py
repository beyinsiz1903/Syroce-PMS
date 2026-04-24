"""
Booking Holds Router — TTL/Hold Management API
================================================
Endpoints for managing booking holds with automatic TTL-based expiry.

  POST /api/booking-holds          — Create a hold on room nights
  POST /api/booking-holds/confirm  — Convert hold to confirmed booking
  DELETE /api/booking-holds         — Manually release a hold
  GET /api/booking-holds/status     — Get hold status for a booking
  POST /api/booking-holds/sweep     — Manually trigger expired hold cleanup
"""
import logging
from modules.pms_core.role_permission_service import require_module as require_module_v97  # v97 DW

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.security import get_current_user

logger = logging.getLogger("routers.booking_holds")

router = APIRouter(prefix="/api/booking-holds", tags=["Booking Holds"])


class HoldCreateRequest(BaseModel):
    booking_id: str
    room_id: str
    check_in: str
    check_out: str
    ttl_minutes: int | None = None


class HoldConfirmRequest(BaseModel):
    booking_id: str


class HoldReleaseRequest(BaseModel):
    booking_id: str
    reason: str = "manual"


@router.post("")
async def create_hold(req: HoldCreateRequest, current_user=Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Create a temporary hold on room nights with automatic TTL expiry."""
    from core.booking_hold_service import create_booking_hold
    result = await create_booking_hold(
        tenant_id=current_user.tenant_id,
        booking_id=req.booking_id,
        room_id=req.room_id,
        check_in=req.check_in,
        check_out=req.check_out,
        ttl_minutes=req.ttl_minutes,
    )
    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result.get("error", "Hold failed"))
    return result


@router.post("/confirm")
async def confirm_hold(req: HoldConfirmRequest, current_user=Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Convert a hold to a confirmed booking lock (remove TTL)."""
    from core.booking_hold_service import confirm_hold as do_confirm
    result = await do_confirm(
        tenant_id=current_user.tenant_id,
        booking_id=req.booking_id,
    )
    return result


@router.delete("")
async def release_hold_endpoint(
    booking_id: str,
    reason: str = "manual",
    current_user=Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Manually release a booking hold before TTL expiry."""
    from core.booking_hold_service import release_hold
    result = await release_hold(
        tenant_id=current_user.tenant_id,
        booking_id=booking_id,
        reason=reason,
    )
    return result


@router.get("/status")
async def get_hold_status(booking_id: str, current_user=Depends(get_current_user)):
    """Get hold status for a booking."""
    from core.database import db
    locks = await db.room_night_locks.find(
        {
            "tenant_id": current_user.tenant_id,
            "booking_id": booking_id,
            "lock_type": "hold",
        },
        {"_id": 0, "night_date": 1, "hold_expires_at": 1, "room_id": 1},
    ).to_list(365)

    if not locks:
        return {"has_hold": False, "booking_id": booking_id}

    return {
        "has_hold": True,
        "booking_id": booking_id,
        "room_id": locks[0].get("room_id"),
        "nights_held": [l["night_date"] for l in locks],
        "hold_expires_at": locks[0].get("hold_expires_at"),
        "night_count": len(locks),
    }


@router.post("/sweep")
async def trigger_sweep(current_user=Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Manually trigger a sweep of expired booking holds (admin action)."""
    from core.booking_hold_service import sweep_expired_holds
    result = await sweep_expired_holds()
    return result
