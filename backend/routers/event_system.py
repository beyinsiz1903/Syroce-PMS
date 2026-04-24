"""
Real-Time Operational Event System Router - Event bus, live feed, notifications.
All endpoints under /api/event-system/
"""

from fastapi import APIRouter, Depends, HTTPException
from modules.pms_core.role_permission_service import require_op  # v98 DW
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User
from modules.event_system.event_bus import EventBus

router = APIRouter(prefix="/api/event-system", tags=["event-system"])
event_bus = EventBus()


class PublishEventRequest(BaseModel):
    event_type: str
    payload: dict
    property_id: str | None = None


class MarkReadRequest(BaseModel):
    event_ids: list[str]


class AcknowledgeRequest(BaseModel):
    event_id: str
    note: str | None = None


# ── EVENT PUBLISHING ──

@router.post("/publish")
async def api_publish_event(req: PublishEventRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """Publish an operational event."""
    result = await event_bus.publish(
        current_user.tenant_id, req.event_type, req.payload, current_user.id, req.property_id
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


# ── LIVE FEED ──

@router.get("/live-feed")
async def api_live_feed(
    limit: int = 50,
    event_type: str | None = None,
    priority: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get live operational activity feed."""
    return await event_bus.get_live_feed(current_user.tenant_id, limit, event_type, priority)


@router.get("/unread-count")
async def api_unread_count(role: str | None = None, current_user: User = Depends(get_current_user)):
    """Get unread event count."""
    user_role = role or current_user.role
    return await event_bus.get_unread_count(current_user.tenant_id, user_role)


@router.post("/mark-read")
async def api_mark_read(req: MarkReadRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """Mark events as read."""
    return await event_bus.mark_read(current_user.tenant_id, req.event_ids)


@router.post("/acknowledge")
async def api_acknowledge(req: AcknowledgeRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """Acknowledge a critical event."""
    result = await event_bus.acknowledge_event(
        current_user.tenant_id, req.event_id, current_user.id, req.note
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


# ── STATISTICS ──

@router.get("/stats")
async def api_event_stats(hours: int = 24, current_user: User = Depends(get_current_user)):
    """Get event statistics for the last N hours."""
    return await event_bus.get_event_stats(current_user.tenant_id, hours)


# ── OPERATIONAL BOARDS ──

@router.get("/front-desk-queue")
async def api_front_desk_queue(current_user: User = Depends(get_current_user)):
    """Get front desk live queue."""
    return await event_bus.get_front_desk_queue(current_user.tenant_id)


@router.get("/housekeeping-board")
async def api_housekeeping_board(current_user: User = Depends(get_current_user)):
    """Get housekeeping live board."""
    return await event_bus.get_housekeeping_board(current_user.tenant_id)
