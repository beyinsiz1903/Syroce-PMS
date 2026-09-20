"""
PMS Availability & Room Blocks Router — Core inventory management.
Extracted from pms.py (Stage 3d-availability — FINAL extraction).

CRITICAL: This is the most sensitive module in the PMS.
Room blocks directly affect availability calculations.
Any bug here can cause overbooking or inventory drift.

Routes:
  GET   /pms/rooms/availability

Dependencies:
  - AvailabilityReadService (semantic inventory)
  - CreateRoomBlockService (idempotent block creation)
  - ReleaseRoomBlockService (block cancellation)
  - Shadow compare (legacy parity validation)
"""

import asyncio

from fastapi import APIRouter, Depends, Request

from core.database import db
from core.security import get_current_user
from domains.channel_manager.unified_rate_manager_router import (
    get_pricing_settings,
    get_unified_grid,
)
from models.schemas import User
from modules.inventory.services.availability_read_service import AvailabilityReadService
from shared_kernel.shadow_metrics import compare_availability_payloads, run_shadow_compare

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


router = APIRouter(prefix="/api", tags=["pms-availability"])

availability_read_service = AvailabilityReadService()


@router.get("/pms/calendar/rates")
async def get_calendar_rates(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Read-only rate data required by the PMS reservation calendar.

    This deliberately exposes only the two read models needed to render the
    calendar.  Front-desk users must see the same published rates as admins,
    without receiving Channel Manager configuration or write access.
    """
    grid = await get_unified_grid(
        start_date=start_date,
        end_date=end_date,
        current_user=current_user,
    )
    pricing = await get_pricing_settings(current_user=current_user)
    return {"grid": grid.get("grid", []), "rules": pricing.get("rules", {})}


# ═══════════════════════════════════════════════════════════════════
# Availability (read path — queries blocks + bookings)
# ═══════════════════════════════════════════════════════════════════


# rbac-allow: cache-rbac — operasyonel oda müsaitliği tüm rolelere açık (sat-bil + servis koordinasyon)
@router.get("/pms/rooms/availability")
@cached(ttl=120, key_prefix="rooms_availability")  # Cache for 2 min
async def check_room_availability(request: Request, check_in: str | None = None, check_out: str | None = None, room_type: str | None = None, current_user: User = Depends(get_current_user)):
    """Check room availability including blocks"""
    # Tur 3: defaults — today / today+1 when omitted
    from datetime import date as _d
    from datetime import timedelta as _td

    if not check_in:
        check_in = _d.today().isoformat()
    if not check_out:
        check_out = (_d.today() + _td(days=1)).isoformat()
    semantic_response = await availability_read_service.get_availability(
        tenant_id=current_user.tenant_id,
        check_in=check_in,
        check_out=check_out,
        room_type=room_type,
    )
    asyncio.create_task(
        run_shadow_compare(
            endpoint="availability",
            tenant_id=current_user.tenant_id,
            property_id=request.headers.get("x-property-id"),
            correlation_id=request.headers.get("x-correlation-id"),
            semantic_payload=semantic_response,
            legacy_loader=lambda: _legacy_check_room_availability(
                tenant_id=current_user.tenant_id,
                check_in=check_in,
                check_out=check_out,
                room_type=room_type,
            ),
            comparator=compare_availability_payloads,
            entity_id=f"{check_in}:{check_out}:{room_type or '*'}",
        )
    )
    return semantic_response


async def _legacy_check_room_availability(
    tenant_id: str,
    check_in: str,
    check_out: str,
    room_type: str | None = None,
):
    query = {"tenant_id": tenant_id}

    if room_type:
        query["room_type"] = room_type

    rooms = await db.rooms.find(query, {"_id": 0}).to_list(1000)
    bookings = await db.bookings.find(
        {"tenant_id": tenant_id, "status": {"$in": ["confirmed", "checked_in", "guaranteed"]}, "check_in": {"$lt": check_out}, "check_out": {"$gt": check_in}}, {"_id": 0}
    ).to_list(1000)
    blocks = await db.room_blocks.find(
        {"tenant_id": tenant_id, "status": "active", "start_date": {"$lt": check_out}, "$or": [{"end_date": {"$gt": check_in}}, {"end_date": None}]}, {"_id": 0}
    ).to_list(1000)

    available = []
    for room in rooms:
        is_booked = any(b["room_id"] == room["id"] for b in bookings)
        room_blocks = [b for b in blocks if b["room_id"] == room["id"]]
        is_blocked = any(not b.get("allow_sell", False) for b in room_blocks)

        if not is_booked and not is_blocked:
            available.append({**room, "available": True, "occupancy_status": "free"})
        else:
            unavailable_reason = []
            if is_booked:
                unavailable_reason.append("booked")
            if is_blocked:
                block_info = [b for b in room_blocks if not b.get("allow_sell")]
                if block_info:
                    unavailable_reason.append(f"{block_info[0]['type']}")

            available.append({**room, "available": False, "reason": ", ".join(unavailable_reason), "blocks": room_blocks, "occupancy_status": "occupied" if is_booked else "blocked"})

    return available
