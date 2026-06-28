"""
PMS / Turndown (Akşam Servisi) Otomatik Planlama
================================================
Dolu (checked_in) ve opsiyonel VIP odalara, gün başına TEK turndown
housekeeping görevi üretir. Çift üretim DB seviyesinde engellenir
(housekeeping_tasks üzerinde partial-unique compound index).

Değişmezler:
  * Tenant-scoped; housekeeping RBAC.
  * Idempotent: (tenant_id, room_id, task_type='turndown', turndown_date) partial
    unique → aynı gün/oda için ikinci üretim DuplicateKeyError → atlanır
    (sessiz çift-görev YOK; fail-closed index).
  * Yalnızca checked_in rezervasyonu olan odalar; vip_only ise vip_status dolu.
  * Görev gövdesi mevcut housekeeping_tasks şemasıyla uyumlu (task_type='turndown'
    zaten geçerli tip).
"""

import logging
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from core.database import db
from core.security import get_current_user
from models.schemas import User
from shared_kernel.pos_idem import ensure_compound_unique

logger = logging.getLogger("domains.pms.turndown")

router = APIRouter(prefix="/api/turndown", tags=["PMS / Turndown"])

_HK_ROLES = {"super_admin", "admin", "manager", "housekeeping", "supervisor"}

# VIP odalara akşam servisi yüksek öncelik, normal odalara normal.
_DEFAULT_CHECKLIST = [
    "Yatak açma",
    "Perde kapatma",
    "Işık ayarı / gece lambası",
    "Havlu/amenity yenileme",
    "Çikolata/su bırakma",
    "Zemin/çöp kontrolü",
]


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


async def _ensure_turndown_index() -> None:
    await ensure_compound_unique(
        db.housekeeping_tasks,
        [("tenant_id", 1), ("room_id", 1), ("task_type", 1), ("turndown_date", 1)],
        partial_filter={"turndown_date": {"$type": "string"}},
        name="ux_hk_turndown_day_room",
    )


class ScheduleIn(BaseModel):
    service_date: str | None = Field(None, description="YYYY-MM-DD; verilmezse bugün (sunucu).")
    vip_only: bool = False


def _resolve_date(service_date: str | None) -> str:
    if not service_date:
        return date.today().isoformat()
    try:
        return date.fromisoformat(service_date).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Geçersiz service_date (YYYY-MM-DD)") from exc


@router.post("/schedule")
async def schedule_turndown(payload: ScheduleIn, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _HK_ROLES)
    tenant_id = _tenant_of(current_user)
    svc_date = _resolve_date(payload.service_date)
    await _ensure_turndown_index()

    res_query: dict = {"tenant_id": tenant_id, "status": "checked_in"}
    if payload.vip_only:
        res_query["vip_status"] = {"$nin": [None, ""]}

    reservations = await db.reservations.find(
        res_query,
        {"_id": 0, "room_id": 1, "room_number": 1, "vip_status": 1, "id": 1},
    ).to_list(2000)

    created = 0
    skipped = 0
    seen_rooms: set[str] = set()
    for r in reservations:
        room_id = r.get("room_id")
        if not room_id or room_id in seen_rooms:
            continue
        seen_rooms.add(room_id)
        is_vip = bool(r.get("vip_status"))
        now = _now_iso()
        task = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "room_id": room_id,
            "room_number": r.get("room_number"),
            "task_type": "turndown",
            "turndown_date": svc_date,
            "status": "pending",
            "priority": "high" if is_vip else "normal",
            "vip": is_vip,
            "checklist": list(_DEFAULT_CHECKLIST),
            "reservation_id": r.get("id"),
            "auto_assigned": True,
            "created_by": _actor_id(current_user),
            "created_at": now,
        }
        try:
            await db.housekeeping_tasks.insert_one(task)
            created += 1
        except DuplicateKeyError:
            skipped += 1

    return {
        "service_date": svc_date,
        "vip_only": payload.vip_only,
        "rooms_considered": len(seen_rooms),
        "created": created,
        "skipped_existing": skipped,
    }


@router.get("/tasks")
async def list_turndown_tasks(
    service_date: str | None = None,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _HK_ROLES)
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id, "task_type": "turndown"}
    if service_date:
        q["turndown_date"] = _resolve_date(service_date)
    items = await db.housekeeping_tasks.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return {"items": items, "count": len(items)}
