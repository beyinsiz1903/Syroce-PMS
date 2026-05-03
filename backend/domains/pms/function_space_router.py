"""Function Space — Toplantı/balo salonu saatlik takvim, kurulum tipi, kapasite.
Opera Cloud Function Space modülünün karşılığı. Banquet/MICE event'leri için.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User

router = APIRouter(prefix="/api/function-space", tags=["Function Space"])

SETUP_TYPES = (
    "theatre", "classroom", "boardroom", "u_shape", "banquet",
    "cocktail", "hollow_square", "cabaret", "custom",
)


class FunctionRoom(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1)
    capacity: int = Field(..., ge=1)  # banket maks koltuk
    area_m2: float | None = None
    floor: str | None = None
    hourly_rate: float = 0
    daily_rate: float = 0
    supported_setups: list[str] = Field(default_factory=list)
    active: bool = True


class FunctionBookingCreate(BaseModel):
    room_id: str
    event_name: str = Field(..., min_length=1)
    organizer: str | None = None  # şirket / grup adı
    group_id: str | None = None
    starts_at: str  # ISO
    ends_at: str
    setup_type: str = Field("theatre")
    attendees: int = Field(1, ge=1)
    note: str | None = None


class FunctionBooking(FunctionBookingCreate):
    id: str
    tenant_id: str
    status: str = "booked"
    created_by: str
    created_at: str


# ---------- Rooms ----------

@router.get("/rooms", response_model=list[FunctionRoom])
async def list_rooms(user: User = Depends(get_current_user)):
    db = get_system_db()
    cur = db.function_rooms.find({"tenant_id": user.tenant_id, "active": True}).sort("name", 1)
    out: list[dict[str, Any]] = []
    async for r in cur:
        r.pop("_id", None)
        out.append(r)
    return out


@router.post("/rooms", response_model=FunctionRoom, status_code=201)
async def create_room(payload: FunctionRoom, user: User = Depends(get_current_user)):
    db = get_system_db()
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["tenant_id"] = user.tenant_id
    doc["created_at"] = datetime.now(UTC).isoformat()
    doc["created_by"] = user.email
    await db.function_rooms.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/rooms/{room_id}", status_code=204)
async def delete_room(room_id: str, user: User = Depends(get_current_user)):
    db = get_system_db()
    res = await db.function_rooms.update_one(
        {"id": room_id, "tenant_id": user.tenant_id},
        {"$set": {"active": False}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Salon bulunamadı")


# ---------- Bookings ----------

async def _has_clash(db, tenant_id: str, room_id: str, starts: str, ends: str, exclude_id: str | None = None) -> bool:
    """Aynı salon için verilen aralıkla çakışan onaylı booking var mı?"""
    q = {
        "tenant_id": tenant_id,
        "room_id": room_id,
        "status": {"$ne": "cancelled"},
        # Çakışma: existing.starts < new.ends AND existing.ends > new.starts
        "starts_at": {"$lt": ends},
        "ends_at": {"$gt": starts},
    }
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    return (await db.function_bookings.find_one(q)) is not None


@router.get("/bookings", response_model=list[FunctionBooking])
async def list_bookings(
    date: str | None = None,
    room_id: str | None = None,
    user: User = Depends(get_current_user),
):
    """Tarih (YYYY-MM-DD) veya salon filtreli booking listesi.
    Tarih verilirse o güne dokunan tüm booking'ler döner (gece taşan dahil)."""
    db = get_system_db()
    q: dict[str, Any] = {"tenant_id": user.tenant_id}
    if room_id:
        q["room_id"] = room_id
    if date:
        # O günün başlangıcı..bitişi ile çakışan booking'ler
        day_start = f"{date}T00:00"
        day_end = f"{date}T23:59"
        q["starts_at"] = {"$lte": day_end}
        q["ends_at"] = {"$gte": day_start}
    cur = db.function_bookings.find(q).sort("starts_at", 1)
    out: list[dict[str, Any]] = []
    async for b in cur:
        b.pop("_id", None)
        out.append(b)
    return out


@router.post("/bookings", response_model=FunctionBooking, status_code=201)
async def create_booking(payload: FunctionBookingCreate, user: User = Depends(get_current_user)):
    db = get_system_db()
    if payload.setup_type not in SETUP_TYPES:
        raise HTTPException(400, f"Geçersiz kurulum tipi. Seçenekler: {', '.join(SETUP_TYPES)}")
    if payload.starts_at >= payload.ends_at:
        raise HTTPException(400, "Bitiş başlangıçtan sonra olmalı")

    room = await db.function_rooms.find_one({"id": payload.room_id, "tenant_id": user.tenant_id})
    if not room:
        raise HTTPException(404, "Salon bulunamadı")
    if not room.get("active", True):
        raise HTTPException(400, "Salon pasif durumda; rezervasyon açılamaz")
    if payload.attendees > (room.get("capacity") or 0):
        raise HTTPException(400, f"Katılımcı sayısı salon kapasitesini ({room.get('capacity')}) aşıyor")
    if room.get("supported_setups") and payload.setup_type not in room["supported_setups"]:
        raise HTTPException(400, f"Bu salon '{payload.setup_type}' kurulumunu desteklemiyor")

    if await _has_clash(db, user.tenant_id, payload.room_id, payload.starts_at, payload.ends_at):
        raise HTTPException(409, "Bu salon seçilen saatlerde dolu (çakışma)")

    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["tenant_id"] = user.tenant_id
    doc["status"] = "booked"
    doc["created_by"] = user.email
    doc["created_at"] = datetime.now(UTC).isoformat()
    await db.function_bookings.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(booking_id: str, user: User = Depends(get_current_user)):
    db = get_system_db()
    res = await db.function_bookings.update_one(
        {"id": booking_id, "tenant_id": user.tenant_id},
        {"$set": {"status": "cancelled", "cancelled_at": datetime.now(UTC).isoformat(), "cancelled_by": user.email}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Booking bulunamadı")
    return {"ok": True}


@router.get("/availability")
async def availability(
    date: str,
    setup_type: str | None = None,
    min_capacity: int = 1,
    user: User = Depends(get_current_user),
):
    """Belirli gün için boş salonları listele (kapasite + setup filtreli)."""
    db = get_system_db()
    rq: dict[str, Any] = {
        "tenant_id": user.tenant_id,
        "active": True,
        "capacity": {"$gte": min_capacity},
    }
    rooms = []
    async for r in db.function_rooms.find(rq):
        r.pop("_id", None)
        if setup_type and r.get("supported_setups") and setup_type not in r["supported_setups"]:
            continue
        rooms.append(r)

    day_start = f"{date}T00:00"
    day_end = f"{date}T23:59"
    busy_cur = db.function_bookings.find({
        "tenant_id": user.tenant_id,
        "status": {"$ne": "cancelled"},
        "starts_at": {"$lte": day_end},
        "ends_at": {"$gte": day_start},
    })
    busy: dict[str, list[dict[str, str]]] = {}
    async for b in busy_cur:
        busy.setdefault(b["room_id"], []).append({
            "starts_at": b["starts_at"],
            "ends_at": b["ends_at"],
            "event_name": b.get("event_name"),
        })
    return {
        "date": date,
        "rooms": [
            {
                "id": r["id"],
                "name": r["name"],
                "capacity": r["capacity"],
                "supported_setups": r.get("supported_setups", []),
                "busy_intervals": busy.get(r["id"], []),
            }
            for r in rooms
        ],
    }
