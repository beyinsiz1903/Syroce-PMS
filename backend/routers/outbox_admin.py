"""
OTA-002: Outbox Admin Router — Requeue, Replay, Status
========================================================
Operational endpoints for managing the outbox event queue.

Endpoints:
  - GET  /api/outbox/status          → Queue health + metrics
  - GET  /api/outbox/events          → List events by status/provider
  - POST /api/outbox/{id}/requeue    → Requeue a single failed event
  - POST /api/outbox/replay          → Replay all failed events for a provider
"""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from cache_manager import cached
from core.database import db
from core.helpers import require_super_admin_guard
from core.outbox_service import STATUS_FAILED, STATUS_PENDING, STATUS_RETRY

logger = logging.getLogger("routers.outbox_admin")

require_super_admin = require_super_admin_guard()

outbox_admin_router = APIRouter(
    prefix="/outbox",
    tags=["outbox-admin"],
    dependencies=[Depends(require_super_admin)],
)


class RequeueResponse(BaseModel):
    success: bool
    message: str
    event_id: str


class ReplayResponse(BaseModel):
    success: bool
    requeued_count: int
    message: str


class OutboxStatusResponse(BaseModel):
    pending: int
    processing: int
    processed_24h: int
    retry: int
    failed: int
    oldest_pending_seconds: float | None
    last_processed_at: str | None
    provider_failures: dict
    worker: dict


# NOTE: Global admin/ops metric — counts across ALL tenants (no tenant_id filter
# in the queries below). Cache key intentionally resolves to 'global' namespace.
@outbox_admin_router.get("/status", response_model=OutboxStatusResponse)
@cached(ttl=30, key_prefix="outbox_status_global")
async def outbox_status():
    """Get outbox queue health and metrics."""
    now = datetime.now(UTC)

    pending = await db.outbox_events.count_documents({"status": "pending"})
    processing = await db.outbox_events.count_documents({"status": "processing"})
    retry = await db.outbox_events.count_documents({"status": "retry"})
    failed = await db.outbox_events.count_documents({"status": "failed"})

    cutoff_24h = (now - __import__("datetime").timedelta(hours=24)).isoformat()
    processed_24h = await db.outbox_events.count_documents({
        "status": "processed",
        "processed_at": {"$gte": cutoff_24h},
    })

    # Oldest pending event age
    oldest_pending = await db.outbox_events.find_one(
        {"status": {"$in": ["pending", "retry"]}},
        {"_id": 0, "created_at": 1},
        sort=[("created_at", 1)],
    )
    oldest_seconds = None
    if oldest_pending and oldest_pending.get("created_at"):
        try:
            created = datetime.fromisoformat(oldest_pending["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            oldest_seconds = round((now - created).total_seconds(), 1)
        except Exception:
            pass

    # Last processed timestamp
    last_processed = await db.outbox_events.find_one(
        {"status": "processed"},
        {"_id": 0, "processed_at": 1},
        sort=[("processed_at", -1)],
    )
    last_processed_at = last_processed.get("processed_at") if last_processed else None

    # Provider-level failure counts
    pipeline = [
        {"$match": {"status": "failed"}},
        {"$group": {"_id": "$provider", "count": {"$sum": 1}}},
    ]
    provider_failures = {}
    async for doc in db.outbox_events.aggregate(pipeline):
        provider = doc["_id"] or "fan-out"
        provider_failures[provider] = doc["count"]

    # Worker metrics
    try:
        from core.outbox_worker import outbox_ota_worker
        worker_metrics = outbox_ota_worker.metrics
    except Exception:
        worker_metrics = {"running": False}

    return OutboxStatusResponse(
        pending=pending,
        processing=processing,
        processed_24h=processed_24h,
        retry=retry,
        failed=failed,
        oldest_pending_seconds=oldest_seconds,
        last_processed_at=last_processed_at,
        provider_failures=provider_failures,
        worker=worker_metrics,
    )


@outbox_admin_router.get("/events")
async def list_outbox_events(
    status: str | None = Query(None, description="Filter by status"),
    provider: str | None = Query(None, description="Filter by provider"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List outbox events with optional filters."""
    query = {}
    if status:
        query["status"] = status
    if provider:
        query["provider"] = provider

    events = await db.outbox_events.find(
        query, {"_id": 0}
    ).sort("created_at", -1).skip(offset).limit(limit).to_list(limit)

    total = await db.outbox_events.count_documents(query)

    return {
        "events": events,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@outbox_admin_router.post("/{event_id}/requeue", response_model=RequeueResponse)
async def requeue_event(event_id: str):
    """Requeue a single failed event for retry."""
    now = datetime.now(UTC).isoformat()

    result = await db.outbox_events.find_one_and_update(
        {
            "id": event_id,
            "status": {"$in": [STATUS_FAILED, STATUS_RETRY]},
        },
        {
            "$set": {
                "status": STATUS_PENDING,
                "available_at": now,
                "updated_at": now,
                "attempt_count": 0,
                "last_error": None,
                "requeued_at": now,
            },
        },
        projection={"_id": 0, "id": 1},
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Event {event_id} not found or not in failed/retry status",
        )

    logger.info("Outbox event requeued: %s", event_id)
    return RequeueResponse(
        success=True,
        message="Event requeued for retry",
        event_id=event_id,
    )


@outbox_admin_router.post("/replay", response_model=ReplayResponse)
async def replay_failed_events(
    provider: str | None = Query(None, description="Filter by provider"),
    tenant_id: str | None = Query(None, description="Filter by tenant"),
):
    """Replay all failed events, optionally filtered by provider/tenant."""
    now = datetime.now(UTC).isoformat()

    query = {"status": STATUS_FAILED}
    if provider:
        query["provider"] = provider
    if tenant_id:
        query["tenant_id"] = tenant_id

    result = await db.outbox_events.update_many(
        query,
        {
            "$set": {
                "status": STATUS_PENDING,
                "available_at": now,
                "updated_at": now,
                "attempt_count": 0,
                "last_error": None,
                "requeued_at": now,
            },
        },
    )

    count = result.modified_count
    logger.info(
        "Outbox replay: %d events requeued (provider=%s, tenant=%s)",
        count, provider, tenant_id,
    )
    return ReplayResponse(
        success=True,
        requeued_count=count,
        message=f"{count} failed events requeued for retry",
    )
