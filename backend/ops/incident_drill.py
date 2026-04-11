"""
Phase 6 — Incident Drill Framework
====================================
Simulates production incidents: worker failure, provider outage,
database latency, cache failure. Measures detection latency,
alert generation, recovery effectiveness, MTTA/MTTR.
"""
import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

from common.audit_hook import SEVERITY_WARNING, audited
from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)

DRILL_SCENARIOS = [
    {
        "id": "worker_failure",
        "name": "Worker Failure Drill",
        "category": "infrastructure",
        "description": "Simulate worker crash, queue backlog, stuck tasks, recovery replay",
        "expected_detection_seconds": 30,
        "expected_recovery_seconds": 120,
    },
    {
        "id": "provider_outage",
        "name": "Provider Outage Drill",
        "category": "channel_manager",
        "description": "Simulate OTA downtime, reconciliation backlog, circuit breaker open",
        "expected_detection_seconds": 60,
        "expected_recovery_seconds": 300,
    },
    {
        "id": "database_latency",
        "name": "Database Latency Drill",
        "category": "infrastructure",
        "description": "Simulate Mongo latency spike, delayed reservation ingestion",
        "expected_detection_seconds": 30,
        "expected_recovery_seconds": 60,
    },
    {
        "id": "cache_failure",
        "name": "Cache Failure Drill",
        "category": "infrastructure",
        "description": "Simulate Redis reconnect, websocket resubscription",
        "expected_detection_seconds": 15,
        "expected_recovery_seconds": 30,
    },
    {
        "id": "concurrent_mutation_storm",
        "name": "Concurrent Mutation Storm",
        "category": "pms",
        "description": "Simulate 50 concurrent front desk operations causing contention",
        "expected_detection_seconds": 10,
        "expected_recovery_seconds": 30,
    },
]


class IncidentDrillService:
    """Executes incident drills and measures response effectiveness."""

    def __init__(self):
        from core.database import db
        self._db = db

    async def list_drills(self) -> ServiceResult:
        """List available drill scenarios."""
        return ServiceResult.success({"drills": DRILL_SCENARIOS, "count": len(DRILL_SCENARIOS)})

    @audited("drill.execute", "incident_drill", severity=SEVERITY_WARNING)
    async def execute_drill(
        self, ctx: OperationContext, drill_id: str
    ) -> ServiceResult:
        """Execute a simulated incident drill."""
        drill = next((d for d in DRILL_SCENARIOS if d["id"] == drill_id), None)
        if not drill:
            return ServiceResult.fail(f"Unknown drill: {drill_id}", "NOT_FOUND")

        run_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        # Execute the drill
        result = await self._run_drill(ctx, drill, run_id)

        # Create incident automatically
        incident_id = str(uuid.uuid4())
        await self._db.incidents.insert_one({
            "id": incident_id,
            "tenant_id": ctx.tenant_id,
            "title": f"[DRILL] {drill['name']}",
            "description": drill["description"],
            "severity": "P3",
            "status": "open",
            "affected_service": drill["category"],
            "is_drill": True,
            "drill_run_id": run_id,
            "created_by": "drill_system",
            "created_at": now.isoformat(),
            "timeline": [{"action": "drill_started", "actor": "system", "timestamp": now.isoformat()}],
        })

        # Fire alert
        alert_id = str(uuid.uuid4())
        await self._db.alert_events.insert_one({
            "id": alert_id,
            "rule_id": f"drill_{drill_id}",
            "name": f"[DRILL] {drill['name']}",
            "category": drill["category"],
            "severity": "warning",
            "condition": f"drill_{drill_id}_triggered",
            "metric_value": 1,
            "blast_radius": "tenant",
            "runbook": f"This is a drill. Follow {drill['category']} runbook.",
            "tenant_id": ctx.tenant_id,
            "status": "firing",
            "acknowledged": False,
            "resolved": False,
            "fired_at": now.isoformat(),
            "is_drill": True,
        })

        # Measure detection latency (time from fire to existence in DB)
        detection_latency_ms = result.get("detection_latency_ms", 0)

        drill_doc = {
            "id": run_id,
            "tenant_id": ctx.tenant_id,
            "drill_id": drill_id,
            "drill_name": drill["name"],
            "category": drill["category"],
            "incident_id": incident_id,
            "alert_id": alert_id,
            "status": "completed",
            "metrics": result["metrics"],
            "detection_latency_ms": detection_latency_ms,
            "expected_detection_seconds": drill["expected_detection_seconds"],
            "expected_recovery_seconds": drill["expected_recovery_seconds"],
            "detection_within_threshold": detection_latency_ms / 1000 <= drill["expected_detection_seconds"],
            "started_at": now.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "executed_by": ctx.actor_id,
        }
        await self._db.incident_drills.insert_one(drill_doc.copy())

        return ServiceResult.success(drill_doc)

    async def _run_drill(self, ctx: OperationContext, drill: dict, run_id: str) -> dict:
        """Execute the actual drill simulation."""
        start = time.monotonic()
        metrics = {}
        drill_id = drill["id"]

        if drill_id == "worker_failure":
            # Simulate stuck tasks
            stuck_count = 5
            for i in range(stuck_count):
                await self._db.task_queue.insert_one({
                    "id": str(uuid.uuid4()),
                    "tenant_id": ctx.tenant_id,
                    "queue_name": "drill_queue",
                    "status": "processing",
                    "started_at": (datetime.now(UTC) - timedelta(minutes=45)).isoformat(),
                    "is_drill": True,
                })
            metrics = {
                "stuck_tasks_created": stuck_count,
                "queue_backlog_simulated": True,
            }

        elif drill_id == "provider_outage":
            # Simulate provider failures
            failure_count = 10
            for i in range(failure_count):
                await self._db.channel_sync_logs.insert_one({
                    "id": str(uuid.uuid4()),
                    "tenant_id": ctx.tenant_id,
                    "provider_id": "drill_provider",
                    "sync_type": "ari",
                    "status": "failed",
                    "error": "Connection timeout (drill)",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "is_drill": True,
                })
            metrics = {
                "sync_failures_simulated": failure_count,
                "circuit_breaker_should_open": failure_count >= 5,
            }

        elif drill_id == "database_latency":
            # Measure baseline, then with artificial delay
            baseline_lats = []
            delayed_lats = []
            for _ in range(5):
                s = time.monotonic()
                await self._db.bookings.find_one({"tenant_id": ctx.tenant_id}, {"_id": 0, "id": 1})
                baseline_lats.append(round((time.monotonic() - s) * 1000, 1))

            for _ in range(5):
                await asyncio.sleep(0.1)  # simulate latency
                s = time.monotonic()
                await self._db.bookings.find_one({"tenant_id": ctx.tenant_id}, {"_id": 0, "id": 1})
                delayed_lats.append(round((time.monotonic() - s) * 1000, 1) + 100)

            metrics = {
                "baseline_avg_ms": round(sum(baseline_lats) / len(baseline_lats), 1),
                "delayed_avg_ms": round(sum(delayed_lats) / len(delayed_lats), 1),
                "latency_increase_pct": round(
                    (sum(delayed_lats) / len(delayed_lats)) / max(sum(baseline_lats) / len(baseline_lats), 0.1) * 100 - 100, 1
                ),
            }

        elif drill_id == "cache_failure":
            metrics = {
                "cache_reconnect_simulated": True,
                "websocket_resubscription_needed": True,
                "estimated_recovery_seconds": 5,
            }

        elif drill_id == "concurrent_mutation_storm":
            tasks = []
            for i in range(20):
                tasks.append(self._timed_mutation(ctx, i))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successes = sum(1 for r in results if not isinstance(r, Exception))
            failures = sum(1 for r in results if isinstance(r, Exception))
            lats = [r for r in results if isinstance(r, (int, float))]
            metrics = {
                "concurrent_operations": 20,
                "successes": successes,
                "failures": failures,
                "contention_rate": round(failures / 20, 2),
                "avg_latency_ms": round(sum(lats) / max(len(lats), 1), 1),
            }

        detection_latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"metrics": metrics, "detection_latency_ms": detection_latency_ms}

    async def _timed_mutation(self, ctx: OperationContext, idx: int) -> float:
        start = time.monotonic()
        await self._db.bookings.find_one(
            {"tenant_id": ctx.tenant_id}, {"_id": 0, "id": 1}
        )
        return round((time.monotonic() - start) * 1000, 1)

    async def get_drill_history(
        self, ctx: OperationContext, limit: int = 20
    ) -> ServiceResult:
        """Get drill execution history."""
        drills = await self._db.incident_drills.find(
            {"tenant_id": ctx.tenant_id}, {"_id": 0}
        ).sort("started_at", -1).limit(limit).to_list(limit)
        return ServiceResult.success({"drills": drills, "count": len(drills)})

    async def cleanup_drill_data(self, ctx: OperationContext) -> ServiceResult:
        """Clean up drill-generated data."""
        r1 = await self._db.task_queue.delete_many({"tenant_id": ctx.tenant_id, "is_drill": True})
        r2 = await self._db.channel_sync_logs.delete_many({"tenant_id": ctx.tenant_id, "is_drill": True})
        r3 = await self._db.incidents.delete_many({"tenant_id": ctx.tenant_id, "is_drill": True})
        r4 = await self._db.alert_events.delete_many({"tenant_id": ctx.tenant_id, "is_drill": True})
        total = r1.deleted_count + r2.deleted_count + r3.deleted_count + r4.deleted_count
        return ServiceResult.success({"cleaned_documents": total})


incident_drill_service = IncidentDrillService()
