"""
Wire Status API — Unified failure chain visibility across
Import Bridge → Outbox → ARI Push.

Provides a single endpoint to see the health and failure state
of the entire reservation processing pipeline.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends

from cache_manager import cached
from core.security import get_current_user
from core.tenant_db import get_system_db
from modules.pms_core.role_permission_service import require_op  # v80 Bug DP

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wire-status", tags=["wire-status"])

WIRE_SUBSYSTEMS = ["reservation_import", "outbox_dispatch", "ari_outbound_push"]


async def _subsystem_stats(db, tenant_id: str, operation_type: str, hours: int = 24) -> dict[str, Any]:
    """Aggregate failure stats for a subsystem within a time window."""
    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    pipeline = [
        {
            "$match": {
                "tenant_id": tenant_id,
                "operation_type": operation_type,
                "last_seen_at": {"$gte": cutoff},
            },
        },
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1},
                "last_seen": {"$max": "$last_seen_at"},
            },
        },
    ]
    results = await db.cp_failures.aggregate(pipeline).to_list(20)
    stats = {r["_id"]: {"count": r["count"], "last_seen": r["last_seen"]} for r in results}
    return stats


async def _recent_failures(db, tenant_id: str, operation_type: str, limit: int = 5) -> list:
    """Get most recent failures for a subsystem."""
    return (
        await db.cp_failures.find(
            {
                "tenant_id": tenant_id,
                "operation_type": operation_type,
                "status": {"$in": ["open", "recurring"]},
            },
            {"_id": 0, "failure_id": 1, "error_code": 1, "error_message": 1, "severity": 1, "occurrence_count": 1, "last_seen_at": 1, "provider": 1},
        )
        .sort("last_seen_at", -1)
        .limit(limit)
        .to_list(limit)
    )


def _health_status(stats: dict) -> str:
    """Derive health status from failure stats."""
    open_count = stats.get("open", {}).get("count", 0)
    recurring_count = stats.get("recurring", {}).get("count", 0)
    if open_count + recurring_count == 0:
        return "healthy"
    if recurring_count > 0 or open_count > 3:
        return "degraded"
    return "warning"


@router.get("")
@cached(ttl=60, key_prefix="wire_status")
async def get_wire_status(
    user=Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v80 Bug DP: bank wire transfer status
):
    """Get unified wire status across all pipeline subsystems."""
    tenant_id = user.tenant_id if hasattr(user, "tenant_id") else ""
    db = get_system_db()

    subsystems = {}
    overall_health = "healthy"

    for op_type in WIRE_SUBSYSTEMS:
        stats = await _subsystem_stats(db, tenant_id, op_type)
        recent = await _recent_failures(db, tenant_id, op_type)
        health = _health_status(stats)

        subsystems[op_type] = {
            "health": health,
            "failure_stats": stats,
            "recent_failures": recent,
        }

        if health == "degraded":
            overall_health = "degraded"
        elif health == "warning" and overall_health == "healthy":
            overall_health = "warning"

    # Pipeline counts from outbox
    outbox_pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    outbox_counts = {}
    try:
        results = await db.outbox_events.aggregate(outbox_pipeline).to_list(20)
        outbox_counts = {r["_id"]: r["count"] for r in results}
    except Exception:
        pass

    # Import pipeline counts
    import_pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {"_id": "$import_status", "count": {"$sum": 1}}},
    ]
    import_counts = {}
    try:
        results = await db.imported_reservations.aggregate(import_pipeline).to_list(20)
        import_counts = {r["_id"]: r["count"] for r in results}
    except Exception:
        pass

    return {
        "overall_health": overall_health,
        "tenant_id": tenant_id,
        "subsystems": subsystems,
        "pipeline_counts": {
            "outbox": outbox_counts,
            "imports": import_counts,
        },
    }


@router.get("/failures")
async def get_wire_failures(
    operation_type: str = None,
    severity: str = None,
    limit: int = 20,
    user=Depends(get_current_user),
):
    """List wire failures with optional filters."""
    from controlplane.failure_tracker import get_failure_tracker

    tracker = get_failure_tracker()
    tenant_id = user.tenant_id if hasattr(user, "tenant_id") else ""

    result = await tracker.list_failures(
        tenant_id=tenant_id,
        operation_type=operation_type,
        severity=severity,
        limit=limit,
    )
    return result
