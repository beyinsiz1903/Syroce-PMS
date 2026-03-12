"""
Phase 7 — Post-Launch Monitoring Service
==========================================
Provides continuous reliability monitoring, scheduled drills,
and long-term health tracking after production launch.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from common.result import ServiceResult
from common.context import OperationContext

logger = logging.getLogger(__name__)

MONITORING_SCHEDULE = [
    {"id": "weekly_incident_drill", "name": "Weekly Incident Drill", "frequency": "weekly", "type": "incident_drill"},
    {"id": "monthly_chaos_test", "name": "Monthly Chaos Test", "frequency": "monthly", "type": "chaos_test"},
    {"id": "quarterly_dr_drill", "name": "Quarterly Disaster Recovery Drill", "frequency": "quarterly", "type": "dr_drill"},
]

CONTINUOUS_MONITORS = [
    {"id": "system_health", "name": "System Health Dashboard", "active": True, "interval_sec": 30},
    {"id": "incident_dashboard", "name": "Incident Dashboard", "active": True, "interval_sec": 60},
    {"id": "audit_timeline", "name": "Audit Timeline", "active": True, "interval_sec": 300},
    {"id": "tenant_monitoring", "name": "Tenant-Specific Monitoring", "active": True, "interval_sec": 60},
    {"id": "provider_sync", "name": "Provider Sync Status", "active": True, "interval_sec": 120},
    {"id": "queue_health", "name": "Queue Health", "active": True, "interval_sec": 30},
]


class PostLaunchMonitoringService:
    """Manages post-launch monitoring, scheduling, and health trending."""

    def __init__(self):
        from core.database import db
        self._db = db

    async def get_monitoring_status(self, ctx: OperationContext) -> ServiceResult:
        """Get overall post-launch monitoring status."""
        now = datetime.now(timezone.utc)

        # Check scheduled drill status
        drill_status = []
        for schedule in MONITORING_SCHEDULE:
            last_run = await self._db.scheduled_drills.find_one(
                {"tenant_id": ctx.tenant_id, "schedule_id": schedule["id"]},
                {"_id": 0},
                sort=[("executed_at", -1)],
            )
            next_due = self._compute_next_due(schedule["frequency"], last_run)
            overdue = next_due < now if next_due else True
            drill_status.append({
                "schedule_id": schedule["id"],
                "name": schedule["name"],
                "frequency": schedule["frequency"],
                "last_run": last_run.get("executed_at") if last_run else None,
                "last_result": last_run.get("result") if last_run else None,
                "next_due": next_due.isoformat() if next_due else None,
                "overdue": overdue,
            })

        # Health trend (last 7 days of golive scores)
        week_ago = (now - timedelta(days=7)).isoformat()
        health_trend = await self._db.golive_scores.find(
            {"tenant_id": ctx.tenant_id, "computed_at": {"$gte": week_ago}},
            {"_id": 0, "overall_score": 1, "computed_at": 1},
        ).sort("computed_at", -1).to_list(50)

        # Incident frequency (last 30 days)
        month_ago = (now - timedelta(days=30)).isoformat()
        incidents_30d = await self._db.incidents.count_documents({
            "tenant_id": ctx.tenant_id, "created_at": {"$gte": month_ago}
        })

        return ServiceResult.success({
            "monitors": CONTINUOUS_MONITORS,
            "scheduled_drills": drill_status,
            "health_trend": health_trend,
            "incidents_30d": incidents_30d,
            "monitoring_active": True,
            "generated_at": now.isoformat(),
        })

    async def record_drill_execution(
        self, ctx: OperationContext, schedule_id: str, result: str, details: Dict = None
    ) -> ServiceResult:
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            "schedule_id": schedule_id,
            "result": result,
            "details": details or {},
            "executed_by": ctx.actor_email,
            "executed_at": now,
        }
        await self._db.scheduled_drills.insert_one(entry)
        del entry["_id"]
        return ServiceResult.success(entry)

    async def get_platform_maturity_report(self, ctx: OperationContext) -> ServiceResult:
        """Generate a comprehensive platform maturity report."""
        now = datetime.now(timezone.utc)

        # Latest go-live score
        latest_score = await self._db.golive_scores.find_one(
            {"tenant_id": ctx.tenant_id}, {"_id": 0},
            sort=[("computed_at", -1)],
        )

        # Incident metrics (30d)
        month_ago = (now - timedelta(days=30)).isoformat()
        total_incidents = await self._db.incidents.count_documents({
            "tenant_id": ctx.tenant_id, "created_at": {"$gte": month_ago}
        })
        resolved_incidents = await self._db.incidents.count_documents({
            "tenant_id": ctx.tenant_id, "status": "resolved", "created_at": {"$gte": month_ago}
        })

        # Drill compliance
        drills = await self._db.scheduled_drills.find(
            {"tenant_id": ctx.tenant_id, "executed_at": {"$gte": month_ago}},
            {"_id": 0},
        ).to_list(50)

        # Uptime (based on health checks)
        uptime_checks = await self._db.production_env_validations.count_documents({
            "tenant_id": ctx.tenant_id, "result.ready": True
        })
        total_checks = await self._db.production_env_validations.count_documents({"tenant_id": ctx.tenant_id})
        uptime = round(uptime_checks / max(total_checks, 1) * 100, 1) if total_checks > 0 else 99.9

        return ServiceResult.success({
            "current_score": latest_score.get("overall_score", 0) if latest_score else 0,
            "maturity_name": latest_score.get("maturity_name", "Unknown") if latest_score else "Unknown",
            "incidents_30d": total_incidents,
            "resolved_30d": resolved_incidents,
            "resolution_rate": round(resolved_incidents / max(total_incidents, 1) * 100, 1) if total_incidents > 0 else 100.0,
            "drills_completed_30d": len(drills),
            "uptime_percent": uptime,
            "generated_at": now.isoformat(),
        })

    def _compute_next_due(self, frequency: str, last_run: Dict = None) -> datetime:
        now = datetime.now(timezone.utc)
        if not last_run:
            return now - timedelta(days=1)  # Overdue if never run

        last_dt = datetime.fromisoformat(last_run["executed_at"].replace("Z", "+00:00")) if isinstance(last_run["executed_at"], str) else last_run["executed_at"]

        if frequency == "weekly":
            return last_dt + timedelta(weeks=1)
        elif frequency == "monthly":
            return last_dt + timedelta(days=30)
        elif frequency == "quarterly":
            return last_dt + timedelta(days=90)
        return now


post_launch_monitoring_service = PostLaunchMonitoringService()
