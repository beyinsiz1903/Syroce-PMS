"""
Revenue / RMS — Service Layer
Orchestrates group bookings, corporate contracts, OTA promotions,
inventory management, and yield analysis. No FastAPI dependencies.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import uuid
import logging

from common.context import OperationContext
from common.result import ServiceResult
from common.audit_hook import audited, SEVERITY_INFO, SEVERITY_WARNING

logger = logging.getLogger(__name__)


class RmsService:
    """Business logic for Revenue Management System operations."""

    def __init__(self):
        from core.database import db
        self._db = db

    @audited("rms.create_group_booking", "group_booking", severity=SEVERITY_INFO)
    async def create_group_booking(self, ctx: OperationContext, data: dict) -> ServiceResult:
        group = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            **data,
            "status": "tentative",
            "created_by": ctx.actor_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._db.group_bookings.insert_one(group)
        group.pop("_id", None)
        return ServiceResult.success(group)

    async def list_group_bookings(self, ctx: OperationContext, status: Optional[str] = None) -> ServiceResult:
        query: Dict[str, Any] = {"tenant_id": ctx.tenant_id}
        if status:
            query["status"] = status
        groups = await self._db.group_bookings.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
        return ServiceResult.success({"groups": groups, "count": len(groups)})

    @audited("rms.create_corporate_contract", "corporate_contract", severity=SEVERITY_INFO)
    async def create_corporate_contract(self, ctx: OperationContext, data: dict) -> ServiceResult:
        contract = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            **data,
            "status": "active",
            "created_by": ctx.actor_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._db.corporate_contracts.insert_one(contract)
        contract.pop("_id", None)
        return ServiceResult.success(contract)

    async def list_corporate_contracts(self, ctx: OperationContext, status: Optional[str] = None) -> ServiceResult:
        query: Dict[str, Any] = {"tenant_id": ctx.tenant_id}
        if status:
            query["status"] = status
        contracts = await self._db.corporate_contracts.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
        return ServiceResult.success({"contracts": contracts, "count": len(contracts)})

    @audited("rms.create_ota_promotion", "ota_promotion", severity=SEVERITY_INFO)
    async def create_ota_promotion(self, ctx: OperationContext, data: dict) -> ServiceResult:
        promo = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            **data,
            "status": "active",
            "created_by": ctx.actor_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._db.ota_promotions.insert_one(promo)
        promo.pop("_id", None)
        return ServiceResult.success(promo)

    async def list_ota_promotions(self, ctx: OperationContext, channel: Optional[str] = None) -> ServiceResult:
        query: Dict[str, Any] = {"tenant_id": ctx.tenant_id}
        if channel:
            query["channel"] = channel
        promos = await self._db.ota_promotions.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
        return ServiceResult.success({"promotions": promos, "count": len(promos)})

    async def create_inventory_item(self, ctx: OperationContext, data: dict) -> ServiceResult:
        item = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            **data,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._db.inventory.insert_one(item)
        item.pop("_id", None)
        return ServiceResult.success(item)

    @audited("rms.record_inventory_usage", "inventory", severity=SEVERITY_WARNING, capture_before=True)
    async def record_inventory_usage(self, ctx: OperationContext, data: dict) -> ServiceResult:
        item = await self._db.inventory.find_one({"id": data["item_id"], "tenant_id": ctx.tenant_id})
        if not item:
            return ServiceResult.fail("Inventory item not found", "NOT_FOUND")
        qty = data["quantity"]
        current = item.get("quantity", 0)
        if data["usage_type"] == "consume":
            new_qty = max(0, current - qty)
        else:
            new_qty = current + qty

        await self._db.inventory.update_one(
            {"id": data["item_id"]},
            {"$set": {"quantity": new_qty, "last_updated": datetime.now(timezone.utc).isoformat()}},
        )
        usage_record = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            **data,
            "previous_quantity": current,
            "new_quantity": new_qty,
            "recorded_by": ctx.actor_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self._db.inventory_usage.insert_one(usage_record)
        usage_record.pop("_id", None)
        return ServiceResult.success(usage_record)

    async def get_yield_analysis(self, ctx: OperationContext, start_date: Optional[str] = None, end_date: Optional[str] = None) -> ServiceResult:
        today = datetime.now(timezone.utc)
        if not start_date:
            start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end_date:
            end_date = today.strftime("%Y-%m-%d")

        bookings = await self._db.bookings.find({
            "tenant_id": ctx.tenant_id,
            "check_in": {"$gte": start_date, "$lte": end_date},
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
        }, {"_id": 0}).to_list(10000)

        total_rooms = await self._db.rooms.count_documents({"tenant_id": ctx.tenant_id})
        days = (datetime.fromisoformat(end_date) - datetime.fromisoformat(start_date)).days or 1
        total_room_nights = total_rooms * days
        sold_room_nights = len(bookings)
        total_revenue = sum(b.get("total_amount", 0) for b in bookings)

        return ServiceResult.success({
            "period": {"start": start_date, "end": end_date, "days": days},
            "total_room_nights": total_room_nights,
            "sold_room_nights": sold_room_nights,
            "occupancy_rate": round(sold_room_nights / total_room_nights * 100, 1) if total_room_nights > 0 else 0,
            "total_revenue": round(total_revenue, 2),
            "adr": round(total_revenue / sold_room_nights, 2) if sold_room_nights > 0 else 0,
            "rev_par": round(total_revenue / total_room_nights, 2) if total_room_nights > 0 else 0,
        })


rms_service = RmsService()
