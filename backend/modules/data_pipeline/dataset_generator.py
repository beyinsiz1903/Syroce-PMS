"""
Dataset Generator - Creates training datasets from feature store outputs.
Supports dataset versioning and lineage tracking.
"""
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core.database import db

logger = logging.getLogger("data_pipeline.dataset_generator")


class DatasetGenerator:
    """Generates versioned training datasets from feature store data."""

    async def generate_dataset(self, tenant_id: str, model_type: str,
                               feature_set: str, description: str = "") -> dict[str, Any]:
        """Generate a new training dataset from latest features."""
        dataset_id = str(uuid.uuid4())
        version = await self._next_version(tenant_id, model_type)
        now = datetime.now(UTC).isoformat()

        latest_features = await db.feature_store.find_one(
            {"tenant_id": tenant_id, "feature_set": feature_set},
            {"_id": 0},
            sort=[("extracted_at", -1)],
        )

        if not latest_features:
            return {
                "error": f"No features found for set '{feature_set}'",
                "tenant_id": tenant_id,
            }

        record_count = latest_features.get("record_count", 0)
        feature_data = latest_features.get("features", {})

        dataset = {
            "id": dataset_id,
            "tenant_id": tenant_id,
            "model_type": model_type,
            "feature_set": feature_set,
            "version": version,
            "description": description or f"Auto-generated dataset v{version}",
            "status": "ready",
            "record_count": record_count,
            "feature_count": len(feature_data),
            "feature_names": list(feature_data.keys()),
            "lineage": {
                "source_collection": feature_set,
                "feature_extraction_time": latest_features.get("extracted_at"),
                "source_date_range": latest_features.get("date_range"),
                "generation_time": now,
            },
            "quality_metrics": {
                "completeness": self._compute_completeness(feature_data),
                "freshness_hours": self._compute_freshness(latest_features.get("extracted_at")),
            },
            "created_at": now,
        }

        await db.ml_datasets.insert_one({**dataset})
        logger.info(f"Dataset generated: {dataset_id} v{version} for {model_type}")
        return {k: v for k, v in dataset.items() if k != "_id"}

    async def list_datasets(self, tenant_id: str, model_type: str | None = None,
                            limit: int = 20) -> list[dict]:
        q: dict[str, Any] = {"tenant_id": tenant_id}
        if model_type:
            q["model_type"] = model_type
        datasets = await db.ml_datasets.find(
            q, {"_id": 0}
        ).sort("created_at", -1).to_list(limit)
        return datasets

    async def get_dataset(self, dataset_id: str) -> dict | None:
        return await db.ml_datasets.find_one({"id": dataset_id}, {"_id": 0})

    async def _next_version(self, tenant_id: str, model_type: str) -> int:
        latest = await db.ml_datasets.find_one(
            {"tenant_id": tenant_id, "model_type": model_type},
            {"version": 1, "_id": 0},
            sort=[("version", -1)],
        )
        return (latest.get("version", 0) if latest else 0) + 1

    def _compute_completeness(self, features: dict) -> float:
        if not features:
            return 0.0
        non_null = sum(1 for v in features.values() if v is not None and v != 0 and v != "")
        return round(non_null / len(features), 4)

    def _compute_freshness(self, extracted_at: str | None) -> float:
        if not extracted_at:
            return 999.0
        try:
            dt = datetime.fromisoformat(extracted_at.replace("Z", "+00:00"))
            delta = datetime.now(UTC) - dt
            return round(delta.total_seconds() / 3600, 2)
        except (ValueError, TypeError):
            return 999.0


dataset_generator = DatasetGenerator()
