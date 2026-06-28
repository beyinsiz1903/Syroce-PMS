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
        await db.spa_appointments.create_index([("tenant_id", 1), ("therapist_id", 1), ("starts_at", 1)], name="spa_appt_therapist_time")
        await db.spa_appointments.create_index([("tenant_id", 1), ("room_id", 1), ("starts_at", 1)], name="spa_appt_room_time")
        await db.spa_appointments.create_index([("tenant_id", 1), ("guest_id", 1), ("starts_at", -1)], name="spa_appt_guest_time")
        await db.spa_appointments.create_index([("tenant_id", 1), ("status", 1), ("starts_at", 1)], name="spa_appt_status_time")
        await db.spa_services.create_index([("tenant_id", 1), ("category", 1)])
        await db.spa_therapists.create_index([("tenant_id", 1), ("active", 1)])
        await db.spa_rooms.create_index([("tenant_id", 1), ("active", 1)])
        await db.spa_locks.create_index([("tenant_id", 1), ("kind", 1), ("resource_id", 1)], unique=True, name="uniq_spa_lock")
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
    cur = db.spa_services.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).sort("category", 1)
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
        docs.append(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "name": name,
                "category": cat,
                "duration_minutes": dur,
                "price": price,
                "currency": "TRY",
                "description": None,
                "requires_room_type": None,
                "commission_rate": 0.10,
                "active": True,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
    await db.spa_services.insert_many(docs)
    for d in docs:
        d.pop("_id", None)
    return docs


@router.post("/services")
async def create_service(
    body: ServiceIn,
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
async def update_service(
    service_id: str,
    body: ServiceIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    res = await db.spa_services.update_one(
        {"id": service_id, "tenant_id": current_user.tenant_id},
        {"$set": {**body.model_dump(), "updated_at": datetime.now(UTC).isoformat()}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Hizmet bulunamadı")
    _invalidate_spa_services_cache(current_user.tenant_id)
    return {"ok": True}


@router.delete("/services/{service_id}")
async def delete_service(
    service_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    res = await db.spa_services.delete_one({"id": service_id, "tenant_id": current_user.tenant_id})
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
    cur = db.spa_therapists.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).sort("name", 1)
    return {"therapists": [doc async for doc in cur]}


@router.post("/therapists")
async def create_therapist(
    body: TherapistIn,
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
async def update_therapist(
    therapist_id: str,
    body: TherapistIn,
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
async def delete_therapist(
    therapist_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    await db.spa_therapists.delete_one({"id": therapist_id, "tenant_id": current_user.tenant_id})
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
    cur = db.spa_rooms.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).sort("name", 1)
    return {"rooms": [doc async for doc in cur]}


@router.post("/rooms")
async def create_room(
    body: TreatmentRoomIn,
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
async def update_room(
    room_id: str,
    body: TreatmentRoomIn,
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
async def delete_room(
    room_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    await db.spa_rooms.delete_one({"id": room_id, "tenant_id": current_user.tenant_id})
    return {"ok": True}


# ── Appointments ────────────────────────────────────────────────
class AppointmentIn(BaseModel):
    service_id: str
    therapist_id: str | None = None  # optional → "first available"
    room_id: str | None = None  # optional → "first available"
    starts_at: datetime
    guest_id: str | None = None
    guest_name: str
    guest_phone: str | None = None
    reservation_id: str | None = None  # link to PMS reservation
    notes: str | None = None
    charge_to_room: bool = False
    price_override: float | None = None


def _overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and start_b < end_a


async def _check_conflict(tenant_id: str, *, therapist_id: str | None, room_id: str | None, start: datetime, end: datetime, exclude_id: str | None = None, session=None) -> str | None:
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
async def create_appointment(
    body: AppointmentIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_spa_ops(current_user)
    await _ensure_indexes()
    db = get_system_db()
    tenant_id = current_user.tenant_id

    service = await db.spa_services.find_one({"id": body.service_id, "tenant_id": tenant_id})
    if not service:
        raise HTTPException(404, "Hizmet bulunamadı")

    starts = body.starts_at if body.starts_at.tzinfo else body.starts_at.replace(tzinfo=UTC)
    ends = starts + timedelta(minutes=service["duration_minutes"])

    therapist_id = body.therapist_id
    room_id = body.room_id

    # ── Auto-pick (best-effort outside the lock; final check is atomic) ──
    if not therapist_id:
        async for t in db.spa_therapists.find({"tenant_id": tenant_id, "active": True}):
            if service["category"] in (t.get("specialties") or []) or not t.get("specialties"):
                if not await _check_conflict(tenant_id, therapist_id=t["id"], room_id=None, start=starts, end=ends):
                    therapist_id = t["id"]
                    break
    if not room_id:
        req_type = service.get("requires_room_type")
        async for r in db.spa_rooms.find({"tenant_id": tenant_id, "active": True}):
            if req_type and r.get("room_type") != req_type:
                continue
            if not await _check_conflict(tenant_id, therapist_id=None, room_id=r["id"], start=starts, end=ends):
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
            tenant_id,
            therapist_id=therapist_id,
            room_id=room_id,
            start=starts,
            end=ends,
            session=session,
        )
        if conflict:
            raise HTTPException(409, conflict)
        await db.spa_appointments.insert_one(appt, session=session)
        return appt

    try:
        await with_resource_locks(
            client=db.client,
            db=db,
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
                detail=("Rezervasyon servisi şu anda atomik garanti sağlayamıyor (Mongo replica set gerekli)."),
            )
        # Dev opt-in: best-effort non-tx fallback.
        conflict = await _check_conflict(
            tenant_id,
            therapist_id=therapist_id,
            room_id=room_id,
            start=starts,
            end=ends,
        )
        if conflict:
            raise HTTPException(409, conflict)
        await db.spa_appointments.insert_one(appt)

    appt.pop("_id", None)
    return appt


class StatusUpdate(BaseModel):
    status: str  # scheduled / in_progress / completed / no_show / cancelled


@router.post("/appointments/{appt_id}/status")
async def change_status(
    appt_id: str,
    body: StatusUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_spa_ops(current_user)
    if body.status == "completed":
        require_finance(current_user)  # folio-impacting transition
    if body.status not in _SPA_TRANSITIONS:
        raise HTTPException(400, "Geçersiz durum")
    db = get_system_db()
    appt = await db.spa_appointments.find_one({"id": appt_id, "tenant_id": current_user.tenant_id})
    if not appt:
        raise HTTPException(404, "Randevu bulunamadı")
    cur_status = appt.get("status", "scheduled")
    if body.status not in _SPA_TRANSITIONS.get(cur_status, set()):
        raise HTTPException(409, f"Geçersiz geçiş: {cur_status} → {body.status}")
    update = {"status": body.status, "updated_at": datetime.now(UTC).isoformat()}
    if body.status == "completed":
        update["completed_at"] = datetime.now(UTC).isoformat()
    # Atomic CAS claim FIRST: only the request that flips the status from the
    # observed value runs the folio side effect, so a concurrent transition
    # (e.g. another "completed", or a "cancelled") never leaves a charge
    # attached to a non-completed record. tenant_id keeps cross-tenant safety.
    res = await db.spa_appointments.update_one(
        {"id": appt_id, "tenant_id": current_user.tenant_id, "status": cur_status},
        {"$set": update},
    )
    if res.modified_count == 0:
        latest = await db.spa_appointments.find_one({"id": appt_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
        return {"ok": True, "status": latest.get("status") if latest else body.status, "idempotent": True}
    # We won the transition → run the folio side effect (idempotent via the
    # dedup index). If it fails, the completion must not stand: revert the
    # transition we just claimed (fail-closed, no completed-without-charge).
    if body.status == "completed" and appt.get("charge_to_room") and appt.get("reservation_id"):
        try:
            await _post_to_folio(current_user.tenant_id, appt)
        except Exception:
            await db.spa_appointments.update_one(
                {"id": appt_id, "tenant_id": current_user.tenant_id, "status": "completed"},
                {"$set": {"status": cur_status, "updated_at": datetime.now(UTC).isoformat()}, "$unset": {"completed_at": ""}},
            )
            raise
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
    """Write a folio posting (idempotent) and emit Xchange POSTING_CHARGE.

    Dedup: a unique partial index on ``(tenant_id, dedup_key)`` makes the
    posting insert idempotent per appointment. A second "completed" PATCH
    (or a retry) hits ``DuplicateKeyError`` → no double charge and no
    duplicate Xchange event. Fail-closed: if the dedup index cannot be
    ensured, the insert is aborted so completion fails rather than risk a
    non-idempotent charge.
    """
    from pymongo.errors import DuplicateKeyError

    from shared_kernel.pos_idem import ensure_compound_unique

    db = get_system_db()
    await ensure_compound_unique(
        db.folio_postings,
        [("tenant_id", 1), ("dedup_key", 1)],
        partial_filter={"dedup_key": {"$type": "string"}},
        name="uniq_folio_postings_dedup",
    )  # may raise → fail-closed (no charge without dedup guarantee)
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
        "dedup_key": f"spa_module:{appt.get('id')}",
    }
    try:
        await db.folio_postings.insert_one(posting)
    except DuplicateKeyError:
        # Already posted for this appointment → idempotent no-op; do not
        # re-publish the Xchange event.
        return
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

        logging.getLogger("spa").warning("Xchange POSTING_CHARGE publish failed (best-effort): %s", exc)


@router.delete("/appointments/{appt_id}")
async def delete_appointment(
    appt_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
) -> dict:
    require_spa_ops(current_user)
    db = get_system_db()
    res = await db.spa_appointments.delete_one({"id": appt_id, "tenant_id": current_user.tenant_id})
    if not res.deleted_count:
        raise HTTPException(404, "Randevu bulunamadı")
    return {"ok": True}


# ── Guest history ───────────────────────────────────────────────
@router.get("/guests/{guest_id}/history")
async def guest_history(guest_id: str, current_user: User = Depends(get_current_user)) -> dict:
    db = get_system_db()
    cur = (
        db.spa_appointments.find(
            {"tenant_id": current_user.tenant_id, "guest_id": guest_id},
            {"_id": 0},
        )
        .sort("starts_at", -1)
        .limit(50)
    )
    items = [doc async for doc in cur]
    total_spend = sum(float(a.get("price", 0)) for a in items if a.get("status") == "completed")
    return {
        "appointments": items,
        "total_visits": sum(1 for a in items if a.get("status") == "completed"),
        "total_spend": round(total_spend, 2),
        "favorite_category": _most_common([a.get("service_category") for a in items if a.get("status") == "completed"]),
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
    cur = db.spa_appointments.find(
        {
            "tenant_id": current_user.tenant_id,
            "starts_at": {"$gte": target, "$lt": next_day},
        },
        {"_id": 0},
    )
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


# ── v97: Resource scheduling depth — availability grid + waitlist ──
# Opera Cloud parity gap'inden gelen iki eksik:
# 1) Real-time terapist+oda müsaitlik penceresi (dashboard rezervasyon UX'i)
# 2) Slot dolu ise misafiri kuyruğa al, slot açıldıkça öneri ver


@router.get("/availability")
async def availability_grid(
    date: str = Query(..., description="YYYY-MM-DD"),
    service_id: str | None = Query(None),
    slot_minutes: int = Query(30, ge=15, le=120),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Terapist x zaman dilimi şeklinde müsaitlik tablosu döndürür.

    Bir slot 'available' ise ilgili terapist o pencerede başka bir
    randevuya atanmamış demektir. service_id verilirse o servisin
    süresi kadar (slot_minutes yerine) blok kontrol edilir.
    """
    db = get_system_db()
    tenant_id = current_user.tenant_id

    try:
        day = datetime.fromisoformat(date).date()
    except ValueError:
        raise HTTPException(400, "Geçersiz tarih (YYYY-MM-DD bekleniyor)")

    # Aktif terapistler
    therapists = [t async for t in db.spa_therapists.find({"tenant_id": tenant_id, "active": True}, {"_id": 0})]
    if not therapists:
        return {
            "date": date,
            "slots": [],
            "therapists": [],
            "stats": {
                "total_slots": 0,
                "available_slots": 0,
                "utilization_pct": 0,
            },
        }

    duration = slot_minutes
    if service_id:
        svc = await db.spa_services.find_one({"id": service_id, "tenant_id": tenant_id})
        if svc:
            duration = int(svc.get("duration_minutes") or slot_minutes)

    # Çalışma penceresi: terapist working_hours min/max'i
    work_start_h = min(int((t.get("work_start") or "09:00").split(":")[0]) for t in therapists)
    work_end_h = max(int((t.get("work_end") or "21:00").split(":")[0]) for t in therapists)
    if work_end_h <= work_start_h:
        work_end_h = work_start_h + 1

    base = datetime.combine(day, datetime.min.time()).replace(hour=work_start_h, tzinfo=UTC)
    end_of_day = datetime.combine(day, datetime.min.time()).replace(hour=work_end_h, tzinfo=UTC)

    # Günün tüm randevularını tek seferde çek
    appts = [
        a
        async for a in db.spa_appointments.find(
            {
                "tenant_id": tenant_id,
                "starts_at": {"$gte": base.isoformat(), "$lt": end_of_day.isoformat()},
                "status": {"$in": ["scheduled", "in_progress", "completed"]},
            },
            {"_id": 0, "therapist_id": 1, "starts_at": 1, "ends_at": 1},
        )
    ]

    # Therapist-bazında randevu pencerelerini çıkar
    busy: dict[str, list[tuple[datetime, datetime]]] = {}
    for a in appts:
        tid = a.get("therapist_id")
        if not tid:
            continue
        try:
            s = datetime.fromisoformat(a["starts_at"])
            e = datetime.fromisoformat(a["ends_at"])
        except (KeyError, ValueError):
            continue
        if s.tzinfo is None:
            s = s.replace(tzinfo=UTC)
        if e.tzinfo is None:
            e = e.replace(tzinfo=UTC)
        busy.setdefault(tid, []).append((s, e))

    # Slot grid'i kur
    slots: list[dict[str, Any]] = []
    cur_t = base
    while cur_t < end_of_day:
        slot_end = cur_t + timedelta(minutes=duration)
        therapist_slots: list[dict[str, Any]] = []
        for t in therapists:
            tid = t["id"]
            available = True
            for bs, be in busy.get(tid, []):
                if cur_t < be and bs < slot_end:
                    available = False
                    break
            therapist_slots.append(
                {
                    "therapist_id": tid,
                    "therapist_name": t.get("name"),
                    "color": t.get("color"),
                    "available": available,
                }
            )
        slots.append(
            {
                "starts_at": cur_t.isoformat(),
                "ends_at": slot_end.isoformat(),
                "therapists": therapist_slots,
                "any_available": any(s["available"] for s in therapist_slots),
            }
        )
        cur_t += timedelta(minutes=slot_minutes)

    total_cells = len(slots) * len(therapists)
    avail_cells = sum(1 for s in slots for ts in s["therapists"] if ts["available"])
    return {
        "date": date,
        "duration_minutes": duration,
        "therapists": [{"id": t["id"], "name": t.get("name"), "color": t.get("color")} for t in therapists],
        "slots": slots,
        "stats": {
            "total_slots": len(slots),
            "any_available_slots": sum(1 for s in slots if s["any_available"]),
            "total_cells": total_cells,
            "available_cells": avail_cells,
            "utilization_pct": round((1 - avail_cells / total_cells) * 100, 1) if total_cells else 0,
        },
    }


# ── Waitlist ─────────────────────────────────────────────────────
class WaitlistEntryIn(BaseModel):
    service_id: str
    guest_name: str
    guest_phone: str | None = None
    guest_id: str | None = None
    preferred_date: str  # YYYY-MM-DD
    preferred_window: str = "any"  # any / morning / afternoon / evening
    therapist_id: str | None = None  # opsiyonel tercih
    notes: str | None = None


@router.get("/waitlist")
async def list_waitlist(
    date: str | None = Query(None),
    current_user: User = Depends(get_current_user),
) -> dict:
    db = get_system_db()
    q: dict[str, Any] = {"tenant_id": current_user.tenant_id, "status": {"$in": ["waiting", "notified"]}}
    if date:
        q["preferred_date"] = date
    cur = db.spa_waitlist.find(q, {"_id": 0}).sort("created_at", 1).limit(200)
    return {"waitlist": [d async for d in cur]}


@router.post("/waitlist")
async def add_to_waitlist(
    body: WaitlistEntryIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_spa_ops(current_user)
    db = get_system_db()
    svc = await db.spa_services.find_one({"id": body.service_id, "tenant_id": current_user.tenant_id})
    if not svc:
        raise HTTPException(404, "Hizmet bulunamadı")
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **body.model_dump(),
        "service_name": svc.get("name"),
        "duration_minutes": svc.get("duration_minutes"),
        "status": "waiting",
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.username,
    }
    await db.spa_waitlist.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/waitlist/{entry_id}")
async def remove_waitlist(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_spa_ops(current_user)
    db = get_system_db()
    res = await db.spa_waitlist.delete_one({"id": entry_id, "tenant_id": current_user.tenant_id})
    if not res.deleted_count:
        raise HTTPException(404, "Bekleme listesi kaydı bulunamadı")
    return {"ok": True}


# ── v97 architect-DL: Waitlist update (full CRUD) ──────────────
class WaitlistUpdate(BaseModel):
    status: str | None = None  # waiting / notified / fulfilled / cancelled
    preferred_window: str | None = None
    therapist_id: str | None = None
    notes: str | None = None


_WAITLIST_STATUSES = {"waiting", "notified", "fulfilled", "cancelled"}


@router.patch("/waitlist/{entry_id}")
async def update_waitlist(
    entry_id: str,
    body: WaitlistUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_spa_ops(current_user)
    db = get_system_db()
    if body.status is not None and body.status not in _WAITLIST_STATUSES:
        raise HTTPException(400, f"Geçersiz durum: {body.status}")
    update = dict(body.model_dump(exclude_none=True).items())
    if not update:
        raise HTTPException(400, "Güncellenecek alan yok")
    update["updated_at"] = datetime.now(UTC).isoformat()
    res = await db.spa_waitlist.update_one(
        {"id": entry_id, "tenant_id": current_user.tenant_id},
        {"$set": update},
    )
    if not res.matched_count:
        raise HTTPException(404, "Bekleme listesi kaydı bulunamadı")
    return {"ok": True, **update}
