"""
Phase 7 — Production Load Validation Service
==============================================
Validates platform behavior under real traffic patterns:
OTA reservation burst, ARI update storm, queue backlog,
night audit concurrency, websocket event stream.
"""

import logging
import os
import uuid
from datetime import UTC, datetime

from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)

LOAD_SCENARIOS = [
    {
        "id": "ota_reservation_burst",
        "name": "OTA Reservation Burst",
        "description": "Simulate 100 concurrent OTA reservations in 60s",
        "metrics": ["latency_p95", "error_rate", "throughput"],
        "thresholds": {"latency_p95_ms": 500, "error_rate_pct": 1.0, "throughput_rps": 50},
    },
    {
        "id": "ari_update_storm",
        "name": "ARI Update Storm",
        "description": "Push 500 rate/availability updates in 30s",
        "metrics": ["sync_latency", "queue_growth", "provider_ack_rate"],
        "thresholds": {"sync_latency_ms": 300, "queue_growth": 50, "provider_ack_rate_pct": 99},
    },
    {
        "id": "queue_backlog_scenario",
        "name": "Queue Backlog Scenario",
        "description": "Inject 1000 tasks while workers process at 50/s",
        "metrics": ["drain_time", "dead_letter_count", "worker_utilization"],
        "thresholds": {"drain_time_sec": 30, "dead_letter_count": 0, "worker_utilization_pct": 90},
    },
    {
        "id": "night_audit_concurrency",
        "name": "Night Audit Concurrency",
        "description": "Run night audit while 20 concurrent frontdesk operations execute",
        "metrics": ["audit_duration", "concurrent_op_latency", "lock_contention"],
        "thresholds": {"audit_duration_ms": 5000, "concurrent_op_latency_ms": 200, "lock_contention_count": 2},
    },
    {
        "id": "websocket_event_stream",
        "name": "WebSocket Event Stream Load",
        "description": "Push 200 events/sec to connected WebSocket clients",
        "metrics": ["event_latency", "dropped_events", "memory_growth"],
        "thresholds": {"event_latency_ms": 100, "dropped_events": 0, "memory_growth_mb": 50},
    },
]


class ProductionLoadValidationService:
    """Runs and evaluates production load validation scenarios."""

    def __init__(self):
        from core.database import db

        self._db = db

    async def get_scenarios(self) -> ServiceResult:
        # The UI must never present local random numbers as production load
        # evidence.  A scenario becomes executable only when an externally
        # operated, measured load runner has been configured.
        runner_configured = bool(os.environ.get("PRODUCTION_LOAD_RUNNER_URL", "").strip())
        return ServiceResult.success(
            {
                "scenarios": [
                    {
                        **scenario,
                        "execution_mode": "external_runner_required",
                        "evidence_status": "ready_to_run" if runner_configured else "not_configured",
                    }
                    for scenario in LOAD_SCENARIOS
                ],
                "runner_configured": runner_configured,
                "runner_requirement": "Measured production validation requires PRODUCTION_LOAD_RUNNER_URL.",
            }
        )

    async def run_scenario(self, ctx: OperationContext, scenario_id: str) -> ServiceResult:
        scenario = next((s for s in LOAD_SCENARIOS if s["id"] == scenario_id), None)
        if not scenario:
            return ServiceResult.fail(f"Unknown scenario: {scenario_id}", "INVALID_SCENARIO")

        now = datetime.now(UTC)
        runner_configured = bool(os.environ.get("PRODUCTION_LOAD_RUNNER_URL", "").strip())
        # No runner adapter exists in this process yet.  Record the request as
        # unverified rather than generating synthetic values that always look
        # healthy.  This makes the operational gap visible without turning a
        # button click into a false green go-live signal.
        run_entry: dict[str, object] = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            "scenario_id": scenario_id,
            "scenario_name": scenario["name"],
            "status": "not_run",
            "evidence_status": "runner_configured_but_not_connected" if runner_configured else "not_configured",
            "execution_mode": "external_runner_required",
            "message": "No measured load-runner result is available; this is not a passed production validation.",
            "metrics": [],
            "passed_count": 0,
            "total_count": len(scenario["thresholds"]),
            "started_at": now.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
        }

        await self._db.production_load_runs.insert_one(run_entry)
        del run_entry["_id"]
        return ServiceResult.success(run_entry)

    async def get_load_report(self, ctx: OperationContext, hours: int = 24) -> ServiceResult:
        from datetime import timedelta

        since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        runs = (
            await self._db.production_load_runs.find(
                {"tenant_id": ctx.tenant_id, "started_at": {"$gte": since}},
                {"_id": 0},
            )
            .sort("started_at", -1)
            .to_list(100)
        )

        passed = sum(1 for r in runs if r["status"] == "passed")
        return ServiceResult.success(
            {
                "runs": runs,
                "total": len(runs),
                "passed": passed,
                "pass_rate": round(passed / max(len(runs), 1) * 100, 1),
            }
        )

production_load_validation_service = ProductionLoadValidationService()
