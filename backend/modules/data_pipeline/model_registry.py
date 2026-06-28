"""
Model Registry - Model version tracking, training metrics, and lifecycle management.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

logger = logging.getLogger("data_pipeline.model_registry")


class ModelStatus:
    TRAINING = "training"
    READY = "ready"
    DEPLOYED = "deployed"
    DEPRECATED = "deprecated"
    FAILED = "failed"


class ModelRegistry:
    """Tracks ML model versions, training metrics, and deployment status."""

    MODEL_TYPES = ["revenue_ml", "operational_ai", "guest_intelligence"]

    async def register_model(self, tenant_id: str, model_type: str, dataset_id: str, training_metrics: dict[str, Any], description: str = "") -> dict[str, Any]:
        """Register a new model version after training."""
        model_id = str(uuid.uuid4())
        version = await self._next_version(tenant_id, model_type)
        now = datetime.now(UTC).isoformat()

        model = {
            "id": model_id,
            "tenant_id": tenant_id,
            "model_type": model_type,
            "version": version,
            "dataset_id": dataset_id,
            "status": ModelStatus.READY,
            "description": description or f"{model_type} v{version}",
            "training_metrics": training_metrics,
            "deployment": {
                "deployed_at": None,
                "predictions_made": 0,
                "avg_confidence": 0.0,
                "last_prediction_at": None,
            },
            "lineage": {
                "dataset_id": dataset_id,
                "trained_at": now,
                "framework": "internal",
            },
            "created_at": now,
            "updated_at": now,
        }

        await db.model_registry.insert_one({**model})
        logger.info(f"Model registered: {model_id} {model_type} v{version}")
        return {k: v for k, v in model.items() if k != "_id"}

    async def deploy_model(self, model_id: str) -> dict[str, Any]:
        """Mark a model as deployed (active for predictions)."""
        model = await db.model_registry.find_one({"id": model_id}, {"_id": 0})
        if not model:
            return {"error": "Model not found"}

        # Deprecate previous deployed version
        await db.model_registry.update_many(
            {
                "tenant_id": model["tenant_id"],
                "model_type": model["model_type"],
                "status": ModelStatus.DEPLOYED,
                "id": {"$ne": model_id},
            },
            {"$set": {"status": ModelStatus.DEPRECATED, "updated_at": datetime.now(UTC).isoformat()}},
        )

        now = datetime.now(UTC).isoformat()
        await db.model_registry.update_one(
            {"id": model_id},
            {
                "$set": {
                    "status": ModelStatus.DEPLOYED,
                    "deployment.deployed_at": now,
                    "updated_at": now,
                }
            },
        )
        return {"model_id": model_id, "status": "deployed", "deployed_at": now}

    async def get_deployed_model(self, tenant_id: str, model_type: str) -> dict | None:
        """Get the currently deployed model for a type."""
        return await db.model_registry.find_one(
            {"tenant_id": tenant_id, "model_type": model_type, "status": ModelStatus.DEPLOYED},
            {"_id": 0},
        )

    async def list_models(self, tenant_id: str, model_type: str | None = None, limit: int = 20) -> list[dict]:
        q: dict[str, Any] = {"tenant_id": tenant_id}
        if model_type:
            q["model_type"] = model_type
        return await db.model_registry.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)

    async def update_prediction_stats(self, model_id: str, confidence: float):
        """Update prediction statistics for a deployed model."""
        model = await db.model_registry.find_one({"id": model_id}, {"_id": 0})
        if not model:
            return
        dep = model.get("deployment", {})
        count = dep.get("predictions_made", 0) + 1
        avg_conf = dep.get("avg_confidence", 0.0)
        new_avg = round(((avg_conf * (count - 1)) + confidence) / count, 4)
        now = datetime.now(UTC).isoformat()
        await db.model_registry.update_one(
            {"id": model_id},
            {
                "$set": {
                    "deployment.predictions_made": count,
                    "deployment.avg_confidence": new_avg,
                    "deployment.last_prediction_at": now,
                    "updated_at": now,
                }
            },
        )

    async def get_stale_models(self, tenant_id: str, stale_hours: int = 24) -> list[dict]:
        """Find models whose last prediction is older than threshold."""
        cutoff = (datetime.now(UTC) - timedelta(hours=stale_hours)).isoformat()
        return await db.model_registry.find(
            {
                "tenant_id": tenant_id,
                "status": ModelStatus.DEPLOYED,
                "$or": [
                    {"deployment.last_prediction_at": {"$lt": cutoff}},
                    {"deployment.last_prediction_at": None},
                ],
            },
            {"_id": 0},
        ).to_list(20)

    async def get_summary(self, tenant_id: str) -> dict[str, Any]:
        """Get model registry summary."""
        pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {
                "$group": {
                    "_id": {"type": "$model_type", "status": "$status"},
                    "count": {"$sum": 1},
                    "latest": {"$max": "$created_at"},
                }
            },
        ]
        results = await db.model_registry.aggregate(pipeline).to_list(50)

        by_type: dict[str, dict] = {}
        for r in results:
            mt = r["_id"]["type"]
            st = r["_id"]["status"]
            if mt not in by_type:
                by_type[mt] = {"total": 0, "by_status": {}, "latest": None}
            by_type[mt]["total"] += r["count"]
            by_type[mt]["by_status"][st] = r["count"]
            if not by_type[mt]["latest"] or r["latest"] > by_type[mt]["latest"]:
                by_type[mt]["latest"] = r["latest"]

        return {
            "tenant_id": tenant_id,
            "model_types": by_type,
            "available_types": self.MODEL_TYPES,
        }

    async def _next_version(self, tenant_id: str, model_type: str) -> int:
        latest = await db.model_registry.find_one(
            {"tenant_id": tenant_id, "model_type": model_type},
            {"version": 1, "_id": 0},
            sort=[("version", -1)],
        )
        return (latest.get("version", 0) if latest else 0) + 1


model_registry = ModelRegistry()
