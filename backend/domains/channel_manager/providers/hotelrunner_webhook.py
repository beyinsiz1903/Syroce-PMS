"""
HotelRunner Webhook Receiver

Lightweight receiver -> raw_channel_events -> async process via unified ingest pipeline.
Webhook endpoints for new reservations, modifications, and cancellations.
Raw event logs and replay API for debugging and audit.

UPDATED: Now feeds into the unified 9-collection ingest pipeline.
TIMELINE: Every webhook writes received -> normalized -> deduplicated stages.
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from core.database import db
from core.security import get_current_user
from domains.channel_manager.providers.hotelrunner_shared import (
    _persist_and_process,
    _resolve_property_id,
    explode_multi_room_reservation,
)
from models.schemas import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/channel-manager/hotelrunner",
    tags=["HotelRunner Webhooks"],
)


# ── Webhook Batch Processor ──────────────────────────────────────────

async def _process_webhook_batch(
    tenant_id: str, property_id: str, reservations: list, event_type: str,
    source_ip: str = "system",
):
    """Background task: process webhook reservations through ingest pipeline.
    Multi-room reservations are exploded into per-room pipeline events.
    """
    for res in reservations:
        try:
            sub_reservations = explode_multi_room_reservation(res)
            for sub_res in sub_reservations:
                try:
                    await _persist_and_process(tenant_id, property_id, sub_res, event_type, source_ip)
                except Exception as e:
                    logger.error(f"[WEBHOOK] Error processing sub-reservation {sub_res.get('hr_number')}: {e}")
        except Exception as e:
            logger.error(f"[WEBHOOK] Error processing {event_type}: {e}")


# ── Webhook Endpoints ────────────────────────────────────────────────

@router.post("/webhooks/reservations")
async def webhook_reservations(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook endpoint for new reservations from HotelRunner.
    Persists as raw_channel_event and processes via unified ingest pipeline.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    if not tenant_id:
        tenant_id = body.get("tenant_id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required (header X-Tenant-ID or query param)")

    property_id = _resolve_property_id(body)
    reservations = body.get("reservations", [body] if "hr_number" in body else [])
    source_ip = request.client.host if request.client else "unknown"

    background_tasks.add_task(
        _process_webhook_batch, tenant_id, property_id, reservations, "reservation_create", source_ip,
    )

    return {
        "status": "accepted",
        "count": len(reservations),
        "message": f"{len(reservations)} rezervasyon alindi, islenmeye baslandi",
    }


@router.post("/webhooks/modifications")
async def webhook_modifications(request: Request, background_tasks: BackgroundTasks):
    """Webhook for reservation modifications -> unified ingest pipeline."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    if not tenant_id:
        tenant_id = body.get("tenant_id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    property_id = _resolve_property_id(body)
    reservations = body.get("reservations", [body] if "hr_number" in body else [])
    source_ip = request.client.host if request.client else "unknown"

    background_tasks.add_task(
        _process_webhook_batch, tenant_id, property_id, reservations, "reservation_modify", source_ip,
    )
    return {"status": "accepted", "count": len(reservations)}


@router.post("/webhooks/cancellations")
async def webhook_cancellations(request: Request, background_tasks: BackgroundTasks):
    """Webhook for reservation cancellations -> unified ingest pipeline."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    if not tenant_id:
        tenant_id = body.get("tenant_id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    property_id = _resolve_property_id(body)
    reservations = body.get("reservations", [body] if "hr_number" in body else [])
    source_ip = request.client.host if request.client else "unknown"

    # Set status to cancelled for the decision engine
    for res in reservations:
        if "status" not in res:
            res["status"] = "cancelled"

    background_tasks.add_task(
        _process_webhook_batch, tenant_id, property_id, reservations, "reservation_cancel", source_ip,
    )
    return {"status": "accepted", "count": len(reservations)}


# ── Raw Events API ───────────────────────────────────────────────────

@router.get("/logs/events")
async def get_raw_events(
    limit: int = 50,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get raw ingest events for debugging and audit."""
    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status

    events = await db.hotelrunner_raw_events.find(
        query, {"_id": 0, "payload": 0}
    ).sort("received_at", -1).to_list(limit)
    return {"events": events, "count": len(events)}


@router.get("/logs/errors")
async def get_error_events(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    """Get failed ingest events."""
    events = await db.hotelrunner_raw_events.find(
        {"tenant_id": current_user.tenant_id, "status": "error"},
        {"_id": 0},
    ).sort("received_at", -1).to_list(limit)
    return {"events": events, "count": len(events)}


@router.post("/sync/reservations/replay/{event_id}")
async def replay_event(
    event_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Replay a raw event through the ingest pipeline."""
    event = await db.hotelrunner_raw_events.find_one(
        {"id": event_id, "tenant_id": current_user.tenant_id},
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event bulunamadi")

    # Reset event status
    await db.hotelrunner_raw_events.update_one(
        {"id": event_id},
        {"$set": {"status": "pending", "processed_at": None, "error_message": None, "retry_count": (event.get("retry_count", 0) + 1)}},
    )

    background_tasks.add_task(
        _process_webhook_batch,
        current_user.tenant_id,
        _resolve_property_id(event.get("payload", {})),
        [event["payload"]],
        event["event_type"],
    )
    return {"message": "Event replay baslatildi", "event_id": event_id}
