"""
Connector Health Dashboard Service — Aggregates health metrics for each connector.

Metrics per connector:
  - uptime_percentage
  - sync_success_rate
  - import_success_rate
  - last_successful_sync
  - last_successful_import
  - failure_spike_alerts
  - retry_count

Health Score Formula:
  score = (sync_success_rate * 0.3) + (import_success_rate * 0.3)
        + (uptime * 0.2) + (alert_penalty * 0.1) + (retry_penalty * 0.1)

Classifications:
  - HEALTHY (score >= 85)
  - DEGRADED (score >= 60)
  - CRITICAL (score < 60)
"""
import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db

from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.connector_health")

_NO_ID = {"_id": 0}


class ConnectorHealthService:
    """Computes health dashboard data for all connectors."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    async def get_connector_health(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        """Get detailed health metrics for a single connector."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            return {"error": "Connector not found"}

        # Sync metrics
        sync_jobs = await self._repo.get_sync_jobs(tenant_id, connector_id, limit=200)
        total_syncs = len(sync_jobs)
        succeeded_syncs = [j for j in sync_jobs if j.get("status") == "succeeded"]
        [j for j in sync_jobs if j.get("status") == "failed"]
        sync_success_rate = round(len(succeeded_syncs) / max(total_syncs, 1) * 100, 1)

        # Last successful sync
        last_sync = None
        for j in sorted(sync_jobs, key=lambda x: x.get("completed_at") or "", reverse=True):
            if j.get("status") == "succeeded":
                last_sync = j.get("completed_at")
                break

        # Import metrics
        import_total = await db.cm_imported_reservations.count_documents(
            {"tenant_id": tenant_id, "connector_id": connector_id}
        )
        import_failed = await db.cm_imported_reservations.count_documents(
            {"tenant_id": tenant_id, "connector_id": connector_id, "import_status": "failed"}
        )
        import_success_rate = round(
            (import_total - import_failed) / max(import_total, 1) * 100, 1
        )

        # Last successful import
        last_import_doc = await db.cm_imported_reservations.find_one(
            {"tenant_id": tenant_id, "connector_id": connector_id, "import_status": {"$ne": "failed"}},
            {"_id": 0, "imported_at": 1},
            sort=[("imported_at", -1)],
        )
        last_import = last_import_doc.get("imported_at") if last_import_doc else None

        # Uptime
        uptime = self._calc_uptime(connector, sync_jobs)

        # Active alerts
        active_alerts = await db.cm_alerts.count_documents({
            "tenant_id": tenant_id, "connector_id": connector_id,
            "status": {"$in": ["active", "acknowledged"]},
        })
        critical_alerts = await db.cm_alerts.count_documents({
            "tenant_id": tenant_id, "connector_id": connector_id,
            "status": "active", "severity": "critical",
        })

        # Retry count
        retry_count = sum(j.get("retry_count", 0) for j in sync_jobs)

        # Import job metrics
        import_jobs = await db.cm_import_jobs.find(
            {"tenant_id": tenant_id, "connector_id": connector_id},
            _NO_ID,
        ).sort("created_at", -1).limit(50).to_list(50)
        import_job_total = len(import_jobs)
        import_job_failed = sum(1 for j in import_jobs if j.get("status") == "failed")

        # Rate push metrics
        rate_push_success_rate = 100.0
        try:
            from .rate_push_tracking_service import RatePushTrackingService
            rpt_svc = RatePushTrackingService(repo=self._repo)
            rp_metrics = await rpt_svc.get_metrics(tenant_id, connector_id)
            rate_push_success_rate = rp_metrics.get("rate_push_success_rate", 100.0)
        except Exception:
            logger.warning("connector_health: rate-push metrics fetch failed", exc_info=True)

        # Health score
        health_score = self._calc_health_score(
            sync_success_rate, import_success_rate, uptime,
            active_alerts, critical_alerts, retry_count, total_syncs,
            rate_push_success_rate=rate_push_success_rate,
        )
        classification = self._classify(health_score)

        # Record trend snapshot (fire-and-forget)
        try:
            from .health_trend_service import HealthTrendService
            trend_svc = HealthTrendService(repo=self._repo)
            await trend_svc.record_health_snapshot(
                tenant_id, connector_id,
                health_score=health_score,
                sync_success_rate=sync_success_rate,
                import_success_rate=import_success_rate,
                active_alerts=active_alerts,
                retry_count=retry_count,
                rate_push_success_rate=rate_push_success_rate,
            )
        except Exception:
            logger.warning("connector_health: trend snapshot record failed", exc_info=True)

        return {
            "connector_id": connector_id,
            "property_id": connector.get("property_id", ""),
            "provider": connector.get("provider", ""),
            "display_name": connector.get("display_name", ""),
            "status": connector.get("status", ""),
            "health_score": health_score,
            "classification": classification,
            "uptime_percentage": uptime,
            "sync_success_rate": sync_success_rate,
            "import_success_rate": import_success_rate,
            "last_successful_sync": last_sync,
            "last_successful_import": last_import,
            "active_alerts": active_alerts,
            "critical_alerts": critical_alerts,
            "retry_count": retry_count,
            "total_syncs": total_syncs,
            "total_imports": import_total,
            "import_jobs_total": import_job_total,
            "import_jobs_failed": import_job_failed,
            "rate_push_success_rate": rate_push_success_rate,
            "calculated_at": datetime.now(UTC).isoformat(),
        }

    async def get_all_health(self, tenant_id: str) -> dict[str, Any]:
        """Get health metrics for all connectors of a tenant.

        Perf: N-connector seri await yerine asyncio.gather ile paralel
        topla. Her get_connector_health çağrısı ~7 DB query yapıyor;
        seri toplam = N × ~700ms, paralelde ≈ tek connector süresi.
        """
        connectors = await self._repo.get_connectors_by_tenant(tenant_id)
        results = await asyncio.gather(
            *[self.get_connector_health(tenant_id, c["id"]) for c in connectors],
            return_exceptions=False,
        ) if connectors else []

        total = len(results)
        healthy = sum(1 for r in results if r.get("classification") == "HEALTHY")
        degraded = sum(1 for r in results if r.get("classification") == "DEGRADED")
        critical = sum(1 for r in results if r.get("classification") == "CRITICAL")
        avg_score = round(sum(r.get("health_score", 0) for r in results) / max(total, 1), 1)

        return {
            "connectors": results,
            "total": total,
            "healthy": healthy,
            "degraded": degraded,
            "critical": critical,
            "average_health_score": avg_score,
        }

    async def get_health_by_property(self, tenant_id: str, property_id: str) -> dict[str, Any]:
        """Get health for connectors of a specific property."""
        connectors = await self._repo.get_connectors_by_tenant(tenant_id)
        prop_connectors = [c for c in connectors if c.get("property_id") == property_id]
        results = await asyncio.gather(
            *[self.get_connector_health(tenant_id, c["id"]) for c in prop_connectors],
            return_exceptions=False,
        ) if prop_connectors else []
        return {"connectors": results, "property_id": property_id, "count": len(results)}

    # ─── Calculations ─────────────────────────────────────────────────

    @staticmethod
    def _calc_uptime(connector: dict, jobs: list[dict]) -> float:
        if not jobs:
            return 100.0 if connector.get("status") == "active" else 0.0
        total = len(jobs)
        failed = sum(1 for j in jobs if j.get("status") == "failed")
        return round((total - failed) / max(total, 1) * 100, 1)

    @staticmethod
    def _calc_health_score(
        sync_rate: float, import_rate: float, uptime: float,
        active_alerts: int, critical_alerts: int,
        retry_count: int, total_syncs: int,
        rate_push_success_rate: float = 100.0,
    ) -> float:
        # Base components (adjusted weights to include rate push)
        sync_component = sync_rate * 0.25
        import_component = import_rate * 0.25
        uptime_component = uptime * 0.15
        rate_push_component = rate_push_success_rate * 0.15

        # Alert penalty (max 10 points)
        alert_penalty = min(active_alerts * 2 + critical_alerts * 5, 10)
        alert_component = max(0, 10 - alert_penalty)

        # Retry penalty (max 10 points)
        retry_rate = (retry_count / max(total_syncs, 1)) * 100
        retry_penalty = min(retry_rate / 5, 10)
        retry_component = max(0, 10 - retry_penalty)

        score = sync_component + import_component + uptime_component + rate_push_component + alert_component + retry_component
        return round(min(max(score, 0), 100), 1)

    @staticmethod
    def _classify(score: float) -> str:
        if score >= 85:
            return "HEALTHY"
        elif score >= 60:
            return "DEGRADED"
        return "CRITICAL"
