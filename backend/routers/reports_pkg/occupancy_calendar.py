"""Read-only, tenant-scoped occupancy calendar and same-data Excel export."""
import asyncio
import hashlib
import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from core.business_date_service import ensure_business_date_initialized
from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.occupancy_calendar import occupancy_calendar
from modules.pms_core.stay_night_metrics import room_block_overlap_match, stay_overlap_match

sub_router = APIRouter()


def date_range(start_date, end_date):
    try:
        first, last = date.fromisoformat(start_date), date.fromisoformat(end_date)
        if first.isoformat() != start_date or last.isoformat() != end_date or not 0 <= (last - first).days <= 365 or last.year == 9999:
            raise ValueError
        return first, last
    except (ValueError, TypeError):
        raise HTTPException(422, "Başlangıç/bitiş tarihlerini YYYY-MM-DD biçiminde, en fazla 366 gün olacak şekilde seçin.") from None


@sub_router.get("/reports/occupancy-calendar")
async def get_occupancy_calendar(start_date: str, end_date: str, room_type: str | None = None,
                                 output: Literal["json", "xlsx"] = "json", snapshot: str | None = None,
                                 view: Literal["matrix", "daily"] = "matrix",
                                 metric: Literal["occupancy", "remaining", "occupied"] = "occupancy",
                                 current_user: User = Depends(get_current_user),
                                 _: None = Depends(require_module("basic_reporting"))):
    first, last = date_range(start_date, end_date)
    tid = current_user.tenant_id
    rooms, bookings, blocks = await asyncio.gather(
        db.rooms.find({"tenant_id": tid}, {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "is_active": 1}).to_list(None),
        db.bookings.find({"tenant_id": tid, **stay_overlap_match(first, last)},
                         {"_id": 0, "id": 1, "room_id": 1, "room_number": 1, "room_type": 1,
                          "status": 1, "check_in": 1, "check_out": 1, "checked_in_at": 1, "checked_out_at": 1}).to_list(None),
        db.room_blocks.find({"tenant_id": tid, **room_block_overlap_match(first, last)},
                            {"_id": 0, "room_id": 1, "start_date": 1, "end_date": 1, "allow_sell": 1, "status": 1}).to_list(None),
    )
    business_day = date.fromisoformat((await ensure_business_date_initialized(db, tid))["business_date"])
    data = occupancy_calendar(rooms, bookings, blocks, first, last, business_day, room_type)
    if room_type and room_type not in data["room_types"]:
        raise HTTPException(422, "Geçerli bir oda tipi seçin.")
    data["snapshot"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    if output == "json":
        return data
    if snapshot != data["snapshot"]:
        raise HTTPException(409, "Doluluk verisi değişti. Ekranı yenileyip Excel çıktısını yeniden alın.")
    from modules.pms_core.occupancy_calendar_export import occupancy_workbook

    buffer = occupancy_workbook(data, view=view, metric=metric)
    return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="occupancy_{start_date}_{end_date}.xlsx"'})
