"""
Revenue Domain — Pricing Service
Business logic for rate management and pricing. No FastAPI dependencies.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

from domains.revenue.pricing.repositories.pricing_repository import PricingRepository


class PricingService:
    """Pure business logic for pricing and rate management."""

    @staticmethod
    async def get_rate_plans(tenant_id: str) -> List[Dict[str, Any]]:
        return await PricingRepository.get_rate_plans(tenant_id)

    @staticmethod
    async def create_rate_plan(tenant_id: str, plan_data: Dict[str, Any]) -> Dict[str, Any]:
        plan = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            **plan_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await PricingRepository.upsert_rate_plan(plan)
        return plan

    @staticmethod
    async def get_effective_rate(
        tenant_id: str, room_type: str,
        check_in: str, check_out: str,
    ) -> Dict[str, Any]:
        """Calculate the effective rate for a room type and date range."""
        rate_periods = await PricingRepository.get_rate_periods(
            tenant_id, room_type=room_type, date_from=check_in, date_to=check_out,
        )

        if rate_periods:
            avg_rate = sum(rp.get("rate", 0) for rp in rate_periods) / len(rate_periods)
            return {
                "rate": round(avg_rate, 2),
                "source": "rate_periods",
                "periods_found": len(rate_periods),
            }

        # Fallback to room base price
        from core.database import db
        room = await db.rooms.find_one(
            {"tenant_id": tenant_id, "room_type": room_type},
            {"_id": 0, "base_price": 1},
        )
        if room:
            return {
                "rate": room.get("base_price", 0),
                "source": "rooms.base_price",
                "periods_found": 0,
            }

        return {"rate": 0, "source": "none", "periods_found": 0}

    @staticmethod
    async def override_rate(
        tenant_id: str, user_id: str,
        room_type: str, date_range: Dict[str, str],
        new_rate: float, reason: str,
    ) -> Dict[str, Any]:
        override = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "room_type": room_type,
            "date_from": date_range.get("from"),
            "date_to": date_range.get("to"),
            "rate": new_rate,
            "reason": reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await PricingRepository.insert_rate_override(override)
        return override
