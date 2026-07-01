"""
frontdesk

Auto-split sub-router (shared imports/classes inlined).
"""

"""
Domain Router: Analytics

Extracted from legacy_routes.py — GM Dashboard, pickup analysis, anomaly detection, revenue analytics.
"""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from core.cache import cached
from core.database import db
from core.security import get_current_user, security
from modules.pms_core.role_permission_service import require_module as require_module_rbac  # v89 DW
from modules.pms_core.role_permission_service import require_role as _require_role

# v67 Bug DD: frontdesk/* endpoint'lerinde RBAC eksikti — HK kullanıcı guest PII (search-bookings),
# müsaitlik (available-rooms), oda atama (assign-room) erişebiliyordu. Front office personeline kısıtla.
_FD_READ = Depends(_require_role("super_admin", "admin", "supervisor", "front_desk"))
_FD_WRITE = Depends(_require_role("super_admin", "admin", "front_desk"))

try:
    from routers.pms_availability import check_room_availability
except Exception:  # pragma: no cover

    async def check_room_availability(*args, **kwargs):
        return {"available": False, "rooms": []}


# --------------------------------------------------------------------------
# GM Dashboard - Pickup Analysis & Anomaly Detection
# --------------------------------------------------------------------------


# rbac-allow: cache-rbac — FO booking search operasyonel

# rbac-allow: cache-rbac — FO available rooms operasyonel


_SYSTEM_HEALTH_CACHE: dict = {"ts": 0.0, "payload": None}
_SYSTEM_HEALTH_TTL = 5.0  # seconds

router = APIRouter(prefix="/api", tags=["analytics"])


# ── POST /frontdesk/assign-room ──
@router.post("/frontdesk/assign-room", dependencies=[_FD_WRITE])
async def assign_room_to_booking(
    assignment_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_rbac("frontdesk")),  # v92 DW
):
    """Assign a specific room to a booking"""
    current_user = await get_current_user(credentials)

    booking_id = assignment_data.get("booking_id")
    room_id = assignment_data.get("room_id")

    # Check if room is available
    room = await db.rooms.find_one({"id": room_id, "tenant_id": current_user.tenant_id})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if room.get("status") not in ["available", "inspected"]:
        raise HTTPException(status_code=400, detail="Room not available")

    # Update booking with room
    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": current_user.tenant_id},
        {"$set": {"room_id": room_id, "room_number": room["room_number"], "room_assigned_at": datetime.now(UTC).isoformat(), "room_assigned_by": current_user.name}},
    )

    # Update room status (v67 architect: tenant_id filter eklendi — cross-tenant write hardening)
    await db.rooms.update_one({"id": room_id, "tenant_id": current_user.tenant_id}, {"$set": {"current_booking_id": booking_id, "status": "reserved"}})

    return {"message": "Room assigned successfully", "booking_id": booking_id, "room_number": room["room_number"]}


# ── GET /frontdesk/search-bookings ──
@router.get("/frontdesk/search-bookings", dependencies=[_FD_READ])
@cached(ttl=180, key_prefix="frontdesk_search_bookings")  # Cache for 3 min
async def search_bookings(
    query: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    current_user=Depends(get_current_user),  # v67 Bug DD2 (architect): cache_manager
    # tenant_id'yi yalnızca current_user/user/tenant arg'larından
    # çıkarır. Eski imza credentials-only olduğundan tenant_id
    # 'global' düşüyor → cross-tenant cache leak. Burada
    # current_user explicit alınarak tenant-scoped key garanti.
):
    """Search bookings by various criteria"""
    search_query = {"tenant_id": current_user.tenant_id}

    # Text search on booking number or guest name — index-serviceable anchored
    # prefix match on the `<field>_lower` companion fields (backed by
    # (tenant_id, <field>_lower) indexes), replacing the un-indexable unanchored
    # case-insensitive regex scan that drove Atlas query-targeting alerts.
    if query:
        from security.search_normalize import prefix_conditions

        conds = prefix_conditions(["booking_number", "guest_name"], query)
        if conds:
            search_query["$or"] = conds

    # Date range filter
    if date_from or date_to:
        date_filter = {}
        if date_from:
            date_filter["$gte"] = date_from
        if date_to:
            date_filter["$lte"] = date_to
        if date_filter:
            search_query["check_in"] = date_filter

    # Status filter
    if status:
        search_query["status"] = status

    bookings = []
    async for booking in db.bookings.find(search_query).sort("created_at", -1).limit(50):
        booking.pop("_id", None)
        bookings.append(booking)

    return {"bookings": bookings, "count": len(bookings)}


# ── GET /frontdesk/available-rooms ──
@router.get("/frontdesk/available-rooms", dependencies=[_FD_READ])
@cached(ttl=120, key_prefix="frontdesk_available_rooms")  # Cache for 2 min
async def get_available_rooms_for_assignment(
    check_in: str | None = None,
    check_out: str | None = None,
    room_type: str | None = None,
    current_user=Depends(get_current_user),  # v67 Bug DD2 (architect): tenant-scoped cache key garanti.
):
    """Get available rooms for a specific date range. Varsayılan: bugün/yarın."""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    if not check_in:
        check_in = _dt.now(_UTC).date().isoformat()
    if not check_out:
        check_out = (_dt.now(_UTC).date() + _td(days=1)).isoformat()
    query = {"tenant_id": current_user.tenant_id, "status": {"$in": ["available", "inspected"]}, "is_active": True}

    if room_type:
        query["room_type"] = room_type

    available_rooms = []
    async for room in db.rooms.find(query).sort("room_number", 1):
        room.pop("_id", None)
        available_rooms.append(room)

    return {"rooms": available_rooms, "count": len(available_rooms), "check_in": check_in, "check_out": check_out}
