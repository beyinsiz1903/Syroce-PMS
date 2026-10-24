"""Read-only operational forecast and snapshot-bound export."""
import asyncio
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from core.business_date_service import ensure_business_date_initialized
from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from core.tenant_currency import get_tenant_currency
from models.schemas import User, _ensure_hotel_context
from modules.pms_core.frontdesk_forecast import frontdesk_forecast
from modules.pms_core.frontdesk_forecast_export import forecast_columns, forecast_workbook
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import room_block_overlap_match, stay_overlap_match
from routers.reports_pkg.occupancy_calendar import date_range

sub_router = APIRouter()


@sub_router.get("/reports/frontdesk-forecast")
async def get_frontdesk_forecast(start_date: str, end_date: str, room_type: str | None = None,
        output: Literal["json", "xlsx"] = "json", snapshot: str | None = None,
        view: Literal["availability", "movements", "occupancy", "revenue", "stay_types"] = "availability",
        basis: Literal["physical", "sellable"] = "physical",
        current_user: User = Depends(get_current_user), _module=Depends(require_module("basic_reporting")),
        _perm=Depends(require_op("view_reports"))):
    _ensure_hotel_context(current_user)
    first, last = date_range(start_date, end_date)
    tid = current_user.tenant_id
    previous = max(first, date.min + timedelta(days=1)) - timedelta(days=1)
    after = last + timedelta(days=1)
    overlaps = stay_overlap_match(previous, last)
    legacy_overlaps = {"$or": [{"check_in_date" if key == "check_in" else "check_out_date": value for key, value in clause.items()} for clause in overlaps["$or"]]}
    rooms, bookings, closed, groups, rates, allotments = await asyncio.gather(
        db.rooms.find({"tenant_id": tid}, {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "is_active": 1}).to_list(None),
        db.bookings.find({"tenant_id": tid, "$or": [overlaps, legacy_overlaps]}, {"_id": 0, "id": 1, "room_id": 1,
            "room_number": 1, "room_type": 1, "status": 1, "check_in": 1, "check_out": 1, "checked_in_at": 1, "checked_out_at": 1,
            "adults": 1, "children": 1, "children_ages": 1, "is_complimentary": 1, "booking_type": 1, "is_house_use": 1,
            "group_block_id": 1, "group_booking_id": 1, "group_id": 1, "block_id": 1, "check_in_date": 1, "check_out_date": 1, "total_amount": 1, "currency": 1}).to_list(None),
        db.room_blocks.find({"tenant_id": tid, **room_block_overlap_match(first, last)}, {"_id": 0, "room_id": 1,
            "start_date": 1, "end_date": 1, "status": 1, "allow_sell": 1}).to_list(None),
        db.group_blocks.find({"tenant_id": tid, **stay_overlap_match(first, last)}, {"id": 1, "check_in": 1, "check_out": 1,
            "room_type": 1, "room_breakdown": 1, "total_rooms": 1, "rooms_blocked": 1, "status": 1}).to_list(None),
        db.daily_rates.find({"tenant_id": tid, "$or": [{"date": {"$gte": first.isoformat(), "$lt": after.isoformat()}},
            {"date": {"$gte": datetime.combine(first, datetime.min.time(), UTC), "$lt": datetime.combine(after, datetime.min.time(), UTC)}}]},
            {"_id": 0, "booking_id": 1, "date": 1, "rate": 1, "currency": 1, "is_complimentary": 1}).to_list(None),
        db.block_reservations.find({"tenant_id": tid, **room_block_overlap_match(first, last)}, {"id": 1, "room_type": 1,
            "start_date": 1, "end_date": 1, "total_rooms": 1, "status": 1}).to_list(None),
    )
    groups.extend({**block, "id": f"block:{block.get('id') or block.get('_id')}" if block.get('id') or block.get('_id') else None,
        "check_in": block.get("start_date"), "check_out": block.get("end_date")} for block in allotments)
    business_day = date.fromisoformat((await ensure_business_date_initialized(db, tid))["business_date"])
    currency, _ = await get_tenant_currency(tid)
    data = frontdesk_forecast(rooms, bookings, closed, groups, rates, first, last, business_day, room_type=room_type, fallback_currency=currency)
    if room_type and room_type not in data["room_types"]:
        raise HTTPException(422, "Geçerli bir oda tipi seçin.")
    data["columns"] = forecast_columns()
    data["snapshot"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    if output == "json":
        return data
    if snapshot != data["snapshot"]:
        raise HTTPException(409, "Forecast verisi değişti; raporu yenileyip çıktıyı tekrar alın.")
    return StreamingResponse(forecast_workbook(data, view, basis), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="forecast_{start_date}_{end_date}.xlsx"'})
