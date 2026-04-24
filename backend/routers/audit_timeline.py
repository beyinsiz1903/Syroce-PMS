"""
Audit Timeline — API Foundations
Provides timeline-friendly audit log queries, entity audit trails,
and summary endpoints for the upcoming Audit Timeline Panel.
"""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from common.context import OperationContext
from core.database import db
from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit", tags=["Audit Timeline"])


@router.get("/timeline")
async def get_audit_timeline(
    start_date: str | None = None,
    end_date: str | None = None,
    actor_id: str | None = None,
    action: str | None = None,
    severity: str | None = None,
    entity_type: str | None = None,
    limit: int = Query(default=50, le=200),
    cursor: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """
    Timeline-friendly audit log query.
    Supports cursor-based pagination and comprehensive filtering.
    """
    ctx = OperationContext.from_user(current_user)
    query = {"tenant_id": ctx.tenant_id}

    if start_date:
        query.setdefault("timestamp", {})["$gte"] = start_date
    if end_date:
        query.setdefault("timestamp", {})["$lte"] = end_date
    if actor_id:
        query["actor_id"] = actor_id
    if action:
        from security.query_safety import safe_search_term
        if (_a := safe_search_term(action)):
            query["operation_name"] = {"$regex": _a, "$options": "i"}
    if severity:
        query["severity"] = severity
    if entity_type:
        query["target_type"] = entity_type
    if cursor:
        query["timestamp"] = {"$lt": cursor}

    logs = await db.audit_logs.find(query, {"_id": 0}).sort(
        "timestamp", -1
    ).limit(limit + 1).to_list(limit + 1)

    has_more = len(logs) > limit
    if has_more:
        logs = logs[:limit]

    next_cursor = logs[-1]["timestamp"] if has_more and logs else None

    # Group by time buckets for timeline rendering
    grouped = _group_by_time(logs)

    return {
        "events": logs,
        "count": len(logs),
        "has_more": has_more,
        "next_cursor": next_cursor,
        "grouped": grouped,
    }


@router.get("/timeline/{entity_type}/{entity_id}")
async def get_entity_audit_trail(
    entity_type: str,
    entity_id: str,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user),
):
    """
    Get full audit trail for a specific entity (booking, guest, room, folio, etc.)
    with before/after snapshot diffs.
    """
    ctx = OperationContext.from_user(current_user)
    query = {
        "tenant_id": ctx.tenant_id,
        "target_type": entity_type,
        "target_id": entity_id,
    }

    logs = await db.audit_logs.find(query, {"_id": 0}).sort(
        "timestamp", -1
    ).limit(limit).to_list(limit)

    # Compute diffs between snapshots
    trail = []
    for log in logs:
        entry = {
            "id": log.get("id"),
            "operation": log.get("operation_name"),
            "actor_id": log.get("actor_id"),
            "actor_role": log.get("actor_role"),
            "result_status": log.get("result_status"),
            "severity": log.get("severity"),
            "timestamp": log.get("timestamp"),
            "duration_ms": log.get("duration_ms"),
            "before_snapshot": log.get("before_snapshot"),
            "after_snapshot": log.get("after_snapshot"),
            "override_reason": log.get("override_reason"),
        }
        # Compute changed fields if both snapshots exist
        before = log.get("before_snapshot") or {}
        after = log.get("after_snapshot") or {}
        if before and after and isinstance(before, dict) and isinstance(after, dict):
            changed = {}
            all_keys = set(list(before.keys()) + list(after.keys()))
            for k in all_keys:
                if before.get(k) != after.get(k):
                    changed[k] = {"before": before.get(k), "after": after.get(k)}
            entry["changed_fields"] = changed
        trail.append(entry)

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "trail": trail,
        "count": len(trail),
    }


@router.get("/summary")
async def get_audit_summary(
    period: str = Query(default="24h", pattern="^(1h|6h|24h|7d|30d)$"),
    current_user: User = Depends(get_current_user),
):
    """
    Aggregated audit summary for dashboard cards.
    Counts by severity, operation, and actor.
    """
    ctx = OperationContext.from_user(current_user)

    period_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}
    hours = period_map.get(period, 24)
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

    pipeline = [
        {"$match": {"tenant_id": ctx.tenant_id, "timestamp": {"$gte": since}}},
        {"$facet": {
            "by_severity": [
                {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
            ],
            "by_operation": [
                {"$group": {"_id": "$operation_name", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10},
            ],
            "by_actor": [
                {"$group": {"_id": "$actor_id", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10},
            ],
            "by_result": [
                {"$group": {"_id": "$result_status", "count": {"$sum": 1}}},
            ],
            "total": [{"$count": "count"}],
        }},
    ]

    result = await db.audit_logs.aggregate(pipeline).to_list(1)
    data = result[0] if result else {}

    total = data.get("total", [{}])[0].get("count", 0) if data.get("total") else 0

    return {
        "period": period,
        "since": since,
        "total_events": total,
        "by_severity": {d["_id"]: d["count"] for d in data.get("by_severity", []) if d["_id"]},
        "by_operation": {d["_id"]: d["count"] for d in data.get("by_operation", []) if d["_id"]},
        "by_actor": {d["_id"]: d["count"] for d in data.get("by_actor", []) if d["_id"]},
        "by_result": {d["_id"]: d["count"] for d in data.get("by_result", []) if d["_id"]},
    }


def _group_by_time(logs: list) -> list:
    """Group audit events by hour for timeline visualization."""
    buckets = {}
    for log in logs:
        ts = log.get("timestamp", "")
        hour_key = ts[:13] if len(ts) >= 13 else ts[:10]
        if hour_key not in buckets:
            buckets[hour_key] = {"time_bucket": hour_key, "count": 0, "events": []}
        buckets[hour_key]["count"] += 1
        buckets[hour_key]["events"].append({
            "id": log.get("id"),
            "operation": log.get("operation_name"),
            "severity": log.get("severity"),
            "target_type": log.get("target_type"),
        })
    return list(buckets.values())
