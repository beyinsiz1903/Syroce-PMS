"""
PMS / İnsan-Concierge Görev Takibi
==================================
Resepsiyon/concierge ekibinin insan-eliyle yürüttüğü görevlerin (bagaj, transfer
ayarlama, çiçek, hatırlatma, restoran rezervasyonu, uyandırma, amenity teslimi)
atama ve takibi. AI/dijital concierge'den (ai.router.concierge_social) ayrıdır.

Tasarım (laundry/transfer desenleriyle hizalı):
  1. Tüm uçlar tenant-scoped; mutasyonlar RBAC kapılı. PII/secret loglanmaz.
  2. Durum akışı defansif geçiş guard'ı ile korunur; geçersiz geçiş 409.
  3. Atama ve terminal geçişler atomik CAS ile yapılır (yarış → tek kazanan).
  4. Folio etkisi yoktur (saf hizmet takibi).
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger("domains.pms.concierge")

router = APIRouter(prefix="/api/concierge", tags=["PMS / Concierge"])

# Görev girebilen/atayabilen/durum güncelleyebilen roller.
_TASK_ROLES = {
    "super_admin",
    "admin",
    "supervisor",
    "front_desk",
    "concierge",
    "staff",
}

# Geçerli görev tipleri (sunucu otoritedir).
_TASK_TYPES = {
    "luggage",
    "transfer_arrangement",
    "flowers",
    "reminder",
    "restaurant_reservation",
    "wakeup_call",
    "amenity_delivery",
    "general",
}

_PRIORITIES = {"low", "normal", "high", "urgent"}

# Durum akışı (defansif workflow guard).
_TRANSITIONS: dict[str, set[str]] = {
    "open": {"assigned", "in_progress", "completed", "cancelled"},
    "assigned": {"in_progress", "completed", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _tenant_of(user: User) -> str:
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=400, detail="Tenant bulunamadı")
    return tid


def _role_of(user: User) -> str:
    role = getattr(user, "role", None)
    return getattr(role, "value", role) or ""


def _require_role(user: User, allowed: set[str]) -> None:
    if getattr(user, "is_super_admin", False):
        return
    if _role_of(user) not in allowed:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")


def _actor_id(user: User) -> str:
    return getattr(user, "id", None) or getattr(user, "user_id", None) or "system"


def _serialize(doc: dict | None) -> dict | None:
    if not doc:
        return doc
    d = dict(doc)
    d.pop("_id", None)
    return d


# ─────────────────────────────────────────────────────────────────────
# Şemalar
# ─────────────────────────────────────────────────────────────────────
class TaskIn(BaseModel):
    task_type: str = Field("general", max_length=40)
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    room_number: str | None = Field(None, max_length=40)
    guest_name: str | None = Field(None, max_length=200)
    booking_id: str | None = Field(None, max_length=64)
    priority: str = Field("normal", max_length=20)
    assigned_to: str | None = Field(None, max_length=64)
    assigned_to_name: str | None = Field(None, max_length=200)
    due_at: str | None = Field(None, max_length=40)


class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    priority: str | None = Field(None, max_length=20)
    due_at: str | None = Field(None, max_length=40)
    notes: str | None = Field(None, max_length=1000)


class AssignIn(BaseModel):
    assigned_to: str = Field(..., min_length=1, max_length=64)
    assigned_to_name: str | None = Field(None, max_length=200)


class StatusUpdate(BaseModel):
    status: str = Field(..., min_length=1, max_length=30)
    resolution_note: str | None = Field(None, max_length=1000)


# ─────────────────────────────────────────────────────────────────────
# Listeleme / istatistik
# ─────────────────────────────────────────────────────────────────────
@router.get("/tasks")
async def list_tasks(
    status: str | None = Query(None),
    task_type: str | None = Query(None),
    assigned_to: str | None = Query(None),
    room_number: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if status and status != "all":
        q["status"] = status
    if task_type and task_type != "all":
        q["task_type"] = task_type
    if assigned_to:
        q["assigned_to"] = assigned_to
    if room_number:
        q["room_number"] = str(room_number).strip()
    rows = await db.concierge_tasks.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"tasks": rows}


@router.get("/tasks/stats")
async def task_stats(current_user: User = Depends(get_current_user)):
    tenant_id = _tenant_of(current_user)
    pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    rows = await db.concierge_tasks.aggregate(pipeline).to_list(50)
    by_status = {r["_id"]: r["count"] for r in rows if r.get("_id")}
    open_like = by_status.get("open", 0) + by_status.get("assigned", 0) + by_status.get("in_progress", 0)
    return {
        "by_status": by_status,
        "open_total": open_like,
        "completed": by_status.get("completed", 0),
        "cancelled": by_status.get("cancelled", 0),
    }


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, current_user: User = Depends(get_current_user)):
    tenant_id = _tenant_of(current_user)
    doc = await db.concierge_tasks.find_one({"id": task_id, "tenant_id": tenant_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Görev bulunamadı")
    return {"task": doc}


# ─────────────────────────────────────────────────────────────────────
# Oluşturma / güncelleme
# ─────────────────────────────────────────────────────────────────────
@router.post("/tasks")
async def create_task(
    payload: TaskIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _TASK_ROLES)
    tenant_id = _tenant_of(current_user)
    actor = _actor_id(current_user)

    task_type = payload.task_type if payload.task_type in _TASK_TYPES else "general"
    priority = payload.priority if payload.priority in _PRIORITIES else "normal"

    assigned_to = (payload.assigned_to or "").strip() or None
    status = "assigned" if assigned_to else "open"

    now = _now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "task_type": task_type,
        "title": payload.title.strip(),
        "description": (payload.description or "").strip() or None,
        "room_number": (payload.room_number or "").strip() or None,
        "guest_name": (payload.guest_name or "").strip() or None,
        "booking_id": payload.booking_id or None,
        "priority": priority,
        "status": status,
        "assigned_to": assigned_to,
        "assigned_to_name": (payload.assigned_to_name or "").strip() or None,
        "assigned_at": now if assigned_to else None,
        "due_at": (payload.due_at or "").strip() or None,
        "notes": None,
        "resolution_note": None,
        "completed_at": None,
        "created_at": now,
        "updated_at": now,
        "created_by": actor,
    }
    await db.concierge_tasks.insert_one(dict(doc))
    return {"task": _serialize(doc)}


@router.put("/tasks/{task_id}")
async def update_task(
    task_id: str,
    payload: TaskUpdate,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _TASK_ROLES)
    tenant_id = _tenant_of(current_user)

    task = await db.concierge_tasks.find_one({"id": task_id, "tenant_id": tenant_id})
    if not task:
        raise HTTPException(status_code=404, detail="Görev bulunamadı")
    if task.get("status") in ("completed", "cancelled"):
        raise HTTPException(status_code=409, detail="Tamamlanmış/iptal görev düzenlenemez")

    updates = dict(payload.model_dump(exclude_unset=True))
    if "title" in updates and updates["title"]:
        updates["title"] = updates["title"].strip()
    if "priority" in updates and updates["priority"] not in _PRIORITIES:
        raise HTTPException(status_code=400, detail="Geçersiz öncelik")
    if not updates:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")
    updates["updated_at"] = _now_iso()
    await db.concierge_tasks.update_one({"id": task_id, "tenant_id": tenant_id}, {"$set": updates})
    doc = await db.concierge_tasks.find_one({"id": task_id, "tenant_id": tenant_id}, {"_id": 0})
    return {"task": doc}


@router.post("/tasks/{task_id}/assign")
async def assign_task(
    task_id: str,
    payload: AssignIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _TASK_ROLES)
    tenant_id = _tenant_of(current_user)

    task = await db.concierge_tasks.find_one({"id": task_id, "tenant_id": tenant_id})
    if not task:
        raise HTTPException(status_code=404, detail="Görev bulunamadı")
    if task.get("status") in ("completed", "cancelled"):
        raise HTTPException(status_code=409, detail="Tamamlanmış/iptal görev atanamaz")

    now = _now_iso()
    new_status = "assigned" if task.get("status") == "open" else task.get("status")
    await db.concierge_tasks.update_one(
        {"id": task_id, "tenant_id": tenant_id},
        {
            "$set": {
                "assigned_to": payload.assigned_to.strip(),
                "assigned_to_name": (payload.assigned_to_name or "").strip() or None,
                "assigned_at": now,
                "status": new_status,
                "updated_at": now,
            }
        },
    )
    doc = await db.concierge_tasks.find_one({"id": task_id, "tenant_id": tenant_id}, {"_id": 0})
    return {"task": doc}


@router.patch("/tasks/{task_id}")
async def update_task_status(
    task_id: str,
    payload: StatusUpdate,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _TASK_ROLES)
    tenant_id = _tenant_of(current_user)

    new_status = payload.status.strip()
    if new_status not in _TRANSITIONS:
        raise HTTPException(status_code=400, detail="Geçersiz durum")

    task = await db.concierge_tasks.find_one({"id": task_id, "tenant_id": tenant_id})
    if not task:
        raise HTTPException(status_code=404, detail="Görev bulunamadı")

    cur_status = task.get("status", "open")
    if new_status == cur_status:
        return {"ok": True, "status": cur_status}
    if new_status not in _TRANSITIONS.get(cur_status, set()):
        raise HTTPException(status_code=409, detail=f"Geçersiz geçiş: {cur_status} → {new_status}")

    now = _now_iso()
    update_set: dict = {"status": new_status, "updated_at": now}
    if payload.resolution_note:
        update_set["resolution_note"] = payload.resolution_note.strip()
    if new_status == "completed":
        update_set["completed_at"] = now

    # Atomik CAS: yalnız mevcut durumu hâlâ cur_status olan tek istek kazanır.
    res = await db.concierge_tasks.update_one(
        {"id": task_id, "tenant_id": tenant_id, "status": cur_status},
        {"$set": update_set},
    )
    if res.modified_count == 0:
        latest = await db.concierge_tasks.find_one({"id": task_id, "tenant_id": tenant_id}, {"_id": 0})
        return {"ok": True, "status": (latest or {}).get("status")}
    return {"ok": True, "status": new_status}


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, {"super_admin", "admin", "supervisor"})
    tenant_id = _tenant_of(current_user)
    res = await db.concierge_tasks.delete_one({"id": task_id, "tenant_id": tenant_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Görev bulunamadı")
    return {"ok": True, "id": task_id}
