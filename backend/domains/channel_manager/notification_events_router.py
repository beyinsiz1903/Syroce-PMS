"""
Notification Events Router
===========================

API endpoints for the high-signal notification system:
  - Event history & summary
  - Event configuration
  - Manual evaluation trigger
"""
import logging
from modules.pms_core.role_permission_service import require_op  # v100 DW

from fastapi import APIRouter, Depends, Query

from core.security import get_current_user
from domains.channel_manager.notification_events_service import (
    evaluate_tenant_readiness,
    get_event_config,
    get_event_history,
    get_event_summary,
)
from models.schemas import User

logger = logging.getLogger("lockdown.notifications")
router = APIRouter(prefix="/api/lockdown/notifications", tags=["Notification Events"])


@router.get("/events")
async def list_events(
    severity: str | None = Query(None, description="info|warning|critical|blocker"),
    event_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
):
    """List notification events with filters."""
    events = await get_event_history(
        current_user.tenant_id,
        severity=severity,
        event_type=event_type,
        limit=limit,
        skip=skip,
    )
    return {"events": events, "limit": limit, "skip": skip}


@router.get("/summary")
async def event_summary(
    current_user: User = Depends(get_current_user),
):
    """Dashboard-level event summary."""
    return await get_event_summary(current_user.tenant_id)


@router.get("/config")
async def event_config(
    current_user: User = Depends(get_current_user),
):
    """Event type configuration (severities, cooldowns)."""
    return {"event_types": get_event_config()}


@router.post("/evaluate")
async def evaluate_readiness(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    """Trigger tenant readiness evaluation and emit events."""
    property_id = getattr(current_user, "property_id", "default")
    result = await evaluate_tenant_readiness(
        current_user.tenant_id, property_id,
    )
    return result
