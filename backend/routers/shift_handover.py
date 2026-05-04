"""
Shift Handover Router — Vardiya devir notları.
Resepsiyon vardiya değişimlerinde önemli notların taşınması için.
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/pms/shift-handover", tags=["pms"])

_COL = "shift_handovers"
SHIFTS = ("morning", "afternoon", "night")
PRIORITIES = ("low", "normal", "high")


class HandoverCreate(BaseModel):
    business_date: str = Field(..., description="YYYY-MM-DD")
    shift: str = Field(..., description="morning|afternoon|night")
    note: str = Field(..., min_length=1, max_length=4000)
    priority: str = "normal"
    to_shift: Optional[str] = None
    related_room: Optional[str] = None
    related_booking_id: Optional[str] = None


class HandoverAck(BaseModel):
    note: Optional[str] = None


def _serialize(d: dict) -> dict:
    if not d:
        return d
    d.pop("_id", None)
    return d


@router.post("")
async def create_handover(payload: HandoverCreate, current_user: User = Depends(get_current_user)):
    if payload.shift not in SHIFTS:
        raise HTTPException(400, f"shift {SHIFTS} olmalı")
    if payload.priority not in PRIORITIES:
        raise HTTPException(400, f"priority {PRIORITIES} olmalı")
    doc = {
        "id": str(uuid4()),
        "tenant_id": current_user.tenant_id,
        "business_date": payload.business_date,
        "shift": payload.shift,
        "to_shift": payload.to_shift,
        "note": payload.note,
        "priority": payload.priority,
        "related_room": payload.related_room,
        "related_booking_id": payload.related_booking_id,
        "from_user_id": current_user.id,
        "from_user_name": current_user.name or current_user.email,
        "acknowledged": False,
        "acknowledged_by_id": None,
        "acknowledged_by_name": None,
        "acknowledged_at": None,
        "ack_note": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[_COL].insert_one(doc)
    return _serialize(doc)


@router.get("")
async def list_handovers(
    business_date: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="open|acknowledged|all"),
    shift: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    q: dict = {"tenant_id": current_user.tenant_id}
    if business_date:
        q["business_date"] = business_date
    if shift:
        q["shift"] = shift
    if status == "open":
        q["acknowledged"] = False
    elif status == "acknowledged":
        q["acknowledged"] = True
    cursor = db[_COL].find(q).sort("created_at", -1).limit(limit)
    items = [_serialize(d) async for d in cursor]
    return {"items": items, "total": len(items)}


@router.get("/open-count")
async def open_count(current_user: User = Depends(get_current_user)):
    n = await db[_COL].count_documents({
        "tenant_id": current_user.tenant_id,
        "acknowledged": False,
    })
    return {"open": n}


@router.patch("/{handover_id}/acknowledge")
async def acknowledge(handover_id: str, payload: HandoverAck, current_user: User = Depends(get_current_user)):
    res = await db[_COL].find_one_and_update(
        {"id": handover_id, "tenant_id": current_user.tenant_id},
        {"$set": {
            "acknowledged": True,
            "acknowledged_by_id": current_user.id,
            "acknowledged_by_name": current_user.name or current_user.email,
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            "ack_note": payload.note,
        }},
        return_document=True,
    )
    if not res:
        raise HTTPException(404, "Devir notu bulunamadı")
    return _serialize(res)


@router.delete("/{handover_id}")
async def delete_handover(handover_id: str, current_user: User = Depends(get_current_user)):
    res = await db[_COL].delete_one({"id": handover_id, "tenant_id": current_user.tenant_id})
    if not res.deleted_count:
        raise HTTPException(404, "Devir notu bulunamadı")
    return {"ok": True}
