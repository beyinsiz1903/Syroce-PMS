"""
Revenue Domain — Pricing Repository
Data access layer for pricing and rate management. No FastAPI dependencies.
"""
from typing import Optional, List, Dict, Any

from core.database import db


class PricingRepository:
    """MongoDB operations for rate plans and pricing."""

    rate_plans = db.rate_plans
    rate_periods = db.rate_periods
    rate_overrides = db.rate_overrides

    @classmethod
    async def get_rate_plans(cls, tenant_id: str) -> List[Dict[str, Any]]:
        return await cls.rate_plans.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(500)

    @classmethod
    async def get_rate_plan(cls, tenant_id: str, plan_id: str) -> Optional[Dict[str, Any]]:
        return await cls.rate_plans.find_one(
            {"tenant_id": tenant_id, "id": plan_id}, {"_id": 0}
        )

    @classmethod
    async def upsert_rate_plan(cls, plan: Dict[str, Any]) -> None:
        await cls.rate_plans.update_one(
            {"tenant_id": plan["tenant_id"], "id": plan["id"]},
            {"$set": plan},
            upsert=True,
        )

    @classmethod
    async def get_rate_periods(
        cls, tenant_id: str, *, room_type: Optional[str] = None,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if room_type:
            query["room_type_id"] = room_type
        if date_from:
            query.setdefault("start_date", {})["$lte"] = date_to or date_from
        if date_to:
            query.setdefault("end_date", {})["$gte"] = date_from or date_to
        return await cls.rate_periods.find(query, {"_id": 0}).to_list(500)

    @classmethod
    async def insert_rate_override(cls, override: Dict[str, Any]) -> None:
        await cls.rate_overrides.insert_one(override)

    @classmethod
    async def get_rate_overrides(cls, tenant_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        return await cls.rate_overrides.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)
