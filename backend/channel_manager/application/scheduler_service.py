"""
Scheduled Inventory Sync Safety Net - Periodic checks for stale/stuck sync.

Runs per-property and performs:
  - Stale pending job detection
  - Retryable failed job requeue
  - Missing snapshot detection
  - Drift detection (PMS vs snapshot)

Rule: Full refresh is NOT default. Incremental requeue only.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..domain.models.sync import SyncJobStatus
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.scheduler_service")

STALE_JOB_HOURS = 2
MAX_AUTO_RETRIES = 2
SNAPSHOT_STALENESS_HOURS = 48


class SchedulerService:
    """Scheduled inventory sync safety net with audit and metrics."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    async def run_scheduled_check(
        self,
        tenant_id: str,
        connector_id: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Run scheduled safety net check for a single connector."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            raise ValueError("Connector not found")
        if connector.get("status") != "active":
            return {"connector_id": connector_id, "skipped": True, "reason": "Connector not active"}

        property_id = connector.get("property_id", "")
        actions_taken: list[dict[str, Any]] = []

        # Check 1: Stale pending jobs
        stale_pending = await self._check_stale_pending_jobs(tenant_id, connector_id)
        actions_taken.extend(stale_pending)

        # Check 2: Retryable failed jobs
        retryable = await self._check_retryable_failed_jobs(tenant_id, connector_id)
        actions_taken.extend(retryable)

        # Check 3: Missing snapshots
        missing_snaps = await self._check_missing_snapshots(tenant_id, connector_id, property_id)
        actions_taken.extend(missing_snaps)

        # Check 4: Drift detection
        drift_actions = await self._check_drift(tenant_id, connector_id, property_id)
        actions_taken.extend(drift_actions)

        # Audit
        await self._audit(
            tenant_id,
            property_id,
            connector_id,
            AuditAction.SCHEDULED_SYNC_RUN,
            actor_id,
            {
                "actions_taken": len(actions_taken),
                "action_types": list({a["type"] for a in actions_taken}),
            },
        )

        return {
            "connector_id": connector_id,
            "property_id": property_id,
            "actions_taken": actions_taken,
            "total_actions": len(actions_taken),
            "metrics": {
                "stale_jobs": sum(1 for a in actions_taken if a["type"] == "stale_job_failed"),
                "requeued_jobs": sum(1 for a in actions_taken if a["type"] == "failed_job_requeued"),
                "missing_snapshots": sum(1 for a in actions_taken if a["type"] == "missing_snapshot"),
                "drift_detected": any(a["type"] == "drift_detected" for a in actions_taken),
            },
            "run_at": datetime.now(UTC).isoformat(),
        }

    async def run_all_connectors(self, tenant_id: str) -> dict[str, Any]:
        """Run scheduled check for all active connectors of a tenant."""
        connectors = await self._repo.get_connectors_by_tenant(tenant_id, status="active")
        results = []
        for c in connectors:
            try:
                result = await self.run_scheduled_check(tenant_id, c["id"])
                results.append(result)
            except Exception as e:
                results.append(
                    {
                        "connector_id": c["id"],
                        "error": str(e)[:200],
                    }
                )
        return {
            "connectors_checked": len(results),
            "results": results,
            "run_at": datetime.now(UTC).isoformat(),
        }

    # ------------------------------------------------------------------ #
    #  Stale Pending Jobs                                                  #
    # ------------------------------------------------------------------ #

    async def _check_stale_pending_jobs(
        self,
        tenant_id: str,
        connector_id: str,
    ) -> list[dict[str, Any]]:
        """Find pending/dispatched jobs older than threshold and mark failed."""
        threshold = (datetime.now(UTC) - timedelta(hours=STALE_JOB_HOURS)).isoformat()
        actions = []

        jobs = await self._repo.get_sync_jobs(tenant_id, connector_id, limit=200)
        for j in jobs:
            status = j.get("status", "")
            created = j.get("created_at", "")
            if status in ("pending", "dispatched") and created and created < threshold:
                await self._repo.update_sync_job(
                    j["id"],
                    {
                        "status": SyncJobStatus.FAILED.value,
                        "last_error": f"Stale: {status} for >{STALE_JOB_HOURS}h, marked failed by scheduler",
                        "completed_at": datetime.now(UTC).isoformat(),
                    },
                )
                actions.append(
                    {
                        "type": "stale_job_failed",
                        "job_id": j["id"],
                        "original_status": status,
                        "age_hours": STALE_JOB_HOURS,
                    }
                )
        return actions

    # ------------------------------------------------------------------ #
    #  Retryable Failed Jobs                                               #
    # ------------------------------------------------------------------ #

    async def _check_retryable_failed_jobs(
        self,
        tenant_id: str,
        connector_id: str,
    ) -> list[dict[str, Any]]:
        """Requeue failed jobs that haven't exhausted retries."""
        actions = []
        jobs = await self._repo.get_sync_jobs(tenant_id, connector_id, limit=200)
        for j in jobs:
            if j.get("status") != "failed":
                continue
            retry_count = j.get("retry_count", 0)
            if retry_count >= MAX_AUTO_RETRIES:
                continue
            # Only requeue jobs that failed in the last 24h
            completed = j.get("completed_at", "")
            if not completed:
                continue
            try:
                completed_dt = datetime.fromisoformat(completed.replace("Z", "+00:00"))
                age = (datetime.now(UTC) - completed_dt).total_seconds() / 3600
                if age > 24:
                    continue
            except (ValueError, TypeError):
                continue

            await self._repo.update_sync_job(
                j["id"],
                {
                    "status": SyncJobStatus.PENDING.value,
                    "retry_count": retry_count + 1,
                    "last_error": None,
                    "completed_at": None,
                },
            )
            actions.append(
                {
                    "type": "failed_job_requeued",
                    "job_id": j["id"],
                    "retry_count": retry_count + 1,
                }
            )

            await self._audit(
                tenant_id,
                "",
                connector_id,
                AuditAction.SCHEDULED_SYNC_REQUEUED,
                metadata={
                    "job_id": j["id"],
                    "retry_count": retry_count + 1,
                },
            )
        return actions

    # ------------------------------------------------------------------ #
    #  Missing Snapshots                                                   #
    # ------------------------------------------------------------------ #

    async def _check_missing_snapshots(
        self,
        tenant_id: str,
        connector_id: str,
        property_id: str,
    ) -> list[dict[str, Any]]:
        """Find room types with no sync snapshot for today."""
        actions = []
        from ..application.mapping_service import MappingService

        mapping_svc = MappingService(self._repo)
        room_lookup = await mapping_svc.get_mapping_lookup(tenant_id, connector_id, "room_type")

        today = datetime.now(UTC).date().isoformat()
        for pms_rt in room_lookup:
            snapshot = await self._repo.get_sync_snapshot(tenant_id, connector_id, pms_rt, today)
            if not snapshot:
                actions.append(
                    {
                        "type": "missing_snapshot",
                        "room_type_id": pms_rt,
                        "date": today,
                    }
                )
        return actions

    # ------------------------------------------------------------------ #
    #  Drift Detection                                                     #
    # ------------------------------------------------------------------ #

    async def _check_drift(
        self,
        tenant_id: str,
        connector_id: str,
        property_id: str,
    ) -> list[dict[str, Any]]:
        """Lightweight drift detection for today."""
        actions = []
        from ..application.mapping_service import MappingService

        mapping_svc = MappingService(self._repo)
        room_lookup = await mapping_svc.get_mapping_lookup(tenant_id, connector_id, "room_type")
        if not room_lookup:
            return actions

        today = datetime.now(UTC).date().isoformat()
        rooms = await db.rooms.find(
            {"tenant_id": tenant_id, "property_id": property_id, "status": {"$ne": "out_of_service"}},
            {"_id": 0, "room_type": 1},
        ).to_list(1000)
        rt_counts: dict[str, int] = {}
        for r in rooms:
            rt = r.get("room_type", "")
            if rt and rt in room_lookup:
                rt_counts[rt] = rt_counts.get(rt, 0) + 1

        bookings = await db.bookings.find(
            {
                "tenant_id": tenant_id,
                "check_in": {"$lte": today},
                "check_out": {"$gt": today},
                "status": {"$nin": ["cancelled", "no_show"]},
            },
            {"_id": 0, "room_type": 1},
        ).to_list(5000)

        drift_count = 0
        for rt, total in rt_counts.items():
            occupied = sum(1 for b in bookings if b.get("room_type") == rt)
            pms_avail = max(0, total - occupied)
            snapshot = await self._repo.get_sync_snapshot(tenant_id, connector_id, rt, today)
            if snapshot and snapshot.get("available") is not None:
                if pms_avail != snapshot["available"]:
                    drift_count += 1

        if drift_count > 0:
            actions.append(
                {
                    "type": "drift_detected",
                    "drift_count": drift_count,
                    "date": today,
                    "recommendation": "incremental_requeue",
                }
            )
        return actions

    # ------------------------------------------------------------------ #
    #  Audit                                                               #
    # ------------------------------------------------------------------ #

    async def _audit(self, tenant_id, property_id, connector_id, action, actor_id=None, metadata=None):
        log = IntegrationAuditLog(
            tenant_id=tenant_id,
            property_id=property_id,
            connector_id=connector_id,
            action=action,
            actor_id=actor_id,
            metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())
