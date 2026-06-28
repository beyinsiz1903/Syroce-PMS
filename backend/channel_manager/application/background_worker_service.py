"""
Background Scheduler Worker — Centralized background job orchestration.

Job Types:
  - reservation_import_job (every 5 min)
  - inventory_safety_sync (every 30 min)
  - connector_health_check (every 15 min)
  - metrics_aggregation (every 30 min)

Features:
  - Distributed lock (DB-based)
  - Duplicate job prevention
  - Retry with exponential backoff
  - Job lifecycle audit log
  - Job failure alerting
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.background_worker")

WORKER_JOBS = "cm_worker_jobs"
WORKER_LOCKS = "cm_worker_locks"
_NO_ID = {"_id": 0}

# Default intervals in seconds
DEFAULT_INTERVALS = {
    "reservation_import": 300,  # 5 min
    "inventory_safety_sync": 1800,  # 30 min
    "connector_health_check": 900,  # 15 min
    "metrics_aggregation": 1800,  # 30 min
}

MAX_RETRIES = 3


class WorkerJob:
    """Represents a single background worker job execution."""

    def __init__(self, job_type: str, tenant_id: str, connector_id: str = ""):
        self.id = str(uuid.uuid4())
        self.job_type = job_type
        self.tenant_id = tenant_id
        self.connector_id = connector_id
        self.status = "pending"
        self.created_at = datetime.now(UTC).isoformat()
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.retry_count = 0
        self.error: str | None = None
        self.result: dict[str, Any] | None = None

    def to_doc(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "job_type": self.job_type,
            "tenant_id": self.tenant_id,
            "connector_id": self.connector_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "retry_count": self.retry_count,
            "error": self.error,
            "result_summary": self.result,
        }


class BackgroundWorkerService:
    """Manages background worker jobs with locking, retry, and audit."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    # ─── Lock Management ──────────────────────────────────────────────

    async def acquire_lock(self, lock_key: str, ttl_seconds: int = 600) -> bool:
        """Acquire a distributed lock. Returns True if acquired."""
        now = datetime.now(UTC)
        expires = (now + timedelta(seconds=ttl_seconds)).isoformat()

        # Try to insert lock (atomic)
        existing = await db[WORKER_LOCKS].find_one({"lock_key": lock_key})
        if existing:
            if existing.get("expires_at", "") < now.isoformat():
                # Expired lock, take it over
                await db[WORKER_LOCKS].replace_one(
                    {"lock_key": lock_key},
                    {"lock_key": lock_key, "acquired_at": now.isoformat(), "expires_at": expires},
                )
                return True
            return False  # Lock held

        await db[WORKER_LOCKS].insert_one(
            {
                "lock_key": lock_key,
                "acquired_at": now.isoformat(),
                "expires_at": expires,
            }
        )
        return True

    async def release_lock(self, lock_key: str):
        """Release a distributed lock."""
        await db[WORKER_LOCKS].delete_one({"lock_key": lock_key})

    # ─── Job Execution ────────────────────────────────────────────────

    async def run_job(
        self,
        job_type: str,
        tenant_id: str,
        connector_id: str = "",
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a background job with locking and retry."""
        lock_key = f"worker:{job_type}:{tenant_id}:{connector_id}"
        if not await self.acquire_lock(lock_key):
            return {"status": "skipped", "reason": "lock_held", "job_type": job_type}

        job = WorkerJob(job_type, tenant_id, connector_id)
        try:
            return await self._execute_with_retry(job, actor_id)
        finally:
            await self.release_lock(lock_key)

    async def _execute_with_retry(self, job: WorkerJob, actor_id: str | None = None) -> dict[str, Any]:
        """Execute job with exponential backoff retry."""
        job.status = "running"
        job.started_at = datetime.now(UTC).isoformat()
        await self._store_job(job)
        await self._audit_job(job, "started", actor_id)

        while job.retry_count <= MAX_RETRIES:
            try:
                result = await self._dispatch_job(job)
                job.status = "completed"
                job.completed_at = datetime.now(UTC).isoformat()
                job.result = result
                await self._store_job(job)
                await self._audit_job(job, "completed", actor_id)
                return {"status": "completed", "job": job.to_doc()}
            except Exception as e:
                job.error = str(e)[:500]
                job.retry_count += 1
                if job.retry_count <= MAX_RETRIES:
                    job.status = "retrying"
                    await self._store_job(job)
                    await self._audit_job(job, "retrying", actor_id, {"error": job.error, "attempt": job.retry_count})
                    await asyncio.sleep(min(2**job.retry_count, 30))
                else:
                    job.status = "failed"
                    job.completed_at = datetime.now(UTC).isoformat()
                    await self._store_job(job)
                    await self._audit_job(job, "failed", actor_id, {"error": job.error})
                    await self._alert_on_failure(job)
                    return {"status": "failed", "job": job.to_doc()}

        return {"status": "failed", "job": job.to_doc()}

    async def _dispatch_job(self, job: WorkerJob) -> dict[str, Any]:
        """Route job to the appropriate handler."""
        if job.job_type == "reservation_import":
            return await self._run_reservation_import(job)
        elif job.job_type == "inventory_safety_sync":
            return await self._run_inventory_safety_sync(job)
        elif job.job_type == "connector_health_check":
            return await self._run_connector_health_check(job)
        elif job.job_type == "metrics_aggregation":
            return await self._run_metrics_aggregation(job)
        else:
            raise ValueError(f"Unknown job type: {job.job_type}")

    # ─── Job Handlers ─────────────────────────────────────────────────

    async def _run_reservation_import(self, job: WorkerJob) -> dict[str, Any]:
        from .scheduled_import_service import ScheduledImportService

        svc = ScheduledImportService(repo=self._repo)
        if job.connector_id:
            return await svc.run_scheduled_import(job.tenant_id, job.connector_id)
        return await svc.run_all_connectors(job.tenant_id)

    async def _run_inventory_safety_sync(self, job: WorkerJob) -> dict[str, Any]:
        from .scheduled_import_service import ScheduledImportService

        svc = ScheduledImportService(repo=self._repo)
        return await svc.run_safety_net_inventory_sync(job.tenant_id)

    async def _run_connector_health_check(self, job: WorkerJob) -> dict[str, Any]:
        from .connector_health_service import ConnectorHealthService

        svc = ConnectorHealthService(repo=self._repo)
        if job.connector_id:
            return await svc.get_connector_health(job.tenant_id, job.connector_id)
        return await svc.get_all_health(job.tenant_id)

    async def _run_metrics_aggregation(self, job: WorkerJob) -> dict[str, Any]:
        from .historical_metrics_service import HistoricalMetricsService

        svc = HistoricalMetricsService(repo=self._repo)
        connectors = await self._repo.get_connectors_by_tenant(job.tenant_id)
        aggregated = 0
        for c in connectors:
            try:
                await svc.record_snapshot(job.tenant_id, c["id"])
                aggregated += 1
            except Exception as e:
                logger.warning("Metrics aggregation failed for %s: %s", c["id"], e)
        return {"aggregated_connectors": aggregated, "total": len(connectors)}

    # ─── Bulk Operations ──────────────────────────────────────────────

    async def run_all_scheduled(self, tenant_id: str) -> dict[str, Any]:
        """Run all scheduled job types for a tenant."""
        results = {}
        for job_type in DEFAULT_INTERVALS:
            result = await self.run_job(job_type, tenant_id)
            results[job_type] = result
        return {"results": results, "run_at": datetime.now(UTC).isoformat()}

    # ─── Job History ──────────────────────────────────────────────────

    async def get_jobs(
        self,
        tenant_id: str,
        job_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        q: dict[str, Any] = {"tenant_id": tenant_id}
        if job_type:
            q["job_type"] = job_type
        if status:
            q["status"] = status
        return await db[WORKER_JOBS].find(q, _NO_ID).sort("created_at", -1).limit(limit).to_list(limit)

    async def get_job_stats(self, tenant_id: str) -> dict[str, Any]:
        """Get statistics for worker jobs."""
        pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {
                "$group": {
                    "_id": {"job_type": "$job_type", "status": "$status"},
                    "count": {"$sum": 1},
                }
            },
        ]
        stats = {}
        async for doc in db[WORKER_JOBS].aggregate(pipeline):
            jt = doc["_id"]["job_type"]
            st = doc["_id"]["status"]
            if jt not in stats:
                stats[jt] = {}
            stats[jt][st] = doc["count"]
        return {"stats": stats, "intervals": DEFAULT_INTERVALS}

    # ─── Internal Helpers ─────────────────────────────────────────────

    async def _store_job(self, job: WorkerJob):
        doc = job.to_doc()
        await db[WORKER_JOBS].replace_one({"id": job.id}, doc, upsert=True)

    async def _audit_job(
        self,
        job: WorkerJob,
        action: str,
        actor_id: str | None = None,
        metadata: dict | None = None,
    ):
        log = IntegrationAuditLog(
            tenant_id=job.tenant_id,
            connector_id=job.connector_id or None,
            action=AuditAction.SCHEDULED_SYNC_RUN,
            actor_id=actor_id or "background_worker",
            metadata={
                "job_id": job.id,
                "job_type": job.job_type,
                "job_action": action,
                **(metadata or {}),
            },
        )
        await self._repo.create_audit_log(log.to_doc())

    async def _alert_on_failure(self, job: WorkerJob):
        from .alerting_service import AlertingService

        alert_svc = AlertingService(repo=self._repo)
        await alert_svc.check_and_fire_alert(
            tenant_id=job.tenant_id,
            trigger=f"worker_{job.job_type}_failure",
            connector_id=job.connector_id or None,
            metadata={"job_id": job.id, "error": job.error},
        )
