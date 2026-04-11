"""
Revenue Domain — Pricing Repository
Data access layer for pricing and rate management. No FastAPI dependencies.
"""
from typing import Any

from core.tenant_db import LazyCollection


class PricingRepository:
    """MongoDB operations for rate plans and pricing."""

    rate_plans = LazyCollection("rate_plans")
    rate_periods = LazyCollection("rate_periods")
    rate_overrides = LazyCollection("rate_overrides")

    @classmethod
    async def get_rate_plans(cls, tenant_id: str) -> list[dict[str, Any]]:
        return await cls.rate_plans.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(500)

    @classmethod
    async def get_rate_plan(cls, tenant_id: str, plan_id: str) -> dict[str, Any] | None:
        return await cls.rate_plans.find_one(
            {"tenant_id": tenant_id, "id": plan_id}, {"_id": 0}
        )

    @classmethod
    async def upsert_rate_plan(cls, plan: dict[str, Any]) -> None:
        await cls.rate_plans.update_one(
            {"tenant_id": plan["tenant_id"], "id": plan["id"]},
            {"$set": plan},
            upsert=True,
        )

    @classmethod
    async def get_rate_periods(
        cls, tenant_id: str, *, room_type: str | None = None,
        date_from: str | None = None, date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if room_type:
            query["room_type_id"] = room_type
        if date_from:
            query.setdefault("start_date", {})["$lte"] = date_to or date_from
        if date_to:
            query.setdefault("end_date", {})["$gte"] = date_from or date_to
        return await cls.rate_periods.find(query, {"_id": 0}).to_list(500)

    @classmethod
    async def insert_rate_override(cls, override: dict[str, Any]) -> None:
        await cls.rate_overrides.insert_one(override)

    @classmethod
    async def get_rate_overrides(cls, tenant_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return await cls.rate_overrides.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)
