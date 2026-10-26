"""
PMS / Minibar — Otomatik Tüketim → Folio
=========================================
Personel bir oda için minibar tüketimi girer. Sistem:
  1. Misafir folio'suna idempotent charge yazar (dedup index +
     ledger-tabanlı balance recalc — ASLA $inc).
  2. (Opsiyonel) merkezi envanterden stok düşer + inventory_movements loglar
     (best-effort; tamamlanmış faturalamayı geri almaz, ama sessiz değildir).
  3. Fail-closed: aktif booking yoksa faturalamaz; folio açık değilse sessizce
     kapalı folio'ya yazmaz, operatör görünür `minibar_late_charges` kaydına
     yönlendirir.

Tüm uçlar tenant-scoped; mutasyonlar RBAC ile sınırlı. PII/secret loglanmaz.

POS → folio deseni (core.pos_folio_consumer) birebir takip edilir; tek fark
tüketici asenkron outbox yerine personel-tetikli senkron akış olmasıdır
(personel anında "yazıldı / late-charge'a düştü" geri bildirimi alır).
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from domains.pms.pos_extensions._idem import ensure_compound_unique
from models.schemas import User

logger = logging.getLogger("domains.pms.minibar")

router = APIRouter(prefix="/api/minibar", tags=["PMS / Minibar"])

# Tüketim girebilen roller (housekeeping minibar tüketimini tipik olarak girer).
_CONSUME_ROLES = {
    "super_admin",
    "admin",
    "supervisor",
    "front_desk",
    "housekeeping",
    "staff",
}
# Katalog (minibar ürünleri) yönetimi yönetici seviyesi.
_CATALOG_ROLES = {"super_admin", "admin", "supervisor"}

_LATE_CHARGE_COLLECTION = "minibar_late_charges"


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


# Sabit namespace — idempotency_key'den deterministik (stabil) log_id türetmek
# için. Aynı (tenant, key) HER ZAMAN aynı source_minibar_log_id'yi verir; böylece
# retry/kismi-basari sonrasi folio_charges dedup index'i cift faturalamayi kapatir.
_MINIBAR_LOG_NS = uuid.UUID("6f1d3c4a-2b7e-4a91-9c0d-000000000000")


def _stable_log_id(tenant_id: str, idempotency_key: str) -> str:
    return str(uuid.uuid5(_MINIBAR_LOG_NS, f"{tenant_id}:{idempotency_key}"))


async def _ensure_minibar_charge_index() -> None:
    """Minibar folio-charge idempotency index (fail-closed).

    POS tarafıyla çakışmaması için ayrı kaynak alanı: source_minibar_log_id.
    """
    await ensure_compound_unique(
        db.folio_charges,
        [("tenant_id", 1), ("source_minibar_log_id", 1), ("line_no", 1)],
        partial_filter={"source_minibar_log_id": {"$type": "string"}},
        name="ux_folio_charges_minibar_source",
    )


async def _ensure_minibar_consumption_index() -> None:
    """Tüketim idempotency claim'i (fail-closed, DB-seviyesi).

    (tenant_id, idempotency_key) partial-unique → eşzamanlı iki istek aynı key
    ile çift tüketim/charge üretemez (check-then-act yarışını DB kapatır).
    """
    await ensure_compound_unique(
        db.minibar_consumptions,
        [("tenant_id", 1), ("idempotency_key", 1)],
        partial_filter={"idempotency_key": {"$type": "string"}},
        name="ux_minibar_consumptions_idem",
    )


async def _find_active_booking(tenant_id: str, room_id: str) -> dict | None:
    """Odadaki aktif rezervasyonu bulur (check-in yapmış misafir)."""
    return await db.bookings.find_one(
        {
            "tenant_id": tenant_id,
            "room_id": room_id,
            "status": {"$in": ["checked_in", "in_house"]},
        }
    )


def _serialize(doc: dict | None) -> dict | None:
    if not doc:
        return doc
    d = dict(doc)
    d.pop("_id", None)
    return d


# ─────────────────────────────────────────────────────────────────────
# Katalog — minibar ürünleri (CRUD)
# ─────────────────────────────────────────────────────────────────────
class MinibarItemIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    price: float = Field(..., ge=0, le=1e9, allow_inf_nan=False)
    currency: str | None = Field(None, pattern=r'^[A-Z]{3}$')
    tax_rate: float | None = Field(None, ge=0, le=1)
    category: str = Field("drink", max_length=40)
    active: bool = True
    # Opsiyonel: merkezi envanter (`inventory`) ürünüyle stok bağlama.
    inventory_product_id: str | None = Field(None, max_length=64)


class MinibarItemUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    price: float | None = Field(None, ge=0, le=1e9, allow_inf_nan=False)
    currency: str | None = Field(None, pattern=r'^[A-Z]{3}$')
    tax_rate: float | None = Field(None, ge=0, le=1)
    category: str | None = Field(None, max_length=40)
    active: bool | None = None
    inventory_product_id: str | None = Field(None, max_length=64)


@router.get("/items")
async def list_items(
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if not include_inactive:
        q["active"] = True
    items = await db.minibar_items.find(q, {"_id": 0}).sort("name", 1).to_list(1000)
    return {"items": items}


@router.post("/items")
async def create_item(
    payload: MinibarItemIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _CATALOG_ROLES)
    tenant_id = _tenant_of(current_user)
    now = _now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "name": payload.name.strip(),
        "price": round(float(payload.price), 2),
        "currency": payload.currency,
        "tax_rate": payload.tax_rate,
        "category": payload.category,
        "active": payload.active,
        "inventory_product_id": payload.inventory_product_id,
        "created_at": now,
        "updated_at": now,
        "created_by": _actor_id(current_user),
    }
    await db.minibar_items.insert_one(dict(doc))
    return {"item": _serialize(doc)}


@router.put("/items/{item_id}")
async def update_item(
    item_id: str,
    payload: MinibarItemUpdate,
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
    res = await db.minibar_items.update_one(
        {"id": item_id, "tenant_id": tenant_id},
        {"$set": updates},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    doc = await db.minibar_items.find_one({"id": item_id, "tenant_id": tenant_id}, {"_id": 0})
    return {"item": doc}


@router.delete("/items/{item_id}")
async def deactivate_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
):
    """Soft-delete: ürünü pasifleştirir (geçmiş charge referansları korunur)."""
    _require_role(current_user, _CATALOG_ROLES)
    tenant_id = _tenant_of(current_user)
    res = await db.minibar_items.update_one(
        {"id": item_id, "tenant_id": tenant_id},
        {"$set": {"active": False, "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return {"ok": True, "id": item_id}


# ─────────────────────────────────────────────────────────────────────
# Tüketim → folio
# ─────────────────────────────────────────────────────────────────────
class ConsumeLine(BaseModel):
    item_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0, le=1000)


class ConsumeIn(BaseModel):
    room_id: str = Field(..., min_length=1)
    lines: list[ConsumeLine] = Field(..., min_length=1, max_length=50)
    note: str | None = Field(None, max_length=500)
    # Aynı tüketim girişinin çift gönderimine karşı (UI double-submit, retry).
    idempotency_key: str | None = Field(None, max_length=80)


async def _deplete_stock_best_effort(
    tenant_id: str,
    actor: str,
    item: dict,
    quantity: int,
    source_log_id: str,
    line_no: int,
) -> dict:
    """Merkezi envanterden atomik (optimistic-lock) stok düşer + hareket loglar.

    Best-effort: tamamlanmış faturalamayı ASLA geri almaz. Stok yetersiz/çakışma
    durumunda sessiz değil — uyarı loglanır ve sonuç çağrıya döner.
    Idempotent: inventory_movements üzerinde (tenant, source_minibar_log_id,
    line_no) tekilliği ile çift düşüm engellenir.
    """
    product_id = item.get("inventory_product_id")
    if not product_id:
        return {"status": "skipped", "reason": "no_inventory_link"}

    # Idempotent guard: bu (log, satır) için hareket zaten yazıldıysa atla.
    existing = await db.inventory_movements.find_one(
        {
            "tenant_id": tenant_id,
            "source_minibar_log_id": source_log_id,
            "line_no": line_no,
        }
    )
    if existing:
        return {"status": "already_applied"}

    product = await db.inventory.find_one({"id": product_id, "tenant_id": tenant_id})
    if not product:
        logger.warning(
            "Minibar stok düşümü: envanter ürünü yok product=%s tenant=%s",
            product_id,
            tenant_id,
        )
        return {"status": "product_not_found"}

    current_qty = product.get("quantity", 0)
    if current_qty < quantity:
        logger.warning(
            "Minibar stok yetersiz product=%s mevcut=%s istenen=%s tenant=%s (faturalama sürüyor)",
            product_id,
            current_qty,
            quantity,
            tenant_id,
        )
        return {"status": "insufficient_stock", "available": current_qty}

    new_qty = current_qty - quantity
    res = await db.inventory.update_one(
        {"id": product_id, "tenant_id": tenant_id, "quantity": current_qty},
        {"$set": {"quantity": new_qty, "last_updated": _now_iso(), "last_updated_by": actor}},
    )
    if res.modified_count == 0:
        logger.warning(
            "Minibar stok eşzamanlı değişti product=%s tenant=%s (faturalama sürüyor)",
            product_id,
            tenant_id,
        )
        return {"status": "concurrent_modification"}

    await db.inventory_movements.insert_one(
        {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "product_id": product_id,
            "product_name": product.get("product_name", item.get("name", "Minibar")),
            "movement_type": "out",
            "quantity": -quantity,
            "previous_quantity": current_qty,
            "new_quantity": new_qty,
            "reason": "minibar_consumption",
            "source_minibar_log_id": source_log_id,
            "line_no": line_no,
            "performed_by": actor,
            "timestamp": _now_iso(),
        }
    )
    return {"status": "depleted", "new_quantity": new_qty}


@router.post("/consume")
async def consume(
    payload: ConsumeIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _CONSUME_ROLES)
    from domains.pms.minibar_consumption import consume_to_folio

    return await consume_to_folio(db, payload, current_user)


@router.get("/consumptions")
async def list_consumptions(
    room_id: str | None = Query(None),
    booking_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if room_id:
        q["room_id"] = room_id
    if booking_id:
        q["booking_id"] = booking_id
    rows = await db.minibar_consumptions.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"consumptions": rows}


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
