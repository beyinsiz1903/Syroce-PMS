"""
Phase 7 — Canary Deployment Strategy Service
==============================================
Manages staged rollout from internal → pilot → gradual traffic increase.
Feature flags, rollback triggers, canary monitoring.
"""

import logging
import uuid
from datetime import UTC, datetime

from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)

DEPLOYMENT_STAGES = [
    {
        "id": "stage_1",
        "name": "Internal Tenant Only",
        "description": "Deploy to internal test tenant for smoke testing",
        "traffic_percent": 0,
        "target": "internal",
        "checks": ["smoke_test", "health_api", "basic_crud"],
        "rollback_auto": True,
    },
    {
        "id": "stage_2",
        "name": "Pilot Tenant (1 Hotel)",
        "description": "Enable for a single pilot hotel with full monitoring",
        "traffic_percent": 1,
        "target": "pilot",
        "checks": ["reservation_flow", "sync_validation", "night_audit", "folio_ops"],
        "rollback_auto": True,
    },
    {
        "id": "stage_3",
        "name": "Small Traffic Slice (5-10%)",
        "description": "Expand to 5-10% of tenant traffic with gradual ramp",
        "traffic_percent": 10,
        "target": "partial",
        "checks": ["latency_baseline", "error_rate", "queue_health", "provider_sync"],
        "rollback_auto": True,
    },
    {
        "id": "stage_4",
        "name": "Gradual Rollout (25% → 50% → 100%)",
        "description": "Full production rollout with stepped traffic increase",
        "traffic_percent": 100,
        "target": "all",
        "checks": ["full_load_validation", "tenant_isolation", "observability_coverage"],
        "rollback_auto": False,
    },
]

ROLLBACK_TRIGGERS = [
    {"id": "latency_spike", "name": "Latency Spike", "metric": "p95_latency_ms", "threshold": 500, "action": "auto_rollback"},
    {"id": "error_rate", "name": "Error Rate Threshold", "metric": "error_rate_percent", "threshold": 5.0, "action": "auto_rollback"},
    {"id": "provider_sync_failure", "name": "Provider Sync Failure Spike", "metric": "sync_failure_rate", "threshold": 10.0, "action": "auto_rollback"},
    {"id": "queue_backlog", "name": "Queue Backlog Growth", "metric": "queue_depth", "threshold": 1000, "action": "alert_and_pause"},
    {"id": "reservation_ingest_latency", "name": "Reservation Ingest Latency", "metric": "ingest_latency_ms", "threshold": 2000, "action": "alert_and_pause"},
    {"id": "reconciliation_delay", "name": "Reconciliation Delay", "metric": "recon_delay_min", "threshold": 30, "action": "alert"},
    {"id": "websocket_event_latency", "name": "WebSocket Event Latency", "metric": "ws_event_latency_ms", "threshold": 1000, "action": "alert"},
]

CANARY_METRICS = [
    {"id": "request_latency", "name": "Request Latency", "unit": "ms", "target": "< 200ms p95"},
    {"id": "error_rate", "name": "Error Rate", "unit": "%", "target": "< 1%"},
    {"id": "queue_lag", "name": "Queue Lag", "unit": "items", "target": "< 50"},
    {"id": "reservation_ingest_latency", "name": "Reservation Ingest Latency", "unit": "ms", "target": "< 500ms"},
    {"id": "reconciliation_delay", "name": "Reconciliation Delay", "unit": "min", "target": "< 15min"},
    {"id": "websocket_event_latency", "name": "WebSocket Event Latency", "unit": "ms", "target": "< 200ms"},
]


class CanaryDeploymentService:
    """Manages canary deployment stages and rollback logic."""

    def __init__(self):
        from core.database import db

        self._db = db

    async def get_deployment_plan(self) -> ServiceResult:
        return ServiceResult.success(
            {
                "stages": DEPLOYMENT_STAGES,
                "rollback_triggers": ROLLBACK_TRIGGERS,
                "canary_metrics": CANARY_METRICS,
            }
        )

    async def get_current_stage(self, ctx: OperationContext) -> ServiceResult:
        state = await self._db.canary_deployments.find_one(
            {"tenant_id": ctx.tenant_id},
            {"_id": 0},
            sort=[("updated_at", -1)],
        )
        if not state:
            return ServiceResult.success(
                {
                    "current_stage": None,
                    "status": "not_started",
                    "history": [],
                }
            )
        return ServiceResult.success(state)

    async def advance_stage(self, ctx: OperationContext, target_stage_id: str) -> ServiceResult:
        stage = next((s for s in DEPLOYMENT_STAGES if s["id"] == target_stage_id), None)
        if not stage:
            return ServiceResult.fail(f"Unknown stage: {target_stage_id}", "INVALID_STAGE")

        now = datetime.now(UTC).isoformat()

        # Check prerequisites for advancing
        current = await self._db.canary_deployments.find_one(
            {"tenant_id": ctx.tenant_id},
            {"_id": 0},
            sort=[("updated_at", -1)],
        )
        current_idx = -1
        if current and current.get("current_stage_id"):
            for i, s in enumerate(DEPLOYMENT_STAGES):
                if s["id"] == current["current_stage_id"]:
                    current_idx = i
                    break

        target_idx = next(i for i, s in enumerate(DEPLOYMENT_STAGES) if s["id"] == target_stage_id)
        if target_idx > current_idx + 1:
            return ServiceResult.fail("Cannot skip stages. Advance one stage at a time.", "STAGE_SKIP")

        entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            "current_stage_id": target_stage_id,
            "current_stage_name": stage["name"],
            "traffic_percent": stage["traffic_percent"],
            "status": "active",
            "advanced_by": ctx.actor_email,
            "advanced_at": now,
            "updated_at": now,
            "checks_status": dict.fromkeys(stage["checks"], "pending"),
        }

        await self._db.canary_deployments.insert_one(entry)
        del entry["_id"]
        return ServiceResult.success(entry)

    async def rollback(self, ctx: OperationContext, reason: str) -> ServiceResult:
        now = datetime.now(UTC).isoformat()
        current = await self._db.canary_deployments.find_one(
            {"tenant_id": ctx.tenant_id, "status": "active"},
            {"_id": 0},
            sort=[("updated_at", -1)],
        )
        if not current:
            return ServiceResult.fail("No active deployment to rollback", "NO_ACTIVE")

        rollback_entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            "current_stage_id": "rollback",
            "current_stage_name": "Rolled Back",
            "traffic_percent": 0,
            "status": "rolled_back",
            "rolled_back_from": current["current_stage_id"],
            "rollback_reason": reason,
            "rolled_back_by": ctx.actor_email,
            "rolled_back_at": now,
            "updated_at": now,
        }

        await self._db.canary_deployments.update_many(
            {"tenant_id": ctx.tenant_id, "status": "active"},
            {"$set": {"status": "rolled_back", "updated_at": now}},
        )
        await self._db.canary_deployments.insert_one(rollback_entry)
        del rollback_entry["_id"]
        return ServiceResult.success(rollback_entry)

    async def check_rollback_triggers(self, ctx: OperationContext) -> ServiceResult:
        """Evaluate current metrics against rollback trigger thresholds."""
        results = []
        for trigger in ROLLBACK_TRIGGERS:
            # Simulated metric evaluation — in production reads from Prometheus/metrics store
            current_value = await self._get_metric_value(ctx, trigger["metric"])
            triggered = current_value > trigger["threshold"]
            results.append(
                {
                    "trigger_id": trigger["id"],
                    "name": trigger["name"],
                    "threshold": trigger["threshold"],
                    "current_value": current_value,
                    "triggered": triggered,
                    "action": trigger["action"] if triggered else "none",
                }
            )

        any_triggered = any(r["triggered"] for r in results)
        return ServiceResult.success(
            {
                "triggers": results,
                "any_triggered": any_triggered,
                "recommendation": "rollback" if any_triggered else "continue",
            }
        )

    async def _get_metric_value(self, ctx: OperationContext, metric: str) -> float:
        """Get current metric value. In prod reads from Prometheus."""
        # Simulated healthy values for now
        defaults = {
            "p95_latency_ms": 120.0,
            "error_rate_percent": 0.3,
            "sync_failure_rate": 0.5,
            "queue_depth": 12.0,
            "ingest_latency_ms": 180.0,
            "recon_delay_min": 5.0,
            "ws_event_latency_ms": 45.0,
        }
        return defaults.get(metric, 0.0)


canary_deployment_service = CanaryDeploymentService()
