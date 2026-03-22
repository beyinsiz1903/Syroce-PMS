"""
Usage Metering Service
Tracks per-tenant usage events: API calls, reservations, rooms, users, etc.
Fire-and-forget recording with background aggregation.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from collections import defaultdict

from core.database import db

logger = logging.getLogger(__name__)

# ─── In-memory buffer for high-frequency events ───
_buffer: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
_last_flush = datetime.now(timezone.utc)
FLUSH_INTERVAL_SECONDS = 60


class UsageEventType:
    API_CALL = "api_call"
    RESERVATION_CREATED = "reservation_created"
    RESERVATION_CANCELLED = "reservation_cancelled"
    GUEST_CREATED = "guest_created"
    ROOM_CREATED = "room_created"
    ROOM_DELETED = "room_deleted"
    USER_CREATED = "user_created"
    USER_DELETED = "user_deleted"
    CHANNEL_SYNC = "channel_sync"
    REPORT_GENERATED = "report_generated"
    INVOICE_CREATED = "invoice_created"
    AI_REQUEST = "ai_request"
    WEBHOOK_RECEIVED = "webhook_received"
    NIGHT_AUDIT_RUN = "night_audit_run"
    LOGIN = "login"


async def record_usage(tenant_id: str, event_type: str, count: int = 1, metadata: Optional[Dict] = None):
    """Fire-and-forget usage event recording. Buffers in memory, flushes periodically."""
    global _last_flush
    try:
        key = f"{tenant_id}:{event_type}"
        _buffer[tenant_id][event_type] += count

        now = datetime.now(timezone.utc)
        if (now - _last_flush).total_seconds() >= FLUSH_INTERVAL_SECONDS:
            await flush_buffer()
    except Exception as e:
        logger.debug(f"Metering record skip: {e}")


async def flush_buffer():
    """Flush in-memory buffer to MongoDB."""
    global _buffer, _last_flush
    if not _buffer:
        return

    now = datetime.now(timezone.utc)
    date_key = now.strftime("%Y-%m-%d")
    month_key = now.strftime("%Y-%m")

    snapshot = dict(_buffer)
    _buffer = defaultdict(lambda: defaultdict(int))
    _last_flush = now

    for tenant_id, events in snapshot.items():
        for event_type, count in events.items():
            try:
                await db.usage_daily.update_one(
                    {"tenant_id": tenant_id, "date": date_key, "event_type": event_type},
                    {
                        "$inc": {"count": count},
                        "$set": {"updated_at": now.isoformat()},
                        "$setOnInsert": {
                            "tenant_id": tenant_id,
                            "date": date_key,
                            "month": month_key,
                            "event_type": event_type,
                            "created_at": now.isoformat(),
                        },
                    },
                    upsert=True,
                )
            except Exception as e:
                logger.warning(f"Metering flush error for {tenant_id}/{event_type}: {e}")


async def get_tenant_usage_summary(tenant_id: str, days: int = 30) -> Dict[str, Any]:
    """Get aggregated usage summary for a tenant."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    pipeline = [
        {"$match": {"tenant_id": tenant_id, "date": {"$gte": cutoff}}},
        {"$group": {"_id": "$event_type", "total": {"$sum": "$count"}}},
        {"$sort": {"total": -1}},
    ]
    results = await db.usage_daily.aggregate(pipeline).to_list(100)

    summary = {r["_id"]: r["total"] for r in results}

    # Current resource counts
    rooms = await db.rooms.count_documents({"tenant_id": tenant_id})
    users = await db.users.count_documents({"tenant_id": tenant_id})
    guests = await db.guests.count_documents({"tenant_id": tenant_id})

    return {
        "tenant_id": tenant_id,
        "period_days": days,
        "events": summary,
        "current_resources": {
            "rooms": rooms,
            "users": users,
            "guests": guests,
        },
    }


async def get_tenant_usage_timeline(tenant_id: str, days: int = 30, event_type: Optional[str] = None) -> List[Dict]:
    """Get daily usage timeline for charts."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    match_q: Dict[str, Any] = {"tenant_id": tenant_id, "date": {"$gte": cutoff}}
    if event_type:
        match_q["event_type"] = event_type

    pipeline = [
        {"$match": match_q},
        {"$group": {"_id": {"date": "$date", "event_type": "$event_type"}, "count": {"$sum": "$count"}}},
        {"$sort": {"_id.date": 1}},
    ]
    results = await db.usage_daily.aggregate(pipeline).to_list(1000)

    timeline = []
    for r in results:
        timeline.append({
            "date": r["_id"]["date"],
            "event_type": r["_id"]["event_type"],
            "count": r["count"],
        })
    return timeline


async def get_system_usage_overview() -> Dict[str, Any]:
    """System-wide usage overview for super admin. Uses raw DB for cross-tenant access."""
    from core.database import _raw_db

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    month = now.strftime("%Y-%m")

    # Today's totals by event type
    today_pipeline = [
        {"$match": {"date": today}},
        {"$group": {"_id": "$event_type", "total": {"$sum": "$count"}}},
    ]
    today_results = await _raw_db.usage_daily.aggregate(today_pipeline).to_list(100)
    today_totals = {r["_id"]: r["total"] for r in today_results}

    # Monthly totals by event type
    month_pipeline = [
        {"$match": {"month": month}},
        {"$group": {"_id": "$event_type", "total": {"$sum": "$count"}}},
    ]
    month_results = await _raw_db.usage_daily.aggregate(month_pipeline).to_list(100)
    month_totals = {r["_id"]: r["total"] for r in month_results}

    # Active tenants (had usage in last 7 days)
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    active_pipeline = [
        {"$match": {"date": {"$gte": week_ago}}},
        {"$group": {"_id": "$tenant_id"}},
        {"$count": "active_tenants"},
    ]
    active_result = await _raw_db.usage_daily.aggregate(active_pipeline).to_list(1)
    active_tenants = active_result[0]["active_tenants"] if active_result else 0

    # Top tenants by usage
    top_pipeline = [
        {"$match": {"month": month}},
        {"$group": {"_id": "$tenant_id", "total": {"$sum": "$count"}}},
        {"$sort": {"total": -1}},
        {"$limit": 10},
    ]
    top_results = await _raw_db.usage_daily.aggregate(top_pipeline).to_list(10)

    # Enrich with tenant names
    top_tenants = []
    for r in top_results:
        t = await _raw_db.tenants.find_one({"id": r["_id"]}, {"_id": 0, "property_name": 1, "subscription_tier": 1})
        top_tenants.append({
            "tenant_id": r["_id"],
            "property_name": t.get("property_name", "?") if t else "?",
            "tier": t.get("subscription_tier", "?") if t else "?",
            "total_events": r["total"],
        })

    return {
        "today": today_totals,
        "this_month": month_totals,
        "active_tenants_7d": active_tenants,
        "top_tenants": top_tenants,
        "generated_at": now.isoformat(),
    }


async def ensure_metering_indexes():
    """Create indexes for usage_daily collection."""
    try:
        await db.usage_daily.create_index(
            [("tenant_id", 1), ("date", 1), ("event_type", 1)],
            unique=True,
            name="idx_usage_tenant_date_event",
        )
        await db.usage_daily.create_index(
            [("date", 1)],
            name="idx_usage_date",
        )
        await db.usage_daily.create_index(
            [("month", 1)],
            name="idx_usage_month",
        )
        logger.info("Metering indexes ensured")
    except Exception as e:
        logger.warning(f"Metering index creation: {e}")
