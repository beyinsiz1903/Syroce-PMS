"""
Agency Content Distribution Router — Icerik Dagitim Sistemi
============================================================
Hotel staff manages content once, selects agencies, and distributes.

Endpoints:
  GET    /api/hotel-content              - Get hotel content
  PUT    /api/hotel-content              - Update hotel content
  POST   /api/hotel-content/distribute   - Update publish list (atomic, additive by default)
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.database import db
from core.security import _is_super_admin, get_current_user
from models.enums import UserRole
from models.schemas import User

router = APIRouter(prefix="/api", tags=["agency-content"])


def _now_iso():
    return datetime.now(UTC).isoformat()


def _uuid():
    return str(uuid.uuid4())


def _require_hotel_staff(user: User):
    if _is_super_admin(user):
        return
    if user.role in (UserRole.AGENCY_ADMIN, UserRole.AGENCY_AGENT):
        raise HTTPException(status_code=403, detail="Acente kullanıcıları bu işlemi yapamaz")


# ─── Models ──────────────────────────────────────────────────────


class RoomTypeContent(BaseModel):
    room_type: str
    name: str = ""
    description: str = ""
    capacity: int = 2
    base_price: float = 0
    images: list[str] = []
    amenities: list[str] = []
    bed_type: str = ""


class ServiceContent(BaseModel):
    name: str
    description: str = ""
    icon: str = ""


class HotelContentUpdate(BaseModel):
    hotel_name: str = ""
    description: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    images: list[str] = []
    amenities: list[str] = []
    room_types: list[RoomTypeContent] = []
    services: list[ServiceContent] = []


class ContentDistributeRequest(BaseModel):
    agency_ids: list[str]
    # FIX #1 (KRITIK): Eskiden distribute her zaman "diff senkron" yapiyordu —
    # listede olmayan acenteler sessizce unpublish ediliyordu. Artik DEFAULT
    # additive (sadece ekle); cikarmak icin acikca True gonderilmeli.
    unpublish_omitted: bool = Field(
        default=False,
        description="True ise listede olmayan acentelerin yayini kaldirilir (destruktif).",
    )


# ─── Helpers ─────────────────────────────────────────────────────


def _validate_content_for_distribute(content: dict) -> list[str]:
    """Dagitim oncesi icerigin minimum dolu oldugunu dogrula. Hata listesi doner."""
    errors: list[str] = []
    if not (content.get("hotel_name") or "").strip():
        errors.append("Otel adı boş olamaz.")
    rts = content.get("room_types") or []
    if not rts:
        errors.append("En az bir oda tipi tanımlanmalı.")
    else:
        for i, rt in enumerate(rts, 1):
            if not (rt.get("name") or rt.get("room_type") or "").strip():
                errors.append(f"Oda Tipi {i}: ad/tip kodu boş.")
    return errors


# ─── Endpoints ───────────────────────────────────────────────────


@router.get("/hotel-content")
async def get_hotel_content(current_user: User = Depends(get_current_user)):
    """Otel içeriğini getir."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    content = await db.hotel_content.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if not content:
        # Auto-initialize from tenant and rooms
        tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})
        rooms = await db.rooms.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(500)

        # Group rooms by type
        rt_map = {}
        for r in rooms:
            rt = r.get("room_type", "Standard")
            if rt not in rt_map:
                rt_map[rt] = {
                    "room_type": rt,
                    "name": rt,
                    "description": "",
                    "capacity": r.get("capacity", 2),
                    "base_price": r.get("base_price", 0),
                    "images": [],
                    "amenities": r.get("amenities", []),
                    "bed_type": r.get("bed_type", ""),
                }

        content = {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "hotel_name": tenant.get("property_name", "") if tenant else "",
            "description": "",
            "address": tenant.get("address", "") if tenant else "",
            "phone": tenant.get("contact_phone", "") if tenant else "",
            "email": tenant.get("contact_email", "") if tenant else "",
            "images": [],
            "amenities": tenant.get("amenities", []) if tenant else [],
            "room_types": list(rt_map.values()),
            "services": [],
            "content_version": 1,
            "updated_at": _now_iso(),
        }
        await db.hotel_content.insert_one(content)
        content.pop("_id", None)

    return content


@router.put("/hotel-content")
async def update_hotel_content(data: HotelContentUpdate, current_user: User = Depends(get_current_user)):
    """Otel içeriğini güncelle. content_version'i +1 artirir (acente portal cache invalidation icin)."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    update_data = {
        "tenant_id": tenant_id,
        "hotel_name": data.hotel_name,
        "description": data.description,
        "address": data.address,
        "phone": data.phone,
        "email": data.email,
        "images": data.images,
        "amenities": data.amenities,
        "room_types": [rt.model_dump() for rt in data.room_types],
        "services": [s.model_dump() for s in data.services],
        "updated_at": _now_iso(),
    }

    existing = await db.hotel_content.find_one({"tenant_id": tenant_id}, {"_id": 0, "content_version": 1})
    if existing:
        await db.hotel_content.update_one(
            {"tenant_id": tenant_id},
            {
                "$set": update_data,
                "$inc": {"content_version": 1},  # Acente portal SWR/polling icin tetikleyici
            },
        )
        update_data["content_version"] = (existing.get("content_version") or 0) + 1
    else:
        update_data["id"] = _uuid()
        update_data["content_version"] = 1
        await db.hotel_content.insert_one(update_data)

    update_data.pop("_id", None)
    return update_data


@router.post("/hotel-content/distribute")
async def distribute_content(
    data: ContentDistributeRequest,
    current_user: User = Depends(get_current_user),
):
    """Yayin listesini guncelle.

    DEFAULT (additive): sadece secili acenteleri yayin listesine ekler.
    `unpublish_omitted=True` ise listede olmayan acentelerin yayinini KALDIRIR
    (destruktif — frontend bunu acikca onaylatmali).

    Tek update_many cagrisi ile O(1) roundtrip + atomik."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    if not data.agency_ids:
        raise HTTPException(status_code=400, detail="En az bir acente seçmelisiniz")

    # Icerik var mi + minimum dolulukta mi?
    content = await db.hotel_content.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if not content:
        raise HTTPException(status_code=404, detail="Önce otel içeriğini kaydedin")
    errors = _validate_content_for_distribute(content)
    if errors:
        raise HTTPException(
            status_code=400,
            detail={"code": "content_incomplete", "errors": errors, "message": "Dağıtımdan önce eksikleri tamamlayın: " + " ".join(errors)},
        )

    now = _now_iso()
    user_id = getattr(current_user, "id", None) or getattr(current_user, "email", "")
    content_version = content.get("content_version", 1)

    # FIX #2 (N+1): Tek update_many — eskiden 50 acente icin 51 roundtrip vardi.
    # FIX #4 (atomik): MongoDB update_many tek-cagri atomik bir mutasyondur.
    add_res = await db.agencies.update_many(
        {"id": {"$in": data.agency_ids}, "tenant_id": tenant_id, "status": "active"},
        {
            "$set": {
                "published_content": True,
                "published_at": now,
                "published_by": user_id,
                "published_content_version": content_version,
            }
        },
    )

    removed = 0
    if data.unpublish_omitted:
        # Sadece daha onceden yayinda olanlardan listede OLMAYANlari unpublish et —
        # boylece "modified_count" gercek diff'i yansitir.
        rem_res = await db.agencies.update_many(
            {
                "tenant_id": tenant_id,
                "id": {"$nin": data.agency_ids},
                "published_content": True,
            },
            {"$set": {"published_content": False, "published_at": None}},
        )
        removed = rem_res.modified_count or 0

    # Toplam su anki yayinda
    total_published = await db.agencies.count_documents({"tenant_id": tenant_id, "published_content": True})

    return {
        "ok": True,
        "added": add_res.modified_count or 0,
        "removed": removed,
        "total_published": total_published,
        "total_selected": len(data.agency_ids),
        "content_version": content_version,
        "message": (f"{add_res.modified_count or 0} acente yayına eklendi" + (f", {removed} acente yayından kaldırıldı" if removed else "")),
    }


@router.get("/hotel-content/distribute-preview")
async def distribute_preview(
    agency_ids: str = "",  # CSV
    current_user: User = Depends(get_current_user),
):
    """Dagitim oncesi onay diyalogu icin diff onizlemesi: kac eklenecek/kaldirilacak."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id
    ids = [x for x in (agency_ids or "").split(",") if x]
    if not ids:
        return {"to_add": 0, "to_remove": 0, "currently_published": 0, "selected": 0}

    currently_published_ids = [
        d["id"]
        async for d in db.agencies.find(
            {"tenant_id": tenant_id, "published_content": True},
            {"_id": 0, "id": 1},
        )
    ]
    cur_set = set(currently_published_ids)
    new_set = set(ids)
    to_add = len(new_set - cur_set)
    to_remove = len(cur_set - new_set)
    return {
        "to_add": to_add,
        "to_remove": to_remove,
        "currently_published": len(cur_set),
        "selected": len(new_set),
    }
