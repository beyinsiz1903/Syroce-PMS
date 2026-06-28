"""Golf module — courses, tee-times, players, bookings, scoring.

Mirrors the Spa module's resource-scheduling pattern:
* Course catalog (par, holes, slope/rating, hole-by-hole length)
* Tee-time grid (configurable interval) with capacity per slot
* Player roster (handicaps, member tier)
* Conflict-checked tee bookings (slot capacity + duplicate-player guard)
* Folio charge integration (charge-to-room when guest is staying)
* Daily summary for ops dashboard

Atomic-by-design via spa-style per-resource lock.
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
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/golf", tags=["golf"])

_indexes_ready = False


async def _ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    db = get_system_db()
    try:
        await db.golf_tee_bookings.create_index([("tenant_id", 1), ("course_id", 1), ("tee_time", 1)], name="golf_book_course_time")
        await db.golf_tee_bookings.create_index([("tenant_id", 1), ("guest_id", 1), ("tee_time", -1)], name="golf_book_guest_time")
        await db.golf_tee_bookings.create_index([("tenant_id", 1), ("status", 1), ("tee_time", 1)], name="golf_book_status_time")
        await db.golf_courses.create_index([("tenant_id", 1), ("active", 1)])
        await db.golf_players.create_index([("tenant_id", 1), ("guest_id", 1)], name="golf_player_guest")
        await db.golf_locks.create_index([("tenant_id", 1), ("kind", 1), ("resource_id", 1)], unique=True, name="uniq_golf_lock")
        _indexes_ready = True
    except Exception as exc:
        import logging

        logging.getLogger("golf").warning("Index creation deferred: %s", exc)


# ─── Courses ────────────────────────────────────────────────────
class CourseIn(BaseModel):
    name: str
    holes: int = Field(18, ge=9, le=36)
    par: int = Field(72, ge=27, le=144)
    course_rating: float = Field(72.0, ge=50, le=85)
    slope_rating: int = Field(113, ge=55, le=155)
    tee_interval_minutes: int = Field(10, ge=5, le=30)
    slot_capacity: int = Field(4, ge=1, le=8)  # players per tee
    open_time: str = "07:00"
    close_time: str = "18:00"
    green_fee: float = Field(0, ge=0)
    cart_fee: float = Field(0, ge=0)
    currency: str = "TRY"
    description: str | None = None
    active: bool = True


def _invalidate_courses_cache(tenant_id: str) -> None:
    _cache.safe_invalidate(tenant_id, "golf_courses")


@router.get("/courses")
@_cached(ttl=300, key_prefix="golf_courses")
async def list_courses(current_user: User = Depends(get_current_user)) -> dict:
    await _ensure_indexes()
    db = get_system_db()
    cur = db.golf_courses.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).sort("name", 1)
    items = [d async for d in cur]
    if not items:
        try:
            require_catalog(current_user)
        except HTTPException:
            return {"courses": []}
        items = await _seed_default_course(current_user.tenant_id)
    return {"courses": items}


async def _seed_default_course(tenant_id: str) -> list[dict]:
    db = get_system_db()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "name": "Resort Championship Course",
        "holes": 18,
        "par": 72,
        "course_rating": 72.4,
        "slope_rating": 132,
        "tee_interval_minutes": 10,
        "slot_capacity": 4,
        "open_time": "07:00",
        "close_time": "18:00",
        "green_fee": 1800,
        "cart_fee": 600,
        "currency": "TRY",
        "description": "Resort üzerindeki şampiyona kursu",
        "active": True,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.golf_courses.insert_one(doc)
    doc.pop("_id", None)
    return [doc]


@router.post("/courses")
async def create_course(
    body: CourseIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **body.model_dump(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.golf_courses.insert_one(doc)
    doc.pop("_id", None)
    _invalidate_courses_cache(current_user.tenant_id)
    return doc


@router.put("/courses/{course_id}")
async def update_course(
    course_id: str,
    body: CourseIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    res = await db.golf_courses.update_one(
        {"id": course_id, "tenant_id": current_user.tenant_id},
        {"$set": {**body.model_dump(), "updated_at": datetime.now(UTC).isoformat()}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Kurs bulunamadı")
    _invalidate_courses_cache(current_user.tenant_id)
    return {"ok": True}


@router.delete("/courses/{course_id}")
async def delete_course(
    course_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    res = await db.golf_courses.delete_one({"id": course_id, "tenant_id": current_user.tenant_id})
    if not res.deleted_count:
        raise HTTPException(404, "Kurs bulunamadı")
    _invalidate_courses_cache(current_user.tenant_id)
    return {"ok": True}


# ─── Players ────────────────────────────────────────────────────
class PlayerIn(BaseModel):
    name: str
    guest_id: str | None = None
    handicap: float = Field(28.0, ge=-10, le=54)
    member_tier: str = "guest"  # guest / member / vip / pro
    phone: str | None = None
    email: str | None = None


@router.get("/players")
async def list_players(
    q: str | None = Query(None, max_length=100),
    current_user: User = Depends(get_current_user),
) -> dict:
    db = get_system_db()
    filt: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    if q and len(q) >= 2:
        import re as _re

        rx = {"$regex": _re.escape(q), "$options": "i"}
        filt["$or"] = [{"name": rx}, {"email": rx}, {"phone": rx}]
    cur = db.golf_players.find(filt, {"_id": 0}).sort("name", 1).limit(200)
    return {"players": [d async for d in cur]}


@router.post("/players")
async def create_player(
    body: PlayerIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **body.model_dump(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.golf_players.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/players/{player_id}")
async def update_player(
    player_id: str,
    body: PlayerIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_catalog(current_user)
    db = get_system_db()
    res = await db.golf_players.update_one(
        {"id": player_id, "tenant_id": current_user.tenant_id},
        {"$set": body.model_dump()},
    )
    if not res.matched_count:
        raise HTTPException(404, "Oyuncu bulunamadı")
    return {"ok": True}


# ─── Tee sheet (availability grid) ──────────────────────────────
@router.get("/tee-sheet")
async def tee_sheet(
    course_id: str = Query(...),
    date: str = Query(..., description="YYYY-MM-DD"),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return all tee slots for a course on a date with current bookings.

    Slot capacity comes from the course; a slot with N players where N >=
    capacity is full. Front-end renders this as a grid (hour x slot).
    """
    db = get_system_db()
    course = await db.golf_courses.find_one({"id": course_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not course:
        raise HTTPException(404, "Kurs bulunamadı")

    try:
        day = datetime.fromisoformat(date).date()
    except ValueError:
        raise HTTPException(400, "Geçersiz tarih (YYYY-MM-DD bekleniyor)")

    open_h, open_m = (int(x) for x in course["open_time"].split(":"))
    close_h, close_m = (int(x) for x in course["close_time"].split(":"))
    interval = int(course["tee_interval_minutes"])
    capacity = int(course["slot_capacity"])

    slot_start = datetime.combine(day, datetime.min.time()).replace(hour=open_h, minute=open_m, tzinfo=UTC)
    slot_end_day = datetime.combine(day, datetime.min.time()).replace(hour=close_h, minute=close_m, tzinfo=UTC)

    slots: list[dict[str, Any]] = []
    cur_t = slot_start
    while cur_t < slot_end_day:
        slots.append(
            {
                "tee_time": cur_t.isoformat(),
                "capacity": capacity,
                "booked": 0,
                "bookings": [],
            }
        )
        cur_t += timedelta(minutes=interval)

    by_time = {s["tee_time"]: s for s in slots}

    cur = db.golf_tee_bookings.find(
        {
            "tenant_id": current_user.tenant_id,
            "course_id": course_id,
            "tee_time": {"$gte": slot_start.isoformat(), "$lt": slot_end_day.isoformat()},
            "status": {"$in": ["confirmed", "checked_in", "completed"]},
        },
        {"_id": 0},
    )
    async for b in cur:
        slot = by_time.get(b.get("tee_time"))
        if slot:
            slot["booked"] += int(b.get("party_size", 1))
            slot["bookings"].append(
                {
                    "id": b.get("id"),
                    "lead_player": b.get("lead_player"),
                    "party_size": b.get("party_size", 1),
                    "status": b.get("status"),
                }
            )

    full_count = sum(1 for s in slots if s["booked"] >= s["capacity"])
    return {
        "course": {"id": course_id, "name": course["name"], "tee_interval": interval, "capacity": capacity},
        "date": date,
        "slots": slots,
        "stats": {
            "total_slots": len(slots),
            "full_slots": full_count,
            "available_slots": len(slots) - full_count,
            "utilization_pct": round(full_count / len(slots) * 100, 1) if slots else 0,
        },
    }


# ─── Tee-time bookings ──────────────────────────────────────────
class TeeBookingIn(BaseModel):
    course_id: str
    tee_time: datetime
    lead_player: str
    party_size: int = Field(1, ge=1, le=8)
    player_ids: list[str] = Field(default_factory=list)
    guest_id: str | None = None  # PMS guest if hotel-staying
    reservation_id: str | None = None
    cart_count: int = Field(0, ge=0, le=4)
    notes: str | None = None
    charge_to_room: bool = False
    price_override: float | None = None


def _round_to_slot(dt: datetime, interval_min: int) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    minute = (dt.minute // interval_min) * interval_min
    return dt.replace(minute=minute, second=0, microsecond=0)


@router.get("/bookings")
async def list_bookings(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    course_id: str | None = Query(None),
    status: str | None = Query(None),
    current_user: User = Depends(get_current_user),
) -> dict:
    db = get_system_db()
    q: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    if course_id:
        q["course_id"] = course_id
    if status:
        q["status"] = status
    if date_from or date_to:
        rng: dict[str, Any] = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        q["tee_time"] = rng
    cur = db.golf_tee_bookings.find(q, {"_id": 0}).sort("tee_time", 1).limit(500)
    return {"bookings": [d async for d in cur]}


async def _slot_has_capacity(tenant_id: str, course_id: str, tee_time_iso: str, party_size: int, capacity: int, exclude_id: str | None = None, session=None) -> tuple[bool, int]:
    db = get_system_db()
    q: dict[str, Any] = {
        "tenant_id": tenant_id,
        "course_id": course_id,
        "tee_time": tee_time_iso,
        "status": {"$in": ["confirmed", "checked_in", "completed"]},
    }
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    booked = 0
    async for d in db.golf_tee_bookings.find(q, {"party_size": 1}, session=session):
        booked += int(d.get("party_size", 1))
    return (booked + party_size <= capacity), booked


async def _player_double_booked(
    tenant_id: str,
    tee_time_iso: str,
    player_ids: list[str],
    guest_id: str | None,
    exclude_id: str | None = None,
    session=None,
) -> str | None:
    """Aynı oyuncu / aynı PMS misafirinin aynı tee saatinde başka bir
    rezervasyonda olmadığından emin ol. Çakışma varsa açıklayıcı
    mesaj döner; aksi halde None.
    """
    db = get_system_db()
    or_clauses: list[dict[str, Any]] = []
    if player_ids:
        or_clauses.append({"player_ids": {"$in": player_ids}})
    if guest_id:
        or_clauses.append({"guest_id": guest_id})
    if not or_clauses:
        return None
    q: dict[str, Any] = {
        "tenant_id": tenant_id,
        "tee_time": tee_time_iso,
        "status": {"$in": ["confirmed", "checked_in", "completed"]},
        "$or": or_clauses,
    }
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    doc = await db.golf_tee_bookings.find_one(q, session=session)
    if not doc:
        return None
    return f"Oyuncu çakışması: {doc.get('lead_player') or guest_id} aynı tee saatinde başka bir rezervasyonda ({doc.get('course_name')})"


@router.post("/bookings")
async def create_booking(
    body: TeeBookingIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_spa_ops(current_user)
    await _ensure_indexes()
    db = get_system_db()
    tenant_id = current_user.tenant_id

    course = await db.golf_courses.find_one({"id": body.course_id, "tenant_id": tenant_id})
    if not course:
        raise HTTPException(404, "Kurs bulunamadı")

    interval = int(course["tee_interval_minutes"])
    capacity = int(course["slot_capacity"])

    tee = _round_to_slot(body.tee_time, interval)
    tee_iso = tee.isoformat()

    booking = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "course_id": body.course_id,
        "course_name": course["name"],
        "tee_time": tee_iso,
        "lead_player": body.lead_player,
        "party_size": body.party_size,
        "player_ids": body.player_ids,
        "cart_count": body.cart_count,
        "guest_id": body.guest_id,
        "reservation_id": body.reservation_id,
        "notes": body.notes,
        "charge_to_room": body.charge_to_room,
        "price": (body.price_override if body.price_override is not None else (course.get("green_fee", 0) * body.party_size + course.get("cart_fee", 0) * body.cart_count)),
        "currency": course.get("currency", "TRY"),
        "status": "confirmed",
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.username,
    }

    async def _do_insert(session) -> dict:
        ok, booked_now = await _slot_has_capacity(
            tenant_id,
            body.course_id,
            tee_iso,
            body.party_size,
            capacity,
            session=session,
        )
        if not ok:
            raise HTTPException(409, f"Tee slot dolu ({booked_now}/{capacity} oyuncu kayıtlı)")
        # Aynı oyuncu/misafir aynı saatte başka bir bookingda mı?
        clash = await _player_double_booked(
            tenant_id,
            tee_iso,
            body.player_ids,
            body.guest_id,
            session=session,
        )
        if clash:
            raise HTTPException(409, clash)
        await db.golf_tee_bookings.insert_one(booking, session=session)
        return booking

    # Lock per (course, tee-time) to serialize concurrent bookings
    try:
        await with_resource_locks(
            client=db.client,
            db=db,
            tenant_id=tenant_id,
            locks_collection="golf_locks",
            resources=[("tee_slot", f"{body.course_id}:{tee_iso}")],
            callback=_do_insert,
        )
    except HTTPException:
        raise
    except Exception as exc:
        if not is_replica_set_unavailable(exc):
            raise
        if not standalone_fallback_allowed():
            raise HTTPException(
                status_code=503,
                detail=("Golf rezervasyon servisi şu anda atomik garanti sağlayamıyor (Mongo replica set gerekli)."),
            )
        ok, booked_now = await _slot_has_capacity(tenant_id, body.course_id, tee_iso, body.party_size, capacity)
        if not ok:
            raise HTTPException(409, f"Tee slot dolu ({booked_now}/{capacity} oyuncu kayıtlı)")
        clash = await _player_double_booked(
            tenant_id,
            tee_iso,
            body.player_ids,
            body.guest_id,
        )
        if clash:
            raise HTTPException(409, clash)
        await db.golf_tee_bookings.insert_one(booking)

    booking.pop("_id", None)
    return booking


class GolfStatusUpdate(BaseModel):
    status: str  # confirmed / checked_in / completed / no_show / cancelled


_GOLF_TRANSITIONS: dict[str, set[str]] = {
    "confirmed": {"checked_in", "no_show", "cancelled"},
    "checked_in": {"completed", "cancelled"},
    "completed": set(),
    "no_show": set(),
    "cancelled": set(),
}


@router.post("/bookings/{booking_id}/status")
async def change_booking_status(
    booking_id: str,
    body: GolfStatusUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_spa_ops(current_user)
    if body.status == "completed":
        require_finance(current_user)  # folio-impacting
    db = get_system_db()
    bk = await db.golf_tee_bookings.find_one({"id": booking_id, "tenant_id": current_user.tenant_id})
    if not bk:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    cur_status = bk.get("status", "confirmed")
    if body.status not in _GOLF_TRANSITIONS.get(cur_status, set()):
        raise HTTPException(409, f"Geçersiz geçiş: {cur_status} → {body.status}")

    update = {"status": body.status, "updated_at": datetime.now(UTC).isoformat()}
    if body.status == "checked_in":
        update["checked_in_at"] = datetime.now(UTC).isoformat()
    if body.status == "completed":
        update["completed_at"] = datetime.now(UTC).isoformat()

    # Atomic CAS claim FIRST: only the request that flips the status from the
    # observed value runs the folio side effect, so a concurrent transition
    # never leaves a charge attached to a non-completed record.
    res = await db.golf_tee_bookings.update_one(
        {"id": booking_id, "tenant_id": current_user.tenant_id, "status": cur_status},
        {"$set": update},
    )
    if res.modified_count == 0:
        latest = await db.golf_tee_bookings.find_one({"id": booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
        return {"ok": True, "status": latest.get("status") if latest else body.status, "idempotent": True}
    # We won the transition → run the folio side effect (idempotent via the
    # dedup index). If it fails, revert the completion so it cannot stand
    # without its charge (fail-closed).
    if body.status == "completed" and bk.get("charge_to_room") and bk.get("reservation_id"):
        try:
            await _post_to_folio(current_user.tenant_id, bk)
        except Exception:
            await db.golf_tee_bookings.update_one(
                {"id": booking_id, "tenant_id": current_user.tenant_id, "status": "completed"},
                {"$set": {"status": cur_status, "updated_at": datetime.now(UTC).isoformat()}, "$unset": {"completed_at": ""}},
            )
            raise
    return {"ok": True, "status": body.status}


@router.delete("/bookings/{booking_id}")
async def delete_booking(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_spa_ops(current_user)
    db = get_system_db()
    res = await db.golf_tee_bookings.delete_one({"id": booking_id, "tenant_id": current_user.tenant_id})
    if not res.deleted_count:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    return {"ok": True}


async def _post_to_folio(tenant_id: str, bk: dict) -> None:
    """Write a folio posting (idempotent) and emit Xchange POSTING_CHARGE.

    Dedup: a unique partial index on ``(tenant_id, dedup_key)`` makes the
    posting insert idempotent per booking — a concurrent/retry "completed"
    transition hits ``DuplicateKeyError`` → no double charge and no
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
        "reservation_id": bk.get("reservation_id"),
        "folio_id": bk.get("reservation_id"),
        "transaction_code": "GOLF",
        "description": f"Golf: {bk.get('course_name')} ({bk.get('party_size')} oyuncu)",
        "amount": float(bk.get("price", 0)),
        "currency": bk.get("currency", "TRY"),
        "posting_type": "CHARGE",
        "posted_at": datetime.now(UTC).isoformat(),
        "source": "golf_module",
        "reference": bk.get("id"),
        "dedup_key": f"golf_module:{bk.get('id')}",
    }
    try:
        await db.folio_postings.insert_one(posting)
    except DuplicateKeyError:
        # Already posted for this booking → idempotent no-op; do not
        # re-publish the Xchange event.
        return
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
                "transaction_code": "GOLF",
                "description": posting["description"],
                "amount": posting["amount"],
                "currency": posting["currency"],
                "posted_at": posting["posted_at"],
            },
            message_id=f"golf-{posting['id']}",
        )
    except Exception as exc:
        import logging

        logging.getLogger("golf").warning("Xchange POSTING_CHARGE publish failed (best-effort): %s", exc)


# ─── Daily summary ──────────────────────────────────────────────
@router.get("/daily-summary")
async def daily_summary(
    date: str | None = Query(None),
    current_user: User = Depends(get_current_user),
) -> dict:
    db = get_system_db()
    target = date or datetime.now(UTC).date().isoformat()
    next_day = (datetime.fromisoformat(target) + timedelta(days=1)).date().isoformat()
    cur = db.golf_tee_bookings.find(
        {
            "tenant_id": current_user.tenant_id,
            "tee_time": {"$gte": target, "$lt": next_day},
        },
        {"_id": 0},
    )
    items = [d async for d in cur]
    by_status: dict[str, int] = {}
    revenue = 0.0
    rounds_played = 0
    for b in items:
        by_status[b["status"]] = by_status.get(b["status"], 0) + 1
        if b["status"] == "completed":
            revenue += float(b.get("price", 0))
            rounds_played += int(b.get("party_size", 1))
    return {
        "date": target,
        "total": len(items),
        "rounds_played": rounds_played,
        "by_status": by_status,
        "revenue": round(revenue, 2),
    }


# ── v97 architect-DL: Explicit folio-post endpoint ─────────────
# Status='completed' geçişinde dahili _post_to_folio çağrılır; ancak
# operatör elle bir bookingı folyoya basmak isteyebilir (örn. paket
# satışı, geç ücretlendirme). Bu uç idempotent: aynı booking için
# ikinci posting reddedilir.
class FolioPostIn(BaseModel):
    amount_override: float | None = None


@router.post("/bookings/{booking_id}/folio-post")
async def post_booking_to_folio(
    booking_id: str,
    body: FolioPostIn = FolioPostIn(),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
) -> dict:
    require_finance(current_user)  # folio-impacting
    db = get_system_db()
    bk = await db.golf_tee_bookings.find_one({"id": booking_id, "tenant_id": current_user.tenant_id})
    if not bk:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    if not bk.get("reservation_id"):
        raise HTTPException(400, "Rezervasyon bir oda hesabına bağlı değil")

    # Idempotency — aynı booking için folyoda posting var mı?
    existing = await db.folio_postings.find_one(
        {
            "tenant_id": current_user.tenant_id,
            "reference": booking_id,
            "transaction_code": "GOLF",
        }
    )
    if existing:
        raise HTTPException(409, "Bu rezervasyon için folyo postingi zaten mevcut")

    if body.amount_override is not None:
        bk = {**bk, "price": body.amount_override}
    await _post_to_folio(current_user.tenant_id, bk)
    await db.golf_tee_bookings.update_one(
        {"id": booking_id, "tenant_id": current_user.tenant_id},
        {"$set": {"folio_posted_at": datetime.now(UTC).isoformat()}},
    )
    return {"ok": True, "amount": float(bk.get("price", 0)), "currency": bk.get("currency", "TRY")}
