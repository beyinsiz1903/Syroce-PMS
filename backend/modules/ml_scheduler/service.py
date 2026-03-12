"""
ML Model Scheduled Execution Engine.
Manages periodic execution of Revenue ML, Operational AI, Guest Intelligence models.
"""
import logging
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class ModelType:
    REVENUE_ML = "revenue_ml"
    OPERATIONAL_AI = "operational_ai"
    GUEST_INTELLIGENCE = "guest_intelligence"


class ExecutionStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# Default schedules (cron-like descriptions; actual scheduling via background task)
DEFAULT_SCHEDULES = {
    ModelType.REVENUE_ML: {"interval_hours": 6, "description": "4x daily"},
    ModelType.OPERATIONAL_AI: {"interval_hours": 1, "description": "Hourly"},
    ModelType.GUEST_INTELLIGENCE: {"interval_hours": 24, "description": "Daily"},
}


def new_execution_job(
    tenant_id: str,
    model_type: str,
    property_id: Optional[str] = None,
    triggered_by: str = "scheduler",
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "model_type": model_type,
        "property_id": property_id,
        "status": ExecutionStatus.PENDING,
        "triggered_by": triggered_by,
        "started_at": None,
        "completed_at": None,
        "duration_ms": None,
        "result_snapshot_id": None,
        "error_message": None,
        "retry_count": 0,
        "max_retries": 2,
        "model_version": "1.0",
        "confidence_avg": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def new_schedule_policy(
    tenant_id: str,
    model_type: str,
    interval_hours: int,
    enabled: bool = True,
    property_id: Optional[str] = None,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "model_type": model_type,
        "property_id": property_id,
        "interval_hours": interval_hours,
        "enabled": enabled,
        "last_run_at": None,
        "next_run_at": None,
        "snapshot_retention_days": 30,
        "stale_threshold_hours": interval_hours * 3,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


class MLSchedulerService:
    """Manages scheduling and execution of ML model runs."""

    def __init__(self, db):
        self.db = db

    async def get_schedule_policies(self, tenant_id: str) -> list:
        policies = await self.db.ml_schedule_policies.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(50)
        if not policies:
            # seed defaults
            for mt, cfg in DEFAULT_SCHEDULES.items():
                p = new_schedule_policy(tenant_id, mt, cfg["interval_hours"])
                await self.db.ml_schedule_policies.insert_one(p)
                p.pop("_id", None)
                policies.append(p)
        return policies

    async def update_schedule(self, tenant_id: str, model_type: str,
                              interval_hours: Optional[int] = None, enabled: Optional[bool] = None) -> dict:
        update = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if interval_hours is not None:
            update["interval_hours"] = interval_hours
            update["stale_threshold_hours"] = interval_hours * 3
        if enabled is not None:
            update["enabled"] = enabled
        result = await self.db.ml_schedule_policies.update_one(
            {"tenant_id": tenant_id, "model_type": model_type},
            {"$set": update},
        )
        if result.matched_count == 0:
            return {"success": False, "error": "Schedule not found"}
        return {"success": True}

    async def _prevent_duplicate(self, tenant_id: str, model_type: str) -> bool:
        """Return True if a run is already in progress."""
        running = await self.db.ml_execution_jobs.find_one(
            {"tenant_id": tenant_id, "model_type": model_type, "status": ExecutionStatus.RUNNING},
            {"_id": 0},
        )
        return running is not None

    async def trigger_execution(self, tenant_id: str, model_type: str,
                                property_id: Optional[str] = None,
                                triggered_by: str = "manual") -> dict:
        """Trigger a model execution."""
        if await self._prevent_duplicate(tenant_id, model_type):
            return {"success": False, "error": "Execution already running", "status": "skipped"}

        job = new_execution_job(tenant_id, model_type, property_id, triggered_by)
        await self.db.ml_execution_jobs.insert_one(job)

        # execute in background
        asyncio.create_task(self._run_model(job))
        return {"success": True, "job_id": job["id"], "model_type": model_type, "status": "started"}

    async def _run_model(self, job: dict):
        """Execute the model and store results."""
        job_id = job["id"]
        tenant_id = job["tenant_id"]
        model_type = job["model_type"]
        start = datetime.now(timezone.utc)

        await self.db.ml_execution_jobs.update_one(
            {"id": job_id},
            {"$set": {"status": ExecutionStatus.RUNNING, "started_at": start.isoformat()}},
        )

        try:
            result = {}
            confidence = 0.0

            if model_type == ModelType.REVENUE_ML:
                from modules.data_intelligence.revenue_ml_pipeline import revenue_pipeline
                result = await revenue_pipeline.run_pipeline(tenant_id)
                confidence = result.get("confidence_score", 0.75)
            elif model_type == ModelType.OPERATIONAL_AI:
                from modules.data_intelligence.operational_ai import operational_ai
                result = await operational_ai.get_dashboard(tenant_id)
                confidence = 0.82
            elif model_type == ModelType.GUEST_INTELLIGENCE:
                from modules.data_intelligence.guest_intelligence import guest_intelligence
                result = await guest_intelligence.get_dashboard(tenant_id, 30)
                confidence = 0.78

            end = datetime.now(timezone.utc)
            duration_ms = int((end - start).total_seconds() * 1000)

            # store snapshot
            snapshot = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "model_type": model_type,
                "job_id": job_id,
                "data": result,
                "confidence_avg": confidence,
                "created_at": end.isoformat(),
            }
            await self.db.ml_snapshots.insert_one(snapshot)

            await self.db.ml_execution_jobs.update_one(
                {"id": job_id},
                {"$set": {
                    "status": ExecutionStatus.COMPLETED,
                    "completed_at": end.isoformat(),
                    "duration_ms": duration_ms,
                    "result_snapshot_id": snapshot["id"],
                    "confidence_avg": confidence,
                    "updated_at": end.isoformat(),
                }},
            )

            # update schedule
            await self.db.ml_schedule_policies.update_one(
                {"tenant_id": tenant_id, "model_type": model_type},
                {"$set": {"last_run_at": end.isoformat()}},
            )

            # alert on low confidence
            if confidence < 0.5:
                await self._log_alert(tenant_id, model_type, job_id, f"Low confidence: {confidence}")

        except Exception as e:
            logger.exception(f"ML execution failed: {model_type}")
            end = datetime.now(timezone.utc)
            await self.db.ml_execution_jobs.update_one(
                {"id": job_id},
                {"$set": {
                    "status": ExecutionStatus.FAILED,
                    "error_message": str(e)[:500],
                    "completed_at": end.isoformat(),
                    "duration_ms": int((end - start).total_seconds() * 1000),
                    "updated_at": end.isoformat(),
                }},
            )
            await self._log_alert(tenant_id, model_type, job_id, f"Execution failed: {str(e)[:200]}")

    async def _log_alert(self, tenant_id: str, model_type: str, job_id: str, message: str):
        await self.db.system_alerts.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "source": "ml_scheduler",
            "severity": "high",
            "title": f"ML Execution Alert: {model_type}",
            "message": message,
            "entity_type": "ml_execution_job",
            "entity_id": job_id,
            "acknowledged": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    async def get_execution_history(self, tenant_id: str, model_type: Optional[str] = None,
                                     limit: int = 20) -> list:
        q = {"tenant_id": tenant_id}
        if model_type:
            q["model_type"] = model_type
        return await self.db.ml_execution_jobs.find(
            q, {"_id": 0}
        ).sort("created_at", -1).to_list(limit)

    async def get_stale_models(self, tenant_id: str) -> list:
        """Find models whose last run exceeds the stale threshold."""
        policies = await self.get_schedule_policies(tenant_id)
        stale = []
        now = datetime.now(timezone.utc)
        for p in policies:
            if not p.get("enabled"):
                continue
            last_run = p.get("last_run_at")
            threshold = p.get("stale_threshold_hours", 24)
            if not last_run:
                stale.append({"model_type": p["model_type"], "hours_overdue": None, "status": "never_run"})
            else:
                try:
                    lr = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                    delta = (now - lr).total_seconds() / 3600
                    if delta > threshold:
                        stale.append({"model_type": p["model_type"], "hours_overdue": round(delta, 1), "status": "stale"})
                except Exception:
                    stale.append({"model_type": p["model_type"], "hours_overdue": None, "status": "parse_error"})
        return stale

    async def get_dashboard(self, tenant_id: str) -> dict:
        policies = await self.get_schedule_policies(tenant_id)
        recent_jobs = await self.get_execution_history(tenant_id, limit=10)
        stale = await self.get_stale_models(tenant_id)
        return {
            "schedules": policies,
            "recent_executions": recent_jobs,
            "stale_models": stale,
        }
