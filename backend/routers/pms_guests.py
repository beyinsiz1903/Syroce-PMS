"""
PMS Guests Router — Extracted from routers/pms.py (Stage 1 decomposition)
Guest CRUD and search.
"""

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import Guest, GuestCreate, User

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

router = APIRouter(prefix="/api", tags=["pms"])


@router.post("/pms/guests", response_model=Guest)
async def create_guest(
    guest_data: GuestCreate,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    guest = Guest(tenant_id=current_user.tenant_id, **guest_data.model_dump())
    guest_dict = guest.model_dump()
    guest_dict['created_at'] = guest_dict['created_at'].isoformat()
    await db.guests.insert_one(guest_dict)
    return guest


@router.get("/pms/guests", response_model=list[Guest])
@cached(ttl=300, key_prefix="pms_guests")  # Cache for 5 minutes
async def get_guests(
    limit: int = 1000,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    guests_raw = await db.guests.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).skip(offset).limit(limit).to_list(limit)

    # Map database fields to model fields
    guests = []
    for guest in guests_raw:
        # Combine first_name and last_name into name if they exist
        if 'first_name' in guest and 'last_name' in guest:
            guest['name'] = f"{guest.get('first_name', '')} {guest.get('last_name', '')}".strip()
        elif 'name' not in guest:
            guest['name'] = guest.get('email', 'Unknown')

        # Use passport_number as id_number if id_number doesn't exist
        if 'id_number' not in guest and 'passport_number' in guest:
            guest['id_number'] = guest.get('passport_number', '')
        elif 'id_number' not in guest:
            guest['id_number'] = ''

        guests.append(guest)

    return guests


@router.get("/pms/guests/search")
async def search_guests(
    q: str = "",
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    """Misafir arama: ad, e-posta, telefon veya kimlik numarasina gore arar."""
    q = q.strip()
    if not q or len(q) < 2:
        return []

    tenant_id = current_user.tenant_id
    regex = {"$regex": q, "$options": "i"}
    query = {
        "tenant_id": tenant_id,
        "$or": [
            {"name": regex},
            {"first_name": regex},
            {"last_name": regex},
            {"email": regex},
            {"phone": regex},
            {"id_number": regex},
            {"passport_number": regex},
        ],
    }
    guests_raw = await db.guests.find(query, {"_id": 0}).sort("name", 1).limit(limit).to_list(limit)

    results = []
    for g in guests_raw:
        if "first_name" in g and "last_name" in g:
            g["name"] = f"{g.get('first_name', '')} {g.get('last_name', '')}".strip()
        elif "name" not in g:
            g["name"] = g.get("email", "Unknown")
        if "id_number" not in g:
            g["id_number"] = g.get("passport_number", "")
        results.append({
            "id": g.get("id", ""),
            "name": g.get("name", ""),
            "email": g.get("email", ""),
            "phone": g.get("phone", ""),
            "id_number": g.get("id_number", ""),
            "vip_status": g.get("vip_status", False),
            "total_stays": g.get("total_stays", 0),
        })
    return results


@router.get("/pms/guests/{guest_id}")
async def get_guest_by_id(
    guest_id: str,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    guest = await db.guests.find_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")
    if "first_name" in guest and "last_name" in guest:
        guest["name"] = f"{guest.get('first_name', '')} {guest.get('last_name', '')}".strip()
    elif "name" not in guest:
        guest["name"] = guest.get("email", "Unknown")
    if "id_number" not in guest:
        guest["id_number"] = guest.get("passport_number", "")
    return guest


@router.put("/pms/guests/{guest_id}")
async def update_guest(
    guest_id: str,
    data: dict,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms")),
):
    guest = await db.guests.find_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")
    allowed = {
        "name", "email", "phone", "id_type", "id_number",
        "nationality", "date_of_birth", "address", "city",
        "postal_code", "country", "gender", "notes",
        "id_issue_date", "id_expiry_date", "id_issuing_authority",
    }
    update_fields = {k: v for k, v in data.items() if k in allowed}
    if not update_fields:
        raise HTTPException(status_code=400, detail="Guncellenecek alan bulunamadi")
    await db.guests.update_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id},
        {"$set": update_fields},
    )
    updated = await db.guests.find_one(
        {"id": guest_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    return updated
