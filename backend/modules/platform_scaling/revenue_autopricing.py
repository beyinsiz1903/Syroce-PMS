"""
Revenue Auto-Pricing Workflow - Controlled and automatic rate application
with approval workflows, rollback support, blackout rules, audit trail,
and channel push status tracking.
"""
import uuid
from datetime import datetime, timezone, date
from typing import Dict, Any, Optional
from core.database import db
import logging

logger = logging.getLogger(__name__)


class AutoPricingWorkflow:
    """
    Revenue recommendation → approval → apply → push → audit workflow.
    Supports both human-approval and auto-apply modes.
    """

    # ── Recommendation Creation ──

    async def create_recommendation(
        self, tenant_id: str, room_type: str, current_rate: float,
        suggested_rate: float, reason: str, source: str = "ml",
        confidence: float = 0.0, property_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a pricing recommendation for review/auto-apply."""
        # Check property automation policy
        policy = await self._get_automation_policy(tenant_id, property_id)
        change_pct = abs(suggested_rate - current_rate) / max(current_rate, 1) * 100

        # Check blackout/protected dates
        today_s = date.today().isoformat()
        is_protected = await self._is_protected_date(tenant_id, today_s)

        # Determine auto-apply eligibility
        auto_eligible = (
            policy.get("mode") in ("full_auto", "supervised")
            and change_pct <= policy.get("max_auto_change_pct", 10)
            and suggested_rate >= policy.get("min_rate", 0)
            and suggested_rate <= policy.get("max_rate", 99999)
            and not is_protected
        )

        rec = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "property_id": property_id or tenant_id,
            "room_type": room_type,
            "current_rate": current_rate,
            "suggested_rate": suggested_rate,
            "change_pct": round(change_pct, 2),
            "reason": reason,
            "source": source,
            "confidence": round(confidence, 3),
            "status": "pending",
            "auto_eligible": auto_eligible,
            "is_protected_date": is_protected,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.pricing_recommendations.insert_one(rec)

        # Auto-apply if eligible and policy allows
        if auto_eligible and policy.get("mode") == "full_auto":
            return await self.apply_recommendation(tenant_id, rec["id"], "system", auto=True)

        return {"success": True, "recommendation_id": rec["id"],
                "auto_eligible": auto_eligible, "status": "pending_approval"}

    # ── Approval Workflow ──

    async def approve_recommendation(self, tenant_id: str, rec_id: str,
                                      user_id: str, note: Optional[str] = None) -> Dict[str, Any]:
        """Approve and apply a pricing recommendation."""
        rec = await db.pricing_recommendations.find_one(
            {"id": rec_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not rec:
            return {"success": False, "error": "Recommendation not found"}
        if rec["status"] != "pending":
            return {"success": False, "error": f"Cannot approve: status is {rec['status']}"}

        await db.pricing_recommendations.update_one(
            {"id": rec_id},
            {"$set": {"status": "approved", "approved_by": user_id,
                       "approved_at": datetime.now(timezone.utc).isoformat(),
                       "approval_note": note}},
        )
        return await self.apply_recommendation(tenant_id, rec_id, user_id)

    async def reject_recommendation(self, tenant_id: str, rec_id: str,
                                     user_id: str, reason: str = "") -> Dict[str, Any]:
        """Reject a pricing recommendation."""
        result = await db.pricing_recommendations.update_one(
            {"id": rec_id, "tenant_id": tenant_id, "status": "pending"},
            {"$set": {"status": "rejected", "rejected_by": user_id,
                       "rejected_at": datetime.now(timezone.utc).isoformat(),
                       "rejection_reason": reason}},
        )
        if result.matched_count == 0:
            return {"success": False, "error": "Recommendation not found or not pending"}
        return {"success": True, "recommendation_id": rec_id, "status": "rejected"}

    # ── Rate Application ──

    async def apply_recommendation(self, tenant_id: str, rec_id: str,
                                    user_id: str, auto: bool = False) -> Dict[str, Any]:
        """Apply the recommended rate to rooms."""
        rec = await db.pricing_recommendations.find_one(
            {"id": rec_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not rec:
            return {"success": False, "error": "Recommendation not found"}

        room_type = rec["room_type"]
        new_rate = rec["suggested_rate"]
        old_rate = rec["current_rate"]
        property_id = rec.get("property_id", tenant_id)

        # Store rollback snapshot
        rooms_before = await db.rooms.find(
            {"tenant_id": property_id, "room_type": room_type},
            {"_id": 0, "id": 1, "base_price": 1},
        ).to_list(500)

        rollback_snapshot = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "recommendation_id": rec_id,
            "room_type": room_type,
            "rooms": [{"room_id": r["id"], "old_price": r.get("base_price", 0)} for r in rooms_before],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.pricing_rollbacks.insert_one(rollback_snapshot)

        # Apply new rate
        update_result = await db.rooms.update_many(
            {"tenant_id": property_id, "room_type": room_type},
            {"$set": {"base_price": new_rate,
                       "rate_updated_at": datetime.now(timezone.utc).isoformat(),
                       "rate_source": "auto_pricing"}},
        )

        # Update recommendation status
        await db.pricing_recommendations.update_one(
            {"id": rec_id},
            {"$set": {
                "status": "applied",
                "applied_by": user_id,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "auto_applied": auto,
                "rooms_affected": update_result.modified_count,
                "rollback_id": rollback_snapshot["id"],
            }},
        )

        # Audit trail
        await db.pricing_audit.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "recommendation_id": rec_id,
            "action": "apply",
            "room_type": room_type,
            "old_rate": old_rate,
            "new_rate": new_rate,
            "rooms_affected": update_result.modified_count,
            "applied_by": user_id,
            "auto": auto,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Channel push status tracking (simulate)
        push_status = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "recommendation_id": rec_id,
            "room_type": room_type,
            "new_rate": new_rate,
            "channels": [],
            "status": "pending_push",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        # Check connected channels
        channels = await db.channel_connections.find(
            {"tenant_id": tenant_id, "status": "active"},
            {"_id": 0, "id": 1, "channel_type": 1, "name": 1},
        ).to_list(50)
        for ch in channels:
            push_status["channels"].append({
                "channel_id": ch["id"],
                "channel_name": ch.get("name") or ch.get("channel_type"),
                "push_status": "queued",
            })
        if not channels:
            push_status["status"] = "no_channels"
        await db.rate_push_tracking.insert_one(push_status)

        return {
            "success": True,
            "recommendation_id": rec_id,
            "status": "applied",
            "auto": auto,
            "room_type": room_type,
            "old_rate": old_rate,
            "new_rate": new_rate,
            "rooms_affected": update_result.modified_count,
            "rollback_id": rollback_snapshot["id"],
            "channel_push_id": push_status["id"],
        }

    # ── Rollback ──

    async def rollback_recommendation(self, tenant_id: str, rec_id: str,
                                       user_id: str, reason: str = "") -> Dict[str, Any]:
        """Rollback a previously applied recommendation."""
        rec = await db.pricing_recommendations.find_one(
            {"id": rec_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not rec or rec.get("status") != "applied":
            return {"success": False, "error": "No applied recommendation found"}

        rollback_id = rec.get("rollback_id")
        snapshot = await db.pricing_rollbacks.find_one(
            {"id": rollback_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not snapshot:
            return {"success": False, "error": "Rollback snapshot not found"}

        # Restore old prices
        restored = 0
        for room_data in snapshot.get("rooms", []):
            await db.rooms.update_one(
                {"id": room_data["room_id"]},
                {"$set": {"base_price": room_data["old_price"],
                           "rate_updated_at": datetime.now(timezone.utc).isoformat(),
                           "rate_source": "rollback"}},
            )
            restored += 1

        # Update recommendation
        await db.pricing_recommendations.update_one(
            {"id": rec_id},
            {"$set": {"status": "rolled_back",
                       "rolled_back_by": user_id,
                       "rolled_back_at": datetime.now(timezone.utc).isoformat(),
                       "rollback_reason": reason}},
        )

        # Audit
        await db.pricing_audit.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "recommendation_id": rec_id,
            "action": "rollback",
            "room_type": rec["room_type"],
            "restored_rooms": restored,
            "rolled_back_by": user_id,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {"success": True, "recommendation_id": rec_id, "status": "rolled_back",
                "rooms_restored": restored}

    # ── Protected Dates / Blackout Rules ──

    async def add_protected_dates(self, tenant_id: str, start_date: str, end_date: str,
                                   reason: str, user_id: str) -> Dict[str, Any]:
        rule = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date,
            "reason": reason,
            "created_by": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "active": True,
        }
        await db.protected_dates.insert_one(rule)
        return {"success": True, "rule_id": rule["id"]}

    async def get_protected_dates(self, tenant_id: str) -> Dict[str, Any]:
        rules = await db.protected_dates.find(
            {"tenant_id": tenant_id, "active": True}, {"_id": 0}
        ).to_list(200)
        return {"count": len(rules), "rules": rules}

    async def _is_protected_date(self, tenant_id: str, date_str: str) -> bool:
        rule = await db.protected_dates.find_one({
            "tenant_id": tenant_id, "active": True,
            "start_date": {"$lte": date_str},
            "end_date": {"$gte": date_str},
        })
        return bool(rule)

    # ── Automation Policy ──

    async def set_automation_policy(self, tenant_id: str, mode: str,
                                     max_auto_change_pct: float = 10,
                                     min_rate: float = 0, max_rate: float = 99999,
                                     property_id: Optional[str] = None,
                                     user_id: str = "") -> Dict[str, Any]:
        pid = property_id or tenant_id
        policy = {
            "tenant_id": tenant_id,
            "property_id": pid,
            "mode": mode,  # full_auto, supervised, manual
            "max_auto_change_pct": max_auto_change_pct,
            "min_rate": min_rate,
            "max_rate": max_rate,
            "updated_by": user_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.automation_policies.update_one(
            {"tenant_id": tenant_id, "property_id": pid},
            {"$set": policy},
            upsert=True,
        )
        return {"success": True, "policy": policy}

    async def _get_automation_policy(self, tenant_id: str, property_id: Optional[str] = None) -> Dict:
        pid = property_id or tenant_id
        policy = await db.automation_policies.find_one(
            {"tenant_id": tenant_id, "property_id": pid}, {"_id": 0}
        )
        return policy or {"mode": "manual", "max_auto_change_pct": 10,
                          "min_rate": 0, "max_rate": 99999}

    # ── Dashboard / Queries ──

    async def get_pending_recommendations(self, tenant_id: str) -> Dict[str, Any]:
        recs = await db.pricing_recommendations.find(
            {"tenant_id": tenant_id, "status": "pending"},
            {"_id": 0},
        ).sort("created_at", -1).to_list(100)
        return {"count": len(recs), "recommendations": recs}

    async def get_recommendation_history(self, tenant_id: str, limit: int = 50) -> Dict[str, Any]:
        recs = await db.pricing_recommendations.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        return {"count": len(recs), "recommendations": recs}

    async def get_pricing_audit_trail(self, tenant_id: str, limit: int = 50) -> Dict[str, Any]:
        audits = await db.pricing_audit.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        return {"count": len(audits), "audits": audits}

    async def get_channel_push_status(self, tenant_id: str, rec_id: Optional[str] = None) -> Dict[str, Any]:
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if rec_id:
            query["recommendation_id"] = rec_id
        pushes = await db.rate_push_tracking.find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(50).to_list(50)
        return {"count": len(pushes), "pushes": pushes}

    async def get_autopricing_dashboard(self, tenant_id: str) -> Dict[str, Any]:
        pending = await self.get_pending_recommendations(tenant_id)
        policy = await self._get_automation_policy(tenant_id)
        protected = await self.get_protected_dates(tenant_id)

        # Recent activity
        recent = await db.pricing_recommendations.find(
            {"tenant_id": tenant_id},
            {"_id": 0, "status": 1},
        ).to_list(500)

        stats = {"pending": 0, "applied": 0, "rejected": 0, "rolled_back": 0}
        for r in recent:
            s = r.get("status", "")
            if s in stats:
                stats[s] += 1

        return {
            "tenant_id": tenant_id,
            "policy": policy,
            "pending_count": pending["count"],
            "pending_recommendations": pending["recommendations"][:10],
            "protected_dates": protected,
            "stats": stats,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# Singleton
autopricing = AutoPricingWorkflow()
