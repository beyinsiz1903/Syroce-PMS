"""
Incident Response & Recovery Service
=====================================
Tooling for first production incidents: stuck worker recovery, queue replay,
drift workflow, degraded service detection, incident lifecycle management.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from common.audit_hook import SEVERITY_CRITICAL, SEVERITY_WARNING, audited
from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)


class IncidentSeverity:
    P1 = "P1"  # Critical - service down
    P2 = "P2"  # High - major degradation
    P3 = "P3"  # Medium - partial impact
    P4 = "P4"  # Low - minor issue


class IncidentResponseService:
    """Manages incident lifecycle, recovery, and operational tooling."""

    def __init__(self):
        from core.database import db
        self._db = db

    # ==================================================================
    # Incident Lifecycle
    # ==================================================================
    @audited("incident.create", "incident", severity=SEVERITY_CRITICAL)
    async def create_incident(
        self,
        ctx: OperationContext,
        title: str,
        description: str,
        severity: str = IncidentSeverity.P2,
        affected_service: str = "",
        affected_tenant_id: Optional[str] = None,
        affected_property_id: Optional[str] = None,
    ) -> ServiceResult:
        incident_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        incident = {
            "id": incident_id,
            "tenant_id": ctx.tenant_id,
            "title": title,
            "description": description,
            "severity": severity,
            "status": "open",
            "affected_service": affected_service,
            "affected_tenant_id": affected_tenant_id or ctx.tenant_id,
            "affected_property_id": affected_property_id,
            "created_by": ctx.actor_id,
            "created_at": now.isoformat(),
            "acknowledged_at": None,
            "resolved_at": None,
            "resolution_note": None,
            "timeline": [
                {
                    "action": "created",
                    "actor": ctx.actor_id,
                    "timestamp": now.isoformat(),
                    "note": description,
                }
            ],
            "related_alerts": [],
            "recovery_actions": [],
        }
        await self._db.incidents.insert_one(incident)
        return ServiceResult.success({
            "incident_id": incident_id,
            "severity": severity,
            "status": "open",
        })

    @audited("incident.acknowledge", "incident", severity=SEVERITY_WARNING)
    async def acknowledge_incident(
        self, ctx: OperationContext, incident_id: str
    ) -> ServiceResult:
        now = datetime.now(timezone.utc)
        result = await self._db.incidents.update_one(
            {"id": incident_id, "tenant_id": ctx.tenant_id, "status": "open"},
            {
                "$set": {
                    "status": "acknowledged",
                    "acknowledged_at": now.isoformat(),
                    "acknowledged_by": ctx.actor_id,
                },
                "$push": {
                    "timeline": {
                        "action": "acknowledged",
                        "actor": ctx.actor_id,
                        "timestamp": now.isoformat(),
                    }
                },
            },
        )
        if result.modified_count == 0:
            return ServiceResult.fail("Incident not found or already acknowledged", "NOT_FOUND")
        return ServiceResult.success({"message": "Incident acknowledged", "incident_id": incident_id})

    @audited("incident.resolve", "incident", severity=SEVERITY_WARNING)
    async def resolve_incident(
        self,
        ctx: OperationContext,
        incident_id: str,
        resolution_note: str,
    ) -> ServiceResult:
        now = datetime.now(timezone.utc)
        result = await self._db.incidents.update_one(
            {"id": incident_id, "tenant_id": ctx.tenant_id, "status": {"$in": ["open", "acknowledged"]}},
            {
                "$set": {
                    "status": "resolved",
                    "resolved_at": now.isoformat(),
                    "resolved_by": ctx.actor_id,
                    "resolution_note": resolution_note,
                },
                "$push": {
                    "timeline": {
                        "action": "resolved",
                        "actor": ctx.actor_id,
                        "timestamp": now.isoformat(),
                        "note": resolution_note,
                    }
                },
            },
        )
        if result.modified_count == 0:
            return ServiceResult.fail("Incident not found or already resolved", "NOT_FOUND")
        return ServiceResult.success({"message": "Incident resolved", "incident_id": incident_id})

    async def list_incidents(
        self,
        ctx: OperationContext,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> ServiceResult:
        query: Dict[str, Any] = {"tenant_id": ctx.tenant_id}
        if status:
            query["status"] = status
        if severity:
            query["severity"] = severity
        incidents = await self._db.incidents.find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        return ServiceResult.success({"incidents": incidents, "count": len(incidents)})

    # ==================================================================
    # Recovery Tools
    # ==================================================================
    @audited("recovery.replay_queue", "queue", severity=SEVERITY_WARNING, require_reason=True)
    async def replay_dead_letters(
        self,
        ctx: OperationContext,
        queue_name: str,
        max_count: int = 10,
        reason: str = "",
    ) -> ServiceResult:
        """Replay dead-letter queue entries back to their original queue."""
        if ctx.actor_role not in ("admin", "super_admin"):
            return ServiceResult.fail("Admin only operation", "FORBIDDEN")

        dead_letters = await self._db.dead_letter_queue.find(
            {"queue_name": queue_name, "tenant_id": ctx.tenant_id, "replayed": {"$ne": True}},
            {"_id": 0},
        ).limit(max_count).to_list(max_count)

        replayed = 0
        for dl in dead_letters:
            await self._db.task_queue.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": ctx.tenant_id,
                "queue_name": queue_name,
                "payload": dl.get("payload"),
                "status": "pending",
                "replayed_from": dl.get("id"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            await self._db.dead_letter_queue.update_one(
                {"id": dl["id"]},
                {
                    "$set": {
                        "replayed": True,
                        "replayed_at": datetime.now(timezone.utc).isoformat(),
                        "replayed_by": ctx.actor_id,
                    }
                },
            )
            replayed += 1

        return ServiceResult.success({
            "queue_name": queue_name,
            "replayed_count": replayed,
            "total_dead_letters": len(dead_letters),
        })

    @audited("recovery.stuck_worker", "worker", severity=SEVERITY_WARNING)
    async def recover_stuck_workers(
        self, ctx: OperationContext, stale_minutes: int = 30
    ) -> ServiceResult:
        """Find and reset stuck worker tasks."""
        if ctx.actor_role not in ("admin", "super_admin"):
            return ServiceResult.fail("Admin only operation", "FORBIDDEN")

        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)).isoformat()
        stuck = await self._db.task_queue.find(
            {
                "tenant_id": ctx.tenant_id,
                "status": "processing",
                "started_at": {"$lt": cutoff},
            },
            {"_id": 0},
        ).to_list(100)

        recovered = 0
        for task in stuck:
            await self._db.task_queue.update_one(
                {"id": task["id"]},
                {
                    "$set": {
                        "status": "pending",
                        "recovered_at": datetime.now(timezone.utc).isoformat(),
                        "recovered_by": ctx.actor_id,
                        "recovery_reason": "stuck_worker_timeout",
                    },
                    "$inc": {"retry_count": 1},
                },
            )
            recovered += 1

        return ServiceResult.success({
            "stuck_tasks_found": len(stuck),
            "recovered": recovered,
            "stale_threshold_minutes": stale_minutes,
        })

    @audited("recovery.force_reconciliation", "reconciliation", severity=SEVERITY_WARNING, require_reason=True)
    async def force_reconciliation(
        self,
        ctx: OperationContext,
        provider_id: str,
        reason: str = "",
    ) -> ServiceResult:
        """Queue a force reconciliation for a specific provider."""
        recon_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        await self._db.reconciliation_queue.insert_one({
            "id": recon_id,
            "tenant_id": ctx.tenant_id,
            "provider_id": provider_id,
            "type": "force_full",
            "status": "queued",
            "triggered_by": ctx.actor_id,
            "reason": reason,
            "created_at": now.isoformat(),
        })
        return ServiceResult.success({
            "reconciliation_id": recon_id,
            "provider_id": provider_id,
            "status": "queued",
        })

    # ==================================================================
    # Degraded Service Monitor
    # ==================================================================
    async def get_service_health_matrix(self, ctx: OperationContext) -> ServiceResult:
        """Check health of all major services and return matrix."""
        services = [
            "pms_core", "channel_manager", "night_audit", "messaging",
            "queue_workers", "security", "ml_pipeline", "websocket",
        ]
        matrix = []
        now = datetime.now(timezone.utc)

        for svc in services:
            last_heartbeat = await self._db.service_heartbeats.find_one(
                {"service_name": svc, "tenant_id": ctx.tenant_id},
                sort=[("timestamp", -1)],
            )
            if last_heartbeat:
                last_ts = last_heartbeat.get("timestamp", "")
                try:
                    age = (now - datetime.fromisoformat(last_ts.replace("Z", "+00:00"))).total_seconds()
                except Exception:
                    age = 9999
                status = "healthy" if age < 120 else ("degraded" if age < 600 else "down")
            else:
                status = "unknown"
                age = None

            active_incidents = await self._db.incidents.count_documents(
                {"affected_service": svc, "tenant_id": ctx.tenant_id, "status": {"$in": ["open", "acknowledged"]}}
            )

            matrix.append({
                "service": svc,
                "status": status,
                "last_heartbeat_age_seconds": round(age, 1) if age else None,
                "active_incidents": active_incidents,
            })

        overall = "healthy"
        for m in matrix:
            if m["status"] == "down":
                overall = "critical"
                break
            if m["status"] == "degraded":
                overall = "degraded"

        return ServiceResult.success({
            "services": matrix,
            "overall_status": overall,
            "checked_at": now.isoformat(),
        })


incident_response_service = IncidentResponseService()
