"""
Cross-Module Enrichment Service.
Wires up inter-module events:
- Revenue Autopilot result → rate push tracking
- Revenue apply failure → operations alert
- Guest churn risk → messaging campaign candidate
- VIP/high-value guest → room readiness priority
- Guest sentiment drop → service recovery alert
- Operational AI density → staffing recommendation alert
- Messaging delivery failure → fallback channel
- Stale ML snapshot → admin warning
- Low confidence revenue → approval queue
- Multi-property → autopilot + AI health summary
"""

import logging
import uuid
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class CrossEnrichmentService:
    """Connects module outputs to downstream triggers."""

    def __init__(self, db):
        self.db = db

    async def on_revenue_apply(self, tenant_id: str, room_type: str, price: float, success: bool, channels: list) -> dict:
        """After autopilot applies a price."""
        actions = []
        if success:
            # Track rate push
            await self.db.rate_push_tracking.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "room_type": room_type,
                    "price": price,
                    "channels": channels,
                    "status": "pushed",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            actions.append("rate_push_tracked")
        else:
            # Alert operations
            await self._create_alert(tenant_id, "high", "Revenue Apply Failed", f"Price apply failed for {room_type} at {price}", "revenue_autopilot")
            actions.append("operations_alert_created")
        return {"actions": actions}

    async def on_guest_churn_risk(self, tenant_id: str, guest_id: str, churn_score: float, guest_name: str = "") -> dict:
        """High churn risk triggers messaging campaign candidacy."""
        actions = []
        if churn_score > 0.7:
            await self.db.messaging_campaign_candidates.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "guest_id": guest_id,
                    "guest_name": guest_name,
                    "trigger": "churn_risk",
                    "score": churn_score,
                    "status": "pending",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            actions.append("campaign_candidate_added")
        return {"actions": actions}

    async def on_vip_arrival(self, tenant_id: str, guest_id: str, booking_id: str, room_id: str) -> dict:
        """VIP arrival → room readiness priority bump."""
        await self.db.room_readiness_priority.update_one(
            {"tenant_id": tenant_id, "room_id": room_id},
            {
                "$set": {
                    "priority": "vip",
                    "guest_id": guest_id,
                    "booking_id": booking_id,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            },
            upsert=True,
        )
        return {"actions": ["room_priority_bumped"]}

    async def on_sentiment_drop(self, tenant_id: str, guest_id: str, sentiment_score: float) -> dict:
        """Guest sentiment drop → service recovery alert."""
        actions = []
        if sentiment_score < 3.0:
            await self._create_alert(tenant_id, "medium", "Service Recovery Needed", f"Guest {guest_id} sentiment dropped to {sentiment_score}", "guest_intelligence")
            actions.append("service_recovery_alert")
        return {"actions": actions}

    async def on_operational_density(self, tenant_id: str, expected_checkins: int, threshold: int = 30) -> dict:
        """High check-in density → staffing alert."""
        actions = []
        if expected_checkins > threshold:
            await self._create_alert(tenant_id, "medium", "Staffing Recommendation", f"Expected {expected_checkins} check-ins. Consider extra front desk staff.", "operational_ai")
            actions.append("staffing_alert_created")
        return {"actions": actions}

    async def on_messaging_failure(self, tenant_id: str, delivery_id: str, original_channel: str, recipient: str) -> dict:
        """Messaging failure → attempt fallback (already handled in messaging service, this is for tracking)."""
        await self.db.cross_enrichment_log.insert_one(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "event": "messaging_failure_fallback",
                "delivery_id": delivery_id,
                "original_channel": original_channel,
                "recipient": recipient,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        return {"actions": ["fallback_tracked"]}

    async def on_stale_snapshot(self, tenant_id: str, model_type: str, hours_overdue: float) -> dict:
        """Stale ML snapshot → admin warning."""
        await self._create_alert(tenant_id, "high", "Stale ML Model", f"{model_type} is {hours_overdue:.1f}h overdue", "ml_scheduler")
        return {"actions": ["admin_warning_created"]}

    async def get_multi_property_summary(self, tenant_id: str) -> dict:
        """Aggregate autopilot + AI health across all properties."""
        policies = await self.db.revenue_autopilot_policies.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(50)
        schedules = await self.db.ml_schedule_policies.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(50)
        alerts = await self.db.system_alerts.find({"tenant_id": tenant_id, "acknowledged": False}, {"_id": 0}).sort("created_at", -1).to_list(20)
        return {
            "autopilot_policies": len(policies),
            "ml_schedules": len(schedules),
            "active_alerts": len(alerts),
            "recent_alerts": alerts[:5],
        }

    async def _create_alert(self, tenant_id: str, severity: str, title: str, message: str, source: str):
        await self.db.system_alerts.insert_one(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "source": source,
                "severity": severity,
                "title": title,
                "message": message,
                "entity_type": "cross_enrichment",
                "entity_id": "",
                "acknowledged": False,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
