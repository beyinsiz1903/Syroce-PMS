"""
Historical Metrics Service — Phase 1: Time-based metric snapshots and trend analysis.

Collections: cm_metrics_snapshots
Stores: sync success, ack success, retry, latency, error types, mapping validation,
        health score, reconciliation issue counts over time.
Retention: 30d (hourly), 90d (daily), 1y (weekly)
Aggregation: daily, weekly, monthly
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from core.database import db
from ..domain.models.audit import IntegrationAuditLog, AuditAction
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.historical_metrics")

SNAPSHOTS = "cm_metrics_snapshots"


class HistoricalMetricsService:
    """Collects, stores, and queries historical metrics snapshots."""

    def __init__(self, repo: Optional[ChannelManagerRepository] = None):
        self._repo = repo or ChannelManagerRepository()

    # ─── Snapshot Creation ─────────────────────────────────────────────

    async def create_snapshot(self, tenant_id: str, connector_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a metrics snapshot for all connectors or a specific one."""
        connectors = await self._repo.get_connectors_by_tenant(tenant_id)
        if connector_id:
            connectors = [c for c in connectors if c.get("id") == connector_id]

        snapshots = []
        now = datetime.now(timezone.utc)

        for c in connectors:
            cid = c.get("id", "")
            metrics = await self._repo.get_sync_metrics(tenant_id, cid)
            error_summary = await self._repo.get_error_queue_summary(tenant_id, cid)
            from ..application.reconciliation_service import ReconciliationService
            recon = ReconciliationService(self._repo)
            health = await recon.get_health_score(tenant_id, cid)

            # ACK metrics
            total_imports = await db.cm_imported_reservations.count_documents(
                {"tenant_id": tenant_id, "connector_id": cid}
            )
            ack_sent = await db.cm_imported_reservations.count_documents(
                {"tenant_id": tenant_id, "connector_id": cid, "ack_status": "ack_sent"}
            )
            ack_failed = await db.cm_imported_reservations.count_documents(
                {"tenant_id": tenant_id, "connector_id": cid, "ack_status": "ack_failed"}
            )

            # Sync stats
            jobs = metrics.get("sync_jobs", {})
            total_sync = sum(jobs.values())
            succeeded_sync = jobs.get("succeeded", 0)
            failed_sync = jobs.get("failed", 0)
            retry_jobs = sum(1 for _ in await db.cm_sync_jobs.find(
                {"tenant_id": tenant_id, "connector_id": cid, "retry_count": {"$gt": 0}},
                {"_id": 0, "id": 1}
            ).to_list(1000))

            # Mapping
            mappings = await self._repo.get_mappings(tenant_id, cid)
            valid_mappings = sum(1 for m in mappings if m.get("validation_status") != "invalid")

            # Recon issues
            recon_summary = await self._repo.get_reconciliation_summary(tenant_id, cid)

            snapshot = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "connector_id": cid,
                "property_id": c.get("property_id", ""),
                "provider": c.get("provider", ""),
                "granularity": "hourly",
                "timestamp": now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
                "hour": now.strftime("%Y-%m-%dT%H"),
                "metrics": {
                    "health_score": health.get("health_score", 0),
                    "sync_total": total_sync,
                    "sync_succeeded": succeeded_sync,
                    "sync_failed": failed_sync,
                    "sync_success_rate": round(succeeded_sync / max(total_sync, 1) * 100, 1),
                    "ack_total": total_imports,
                    "ack_sent": ack_sent,
                    "ack_failed": ack_failed,
                    "ack_success_rate": round(ack_sent / max(total_imports, 1) * 100, 1),
                    "retry_count": retry_jobs,
                    "retry_rate": round(retry_jobs / max(total_sync, 1) * 100, 1),
                    "mapping_total": len(mappings),
                    "mapping_valid": valid_mappings,
                    "mapping_validation_rate": round(valid_mappings / max(len(mappings), 1) * 100, 1),
                    "error_queue_total": error_summary.get("total", 0),
                    "error_sync_failed": error_summary.get("sync_failed", 0),
                    "error_import_failed": error_summary.get("import_failed", 0),
                    "error_ack_failed": error_summary.get("ack_failed", 0),
                    "recon_total_open": recon_summary.get("total_open", 0),
                    "recon_by_severity": recon_summary.get("by_severity", {}),
                },
                "created_at": now.isoformat(),
            }
            await db[SNAPSHOTS].insert_one(snapshot)
            snapshot.pop("_id", None)
            snapshots.append(snapshot)

        return {"snapshots_created": len(snapshots), "timestamp": now.isoformat()}

    # ─── Trend Calculation ─────────────────────────────────────────────

    async def get_trends(
        self, tenant_id: str, connector_id: Optional[str] = None,
        period: str = "7d", metric_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get trend data for specified metrics over a period."""
        days = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365}.get(period, 7)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        q: Dict[str, Any] = {"tenant_id": tenant_id, "timestamp": {"$gte": cutoff}}
        if connector_id:
            q["connector_id"] = connector_id

        docs = await db[SNAPSHOTS].find(q, {"_id": 0}).sort("timestamp", 1).to_list(5000)

        if not metric_keys:
            metric_keys = [
                "health_score", "sync_success_rate", "ack_success_rate",
                "retry_rate", "mapping_validation_rate", "error_queue_total",
                "recon_total_open",
            ]

        # Aggregate by date
        by_date: Dict[str, Dict[str, List]] = {}
        for doc in docs:
            date = doc.get("date", "")
            if date not in by_date:
                by_date[date] = {k: [] for k in metric_keys}
            m = doc.get("metrics", {})
            for k in metric_keys:
                if k in m:
                    by_date[date][k].append(m[k])

        trend_data = []
        for date in sorted(by_date.keys()):
            point = {"date": date}
            for k in metric_keys:
                vals = by_date[date][k]
                point[k] = round(sum(vals) / max(len(vals), 1), 1) if vals else 0
            trend_data.append(point)

        return {
            "period": period,
            "metric_keys": metric_keys,
            "data_points": len(trend_data),
            "trends": trend_data,
        }

    # ─── History Query ─────────────────────────────────────────────────

    async def get_history(
        self, tenant_id: str, connector_id: Optional[str] = None,
        period: str = "7d", limit: int = 500,
    ) -> Dict[str, Any]:
        """Get raw snapshot history."""
        days = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365}.get(period, 7)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        q: Dict[str, Any] = {"tenant_id": tenant_id, "timestamp": {"$gte": cutoff}}
        if connector_id:
            q["connector_id"] = connector_id

        docs = await db[SNAPSHOTS].find(q, {"_id": 0}).sort("timestamp", -1).to_list(limit)
        return {"snapshots": docs, "count": len(docs), "period": period}

    async def get_history_by_property(
        self, tenant_id: str, property_id: str,
        period: str = "7d", limit: int = 500,
    ) -> Dict[str, Any]:
        """Get snapshot history for a specific property."""
        days = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365}.get(period, 7)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        q = {"tenant_id": tenant_id, "property_id": property_id, "timestamp": {"$gte": cutoff}}
        docs = await db[SNAPSHOTS].find(q, {"_id": 0}).sort("timestamp", -1).to_list(limit)
        return {"snapshots": docs, "count": len(docs), "period": period, "property_id": property_id}

    # ─── Retention Cleanup ─────────────────────────────────────────────

    async def run_retention_cleanup(self, tenant_id: str) -> Dict[str, Any]:
        """Clean up old snapshots based on retention policy."""
        now = datetime.now(timezone.utc)
        deleted = {"hourly": 0, "daily": 0, "weekly": 0}

        # Hourly snapshots older than 30 days
        cutoff_30d = (now - timedelta(days=30)).isoformat()
        r = await db[SNAPSHOTS].delete_many({
            "tenant_id": tenant_id, "granularity": "hourly", "timestamp": {"$lt": cutoff_30d}
        })
        deleted["hourly"] = r.deleted_count

        # Daily snapshots older than 90 days
        cutoff_90d = (now - timedelta(days=90)).isoformat()
        r = await db[SNAPSHOTS].delete_many({
            "tenant_id": tenant_id, "granularity": "daily", "timestamp": {"$lt": cutoff_90d}
        })
        deleted["daily"] = r.deleted_count

        # Weekly snapshots older than 1 year
        cutoff_1y = (now - timedelta(days=365)).isoformat()
        r = await db[SNAPSHOTS].delete_many({
            "tenant_id": tenant_id, "granularity": "weekly", "timestamp": {"$lt": cutoff_1y}
        })
        deleted["weekly"] = r.deleted_count

        return {"deleted": deleted, "cleaned_at": now.isoformat()}

    # ─── Daily Aggregation ─────────────────────────────────────────────

    async def create_daily_aggregation(self, tenant_id: str, date: Optional[str] = None) -> Dict[str, Any]:
        """Aggregate hourly snapshots into a daily snapshot."""
        if not date:
            date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

        q = {"tenant_id": tenant_id, "granularity": "hourly", "date": date}
        hourly_docs = await db[SNAPSHOTS].find(q, {"_id": 0}).to_list(5000)

        if not hourly_docs:
            return {"aggregated": 0, "date": date}

        # Group by connector
        by_connector: Dict[str, List] = {}
        for doc in hourly_docs:
            cid = doc.get("connector_id", "")
            if cid not in by_connector:
                by_connector[cid] = []
            by_connector[cid].append(doc)

        created = 0
        for cid, docs in by_connector.items():
            metric_keys = list(docs[0].get("metrics", {}).keys())
            avg_metrics = {}
            for k in metric_keys:
                vals = [d.get("metrics", {}).get(k, 0) for d in docs if isinstance(d.get("metrics", {}).get(k), (int, float))]
                avg_metrics[k] = round(sum(vals) / max(len(vals), 1), 1) if vals else 0
            # Keep dict values as-is (e.g., recon_by_severity)
            for k in metric_keys:
                if isinstance(docs[0].get("metrics", {}).get(k), dict):
                    avg_metrics[k] = docs[-1].get("metrics", {}).get(k, {})

            daily = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "connector_id": cid,
                "property_id": docs[0].get("property_id", ""),
                "provider": docs[0].get("provider", ""),
                "granularity": "daily",
                "timestamp": f"{date}T23:59:59+00:00",
                "date": date,
                "hour": "",
                "metrics": avg_metrics,
                "sample_count": len(docs),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db[SNAPSHOTS].insert_one(daily)
            daily.pop("_id", None)
            created += 1

        return {"aggregated": created, "date": date}
