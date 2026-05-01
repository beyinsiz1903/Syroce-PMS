"""Spa & Wellness — services, therapists, treatment rooms, scheduling.

Goes well beyond the original 6-treatment template:
* Service catalog (categorized, taxable, commissionable)
* Therapist roster with specialties + working hours
* Treatment rooms with type/equipment
* Conflict-checked appointment scheduling (therapist AND room)
* Guest treatment history
* Charge-to-folio integration (writes a posting record + raises
  Xchange POSTING_CHARGE event so SAP/finance partners stay in sync)
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from cache_manager import cache as _cache
from cache_manager import cached as _cached
from core.booking_atomicity import (
    is_replica_set_unavailable,
    standalone_fallback_allowed,
    with_resource_locks,
)
from core.security import get_current_user
from core.spa_mice_authz import require_catalog, require_finance, require_spa_ops
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v101 DW

router = APIRouter(prefix="/api/spa", tags=["spa"])

# ── One-time index bootstrap ────────────────────────────────────
_indexes_ready = False


async def _ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    db = get_system_db()
    try:
        await db.spa_appointments.create_index(
            [("tenant_id", 1), ("therapist_id", 1), ("starts_at", 1)],
            name="spa_appt_therapist_time")
        await db.spa_appointments.create_index(
            [("tenant_id", 1), ("room_id", 1), ("starts_at", 1)],
            name="spa_appt_room_time")
        await db.spa_appointments.create_index(
            [("tenant_id", 1), ("guest_id", 1), ("starts_at", -1)],
            name="spa_appt_guest_time")
        await db.spa_appointments.create_index(
            [("tenant_id", 1), ("status", 1), ("starts_at", 1)],
            name="spa_appt_status_time")
        await db.spa_services.create_index([("tenant_id", 1), ("category", 1)])
        await db.spa_therapists.create_index([("tenant_id", 1), ("active", 1)])
        await db.spa_rooms.create_index([("tenant_id", 1), ("active", 1)])
        await db.spa_locks.create_index(
            [("tenant_id", 1), ("kind", 1), ("resource_id", 1)],
            unique=True, name="uniq_spa_lock")
        _indexes_ready = True
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("spa").warning("Index creation deferred: %s", exc)

# ── Catalog: Services ────────────────────────────────────────────
class ServiceIn(BaseModel):
    name: str
    category: str = "massage"  # massage / facial / body / hydro / nail / hair
    duration_minutes: int = Field(60, ge=10, le=480)
    price: float = Field(0, ge=0)
    currency: str = "TRY"
    description: str | None = None
    requires_room_type: str | None = None  # e.g. "wet_room"
    commission_rate: float = Field(0, ge=0, le=1)
    active: bool = True


def _invalidate_spa_services_cache(tenant_id: str) -> None:
    _cache.safe_invalidate(tenant_id, "spa_services")


# rbac-allow: cache-rbac — operasyonel servis listesi tüm rolelere açık (HK temizlik, FO upsell)
@router.get("/services")
@_cached(ttl=30, key_prefix="spa_services")
async def list_services(current_user: User = Depends(get_current_user)) -> dict:
    await _ensure_indexes()
    db = get_system_db()
    cur = db.spa_services.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("category", 1)
    items = [doc async for doc in cur]
    if not items:
        # Seed a sensible default catalog so demos have content immediately.
        # Seeding is a write — gate it on catalog role to keep RBAC honest.
        try:
            require_catalog(current_user)
        except HTTPException:
            return {"services": []}
        items = await _seed_default_catalog(current_user.tenant_id)
    return {"services": items}


async def _seed_default_catalog(tenant_id: str) -> list[dict]:
    db = get_system_db()
    seeds = [
        ("İsveç Masajı 60dk", "massage", 60, 1500),
        ("Derin Doku Masajı 90dk", "massage", 90, 2200),
        ("Sıcak Taş Terapisi", "massage", 75, 2000),
        ("Çiftler Masajı 90dk", "massage", 90, 3600),
        ("Hidratasyon Yüz Bakımı", "facial", 60, 1700),
        ("Anti-aging Yüz Bakımı", "facial", 75, 2300),
        ("Vücut Peelingi & Maske", "body", 75, 1900),
        ("Aromaterapi Banyo", "hydro", 45, 1100),
    ]
    docs = []
    for name, cat, dur, price in seeds:
        docs.append({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "name": name, "category": cat,
            "duration_minutes": dur, "price": price,
            "currency": "TRY", "description": None,
            "requires_room_type": None, "commission_rate": 0.10,
            "active": True,
            "created_at": datetime.now(UTC).isoformat(),
        })
    await db.spa_services.insert_many(docs)
    for d in docs:
        d.pop("_id", None)
    return docs


@router.post("/services")
async def create_service(body: ServiceIn,
                         current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **body.model_dump(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.spa_services.insert_one(doc)
    doc.pop("_id", None)
    _invalidate_spa_services_cache(current_user.tenant_id)
    return doc


@router.put("/services/{service_id}")
async def update_service(service_id: str, body: ServiceIn,
                         current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    res = await db.spa_services.update_one(
        {"id": service_id, "tenant_id": current_user.tenant_id},
        {"$set": {**body.model_dump(),
                  "updated_at": datetime.now(UTC).isoformat()}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Hizmet bulunamadı")
    _invalidate_spa_services_cache(current_user.tenant_id)
    return {"ok": True}


@router.delete("/services/{service_id}")
async def delete_service(service_id: str,
                         current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    res = await db.spa_services.delete_one(
        {"id": service_id, "tenant_id": current_user.tenant_id})
    if not res.deleted_count:
        raise HTTPException(404, "Hizmet bulunamadı")
    _invalidate_spa_services_cache(current_user.tenant_id)
    return {"ok": True}


# ── Therapists ──────────────────────────────────────────────────
class TherapistIn(BaseModel):
    name: str
    specialties: list[str] = Field(default_factory=list)  # service categories
    phone: str | None = None
    email: str | None = None
    working_days: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5, 6, 7])  # ISO 1=Mon
    work_start: str = "09:00"  # HH:MM
    work_end: str = "21:00"
    color: str = "#8b5cf6"
    active: bool = True


@router.get("/therapists")
async def list_therapists(current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    cur = db.spa_therapists.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("name", 1)
    return {"therapists": [doc async for doc in cur]}


@router.post("/therapists")
async def create_therapist(body: TherapistIn,
                           current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **body.model_dump(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.spa_therapists.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/therapists/{therapist_id}")
async def update_therapist(therapist_id: str, body: TherapistIn,
                           current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    res = await db.spa_therapists.update_one(
        {"id": therapist_id, "tenant_id": current_user.tenant_id},
        {"$set": body.model_dump()},
    )
    if not res.matched_count:
        raise HTTPException(404, "Terapist bulunamadı")
    return {"ok": True}


@router.delete("/therapists/{therapist_id}")
async def delete_therapist(therapist_id: str,
                           current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    await db.spa_therapists.delete_one(
        {"id": therapist_id, "tenant_id": current_user.tenant_id})
    return {"ok": True}


# ── Treatment rooms ─────────────────────────────────────────────
class TreatmentRoomIn(BaseModel):
    name: str
    room_type: str = "standard"  # standard / couples / wet_room / hammam / sauna
    capacity: int = Field(1, ge=1)
    equipment: list[str] = Field(default_factory=list)
    active: bool = True


@router.get("/rooms")
async def list_rooms(current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    cur = db.spa_rooms.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("name", 1)
    return {"rooms": [doc async for doc in cur]}


@router.post("/rooms")
async def create_room(body: TreatmentRoomIn,
                      current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **body.model_dump(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.spa_rooms.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/rooms/{room_id}")
async def update_room(room_id: str, body: TreatmentRoomIn,
                      current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    res = await db.spa_rooms.update_one(
        {"id": room_id, "tenant_id": current_user.tenant_id},
        {"$set": body.model_dump()},
    )
    if not res.matched_count:
        raise HTTPException(404, "Oda bulunamadı")
    return {"ok": True}


@router.delete("/rooms/{room_id}")
async def delete_room(room_id: str,
                      current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    await db.spa_rooms.delete_one(
        {"id": room_id, "tenant_id": current_user.tenant_id})
    return {"ok": True}


# ── Appointments ────────────────────────────────────────────────
class AppointmentIn(BaseModel):
    service_id: str
    therapist_id: str | None = None  # optional → "first available"
    room_id: str | None = None       # optional → "first available"
    starts_at: datetime
    guest_id: str | None = None
    guest_name: str
    guest_phone: str | None = None
    reservation_id: str | None = None  # link to PMS reservation
    notes: str | None = None
    charge_to_room: bool = False
    price_override: float | None = None


def _overlap(start_a: datetime, end_a: datetime,
             start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and start_b < end_a


async def _check_conflict(tenant_id: str, *, therapist_id: str | None,
                          room_id: str | None, start: datetime, end: datetime,
                          exclude_id: str | None = None,
                          session=None) -> str | None:
    db = get_system_db()
    q: dict[str, Any] = {
        "tenant_id": tenant_id,
        "status": {"$in": ["scheduled", "in_progress"]},
        "starts_at": {"$lt": end.isoformat()},
        "ends_at": {"$gt": start.isoformat()},
    }
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    async for doc in db.spa_appointments.find(q, session=session):
        if therapist_id and doc.get("therapist_id") == therapist_id:
            return f"Terapist çakışması: {doc.get('guest_name')}"
        if room_id and doc.get("room_id") == room_id:
            return f"Oda çakışması: {doc.get('guest_name')}"
    return None


@router.get("/appointments")
async def list_appointments(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    therapist_id: str | None = Query(None),
    status: str | None = Query(None),
    current_user: User = Depends(get_current_user),
) -> dict:
    db = get_system_db()
    q: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    if therapist_id:
        q["therapist_id"] = therapist_id
    if status:
        q["status"] = status
    if date_from or date_to:
        rng: dict[str, Any] = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        q["starts_at"] = rng
    cur = db.spa_appointments.find(q, {"_id": 0}).sort("starts_at", 1).limit(500)
    return {"appointments": [doc async for doc in cur]}


@router.post("/appointments")
async def create_appointment(body: AppointmentIn,
                             current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_spa_ops(current_user)
    await _ensure_indexes()
    db = get_system_db()
    tenant_id = current_user.tenant_id

    service = await db.spa_services.find_one(
        {"id": body.service_id, "tenant_id": tenant_id})
    if not service:
        raise HTTPException(404, "Hizmet bulunamadı")

    starts = body.starts_at if body.starts_at.tzinfo else body.starts_at.replace(tzinfo=UTC)
    ends = starts + timedelta(minutes=service["duration_minutes"])

    therapist_id = body.therapist_id
    room_id = body.room_id

    # ── Auto-pick (best-effort outside the lock; final check is atomic) ──
    if not therapist_id:
        async for t in db.spa_therapists.find(
                {"tenant_id": tenant_id, "active": True}):
            if service["category"] in (t.get("specialties") or []) or not t.get("specialties"):
                if not await _check_conflict(tenant_id, therapist_id=t["id"],
                                             room_id=None, start=starts, end=ends):
                    therapist_id = t["id"]
                    break
    if not room_id:
        req_type = service.get("requires_room_type")
        async for r in db.spa_rooms.find({"tenant_id": tenant_id, "active": True}):
            if req_type and r.get("room_type") != req_type:
                continue
            if not await _check_conflict(tenant_id, therapist_id=None,
                                         room_id=r["id"], start=starts, end=ends):
                room_id = r["id"]
                break

    appt = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "service_id": body.service_id,
        "service_name": service["name"],
        "service_category": service["category"],
        "therapist_id": therapist_id,
        "room_id": room_id,
        "starts_at": starts.isoformat(),
        "ends_at": ends.isoformat(),
        "duration_minutes": service["duration_minutes"],
        "price": body.price_override if body.price_override is not None else service["price"],
        "currency": service.get("currency", "TRY"),
        "guest_id": body.guest_id,
        "guest_name": body.guest_name,
        "guest_phone": body.guest_phone,
        "reservation_id": body.reservation_id,
        "notes": body.notes,
        "charge_to_room": body.charge_to_room,
        "status": "scheduled",
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.username,
    }

    # ── Atomic conflict re-check + insert under per-resource locks ──
    async def _do_insert(session) -> dict:
        conflict = await _check_conflict(
            tenant_id, therapist_id=therapist_id, room_id=room_id,
            start=starts, end=ends, session=session,
        )
        if conflict:
            raise HTTPException(409, conflict)
        await db.spa_appointments.insert_one(appt, session=session)
        return appt

    try:
        await with_resource_locks(
            client=db.client, db=db,
            tenant_id=tenant_id,
            locks_collection="spa_locks",
            resources=[("therapist", therapist_id), ("room", room_id)],
            callback=_do_insert,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        if not is_replica_set_unavailable(exc):
            raise
        if not standalone_fallback_allowed():
            # Production-safe default: refuse rather than risk a race.
            raise HTTPException(
                status_code=503,
                detail=("Rezervasyon servisi şu anda atomik garanti "
                        "sağlayamıyor (Mongo replica set gerekli)."),
            )
        # Dev opt-in: best-effort non-tx fallback.
        conflict = await _check_conflict(
            tenant_id, therapist_id=therapist_id, room_id=room_id,
            start=starts, end=ends,
        )
        if conflict:
            raise HTTPException(409, conflict)
        await db.spa_appointments.insert_one(appt)

    appt.pop("_id", None)
    return appt


class StatusUpdate(BaseModel):
    status: str  # scheduled / in_progress / completed / no_show / cancelled


@router.post("/appointments/{appt_id}/status")
async def change_status(appt_id: str, body: StatusUpdate,
                        current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_spa_ops(current_user)
    if body.status == "completed":
        require_finance(current_user)  # folio-impacting transition
    if body.status not in _SPA_TRANSITIONS:
        raise HTTPException(400, "Geçersiz durum")
    db = get_system_db()
    appt = await db.spa_appointments.find_one(
        {"id": appt_id, "tenant_id": current_user.tenant_id})
    if not appt:
        raise HTTPException(404, "Randevu bulunamadı")
    cur_status = appt.get("status", "scheduled")
    if body.status not in _SPA_TRANSITIONS.get(cur_status, set()):
        raise HTTPException(
            409, f"Geçersiz geçiş: {cur_status} → {body.status}")
    update = {"status": body.status,
              "updated_at": datetime.now(UTC).isoformat()}
    if body.status == "completed":
        update["completed_at"] = datetime.now(UTC).isoformat()
        if appt.get("charge_to_room") and appt.get("reservation_id"):
            await _post_to_folio(current_user.tenant_id, appt)
    # IMPORTANT: include tenant_id in the write filter (cross-tenant safety).
    await db.spa_appointments.update_one(
        {"id": appt_id, "tenant_id": current_user.tenant_id},
        {"$set": update},
    )
    return {"ok": True, "status": body.status}


# Allowed status transitions (defensive workflow guard).
_SPA_TRANSITIONS: dict[str, set[str]] = {
    "scheduled": {"in_progress", "completed", "no_show", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
    "no_show": set(),
    "cancelled": set(),
}


async def _post_to_folio(tenant_id: str, appt: dict) -> None:
    """Write a folio posting and emit Xchange POSTING_CHARGE if available."""
    db = get_system_db()
    posting = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "reservation_id": appt.get("reservation_id"),
        "folio_id": appt.get("reservation_id"),  # 1:1 with reservation
        "transaction_code": "SPA",
        "description": f"Spa: {appt.get('service_name')}",
        "amount": float(appt.get("price", 0)),
        "currency": appt.get("currency", "TRY"),
        "posting_type": "CHARGE",
        "posted_at": datetime.now(UTC).isoformat(),
        "source": "spa_module",
        "reference": appt.get("id"),
    }
    await db.folio_postings.insert_one(posting)
    # Best-effort Xchange publish (don't fail the spa workflow on bus error)
    try:
        from integrations.xchange.bus import bus
        from integrations.xchange.schemas import MessageType
        await bus.publish(
            tenant_id=tenant_id,
            message_type=MessageType.POSTING_CHARGE,
            payload={
                "posting_id": posting["id"],
                "reservation_id": posting["reservation_id"],
                "folio_id": posting["folio_id"],
                "posting_type": "CHARGE",
                "transaction_code": "SPA",
                "description": posting["description"],
                "amount": posting["amount"],
                "currency": posting["currency"],
                "posted_at": posting["posted_at"],
            },
            message_id=f"spa-{posting['id']}",
        )
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("spa").warning(
            "Xchange POSTING_CHARGE publish failed (best-effort): %s", exc)


@router.delete("/appointments/{appt_id}")
async def delete_appointment(appt_id: str,
                             current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_spa_ops(current_user)
    db = get_system_db()
    res = await db.spa_appointments.delete_one(
        {"id": appt_id, "tenant_id": current_user.tenant_id})
    if not res.deleted_count:
        raise HTTPException(404, "Randevu bulunamadı")
    return {"ok": True}


# ── Guest history ───────────────────────────────────────────────
@router.get("/guests/{guest_id}/history")
async def guest_history(guest_id: str,
                        current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    cur = db.spa_appointments.find(
        {"tenant_id": current_user.tenant_id, "guest_id": guest_id},
        {"_id": 0},
    ).sort("starts_at", -1).limit(50)
    items = [doc async for doc in cur]
    total_spend = sum(
        float(a.get("price", 0)) for a in items
        if a.get("status") == "completed"
    )
    return {
        "appointments": items,
        "total_visits": sum(1 for a in items if a.get("status") == "completed"),
        "total_spend": round(total_spend, 2),
        "favorite_category": _most_common(
            [a.get("service_category") for a in items if a.get("status") == "completed"]
        ),
    }


def _most_common(items: list[Any]) -> Any:
    counts: dict[Any, int] = {}
    for x in items:
        if x is None:
            continue
        counts[x] = counts.get(x, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0] if counts else None


# ── Daily summary (dashboard) ───────────────────────────────────
@router.get("/daily-summary")
async def daily_summary(
    date: str | None = Query(None),
    current_user: User = Depends(get_current_user),
) -> dict:
    db = get_system_db()
    target = date or datetime.now(UTC).date().isoformat()
    # Use proper next-day range instead of ascii-trick string compare.
    next_day = (datetime.fromisoformat(target) + timedelta(days=1)).date().isoformat()
    cur = db.spa_appointments.find({
        "tenant_id": current_user.tenant_id,
        "starts_at": {"$gte": target, "$lt": next_day},
    }, {"_id": 0})
    items = [d async for d in cur]
    by_status: dict[str, int] = {}
    revenue = 0.0
    for a in items:
        by_status[a["status"]] = by_status.get(a["status"], 0) + 1
        if a["status"] == "completed":
            revenue += float(a.get("price", 0))
    return {
        "date": target,
        "total": len(items),
        "by_status": by_status,
        "revenue": round(revenue, 2),
    }
