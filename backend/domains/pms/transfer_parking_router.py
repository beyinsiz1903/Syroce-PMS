"""
PMS / Transfer & Otopark — Kaynak Rezervasyonu → Folio
======================================================
Araç (transfer) ve park yeri (otopark) gibi sınırlı kaynakların çift-rezervasyon
korumalı planlanması + minibar deseniyle idempotent folio faturalaması.

Tasarım:
  1. Çift-rezervasyon kilidi: her dolu zaman dilimi için `transport_slot_locks`
     koleksiyonunda (tenant_id, resource_id, slot_key) UNIQUE bir doküman tutulur
     (room_night_locks deseni). Rezervasyon tüm dilimlerini sırayla claim eder;
     herhangi biri DuplicateKey verirse claim edilenler geri alınır ve 409 döner.
     UNIQUE index garantisi sayesinde iki rezervasyon asla aynı dilimi tutamaz.
  2. Folio: minibar (core.pos_folio_consumer) deseni — dedup
     (tenant_id, source_transport_booking_id, line_no) + ledger recalc (ASLA
     $inc). Açık guest folio yoksa kapalıya yazılmaz; görünür
     `transport_late_charges` kaydına yönlendirilir (fail-closed). Kaynak yine de
     rezerve kalır.
  3. İptal: dilim kilitleri serbest bırakılır, rezervasyon `cancelled` olur.

Tüm uçlar tenant-scoped; mutasyonlar RBAC ile sınırlı. PII/secret loglanmaz.
"""
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from core.database import db
from core.pos_folio_consumer import _recalc_folio_balance
from core.security import get_current_user
from domains.pms.pos_extensions._idem import ensure_compound_unique
from models.schemas import User

logger = logging.getLogger("domains.pms.transfer_parking")

router = APIRouter(prefix="/api/transfer-parking", tags=["PMS / Transfer & Parking"])

_BOOK_ROLES = {
    "super_admin", "admin", "supervisor", "front_desk", "concierge", "staff",
}
_CATALOG_ROLES = {"super_admin", "admin", "supervisor"}

_LATE_CHARGE_COLLECTION = "transport_late_charges"

_KIND_TRANSFER = "transfer_vehicle"
_KIND_PARKING = "parking_spot"
_VALID_KINDS = {_KIND_TRANSFER, _KIND_PARKING}

# Deterministik (stabil) booking id türetmek için sabit namespace (idempotency).
_TRANSPORT_NS = uuid.UUID("9c2e7b14-3a8d-4f60-bd21-000000000000")


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


def _stable_booking_id(tenant_id: str, idempotency_key: str) -> str:
    return str(uuid.uuid5(_TRANSPORT_NS, f"{tenant_id}:{idempotency_key}"))


async def _ensure_slot_lock_index() -> None:
    await ensure_compound_unique(
        db.transport_slot_locks,
        [("tenant_id", 1), ("resource_id", 1), ("slot_key", 1)],
        name="ux_transport_slot_locks",
    )


async def _ensure_charge_index() -> None:
    await ensure_compound_unique(
        db.folio_charges,
        [("tenant_id", 1), ("source_transport_booking_id", 1), ("line_no", 1)],
        partial_filter={"source_transport_booking_id": {"$type": "string"}},
        name="ux_folio_charges_transport_source",
    )


async def _find_active_booking_by_room_number(tenant_id: str, room_number: str) -> dict | None:
    if not room_number:
        return None
    room = await db.rooms.find_one(
        {"tenant_id": tenant_id, "room_number": str(room_number).strip()}
    )
    if not room:
        return None
    return await db.bookings.find_one({
        "tenant_id": tenant_id,
        "room_id": room.get("id"),
        "status": {"$in": ["checked_in", "in_house"]},
    })


# ─────────────────────────────────────────────────────────────────────
# Katalog — kaynaklar (araç / park yeri)
# ─────────────────────────────────────────────────────────────────────
class ResourceIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    kind: str = Field(..., max_length=30)
    price: float = Field(..., ge=0)
    capacity: int = Field(1, ge=1, le=999)
    active: bool = True


class ResourceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    price: float | None = Field(None, ge=0)
    capacity: int | None = Field(None, ge=1, le=999)
    active: bool | None = None


@router.get("/resources")
async def list_resources(
    kind: str | None = Query(None),
    include_inactive: bool = Query(True),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if kind:
        q["kind"] = kind
    if not include_inactive:
        q["active"] = True
    rows = await db.transport_resources.find(q, {"_id": 0}).sort("name", 1).to_list(1000)
    return {"resources": rows}


@router.post("/resources")
async def create_resource(
    payload: ResourceIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _CATALOG_ROLES)
    tenant_id = _tenant_of(current_user)
    if payload.kind not in _VALID_KINDS:
        raise HTTPException(status_code=400, detail="Geçersiz kaynak tipi")
    now = _now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "name": payload.name.strip(),
        "kind": payload.kind,
        "price": round(float(payload.price), 2),
        "capacity": payload.capacity,
        "active": payload.active,
        "created_at": now,
        "updated_at": now,
        "created_by": _actor_id(current_user),
    }
    await db.transport_resources.insert_one(dict(doc))
    return {"resource": _serialize(doc)}


@router.put("/resources/{resource_id}")
async def update_resource(
    resource_id: str,
    payload: ResourceUpdate,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _CATALOG_ROLES)
    tenant_id = _tenant_of(current_user)
    updates = dict(payload.model_dump(exclude_unset=True))
    if "name" in updates and updates["name"]:
        updates["name"] = updates["name"].strip()
    if "price" in updates and updates["price"] is not None:
        updates["price"] = round(float(updates["price"]), 2)
    if not updates:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")
    updates["updated_at"] = _now_iso()
    res = await db.transport_resources.update_one(
        {"id": resource_id, "tenant_id": tenant_id}, {"$set": updates}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Kaynak bulunamadı")
    doc = await db.transport_resources.find_one(
        {"id": resource_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    return {"resource": doc}


@router.delete("/resources/{resource_id}")
async def deactivate_resource(
    resource_id: str,
    current_user: User = Depends(get_current_user),
):
    """Soft-delete: kaynağı pasifleştirir (geçmiş rezervasyon referansları korunur)."""
    _require_role(current_user, _CATALOG_ROLES)
    tenant_id = _tenant_of(current_user)
    res = await db.transport_resources.update_one(
        {"id": resource_id, "tenant_id": tenant_id},
        {"$set": {"active": False, "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Kaynak bulunamadı")
    return {"ok": True, "id": resource_id}


# ─────────────────────────────────────────────────────────────────────
# Rezervasyon → folio
# ─────────────────────────────────────────────────────────────────────
class BookingIn(BaseModel):
    resource_id: str = Field(..., min_length=1)
    guest_name: str | None = Field(None, max_length=200)
    room_number: str | None = Field(None, max_length=40)
    booking_id: str | None = Field(None, max_length=64)
    # Otopark: başlangıç günü + gün sayısı.
    start_date: str | None = Field(None, max_length=10)  # YYYY-MM-DD
    num_days: int | None = Field(None, ge=1, le=365)
    # Transfer: tek sefer kalkış zamanı.
    pickup_at: datetime | None = None
    note: str | None = Field(None, max_length=500)
    idempotency_key: str | None = Field(None, max_length=80)


def _compute_slots(resource: dict, payload: BookingIn) -> tuple[list[str], float, dict]:
    """Kaynak tipine göre dolu zaman dilimlerini + toplam tutarı hesaplar."""
    kind = resource.get("kind")
    unit_price = round(float(resource.get("price", 0)), 2)
    if kind == _KIND_PARKING:
        if not payload.start_date or not payload.num_days:
            raise HTTPException(status_code=400, detail="Otopark için başlangıç günü ve gün sayısı gerekli")
        try:
            start = date.fromisoformat(payload.start_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Geçersiz tarih (YYYY-MM-DD)") from exc
        slots = [f"D:{(start + timedelta(days=i)).isoformat()}" for i in range(payload.num_days)]
        total = round(unit_price * payload.num_days, 2)
        sched = {"start_date": start.isoformat(), "num_days": payload.num_days,
                 "end_date": (start + timedelta(days=payload.num_days - 1)).isoformat()}
        return slots, total, sched
    if kind == _KIND_TRANSFER:
        if not payload.pickup_at:
            raise HTTPException(status_code=400, detail="Transfer için kalkış zamanı gerekli")
        pickup = payload.pickup_at if payload.pickup_at.tzinfo else payload.pickup_at.replace(tzinfo=UTC)
        # Saat kovasına yuvarla (aynı araç aynı saat diliminde tek sefer).
        bucket = pickup.replace(minute=0, second=0, microsecond=0)
        slots = [f"T:{bucket.isoformat()}"]
        total = unit_price
        sched = {"pickup_at": pickup.isoformat()}
        return slots, total, sched
    raise HTTPException(status_code=400, detail="Geçersiz kaynak tipi")


@router.get("/bookings")
async def list_bookings(
    resource_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if resource_id:
        q["resource_id"] = resource_id
    if status and status != "all":
        q["status"] = status
    rows = await db.transport_bookings.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"bookings": rows}


async def _claim_slots(tenant_id: str, resource_id: str, booking_id: str, slots: list[str]) -> None:
    """Tüm dilimleri atomik claim eder; çakışma → claim edilenleri geri al + 409."""
    claimed: list[str] = []
    now = _now_iso()
    for slot_key in slots:
        try:
            await db.transport_slot_locks.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "resource_id": resource_id,
                "slot_key": slot_key,
                "booking_id": booking_id,
                "created_at": now,
            })
            claimed.append(slot_key)
        except DuplicateKeyError:
            # Rollback: bu rezervasyonun şimdiye dek aldığı kilitleri serbest bırak.
            for done in claimed:
                await db.transport_slot_locks.delete_one(
                    {"tenant_id": tenant_id, "resource_id": resource_id,
                     "slot_key": done, "booking_id": booking_id}
                )
            raise HTTPException(
                status_code=409,
                detail=f"Bu kaynak seçilen zaman diliminde dolu ({slot_key})",
            )


async def _post_booking_to_folio(
    tenant_id: str, actor: str, booking_doc: dict
) -> dict:
    """Rezervasyonu açık guest folio'ya idempotent yazar (tek satır)."""
    booking_id = booking_doc.get("booking_id")
    pms_booking = None
    if not booking_id:
        pms_booking = await _find_active_booking_by_room_number(
            tenant_id, booking_doc.get("room_number", "")
        )
        booking_id = pms_booking.get("id") if pms_booking else None

    if not booking_id:
        return {"charged": False, "reason": "no_active_booking_or_folio"}

    open_folio = await db.folios.find_one(
        {"booking_id": booking_id, "folio_type": "guest", "status": "open", "tenant_id": tenant_id}
    )

    # Sessiz degrade YOK: index kurulamazsa yükselt (çağıran rezervasyonu hiç
    # başlatmamış olur — pre-claim gate ile fail-closed).
    try:
        await _ensure_charge_index()
    except Exception as exc:  # noqa: BLE001
        logger.warning("transport charge index ensure başarısız: %r", exc)
        raise HTTPException(
            status_code=503,
            detail="Faturalama geçici olarak kullanılamıyor (index), tekrar deneyin",
        ) from exc

    src_id = booking_doc["id"]
    total = round(float(booking_doc.get("total", 0)), 2)
    label = "Transfer" if booking_doc.get("kind") == _KIND_TRANSFER else "Otopark"
    now = _now_iso()

    if open_folio:
        folio_id = open_folio["id"]
        guest_id = open_folio.get("guest_id") or (pms_booking.get("guest_id") if pms_booking else None)
        charge_doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "folio_id": folio_id,
            "guest_id": guest_id,
            "charge_type": booking_doc.get("kind"),
            "charge_category": "transfer" if booking_doc.get("kind") == _KIND_TRANSFER else "parking",
            "description": f"{label} - {booking_doc.get('resource_name')}",
            "amount": total,
            "tax_amount": 0,
            "total": total,
            "voided": False,
            "date": now,
            "posted_by": actor,
            "created_at": now,
            "source_transport_booking_id": src_id,
            "line_no": 0,
        }
        charged = True
        try:
            await db.folio_charges.insert_one(dict(charge_doc))
        except DuplicateKeyError:
            # Zaten yazılmış — idempotent.
            charged = True
        balance = await _recalc_folio_balance(db, tenant_id, folio_id)
        return {"charged": charged, "amount": total, "folio_id": folio_id, "balance": balance}

    # Açık folio yok → late-charge.
    any_folio = await db.folios.find_one(
        {"booking_id": booking_id, "folio_type": "guest", "tenant_id": tenant_id},
        sort=[("created_at", -1)],
    )
    await db[_LATE_CHARGE_COLLECTION].update_one(
        {"tenant_id": tenant_id, "source_transport_booking_id": src_id},
        {
            "$set": {
                "tenant_id": tenant_id,
                "source_transport_booking_id": src_id,
                "kind": booking_doc.get("kind"),
                "resource_id": booking_doc.get("resource_id"),
                "resource_name": booking_doc.get("resource_name"),
                "room_number": booking_doc.get("room_number"),
                "booking_id": booking_id,
                "guest_id": pms_booking.get("guest_id") if pms_booking else None,
                "folio_id": any_folio.get("id") if any_folio else None,
                "folio_status_at_apply": any_folio.get("status") if any_folio else "missing",
                "total": total,
                "status": "pending_review",
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    logger.warning(
        "Transport late-charge: booking=%s kaynak=%s folio açık değil → late-charge "
        "(total=%s tenant=%s)",
        booking_id, booking_doc.get("resource_id"), total, tenant_id,
    )
    return {"charged": False, "reason": "no_active_booking_or_folio"}


@router.post("/bookings")
async def create_booking(
    payload: BookingIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _BOOK_ROLES)
    tenant_id = _tenant_of(current_user)
    actor = _actor_id(current_user)

    # Idempotency: aynı anahtarla önceki rezervasyonu dön.
    if payload.idempotency_key:
        prior = await db.transport_bookings.find_one(
            {"tenant_id": tenant_id,
             "id": _stable_booking_id(tenant_id, payload.idempotency_key)},
            {"_id": 0},
        )
        if prior:
            return {"booking": prior, "idempotent": True}

    resource = await db.transport_resources.find_one(
        {"id": payload.resource_id, "tenant_id": tenant_id}
    )
    if not resource:
        raise HTTPException(status_code=404, detail="Kaynak bulunamadı")
    if not resource.get("active", True):
        raise HTTPException(status_code=400, detail="Kaynak pasif")

    slots, total, sched = _compute_slots(resource, payload)

    booking_id = (
        _stable_booking_id(tenant_id, payload.idempotency_key)
        if payload.idempotency_key
        else str(uuid.uuid4())
    )

    # Slot kilidi index'i (fail-closed) — yoksa çift-rezervasyon riski.
    try:
        await _ensure_slot_lock_index()
    except Exception as exc:  # noqa: BLE001
        logger.warning("transport slot-lock index ensure başarısız: %r", exc)
        raise HTTPException(
            status_code=503,
            detail="Rezervasyon geçici olarak kullanılamıyor (index), tekrar deneyin",
        ) from exc

    # Faturalama idempotency index'ini de claim'den ÖNCE garanti et: index
    # kurulamazsa rezervasyonu hiç başlatma (fail-closed; reserved-but-billing-
    # degraded sahte-yeşili YOK).
    try:
        await _ensure_charge_index()
    except Exception as exc:  # noqa: BLE001
        logger.warning("transport charge index ensure başarısız: %r", exc)
        raise HTTPException(
            status_code=503,
            detail="Rezervasyon geçici olarak kullanılamıyor (index), tekrar deneyin",
        ) from exc

    # Atomik çift-rezervasyon koruması.
    await _claim_slots(tenant_id, payload.resource_id, booking_id, slots)

    now = _now_iso()
    doc = {
        "id": booking_id,
        "tenant_id": tenant_id,
        "resource_id": payload.resource_id,
        "resource_name": resource.get("name"),
        "kind": resource.get("kind"),
        "guest_name": (payload.guest_name or "").strip() or None,
        "room_number": (payload.room_number or "").strip() or None,
        "booking_id": payload.booking_id or None,
        "slots": slots,
        "schedule": sched,
        "total": total,
        "note": (payload.note or "").strip() or None,
        "idempotency_key": payload.idempotency_key,
        "status": "reserved",
        "folio_charged": False,
        "created_at": now,
        "updated_at": now,
        "created_by": actor,
    }

    # Folio faturalama (kaynak rezerve edildikten sonra).
    try:
        folio_charge = await _post_booking_to_folio(tenant_id, actor, doc)
    except Exception as exc:  # noqa: BLE001 — faturalama hatası rezervasyonu bozmaz
        logger.exception("Transport folio post hata booking=%s tenant=%s", booking_id, tenant_id)
        folio_charge = {"charged": False, "error": str(exc)[:120]}
    doc["folio_charged"] = bool(folio_charge and folio_charge.get("charged"))
    doc["folio_id"] = folio_charge.get("folio_id") if folio_charge else None

    await db.transport_bookings.insert_one(dict(doc))
    return {"booking": _serialize(doc), "folio_charge": folio_charge}


@router.delete("/bookings/{transport_booking_id}")
async def cancel_booking(
    transport_booking_id: str,
    current_user: User = Depends(get_current_user),
):
    """Rezervasyonu iptal eder ve tuttuğu zaman dilimi kilitlerini serbest bırakır."""
    _require_role(current_user, _BOOK_ROLES)
    tenant_id = _tenant_of(current_user)
    bk = await db.transport_bookings.find_one(
        {"id": transport_booking_id, "tenant_id": tenant_id}
    )
    if not bk:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")
    if bk.get("status") == "cancelled":
        return {"ok": True, "status": "cancelled"}
    # Kilitleri serbest bırak.
    for slot_key in bk.get("slots", []):
        await db.transport_slot_locks.delete_one({
            "tenant_id": tenant_id,
            "resource_id": bk.get("resource_id"),
            "slot_key": slot_key,
            "booking_id": transport_booking_id,
        })
    await db.transport_bookings.update_one(
        {"id": transport_booking_id, "tenant_id": tenant_id},
        {"$set": {"status": "cancelled", "updated_at": _now_iso()}},
    )
    return {"ok": True, "status": "cancelled"}


@router.get("/late-charges")
async def list_late_charges(
    status: str = Query("pending_review"),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if status and status != "all":
        q["status"] = status
    rows = await db[_LATE_CHARGE_COLLECTION].find(q, {"_id": 0}).sort("updated_at", -1).to_list(limit)
    return {"late_charges": rows}
