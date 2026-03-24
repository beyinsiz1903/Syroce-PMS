"""
Auto-Rollback Engine — Metric-Based Automatic Rollback
========================================================
Monitors real system health metrics and triggers rollback when thresholds are breached.
Works with the canary deployment service for progressive deploy safety.
"""
import logging
from datetime import datetime, timedelta, timezone

from common.result import ServiceResult

logger = logging.getLogger("ops.auto_rollback")

# Rollback trigger definitions with REAL metric sources
ROLLBACK_TRIGGERS = [
    {
        "id": "error_rate_5xx",
        "name": "5xx Error Rate",
        "description": "Percentage of 500-level errors in last 5 minutes",
        "threshold": 5.0,
        "unit": "%",
        "window_minutes": 5,
        "action": "auto_rollback",
        "source": "apm",
    },
    {
        "id": "health_endpoint_down",
        "name": "Health Endpoint Down",
        "description": "Liveness probe returns non-200",
        "threshold": 1,
        "unit": "failures",
        "window_minutes": 2,
        "action": "auto_rollback",
        "source": "health",
    },
    {
        "id": "db_connection_fail",
        "name": "DB Connection Failure",
        "description": "MongoDB ping fails",
        "threshold": 1,
        "unit": "failures",
        "window_minutes": 1,
        "action": "auto_rollback",
        "source": "db",
    },
    {
        "id": "outbox_backlog",
        "name": "Outbox Backlog Critical",
        "description": "Pending outbox events exceed threshold",
        "threshold": 500,
        "unit": "events",
        "window_minutes": 10,
        "action": "alert_and_pause",
        "source": "outbox",
    },
    {
        "id": "import_failure_rate",
        "name": "Import Failure Rate",
        "description": "Failed imports exceed threshold",
        "threshold": 20,
        "unit": "failures",
        "window_minutes": 30,
        "action": "alert_and_pause",
        "source": "import",
    },
]


class AutoRollbackEngine:
    """Monitors real metrics and triggers auto-rollback decisions."""

    def __init__(self):
        from core.database import db
        self._db = db

    async def evaluate_triggers(self) -> ServiceResult:
        """Evaluate all rollback triggers against real system state."""
        now = datetime.now(timezone.utc)
        results = []
        any_triggered = False
        auto_rollback_needed = False

        for trigger in ROLLBACK_TRIGGERS:
            current_value = await self._get_real_metric(trigger)
            triggered = current_value > trigger["threshold"]

            if triggered:
                any_triggered = True
                if trigger["action"] == "auto_rollback":
                    auto_rollback_needed = True

            results.append({
                "trigger_id": trigger["id"],
                "name": trigger["name"],
                "description": trigger["description"],
                "threshold": trigger["threshold"],
                "current_value": current_value,
                "unit": trigger["unit"],
                "triggered": triggered,
                "action": trigger["action"] if triggered else "none",
                "source": trigger["source"],
            })

        recommendation = "continue"
        if auto_rollback_needed:
            recommendation = "rollback"
        elif any_triggered:
            recommendation = "pause"

        # Record evaluation
        eval_record = {
            "evaluated_at": now.isoformat(),
            "triggers": results,
            "any_triggered": any_triggered,
            "recommendation": recommendation,
        }
        await self._db.rollback_evaluations.insert_one(eval_record)
        eval_record.pop("_id", None)

        return ServiceResult.success(eval_record)

    async def execute_rollback(self, reason: str, triggered_by: str) -> ServiceResult:
        """Record a rollback execution event."""
        now = datetime.now(timezone.utc).isoformat()

        # Get current canary state
        canary_state = await self._db.canary_deployments.find_one(
            {"status": "active"}, {"_id": 0},
            sort=[("updated_at", -1)],
        )

        rollback_record = {
            "rollback_id": f"rb-{now.replace(':', '').replace('-', '')[:15]}",
            "executed_at": now,
            "reason": reason,
            "triggered_by": triggered_by,
            "previous_stage": canary_state.get("current_stage_id") if canary_state else "unknown",
            "status": "executed",
            "verification": None,
        }

        # Deactivate all active canary deployments
        if canary_state:
            await self._db.canary_deployments.update_many(
                {"status": "active"},
                {"$set": {"status": "rolled_back", "updated_at": now, "rollback_reason": reason}},
            )

        await self._db.rollback_history.insert_one(rollback_record)
        rollback_record.pop("_id", None)

        # Run post-rollback smoke tests
        from ops.smoke_test_runner import smoke_test_runner
        smoke_result = await smoke_test_runner.run_all()
        if smoke_result.ok:
            rollback_record["verification"] = {
                "smoke_tests_passed": smoke_result.data["passed"],
                "smoke_tests_total": smoke_result.data["total"],
                "verdict": smoke_result.data["verdict"],
            }
            await self._db.rollback_history.update_one(
                {"rollback_id": rollback_record["rollback_id"]},
                {"$set": {"verification": rollback_record["verification"]}},
            )

        return ServiceResult.success(rollback_record)

    async def get_rollback_history(self, limit: int = 20) -> ServiceResult:
        cursor = self._db.rollback_history.find({}, {"_id": 0}).sort("executed_at", -1).limit(limit)
        history = await cursor.to_list(length=limit)
        return ServiceResult.success({"rollbacks": history, "total": len(history)})

    async def get_trigger_definitions(self) -> ServiceResult:
        return ServiceResult.success({"triggers": ROLLBACK_TRIGGERS})

    # ── Real Metric Collectors ───────────────────────────────────────

    async def _get_real_metric(self, trigger: dict) -> float:
        source = trigger["source"]
        try:
            if source == "apm":
                return await self._metric_error_rate()
            elif source == "health":
                return await self._metric_health_check()
            elif source == "db":
                return await self._metric_db_health()
            elif source == "outbox":
                return await self._metric_outbox_backlog()
            elif source == "import":
                return await self._metric_import_failures()
            return 0.0
        except Exception as e:
            logger.warning(f"Metric collection error ({source}): {e}")
            return 0.0

    async def _metric_error_rate(self) -> float:
        """Get 5xx error rate from APM store."""
        try:
            from server import apm_store
            summary = apm_store.get_summary(minutes=5)
            return summary.get("error_rate_percent", 0.0)
        except Exception:
            return 0.0

    async def _metric_health_check(self) -> float:
        """Ping liveness endpoint — 0 = OK, 1 = DOWN."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("http://localhost:8001/health/liveness")
                return 0.0 if resp.status_code == 200 else 1.0
        except Exception:
            return 1.0

    async def _metric_db_health(self) -> float:
        """MongoDB ping — 0 = OK, 1 = FAIL."""
        try:
            await self._db.command("ping")
            return 0.0
        except Exception:
            return 1.0

    async def _metric_outbox_backlog(self) -> float:
        """Count pending + retry outbox events."""
        try:
            pending = await self._db.outbox_events.count_documents({"status": {"$in": ["pending", "retry"]}})
            return float(pending)
        except Exception:
            return 0.0

    async def _metric_import_failures(self) -> float:
        """Count failed imports in the last window."""
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
            failed = await self._db.imported_reservations.count_documents({
                "import_status": "failed",
                "updated_at": {"$gte": cutoff},
            })
            return float(failed)
        except Exception:
            return 0.0


auto_rollback_engine = AutoRollbackEngine()
