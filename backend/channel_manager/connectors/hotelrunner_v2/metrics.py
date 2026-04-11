"""
HotelRunner v2 — Metrics Collector
====================================

Collects operational metrics in MongoDB for dashboard visibility:
  - sync_success_rate
  - ingest_latency_ms
  - push_latency_ms
  - drift_rate
  - retry_count
  - error_taxonomy (timeout, auth, validation, conflict, server)
"""
import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db

logger = logging.getLogger("hrv2.metrics")

COLL_METRICS = "connector_metrics"
_NO_ID = {"_id": 0}


async def record_metric(
    tenant_id: str,
    operation: str,
    *,
    success: bool,
    duration_ms: int = 0,
    error_category: str = "",
    correlation_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record a single operation metric."""
    doc = {
        "tenant_id": tenant_id,
        "provider": "hotelrunner_v2",
        "operation": operation,
        "success": success,
        "duration_ms": duration_ms,
        "error_category": error_category,
        "correlation_id": correlation_id,
        "metadata": metadata or {},
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    try:
        await db[COLL_METRICS].insert_one(doc)
    except Exception as e:
        logger.warning("[HRv2 metrics] write failed: %s", e)


async def get_summary(tenant_id: str, hours: int = 24) -> dict[str, Any]:
    """Get metric summary for the last N hours."""
    from datetime import timedelta

    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

    pipeline = [
        {"$match": {"tenant_id": tenant_id, "provider": "hotelrunner_v2", "recorded_at": {"$gte": since}}},
        {"$group": {
            "_id": "$operation",
            "total": {"$sum": 1},
            "success_count": {"$sum": {"$cond": ["$success", 1, 0]}},
            "fail_count": {"$sum": {"$cond": ["$success", 0, 1]}},
            "avg_duration_ms": {"$avg": "$duration_ms"},
            "max_duration_ms": {"$max": "$duration_ms"},
        }},
    ]

    results = await db[COLL_METRICS].aggregate(pipeline).to_list(50)

    summary: dict[str, Any] = {
        "tenant_id": tenant_id,
        "period_hours": hours,
        "operations": {},
    }
    total_ops = 0
    total_success = 0

    for r in results:
        op = r["_id"]
        total_ops += r["total"]
        total_success += r["success_count"]
        summary["operations"][op] = {
            "total": r["total"],
            "success": r["success_count"],
            "failed": r["fail_count"],
            "success_rate": round(r["success_count"] / r["total"] * 100, 1) if r["total"] > 0 else 0,
            "avg_latency_ms": round(r["avg_duration_ms"] or 0, 1),
            "max_latency_ms": r["max_duration_ms"] or 0,
        }

    summary["total_operations"] = total_ops
    summary["overall_success_rate"] = round(total_success / total_ops * 100, 1) if total_ops > 0 else 0

    # Error taxonomy
    err_pipeline = [
        {"$match": {"tenant_id": tenant_id, "provider": "hotelrunner_v2",
                     "recorded_at": {"$gte": since}, "success": False}},
        {"$group": {"_id": "$error_category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    err_results = await db[COLL_METRICS].aggregate(err_pipeline).to_list(20)
    summary["error_taxonomy"] = {r["_id"]: r["count"] for r in err_results if r["_id"]}

    return summary


async def get_last_sync(tenant_id: str) -> dict[str, Any] | None:
    """Get the last sync operation for a tenant."""
    doc = await db[COLL_METRICS].find_one(
        {"tenant_id": tenant_id, "provider": "hotelrunner_v2",
         "operation": {"$in": ["ingest_reservation", "pull_reservations"]}},
        _NO_ID,
        sort=[("recorded_at", -1)],
    )
    return doc
