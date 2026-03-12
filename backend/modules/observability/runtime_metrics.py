"""
Observability — Runtime Metrics Collector
Aggregates hardening metrics for monitoring and alerting.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from core.database import db

logger = logging.getLogger(__name__)


class RuntimeMetricsCollector:
    """Collects and aggregates runtime observability metrics."""

    @staticmethod
    async def collect_all(tenant_id: str) -> Dict[str, Any]:
        """Collect all runtime metrics for a tenant."""
        now = datetime.now(timezone.utc)
        last_hour = (now - timedelta(hours=1)).isoformat()
        last_24h = (now - timedelta(hours=24)).isoformat()

        metrics = {
            "tenant_id": tenant_id,
            "collected_at": now.isoformat(),
            "sync": await _sync_metrics(tenant_id, last_hour),
            "drift": await _drift_metrics(tenant_id, last_24h),
            "reconciliation": await _recon_metrics(tenant_id, last_24h),
            "queue": await _queue_metrics(last_24h),
            "security": await _security_metrics(tenant_id, last_24h),
        }

        # Store snapshot
        await db.runtime_metrics_snapshots.insert_one({
            **metrics, "timestamp": now.isoformat(),
        })

        return metrics

    @staticmethod
    async def get_alerts(tenant_id: str) -> List[Dict[str, Any]]:
        """Generate alerts based on current metrics thresholds."""
        alerts = []
        now = datetime.now(timezone.utc)
        last_hour = (now - timedelta(hours=1)).isoformat()
        last_24h = (now - timedelta(hours=24)).isoformat()

        # Drift alerts
        recent_drift = await db.drift_scan_results.find_one(
            {"tenant_id": tenant_id},
            {"_id": 0},
            sort=[("timestamp", -1)],
        )
        if recent_drift and recent_drift.get("critical_drifts", 0) > 0:
            alerts.append({
                "type": "critical_drift",
                "severity": "critical",
                "message": f"{recent_drift['critical_drifts']} critical inventory drifts detected",
                "source": "channel_manager",
                "timestamp": now.isoformat(),
            })

        # Queue alerts
        pending = await db.task_queue.count_documents({"status": "pending"})
        if pending > 200:
            alerts.append({
                "type": "queue_saturation",
                "severity": "critical",
                "message": f"Queue backlog critical: {pending} pending tasks",
                "source": "workers",
                "timestamp": now.isoformat(),
            })
        elif pending > 50:
            alerts.append({
                "type": "queue_backlog",
                "severity": "warning",
                "message": f"Queue backlog elevated: {pending} pending tasks",
                "source": "workers",
                "timestamp": now.isoformat(),
            })

        # Stuck tasks
        stuck_threshold = (now - timedelta(hours=1)).isoformat()
        stuck = await db.task_queue.count_documents({
            "status": "processing", "started_at": {"$lt": stuck_threshold},
        })
        if stuck > 0:
            alerts.append({
                "type": "stuck_tasks",
                "severity": "warning",
                "message": f"{stuck} tasks stuck in processing",
                "source": "workers",
                "timestamp": now.isoformat(),
            })

        # Tenant guard violations
        violations = await db.tenant_guard_violations.count_documents({
            "expected_tenant_id": tenant_id,
            "timestamp": {"$gte": last_24h},
        })
        if violations > 0:
            alerts.append({
                "type": "tenant_guard_violation",
                "severity": "critical",
                "message": f"{violations} tenant isolation violations in 24h",
                "source": "security",
                "timestamp": now.isoformat(),
            })

        # Sync failures
        failed_syncs = await db.channel_sync_logs.count_documents({
            "tenant_id": tenant_id,
            "timestamp": {"$gte": last_hour},
            "status": "error",
        })
        if failed_syncs > 5:
            alerts.append({
                "type": "sync_failures",
                "severity": "warning",
                "message": f"{failed_syncs} sync failures in last hour",
                "source": "channel_manager",
                "timestamp": now.isoformat(),
            })

        return alerts


async def _sync_metrics(tenant_id: str, since: str) -> Dict[str, Any]:
    total = await db.channel_sync_logs.count_documents({
        "tenant_id": tenant_id, "timestamp": {"$gte": since},
    })
    failed = await db.channel_sync_logs.count_documents({
        "tenant_id": tenant_id, "timestamp": {"$gte": since}, "status": "error",
    })
    return {
        "total_syncs": total,
        "failed_syncs": failed,
        "success_rate": round((1 - failed / max(total, 1)) * 100, 1),
        "period": "1h",
    }


async def _drift_metrics(tenant_id: str, since: str) -> Dict[str, Any]:
    scans = await db.drift_scan_results.find(
        {"tenant_id": tenant_id, "timestamp": {"$gte": since}},
        {"_id": 0, "drifts_found": 1, "critical_drifts": 1},
    ).to_list(100)
    return {
        "scans_count": len(scans),
        "total_drifts": sum(s.get("drifts_found", 0) for s in scans),
        "critical_drifts": sum(s.get("critical_drifts", 0) for s in scans),
        "period": "24h",
    }


async def _recon_metrics(tenant_id: str, since: str) -> Dict[str, Any]:
    results = await db.reconciliation_results.find(
        {"tenant_id": tenant_id, "timestamp": {"$gte": since}},
        {"_id": 0, "auto_fixed": 1, "manual_review": 1, "status": 1},
    ).to_list(100)
    return {
        "runs": len(results),
        "auto_fixed": sum(r.get("auto_fixed", 0) for r in results),
        "manual_review": sum(r.get("manual_review", 0) for r in results),
        "success_rate": round(
            sum(1 for r in results if r.get("status") in ("clean", "reconciled")) / max(len(results), 1) * 100, 1
        ),
        "period": "24h",
    }


async def _queue_metrics(since: str) -> Dict[str, Any]:
    pending = await db.task_queue.count_documents({"status": "pending"})
    processing = await db.task_queue.count_documents({"status": "processing"})
    failed_24h = await db.task_queue.count_documents({
        "status": "failed", "started_at": {"$gte": since},
    })
    dead_letter = await db.dead_letter_tasks.count_documents({})
    return {
        "pending": pending,
        "processing": processing,
        "failed_24h": failed_24h,
        "dead_letter_total": dead_letter,
    }


async def _security_metrics(tenant_id: str, since: str) -> Dict[str, Any]:
    audit_entries = await db.audit_logs.count_documents({
        "tenant_id": tenant_id, "timestamp": {"$gte": since},
    })
    guard_violations = await db.tenant_guard_violations.count_documents({
        "expected_tenant_id": tenant_id, "timestamp": {"$gte": since},
    })
    return {
        "audit_entries_24h": audit_entries,
        "tenant_guard_violations_24h": guard_violations,
        "period": "24h",
    }


runtime_metrics = RuntimeMetricsCollector()
