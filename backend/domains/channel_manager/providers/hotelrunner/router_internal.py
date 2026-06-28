"""
HotelRunner Router — Internal / Diagnostic Endpoints
=====================================================

Read-only diagnostic endpoints used by the Channel Manager UI:
  - PMS room types dropdown
  - Cached HR rooms (last fetch result, no live API call)
  - Local reservation cache
  - Sync log history
  - In-process API usage stats (no HTTP egress)

Mounted under the main `/api/channel-manager/hotelrunner` prefix by the
parent router.
"""

import time

from fastapi import APIRouter, Depends

from core.database import db
from core.security import get_current_user
from models.schemas import User

from .factory import get_provider

router = APIRouter()

# In-process micro-cache for /usage. The endpoint is polled by the CM dashboard
# every few seconds; rebuilding the provider + reading two timestamps from Mongo
# costs ~1s per call. A 30-second TTL is well below operator perception while
# slashing per-tenant load by ~30x.
_USAGE_CACHE: dict[str, tuple[float, dict]] = {}
_USAGE_TTL_SEC = 30.0


@router.get("/pms-room-types")
async def get_pms_room_types(current_user: User = Depends(get_current_user)):
    """Get distinct PMS room types for mapping dropdown."""
    types = await db.rooms.distinct("room_type", {"tenant_id": current_user.tenant_id})
    return {"room_types": [t for t in types if t]}


@router.get("/cached-rooms")
async def get_cached_hr_rooms(current_user: User = Depends(get_current_user)):
    """Get cached HotelRunner rooms from last fetch."""
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0, "cached_rooms": 1, "rooms_fetched_at": 1},
    )
    if not conn:
        return {"rooms": [], "fetched_at": None}
    return {
        "rooms": conn.get("cached_rooms", []),
        "fetched_at": conn.get("rooms_fetched_at"),
    }


@router.get("/reservations/local")
async def get_local_reservations(
    pms_status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get locally stored HotelRunner reservations."""
    query = {"tenant_id": current_user.tenant_id}
    if pms_status:
        query["pms_status"] = pms_status

    reservations = await db.hotelrunner_reservations.find(query, {"_id": 0, "raw_data": 0}).sort("synced_at", -1).to_list(100)

    return {"reservations": reservations, "count": len(reservations)}


@router.get("/sync-logs")
async def get_sync_logs(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    """Get HotelRunner sync logs."""
    logs = (
        await db.hotelrunner_sync_logs.find(
            {"tenant_id": current_user.tenant_id},
            {"_id": 0},
        )
        .sort("timestamp", -1)
        .to_list(limit)
    )
    return {"logs": logs, "count": len(logs)}


@router.get("/usage")
async def get_api_usage(current_user: User = Depends(get_current_user)):
    """Get HotelRunner API usage statistics (in-process counters, no HTTP egress)."""
    tenant_id = current_user.tenant_id
    now = time.monotonic()
    cached = _USAGE_CACHE.get(tenant_id)
    if cached and (now - cached[0]) < _USAGE_TTL_SEC:
        return cached[1]

    provider, conn = await get_provider(tenant_id)
    stats = provider.get_usage_stats()
    stats["last_sync_at"] = conn.get("last_sync_at")
    stats["connected_at"] = conn.get("connected_at")
    _USAGE_CACHE[tenant_id] = (now, stats)
    return stats
