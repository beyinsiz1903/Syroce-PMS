"""
ARI Push Engine — API Router.

POST /api/channel-manager/ari/events/publish
GET  /api/channel-manager/ari/events
GET  /api/channel-manager/ari/change-sets
POST /api/channel-manager/ari/change-sets/{id}/push
POST /api/channel-manager/ari/push
POST /api/channel-manager/ari/resync
GET  /api/channel-manager/ari/outbound-logs
GET  /api/channel-manager/ari/drift
POST /api/channel-manager/ari/drift/check
POST /api/channel-manager/ari/drift/reconcile
GET  /api/channel-manager/ari/stats
GET  /api/channel-manager/ari/engine-stats
"""
import logging
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from .events import ARIChangeEvent
from .schemas import (
    PublishARIEventRequest, PushChangeSetsRequest,
    ResyncRequest, DriftCheckRequest,
)
from . import outbound_service
from . import repositories as repo
from . import drift_worker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channel-manager/ari", tags=["ARI Push Engine"])


@router.post("/events/publish")
async def publish_event(req: PublishARIEventRequest):
    """Publish an ARI change event into the push pipeline."""
    event = ARIChangeEvent(
        tenant_id=req.tenant_id,
        property_id=req.property_id,
        source_service=req.source_service,
        event_type=req.event_type,
        room_type_code=req.room_type_code,
        rate_plan_code=req.rate_plan_code,
        date_from=req.date_from,
        date_to=req.date_to,
        payload=req.payload,
        actor_id=req.actor_id,
    )
    result = await outbound_service.publish_ari_event(event)
    return result


@router.get("/events")
async def list_events(
    tenant_id: str,
    property_id: str,
    event_type: Optional[str] = None,
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
):
    """List recent ARI events."""
    events = await repo.get_ari_events(tenant_id, property_id, limit, skip, event_type)
    return {"events": events, "count": len(events)}


@router.get("/change-sets")
async def list_change_sets(
    tenant_id: str,
    property_id: str,
    status: Optional[str] = None,
    provider: Optional[str] = None,
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
):
    """List ARI change sets."""
    change_sets = await repo.get_change_sets(tenant_id, property_id, status, provider, limit, skip)
    return {"change_sets": change_sets, "count": len(change_sets)}


@router.post("/change-sets/{cs_id}/push")
async def force_push_change_set(cs_id: str):
    """Force push a specific change set."""
    result = await outbound_service.force_push_change_set(cs_id)
    return result


@router.post("/push")
async def push_pending(req: PushChangeSetsRequest):
    """Process and push pending change sets."""
    result = await outbound_service.push_pending_changes(
        req.tenant_id, req.provider, req.limit
    )
    return result


@router.post("/resync")
async def resync(req: ResyncRequest):
    """Trigger a full resync for a property+provider."""
    result = await outbound_service.resync_property(
        req.tenant_id, req.property_id, req.provider, req.scope
    )
    return result


@router.get("/outbound-logs")
async def list_outbound_logs(
    tenant_id: str,
    property_id: str,
    provider: Optional[str] = None,
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
):
    """List outbound push logs."""
    logs = await repo.get_outbound_logs(tenant_id, property_id, provider, limit, skip)
    return {"logs": logs, "count": len(logs)}


@router.get("/drift")
async def list_drift_states(
    tenant_id: str,
    property_id: str,
    provider: Optional[str] = None,
    drift_only: bool = False,
    limit: int = Query(50, le=200),
):
    """List drift states."""
    states = await repo.get_drift_states(tenant_id, property_id, provider, drift_only, limit)
    return {"drift_states": states, "count": len(states)}


@router.post("/drift/check")
async def check_drift(req: DriftCheckRequest):
    """Run drift check (requires PMS+provider snapshots, uses mock data for now)."""
    # In production, this would pull real snapshots
    report = await drift_worker.check_drift(
        req.tenant_id, req.property_id, req.provider,
        pms_snapshot=[], provider_snapshot=[],
    )
    return report


@router.post("/drift/reconcile")
async def reconcile(req: DriftCheckRequest):
    """Generate corrective change sets for detected drifts."""
    result = await drift_worker.reconcile_drift(
        req.tenant_id, req.property_id, req.provider
    )
    return result


@router.get("/stats")
async def get_stats(tenant_id: str, property_id: str):
    """Get aggregate ARI push statistics."""
    stats = await repo.get_ari_stats(tenant_id, property_id)
    return stats


@router.get("/engine-stats")
async def get_engine_stats():
    """Get ARI push engine runtime statistics."""
    return outbound_service.get_engine_stats()
