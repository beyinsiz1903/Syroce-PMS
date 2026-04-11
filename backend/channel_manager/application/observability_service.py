"""
Channel Manager Observability Service - Aggregates health metrics and operational status.
"""
import logging
from datetime import UTC, datetime
from typing import Any

from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.observability_service")


class ObservabilityService:
    """Aggregates channel manager health and operational metrics."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    async def get_connector_health(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        """Get health metrics for a specific connector."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            return {"status": "not_found"}

        metrics = await self._repo.get_sync_metrics(tenant_id, connector_id)

        # Determine health status
        health = "green"
        reasons = []

        consecutive_failures = connector.get("consecutive_failures", 0)
        if consecutive_failures >= 5:
            health = "red"
            reasons.append(f"{consecutive_failures} consecutive sync failures")
        elif consecutive_failures >= 3:
            health = "yellow"
            reasons.append(f"{consecutive_failures} consecutive sync failures")

        if connector.get("status") != "active":
            health = "yellow" if health == "green" else health
            reasons.append(f"Connector status: {connector.get('status')}")

        last_sync = connector.get("last_successful_sync")
        if last_sync:
            try:
                dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
                hours_ago = (datetime.now(UTC) - dt).total_seconds() / 3600
                if hours_ago > 24:
                    health = "red" if hours_ago > 48 else "yellow"
                    reasons.append(f"Last sync {hours_ago:.0f}h ago")
            except (ValueError, TypeError):
                pass
        else:
            health = "yellow" if health == "green" else health
            reasons.append("No successful sync recorded")

        open_issues = metrics.get("open_issues", 0)
        if open_issues > 10:
            health = "red"
            reasons.append(f"{open_issues} open reconciliation issues")
        elif open_issues > 3:
            health = "yellow" if health == "green" else health
            reasons.append(f"{open_issues} open reconciliation issues")

        return {
            "connector_id": connector_id,
            "provider": connector.get("provider"),
            "display_name": connector.get("display_name"),
            "status": connector.get("status"),
            "health": health,
            "reasons": reasons,
            "last_successful_sync": last_sync,
            "consecutive_failures": consecutive_failures,
            "total_syncs": connector.get("total_syncs", 0),
            "sync_metrics": metrics,
        }

    async def get_dashboard_overview(self, tenant_id: str) -> dict[str, Any]:
        """Get overall channel manager dashboard data."""
        connectors = await self._repo.get_connectors_by_tenant(tenant_id)

        overview = {
            "total_connectors": len(connectors),
            "active_connectors": sum(1 for c in connectors if c.get("status") == "active"),
            "connectors": [],
            "health_summary": {"green": 0, "yellow": 0, "red": 0},
        }

        for c in connectors:
            health = await self.get_connector_health(tenant_id, c["id"])
            overview["connectors"].append(health)
            h = health.get("health", "green")
            overview["health_summary"][h] = overview["health_summary"].get(h, 0) + 1

        # Recent sync jobs
        recent_jobs = []
        for c in connectors:
            jobs = await self._repo.get_sync_jobs(tenant_id, c["id"], limit=5)
            recent_jobs.extend(jobs)
        recent_jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        overview["recent_sync_jobs"] = recent_jobs[:20]

        # Recent import batches
        recent_batches = await self._repo.get_import_batches(tenant_id, limit=10)
        overview["recent_import_batches"] = recent_batches

        # Open reconciliation issues
        open_issues = await self._repo.get_reconciliation_issues(tenant_id, status="open", limit=20)
        overview["open_issues"] = open_issues
        overview["open_issue_count"] = len(open_issues)

        # Recent audit log
        audit_logs = await self._repo.get_audit_logs(tenant_id, limit=20)
        overview["recent_audit"] = audit_logs

        return overview
