"""
Phase 7 — Pilot Monitoring Pack Service
=========================================
Provides tenant-specific monitoring dashboards, operational alerts,
and daily/weekly reports for pilot hotels.
"""
import logging
from datetime import UTC, datetime, timedelta

from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)

OPERATIONAL_ALERTS = [
    {"id": "reservation_ingest_failure", "name": "Reservation Ingest Failure", "severity": "critical", "threshold": "any failure"},
    {"id": "ari_sync_failure", "name": "ARI Sync Failure", "severity": "critical", "threshold": "> 1 failure/hour"},
    {"id": "queue_backlog", "name": "Queue Backlog", "severity": "high", "threshold": "> 100 items"},
    {"id": "night_audit_delay", "name": "Night Audit Delay", "severity": "high", "threshold": "> 30 min after scheduled"},
    {"id": "drift_detection_spike", "name": "Drift Detection Spike", "severity": "warning", "threshold": "> 2% drift"},
    {"id": "pos_transaction_failure", "name": "POS Transaction Failure", "severity": "high", "threshold": "any failure"},
    {"id": "folio_imbalance", "name": "Folio Imbalance Detected", "severity": "warning", "threshold": "balance mismatch"},
    {"id": "worker_stall", "name": "Worker Stall", "severity": "high", "threshold": "no heartbeat > 5min"},
]


class PilotMonitoringService:
    """Provides monitoring data for pilot hotel tenants."""

    def __init__(self):
        from core.database import db
        self._db = db

    async def get_tenant_dashboard(self, ctx: OperationContext) -> ServiceResult:
        """Get comprehensive monitoring dashboard for a pilot tenant."""
        now = datetime.now(UTC)
        h24 = (now - timedelta(hours=24)).isoformat()

        dashboard = {
            "reservation_metrics": await self._get_reservation_metrics(ctx, h24),
            "sync_metrics": await self._get_sync_metrics(ctx, h24),
            "queue_health": await self._get_queue_health(ctx),
            "incident_summary": await self._get_incident_summary(ctx, h24),
            "night_audit_status": await self._get_night_audit_status(ctx),
            "pos_metrics": await self._get_pos_metrics(ctx, h24),
            "alerts": await self._get_active_alerts(ctx),
            "generated_at": now.isoformat(),
        }

        return ServiceResult.success(dashboard)

    async def get_operational_alerts_config(self) -> ServiceResult:
        return ServiceResult.success({"alerts": OPERATIONAL_ALERTS})

    async def generate_daily_report(self, ctx: OperationContext) -> ServiceResult:
        """Generate daily operations report."""
        now = datetime.now(UTC)
        h24 = (now - timedelta(hours=24)).isoformat()

        report = {
            "report_type": "daily_operations",
            "period_start": h24,
            "period_end": now.isoformat(),
            "tenant_id": ctx.tenant_id,
            "sections": {
                "reservations": {
                    "new": await self._db.bookings.count_documents({"tenant_id": ctx.tenant_id, "created_at": {"$gte": h24}}),
                    "checkins": await self._db.bookings.count_documents({"tenant_id": ctx.tenant_id, "status": "checked_in", "check_in_at": {"$gte": h24}}),
                    "checkouts": await self._db.bookings.count_documents({"tenant_id": ctx.tenant_id, "status": "checked_out", "check_out_at": {"$gte": h24}}),
                    "cancellations": await self._db.bookings.count_documents({"tenant_id": ctx.tenant_id, "status": "cancelled", "cancelled_at": {"$gte": h24}}),
                },
                "sync_accuracy": {
                    "total_syncs": await self._db.channel_sync_logs.count_documents({"tenant_id": ctx.tenant_id, "synced_at": {"$gte": h24}}),
                    "failed_syncs": await self._db.channel_sync_logs.count_documents({"tenant_id": ctx.tenant_id, "status": "failed", "synced_at": {"$gte": h24}}),
                },
                "audit_events": await self._db.audit_logs.count_documents({"tenant_id": ctx.tenant_id, "timestamp": {"$gte": h24}}),
                "incidents": await self._db.incidents.count_documents({"tenant_id": ctx.tenant_id, "created_at": {"$gte": h24}}),
            },
            "generated_at": now.isoformat(),
        }

        await self._db.pilot_reports.insert_one({
            "tenant_id": ctx.tenant_id,
            "report": report,
            "generated_at": now.isoformat(),
        })

        return ServiceResult.success(report)

    async def get_report_history(self, ctx: OperationContext, limit: int = 10) -> ServiceResult:
        reports = await self._db.pilot_reports.find(
            {"tenant_id": ctx.tenant_id}, {"_id": 0}
        ).sort("generated_at", -1).limit(limit).to_list(limit)
        return ServiceResult.success({"reports": reports, "count": len(reports)})

    async def _get_reservation_metrics(self, ctx: OperationContext, since: str) -> dict:
        total = await self._db.bookings.count_documents({"tenant_id": ctx.tenant_id})
        recent = await self._db.bookings.count_documents({"tenant_id": ctx.tenant_id, "created_at": {"$gte": since}})
        checked_in = await self._db.bookings.count_documents({"tenant_id": ctx.tenant_id, "status": "checked_in"})
        return {"total": total, "last_24h": recent, "currently_checked_in": checked_in}

    async def _get_sync_metrics(self, ctx: OperationContext, since: str) -> dict:
        total = await self._db.channel_sync_logs.count_documents({"tenant_id": ctx.tenant_id, "synced_at": {"$gte": since}})
        failed = await self._db.channel_sync_logs.count_documents({"tenant_id": ctx.tenant_id, "status": "failed", "synced_at": {"$gte": since}})
        success_rate = round((1 - failed / max(total, 1)) * 100, 1) if total > 0 else 100.0
        return {"total_syncs_24h": total, "failed_syncs_24h": failed, "success_rate": success_rate}

    async def _get_queue_health(self, ctx: OperationContext) -> dict:
        pending = await self._db.task_queue.count_documents({"tenant_id": ctx.tenant_id, "status": "pending"})
        failed = await self._db.task_queue.count_documents({"tenant_id": ctx.tenant_id, "status": "failed"})
        return {"pending_tasks": pending, "failed_tasks": failed, "healthy": pending < 100}

    async def _get_incident_summary(self, ctx: OperationContext, since: str) -> dict:
        total = await self._db.incidents.count_documents({"tenant_id": ctx.tenant_id, "created_at": {"$gte": since}})
        active = await self._db.incidents.count_documents({"tenant_id": ctx.tenant_id, "status": {"$nin": ["resolved"]}})
        return {"total_24h": total, "active": active}

    async def _get_night_audit_status(self, ctx: OperationContext) -> dict:
        latest = await self._db.night_audit_runs.find_one(
            {"tenant_id": ctx.tenant_id}, {"_id": 0, "status": 1, "business_date": 1, "duration_ms": 1},
            sort=[("started_at", -1)],
        )
        return latest or {"status": "no_runs", "business_date": None}

    async def _get_pos_metrics(self, ctx: OperationContext, since: str) -> dict:
        orders = await self._db.pos_orders.count_documents({"tenant_id": ctx.tenant_id, "created_at": {"$gte": since}})
        return {"orders_24h": orders}

    async def _get_active_alerts(self, ctx: OperationContext) -> list:
        alerts = await self._db.enriched_alerts.find(
            {"tenant_id": ctx.tenant_id, "status": {"$ne": "resolved"}}, {"_id": 0}
        ).sort("fired_at", -1).limit(10).to_list(10)
        return alerts


pilot_monitoring_service = PilotMonitoringService()
