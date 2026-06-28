"""
Revenue Autopilot Service.
Converts ML recommendations into auto-applied or queued pricing decisions.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException

logger = logging.getLogger(__name__)


class AutopilotMode:
    FULL_AUTO = "full_auto"
    SUPERVISED = "supervised"
    ADVISORY = "advisory"


class ApprovalStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPLIED = "auto_applied"
    ROLLED_BACK = "rolled_back"


def new_autopilot_policy(tenant_id: str, property_id: str | None = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "property_id": property_id,
        "mode": AutopilotMode.SUPERVISED,
        "confidence_threshold_auto": 0.85,
        "confidence_threshold_queue": 0.50,
        "max_price_change_pct": 20.0,
        "blackout_dates": [],
        "protected_room_types": [],
        "enabled": True,
        "daily_summary_enabled": True,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def new_approval_item(
    tenant_id: str,
    property_id: str | None,
    room_type: str,
    target_date: str,
    current_price: float,
    recommended_price: float,
    confidence: float,
    reason: str,
    source_job_id: str | None = None,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "property_id": property_id,
        "room_type": room_type,
        "target_date": target_date,
        "current_price": current_price,
        "recommended_price": recommended_price,
        "price_change_pct": round(((recommended_price - current_price) / max(current_price, 1)) * 100, 2),
        "confidence": confidence,
        "reason": reason,
        "status": ApprovalStatus.PENDING,
        "source_job_id": source_job_id,
        "applied_at": None,
        "applied_by": None,
        "rejected_reason": None,
        "rollback_price": None,
        "channel_push_status": None,
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def new_apply_result(
    tenant_id: str,
    approval_item_id: str,
    room_type: str,
    old_price: float,
    new_price: float,
    channels_pushed: list,
    success: bool,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "approval_item_id": approval_item_id,
        "room_type": room_type,
        "old_price": old_price,
        "new_price": new_price,
        "channels_pushed": channels_pushed,
        "success": success,
        "error_message": None,
        "created_at": datetime.now(UTC).isoformat(),
    }


class RevenueAutopilotService:
    """Revenue Autopilot - Controlled auto-pricing from ML recommendations."""

    def __init__(self, db):
        self.db = db

    async def get_policy(self, tenant_id: str, property_id: str | None = None) -> dict:
        q = {"tenant_id": tenant_id}
        if property_id:
            q["property_id"] = property_id
        policy = await self.db.revenue_autopilot_policies.find_one(q, {"_id": 0})
        if not policy:
            policy = new_autopilot_policy(tenant_id, property_id)
            await self.db.revenue_autopilot_policies.insert_one(policy)
            policy.pop("_id", None)
        return policy

    async def update_policy(self, tenant_id: str, updates: dict) -> dict:
        allowed = ["mode", "confidence_threshold_auto", "confidence_threshold_queue", "max_price_change_pct", "blackout_dates", "protected_room_types", "enabled", "daily_summary_enabled"]
        filtered = {k: v for k, v in updates.items() if k in allowed}
        filtered["updated_at"] = datetime.now(UTC).isoformat()
        result = await self.db.revenue_autopilot_policies.update_one(
            {"tenant_id": tenant_id},
            {"$set": filtered},
        )
        if result.matched_count == 0:
            return {"success": False, "error": "Policy not found"}
        return {"success": True}

    async def process_recommendation(self, tenant_id: str, recommendation: dict) -> dict:
        """Process a single ML recommendation through the autopilot pipeline."""
        policy = await self.get_policy(tenant_id)
        if not policy.get("enabled"):
            return {"action": "skipped", "reason": "Autopilot disabled"}

        room_type = recommendation.get("room_type", "Standard")
        target_date = recommendation.get("target_date", "")
        current_price = recommendation.get("current_price", 0)
        recommended_price = recommendation.get("recommended_price", 0)
        confidence = recommendation.get("confidence", 0)

        # blackout check
        if target_date in policy.get("blackout_dates", []):
            return {"action": "blocked", "reason": "Blackout date"}

        # protected room type
        if room_type in policy.get("protected_room_types", []):
            return {"action": "blocked", "reason": "Protected room type"}

        # price change limit
        if current_price > 0:
            change_pct = abs((recommended_price - current_price) / current_price * 100)
            if change_pct > policy.get("max_price_change_pct", 20):
                item = new_approval_item(
                    tenant_id,
                    policy.get("property_id"),
                    room_type,
                    target_date,
                    current_price,
                    recommended_price,
                    confidence,
                    f"Price change {change_pct:.1f}% exceeds limit",
                    recommendation.get("source_job_id"),
                )
                await self.db.revenue_approval_queue.insert_one(item)
                return {"action": "queued", "reason": "Exceeds max change", "item_id": item["id"]}

        mode = policy.get("mode", AutopilotMode.SUPERVISED)
        auto_threshold = policy.get("confidence_threshold_auto", 0.85)
        queue_threshold = policy.get("confidence_threshold_queue", 0.50)

        if mode == AutopilotMode.FULL_AUTO and confidence >= auto_threshold:
            # auto-apply
            result = await self._apply_price(tenant_id, room_type, target_date, current_price, recommended_price)
            if result.get("success"):
                item = new_approval_item(
                    tenant_id,
                    policy.get("property_id"),
                    room_type,
                    target_date,
                    current_price,
                    recommended_price,
                    confidence,
                    "Auto-applied (high confidence)",
                    recommendation.get("source_job_id"),
                )
                item["status"] = ApprovalStatus.AUTO_APPLIED
                item["applied_at"] = datetime.now(UTC).isoformat()
                item["applied_by"] = "autopilot"
                item["channel_push_status"] = "local_only"
                await self.db.revenue_approval_queue.insert_one(item)

                apply_doc = new_apply_result(tenant_id, item["id"], room_type, current_price, recommended_price, result.get("channels", []), True)
                await self.db.revenue_apply_results.insert_one(apply_doc)
                return {"action": "auto_applied", "item_id": item["id"], "result": result}

            # Apply did not actually change a rate plan (no matching plan or DB
            # error). Marking it AUTO_APPLIED would be a fake success, so queue
            # it for manual review instead (doctrine: fail-closed / no fake-green).
            reason = "error" if result.get("error") else "no matching rate plan"
            item = new_approval_item(
                tenant_id,
                policy.get("property_id"),
                room_type,
                target_date,
                current_price,
                recommended_price,
                confidence,
                f"Auto-apply failed ({reason}); queued for manual review",
                recommendation.get("source_job_id"),
            )
            await self.db.revenue_approval_queue.insert_one(item)
            return {"action": "queued", "reason": "auto_apply_failed", "item_id": item["id"], "result": result}

        elif confidence >= queue_threshold:
            item = new_approval_item(
                tenant_id,
                policy.get("property_id"),
                room_type,
                target_date,
                current_price,
                recommended_price,
                confidence,
                "Queued for approval" if mode != AutopilotMode.ADVISORY else "Advisory only",
                recommendation.get("source_job_id"),
            )
            await self.db.revenue_approval_queue.insert_one(item)
            return {"action": "queued", "item_id": item["id"]}

        else:
            return {"action": "rejected", "reason": f"Confidence {confidence} below threshold {queue_threshold}"}

    async def _apply_price(self, tenant_id: str, room_type: str, target_date: str, old_price: float, new_price: float) -> dict:
        """Update the PMS-side rate plan base_price for the room type.

        Distribution to OTA channels is handled by the channel manager's own
        rate-push flow (unified rate manager), not here, so we report the local
        rate update only and never claim a direct channel push that did not
        happen (doctrine: no fake-green).
        """
        try:
            res = await self.db.rate_plans.update_many(
                {"tenant_id": tenant_id, "room_type": room_type},
                {"$set": {"base_price": new_price, "updated_at": datetime.now(UTC).isoformat()}},
            )
            # A price is only really "applied" when a rate plan for this room
            # type actually exists and matched; matched_count==0 means nothing
            # was changed, so we must NOT report success (doctrine: no fake-green).
            applied = res.matched_count > 0
            if applied:
                # audit only an apply that actually matched a rate plan
                await self.db.audit_logs.insert_one(
                    {
                        "id": str(uuid.uuid4()),
                        "tenant_id": tenant_id,
                        "user_id": "autopilot",
                        "action": "revenue_autopilot_apply",
                        "entity_type": "rate_plan",
                        "entity_id": room_type,
                        "changes": {"old_price": old_price, "new_price": new_price, "target_date": target_date},
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            return {
                "success": applied,
                "channels": [],
                "rate_plans_matched": res.matched_count,
                "rate_plans_updated": res.modified_count,
            }
        except Exception as e:
            logger.exception("Price apply error")
            return {"success": False, "error": str(e)[:200], "channels": []}

    async def approve_item(self, tenant_id: str, item_id: str, user_id: str) -> dict:
        item = await self.db.revenue_approval_queue.find_one({"id": item_id, "tenant_id": tenant_id, "status": ApprovalStatus.PENDING}, {"_id": 0})
        if not item:
            raise HTTPException(status_code=404, detail="Item not found or not pending")

        result = await self._apply_price(
            tenant_id,
            item["room_type"],
            item["target_date"],
            item["current_price"],
            item["recommended_price"],
        )
        if not result.get("success"):
            # Nothing was actually applied (no matching rate plan or DB error).
            # Do not mark the item APPROVED or return success — that would be a
            # fake-green. Leave it PENDING so it stays visible and actionable.
            if result.get("error"):
                raise HTTPException(status_code=500, detail="Fiyat uygulanamadı (iç hata)")
            raise HTTPException(
                status_code=409,
                detail="Eşleşen oda tipi fiyat planı bulunamadı; fiyat uygulanmadı",
            )

        await self.db.revenue_approval_queue.update_one(
            {"id": item_id},
            {
                "$set": {
                    "status": ApprovalStatus.APPROVED,
                    "applied_at": datetime.now(UTC).isoformat(),
                    "applied_by": user_id,
                    "channel_push_status": "local_only",
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            },
        )
        apply_doc = new_apply_result(tenant_id, item_id, item["room_type"], item["current_price"], item["recommended_price"], result.get("channels", []), True)
        await self.db.revenue_apply_results.insert_one(apply_doc)
        return {"success": True, "result": result}

    async def reject_item(self, tenant_id: str, item_id: str, user_id: str, reason: str = "") -> dict:
        result = await self.db.revenue_approval_queue.update_one(
            {"id": item_id, "tenant_id": tenant_id, "status": ApprovalStatus.PENDING},
            {
                "$set": {
                    "status": ApprovalStatus.REJECTED,
                    "applied_by": user_id,
                    "rejected_reason": reason,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            },
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Item not found or not pending")
        return {"success": True}

    async def rollback_item(self, tenant_id: str, item_id: str, user_id: str) -> dict:
        item = await self.db.revenue_approval_queue.find_one(
            {"id": item_id, "tenant_id": tenant_id, "status": {"$in": [ApprovalStatus.APPROVED, ApprovalStatus.AUTO_APPLIED]}},
            {"_id": 0},
        )
        if not item:
            raise HTTPException(status_code=404, detail="Item not found or not applied")

        # Rollback restores the previous price by applying it back to the rate
        # plan; if that apply did not actually match a rate plan (or errored),
        # the rollback did NOT happen, so we must not mark it ROLLED_BACK or
        # report success (doctrine: no fake-green terminal state / fail-closed).
        result = await self._apply_price(
            tenant_id,
            item["room_type"],
            item["target_date"],
            item["recommended_price"],
            item["current_price"],
        )
        if not result.get("success"):
            if result.get("error"):
                raise HTTPException(status_code=500, detail="Fiyat geri alınamadı (iç hata)")
            raise HTTPException(
                status_code=409,
                detail="Eşleşen oda tipi fiyat planı bulunamadı; geri alınamadı",
            )

        await self.db.revenue_approval_queue.update_one(
            {"id": item_id},
            {
                "$set": {
                    "status": ApprovalStatus.ROLLED_BACK,
                    "rollback_price": item["current_price"],
                    "applied_by": user_id,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            },
        )
        return {"success": True, "rolled_back_to": item["current_price"]}

    async def get_approval_queue(self, tenant_id: str, status_filter: str | None = None, limit: int = 50) -> list:
        q = {"tenant_id": tenant_id}
        if status_filter:
            q["status"] = status_filter
        return await self.db.revenue_approval_queue.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)

    async def get_daily_summary(self, tenant_id: str) -> dict:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        cutoff = f"{today}T00:00:00"
        pipeline = [
            {"$match": {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        cursor = self.db.revenue_approval_queue.aggregate(pipeline)
        results = await cursor.to_list(20)
        summary = {r["_id"]: r["count"] for r in results}
        total = sum(summary.values())
        return {
            "date": today,
            "total_recommendations": total,
            "auto_applied": summary.get(ApprovalStatus.AUTO_APPLIED, 0),
            "pending_approval": summary.get(ApprovalStatus.PENDING, 0),
            "approved": summary.get(ApprovalStatus.APPROVED, 0),
            "rejected": summary.get(ApprovalStatus.REJECTED, 0),
            "rolled_back": summary.get(ApprovalStatus.ROLLED_BACK, 0),
        }

    async def get_dashboard(self, tenant_id: str) -> dict:
        policy = await self.get_policy(tenant_id)
        queue = await self.get_approval_queue(tenant_id, ApprovalStatus.PENDING, 20)
        summary = await self.get_daily_summary(tenant_id)
        recent_applied = await self.db.revenue_apply_results.find({"tenant_id": tenant_id}, {"_id": 0}).sort("created_at", -1).to_list(10)
        return {
            "policy": policy,
            "pending_queue": queue,
            "daily_summary": summary,
            "recent_applies": recent_applied,
        }
