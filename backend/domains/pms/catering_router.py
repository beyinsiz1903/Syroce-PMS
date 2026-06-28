"""Opera #7 — Catering Menu.
Function Space booking'leri için menü kataloğu + booking'e menü atama:
- Menu items kataloğu (CRUD: list/create/update/delete soft)
- Booking'e seçili menüler. Atama anında price_per_person ve currency
  SNAPSHOT olarak kaydedilir (geriye dönük finansal tutarlılık).
- Mixed currency reddedilir (tek booking → tek para birimi).
- Allergen ve diyet etiketleri.
Yetki: manage_sales (CRUD + read + booking atama).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/catering", tags=["Catering Menu"])

CATEGORIES = ("breakfast", "lunch", "dinner", "coffee_break", "cocktail", "buffet", "plated")
_INDEX_INIT = False


async def _ensure_indexes(db) -> None:
    """Race koşullarında uniqueness garantisi. Başarısızlıkta hata yükselt
    (sessizce degrade etme — finansal/komersiyal veri için kritik)."""
    global _INDEX_INIT
    if _INDEX_INIT:
        return
    try:
        await db.catering_menu_items.create_index(
            [("tenant_id", 1), ("code", 1)],
            unique=True,
            partialFilterExpression={"active": True},
            name="catering_item_unique_active_code",
        )
        await db.catering_booking_menus.create_index(
            [("tenant_id", 1), ("booking_id", 1)],
            name="catering_booking_lookup",
        )
        _INDEX_INIT = True
    except Exception as e:  # noqa: BLE001
        logger.error("Catering index oluşturulamadı: %s", e)
        raise HTTPException(503, "Catering altyapısı hazır değil, tekrar deneyin") from e


class MenuItem(BaseModel):
    id: str | None = None
    code: str = Field(..., min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_\-]+$")
    name: str = Field(..., min_length=1, max_length=160)
    category: str = "lunch"
    price_per_person: float = Field(..., ge=0)
    currency: str = Field("TRY", min_length=3, max_length=3)
    description: str | None = None
    allergens: list[str] = Field(default_factory=list)
    is_vegan: bool = False
    is_vegetarian: bool = False
    is_gluten_free: bool = False
    min_headcount: int = Field(1, ge=1)
    active: bool = True


class MenuItemUpdate(BaseModel):
    """Kısmi güncelleme (PATCH semantiği). Sadece gönderilen alanlar değişir."""

    name: str | None = Field(None, min_length=1, max_length=160)
    category: str | None = None
    price_per_person: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    description: str | None = None
    allergens: list[str] | None = None
    is_vegan: bool | None = None
    is_vegetarian: bool | None = None
    is_gluten_free: bool | None = None
    min_headcount: int | None = Field(None, ge=1)


class BookingMenuLine(BaseModel):
    menu_item_id: str
    headcount: int = Field(..., ge=1)
    note: str | None = None


class BookingMenuPayload(BaseModel):
    lines: list[BookingMenuLine]


# ---------- Menu items catalog ----------


@router.get("/menu-items", response_model=list[MenuItem])
async def list_items(
    category: str | None = None,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    db = get_system_db()
    q: dict[str, Any] = {"tenant_id": user.tenant_id, "active": True}
    if category:
        q["category"] = category
    cur = db.catering_menu_items.find(q).sort([("category", 1), ("name", 1)])
    out: list[dict[str, Any]] = []
    async for d in cur:
        d.pop("_id", None)
        out.append(d)
    return out


@router.post("/menu-items", response_model=MenuItem, status_code=201)
async def create_item(
    payload: MenuItem,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    if payload.category not in CATEGORIES:
        raise HTTPException(400, f"Geçersiz kategori. Seçenekler: {', '.join(CATEGORIES)}")
    db = get_system_db()
    await _ensure_indexes(db)

    existing = await db.catering_menu_items.find_one(
        {
            "tenant_id": user.tenant_id,
            "code": payload.code,
            "active": True,
        }
    )
    if existing:
        raise HTTPException(409, f"Bu kod zaten kullanımda: {payload.code}")

    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["tenant_id"] = user.tenant_id
    doc["currency"] = doc["currency"].upper()
    doc["created_by"] = user.email
    doc["created_at"] = datetime.now(UTC).isoformat()
    try:
        await db.catering_menu_items.insert_one(doc)
    except Exception as e:  # noqa: BLE001
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            raise HTTPException(409, f"Bu kod zaten kullanımda: {payload.code}") from e
        raise
    doc.pop("_id", None)
    return doc


@router.patch("/menu-items/{item_id}", response_model=MenuItem)
async def update_item(
    item_id: str,
    payload: MenuItemUpdate,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    db = get_system_db()
    changes = payload.model_dump(exclude_unset=True)
    if "category" in changes and changes["category"] not in CATEGORIES:
        raise HTTPException(400, f"Geçersiz kategori. Seçenekler: {', '.join(CATEGORIES)}")
    if "currency" in changes:
        changes["currency"] = changes["currency"].upper()
    if not changes:
        raise HTTPException(400, "Güncellenecek alan yok")
    changes["updated_by"] = user.email
    changes["updated_at"] = datetime.now(UTC).isoformat()
    res = await db.catering_menu_items.update_one(
        {"id": item_id, "tenant_id": user.tenant_id, "active": True},
        {"$set": changes},
    )
    if not res.matched_count:
        raise HTTPException(404, "Menü kalemi bulunamadı")
    doc = await db.catering_menu_items.find_one({"id": item_id, "tenant_id": user.tenant_id})
    doc.pop("_id", None)
    return doc


@router.delete("/menu-items/{item_id}", status_code=204)
async def delete_item(
    item_id: str,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    db = get_system_db()
    res = await db.catering_menu_items.update_one(
        {"id": item_id, "tenant_id": user.tenant_id},
        {"$set": {"active": False, "deleted_at": datetime.now(UTC).isoformat()}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Menü kalemi bulunamadı")


# ---------- Booking menüleri ----------


async def _booking_exists(db, tenant_id: str, booking_id: str) -> dict | None:
    return await db.function_bookings.find_one(
        {
            "$or": [{"id": booking_id}, {"_id": booking_id}],
            "tenant_id": tenant_id,
        }
    )


@router.get("/bookings/{booking_id}")
async def get_booking_menus(
    booking_id: str,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    db = get_system_db()
    booking = await _booking_exists(db, user.tenant_id, booking_id)
    if not booking:
        raise HTTPException(404, "Function booking bulunamadı")

    rec = await db.catering_booking_menus.find_one(
        {
            "tenant_id": user.tenant_id,
            "booking_id": booking_id,
        }
    )
    lines = (rec or {}).get("lines", [])

    enriched: list[dict[str, Any]] = []
    total = 0.0
    currency = (rec or {}).get("currency") or "TRY"
    for ln in lines:
        # Snapshot fiyat ve para birimi line'da kayıtlı (değişmez)
        price = float(ln.get("price_per_person_snapshot", 0))
        head = int(ln.get("headcount", 0))
        subtotal = price * head
        total += subtotal
        # Item bilgisini join et (görsellik için, fiyat snapshot'tan)
        item = await db.catering_menu_items.find_one(
            {
                "id": ln["menu_item_id"],
                "tenant_id": user.tenant_id,
            }
        )
        item_view = None
        if item:
            item.pop("_id", None)
            item_view = {
                "code": item.get("code"),
                "name": item.get("name"),
                "category": item.get("category"),
                "is_vegan": item.get("is_vegan"),
                "is_vegetarian": item.get("is_vegetarian"),
                "is_gluten_free": item.get("is_gluten_free"),
                "allergens": item.get("allergens", []),
                "active": item.get("active", False),
                "current_price_per_person": item.get("price_per_person"),
            }
        enriched.append(
            {
                "menu_item_id": ln["menu_item_id"],
                "headcount": head,
                "note": ln.get("note"),
                "price_per_person_snapshot": price,
                "currency_snapshot": ln.get("currency_snapshot", currency),
                "subtotal": round(subtotal, 2),
                "item": item_view,
            }
        )
    return {
        "booking_id": booking_id,
        "lines": enriched,
        "total": round(total, 2),
        "currency": currency,
    }


@router.put("/bookings/{booking_id}")
async def set_booking_menus(
    booking_id: str,
    payload: BookingMenuPayload,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Tam replace. Atama anında her line'a fiyat+currency SNAPSHOT alınır.
    Mixed currency reddedilir (booking düzeyinde tek para birimi)."""
    db = get_system_db()
    await _ensure_indexes(db)
    booking = await _booking_exists(db, user.tenant_id, booking_id)
    if not booking:
        raise HTTPException(404, "Function booking bulunamadı")

    item_ids = [ln.menu_item_id for ln in payload.lines]
    items_by_id: dict[str, dict] = {}
    if item_ids:
        cur = db.catering_menu_items.find(
            {
                "tenant_id": user.tenant_id,
                "id": {"$in": item_ids},
                "active": True,
            }
        )
        async for d in cur:
            d.pop("_id", None)
            items_by_id[d["id"]] = d
        missing = set(item_ids) - set(items_by_id.keys())
        if missing:
            raise HTTPException(400, f"Geçersiz/pasif menü kalemi: {', '.join(missing)}")

    # Mixed currency check
    currencies = {items_by_id[lid].get("currency", "TRY").upper() for lid in item_ids}
    if len(currencies) > 1:
        raise HTTPException(
            400,
            f"Tek booking'de farklı para birimi karıştırılamaz: {', '.join(currencies)}",
        )
    booking_currency = currencies.pop() if currencies else "TRY"

    # min_headcount + snapshot
    snap_lines: list[dict[str, Any]] = []
    for ln in payload.lines:
        it = items_by_id[ln.menu_item_id]
        if ln.headcount < int(it.get("min_headcount", 1)):
            raise HTTPException(
                400,
                f"'{it['name']}' için min kişi sayısı {it['min_headcount']}",
            )
        snap_lines.append(
            {
                "menu_item_id": ln.menu_item_id,
                "headcount": ln.headcount,
                "note": ln.note,
                "price_per_person_snapshot": float(it.get("price_per_person", 0)),
                "currency_snapshot": it.get("currency", "TRY").upper(),
            }
        )

    await db.catering_booking_menus.update_one(
        {"tenant_id": user.tenant_id, "booking_id": booking_id},
        {
            "$set": {
                "tenant_id": user.tenant_id,
                "booking_id": booking_id,
                "lines": snap_lines,
                "currency": booking_currency,
                "updated_by": user.email,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        },
        upsert=True,
    )
    return {"ok": True, "count": len(snap_lines), "currency": booking_currency}
