"""
Scheduled Reservation Import Service — Background job orchestration for periodic
reservation pulling from connected channel managers.

Features:
- Per-connector configurable polling interval (default: 5min)
- Duplicate import job prevention (lock-based)
- Job lifecycle: pending -> running -> completed/retrying/failed
- Audit log for every lifecycle transition
- Import failure spike -> alerting engine
- Cron safety-net inventory sync
"""
import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..infrastructure.repository import ChannelManagerRepository
from .alerting_service import AlertingService
from .reservation_import_service import ReservationImportService

logger = logging.getLogger("channel_manager.application.scheduled_import")

# In-memory lock set to prevent duplicate jobs
_running_jobs: dict[str, str] = {}  # connector_id -> job_id


class ScheduledImportJob:
    """Represents a single scheduled import job with lifecycle tracking."""

    def __init__(
        self,
        tenant_id: str,
        connector_id: str,
        property_id: str = "",
        triggered_by: str = "scheduler",
    ):
        self.id = str(uuid.uuid4())
        self.tenant_id = tenant_id
        self.connector_id = connector_id
        self.property_id = property_id
        self.triggered_by = triggered_by
        self.status = "pending"
        self.created_at = datetime.now(UTC).isoformat()
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.retry_count = 0
        self.max_retries = 3
        self.error: str | None = None
        self.batch_summary: dict[str, Any] | None = None

    def to_doc(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "connector_id": self.connector_id,
            "property_id": self.property_id,
            "triggered_by": self.triggered_by,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error": self.error,
            "batch_summary": self.batch_summary,
        }


class ScheduledImportService:
    """Manages periodic reservation import jobs for all active connectors."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()
        self._import_svc = ReservationImportService(repo=self._repo)
        self._alert_svc = AlertingService(repo=self._repo)

    async def run_scheduled_import(
        self,
        tenant_id: str,
        connector_id: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a single scheduled reservation import for a connector."""
        # Duplicate job prevention
        if connector_id in _running_jobs:
            return {
                "status": "skipped",
                "reason": "duplicate_prevention",
                "existing_job_id": _running_jobs[connector_id],
                "connector_id": connector_id,
            }

        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            return {"status": "error", "reason": "connector_not_found"}
        if connector.get("status") != "active":
            return {"status": "skipped", "reason": "connector_not_active"}

        job = ScheduledImportJob(
            tenant_id=tenant_id,
            connector_id=connector_id,
            property_id=connector.get("property_id", ""),
            triggered_by="scheduler",
        )

        _running_jobs[connector_id] = job.id
        try:
            return await self._execute_job(job, actor_id)
        finally:
            _running_jobs.pop(connector_id, None)

    async def _execute_job(
        self, job: ScheduledImportJob, actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute job with retry logic and lifecycle tracking."""
        job.status = "running"
        job.started_at = datetime.now(UTC).isoformat()

        await self._store_job(job)
        await self._audit(job, AuditAction.IMPORT_JOB_STARTED, actor_id)

        while job.retry_count <= job.max_retries:
            try:
                result = await self._import_svc.pull_and_import(
                    tenant_id=job.tenant_id,
                    connector_id=job.connector_id,
                    triggered_by=job.triggered_by,
                )
                job.status = "completed"
                job.completed_at = datetime.now(UTC).isoformat()
                job.batch_summary = {
                    "total_pulled": result.get("total_pulled", 0),
                    "imported": result.get("imported", 0),
                    "duplicates": result.get("duplicates", 0),
                    "errors": result.get("errors", 0),
                    "batch_id": result.get("batch_id"),
                }
                await self._store_job(job)
                await self._audit(job, AuditAction.IMPORT_JOB_COMPLETED, actor_id)
                return {"status": "completed", "job": job.to_doc()}

            except Exception as e:
                job.error = str(e)[:500]
                job.retry_count += 1

                if job.retry_count <= job.max_retries:
                    job.status = "retrying"
                    await self._store_job(job)
                    await self._audit(job, AuditAction.IMPORT_JOB_RETRYING, actor_id, {
                        "attempt": job.retry_count,
                        "error": job.error,
                    })
                    await asyncio.sleep(min(2 ** job.retry_count, 30))
                else:
                    job.status = "failed"
                    job.completed_at = datetime.now(UTC).isoformat()
                    await self._store_job(job)
                    await self._audit(job, AuditAction.IMPORT_JOB_FAILED, actor_id, {
                        "error": job.error,
                        "total_retries": job.retry_count - 1,
                    })
                    # Alert on failure
                    await self._alert_on_failure(job)
                    return {"status": "failed", "job": job.to_doc()}

        return {"status": "failed", "job": job.to_doc()}

    async def run_all_connectors(self, tenant_id: str) -> dict[str, Any]:
        """Run scheduled import for all active connectors of a tenant."""
        connectors = await self._repo.get_connectors_by_tenant(tenant_id)
        active = [c for c in connectors if c.get("status") == "active"]
        results = []
        for c in active:
            result = await self.run_scheduled_import(tenant_id, c["id"])
            results.append({
                "connector_id": c["id"],
                "display_name": c.get("display_name", ""),
                **result,
            })
        return {
            "total_connectors": len(active),
            "results": results,
            "run_at": datetime.now(UTC).isoformat(),
        }

    async def get_import_jobs(
        self, tenant_id: str, connector_id: str | None = None,
        status: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List import jobs with optional filters."""
        from core.database import db
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if connector_id:
            query["connector_id"] = connector_id
        if status:
            query["status"] = status
        jobs = await db.cm_import_jobs.find(
            query, {"_id": 0},
        ).sort("created_at", -1).limit(limit).to_list(limit)
        return jobs

    async def get_job_detail(self, tenant_id: str, job_id: str) -> dict[str, Any] | None:
        """Get details of a specific import job."""
        from core.database import db
        return await db.cm_import_jobs.find_one(
            {"tenant_id": tenant_id, "id": job_id}, {"_id": 0},
        )

    async def retry_failed_job(self, tenant_id: str, job_id: str, actor_id: str) -> dict[str, Any]:
        """Retry a previously failed import job."""
        from core.database import db
        job_doc = await db.cm_import_jobs.find_one(
            {"tenant_id": tenant_id, "id": job_id, "status": "failed"}, {"_id": 0},
        )
        if not job_doc:
            return {"status": "error", "reason": "Job not found or not in failed state"}

        result = await self.run_scheduled_import(
            tenant_id, job_doc["connector_id"], actor_id,
        )
        return result

    async def run_safety_net_inventory_sync(self, tenant_id: str) -> dict[str, Any]:
        """
        Cron safety-net: Run inventory sync for all active connectors
        to catch any missed updates.
        """
        from .inventory_sync_service import InventorySyncService
        sync_svc = InventorySyncService(repo=self._repo)
        connectors = await self._repo.get_connectors_by_tenant(tenant_id)
        active = [c for c in connectors if c.get("status") == "active"]

        results = []
        for c in active:
            try:
                date_start = datetime.now(UTC).strftime("%Y-%m-%d")
                date_end = (datetime.now(UTC) + timedelta(days=30)).strftime("%Y-%m-%d")
                result = await sync_svc.trigger_inventory_sync(
                    tenant_id=tenant_id,
                    connector_id=c["id"],
                    date_start=date_start,
                    date_end=date_end,
                    triggered_by="cron_safety_net",
                    trigger_reason="Safety-net periodic inventory sync",
                )
                results.append({
                    "connector_id": c["id"],
                    "status": "completed",
                    "result": result,
                })
            except Exception as e:
                results.append({
                    "connector_id": c["id"],
                    "status": "failed",
                    "error": str(e)[:200],
                })

        return {
            "type": "safety_net_inventory_sync",
            "total": len(active),
            "results": results,
            "run_at": datetime.now(UTC).isoformat(),
        }

    # ─── Internal Helpers ────────────────────────────────────────────

    async def _store_job(self, job: ScheduledImportJob):
        from core.database import db
        doc = job.to_doc()
        await db.cm_import_jobs.replace_one(
            {"id": job.id}, doc, upsert=True,
        )

    async def _alert_on_failure(self, job: ScheduledImportJob):
        """Check for repeated failures and trigger alert."""
        from core.database import db
        recent_failures = await db.cm_import_jobs.count_documents({
            "tenant_id": job.tenant_id,
            "connector_id": job.connector_id,
            "status": "failed",
            "completed_at": {"$gte": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
        })
        if recent_failures >= 3:
            await self._alert_svc.check_and_fire_alert(
                tenant_id=job.tenant_id,
                trigger="reservation_import_failure_spike",
                connector_id=job.connector_id,
                metadata={
                    "failures_in_last_hour": recent_failures,
                    "last_error": job.error,
                    "job_id": job.id,
                },
            )

    async def _audit(
        self, job: ScheduledImportJob, action: AuditAction,
        actor_id: str | None = None, metadata: dict | None = None,
    ):
        log = IntegrationAuditLog(
            tenant_id=job.tenant_id,
            property_id=job.property_id,
            connector_id=job.connector_id,
            action=action,
            actor_id=actor_id or "scheduler",
            metadata={
                "job_id": job.id,
                "job_status": job.status,
                **(metadata or {}),
            },
        )
        await self._repo.create_audit_log(log.to_doc())
