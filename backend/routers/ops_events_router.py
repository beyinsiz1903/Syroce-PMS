"""
Operational Events Router — Ops Telemetry & Channel Health Dashboard API
========================================================================

Provides endpoints for:
  - Operational events query
  - Webhook delivery status & DLQ management
  - HotelRunner rate limit status
  - Channel health summary
  - Thin dashboard summary (single endpoint for frontend)
"""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from cache_manager import cached
from core.database import db
from core.security import get_current_user
from models.schemas import User
from routers.webhook_retry_service import retry_dlq_item

logger = logging.getLogger("ops_events_router")

router = APIRouter(prefix="/api/ops-events", tags=["Ops Events & Telemetry"])


# ── Helper ──────────────────────────────────────────────────────────
def _get_tenant(user: User) -> str:
    return user.tenant_id


# ══════════════════════════════════════════════════════════════════════
# 1. Operational Events
# ══════════════════════════════════════════════════════════════════════

@router.get("/list")
@cached(ttl=60, key_prefix="ops_events_list")
async def list_ops_events(
    limit: int = Query(50, ge=1, le=200),
    severity: str = Query("", description="Filter by severity: info, warning, critical, success"),
    event_type: str = Query("", description="Filter by event_type prefix, e.g. 'webhook.delivery'"),
    channel: str = Query("", description="Filter by channel"),
    current_user: User = Depends(get_current_user),
):
    """Operasyonel event'leri listele (son N kayit)."""
    tenant_id = _get_tenant(current_user)
    query = {"tenant_id": tenant_id}

    if severity:
        query["severity"] = severity
    if event_type:
        query["event_type"] = {"$regex": f"^{event_type}"}
    if channel:
        query["channel"] = channel

    events = await db.ops_events.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)

    # Count by severity (last 24h)
    from datetime import timedelta
    since_24h = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    severity_counts = {}
    for sev in ["info", "warning", "critical", "success"]:
        count = await db.ops_events.count_documents({
            "tenant_id": tenant_id,
            "severity": sev,
            "created_at": {"$gte": since_24h},
        })
        severity_counts[sev] = count

    return {
        "events": events,
        "count": len(events),
        "severity_counts_24h": severity_counts,
    }


# ══════════════════════════════════════════════════════════════════════
# 2. Webhook Deliveries
# ══════════════════════════════════════════════════════════════════════

@router.get("/webhook-deliveries")
async def list_webhook_deliveries(
    limit: int = Query(50, ge=1, le=200),
    status: str = Query("", description="Filter: pending, delivering, succeeded, retrying, failed, dlq"),
    current_user: User = Depends(get_current_user),
):
    """Webhook teslimat kayitlarini listele."""
    from core.tenant_db import get_system_db
    sysdb = get_system_db()

    tenant_id = _get_tenant(current_user)
    query = {"tenant_id": tenant_id}
    if status:
        query["status"] = status

    deliveries = await sysdb.webhook_deliveries.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)

    # Summary counts
    total = await sysdb.webhook_deliveries.count_documents({"tenant_id": tenant_id})
    succeeded = await sysdb.webhook_deliveries.count_documents({"tenant_id": tenant_id, "status": "succeeded"})
    failed = await sysdb.webhook_deliveries.count_documents({"tenant_id": tenant_id, "status": {"$in": ["failed", "dlq"]}})
    retrying = await sysdb.webhook_deliveries.count_documents({"tenant_id": tenant_id, "status": "retrying"})

    return {
        "deliveries": deliveries,
        "count": len(deliveries),
        "summary": {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "retrying": retrying,
            "success_rate": round(succeeded / max(total, 1) * 100, 1),
        },
    }


# ══════════════════════════════════════════════════════════════════════
# 3. Webhook DLQ (Dead Letter Queue)
# ══════════════════════════════════════════════════════════════════════

@router.get("/webhook-dlq")
async def list_webhook_dlq(
    limit: int = Query(50, ge=1, le=200),
    status: str = Query("", description="Filter: pending, retrying, resolved, failed"),
    current_user: User = Depends(get_current_user),
):
    """Webhook DLQ kayitlarini listele."""
    from core.tenant_db import get_system_db
    sysdb = get_system_db()

    tenant_id = _get_tenant(current_user)
    query = {"tenant_id": tenant_id}
    if status:
        query["status"] = status

    items = await sysdb.webhook_dlq.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)

    pending_count = await sysdb.webhook_dlq.count_documents({"tenant_id": tenant_id, "status": "pending"})
    total_count = await sysdb.webhook_dlq.count_documents({"tenant_id": tenant_id})

    return {
        "items": items,
        "count": len(items),
        "pending_count": pending_count,
        "total_count": total_count,
    }


@router.post("/webhook-dlq/{dlq_id}/retry")
async def retry_webhook_dlq_item(
    dlq_id: str,
    current_user: User = Depends(get_current_user),
):
    """DLQ'daki bir webhook teslimini manuel olarak retry et."""
    result = await retry_dlq_item(dlq_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Retry başarısız"))
    return result


# ══════════════════════════════════════════════════════════════════════
# 4. HotelRunner Rate Limit Status
# ══════════════════════════════════════════════════════════════════════

@router.get("/rate-limit-status")
async def get_rate_limit_status(
    current_user: User = Depends(get_current_user),
):
    """HotelRunner rate limiter durumunu goster."""
    tenant_id = _get_tenant(current_user)

    # Try to get the global rate limiter instance
    rate_limiter_info = {
        "provider": "hotelrunner",
        "status": "unknown",
        "available_minute_tokens": None,
        "available_hour_tokens": None,
        "max_per_minute": None,
        "max_per_hour": None,
        "is_throttled": False,
        "last_429_at": None,
        "throttle_events_24h": 0,
    }

    try:
        from channel_manager.connectors.hotelrunner_v2.rate_limit import RateLimiter
        # Try to get singleton instance if it exists
        # The rate limiter is typically instantiated per-client
        # For status reporting, we create a snapshot view
        rl = RateLimiter()
        rate_limiter_info.update({
            "status": "active",
            "max_per_minute": rl._max_per_minute,
            "max_per_hour": rl._max_per_hour,
        })
    except Exception:
        pass

    # Get recent throttle events from ops_events
    from datetime import timedelta
    since_24h = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

    throttle_count = await db.ops_events.count_documents({
        "tenant_id": tenant_id,
        "event_type": {"$in": ["rate_limit.active", "push.throttled"]},
        "created_at": {"$gte": since_24h},
    })
    rate_limiter_info["throttle_events_24h"] = throttle_count

    # Get last 429 event
    last_429 = await db.ops_events.find_one(
        {
            "tenant_id": tenant_id,
            "event_type": {"$in": ["rate_limit.active", "push.throttled"]},
        },
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if last_429:
        rate_limiter_info["last_429_at"] = last_429.get("created_at")
        rate_limiter_info["is_throttled"] = throttle_count > 0

    # Get rate push metrics for HotelRunner
    push_metrics = await db.cm_rate_push_metrics.find(
        {"tenant_id": tenant_id},
        {"_id": 0},
    ).sort("recorded_at", -1).limit(5).to_list(5)

    rate_limited_pushes = await db.cm_rate_push_metrics.count_documents({
        "tenant_id": tenant_id,
        "failure_classification": "rate_limited",
        "recorded_at": {"$gte": since_24h},
    })
    rate_limiter_info["rate_limited_pushes_24h"] = rate_limited_pushes
    rate_limiter_info["recent_push_metrics"] = push_metrics

    return rate_limiter_info


# ══════════════════════════════════════════════════════════════════════
# 5. Channel Health Summary
# ══════════════════════════════════════════════════════════════════════

@router.get("/channel-health")
async def get_channel_health(
    current_user: User = Depends(get_current_user),
):
    """Tum kanallarin saglik ozetini goster."""
    tenant_id = _get_tenant(current_user)
    from datetime import timedelta
    since_24h = (datetime.now(UTC) - timedelta(hours=24)).isoformat()

    # Get connectors
    connectors = await db.cm_connectors.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "provider": 1, "status": 1, "property_name": 1, "last_sync_at": 1},
    ).to_list(50)

    channels = []
    for conn in connectors:
        provider = conn.get("provider", "unknown")
        connector_id = conn.get("id", "")

        # Push metrics
        total_pushes = await db.cm_rate_push_metrics.count_documents({
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "recorded_at": {"$gte": since_24h},
        })
        failed_pushes = await db.cm_rate_push_metrics.count_documents({
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "success": False,
            "recorded_at": {"$gte": since_24h},
        })

        # Recent ops events for this channel
        recent_events = await db.ops_events.find({
            "tenant_id": tenant_id,
            "channel": {"$regex": provider, "$options": "i"},
            "created_at": {"$gte": since_24h},
        }, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5)

        # Import status
        recent_imports = await db.ops_events.count_documents({
            "tenant_id": tenant_id,
            "event_type": {"$regex": "^import"},
            "channel": {"$regex": provider, "$options": "i"},
            "created_at": {"$gte": since_24h},
        })
        failed_imports = await db.ops_events.count_documents({
            "tenant_id": tenant_id,
            "event_type": "import.failed",
            "channel": {"$regex": provider, "$options": "i"},
            "created_at": {"$gte": since_24h},
        })

        # Calculate health score
        push_success_rate = round((total_pushes - failed_pushes) / max(total_pushes, 1) * 100, 1)
        health = "healthy"
        if failed_pushes > 0 or failed_imports > 0:
            health = "degraded"
        if push_success_rate < 50:
            health = "critical"

        channels.append({
            "connector_id": connector_id,
            "provider": provider,
            "property_name": conn.get("property_name", ""),
            "status": conn.get("status", "unknown"),
            "last_sync_at": conn.get("last_sync_at"),
            "health": health,
            "push_success_rate_24h": push_success_rate,
            "total_pushes_24h": total_pushes,
            "failed_pushes_24h": failed_pushes,
            "recent_imports_24h": recent_imports,
            "failed_imports_24h": failed_imports,
            "recent_events": recent_events[:3],
        })

    return {
        "channels": channels,
        "total_channels": len(channels),
    }


# ══════════════════════════════════════════════════════════════════════
# 6. Dashboard Summary (single endpoint for frontend)
# ══════════════════════════════════════════════════════════════════════

@router.get("/dashboard-summary")
async def get_dashboard_summary(
    current_user: User = Depends(get_current_user),
):
    """Thin Channel Manager Ops Dashboard icin tek endpoint.

    Returns all data needed for the operations dashboard in one call.
    """
    from core.tenant_db import get_system_db
    sysdb = get_system_db()
    tenant_id = _get_tenant(current_user)
    from datetime import timedelta
    since_24h = (datetime.now(UTC) - timedelta(hours=24)).isoformat()


    # ── Webhook delivery stats ──
    wh_total = await sysdb.webhook_deliveries.count_documents({"tenant_id": tenant_id})
    wh_succeeded = await sysdb.webhook_deliveries.count_documents({"tenant_id": tenant_id, "status": "succeeded"})
    wh_failed = await sysdb.webhook_deliveries.count_documents({"tenant_id": tenant_id, "status": {"$in": ["failed", "dlq"]}})
    wh_retrying = await sysdb.webhook_deliveries.count_documents({"tenant_id": tenant_id, "status": "retrying"})
    wh_dlq_pending = await sysdb.webhook_dlq.count_documents({"tenant_id": tenant_id, "status": "pending"})

    # Recent failed deliveries
    recent_failures = await sysdb.webhook_deliveries.find(
        {"tenant_id": tenant_id, "status": {"$in": ["failed", "dlq"]}},
        {"_id": 0, "id": 1, "event": 1, "url": 1, "last_error": 1, "attempt_count": 1, "status": 1, "created_at": 1},
    ).sort("created_at", -1).limit(10).to_list(10)

    # ── Rate limit status ──
    throttle_count_24h = await db.ops_events.count_documents({
        "tenant_id": tenant_id,
        "event_type": {"$in": ["rate_limit.active", "push.throttled"]},
        "created_at": {"$gte": since_24h},
    })
    rate_limited_pushes_24h = await db.cm_rate_push_metrics.count_documents({
        "tenant_id": tenant_id,
        "failure_classification": "rate_limited",
        "recorded_at": {"$gte": since_24h},
    })
    last_429 = await db.ops_events.find_one(
        {"tenant_id": tenant_id, "event_type": {"$in": ["rate_limit.active", "push.throttled"]}},
        {"_id": 0},
        sort=[("created_at", -1)],
    )

    # ── Channel health ──
    connectors = await db.cm_connectors.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "id": 1, "provider": 1, "status": 1, "property_name": 1, "last_sync_at": 1},
    ).to_list(50)

    channel_summary = []
    for conn in connectors:
        provider = conn.get("provider", "unknown")
        connector_id = conn.get("id", "")

        total_pushes = await db.cm_rate_push_metrics.count_documents({
            "tenant_id": tenant_id, "connector_id": connector_id,
            "recorded_at": {"$gte": since_24h},
        })
        failed_pushes = await db.cm_rate_push_metrics.count_documents({
            "tenant_id": tenant_id, "connector_id": connector_id,
            "success": False, "recorded_at": {"$gte": since_24h},
        })
        push_rate = round((total_pushes - failed_pushes) / max(total_pushes, 1) * 100, 1)

        health = "healthy"
        if failed_pushes > 0:
            health = "degraded"
        if total_pushes > 0 and push_rate < 50:
            health = "critical"

        channel_summary.append({
            "connector_id": connector_id,
            "provider": provider,
            "property_name": conn.get("property_name", ""),
            "status": conn.get("status", "unknown"),
            "last_sync_at": conn.get("last_sync_at"),
            "health": health,
            "push_success_rate_24h": push_rate,
            "total_pushes_24h": total_pushes,
            "failed_pushes_24h": failed_pushes,
        })

    # ── Recent ops events ──
    recent_events = await db.ops_events.find(
        {"tenant_id": tenant_id},
        {"_id": 0},
    ).sort("created_at", -1).limit(20).to_list(20)

    # ── Recent imports ──
    recent_import_events = await db.ops_events.find(
        {"tenant_id": tenant_id, "event_type": {"$regex": "^import"}},
        {"_id": 0},
    ).sort("created_at", -1).limit(10).to_list(10)

    # ── Last successful push per channel ──
    last_pushes = []
    for conn in connectors:
        last_push = await db.cm_rate_push_metrics.find_one(
            {"tenant_id": tenant_id, "connector_id": conn.get("id", ""), "success": True},
            {"_id": 0},
            sort=[("recorded_at", -1)],
        )
        if last_push:
            last_pushes.append({
                "provider": conn.get("provider", ""),
                "connector_id": conn.get("id", ""),
                "last_success_at": last_push.get("recorded_at"),
                "latency_ms": last_push.get("latency_ms", 0),
            })

    return {
        "webhook_delivery": {
            "total": wh_total,
            "succeeded": wh_succeeded,
            "failed": wh_failed,
            "retrying": wh_retrying,
            "dlq_pending": wh_dlq_pending,
            "success_rate": round(wh_succeeded / max(wh_total, 1) * 100, 1),
            "recent_failures": recent_failures,
        },
        "rate_limit": {
            "is_throttled": throttle_count_24h > 0,
            "throttle_events_24h": throttle_count_24h,
            "rate_limited_pushes_24h": rate_limited_pushes_24h,
            "last_429_at": last_429.get("created_at") if last_429 else None,
        },
        "channels": channel_summary,
        "recent_events": recent_events,
        "recent_imports": recent_import_events,
        "last_successful_pushes": last_pushes,
        "generated_at": datetime.now(UTC).isoformat(),
    }
