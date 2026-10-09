"""
Shift Handover Router — Vardiya devir notları.
Resepsiyon vardiya değişimlerinde önemli notların taşınması için.
"""

from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.module_scope_service import require_module_scope

router = APIRouter(prefix="/api/pms/shift-handover", tags=["pms"], dependencies=[Depends(require_module_scope("frontdesk"))])

_COL = "shift_handovers"
SHIFTS = ("morning", "afternoon", "night")
PRIORITIES = ("low", "normal", "high")


class HandoverCreate(BaseModel):
    business_date: str = Field(..., description="YYYY-MM-DD")
    shift: str = Field(..., description="morning|afternoon|night")
    note: str = Field(..., min_length=1, max_length=4000)
    priority: str = "normal"
    to_shift: str | None = None
    related_room: str | None = None
    related_booking_id: str | None = None


class HandoverAck(BaseModel):
    note: str | None = None


class HandoverProgress(BaseModel):
    status: str
    resolution_note: str | None = Field(default=None, max_length=4000)


def handover_status(doc: dict) -> str:
    return doc.get("status") or ("acknowledged" if doc.get("acknowledged") else "open")


def _serialize(d: dict) -> dict:
    if not d:
        return d
    d.pop("_id", None)
    d["status"] = handover_status(d)
    return d


@router.post("")
async def create_handover(payload: HandoverCreate, current_user: User = Depends(get_current_user)):
    try:
        date.fromisoformat(payload.business_date)
    except ValueError as exc:
        raise HTTPException(400, "Geçerli bir iş günü seçin") from exc
    if not payload.note.strip():
        raise HTTPException(400, "Devir notu boş olamaz")
    if payload.to_shift and (payload.to_shift not in SHIFTS or payload.to_shift == payload.shift):
        raise HTTPException(400, "Devralan vardiya geçerli ve devreden vardiyadan farklı olmalı")
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
        "note": payload.note.strip(),
        "status": "open",
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
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db[_COL].insert_one(doc)
    return _serialize(doc)


@router.get("")
async def list_handovers(
    business_date: str | None = Query(None),
    status: str | None = Query(None, description="open|acknowledged|in_progress|resolved|unresolved|all"),
    shift: str | None = Query(None),
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
        q["status"] = {"$nin": ["in_progress", "resolved"]}
    elif status in {"in_progress", "resolved"}:
        q["status"] = status
    elif status == "unresolved":
        q["status"] = {"$ne": "resolved"}
    elif status not in {None, "all"}:
        raise HTTPException(400, "Geçersiz devir durumu")
    total = await db[_COL].count_documents(q)
    cursor = db[_COL].find(q).sort("created_at", -1).limit(limit)
    items = [_serialize(d) async for d in cursor]
    return {"items": items, "total": total, "has_more": total > len(items)}


@router.get("/open-count")
async def open_count(current_user: User = Depends(get_current_user)):
    n = await db[_COL].count_documents(
        {
            "tenant_id": current_user.tenant_id,
            "acknowledged": False,
        }
    )
    return {"open": n}


@router.patch("/{handover_id}/acknowledge")
async def acknowledge(handover_id: str, payload: HandoverAck, current_user: User = Depends(get_current_user)):
    res = await db[_COL].find_one_and_update(
        {"id": handover_id, "tenant_id": current_user.tenant_id, "acknowledged": False},
        {
            "$set": {
                "acknowledged": True,
                "status": "acknowledged",
                "acknowledged_by_id": current_user.id,
                "acknowledged_by_name": current_user.name or current_user.email,
                "acknowledged_at": datetime.now(UTC).isoformat(),
                "ack_note": payload.note,
            }
        },
        return_document=True,
    )
    if not res:
        res = await db[_COL].find_one({"id": handover_id, "tenant_id": current_user.tenant_id})
        if not res:
            raise HTTPException(404, "Devir notu bulunamadı")
    return _serialize(res)


@router.patch("/{handover_id}/progress")
async def progress(handover_id: str, payload: HandoverProgress, current_user: User = Depends(get_current_user)):
    if payload.status not in {"in_progress", "resolved"}:
        raise HTTPException(400, "Geçersiz devir durumu")
    if payload.status == "resolved" and len((payload.resolution_note or "").strip()) < 3:
        raise HTTPException(400, "Tamamlama sonucunu en az üç karakterle açıklayın")
    scope = {"id": handover_id, "tenant_id": current_user.tenant_id}
    doc = await db[_COL].find_one(scope)
    if not doc:
        raise HTTPException(404, "Devir notu bulunamadı")
    previous = handover_status(doc)
    if previous == payload.status:
        return _serialize(doc)
    allowed = {"acknowledged": {"in_progress", "resolved"}, "in_progress": {"resolved"}}
    if payload.status not in allowed.get(previous, set()):
        raise HTTPException(409, "Notu önce devralın; tamamlanan not yeniden işleme alınamaz")
    now = datetime.now(UTC).isoformat()
    changes = {"status": payload.status, "updated_at": now}
    if payload.status == "resolved":
        changes.update(resolution_note=payload.resolution_note.strip(), resolved_at=now,
                       resolved_by_id=current_user.id, resolved_by_name=current_user.name or current_user.email)
    else:
        changes.update(started_at=now, started_by_id=current_user.id,
                       started_by_name=current_user.name or current_user.email)
    # Compare the stored value (including legacy missing status), not only the
    # derived display status. Concurrent completion must not be overwritten.
    res = await db[_COL].find_one_and_update(
        {**scope, "status": doc.get("status"), "acknowledged": True},
        {"$set": changes}, return_document=True,
    )
    if not res:
        raise HTTPException(409, "Not başka bir kullanıcı tarafından güncellendi; listeyi yenileyin")
    return _serialize(res)


@router.delete("/{handover_id}")
async def delete_handover(handover_id: str, current_user: User = Depends(get_current_user)):
    res = await db[_COL].delete_one({"id": handover_id, "tenant_id": current_user.tenant_id})
    if not res.deleted_count:
        raise HTTPException(404, "Devir notu bulunamadı")
    return {"ok": True}
