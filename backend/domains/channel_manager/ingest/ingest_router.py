"""
Reservation Ingest — Monitoring & Control API
===============================================

Endpoints for monitoring the ingest pipeline, triggering workers,
and injecting test events.

Prefix: /api/channel-manager/ingest/
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.security import get_current_user
from domains.channel_manager import unified_repository as repo
from domains.channel_manager.data_model import (
    ConnectorProvider,
    ProcessingStatus,
    RawChannelEvent,
    RawEventSource,
)
from domains.channel_manager.ingest.normalizer import extract_identity
from domains.channel_manager.ingest.pipeline import process_event
from domains.channel_manager.ingest.workers import (
    get_worker_states,
    trigger_ingest_now,
    trigger_pull,
    trigger_replay_now,
)
from models.schemas import User

logger = logging.getLogger("ingest.router")

router = APIRouter(
    prefix="/api/channel-manager/ingest",
    tags=["Reservation Ingest"],
)


# ── Request Models ────────────────────────────────────────────────────

class InjectEventRequest(BaseModel):
    provider: str  # hotelrunner | exely
    property_id: str
    event_type: str = "reservation_create"
    payload: Dict[str, Any] = Field(default_factory=dict)
    received_via: str = "manual"  # webhook | pull | replay | manual


# ── Pipeline Status ───────────────────────────────────────────────────

@router.get("/status")
async def get_ingest_status(
    property_id: str = Query("prop-001"),
    current_user: User = Depends(get_current_user),
):
    """Get comprehensive ingest pipeline status."""
    event_stats = await repo.get_raw_event_stats(current_user.tenant_id, property_id)
    lineage_stats = await repo.get_lineage_stats(current_user.tenant_id, property_id)
    recon_summary = await repo.get_reconciliation_summary(current_user.tenant_id)
    workers = get_worker_states()

    return {
        "pipeline": {
            "raw_events": event_stats,
            "lineage": lineage_stats,
            "reconciliation": recon_summary,
        },
        "workers": workers,
    }


# ── Event Injection (for testing and manual ingestion) ────────────────

@router.post("/inject")
async def inject_event(
    req: InjectEventRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Inject a raw event into the pipeline for testing or manual ingestion.
    The event is persisted first, then optionally processed immediately.
    """
    try:
        provider_enum = ConnectorProvider(req.provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {req.provider}")

    # Extract identity based on provider
    identity = extract_identity(req.provider, req.payload)
    payload_hash = RawChannelEvent.compute_payload_hash(req.payload)

    # Determine received_via
    via_map = {
        "webhook": RawEventSource.WEBHOOK,
        "pull": RawEventSource.PULL,
        "replay": RawEventSource.REPLAY,
        "manual": RawEventSource.MANUAL,
    }
    received_via = via_map.get(req.received_via, RawEventSource.MANUAL)

    event = RawChannelEvent(
        tenant_id=current_user.tenant_id,
        property_id=req.property_id,
        provider=provider_enum,
        event_type=req.event_type,
        provider_event_id=identity["provider_event_id"],
        external_reservation_id=identity["external_reservation_id"],
        provider_version=identity["provider_version"],
        provider_last_modified_at=identity["provider_last_modified_at"],
        raw_payload=req.payload,
        payload_hash=payload_hash,
        received_via=received_via,
        processing_status=ProcessingStatus.PENDING,
    )

    event_doc = event.to_doc()
    event_id = await repo.insert_raw_event(event_doc)
    logger.info(f"Event injected: {event_id} provider={req.provider} type={req.event_type}")

    return {
        "message": "Event injected",
        "event_id": event_id,
        "provider_event_id": identity["provider_event_id"],
        "external_reservation_id": identity["external_reservation_id"],
        "processing_status": "pending",
    }


@router.post("/inject-and-process")
async def inject_and_process(
    req: InjectEventRequest,
    current_user: User = Depends(get_current_user),
):
    """Inject an event and process it immediately through the pipeline."""
    try:
        provider_enum = ConnectorProvider(req.provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {req.provider}")

    identity = extract_identity(req.provider, req.payload)
    payload_hash = RawChannelEvent.compute_payload_hash(req.payload)

    via_map = {
        "webhook": RawEventSource.WEBHOOK,
        "pull": RawEventSource.PULL,
        "replay": RawEventSource.REPLAY,
        "manual": RawEventSource.MANUAL,
    }
    received_via = via_map.get(req.received_via, RawEventSource.MANUAL)

    event = RawChannelEvent(
        tenant_id=current_user.tenant_id,
        property_id=req.property_id,
        provider=provider_enum,
        event_type=req.event_type,
        provider_event_id=identity["provider_event_id"],
        external_reservation_id=identity["external_reservation_id"],
        provider_version=identity["provider_version"],
        provider_last_modified_at=identity["provider_last_modified_at"],
        raw_payload=req.payload,
        payload_hash=payload_hash,
        received_via=received_via,
        processing_status=ProcessingStatus.PENDING,
    )

    event_doc = event.to_doc()
    event_id = await repo.insert_raw_event(event_doc)

    # Process immediately
    event_doc["id"] = event_id
    pipeline_result = await process_event(event_doc)

    return {
        "message": "Event injected and processed",
        "event_id": event_id,
        "pipeline_result": pipeline_result.to_dict(),
    }


# ── Worker Controls ───────────────────────────────────────────────────

@router.post("/workers/process")
async def trigger_process(
    current_user: User = Depends(get_current_user),
):
    """Manually trigger the ingest processor to process pending events."""
    result = await trigger_ingest_now()
    return {"message": "Ingest processor triggered", "result": result}


@router.post("/workers/replay")
async def trigger_replay(
    current_user: User = Depends(get_current_user),
):
    """Manually trigger the replay worker to retry failed events."""
    result = await trigger_replay_now()
    return {"message": "Replay worker triggered", "result": result}


@router.post("/workers/pull/{provider}")
async def trigger_pull_worker(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    """Manually trigger a pull worker for a specific provider."""
    try:
        ConnectorProvider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {provider}")
    result = await trigger_pull(provider)
    return {"message": f"{provider} pull triggered", "result": result}


@router.get("/workers/status")
async def get_workers_status(
    current_user: User = Depends(get_current_user),
):
    """Get current status of all ingest workers."""
    return {"workers": get_worker_states()}


# ── Raw Events Query ──────────────────────────────────────────────────

@router.get("/events")
async def list_ingest_events(
    property_id: str = Query("prop-001"),
    provider: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
):
    """List raw channel events with optional filters."""
    events = await repo.get_raw_events(
        current_user.tenant_id, property_id, provider, status, limit,
    )
    return {"events": events, "count": len(events)}


@router.get("/events/stats")
async def get_event_stats(
    property_id: str = Query("prop-001"),
    current_user: User = Depends(get_current_user),
):
    """Get event processing statistics."""
    stats = await repo.get_raw_event_stats(current_user.tenant_id, property_id)
    return stats
