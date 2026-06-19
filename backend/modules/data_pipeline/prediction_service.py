"""
Prediction Service - Serves predictions from deployed models with confidence monitoring.
"""
import logging
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
        """Generate a prediction using the deployed model.

        Fail-closed: eğitilmiş/yayınlanmış (deployed) gerçek bir model yoksa
        tahmin fabrikasyonu yapılmaz; data_available:false döner. Yayınlanmış
        model varsa çıktı kural-tabanlı deterministiktir (rastgele yok).
        """
        now = datetime.now(UTC).isoformat()

        deployed = await model_registry.get_deployed_model(tenant_id, model_type)
        if not deployed:
            return {
                "tenant_id": tenant_id,
                "model_type": model_type,
                "data_available": False,
                "model_trained": False,
                "message": "Bu model türü için yayınlanmış (deployed) eğitilmiş model yok. Tahmin üretilmedi.",
                "created_at": now,
            }

        result = self._generate_prediction(model_type, input_data)
        if result is None:
            return {
                "tenant_id": tenant_id,
                "model_type": model_type,
                "model_id": deployed["id"],
                "model_version": deployed["version"],
                "data_available": False,
                "message": "Bu model türü için gerçek (deterministik) çıktı üretilemiyor.",
                "created_at": now,
            }

        prediction_id = str(uuid.uuid4())
        confidence = result.get("confidence")
        confidence_band = None
        if confidence is not None:
            confidence_band = "low"
            if confidence >= CONFIDENCE_THRESHOLDS["high"]:
                confidence_band = "high"
            elif confidence >= CONFIDENCE_THRESHOLDS["medium"]:
                confidence_band = "medium"

        prediction = {
            "id": prediction_id,
            "tenant_id": tenant_id,
            "model_type": model_type,
            "model_id": deployed["id"],
            "model_version": deployed["version"],
            "input_summary": {k: type(v).__name__ for k, v in input_data.items()},
            "result": result,
            "confidence": confidence,
            "confidence_band": confidence_band,
            "data_available": True,
            "created_at": now,
        }

        await db.ml_predictions.insert_one({**prediction})

        if confidence is not None:
            await model_registry.update_prediction_stats(deployed["id"], confidence)

        return {k: v for k, v in prediction.items() if k != "_id"}

    def _generate_prediction(self, model_type: str, input_data: dict) -> dict | None:
        """Yayınlanmış model için kural-tabanlı deterministik çıktı.

        Rastgele (fabrikasyon) değer üretilmez ve uydurma confidence eklenmez.
        guest_intelligence ve bilinmeyen tipler için gerçek deterministik bir
        temel olmadığından None döner (üst katman fail-closed eder).
        """
        if model_type == "revenue_ml":
            base_rate = input_data.get("current_rate", 150)
            occ = input_data.get("occupancy", 0.65)
            adjustment = (occ - 0.5) * 0.3
            recommended = round(base_rate * (1 + adjustment), 2)
            return {
                "recommended_rate": recommended,
                "rate_change_pct": round(adjustment * 100, 1),
                "demand_level": "high" if occ > 0.8 else "medium" if occ > 0.5 else "low",
            }
        elif model_type == "operational_ai":
            departures = input_data.get("expected_departures", 15)
            return {
                "predicted_checkouts": departures,
                "hk_staff_needed": max(3, departures // 4),
            }
        return None

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
