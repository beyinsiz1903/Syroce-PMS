"""
Revenue ML Pipeline - Orchestrates existing ML models into a unified pricing pipeline.
Pipeline: historical → demand forecast → rate elasticity → booking probability
→ cancellation prediction → ADR recommendation → confidence score
→ human override threshold → automation rules → channel push → rollback protection

Integrates with:
- modules/platform_scaling/revenue_ml.py (existing ML models)
- modules/platform_scaling/revenue_autopricing.py (existing auto-pricing workflow)
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.database import db
from modules.platform_scaling.revenue_autopricing import autopricing
from modules.platform_scaling.revenue_ml import (
    BookingProbabilityModel,
    CancellationPredictionModel,
    DemandForecastingModel,
    RateElasticityModel,
)

logger = logging.getLogger(__name__)

# Confidence thresholds
HIGH_CONFIDENCE = 0.75
MEDIUM_CONFIDENCE = 0.50
LOW_CONFIDENCE = 0.30
HUMAN_OVERRIDE_THRESHOLD = 0.60  # Below this, require human approval


class RevenueMLPipeline:
    """
    Full ML-driven pricing pipeline that:
    1. Gathers signals from all ML models
    2. Produces ADR recommendations with confidence scores
    3. Routes through automation rules or human approval
    4. Tracks channel push outcomes
    5. Supports rollback
    """

    def __init__(self):
        self.demand_model = DemandForecastingModel()
        self.elasticity_model = RateElasticityModel()
        self.booking_prob_model = BookingProbabilityModel()
        self.cancellation_model = CancellationPredictionModel()

    # ── Full Pipeline Execution ──

    async def run_pipeline(self, tenant_id: str, room_type: Optional[str] = None,
                           target_date: Optional[str] = None,
                           property_id: Optional[str] = None) -> Dict[str, Any]:
        """Execute the full revenue ML pipeline for a tenant/room_type."""
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)

        # Resolve room types
        room_types = [room_type] if room_type else await db.rooms.distinct(
            "room_type", {"tenant_id": tenant_id,
                          "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]}
        )
        if not room_types:
            room_types = ["Standard"]

        # Step 1: Demand Forecast
        demand = await self.demand_model.forecast_demand(tenant_id, 14)

        # Step 2: Rate Elasticity
        elasticity_results = {}
        for rt in room_types:
            elasticity_results[rt] = await self.elasticity_model.analyze_elasticity(tenant_id, rt)

        # Step 3: At-risk bookings (cancellation)
        at_risk = await self.cancellation_model.get_at_risk_bookings(tenant_id, 0.25)

        # Step 4: Portfolio conversion rates
        conversion = await self.booking_prob_model.get_portfolio_conversion_rates(tenant_id)

        # Step 5: Generate recommendations per room type
        recommendations = []
        for rt in room_types:
            rec = await self._generate_recommendation(
                tenant_id, rt, demand, elasticity_results.get(rt, {}),
                at_risk, conversion, property_id
            )
            if rec:
                recommendations.append(rec)

        # Step 6: Persist pipeline run snapshot
        snapshot = {
            "id": run_id,
            "tenant_id": tenant_id,
            "property_id": property_id or tenant_id,
            "model_type": "revenue_ml_pipeline",
            "input_window": {"forecast_days": 14, "room_types": room_types},
            "output_summary": {
                "recommendations_count": len(recommendations),
                "room_types_analyzed": len(room_types),
                "at_risk_bookings": at_risk.get("at_risk_count", 0),
                "at_risk_revenue": at_risk.get("total_at_risk_revenue", 0),
            },
            "confidence_score": self._avg_confidence(recommendations),
            "generated_at": started_at.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
        }
        await db.revenue_ml_snapshots.insert_one(snapshot)

        # Step 7: Model execution log
        await self._log_execution(tenant_id, run_id, "revenue_ml_pipeline",
                                  "success", len(recommendations), started_at)

        return {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "pipeline": "revenue_ml",
            "recommendations": recommendations,
            "signals": {
                "demand_summary": self._summarize_demand(demand),
                "elasticity_summary": {rt: {
                    "coefficient": e.get("elasticity_coefficient", 0),
                    "interpretation": e.get("interpretation", "unknown"),
                } for rt, e in elasticity_results.items()},
                "cancellation_risk": {
                    "at_risk_count": at_risk.get("at_risk_count", 0),
                    "at_risk_revenue": at_risk.get("total_at_risk_revenue", 0),
                },
                "conversion_rates": {
                    r["source"]: r["conversion_rate"]
                    for r in conversion.get("by_source", [])[:5]
                },
            },
            "generated_at": started_at.isoformat(),
        }

    async def _generate_recommendation(
        self, tenant_id: str, room_type: str,
        demand: Dict, elasticity: Dict, at_risk: Dict,
        conversion: Dict, property_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Generate a single ADR recommendation for a room type."""
        # Get current average price
        rooms = await db.rooms.find(
            {"tenant_id": tenant_id, "room_type": room_type},
            {"_id": 0, "base_price": 1},
        ).to_list(500)
        if not rooms:
            return None
        current_avg = sum(r.get("base_price", 0) for r in rooms) / max(len(rooms), 1)
        if current_avg <= 0:
            return None

        # Signals
        demand_signal = self._extract_demand_signal(demand)
        pace_signal = self._extract_pace_signal(demand)
        cancel_risk = at_risk.get("at_risk_count", 0) / max(
            at_risk.get("at_risk_count", 0) + 10, 1)
        price_sensitivity = elasticity.get("elasticity_coefficient", -1.0)

        # ADR adjustment logic
        adjustment = 0.0
        reasons = []

        # Demand signal
        if demand_signal > 0.75:
            adjustment += 0.08
            reasons.append({"signal": "demand", "direction": "up",
                           "detail": f"Yuksek talep ({demand_signal:.0%})", "impact": 0.08})
        elif demand_signal > 0.55:
            adjustment += 0.03
            reasons.append({"signal": "demand", "direction": "up",
                           "detail": f"Orta talep ({demand_signal:.0%})", "impact": 0.03})
        elif demand_signal < 0.35:
            adjustment -= 0.05
            reasons.append({"signal": "demand", "direction": "down",
                           "detail": f"Dusuk talep ({demand_signal:.0%})", "impact": -0.05})

        # Pace signal
        if pace_signal > 0.7:
            adjustment += 0.04
            reasons.append({"signal": "pace", "direction": "up",
                           "detail": "Guclu rezervasyon hizi", "impact": 0.04})
        elif pace_signal < 0.3:
            adjustment -= 0.03
            reasons.append({"signal": "pace", "direction": "down",
                           "detail": "Yavas rezervasyon hizi", "impact": -0.03})

        # Cancellation risk
        if cancel_risk > 0.3:
            adjustment -= 0.02
            reasons.append({"signal": "cancellation_risk", "direction": "down",
                           "detail": f"Yuksek iptal riski ({cancel_risk:.0%})", "impact": -0.02})

        # Price sensitivity
        if price_sensitivity > -0.5:  # inelastic
            adjustment += 0.03
            reasons.append({"signal": "price_sensitivity", "direction": "up",
                           "detail": "Fiyat duyarsiz talep", "impact": 0.03})
        elif price_sensitivity < -1.2:  # very elastic
            adjustment -= 0.03
            reasons.append({"signal": "price_sensitivity", "direction": "down",
                           "detail": "Fiyata cok duyarli talep", "impact": -0.03})

        suggested_rate = round(current_avg * (1 + adjustment), 2)
        change_pct = round(abs(suggested_rate - current_avg) / current_avg * 100, 2)

        # Confidence calculation
        confidence = self._calculate_confidence(
            demand_signal, pace_signal, cancel_risk, price_sensitivity,
            elasticity.get("data_points", 0)
        )

        # Confidence band
        if confidence >= HIGH_CONFIDENCE:
            confidence_band = "high"
        elif confidence >= MEDIUM_CONFIDENCE:
            confidence_band = "medium"
        else:
            confidence_band = "low"

        # Auto-apply eligibility
        auto_eligible = confidence >= HUMAN_OVERRIDE_THRESHOLD and change_pct <= 15

        # Build recommendation reason summary
        direction = "increase" if suggested_rate > current_avg else (
            "decrease" if suggested_rate < current_avg else "hold")
        reason_text = f"ML Pipeline: {direction} ({change_pct}%) - " + ", ".join(
            [r["detail"] for r in reasons[:3]])

        rec_data = {
            "room_type": room_type,
            "current_rate": round(current_avg, 2),
            "suggested_rate": suggested_rate,
            "change_pct": change_pct,
            "direction": direction,
            "confidence_score": round(confidence, 3),
            "confidence_band": confidence_band,
            "auto_eligible": auto_eligible,
            "requires_human_approval": confidence < HUMAN_OVERRIDE_THRESHOLD,
            "recommendation_reasons": reasons,
            "explainability": {
                "demand_signal": round(demand_signal, 3),
                "pace_signal": round(pace_signal, 3),
                "cancellation_risk": round(cancel_risk, 3),
                "price_sensitivity": round(price_sensitivity, 3),
                "recommendation_reason": reason_text,
            },
        }

        # Route through autopricing workflow
        try:
            result = await autopricing.create_recommendation(
                tenant_id=tenant_id,
                room_type=room_type,
                current_rate=round(current_avg, 2),
                suggested_rate=suggested_rate,
                reason=reason_text,
                source="ml_pipeline",
                confidence=confidence,
                property_id=property_id,
            )
            rec_data["recommendation_id"] = result.get("recommendation_id")
            rec_data["auto_applied"] = result.get("status") == "applied"
            rec_data["workflow_status"] = result.get("status", "pending_approval")
        except Exception as e:
            logger.error(f"Failed to create recommendation: {e}")
            rec_data["recommendation_id"] = None
            rec_data["workflow_status"] = "error"

        return rec_data

    def _extract_demand_signal(self, demand: Dict) -> float:
        """Extract aggregate demand signal from forecast."""
        forecast = demand.get("forecast", [])
        if not forecast:
            return 0.5
        occ_values = [f.get("predicted_occupancy_pct", 50) for f in forecast[:7]]
        return min(sum(occ_values) / len(occ_values) / 100, 1.0)

    def _extract_pace_signal(self, demand: Dict) -> float:
        """Extract booking pace signal."""
        forecast = demand.get("forecast", [])
        if not forecast:
            return 0.5
        total_rooms = demand.get("total_rooms", 1)
        otb_values = [f.get("on_the_books", 0) for f in forecast[:7]]
        avg_otb = sum(otb_values) / max(len(otb_values), 1)
        return min(avg_otb / max(total_rooms, 1), 1.0)

    def _calculate_confidence(self, demand: float, pace: float,
                              cancel_risk: float, sensitivity: float,
                              data_points: int) -> float:
        """Calculate composite confidence score."""
        # Base confidence from data availability
        data_conf = min(data_points / 50, 1.0) * 0.3

        # Signal consistency - if signals agree, higher confidence
        signals_positive = sum([
            demand > 0.5, pace > 0.5, cancel_risk < 0.2, sensitivity > -1.0
        ])
        signals_negative = sum([
            demand < 0.5, pace < 0.5, cancel_risk > 0.3, sensitivity < -1.0
        ])
        consistency = max(signals_positive, signals_negative) / 4
        signal_conf = consistency * 0.5

        # Demand strength
        demand_conf = abs(demand - 0.5) * 0.4

        raw = data_conf + signal_conf + demand_conf
        return min(max(round(raw, 3), 0.1), 0.95)

    def _avg_confidence(self, recommendations: List[Dict]) -> float:
        if not recommendations:
            return 0.0
        scores = [r.get("confidence_score", 0) for r in recommendations]
        return round(sum(scores) / len(scores), 3)

    def _summarize_demand(self, demand: Dict) -> Dict[str, Any]:
        forecast = demand.get("forecast", [])
        if not forecast:
            return {"avg_occupancy": 0, "high_days": 0, "low_days": 0}
        occ = [f.get("predicted_occupancy_pct", 0) for f in forecast]
        return {
            "avg_occupancy": round(sum(occ) / len(occ), 1),
            "high_demand_days": sum(1 for f in forecast if f.get("demand_level") == "high"),
            "low_demand_days": sum(1 for f in forecast if f.get("demand_level") == "low"),
            "total_forecast_days": len(forecast),
        }

    # ── Forecast Dashboard ──

    async def get_forecast_dashboard(self, tenant_id: str) -> Dict[str, Any]:
        """Get comprehensive forecast dashboard data."""
        demand = await self.demand_model.forecast_demand(tenant_id, 14)
        price_points = await self.elasticity_model.get_optimal_price_points(tenant_id)
        at_risk = await self.cancellation_model.get_at_risk_bookings(tenant_id, 0.25)
        conversion = await self.booking_prob_model.get_portfolio_conversion_rates(tenant_id)

        # Recent pipeline recommendations
        recent_recs = await db.pricing_recommendations.find(
            {"tenant_id": tenant_id, "source": "ml_pipeline"},
            {"_id": 0},
        ).sort("created_at", -1).limit(20).to_list(20)

        # Pipeline run history
        recent_runs = await db.revenue_ml_snapshots.find(
            {"tenant_id": tenant_id},
            {"_id": 0},
        ).sort("generated_at", -1).limit(5).to_list(5)

        # Auto-pricing dashboard
        autopricing_dash = await autopricing.get_autopricing_dashboard(tenant_id)

        return {
            "tenant_id": tenant_id,
            "demand_forecast": demand,
            "price_optimization": price_points,
            "cancellation_risk": {
                "at_risk_count": at_risk.get("at_risk_count", 0),
                "at_risk_revenue": at_risk.get("total_at_risk_revenue", 0),
                "top_at_risk": at_risk.get("bookings", [])[:5],
            },
            "conversion_rates": conversion,
            "ml_recommendations": recent_recs,
            "pipeline_runs": recent_runs,
            "autopricing": autopricing_dash,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Model Execution Logging ──

    async def _log_execution(self, tenant_id: str, run_id: str,
                             model_type: str, status: str,
                             output_count: int, started_at: datetime):
        await db.model_execution_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "run_id": run_id,
            "model_type": model_type,
            "status": status,
            "output_count": output_count,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000),
        })


# Singleton
revenue_pipeline = RevenueMLPipeline()
