"""Activity Scheduler — Spa dışı genel aktiviteler (Golf, Tenis, Yoga, Bisiklet…)
Kaynak (eğitmen/kort/ekipman) atama, çakışma kontrolü, saatlik takvim.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

try:  # pragma: no cover - mirrors guest read-path import guard
    from security.field_encryption import get_field_encryption_service

    _fenc = get_field_encryption_service()
except Exception:  # pragma: no cover
    _fenc = None

router = APIRouter(prefix="/api/activities", tags=["Activity Scheduler"])

_GUEST_COLLECTION = "guests"


def _guest_display_name(doc: dict) -> str | None:
    """Decrypt a guest doc at the read boundary and derive a display name only.

    Mirrors the unified-search read path: only the guest's name is surfaced, no
    email / phone / id, so this stays within existing PII read boundaries.
    """
    if not doc:
        return None
    if _fenc:
        try:
            doc = _fenc.decrypt_document(doc, collection=_GUEST_COLLECTION)
        except Exception:  # pragma: no cover - never block the list on a bad doc
            pass
    if doc.get("first_name") or doc.get("last_name"):
        name = f"{doc.get('first_name', '')} {doc.get('last_name', '')}".strip()
        if name:
            return name
    return doc.get("name") or None


async def _guest_names_by_id(tenant_id: str, guest_ids: list[str]) -> dict[str, str]:
    """Resolve a batch of guest_ids to display names in a single tenant-scoped query."""
    ids = list({g for g in guest_ids if g})
    if not ids:
        return {}
    db = get_system_db()
    rows = await db.guests.find({"tenant_id": tenant_id, "id": {"$in": ids}}).to_list(len(ids))
    out: dict[str, str] = {}
    for r in rows:
        name = _guest_display_name(r)
        if name:
            out[r["id"]] = name
    return out


ACTIVITY_TYPES = ("golf", "tennis", "yoga", "fitness", "bike", "diving", "kids", "other")


class Activity(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1)
    type: str = Field("other")
    duration_min: int = Field(default=60, ge=15, le=1440)
    price: float = Field(default=0, ge=0, le=10_000_000)
    capacity: int = Field(default=1, ge=1, le=10_000)
    description: str | None = None
    active: bool = True


class ActivityResource(BaseModel):
    """Eğitmen, kort, sahil, ekipman vb."""

    id: str | None = None
    name: str
    kind: str = Field("instructor", pattern="^(instructor|venue|equipment)$")
    activity_types: list[str] = Field(default_factory=list)
    capacity: int = Field(default=1, ge=1, le=10_000)
    active: bool = True


class ActivityBookingCreate(BaseModel):
    activity_id: str
    resource_id: str
    guest_id: str
    starts_at: str  # ISO
    duration_min: int | None = Field(default=None, ge=15, le=1440)
    note: str | None = None

    @field_validator("starts_at")
    @classmethod
    def validate_starts_at(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("starts_at ISO tarih-saat olmalıdır") from exc
        if parsed.tzinfo is None:
            raise ValueError("starts_at saat dilimi içermelidir")
        return parsed.isoformat()


class ActivityBooking(ActivityBookingCreate):
    id: str
    tenant_id: str
    ends_at: str
    status: str = "booked"
    created_by: str
    created_at: str
    guest_name: str | None = None


_INDEXES_INITIALIZED = False


async def _ensure_indexes() -> None:
    global _INDEXES_INITIALIZED
    if _INDEXES_INITIALIZED:
        return
    db = get_system_db()
    try:
        await db.activities.create_index([("tenant_id", 1), ("type", 1), ("active", 1)])
        await db.activity_resources.create_index([("tenant_id", 1), ("kind", 1), ("active", 1)])
        await db.activity_bookings.create_index(
            [("tenant_id", 1), ("resource_id", 1), ("starts_at", 1)],
            name="actbook_resource_time",
        )
        await db.activity_bookings.create_index([("tenant_id", 1), ("guest_id", 1), ("starts_at", -1)])
        _INDEXES_INITIALIZED = True
    except Exception:
        # Index oluşturulamazsa flag set edilmez → bir sonraki çağrıda yeniden denenir.
        pass


# ── Activities ───────────────────────────────────────
@router.get("", response_model=list[Activity])
async def list_activities(type: str | None = None, user: User = Depends(get_current_user)):
    await _ensure_indexes()
    db = get_system_db()
    q: dict[str, Any] = {"tenant_id": user.tenant_id, "active": True}
    if type:
        q["type"] = type
    docs = await db.activities.find(q).to_list(200)
    for d in docs:
        d.pop("_id", None)
    return docs


@router.post("", response_model=Activity, status_code=201)
async def create_activity(body: Activity, user: User = Depends(get_current_user), _perm=Depends(require_op("manage_guests"))):
    if body.type not in ACTIVITY_TYPES:
        raise HTTPException(400, f"Tip şunlardan biri olmalı: {ACTIVITY_TYPES}")
    db = get_system_db()
    doc = body.model_dump()
    doc["id"] = doc.get("id") or str(uuid.uuid4())
    doc["tenant_id"] = user.tenant_id
    doc["created_at"] = datetime.now(UTC).isoformat()
    await db.activities.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/{activity_id}", status_code=204)
async def delete_activity(activity_id: str, user: User = Depends(get_current_user), _perm=Depends(require_op("manage_guests"))):
    db = get_system_db()
    result = await db.activities.update_one({"id": activity_id, "tenant_id": user.tenant_id}, {"$set": {"active": False}})
    if not result.matched_count:
        raise HTTPException(404, "Aktivite bulunamadı")
    return None


# ── Resources ────────────────────────────────────────
@router.get("/resources", response_model=list[ActivityResource])
async def list_resources(kind: str | None = None, user: User = Depends(get_current_user)):
    await _ensure_indexes()
    db = get_system_db()
    q: dict[str, Any] = {"tenant_id": user.tenant_id, "active": True}
    if kind:
        q["kind"] = kind
    docs = await db.activity_resources.find(q).to_list(200)
    for d in docs:
        d.pop("_id", None)
    return docs


@router.post("/resources", response_model=ActivityResource, status_code=201)
async def create_resource(body: ActivityResource, user: User = Depends(get_current_user), _perm=Depends(require_op("manage_guests"))):
    db = get_system_db()
    doc = body.model_dump()
    doc["id"] = doc.get("id") or str(uuid.uuid4())
    doc["tenant_id"] = user.tenant_id
    doc["created_at"] = datetime.now(UTC).isoformat()
    await db.activity_resources.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/resources/{resource_id}", status_code=204)
async def delete_resource(resource_id: str, user: User = Depends(get_current_user), _perm=Depends(require_op("manage_guests"))):
    db = get_system_db()
    result = await db.activity_resources.update_one({"id": resource_id, "tenant_id": user.tenant_id}, {"$set": {"active": False}})
    if not result.matched_count:
        raise HTTPException(404, "Kaynak bulunamadı")
    return None


# ── Bookings ─────────────────────────────────────────
def _add_minutes(iso: str, minutes: int) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (dt + __import__("datetime").timedelta(minutes=minutes)).isoformat()


@router.get("/bookings", response_model=list[ActivityBooking])
async def list_bookings(
    date: str | None = None,
    resource_id: str | None = None,
    user: User = Depends(get_current_user),
):
    await _ensure_indexes()
    db = get_system_db()
    q: dict[str, Any] = {"tenant_id": user.tenant_id}
    if resource_id:
        q["resource_id"] = resource_id
    if date:
        q["starts_at"] = {"$gte": f"{date}T00:00:00", "$lte": f"{date}T23:59:59"}
    docs = await db.activity_bookings.find(q).sort("starts_at", 1).to_list(500)
    for d in docs:
        d.pop("_id", None)
    names = await _guest_names_by_id(user.tenant_id, [d.get("guest_id") for d in docs])
    for d in docs:
        d["guest_name"] = names.get(d.get("guest_id"))
    return docs


@router.post("/bookings", response_model=ActivityBooking, status_code=201)
async def create_booking(body: ActivityBookingCreate, user: User = Depends(get_current_user), _perm=Depends(require_op("manage_guests"))):
    await _ensure_indexes()
    db = get_system_db()
    activity = await db.activities.find_one({"id": body.activity_id, "tenant_id": user.tenant_id, "active": True})
    if not activity:
        raise HTTPException(404, "Aktivite bulunamadı")
    resource = await db.activity_resources.find_one(
        {"id": body.resource_id, "tenant_id": user.tenant_id, "active": True}
    )
    if not resource:
        raise HTTPException(404, "Aktivite kaynağı bulunamadı")
    supported_types = resource.get("activity_types") or []
    if supported_types and activity.get("type") not in supported_types:
        raise HTTPException(400, "Seçilen kaynak bu aktivite tipini desteklemiyor")
    guest = await db.guests.find_one({"id": body.guest_id, "tenant_id": user.tenant_id}, {"_id": 0, "id": 1})
    if not guest:
        raise HTTPException(404, "Misafir bulunamadı")
    duration = body.duration_min or activity.get("duration_min", 60)
    ends_at = _add_minutes(body.starts_at, duration)
    # Çakışma kontrolü: aynı kaynak + zaman dilimi
    overlaps = await db.activity_bookings.count_documents(
        {
            "tenant_id": user.tenant_id,
            "resource_id": body.resource_id,
            "status": {"$ne": "cancelled"},
            "starts_at": {"$lt": ends_at},
            "ends_at": {"$gt": body.starts_at},
        }
    )
    capacity = min(int(resource.get("capacity", 1)), int(activity.get("capacity", resource.get("capacity", 1))))
    if overlaps >= capacity:
        raise HTTPException(409, f"Kaynak bu zaman diliminde dolu ({overlaps}/{capacity})")
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": user.tenant_id,
        "ends_at": ends_at,
        "status": "booked",
        "created_by": user.email,
        "created_at": datetime.now(UTC).isoformat(),
        **body.model_dump(),
        "duration_min": duration,
    }
    await db.activity_bookings.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(booking_id: str, user: User = Depends(get_current_user), _perm=Depends(require_op("manage_guests"))):
    db = get_system_db()
    res = await db.activity_bookings.update_one(
        {"id": booking_id, "tenant_id": user.tenant_id},
        {"$set": {"status": "cancelled", "cancelled_at": datetime.now(UTC).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    return {"ok": True}


@router.get("/availability")
async def availability(
    activity_id: str,
    date: str,
    user: User = Depends(get_current_user),
):
    """Verilen tarih için her kaynağın boş slot'larını döner (basit özet)."""
    db = get_system_db()
    activity = await db.activities.find_one({"id": activity_id, "tenant_id": user.tenant_id})
    if not activity:
        raise HTTPException(404, "Aktivite bulunamadı")
    resources = await db.activity_resources.find(
        {
            "tenant_id": user.tenant_id,
            "active": True,
            "$or": [
                {"activity_types": activity.get("type")},
                {"activity_types": []},
            ],
        }
    ).to_list(200)
    out = []
    for r in resources:
        bookings = await db.activity_bookings.find(
            {
                "tenant_id": user.tenant_id,
                "resource_id": r["id"],
                "status": {"$ne": "cancelled"},
                "starts_at": {"$gte": f"{date}T00:00:00", "$lte": f"{date}T23:59:59"},
            }
        ).to_list(100)
        out.append(
            {
                "resource_id": r["id"],
                "resource_name": r["name"],
                "kind": r.get("kind"),
                "booked": [{"starts_at": b["starts_at"], "ends_at": b["ends_at"]} for b in bookings],
            }
        )
    return {"date": date, "activity_id": activity_id, "resources": out}
