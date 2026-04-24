"""
Agency Portal Router — Acente Yonetim ve Portal Sistemi
========================================================
Endpoints:
  Hotel Admin:
    POST   /api/agencies                  - Create agency
    GET    /api/agencies                  - List agencies
    GET    /api/agencies/{agency_id}      - Get agency detail
    PUT    /api/agencies/{agency_id}      - Update agency
    DELETE /api/agencies/{agency_id}      - Delete (deactivate) agency
    POST   /api/agencies/{agency_id}/users - Create agency user
    GET    /api/agencies/{agency_id}/users  - List agency users
    DELETE /api/agencies/users/{user_id}   - Delete agency user
    GET    /api/agency-reservations        - List all agency reservations

  Agency Portal:
    POST   /api/agency-portal/auth/login   - Agency user login
    GET    /api/agency-portal/profile      - Agency profile + hotel info
    GET    /api/agency-portal/content      - Published content for this agency
    GET    /api/agency-portal/availability - Check room availability
    POST   /api/agency-portal/reservations - Create reservation (auto PMS)
    GET    /api/agency-portal/reservations - List own reservations
"""
import uuid
from datetime import UTC, datetime

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.atomic_booking import BookingConflictError, create_booking_atomic
from core.database import db
from core.security import (
    JWT_ALGORITHM,
    JWT_SECRET,
    _is_super_admin,
    create_token,
    get_current_user,
    hash_password,
    verify_password,
)
from models.enums import UserRole
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v101 DW

router = APIRouter(prefix="/api", tags=["agency-portal"])


# ─── Request / Response Models ────────────────────────────────────

class AgencyCreate(BaseModel):
    name: str
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    commission_rate: float = 10.0
    notes: str = ""

class AgencyUpdate(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    commission_rate: float | None = None
    notes: str | None = None
    status: str | None = None

class AgencyUserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str = "agency_agent"  # agency_admin or agency_agent

class AgencyLoginRequest(BaseModel):
    email: str
    password: str

class AgencyReservationCreate(BaseModel):
    room_type_id: str
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    guest_name: str
    guest_email: str = ""
    guest_phone: str = ""
    adults: int = 2
    children: int = 0
    special_requests: str = ""
    total_amount: float = 0


# ─── Helpers ──────────────────────────────────────────────────────

def _now_iso():
    return datetime.now(UTC).isoformat()


def _uuid():
    return str(uuid.uuid4())


def _require_hotel_staff(user: User):
    """Ensure user is hotel staff (not agency). Super_admin always allowed."""
    if _is_super_admin(user):
        return
    if user.role in (UserRole.AGENCY_ADMIN, UserRole.AGENCY_AGENT):
        raise HTTPException(status_code=403, detail="Acente kullanicilari bu islemi yapamaz")


def _require_agency_user(user: User):
    """Ensure user is an agency user (super_admin always allowed)."""
    if _is_super_admin(user):
        return
    if user.role in (UserRole.AGENCY_ADMIN, UserRole.AGENCY_AGENT):
        return
    extra_roles = getattr(user, "roles", None) or []
    if isinstance(extra_roles, list) and any(
        r in ("agency_admin", "agency_agent", "super_admin") for r in extra_roles
    ):
        return
    raise HTTPException(status_code=403, detail="Bu endpoint sadece acente kullanicilari icindir")


async def _get_agency_user_from_token(token: str) -> dict:
    """Decode agency JWT and fetch user doc."""
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Gecersiz token")
        user_doc = await db.users.find_one(
            {"$or": [{"id": user_id}, {"user_id": user_id}]}, {"_id": 0}
        )
        if not user_doc:
            raise HTTPException(status_code=401, detail="Kullanici bulunamadi")
        primary_role = user_doc.get("role")
        roles_arr = user_doc.get("roles") or []
        is_sa = (
            primary_role == "super_admin"
            or (isinstance(roles_arr, list) and "super_admin" in roles_arr)
        )
        is_agency = (
            primary_role in ("agency_admin", "agency_agent")
            or (isinstance(roles_arr, list) and any(r in ("agency_admin", "agency_agent") for r in roles_arr))
        )
        if not is_sa and not is_agency:
            raise HTTPException(status_code=403, detail="Bu endpoint sadece acente kullanicilari icindir")
        return user_doc
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token suresi dolmus")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Gecersiz token")


# ═══════════════════════════════════════════════════════════════════
# HOTEL ADMIN — Agency CRUD
# ═══════════════════════════════════════════════════════════════════

@router.post("/agencies")
async def create_agency(data: AgencyCreate, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Yeni acente olustur."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    agency = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "name": data.name.strip(),
        "contact_name": data.contact_name.strip(),
        "contact_email": data.contact_email.strip(),
        "contact_phone": data.contact_phone.strip(),
        "commission_rate": data.commission_rate,
        "notes": data.notes.strip(),
        "status": "active",
        "published_content": False,
        "published_at": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.agencies.insert_one(agency)
    agency.pop("_id", None)
    return agency


@router.get("/agencies")
async def list_agencies(current_user: User = Depends(get_current_user)):
    """Otel acentelerini listele."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id
    docs = await db.agencies.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return docs


@router.get("/agencies/{agency_id}")
async def get_agency(agency_id: str, current_user: User = Depends(get_current_user)):
    """Acente detay."""
    _require_hotel_staff(current_user)
    doc = await db.agencies.find_one(
        {"id": agency_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Acente bulunamadi")
    return doc


@router.put("/agencies/{agency_id}")
async def update_agency(agency_id: str, data: AgencyUpdate, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Acente guncelle."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    existing = await db.agencies.find_one(
        {"id": agency_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Acente bulunamadi")

    updates = {"updated_at": _now_iso()}
    for field in ("name", "contact_name", "contact_email", "contact_phone", "commission_rate", "notes", "status"):
        val = getattr(data, field, None)
        if val is not None:
            updates[field] = val.strip() if isinstance(val, str) else val

    await db.agencies.update_one({"id": agency_id, "tenant_id": tenant_id}, {"$set": updates})
    existing.update(updates)
    return existing


@router.delete("/agencies/{agency_id}")
async def delete_agency(agency_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Acenteyi devre disi birak."""
    _require_hotel_staff(current_user)
    await db.agencies.update_one(
        {"id": agency_id, "tenant_id": current_user.tenant_id},
        {"$set": {"status": "inactive", "updated_at": _now_iso()}}
    )
    return {"ok": True, "message": "Acente devre disi birakildi"}


# ─── Agency User Management ──────────────────────────────────────

@router.post("/agencies/{agency_id}/users")
async def create_agency_user(agency_id: str, data: AgencyUserCreate, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Acente kullanicisi olustur."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    agency = await db.agencies.find_one(
        {"id": agency_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not agency:
        raise HTTPException(status_code=404, detail="Acente bulunamadi")

    existing = await db.users.find_one({"email": data.email.strip().lower()}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=409, detail="Bu e-posta adresi zaten kayitli")

    if data.role not in ("agency_admin", "agency_agent"):
        raise HTTPException(status_code=400, detail="Gecersiz rol. agency_admin veya agency_agent olmali")

    user_id = _uuid()
    user_doc = {
        "id": user_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "agency_id": agency_id,
        "name": data.name.strip(),
        "email": data.email.strip().lower(),
        "password": hash_password(data.password),
        "role": data.role,
        "roles": [data.role],
        "status": "active",
        "created_at": _now_iso(),
    }
    await db.users.insert_one(user_doc)
    user_doc.pop("_id", None)
    user_doc.pop("password", None)
    return user_doc


@router.get("/agencies/{agency_id}/users")
async def list_agency_users(agency_id: str, current_user: User = Depends(get_current_user)):
    """Acente kullanicilarini listele."""
    _require_hotel_staff(current_user)
    docs = await db.users.find(
        {"agency_id": agency_id, "tenant_id": current_user.tenant_id},
        {"_id": 0, "password": 0}
    ).to_list(100)
    return docs


@router.delete("/agencies/users/{user_id}")
async def delete_agency_user(user_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v101 DW
):
    """Acente kullanicisini sil."""
    _require_hotel_staff(current_user)
    result = await db.users.delete_one({
        "id": user_id,
        "tenant_id": current_user.tenant_id,
        "role": {"$in": ["agency_admin", "agency_agent"]}
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Acente kullanicisi bulunamadi")
    return {"ok": True}


# ─── Agency Reservations (Hotel Side) ────────────────────────────

@router.get("/agency-reservations")
async def list_agency_reservations(
    agency_id: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Otel icin tum acente rezervasyonlarini listele."""
    _require_hotel_staff(current_user)
    query = {"tenant_id": current_user.tenant_id, "source_channel": "agency"}
    if agency_id:
        query["agency_id"] = agency_id
    docs = await db.bookings.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return docs


# ═══════════════════════════════════════════════════════════════════
# AGENCY PORTAL — Auth & Operations
# ═══════════════════════════════════════════════════════════════════

@router.post("/agency-portal/auth/login")
async def agency_login(data: AgencyLoginRequest):
    """Acente giris."""
    from core.tenant_db import get_system_db
    sysdb = get_system_db()

    user_doc = await sysdb.users.find_one(
        {"email": data.email.strip().lower()}, {"_id": 0}
    )
    if not user_doc:
        raise HTTPException(status_code=401, detail="E-posta veya sifre hatali")

    _login_role = user_doc.get("role")
    _login_roles = user_doc.get("roles") or []
    _login_is_sa = _login_role == "super_admin" or "super_admin" in _login_roles
    _login_is_agency = _login_role in ("agency_admin", "agency_agent") or any(
        r in ("agency_admin", "agency_agent") for r in _login_roles
    )
    if not (_login_is_sa or _login_is_agency):
        raise HTTPException(status_code=403, detail="Bu giris sadece acente kullanicilari icindir")

    if not verify_password(data.password, user_doc.get("password", "")):
        raise HTTPException(status_code=401, detail="E-posta veya sifre hatali")

    agency = None
    if user_doc.get("agency_id"):
        agency = await sysdb.agencies.find_one(
            {"id": user_doc.get("agency_id")}, {"_id": 0}
        )
    if not _login_is_sa:
        if not agency or agency.get("status") != "active":
            raise HTTPException(status_code=403, detail="Acente hesabi aktif degil")

    token = create_token(user_doc["id"], user_doc.get("tenant_id"))

    return {
        "token": token,
        "user": {
            "id": user_doc["id"],
            "name": user_doc.get("name", ""),
            "email": user_doc.get("email", ""),
            "role": user_doc.get("role", ""),
            "roles": list(user_doc.get("roles") or []),
            "agency_id": user_doc.get("agency_id", ""),
            "tenant_id": user_doc.get("tenant_id", ""),
        },
        "agency": {
            "id": agency["id"] if agency else "",
            "name": agency["name"] if agency else "",
        },
    }


@router.get("/agency-portal/profile")
async def agency_portal_profile(current_user: User = Depends(get_current_user)):
    """Acente profil ve otel bilgisi."""
    _require_agency_user(current_user)
    agency_id = getattr(current_user, "agency_id", None)
    agency = None
    if agency_id:
        agency = await db.agencies.find_one({"id": agency_id}, {"_id": 0})
    elif not _is_super_admin(current_user):
        raise HTTPException(status_code=400, detail="Acente bilgisi bulunamadi")

    tenant = await db.tenants.find_one({"id": current_user.tenant_id}, {"_id": 0})

    return {
        "agency": agency,
        "hotel": {
            "name": tenant.get("property_name", "") if tenant else "",
            "address": tenant.get("address", "") if tenant else "",
            "phone": tenant.get("contact_phone", "") if tenant else "",
        },
    }


@router.get("/agency-portal/content")
async def agency_portal_content(current_user: User = Depends(get_current_user)):
    """Acenteye dagitilmis otel icerigi."""
    _require_agency_user(current_user)
    agency_id = getattr(current_user, "agency_id", None)
    tenant_id = current_user.tenant_id

    # Check if content is published to this agency
    agency = await db.agencies.find_one(
        {"id": agency_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not agency or not agency.get("published_content"):
        return {"published": False, "hotel_content": None}

    content = await db.hotel_content.find_one(
        {"tenant_id": tenant_id}, {"_id": 0}
    )
    return {"published": True, "hotel_content": content}


@router.get("/agency-portal/availability")
async def agency_portal_availability(
    check_in: str = Query(..., description="YYYY-MM-DD"),
    check_out: str = Query(..., description="YYYY-MM-DD"),
    adults: int = Query(2),
    current_user: User = Depends(get_current_user),
):
    """Musaitlik sorgula — acente portali."""
    _require_agency_user(current_user)
    tenant_id = current_user.tenant_id

    ci = datetime.fromisoformat(check_in + "T00:00:00+00:00")
    co = datetime.fromisoformat(check_out + "T00:00:00+00:00")
    if co <= ci:
        raise HTTPException(status_code=400, detail="Cikis tarihi giristen sonra olmalidir")

    # Get all room types for this hotel
    rooms = await db.rooms.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).to_list(1000)

    # Group by room_type
    room_types = {}
    for r in rooms:
        rt = r.get("room_type", "Standard")
        if rt not in room_types:
            room_types[rt] = {
                "room_type": rt,
                "capacity": r.get("capacity", 2),
                "base_price": r.get("base_price", 0),
                "amenities": r.get("amenities", []),
                "total_rooms": 0,
                "booked_rooms": 0,
                "available_rooms": 0,
                "room_ids": [],
            }
        room_types[rt]["total_rooms"] += 1
        room_types[rt]["room_ids"].append(r.get("id"))

    # Count booked rooms for date range
    for rt_name, rt_data in room_types.items():
        booked_count = await db.bookings.count_documents({
            "tenant_id": tenant_id,
            "room_id": {"$in": rt_data["room_ids"]},
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
            "check_in": {"$lt": check_out + "T23:59:59"},
            "check_out": {"$gt": check_in + "T00:00:00"},
        })
        rt_data["booked_rooms"] = booked_count
        rt_data["available_rooms"] = max(0, rt_data["total_rooms"] - booked_count)
        rt_data.pop("room_ids")  # Don't expose internal IDs

    results = [v for v in room_types.values() if v["available_rooms"] > 0]
    return {"check_in": check_in, "check_out": check_out, "room_types": results}


@router.post("/agency-portal/reservations")
async def agency_portal_create_reservation(
    data: AgencyReservationCreate,
    current_user: User = Depends(get_current_user),
):
    """Acente rezervasyonu olustur — otomatik PMS'e duser."""
    _require_agency_user(current_user)
    tenant_id = current_user.tenant_id
    agency_id = getattr(current_user, "agency_id", None)

    ci = datetime.fromisoformat(data.check_in + "T14:00:00+00:00")
    co = datetime.fromisoformat(data.check_out + "T11:00:00+00:00")
    if co <= ci:
        raise HTTPException(status_code=400, detail="Cikis tarihi giristen sonra olmalidir")

    # Find an available room of the requested type
    rooms = await db.rooms.find(
        {"tenant_id": tenant_id, "room_type": data.room_type_id},
        {"_id": 0}
    ).to_list(500)

    if not rooms:
        raise HTTPException(status_code=404, detail="Bu oda tipi bulunamadi")

    available_room = None
    for room in rooms:
        conflict = await db.bookings.count_documents({
            "tenant_id": tenant_id,
            "room_id": room["id"],
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
            "check_in": {"$lt": data.check_out + "T23:59:59"},
            "check_out": {"$gt": data.check_in + "T00:00:00"},
        })
        if conflict == 0:
            available_room = room
            break

    if not available_room:
        raise HTTPException(status_code=409, detail="Secilen tarihler icin musait oda bulunamadi")

    # Get agency info
    agency = await db.agencies.find_one({"id": agency_id}, {"_id": 0})
    agency_name = agency.get("name", "Bilinmeyen Acente") if agency else "Bilinmeyen Acente"
    commission_rate = agency.get("commission_rate", 0) if agency else 0

    # Create guest
    guest_id = _uuid()
    guest_doc = {
        "id": guest_id,
        "tenant_id": tenant_id,
        "name": data.guest_name.strip(),
        "email": data.guest_email.strip() or f"agency-{guest_id[:8]}@placeholder.local",
        "phone": data.guest_phone.strip(),
        "id_number": "",
        "vip_status": False,
        "loyalty_points": 0,
        "total_stays": 0,
        "total_spend": 0.0,
        "created_at": _now_iso(),
    }
    await db.guests.insert_one(guest_doc)

    # Create booking directly in PMS
    booking_id = _uuid()
    confirmation_code = f"AGN-{booking_id[:8].upper()}"
    nights = (co - ci).days
    total = data.total_amount if data.total_amount > 0 else available_room.get("base_price", 0) * max(nights, 1)
    commission_amount = round(total * commission_rate / 100, 2)

    booking_doc = {
        "id": booking_id,
        "tenant_id": tenant_id,
        "guest_id": guest_id,
        "room_id": available_room["id"],
        "room_number": available_room.get("room_number", ""),
        "room_type": available_room.get("room_type", ""),
        "check_in": data.check_in + "T14:00:00",
        "check_out": data.check_out + "T11:00:00",
        "adults": data.adults,
        "children": data.children,
        "guests_count": data.adults + data.children,
        "status": "confirmed",
        "payment_status": "pending",
        "total_amount": total,
        "balance": total,
        "channel": "agency",
        "source_channel": "agency",
        "agency_id": agency_id,
        "agency_name": agency_name,
        "agency_commission_rate": commission_rate,
        "agency_commission_amount": commission_amount,
        "agency_user_id": current_user.id,
        "confirmation_code": confirmation_code,
        "special_requests": data.special_requests,
        "guest_name": data.guest_name.strip(),
        "guest_email": data.guest_email.strip(),
        "guest_phone": data.guest_phone.strip(),
        "origin": "agency_portal",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    # v106 architect follow-up (race-safety): direct insert_one bypassed
    # the room_night_locks atomic guard → double-booking risk on agency
    # portal bookings. Now routed through create_booking_atomic so the
    # unique compound index on (tenant_id, room_id, night_date) prevents
    # concurrent agency requests from claiming the same room.
    try:
        booking_doc = await create_booking_atomic(booking_doc)
    except BookingConflictError as conflict_err:
        raise HTTPException(status_code=409, detail=str(conflict_err))

    return {
        "ok": True,
        "booking": booking_doc,
        "message": f"Rezervasyon olusturuldu: {confirmation_code}",
    }


@router.get("/agency-portal/reservations")
async def agency_portal_list_reservations(current_user: User = Depends(get_current_user)):
    """Acente kendi rezervasyonlarini listele."""
    _require_agency_user(current_user)
    agency_id = getattr(current_user, "agency_id", None)

    docs = await db.bookings.find(
        {
            "tenant_id": current_user.tenant_id,
            "agency_id": agency_id,
            "source_channel": "agency",
        },
        {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return docs
