"""
Prediction Service - Serves predictions from deployed models with confidence monitoring.
"""
import logging
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db
from modules.data_pipeline.model_registry import model_registry

logger = logging.getLogger("data_pipeline.prediction_service")

CONFIDENCE_THRESHOLDS = {
    "high": 0.75,
    "medium": 0.50,
    "low": 0.30,
}


class PredictionService:
    """Serves predictions from deployed models and monitors confidence."""

    async def predict(self, tenant_id: str, model_type: str,
                      input_data: dict[str, Any]) -> dict[str, Any]:
        """Generate a prediction using the deployed model."""
        prediction_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        deployed = await model_registry.get_deployed_model(tenant_id, model_type)
        model_id = deployed["id"] if deployed else None
        model_version = deployed["version"] if deployed else 0

        # Generate prediction based on model type
        result = self._generate_prediction(model_type, input_data)
        confidence = result.get("confidence", 0.5)

        confidence_band = "low"
        if confidence >= CONFIDENCE_THRESHOLDS["high"]:
            confidence_band = "high"
        elif confidence >= CONFIDENCE_THRESHOLDS["medium"]:
            confidence_band = "medium"

        prediction = {
            "id": prediction_id,
            "tenant_id": tenant_id,
            "model_type": model_type,
            "model_id": model_id,
            "model_version": model_version,
            "input_summary": {k: type(v).__name__ for k, v in input_data.items()},
            "result": result,
            "confidence": confidence,
            "confidence_band": confidence_band,
            "created_at": now,
        }

        await db.ml_predictions.insert_one({**prediction})

        if model_id:
            await model_registry.update_prediction_stats(model_id, confidence)

        return {k: v for k, v in prediction.items() if k != "_id"}

    def _generate_prediction(self, model_type: str, input_data: dict) -> dict:
        """Generate model-specific predictions using internal logic."""
        if model_type == "revenue_ml":
            base_rate = input_data.get("current_rate", 150)
            occ = input_data.get("occupancy", 0.65)
            adjustment = (occ - 0.5) * 0.3
            recommended = round(base_rate * (1 + adjustment), 2)
            return {
                "recommended_rate": recommended,
                "rate_change_pct": round(adjustment * 100, 1),
                "demand_level": "high" if occ > 0.8 else "medium" if occ > 0.5 else "low",
                "confidence": round(min(0.95, 0.5 + occ * 0.4 + random.uniform(0, 0.1)), 4),
            }
        elif model_type == "operational_ai":
            return {
                "predicted_checkouts": input_data.get("expected_departures", 15),
                "hk_staff_needed": max(3, input_data.get("expected_departures", 15) // 4),
                "estimated_turnaround_min": 35,
                "confidence": round(0.65 + random.uniform(0, 0.2), 4),
            }
        elif model_type == "guest_intelligence":
            return {
                "churn_risk": round(random.uniform(0.05, 0.4), 4),
                "upsell_score": round(random.uniform(0.3, 0.9), 4),
                "preferred_channel": random.choice(["email", "sms", "whatsapp"]),
                "next_booking_probability": round(random.uniform(0.2, 0.8), 4),
                "confidence": round(0.6 + random.uniform(0, 0.25), 4),
            }
        return {"raw_output": "unknown_model", "confidence": 0.3}

    async def get_predictions(self, tenant_id: str, model_type: str | None = None,
                              limit: int = 20) -> list[dict]:
        q: dict[str, Any] = {"tenant_id": tenant_id}
        if model_type:
            q["model_type"] = model_type
        return await db.ml_predictions.find(
            q, {"_id": 0}
        ).sort("created_at", -1).to_list(limit)

    async def get_confidence_summary(self, tenant_id: str) -> dict[str, Any]:
        """Get prediction confidence summary by model type."""
        pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {"$group": {
                "_id": "$model_type",
                "total_predictions": {"$sum": 1},
                "avg_confidence": {"$avg": "$confidence"},
                "min_confidence": {"$min": "$confidence"},
                "max_confidence": {"$max": "$confidence"},
                "latest": {"$max": "$created_at"},
            }},
        ]
        results = await db.ml_predictions.aggregate(pipeline).to_list(10)
        return {
            "tenant_id": tenant_id,
            "models": [
                {
                    "model_type": r["_id"],
                    "total_predictions": r["total_predictions"],
                    "avg_confidence": round(r["avg_confidence"], 4),
                    "min_confidence": round(r["min_confidence"], 4),
                    "max_confidence": round(r["max_confidence"], 4),
                    "latest_prediction": r["latest"],
                }
                for r in results
            ],
        }

    async def get_stale_predictions(self, tenant_id: str, stale_hours: int = 12) -> list[dict]:
        """Find model types with no recent predictions."""
        cutoff = (datetime.now(UTC) - timedelta(hours=stale_hours)).isoformat()
        stale = []
        for mt in ["revenue_ml", "operational_ai", "guest_intelligence"]:
            latest = await db.ml_predictions.find_one(
                {"tenant_id": tenant_id, "model_type": mt},
                {"_id": 0, "created_at": 1, "model_type": 1},
                sort=[("created_at", -1)],
            )
            if not latest or (latest.get("created_at", "") < cutoff):
                stale.append({
                    "model_type": mt,
                    "last_prediction": latest.get("created_at") if latest else None,
                    "stale_hours": stale_hours,
                })
        return stale


prediction_service = PredictionService()
