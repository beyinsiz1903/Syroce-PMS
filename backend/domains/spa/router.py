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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from cache_manager import cache as _cache
from cache_manager import cached as _cached
from core.booking_atomicity import (
    is_replica_set_unavailable,
    standalone_fallback_allowed,
    with_resource_locks,
)
from core.entitlements.enforcement import get_tenant_limit, require_feature
from core.entitlements.quota import QuotaExceededException, release_quota, reserve_quota
from core.security import get_current_user
from core.spa_mice_authz import require_catalog, require_finance, require_spa_ops
from core.tenant_db import get_system_db
from models.schemas import User
from shared_kernel.idempotency import (
    claim_idempotency,
    complete_idempotency,
    get_idempotency_key,
    release_idempotency,
)

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
    price: float = Field(0, ge=0, le=1e9, allow_inf_nan=False)
    currency: str = "TRY"
    # Displayed SPA price is VAT-inclusive. None is unknown, never zero tax.
    tax_rate: float | None = Field(None, ge=0, le=1)
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
    _perm: object = None,
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
    _perm: object = None,
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
    _perm: object = None,
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
    request: Request,
    body: TherapistIn,
    current_user: User = Depends(get_current_user),
    _perm: object = None,
) -> dict:
    require_catalog(current_user)
    db = get_system_db()

    idem_key = get_idempotency_key(request)
    lock_id = None
    if idem_key:
        claim = await claim_idempotency(
            db,
            tenant_id=current_user.tenant_id,
            scope="spa_therapist_create",
            idempotency_key=idem_key,
        )
        if claim["status"] == "replay":
            return claim["response"]
        elif claim["status"] == "in_flight":
            raise HTTPException(409, "Aynı Idempotency-Key ile başka bir istek işleniyor")
        lock_id = claim["lock_id"]

    try:
        limit = await get_tenant_limit(current_user.tenant_id, "spa", "therapists")
        therapist_id = str(uuid.uuid4())

        if limit is not None:
            try:
                await reserve_quota(current_user.tenant_id, "spa", "therapists", therapist_id, limit)
            except QuotaExceededException:
                raise HTTPException(status_code=403, detail="Maksimum terapist limitine ulaştınız. Lütfen paketinizi yükseltin.")

        doc = {
            "id": therapist_id,
            "tenant_id": current_user.tenant_id,
            **body.model_dump(),
            "created_at": datetime.now(UTC).isoformat(),
        }
        try:
            await db.spa_therapists.insert_one(doc)
        except Exception:
            if limit is not None:
                await release_quota(current_user.tenant_id, "spa", "therapists", therapist_id)
            raise
        doc.pop("_id", None)

        if lock_id:
            await complete_idempotency(db, lock_id, doc)

        return doc
    except Exception:
        if lock_id:
            await release_idempotency(db, lock_id)
        raise


@router.put("/therapists/{therapist_id}")
async def update_therapist(
    therapist_id: str,
    body: TherapistIn,
    current_user: User = Depends(get_current_user),
    _perm: object = None,
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
    _perm: object = None,
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    res = await db.spa_therapists.delete_one({"id": therapist_id, "tenant_id": current_user.tenant_id})
    if res.deleted_count == 1:
        await release_quota(current_user.tenant_id, "spa", "therapists", therapist_id)
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
    request: Request,
    body: TreatmentRoomIn,
    current_user: User = Depends(get_current_user),
    _perm: object = None,
) -> dict:
    require_catalog(current_user)
    db = get_system_db()

    idem_key = get_idempotency_key(request)
    lock_id = None
    if idem_key:
        claim = await claim_idempotency(
            db,
            tenant_id=current_user.tenant_id,
            scope="spa_room_create",
            idempotency_key=idem_key,
        )
        if claim["status"] == "replay":
            return claim["response"]
        elif claim["status"] == "in_flight":
            raise HTTPException(409, "Aynı Idempotency-Key ile başka bir istek işleniyor")
        lock_id = claim["lock_id"]

    try:
        limit = await get_tenant_limit(current_user.tenant_id, "spa", "rooms")
        room_id = str(uuid.uuid4())

        if limit is not None:
            try:
                await reserve_quota(current_user.tenant_id, "spa", "rooms", room_id, limit)
            except QuotaExceededException:
                raise HTTPException(status_code=403, detail="Maksimum oda limitine ulaştınız. Lütfen paketinizi yükseltin.")

        doc = {
            "id": room_id,
            "tenant_id": current_user.tenant_id,
            **body.model_dump(),
            "created_at": datetime.now(UTC).isoformat(),
        }
        try:
            await db.spa_rooms.insert_one(doc)
        except Exception:
            if limit is not None:
                await release_quota(current_user.tenant_id, "spa", "rooms", room_id)
            raise
        doc.pop("_id", None)

        if lock_id:
            await complete_idempotency(db, lock_id, doc)

        return doc
    except Exception:
        if lock_id:
            await release_idempotency(db, lock_id)
        raise


@router.put("/rooms/{room_id}")
async def update_room(
    room_id: str,
    body: TreatmentRoomIn,
    current_user: User = Depends(get_current_user),
    _perm: object = None,
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
    _perm: object = None,
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    res = await db.spa_rooms.delete_one({"id": room_id, "tenant_id": current_user.tenant_id})
    if res.deleted_count == 1:
        await release_quota(current_user.tenant_id, "spa", "rooms", room_id)
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
    folio_id: str | None = None  # explicit target when the reservation has multiple windows
    notes: str | None = None
    charge_to_room: bool = False
    price_override: float | None = Field(None, ge=0, le=1e9, allow_inf_nan=False)


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
    _perm: object = None,
) -> dict:
    require_spa_ops(current_user)
    await _ensure_indexes()
    db = get_system_db()
    tenant_id = current_user.tenant_id

    service = await db.spa_services.find_one({"id": body.service_id, "tenant_id": tenant_id})
    if not service:
        raise HTTPException(404, "Hizmet bulunamadı")
    if body.charge_to_room:
        if not body.reservation_id:
            raise HTTPException(422, 'Odaya aktarım için otel rezervasyonu gerekli')
        booking = await db.bookings.find_one({'tenant_id': tenant_id, 'id': body.reservation_id}, {'_id': 0})
        if not booking:
            raise HTTPException(404, 'Bağlı otel rezervasyonu bulunamadı')
        if booking.get('status') not in {'confirmed', 'guaranteed', 'checked_in', 'in_house'}:
            raise HTTPException(409, 'Bu konaklamaya SPA randevusu bağlanamaz')
        if str(service.get('currency') or 'TRY').upper() != str(booking.get('currency') or 'TRY').upper():
            raise HTTPException(409, 'SPA hizmeti ve rezervasyon para birimi farklı')
        if service.get('tax_rate') is None:
            raise HTTPException(409, 'Odaya aktarım öncesi SPA hizmetinin KDV oranını tanımlayın')

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
        "tax_rate": service.get("tax_rate"),
        "guest_id": body.guest_id,
        "guest_name": body.guest_name,
        "guest_phone": body.guest_phone,
        "reservation_id": body.reservation_id,
        "folio_id": body.folio_id,
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
    _perm: object = None,
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
    from shared_kernel.audit_helper import audit_log

    tid = current_user.tenant_id

    async def transition(session):
        current = await db.spa_appointments.find_one({'id': appt_id, 'tenant_id': tid}, session=session)
        if not current:
            raise HTTPException(404, 'Randevu bulunamadı')
        old = current.get('status', 'scheduled')
        if body.status not in _SPA_TRANSITIONS.get(old, set()):
            raise HTTPException(409, f'Geçersiz geçiş: {old} → {body.status}')
        update = {'status': body.status, 'updated_at': datetime.now(UTC).isoformat()}
        posted = None
        if body.status == 'completed':
            update['completed_at'] = update['updated_at']
            if current.get('charge_to_room'):
                posted = await _post_to_folio(tid, {**current, **update}, session=session,
                    actor_id=current_user.id, actor_name=current_user.name)
                update['folio_charge_id'] = posted['charge']['id']
                update['folio_id'] = posted['charge']['folio_id']
        changed = await db.spa_appointments.update_one({'id': appt_id, 'tenant_id': tid, 'status': old}, {'$set': update}, session=session)
        if changed.modified_count != 1:
            raise HTTPException(409, 'SPA durumu eşzamanlı değişti; folyo aktarımı geri alındı')
        await audit_log(actor_id=current_user.id, tenant_id=tid, entity_type='reservation' if current.get('reservation_id') else 'spa_appointment',
            entity_id=current.get('reservation_id') or appt_id, action='spa_status_changed',
            metadata={'source_spa_appointment_id': appt_id, 'from_status': old, 'to_status': body.status,
                'reason': current.get('notes'), 'actor_name': current_user.name}, session=session, require_chain=True)
        return {'ok': True, 'status': body.status, 'posted': posted}

    result = await with_resource_locks(client=db.client, db=db, tenant_id=tid, locks_collection='spa_locks',
        resources=[('appointment', appt_id), ('booking', appt.get('reservation_id'))], callback=transition)
    if result['posted']:
        from core.report_cache import invalidate_financial_report_caches

        invalidate_financial_report_caches(tid)
        await _publish_posting(tid, result['posted'])
    return {key: value for key, value in result.items() if key != 'posted'}


# Allowed status transitions (defensive workflow guard).
_SPA_TRANSITIONS: dict[str, set[str]] = {
    "scheduled": {"in_progress", "completed", "no_show", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
    "no_show": set(),
    "cancelled": set(),
}


async def _post_to_folio(tenant_id: str, appt: dict, *, session=None, actor_id=None, actor_name=None):
    from domains.spa.folio import post_charge

    db = get_system_db()
    if session is not None:
        return await post_charge(db, tenant_id, appt, actor_id, actor_name, session=session)
    async def post(s):
        return await post_charge(db, tenant_id, appt, actor_id, actor_name, session=s)
    result = await with_resource_locks(client=db.client, db=db, tenant_id=tenant_id, locks_collection='spa_locks',
        resources=[('appointment', appt['id']), ('booking', appt.get('reservation_id'))], callback=post)
    await _publish_posting(tenant_id, result)
    return result


async def _publish_posting(tenant_id, result):
    if result.get('replayed'):
        return
    posting = result['posting']
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
    _perm: object = None,
) -> dict:
    require_spa_ops(current_user)
    db = get_system_db()
    res = await db.spa_appointments.delete_one({"id": appt_id, "tenant_id": current_user.tenant_id})
    if not res.deleted_count:
        raise HTTPException(404, "Randevu bulunamadı")
    return {"ok": True}


# ── Guest history ───────────────────────────────────────────────
@router.get("/guests/{guest_id}/history")
async def guest_history(
    guest_id: str,
    current_user: User = Depends(get_current_user),
    _feat=Depends(require_feature("spa", "guest_history")),
) -> dict:
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
    from modules.pms_core.report_money import add_amount, rounded_totals, single_amount
    from modules.pms_core.report_period import day_bounds, hotel_zone, instant_between, local_today, parse_day

    db = get_system_db()
    # The hotel's local calendar day; ISO-text and BSON start times both count.
    zone = await hotel_zone(db, current_user.tenant_id)
    day = parse_day(date, "date") if date else local_today(zone, datetime.now(UTC))
    lower, upper = day_bounds(day, day, zone)
    cur = db.spa_appointments.find(
        {"tenant_id": current_user.tenant_id, **instant_between("starts_at", lower, upper)},
        {"_id": 0},
    )
    items = [d async for d in cur]
    by_status: dict[str, int] = {}
    completed = {a['id']: a for a in items if a.get('status') == 'completed'}
    revenue: dict = {}
    catalog_value: dict = {}
    complimentary: dict = {}
    unposted_value: dict = {}
    unposted_count = 0
    charges = await db.folio_charges.find({'tenant_id': current_user.tenant_id,
        'source_spa_appointment_id': {'$in': list(completed)}}, {'_id': 0}).to_list(None) if completed else []
    known_sources = {row['source_spa_appointment_id'] for row in charges}
    # Include transferred parts (same source appointment, other room), but
    # never count a voided charge or substitute its original catalog price.
    for row in charges:
        if row.get('voided'):
            continue
        appt = completed[row['source_spa_appointment_id']]
        code = row.get('currency') or appt.get('currency') or 'TRY'
        add_amount(revenue, code, row['total'])
        if row.get('is_complimentary'):
            add_amount(complimentary, code, row.get('complimentary_original_amount') or 0)
    for a in items:
        status = a.get("status") or "unknown"
        by_status[status] = by_status.get(status, 0) + 1
        if status == "completed":
            add_amount(catalog_value, a.get('currency') or 'TRY', a.get('price') or 0)
            if a['id'] not in known_sources:
                unposted_count += 1
                add_amount(unposted_value, a.get('currency') or 'TRY', a.get('price') or 0)
    by_currency = rounded_totals(revenue)
    return {
        "date": day.isoformat(),
        "timezone": str(zone),
        "total": len(items),
        "by_status": by_status,
        # Per currency, never added across currencies; the scalar only when
        # every completed appointment is in one currency (else null).
        "revenue_by_currency": by_currency,
        "revenue": single_amount(revenue),
        'revenue_basis': 'active_folio_charges_for_completed_appointments',
        'catalog_value_by_currency': rounded_totals(catalog_value),
        'complimentary_value_by_currency': rounded_totals(complimentary),
        'unposted_value_by_currency': rounded_totals(unposted_value),
        'unposted_appointments': unposted_count,
        'revenue_complete': unposted_count == 0,
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
    _feat=Depends(require_feature("spa", "advanced_availability")),
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
    _feat=Depends(require_feature("spa", "advanced_availability")),
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
    _perm: object = None,
    _feat=Depends(require_feature("spa", "advanced_availability")),
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
    _perm: object = None,
    _feat=Depends(require_feature("spa", "advanced_availability")),
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
    _perm: object = None,
    _feat=Depends(require_feature("spa", "advanced_availability")),
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
