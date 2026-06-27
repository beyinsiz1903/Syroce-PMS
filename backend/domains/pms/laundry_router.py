"""
PMS / Çamaşır (Laundry & Valet) — Sipariş → Folio
==================================================
Resepsiyon/housekeeping bir oda için çamaşır siparişi girer; sipariş teslim
edildiğinde (`delivered`) misafir folio'suna idempotent charge yazılır.

Minibar (core.pos_folio_consumer) deseni birebir izlenir:
  1. Charge yalnızca TESLİMDE yazılır; dedup index
     (tenant_id, source_laundry_order_id, line_no) çift faturalamayı kapatır
     (re-deliver / double-PATCH → tek charge). Balance ledger-tabanlı recalc —
     ASLA $inc.
  2. Fail-closed: aktif booking + açık guest folio yoksa kapalı folio'ya
     yazılmaz; operatör görünür `laundry_late_charges` kaydına yönlendirilir.
  3. Tutar SUNUCUDA yeniden hesaplanır (client `total`'a güvenilmez); hizmet
     tipi çarpanı sunucu-tarafıdır.

Tüm uçlar tenant-scoped; mutasyonlar RBAC ile sınırlı. PII/secret loglanmaz.
"""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from core.database import db
from core.pos_folio_consumer import _recalc_folio_balance
from core.security import get_current_user
from domains.pms.pos_extensions._idem import ensure_compound_unique
from models.schemas import User

logger = logging.getLogger("domains.pms.laundry")

router = APIRouter(prefix="/api/laundry", tags=["PMS / Laundry"])

# Sipariş girebilen/durum güncelleyebilen roller (housekeeping çamaşırı işler).
_ORDER_ROLES = {
    "super_admin", "admin", "supervisor", "front_desk", "housekeeping", "staff",
}
# Ürün fiyat kataloğu yönetimi yönetici seviyesi.
_CATALOG_ROLES = {"super_admin", "admin", "supervisor"}

_LATE_CHARGE_COLLECTION = "laundry_late_charges"

# Hizmet tipi çarpanları (frontend SERVICE_TYPES ile birebir; sunucu otoritedir).
_SERVICE_MULTIPLIERS: dict[str, float] = {
    "wash_iron": 1.0,
    "dry_clean": 1.5,
    "iron_only": 0.5,
    "express": 2.0,
}

# Durum akışı (defensive workflow guard). Teslim folyo-etkili terminal geçiş.
_LAUNDRY_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"in_progress", "ready", "delivered", "cancelled"},
    "in_progress": {"ready", "delivered", "cancelled"},
    "ready": {"delivered", "cancelled"},
    "delivered": set(),
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


async def _ensure_laundry_charge_index() -> None:
    """Çamaşır folio-charge idempotency index (fail-closed).

    POS/minibar ile çakışmaması için ayrı kaynak alanı: source_laundry_order_id.
    """
    await ensure_compound_unique(
        db.folio_charges,
        [("tenant_id", 1), ("source_laundry_order_id", 1), ("line_no", 1)],
        partial_filter={"source_laundry_order_id": {"$type": "string"}},
        name="ux_folio_charges_laundry_source",
    )


async def _find_active_booking_by_room_number(tenant_id: str, room_number: str) -> dict | None:
    """Oda numarasından aktif (check-in) rezervasyonu çözer."""
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
# Katalog — çamaşır ürün/fiyat listesi (CRUD)
# ─────────────────────────────────────────────────────────────────────
class LaundryItemIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=120)
    price: float = Field(..., ge=0)
    active: bool = True


class LaundryItemUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    price: float | None = Field(None, ge=0)
    active: bool | None = None


@router.get("/items")
async def list_items(
    include_inactive: bool = Query(True),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if not include_inactive:
        q["active"] = True
    items = await db.laundry_items.find(q, {"_id": 0}).sort("name", 1).to_list(1000)
    return {"items": items}


@router.post("/items")
async def create_item(
    payload: LaundryItemIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _CATALOG_ROLES)
    tenant_id = _tenant_of(current_user)
    code = payload.code.strip().lower()
    existing = await db.laundry_items.find_one(
        {"tenant_id": tenant_id, "code": code}, {"_id": 0}
    )
    if existing:
        raise HTTPException(status_code=400, detail="Bu kod ile ürün zaten var")
    now = _now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "code": code,
        "name": payload.name.strip(),
        "price": round(float(payload.price), 2),
        "active": payload.active,
        "created_at": now,
        "updated_at": now,
        "created_by": _actor_id(current_user),
    }
    await db.laundry_items.insert_one(dict(doc))
    return {"item": _serialize(doc)}


@router.put("/items/{item_id}")
async def update_item(
    item_id: str,
    payload: LaundryItemUpdate,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _CATALOG_ROLES)
    tenant_id = _tenant_of(current_user)
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if "name" in updates and updates["name"]:
        updates["name"] = updates["name"].strip()
    if "price" in updates and updates["price"] is not None:
        updates["price"] = round(float(updates["price"]), 2)
    if not updates:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")
    updates["updated_at"] = _now_iso()
    res = await db.laundry_items.update_one(
        {"id": item_id, "tenant_id": tenant_id},
        {"$set": updates},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    doc = await db.laundry_items.find_one({"id": item_id, "tenant_id": tenant_id}, {"_id": 0})
    return {"item": doc}


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _CATALOG_ROLES)
    tenant_id = _tenant_of(current_user)
    res = await db.laundry_items.delete_one({"id": item_id, "tenant_id": tenant_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return {"ok": True, "id": item_id}


# ─────────────────────────────────────────────────────────────────────
# Siparişler
# ─────────────────────────────────────────────────────────────────────
class OrderLine(BaseModel):
    code: str = Field(..., min_length=1, max_length=40)
    quantity: int = Field(..., gt=0, le=1000)


class OrderIn(BaseModel):
    room_number: str = Field(..., min_length=1, max_length=40)
    guest_name: str | None = Field(None, max_length=200)
    booking_id: str | None = Field(None, max_length=64)
    folio_id: str | None = Field(None, max_length=64)
    service_type: str = Field("wash_iron", max_length=40)
    items: list[OrderLine] = Field(..., min_length=1, max_length=100)
    notes: str | None = Field(None, max_length=500)
    priority: str = Field("normal", max_length=20)


class StatusUpdate(BaseModel):
    status: str = Field(..., min_length=1, max_length=30)


def _build_order_lines(
    items_by_code: dict, lines: list[OrderLine], multiplier: float
) -> tuple[list[dict], float]:
    out: list[dict] = []
    grand_total = 0.0
    for idx, ln in enumerate(lines):
        it = items_by_code.get(ln.code.strip().lower())
        if not it:
            raise HTTPException(status_code=400, detail=f"Geçersiz çamaşır ürünü: {ln.code}")
        unit_price = round(float(it.get("price", 0)), 2)
        line_total = round(unit_price * ln.quantity * multiplier, 2)
        grand_total += line_total
        out.append({
            "line_no": idx,
            "code": it["code"],
            "name": it.get("name", "Çamaşır"),
            "quantity": ln.quantity,
            "unit_price": unit_price,
            "total": line_total,
        })
    return out, round(grand_total, 2)


@router.get("/orders")
async def list_orders(
    status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if status and status != "all":
        q["status"] = status
    rows = await db.laundry_orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"orders": rows}


@router.post("/orders")
async def create_order(
    payload: OrderIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _ORDER_ROLES)
    tenant_id = _tenant_of(current_user)
    actor = _actor_id(current_user)

    multiplier = _SERVICE_MULTIPLIERS.get(payload.service_type, 1.0)

    codes = list({ln.code.strip().lower() for ln in payload.items})
    items = await db.laundry_items.find(
        {"code": {"$in": codes}, "tenant_id": tenant_id}, {"_id": 0}
    ).to_list(1000)
    items_by_code = {it["code"]: it for it in items}
    order_lines, grand_total = _build_order_lines(items_by_code, payload.items, multiplier)

    now = _now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "room_number": str(payload.room_number).strip(),
        "guest_name": (payload.guest_name or "").strip() or None,
        "booking_id": payload.booking_id or None,
        "folio_id": payload.folio_id or None,
        "service_type": payload.service_type,
        "service_multiplier": multiplier,
        "items": order_lines,
        "total": grand_total,
        "notes": (payload.notes or "").strip() or None,
        "priority": payload.priority,
        "status": "pending",
        "folio_charged": False,
        "created_at": now,
        "updated_at": now,
        "created_by": actor,
    }
    await db.laundry_orders.insert_one(dict(doc))
    return {"order": _serialize(doc)}


async def _charge_order_to_folio(tenant_id: str, actor: str, order: dict) -> dict:
    """Teslim edilen siparişi açık guest folio'ya idempotent yazar.

    Döner: {charged: bool, amount?, reason?, error?, folio_id?, balance?}
    """
    booking_id = order.get("booking_id")
    booking = None
    if not booking_id:
        booking = await _find_active_booking_by_room_number(
            tenant_id, order.get("room_number", "")
        )
        booking_id = booking.get("id") if booking else None

    if not booking_id:
        return {"charged": False, "reason": "no_active_booking_or_folio"}

    open_folio = await db.folios.find_one(
        {"booking_id": booking_id, "folio_type": "guest", "status": "open", "tenant_id": tenant_id}
    )

    # Idempotency index (fail-closed) — yoksa çift-post riski. Sessiz degrade
    # YOK: index kurulamazsa yükselt (çağıran teslimi geri sarar / 503 döner).
    try:
        await _ensure_laundry_charge_index()
    except Exception as exc:  # noqa: BLE001
        logger.warning("laundry charge index ensure başarısız: %r", exc)
        raise HTTPException(
            status_code=503,
            detail="Faturalama geçici olarak kullanılamıyor (index), tekrar deneyin",
        ) from exc

    order_id = order["id"]
    order_lines = order.get("items", [])

    if open_folio:
        folio_id = open_folio["id"]
        guest_id = open_folio.get("guest_id") or (booking.get("guest_id") if booking else None)
        now = _now_iso()
        for ln in order_lines:
            charge_doc = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "booking_id": booking_id,
                "folio_id": folio_id,
                "guest_id": guest_id,
                "charge_type": "laundry",
                "charge_category": "laundry",
                "description": f"Çamaşır - {ln['name']} x{ln['quantity']}",
                "amount": ln["total"],
                "tax_amount": 0,
                "total": ln["total"],
                "voided": False,
                "date": now,
                "posted_by": actor,
                "created_at": now,
                # Dedup anahtarı — ux_folio_charges_laundry_source.
                "source_laundry_order_id": order_id,
                "line_no": ln["line_no"],
            }
            try:
                await db.folio_charges.insert_one(dict(charge_doc))
            except DuplicateKeyError:
                # Bu (sipariş, satır) zaten yazılmış — idempotent atla.
                continue
        balance = await _recalc_folio_balance(db, tenant_id, folio_id)
        return {
            "charged": True,
            "amount": float(order.get("total", 0)),
            "folio_id": folio_id,
            "balance": balance,
        }

    # Açık folio yok → kapalıya yazma; görünür late-charge'a yönlendir.
    any_folio = await db.folios.find_one(
        {"booking_id": booking_id, "folio_type": "guest", "tenant_id": tenant_id},
        sort=[("created_at", -1)],
    )
    now = _now_iso()
    await db[_LATE_CHARGE_COLLECTION].update_one(
        {"tenant_id": tenant_id, "source_laundry_order_id": order_id},
        {
            "$set": {
                "tenant_id": tenant_id,
                "source_laundry_order_id": order_id,
                "room_number": order.get("room_number"),
                "booking_id": booking_id,
                "guest_id": booking.get("guest_id") if booking else None,
                "folio_id": any_folio.get("id") if any_folio else None,
                "folio_status_at_apply": any_folio.get("status") if any_folio else "missing",
                "lines": order_lines,
                "total": order.get("total", 0),
                "status": "pending_review",
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    logger.warning(
        "Çamaşır late-charge: booking=%s oda=%s folio açık değil → late-charge "
        "(total=%s tenant=%s)",
        booking_id, order.get("room_number"), order.get("total"), tenant_id,
    )
    return {"charged": False, "reason": "no_active_booking_or_folio"}


@router.patch("/orders/{order_id}")
async def update_order_status(
    order_id: str,
    payload: StatusUpdate,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _ORDER_ROLES)
    tenant_id = _tenant_of(current_user)
    actor = _actor_id(current_user)

    new_status = payload.status.strip()
    if new_status not in _LAUNDRY_TRANSITIONS:
        raise HTTPException(status_code=400, detail="Geçersiz durum")

    order = await db.laundry_orders.find_one({"id": order_id, "tenant_id": tenant_id})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")

    cur_status = order.get("status", "pending")
    if new_status == cur_status:
        return {"ok": True, "status": cur_status, "folio_charge": None}
    if new_status not in _LAUNDRY_TRANSITIONS.get(cur_status, set()):
        raise HTTPException(
            status_code=409, detail=f"Geçersiz geçiş: {cur_status} → {new_status}"
        )

    # Teslim → faturalama. Idempotency index'ini CAS'tan ÖNCE garanti et:
    # index kurulamazsa teslimi hiç başlatma (fail-closed; minibar ile hizalı,
    # delivered-but-billing-degraded sahte-yeşili YOK).
    if new_status == "delivered":
        try:
            await _ensure_laundry_charge_index()
        except Exception as exc:  # noqa: BLE001
            logger.warning("laundry charge index ensure başarısız: %r", exc)
            raise HTTPException(
                status_code=503,
                detail="Faturalama geçici olarak kullanılamıyor (index), tekrar deneyin",
            ) from exc

    # Atomik CAS geçişi: yalnızca mevcut durumu hâlâ `cur_status` olan tek istek
    # kazanır → eşzamanlı iki `delivered` PATCH'inde yalnız biri folio'ya post eder.
    update_set = {"status": new_status, "updated_at": _now_iso()}
    res = await db.laundry_orders.update_one(
        {"id": order_id, "tenant_id": tenant_id, "status": cur_status},
        {"$set": update_set},
    )
    if res.modified_count == 0:
        # Yarışı kaybettik (başka istek geçişi yaptı) → mevcut durumu dön.
        latest = await db.laundry_orders.find_one(
            {"id": order_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        return {"ok": True, "status": (latest or {}).get("status"), "folio_charge": None}

    folio_charge = None
    if new_status == "delivered":
        # Charge dedup index zaten çift-post'u kapatır; CAS yalnız tek post sağlar.
        try:
            folio_charge = await _charge_order_to_folio(tenant_id, actor, order)
        except Exception as exc:  # noqa: BLE001 — faturalama hatası teslimi geri almaz
            logger.exception("Çamaşır folio post hata order=%s tenant=%s", order_id, tenant_id)
            folio_charge = {"charged": False, "error": str(exc)[:120]}
        await db.laundry_orders.update_one(
            {"id": order_id, "tenant_id": tenant_id},
            {"$set": {
                "folio_charged": bool(folio_charge and folio_charge.get("charged")),
                "folio_id": folio_charge.get("folio_id") if folio_charge else order.get("folio_id"),
                "delivered_at": _now_iso(),
            }},
        )

    return {"ok": True, "status": new_status, "folio_charge": folio_charge}


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
