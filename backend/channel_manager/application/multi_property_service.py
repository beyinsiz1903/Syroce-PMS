"""
Multi-Property Integration Dashboard Service — Phase 5.

Features: property-level aggregation, tenant-wide health, cross-property comparison,
           top failing properties, top retry sources, most common provider issues,
           best performing properties, degraded connectors by property.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import db

from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.multi_property")


class MultiPropertyService:
    """Aggregates integration status across all properties in a tenant."""

    def __init__(self, repo: Optional[ChannelManagerRepository] = None):
        self._repo = repo or ChannelManagerRepository()

    async def get_dashboard(self, tenant_id: str) -> Dict[str, Any]:
        """Get the multi-property integration dashboard."""
        connectors = await self._repo.get_connectors_by_tenant(tenant_id)

        # Group by property
        by_property: Dict[str, List[Dict]] = {}
        for c in connectors:
            pid = c.get("property_id", "unknown")
            if pid not in by_property:
                by_property[pid] = []
            by_property[pid].append(c)

        properties = []
        for pid, conns in by_property.items():
            prop_data = await self._aggregate_property(tenant_id, pid, conns)
            properties.append(prop_data)

        # Sort by health
        properties.sort(key=lambda p: p.get("health_score", 0))

        # Tenant-wide aggregation
        total_connectors = len(connectors)
        active_connectors = sum(1 for c in connectors if c.get("status") == "active")
        total_health = sum(p.get("health_score", 0) for p in properties)
        avg_health = round(total_health / max(len(properties), 1))

        healthy_props = sum(1 for p in properties if p.get("health_status") == "healthy")
        degraded_props = sum(1 for p in properties if p.get("health_status") == "degraded")
        critical_props = sum(1 for p in properties if p.get("health_status") == "critical")

        top_failing = sorted(properties, key=lambda p: p.get("failed_syncs", 0), reverse=True)[:5]
        top_retry = sorted(properties, key=lambda p: p.get("retry_rate", 0), reverse=True)[:5]
        best_performing = sorted(properties, key=lambda p: p.get("health_score", 0), reverse=True)[:5]

        # Provider distribution
        provider_dist = {}
        for c in connectors:
            p = c.get("provider", "unknown")
            provider_dist[p] = provider_dist.get(p, 0) + 1

        # Error distribution
        error_dist = await self._get_error_distribution(tenant_id)

        return {
            "total_properties": len(properties),
            "total_connectors": total_connectors,
            "active_connectors": active_connectors,
            "average_health_score": avg_health,
            "tenant_health_status": "healthy" if avg_health >= 80 else ("degraded" if avg_health >= 50 else "critical"),
            "healthy_properties": healthy_props,
            "degraded_properties": degraded_props,
            "critical_properties": critical_props,
            "properties": properties,
            "top_failing": [{"property_id": p["property_id"], "failed_syncs": p.get("failed_syncs", 0)} for p in top_failing],
            "top_retry_sources": [{"property_id": p["property_id"], "retry_rate": p.get("retry_rate", 0)} for p in top_retry],
            "best_performing": [{"property_id": p["property_id"], "health_score": p.get("health_score", 0)} for p in best_performing],
            "provider_distribution": provider_dist,
            "error_distribution": error_dist,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_comparison(self, tenant_id: str) -> Dict[str, Any]:
        """Cross-property comparison."""
        connectors = await self._repo.get_connectors_by_tenant(tenant_id)
        by_property: Dict[str, List[Dict]] = {}
        for c in connectors:
            pid = c.get("property_id", "unknown")
            if pid not in by_property:
                by_property[pid] = []
            by_property[pid].append(c)

        comparisons = []
        for pid, conns in by_property.items():
            prop_data = await self._aggregate_property(tenant_id, pid, conns)
            comparisons.append({
                "property_id": pid,
                "connector_count": len(conns),
                "health_score": prop_data.get("health_score", 0),
                "health_status": prop_data.get("health_status", "unknown"),
                "sync_success_rate": prop_data.get("sync_success_rate", 0),
                "ack_success_rate": prop_data.get("ack_success_rate", 0),
                "retry_rate": prop_data.get("retry_rate", 0),
                "open_issues": prop_data.get("open_issues", 0),
                "failed_syncs": prop_data.get("failed_syncs", 0),
            })

        comparisons.sort(key=lambda x: x.get("health_score", 0), reverse=True)
        return {"comparisons": comparisons, "count": len(comparisons)}

    async def get_issues(self, tenant_id: str, property_id: Optional[str] = None) -> Dict[str, Any]:
        """Get issues across all properties or a specific one."""
        q: Dict[str, Any] = {"tenant_id": tenant_id, "status": {"$in": ["open", "investigating", "retrying"]}}
        if property_id:
            q["property_id"] = property_id

        issues = await db.cm_reconciliation_issues.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)

        by_property: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        for issue in issues:
            pid = issue.get("property_id", "unknown")
            sev = issue.get("severity", "unknown")
            by_property[pid] = by_property.get(pid, 0) + 1
            by_severity[sev] = by_severity.get(sev, 0) + 1

        return {
            "issues": issues[:100],
            "total": len(issues),
            "by_property": by_property,
            "by_severity": by_severity,
        }

    async def get_health(self, tenant_id: str) -> Dict[str, Any]:
        """Get aggregated health across all properties."""
        connectors = await self._repo.get_connectors_by_tenant(tenant_id)
        by_property: Dict[str, List[Dict]] = {}
        for c in connectors:
            pid = c.get("property_id", "unknown")
            if pid not in by_property:
                by_property[pid] = []
            by_property[pid].append(c)

        health_data = []
        for pid, conns in by_property.items():
            prop = await self._aggregate_property(tenant_id, pid, conns)
            health_data.append({
                "property_id": pid,
                "health_score": prop.get("health_score", 0),
                "health_status": prop.get("health_status", "unknown"),
                "connector_count": len(conns),
                "active_connectors": sum(1 for c in conns if c.get("status") == "active"),
            })

        health_data.sort(key=lambda x: x.get("health_score", 0))
        return {"properties": health_data, "count": len(health_data)}

    # ─── Internal Helpers ──────────────────────────────────────────────

    async def _aggregate_property(self, tenant_id: str, property_id: str, connectors: List[Dict]) -> Dict[str, Any]:
        """Aggregate metrics for a single property."""
        from ..application.reconciliation_service import ReconciliationService
        recon = ReconciliationService(self._repo)

        total_health = 0
        total_syncs = 0
        total_succeeded = 0
        total_failed = 0
        total_retries = 0
        total_imports = 0
        total_ack_sent = 0
        open_issues = 0
        connector_details = []

        for c in connectors:
            cid = c.get("id", "")
            health = await recon.get_health_score(tenant_id, cid)
            total_health += health.get("health_score", 0)

            jobs = await self._repo.get_sync_jobs(tenant_id, cid, limit=100)
            succeeded = sum(1 for j in jobs if j.get("status") == "succeeded")
            failed = sum(1 for j in jobs if j.get("status") == "failed")
            retries = sum(1 for j in jobs if j.get("retry_count", 0) > 0)

            total_syncs += len(jobs)
            total_succeeded += succeeded
            total_failed += failed
            total_retries += retries

            imports = await db.cm_imported_reservations.count_documents(
                {"tenant_id": tenant_id, "connector_id": cid}
            )
            acks = await db.cm_imported_reservations.count_documents(
                {"tenant_id": tenant_id, "connector_id": cid, "ack_status": "ack_sent"}
            )
            import_failed_count = await db.cm_imported_reservations.count_documents(
                {"tenant_id": tenant_id, "connector_id": cid, "import_status": "failed"}
            )
            import_review_count = await db.cm_imported_reservations.count_documents(
                {"tenant_id": tenant_id, "connector_id": cid, "import_status": {"$in": ["review", "conflict", "out_of_order"]}}
            )
            total_imports += imports
            total_ack_sent += acks

            summary = await self._repo.get_reconciliation_summary(tenant_id, cid)
            issues = summary.get("total_open", 0)
            open_issues += issues

            connector_details.append({
                "connector_id": cid,
                "display_name": c.get("display_name", ""),
                "provider": c.get("provider", ""),
                "status": c.get("status", ""),
                "health_score": health.get("health_score", 0),
                "import_total": imports,
                "import_failed": import_failed_count,
                "import_review": import_review_count,
            })

        avg_health = round(total_health / max(len(connectors), 1))
        sync_rate = round(total_succeeded / max(total_syncs, 1) * 100, 1)
        ack_rate = round(total_ack_sent / max(total_imports, 1) * 100, 1)
        retry_rate = round(total_retries / max(total_syncs, 1) * 100, 1)
        total_import_failed = sum(c.get("import_failed", 0) for c in connector_details)
        total_import_review = sum(c.get("import_review", 0) for c in connector_details)
        import_success_rate = round(
            (total_imports - total_import_failed - total_import_review) / max(total_imports, 1) * 100, 1
        )

        return {
            "property_id": property_id,
            "connector_count": len(connectors),
            "active_connectors": sum(1 for c in connectors if c.get("status") == "active"),
            "health_score": avg_health,
            "health_status": "healthy" if avg_health >= 80 else ("degraded" if avg_health >= 50 else "critical"),
            "sync_success_rate": sync_rate,
            "ack_success_rate": ack_rate,
            "retry_rate": retry_rate,
            "total_syncs": total_syncs,
            "succeeded_syncs": total_succeeded,
            "failed_syncs": total_failed,
            "open_issues": open_issues,
            "total_imports": total_imports,
            "import_failed": total_import_failed,
            "import_review": total_import_review,
            "import_success_rate": import_success_rate,
            "connectors": connector_details,
        }

    async def _get_error_distribution(self, tenant_id: str) -> Dict[str, int]:
        summary = await self._repo.get_error_queue_summary(tenant_id)
        return summary
