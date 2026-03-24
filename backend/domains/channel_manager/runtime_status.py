"""
Channel Manager — Runtime Status
Aggregates health and operational status across all CM subsystems.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from core.database import db
from domains.channel_manager.provider_failover import provider_failover

logger = logging.getLogger(__name__)


class CMRuntimeStatus:
    """Aggregates channel manager runtime health across all subsystems."""

    @staticmethod
    async def get_status(tenant_id: str) -> Dict[str, Any]:
        """Full runtime status for the channel manager."""
        now = datetime.now(timezone.utc)

        # Active connections
        connections = await db.channel_connections.find(
            {"tenant_id": tenant_id, "status": "active"}, {"_id": 0}
        ).to_list(100)

        # Recent sync logs (last hour)
        one_hour_ago = (now - timedelta(hours=1)).isoformat()
        recent_syncs = await db.channel_sync_logs.count_documents({
            "tenant_id": tenant_id,
            "timestamp": {"$gte": one_hour_ago},
        })
        failed_syncs = await db.channel_sync_logs.count_documents({
            "tenant_id": tenant_id,
            "timestamp": {"$gte": one_hour_ago},
            "status": "error",
        })

        # Recent drift scans
        recent_drifts = await db.drift_scan_results.find(
            {"tenant_id": tenant_id},
            {"_id": 0, "drifts_found": 1, "critical_drifts": 1, "scanned_at": 1},
        ).sort("timestamp", -1).limit(1).to_list(1)

        last_drift = recent_drifts[0] if recent_drifts else None

        # Recent reconciliations
        recent_recon = await db.reconciliation_results.find(
            {"tenant_id": tenant_id},
            {"_id": 0, "status": 1, "auto_fixed": 1, "manual_review": 1, "reconciled_at": 1},
        ).sort("timestamp", -1).limit(1).to_list(1)

        last_recon = recent_recon[0] if recent_recon else None

        # Provider circuit breaker status
        provider_statuses = provider_failover.get_all_status()

        # Overall health
        health = "healthy"
        issues = []
        if failed_syncs > 0:
            health = "degraded"
            issues.append(f"{failed_syncs} failed syncs in last hour")
        if last_drift and last_drift.get("critical_drifts", 0) > 0:
            health = "critical"
            issues.append(f"{last_drift['critical_drifts']} critical drifts detected")
        open_circuits = [p for p in provider_statuses if p.get("state") == "open"]
        if open_circuits:
            health = "degraded" if health == "healthy" else health
            issues.append(f"{len(open_circuits)} provider circuit(s) open")

        return {
            "tenant_id": tenant_id,
            "health": health,
            "issues": issues,
            "active_connections": len(connections),
            "sync_stats": {
                "recent_syncs": recent_syncs,
                "failed_syncs": failed_syncs,
                "period": "1h",
            },
            "drift": {
                "last_scan": last_drift,
            },
            "reconciliation": {
                "last_run": last_recon,
            },
            "providers": provider_statuses,
            "checked_at": now.isoformat(),
        }

    @staticmethod
    async def get_provider_health(tenant_id: str) -> List[Dict[str, Any]]:
        """Get health status per OTA provider."""
        connections = await db.channel_connections.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(100)

        results = []
        for conn in connections:
            channel = conn.get("channel", "unknown")
            breaker = provider_failover.get_breaker(channel)
            last_sync_log = await db.channel_sync_logs.find_one(
                {"tenant_id": tenant_id, "connection_id": conn.get("id")},
                {"_id": 0},
                sort=[("timestamp", -1)],
            )
            results.append({
                "provider": channel,
                "connection_id": conn.get("id"),
                "status": conn.get("status"),
                "circuit_state": breaker.get_status(),
                "last_sync": last_sync_log.get("timestamp") if last_sync_log else None,
                "last_sync_status": last_sync_log.get("status") if last_sync_log else None,
            })
        return results


cm_runtime_status = CMRuntimeStatus()
