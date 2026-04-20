"""
Webhook Admin Router — Deliveries, DLQ, Manual Retry
=====================================================
Operational endpoints for monitoring and manually retrying webhook deliveries.

Endpoints:
  - GET  /api/webhooks/status            → Aggregate health metrics
  - GET  /api/webhooks/deliveries        → List webhook deliveries (filterable)
  - GET  /api/webhooks/dlq               → List DLQ items
  - POST /api/webhooks/dlq/{id}/retry    → Manually retry a DLQ item
  - POST /api/webhooks/dlq/{id}/dismiss  → Mark a DLQ item as dismissed
"""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.helpers import require_super_admin_guard
from core.tenant_db import get_system_db

logger = logging.getLogger("routers.webhook_admin")

require_super_admin = require_super_admin_guard()

webhook_admin_router = APIRouter(
    prefix="/webhooks",
    tags=["webhook-admin"],
    dependencies=[Depends(require_super_admin)],
)


class WebhookStatusResponse(BaseModel):
    deliveries_pending: int
    deliveries_delivering: int
    deliveries_retrying: int
    deliveries_succeeded_24h: int
    deliveries_failed_24h: int
    dlq_pending: int
    dlq_total: int
    last_delivery_at: str | None


@webhook_admin_router.get("/status", response_model=WebhookStatusResponse)
async def webhook_status():
    """Aggregate webhook delivery + DLQ health metrics."""
    sysdb = get_system_db()
    now = datetime.now(UTC)
    cutoff_24h = (now - timedelta(hours=24)).isoformat()

    pending = await sysdb.webhook_deliveries.count_documents({"status": "pending"})
    delivering = await sysdb.webhook_deliveries.count_documents({"status": "delivering"})
    retrying = await sysdb.webhook_deliveries.count_documents({"status": "retrying"})
    succeeded_24h = await sysdb.webhook_deliveries.count_documents({
        "status": "succeeded",
        "completed_at": {"$gte": cutoff_24h},
    })
    failed_24h = await sysdb.webhook_deliveries.count_documents({
        "status": {"$in": ["failed", "dlq"]},
        "completed_at": {"$gte": cutoff_24h},
    })

    dlq_pending = await sysdb.webhook_dlq.count_documents({"status": "pending"})
    dlq_total = await sysdb.webhook_dlq.count_documents({})

    last = await sysdb.webhook_deliveries.find_one(
        {"completed_at": {"$ne": None}},
        {"_id": 0, "completed_at": 1},
        sort=[("completed_at", -1)],
    )
    last_at = last.get("completed_at") if last else None

    return WebhookStatusResponse(
        deliveries_pending=pending,
        deliveries_delivering=delivering,
        deliveries_retrying=retrying,
        deliveries_succeeded_24h=succeeded_24h,
        deliveries_failed_24h=failed_24h,
        dlq_pending=dlq_pending,
        dlq_total=dlq_total,
        last_delivery_at=last_at,
    )


@webhook_admin_router.get("/deliveries")
async def list_deliveries(
    status: str | None = Query(None),
    event: str | None = Query(None),
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List webhook delivery records."""
    sysdb = get_system_db()
    query = {}
    if status:
        query["status"] = status
    if event:
        query["event"] = event
    if tenant_id:
        query["tenant_id"] = tenant_id

    items = await sysdb.webhook_deliveries.find(
        query, {"_id": 0}
    ).sort("created_at", -1).skip(offset).limit(limit).to_list(limit)

    total = await sysdb.webhook_deliveries.count_documents(query)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@webhook_admin_router.get("/dlq")
async def list_dlq(
    status: str | None = Query(None),
    event: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List webhook DLQ items."""
    sysdb = get_system_db()
    query = {}
    if status:
        query["status"] = status
    if event:
        query["event"] = event

    items = await sysdb.webhook_dlq.find(
        query, {"_id": 0}
    ).sort("created_at", -1).skip(offset).limit(limit).to_list(limit)

    total = await sysdb.webhook_dlq.count_documents(query)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@webhook_admin_router.post("/dlq/{dlq_id}/retry")
async def retry_dlq(dlq_id: str):
    """Manually retry a DLQ item."""
    from routers.webhook_retry_service import retry_dlq_item
    result = await retry_dlq_item(dlq_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Retry failed"))
    return result


@webhook_admin_router.post("/dlq/{dlq_id}/dismiss")
async def dismiss_dlq(dlq_id: str):
    """Mark a DLQ item as dismissed (won't retry)."""
    sysdb = get_system_db()
    now = datetime.now(UTC).isoformat()
    result = await sysdb.webhook_dlq.find_one_and_update(
        {"id": dlq_id},
        {"$set": {"status": "dismissed", "dismissed_at": now}},
        projection={"_id": 0, "id": 1},
    )
    if not result:
        raise HTTPException(status_code=404, detail="DLQ item not found")
    logger.info("DLQ item dismissed: %s", dlq_id)
    return {"ok": True, "dlq_id": dlq_id}
