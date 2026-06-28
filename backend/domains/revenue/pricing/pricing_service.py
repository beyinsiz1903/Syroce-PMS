"""
Revenue / Pricing — Service Layer
Orchestrates rate plan management, demand forecasting, competitor analysis,
dynamic pricing, and rate overrides. No FastAPI dependencies.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)


class PricingService:
    """Business logic for pricing & revenue management."""

    def __init__(self):
        from core.database import db

        self._db = db

    async def update_room_rate(self, ctx: OperationContext, rate_data: dict) -> ServiceResult:
        """Fiyat degisikligini yerel olarak KAYDET ve pinned-provider durumunu durustce raporla.

        Bu uc UYDURMA 'tum kanallara gonderildi' URETMEZ: fiyat niyetini rate_updates'e
        kaydeder (gercek audit kaydi), pinned saglayiciyi yalnizca-okuma tespit eder
        (pilot_drift=0) ve durumu durustce dondurur. Gercek OTA dagitimi Unified Rate
        Manager (Toplu Fiyat/Envanter) ekranindan, pinned saglayici uzerinden yapilir.
        """
        # Girdi dogrulama (fail-closed; uydurma varsayilan oda tipi/fiyat YOK).
        room_type = rate_data.get("room_type")
        target_date = rate_data.get("target_date") or rate_data.get("date")
        new_rate = rate_data.get("new_rate")
        valid_rate = isinstance(new_rate, (int, float)) and not isinstance(new_rate, bool) and new_rate > 0
        if not room_type or not target_date or not valid_rate:
            return ServiceResult.success(
                {
                    "success": False,
                    "message": "Eksik/gecersiz alan: oda tipi, tarih ve pozitif bir fiyat gereklidir.",
                    "data_available": False,
                    "queued": False,
                    "pushed": False,
                    "pushed_to": [],
                    "channels_updated": 0,
                }
            )

        # Pinned-provider tespiti OTORITERDIR; istemci girdisi ezemez (yalnizca okuma).
        try:
            from domains.channel_manager.unified_rate_manager_router import (
                _detect_active_provider,
            )

            detection = await _detect_active_provider(ctx.tenant_id, prefer=None)
        except Exception:
            detection = {"provider": None, "configuration_error": "detection_failed"}
        provider = detection.get("provider")
        configuration_error = detection.get("configuration_error")
        ari_status = "recorded_local" if provider else "not_configured"

        # Fiyat niyetini yerel audit olarak kaydet (gercek kayit; uydurma push YOK).
        rate_update = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            "room_type": room_type,
            "target_date": target_date,
            "new_rate": new_rate,
            "reason": rate_data.get("reason", "Manual update"),
            "updated_at": datetime.now(UTC).isoformat(),
            "provider": provider,
            "ari_status": ari_status,
            "configuration_error": configuration_error,
            "pushed_to_channels": [],
        }
        await self._db.rate_updates.insert_one(rate_update)

        if not provider:
            return ServiceResult.success(
                {
                    "success": True,
                    "message": f"{room_type} icin fiyat yerel olarak kaydedildi. Kanal saglayici yapilandirilmamis; gercek OTA dagitimi yapilmadi.",
                    "data_available": False,
                    "queued": False,
                    "pushed": False,
                    "pushed_to": [],
                    "provider": None,
                    "configuration_error": configuration_error,
                    "channels_updated": 0,
                    "log_id": rate_update["id"],
                }
            )

        return ServiceResult.success(
            {
                "success": True,
                "message": f"{room_type} icin fiyat yerel olarak kaydedildi. Gercek OTA dagitimi icin Toplu Fiyat/Envanter (Rate Manager) ekranini kullanin.",
                "data_available": True,
                "queued": False,
                "pushed": False,
                "pushed_to": [],
                "provider": provider,
                "channels_updated": 0,
                "log_id": rate_update["id"],
            }
        )

    async def list_rate_plans(self, ctx: OperationContext, channel=None, company_id=None, stay_date=None) -> ServiceResult:
        query: dict[str, Any] = {"tenant_id": ctx.tenant_id, "is_active": True}
        if channel:
            query["$or"] = [{"channel_restrictions": {"$size": 0}}, {"channel_restrictions": channel.value if hasattr(channel, "value") else channel}]
        if company_id:
            query["company_ids"] = company_id
        plans = await self._db.rate_plans.find(query, {"_id": 0}).to_list(100)
        return ServiceResult.success(plans)

    async def create_rate_plan(self, ctx: OperationContext, data: dict) -> ServiceResult:
        plan = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            **data,
            "is_active": True,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await self._db.rate_plans.insert_one(plan)
        plan.pop("_id", None)
        return ServiceResult.success(plan)

    async def get_demand_forecast(self, ctx: OperationContext, room_type: str, start_date: str, end_date: str) -> ServiceResult:
        forecasts = await self._db.demand_forecasts.find(
            {
                "tenant_id": ctx.tenant_id,
                "room_type": room_type,
                "date": {"$gte": start_date, "$lte": end_date},
            },
            {"_id": 0},
        ).to_list(365)
        return ServiceResult.success({"forecasts": forecasts, "count": len(forecasts)})

    async def get_competitor_rates(self, ctx: OperationContext, date_str: str | None = None, room_type: str | None = None) -> ServiceResult:
        query: dict[str, Any] = {"tenant_id": ctx.tenant_id}
        if date_str:
            query["date"] = date_str
        if room_type:
            query["room_type"] = room_type
        rates = await self._db.competitor_rates.find(query, {"_id": 0}).to_list(200)
        return ServiceResult.success({"competitor_rates": rates, "count": len(rates)})

    async def get_revenue_dashboard(self, ctx: OperationContext, period: str = "month") -> ServiceResult:
        today = datetime.now(UTC)
        if period == "week":
            start = today - timedelta(days=7)
        elif period == "year":
            start = today - timedelta(days=365)
        else:
            start = today - timedelta(days=30)

        bookings = await self._db.bookings.find(
            {
                "tenant_id": ctx.tenant_id,
                "created_at": {"$gte": start.isoformat()},
            },
            {"_id": 0},
        ).to_list(10000)

        total_revenue = sum(b.get("total_amount", 0) for b in bookings)
        total_rooms_sold = len([b for b in bookings if b.get("status") in ("checked_in", "checked_out")])
        total_rooms = await self._db.rooms.count_documents({"tenant_id": ctx.tenant_id})
        occupied_rooms = await self._db.rooms.count_documents({"tenant_id": ctx.tenant_id, "status": "occupied"})
        occupancy_rate = round(occupied_rooms / total_rooms * 100, 1) if total_rooms > 0 else 0

        return ServiceResult.success(
            {
                "period": period,
                "total_revenue": round(total_revenue, 2),
                "total_bookings": len(bookings),
                "total_rooms_sold": total_rooms_sold,
                "adr": round(total_revenue / total_rooms_sold, 2) if total_rooms_sold > 0 else 0,
                "rev_par": round(total_revenue / total_rooms, 2) if total_rooms > 0 else 0,
                "occupancy_rate": occupancy_rate,
            }
        )

    async def set_rate_override(self, ctx: OperationContext, data: dict) -> ServiceResult:
        override = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            **data,
            "created_by": ctx.actor_id,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "pending" if data.get("requires_approval") else "active",
        }
        await self._db.rate_overrides.insert_one(override)
        return ServiceResult.success(override)

    async def get_dynamic_pricing_suggestion(self, ctx: OperationContext, room_type: str, target_date: str) -> ServiceResult:
        base_plan = await self._db.rate_plans.find_one({"tenant_id": ctx.tenant_id, "room_type": room_type, "is_active": True}, {"_id": 0})
        base_rate = base_plan.get("base_price", 100) if base_plan else 100
        bookings_on_date = await self._db.bookings.count_documents(
            {
                "tenant_id": ctx.tenant_id,
                "check_in": {"$lte": target_date},
                "check_out": {"$gte": target_date},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
            }
        )
        total_rooms = await self._db.rooms.count_documents({"tenant_id": ctx.tenant_id, "room_type": room_type})
        occupancy = bookings_on_date / total_rooms if total_rooms > 0 else 0
        occ_pct = round(occupancy * 100, 1)
        multiplier = 1.0
        if occupancy > 0.9:
            multiplier = 1.3
            applied_rule = f"Doluluk %{occ_pct} > %90 -> +%30"
        elif occupancy > 0.7:
            multiplier = 1.15
            applied_rule = f"Doluluk %{occ_pct} > %70 -> +%15"
        elif occupancy < 0.3:
            multiplier = 0.85
            applied_rule = f"Doluluk %{occ_pct} < %30 -> -%15"
        else:
            applied_rule = f"Doluluk %{occ_pct} -> degisiklik yok"
        suggested_rate = round(base_rate * multiplier, 2)
        return ServiceResult.success(
            {
                "room_type": room_type,
                "target_date": target_date,
                "base_rate": base_rate,
                "occupancy": occ_pct,
                "multiplier": multiplier,
                "suggested_rate": suggested_rate,
                "pricing_method": "rule_based_deterministic",
                "applied_rule": applied_rule,
            }
        )


pricing_service = PricingService()
