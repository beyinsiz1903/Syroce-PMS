"""
Agency Content Distribution Router — Icerik Dagitim Sistemi
============================================================
Hotel staff manages content once, selects agencies, and distributes.

Endpoints:
  GET    /api/hotel-content          - Get hotel content
  PUT    /api/hotel-content          - Update hotel content
  POST   /api/hotel-content/distribute - Distribute to selected agencies
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from models.enums import UserRole
from models.schemas import User

router = APIRouter(prefix="/api", tags=["agency-content"])


def _now_iso():
    return datetime.now(UTC).isoformat()


def _uuid():
    return str(uuid.uuid4())


def _require_hotel_staff(user: User):
    if user.role in (UserRole.AGENCY_ADMIN, UserRole.AGENCY_AGENT):
        raise HTTPException(status_code=403, detail="Acente kullanicilari bu islemi yapamaz")


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


# ─── Endpoints ───────────────────────────────────────────────────

@router.get("/hotel-content")
async def get_hotel_content(current_user: User = Depends(get_current_user)):
    """Otel icerigini getir."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    content = await db.hotel_content.find_one(
        {"tenant_id": tenant_id}, {"_id": 0}
    )
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
            "updated_at": _now_iso(),
        }
        await db.hotel_content.insert_one(content)
        content.pop("_id", None)

    return content


@router.put("/hotel-content")
async def update_hotel_content(data: HotelContentUpdate, current_user: User = Depends(get_current_user)):
    """Otel icerigini guncelle."""
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

    existing = await db.hotel_content.find_one({"tenant_id": tenant_id})
    if existing:
        await db.hotel_content.update_one(
            {"tenant_id": tenant_id}, {"$set": update_data}
        )
    else:
        update_data["id"] = _uuid()
        await db.hotel_content.insert_one(update_data)

    update_data.pop("_id", None)
    return update_data


@router.post("/hotel-content/distribute")
async def distribute_content(data: ContentDistributeRequest, current_user: User = Depends(get_current_user)):
    """Secilen acentelere icerik dagit."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    if not data.agency_ids:
        raise HTTPException(status_code=400, detail="En az bir acente secmelisiniz")

    # Verify content exists
    content = await db.hotel_content.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if not content:
        raise HTTPException(status_code=404, detail="Once otel icerigini kaydedin")

    # Update each selected agency's published status
    updated = 0
    now = _now_iso()
    for aid in data.agency_ids:
        result = await db.agencies.update_one(
            {"id": aid, "tenant_id": tenant_id},
            {"$set": {
                "published_content": True,
                "published_at": now,
                "published_by": current_user.id,
            }}
        )
        if result.modified_count > 0:
            updated += 1

    # Unpublish agencies NOT in the list
    await db.agencies.update_many(
        {"tenant_id": tenant_id, "id": {"$nin": data.agency_ids}},
        {"$set": {"published_content": False, "published_at": None}}
    )

    return {
        "ok": True,
        "distributed_to": updated,
        "total_selected": len(data.agency_ids),
        "message": f"{updated} acenteye icerik dagitildi",
    }
