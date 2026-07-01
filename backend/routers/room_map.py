"""
Oda Haritasi: bir tarih icin oda durumlarini ve booking eslemelerini ver,
suruk-birak ile oda degistir.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/pms/room-map", tags=["pms"])


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


@router.get("")
async def get_map(
    business_date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("view_room_status")),
):
    tenant_id = current_user.tenant_id
    bd = business_date or _today()
    next_day = (datetime.fromisoformat(bd) + timedelta(days=1)).strftime("%Y-%m-%d")

    rooms = (
        await db.rooms.find(
            {"tenant_id": tenant_id, "is_active": {"$ne": False}},
            {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "floor": 1, "status": 1, "max_occupancy": 1},
        )
        .sort("room_number", 1)
        .to_list(500)
    )

    bookings_cursor = db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "in_house"]},
            "check_in": {"$lt": next_day},
            "check_out": {"$gt": bd},
        },
        {"_id": 0, "id": 1, "room_id": 1, "guest_id": 1, "check_in": 1, "check_out": 1, "status": 1, "adults": 1, "children": 1, "nights": 1},
    )
    bookings = await bookings_cursor.to_list(1000)

    guest_ids = list({b.get("guest_id") for b in bookings if b.get("guest_id")})
    guests_map = {}
    if guest_ids:
        async for g in db.guests.find(
            {"tenant_id": tenant_id, "id": {"$in": guest_ids}},
            {"_id": 0, "id": 1, "name": 1, "vip_status": 1},
        ):
            guests_map[g["id"]] = g

    by_room: dict[str, dict] = {}
    unassigned: list[dict] = []
    for b in bookings:
        g = guests_map.get(b.get("guest_id"), {})
        item = {
            "booking_id": b["id"],
            "guest_name": g.get("name") or "(misafir)",
            "vip": bool(g.get("vip_status")),
            "check_in": b.get("check_in"),
            "check_out": b.get("check_out"),
            "status": b.get("status"),
            "adults": b.get("adults") or 1,
            "children": b.get("children") or 0,
            "nights": b.get("nights"),
        }
        if b.get("room_id"):
            by_room[b["room_id"]] = item
        else:
            unassigned.append(item)

    rooms_out = []
    for r in rooms:
        rooms_out.append({**r, "booking": by_room.get(r["id"])})

    return {"business_date": bd, "rooms": rooms_out, "unassigned": unassigned}


class AssignRequest(BaseModel):
    booking_id: str
    room_id: str
    business_date: str | None = None


@router.post("/assign")
async def assign(
    payload: AssignRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
    _perm=Depends(require_op("update_booking")),
):
    tenant_id = current_user.tenant_id
    bd = payload.business_date or _today()
    next_day = (datetime.fromisoformat(bd) + timedelta(days=1)).strftime("%Y-%m-%d")

    booking = await db.bookings.find_one({"id": payload.booking_id, "tenant_id": tenant_id}, {"_id": 0})
    if not booking:
        raise HTTPException(404, "Rezervasyon bulunamadi")
    new_room = await db.rooms.find_one({"id": payload.room_id, "tenant_id": tenant_id}, {"_id": 0})
    if not new_room:
        raise HTTPException(404, "Oda bulunamadi")

    # Cakisma kontrolu
    ci = booking.get("check_in") or bd
    co = booking.get("check_out") or next_day
    overlap = await db.bookings.find_one(
        {
            "tenant_id": tenant_id,
            "room_id": payload.room_id,
            "id": {"$ne": payload.booking_id},
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "in_house"]},
            "check_in": {"$lt": co},
            "check_out": {"$gt": ci},
        }
    )
    if overlap:
        raise HTTPException(409, f"Oda {new_room.get('room_number')} bu tarihlerde dolu")

    old_room_id = booking.get("room_id")
    now = datetime.now(UTC).isoformat()
    # Conditional update: yalniz hala eski room_id ile durduysa degistir (yaris kosulu darbogazi)
    res = await db.bookings.update_one(
        {"id": payload.booking_id, "tenant_id": tenant_id, "room_id": old_room_id},
        {"$set": {"room_id": payload.room_id, "room_number": new_room.get("room_number"), "updated_at": now}},
    )
    if res.matched_count == 0:
        raise HTTPException(409, "Rezervasyon bu sirada degistirilmis, lutfen yenileyin")
    await db.room_move_history.insert_one(
        {
            "tenant_id": tenant_id,
            "booking_id": payload.booking_id,
            "from_room_id": old_room_id,
            "to_room_id": payload.room_id,
            "to_room_number": new_room.get("room_number"),
            "moved_by_id": current_user.id,
            "moved_by_name": current_user.name or current_user.email,
            "moved_at": now,
            "reason": "room_map_drag_drop",
        }
    )
    return {"ok": True, "booking_id": payload.booking_id, "room_id": payload.room_id, "room_number": new_room.get("room_number")}
