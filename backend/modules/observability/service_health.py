"""
Service Health Monitor — checks all critical services and dependencies.
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List

logger = logging.getLogger("observability.health")


class ServiceHealthMonitor:
    """Monitors health of all platform dependencies."""

    def __init__(self):
        self._history: List[dict] = []
        self._max_history = 100

    async def check_all_services(self) -> dict:
        results = {}

        # MongoDB
        results["mongodb"] = await self._check_mongodb()

        # Event Bus
        results["event_bus"] = await self._check_event_bus()

        # Messaging
        results["messaging"] = await self._check_messaging()

        # Data Pipeline
        results["data_pipeline"] = await self._check_data_pipeline()

        # ML Models
        results["ml_models"] = await self._check_ml_models()

        # Determine overall
        statuses = [v.get("status", "unknown") for v in results.values()]
        if all(s == "healthy" for s in statuses):
            overall = "healthy"
        elif any(s == "unhealthy" for s in statuses):
            overall = "degraded"
        else:
            overall = "degraded"

        snapshot = {
            "overall_status": overall,
            "services": results,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        # Persist
        self._history.append(snapshot)
        if len(self._history) > self._max_history:
            self._history = self._history[-50:]

        try:
            from core.database import db
            await db.health_check_history.insert_one({**snapshot})
        except Exception:
            pass

        return snapshot

    async def _check_mongodb(self) -> dict:
        start = time.time()
        try:
            from core.database import db
            await db.command("ping")
            return {"status": "healthy", "latency_ms": round((time.time() - start) * 1000, 2)}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)[:200], "latency_ms": round((time.time() - start) * 1000, 2)}

    async def _check_event_bus(self) -> dict:
        try:
            from modules.event_bus.abstraction import event_bus
            status = await event_bus.get_status()
            return {
                "status": "healthy" if status.get("backend_status") == "healthy" else "degraded",
                "mode": status.get("mode"),
                "active_sessions": status.get("total_sessions", 0),
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)[:200]}

    async def _check_messaging(self) -> dict:
        try:
            from core.database import db
            one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            failures = await db.messaging_delivery_logs.count_documents({
                "status": "failed",
                "created_at": {"$gte": one_hour_ago},
            })
            return {"status": "healthy" if failures < 10 else "degraded", "failures_1h": failures}
        except Exception:
            return {"status": "unknown"}

    async def _check_data_pipeline(self) -> dict:
        try:
            from core.database import db
            recent = await db.pipeline_runs.find_one(
                {}, {"_id": 0, "status": 1, "started_at": 1},
                sort=[("started_at", -1)],
            )
            if recent:
                return {"status": "healthy", "last_run_status": recent.get("status")}
            return {"status": "healthy", "last_run_status": "no_runs"}
        except Exception:
            return {"status": "unknown"}

    async def _check_ml_models(self) -> dict:
        try:
            from core.database import db
            model_count = await db.model_versions.estimated_document_count()
            return {"status": "healthy", "registered_models": model_count}
        except Exception:
            return {"status": "unknown"}

    async def get_health_history(self, hours: int = 24, limit: int = 50) -> List[dict]:
        try:
            from core.database import db
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            return await db.health_check_history.find(
                {"checked_at": {"$gte": cutoff}}, {"_id": 0}
            ).sort("checked_at", -1).to_list(limit)
        except Exception:
            return self._history[-limit:]


service_health = ServiceHealthMonitor()
