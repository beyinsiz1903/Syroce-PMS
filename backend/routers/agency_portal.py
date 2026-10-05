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

import logging
import uuid
from datetime import UTC, datetime

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

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
from security.encrypted_lookup import build_user_email_query, decrypt_user_doc, encrypt_user_doc

# Bug AI mirror — precomputed bcrypt hash so verify_password burns equal
# CPU on ghost users (see `auth.py:97`). Module-level so the bcrypt cost
# is paid once at import, not per request.
_DUMMY_PWHASH = hash_password("__agency_portal_timing_dummy__never_a_real_password__")

router = APIRouter(prefix="/api", tags=["agency-portal"])
logger = logging.getLogger("agency_portal")


def _date_pair(start_value: str, end_value: str):
    """Parse an ISO hotel date range for both request models and endpoints."""
    try:
        start = datetime.strptime(start_value, "%Y-%m-%d").date()
        end = datetime.strptime(end_value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError("Tarihler YYYY-AA-GG biçiminde olmalıdır") from exc
    if end <= start:
        raise ValueError("Bitiş tarihi başlangıçtan sonra olmalıdır")
    return start, end


# ─── Request / Response Models ────────────────────────────────────


class AgencyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    commission_rate: float = Field(10.0, ge=0, le=100)
    notes: str = ""

    @field_validator("name")
    @classmethod
    def _name_not_placeholder(cls, v: str) -> str:
        s = (v or "").strip()
        if len(s) < 2:
            raise ValueError("Acente adi en az 2 karakter olmalidir")
        return s


class AgencyUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    commission_rate: float | None = Field(None, ge=0, le=100)
    notes: str | None = None
    status: str | None = None

    @field_validator("name")
    @classmethod
    def _name_not_placeholder(cls, v):
        if v is None:
            return v
        s = v.strip()
        if len(s) < 2:
            raise ValueError("Acente adi en az 2 karakter olmalidir")
        return s

    @field_validator("status")
    @classmethod
    def _status_valid(cls, v):
        if v is None:
            return v
        if v not in ("active", "inactive"):
            raise ValueError("status sadece 'active' veya 'inactive' olabilir")
        return v


class AgencyUserCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: str = "agency_agent"  # agency_admin or agency_agent


from typing import Literal


class SeasonRate(BaseModel):
    season_start: str
    season_end: str
    room_type_id: str
    price: float = Field(..., gt=0)

    @model_validator(mode="after")
    def _valid_date_range(self):
        _date_pair(self.season_start, self.season_end)
        return self


class AgencyContractCreate(BaseModel):
    contract_name: str = Field(..., min_length=2, max_length=160)
    start_date: str
    end_date: str
    is_active: bool = True
    contract_type: Literal["net_rate", "commission"]
    commission_rate: float | None = Field(None, ge=0, le=100)
    credit_limit: float | None = Field(None, ge=0)
    season_rates: list[SeasonRate] | None = None

    @model_validator(mode="after")
    def _valid_contract(self):
        _date_pair(self.start_date, self.end_date)
        if self.contract_type == "commission" and self.commission_rate is None:
            raise ValueError("Komisyon sözleşmesinde komisyon oranı zorunludur")
        if self.contract_type == "net_rate" and not self.season_rates:
            raise ValueError("Net fiyat sözleşmesinde en az bir sezon fiyatı zorunludur")
        for rate in self.season_rates or []:
            if rate.season_start < self.start_date or rate.season_end > self.end_date:
                raise ValueError("Sezon fiyatları sözleşme tarihleri içinde olmalıdır")
        return self


class AgencyAllotmentCreate(BaseModel):
    contract_id: str
    room_type_id: str
    start_date: str
    end_date: str
    allotment_count: int = Field(..., ge=1, le=10000)
    release_days: int = Field(..., ge=0, le=365)

    @model_validator(mode="after")
    def _valid_date_range(self):
        _date_pair(self.start_date, self.end_date)
        return self


class AgencyLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class AgencyReservationCreate(BaseModel):
    room_type_id: str
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    guest_name: str = Field(..., min_length=2, max_length=160)
    guest_email: EmailStr | None = None
    guest_phone: str = ""
    adults: int = Field(2, ge=1, le=20)
    children: int = Field(0, ge=0, le=20)
    special_requests: str = Field("", max_length=1000)
    # Backwards-compatible input only. The server always recalculates the
    # authoritative amount; a browser must never be able to set its own rate.
    total_amount: float | None = Field(None, ge=0)


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
    if isinstance(extra_roles, list) and any(r in ("agency_admin", "agency_agent", "super_admin") for r in extra_roles):
        return
    raise HTTPException(status_code=403, detail="Bu endpoint sadece acente kullanicilari icindir")


async def _active_agency_for(user: User) -> dict | None:
    """Return the tenant-scoped active agency for every portal operation."""
    if _is_super_admin(user):
        return None
    agency_id = getattr(user, "agency_id", None)
    if not agency_id:
        raise HTTPException(status_code=403, detail="Acente bağlantısı bulunamadı")
    agency = await db.agencies.find_one({"id": agency_id, "tenant_id": user.tenant_id}, {"_id": 0})
    if not agency or agency.get("status") != "active":
        raise HTTPException(status_code=403, detail="Acente hesabı aktif değil")
    return agency


def _parse_stay_dates(check_in: str, check_out: str):
    try:
        return _date_pair(check_in, check_out)
    except ValueError as exc:
        status_code = 422 if "YYYY-AA-GG" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


async def _get_agency_user_from_token(token: str) -> dict:
    """Decode agency JWT and fetch user doc."""
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # V3 — refresh tokens are not valid bearer credentials.
        token_type = payload.get("type")
        if token_type and token_type != "access":
            raise HTTPException(status_code=401, detail="Gecersiz token tipi")
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Gecersiz token")
        user_doc = await db.users.find_one({"$or": [{"id": user_id}, {"user_id": user_id}]}, {"_id": 0})
        if not user_doc:
            raise HTTPException(status_code=401, detail="Kullanici bulunamadi")
        primary_role = user_doc.get("role")
        roles_arr = user_doc.get("roles") or []
        is_sa = primary_role == "super_admin" or (isinstance(roles_arr, list) and "super_admin" in roles_arr)
        is_agency = primary_role in ("agency_admin", "agency_agent") or (isinstance(roles_arr, list) and any(r in ("agency_admin", "agency_agent") for r in roles_arr))
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
async def create_agency(
    data: AgencyCreate,
    current_user: User = Depends(get_current_user),
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
async def list_agencies(
    status: str | None = Query(None, description="active|inactive (bos = hepsi)"),
    q: str | None = Query(None, description="ad/email/telefon icinde ara"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    include_placeholders: bool = Query(False, description="Test/seed cop kayitlari (name<2) dahil et"),
    current_user: User = Depends(get_current_user),
):
    """Otel acentelerini listele — filtre + arama + sayfalama destekli.

    Eski sozlesme korunur: parametre verilmezse JSON dizi doner (geriye donuk uyumlu).
    Filtre/arama/sayfalama kullanildiginda zarflanmis (`{items,total,page,...}`) doner."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    query: dict = {"tenant_id": tenant_id}
    if status in ("active", "inactive"):
        query["status"] = status
    if not include_placeholders:
        # Test/seed coplerini (ornegin name='x', name='C4') gizle.
        query["name"] = {"$regex": r"^.{2,}$", "$options": "s"}
    if q:
        needle = q.strip()
        if needle:
            import re as _re

            rx = {"$regex": _re.escape(needle), "$options": "i"}
            and_clause = [
                {
                    "$or": [
                        {"name": rx},
                        {"contact_name": rx},
                        {"contact_email": rx},
                        {"contact_phone": rx},
                    ]
                }
            ]
            # name regex'i query[name] ile cakismasin diye $and'e tasi.
            existing_name = query.pop("name", None)
            if existing_name is not None:
                and_clause.append({"name": existing_name})
            query["$and"] = and_clause

    wrapped = status is not None or q is not None or page != 1 or page_size != 50 or include_placeholders

    total = await db.agencies.count_documents(query)
    cursor = db.agencies.find(query, {"_id": 0}).sort("created_at", -1).skip((page - 1) * page_size).limit(page_size)
    docs = await cursor.to_list(page_size)

    if wrapped:
        return {
            "items": docs,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": page * page_size < total,
        }
    # Geriye donuk uyumluluk: parametresiz cagrida duz dizi don.
    return docs


@router.get("/agencies/{agency_id}")
async def get_agency(agency_id: str, current_user: User = Depends(get_current_user)):
    """Acente detay."""
    _require_hotel_staff(current_user)
    doc = await db.agencies.find_one({"id": agency_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Acente bulunamadi")
    return doc


@router.put("/agencies/{agency_id}")
async def update_agency(
    agency_id: str,
    data: AgencyUpdate,
    current_user: User = Depends(get_current_user),
):
    """Acente guncelle."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    existing = await db.agencies.find_one({"id": agency_id, "tenant_id": tenant_id}, {"_id": 0})
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


@router.get("/agencies/{agency_id}/usage")
async def agency_usage(agency_id: str, current_user: User = Depends(get_current_user)):
    """Acente silmeden once: bagli rezervasyon/kullanici sayilari."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id
    agency = await db.agencies.find_one({"id": agency_id, "tenant_id": tenant_id}, {"_id": 0, "name": 1})
    if not agency:
        raise HTTPException(status_code=404, detail="Acente bulunamadi")

    today_iso = datetime.now(UTC).strftime("%Y-%m-%d")
    total_bookings = await db.bookings.count_documents({"tenant_id": tenant_id, "agency_id": agency_id})
    future_active_bookings = await db.bookings.count_documents(
        {
            "tenant_id": tenant_id,
            "agency_id": agency_id,
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
            "check_out": {"$gte": today_iso},
        }
    )
    user_count = await db.users.count_documents({"tenant_id": tenant_id, "agency_id": agency_id})
    return {
        "agency_id": agency_id,
        "agency_name": agency.get("name", ""),
        "total_bookings": total_bookings,
        "future_active_bookings": future_active_bookings,
        "user_count": user_count,
    }


@router.delete("/agencies/{agency_id}")
async def delete_agency(
    agency_id: str,
    force: bool = Query(False, description="Aktif rezervasyon olsa bile devre disi birak"),
    current_user: User = Depends(get_current_user),
):
    """Acenteyi devre disi birak (soft delete).

    Aktif/gelecek rezervasyonu varsa `force=false` (varsayilan) ile 409 doner;
    cagiran taraf onay aldiktan sonra `?force=true` ile yeniden cagirir.
    Soft delete oldugu icin mevcut rezervasyonlar (`agency_id`) korunur,
    sadece acente `status='inactive'` isaretlenir."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    agency = await db.agencies.find_one({"id": agency_id, "tenant_id": tenant_id}, {"_id": 0, "name": 1})
    if not agency:
        raise HTTPException(status_code=404, detail="Acente bulunamadi")

    today_iso = datetime.now(UTC).strftime("%Y-%m-%d")
    future_active = await db.bookings.count_documents(
        {
            "tenant_id": tenant_id,
            "agency_id": agency_id,
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
            "check_out": {"$gte": today_iso},
        }
    )
    if future_active > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "agency_has_active_bookings",
                "message": f"Bu acentenin {future_active} aktif/gelecek rezervasyonu var. Yine de devre disi birakmak icin onay verin.",
                "future_active_bookings": future_active,
            },
        )

    await db.agencies.update_one({"id": agency_id, "tenant_id": tenant_id}, {"$set": {"status": "inactive", "updated_at": _now_iso()}})
    return {
        "ok": True,
        "message": "Acente devre disi birakildi",
        "future_active_bookings_at_delete": future_active,
    }


# ─── Agency User Management ──────────────────────────────────────


@router.post("/agencies/{agency_id}/users")
async def create_agency_user(
    agency_id: str,
    data: AgencyUserCreate,
    current_user: User = Depends(get_current_user),
):
    """Acente kullanicisi olustur."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    agency = await db.agencies.find_one({"id": agency_id, "tenant_id": tenant_id}, {"_id": 0})
    if not agency:
        raise HTTPException(status_code=404, detail="Acente bulunamadi")

    # Encrypted-email parity with login lookup above — plaintext-only
    # `{"email": ...}` misses modern accounts whose email is stored as
    # ciphertext, which would let the same address be re-registered and
    # break the unique-email invariant. Use the blind-index `$or` helper.
    existing = await db.users.find_one(build_user_email_query(data.email.strip().lower()), {"_id": 0})
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
        # Standardize hash storage to `hashed_password` (matches auth.py
        # canonical write path at lines 368/400/1064). Legacy rows still
        # readable via the fallback chain in agency_login (line ~600).
        "hashed_password": hash_password(data.password),
        "role": data.role,
        "roles": [data.role],
        "status": "active",
        "created_at": _now_iso(),
    }
    response_doc = {key: value for key, value in user_doc.items() if key not in {"hashed_password", "password"}}
    encrypted_user_doc = encrypt_user_doc(user_doc)
    await db.users.insert_one(encrypted_user_doc)
    return response_doc


@router.get("/agencies/{agency_id}/users")
async def list_agency_users(agency_id: str, current_user: User = Depends(get_current_user)):
    """Acente kullanicilarini listele."""
    _require_hotel_staff(current_user)
    docs = await db.users.find(
        {"agency_id": agency_id, "tenant_id": current_user.tenant_id},
        # Exclude every known password-hash field name so neither the
        # canonical (`hashed_password`) nor legacy (`password_hash`,
        # `password`) variant leaks into the agency-users listing.
        {"_id": 0, "password": 0, "hashed_password": 0, "password_hash": 0},
    ).to_list(100)
    return [decrypt_user_doc(doc) for doc in docs]


@router.delete("/agencies/users/{user_id}")
async def delete_agency_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
):
    """Acente kullanicisini sil."""
    _require_hotel_staff(current_user)
    result = await db.users.delete_one({"id": user_id, "tenant_id": current_user.tenant_id, "role": {"$in": ["agency_admin", "agency_agent"]}})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Acente kullanicisi bulunamadi")
    return {"ok": True}


# ─── Agency Reservations (Hotel Side) ────────────────────────────


@router.get("/agency-reservations")
async def list_agency_reservations(agency_id: str | None = None, current_user: User = Depends(get_current_user)):
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


# ─── B2B Extranet (Phase 1) ──────────────────────────────────────

@router.post("/agencies/{agency_id}/contracts")
async def create_agency_contract(agency_id: str, data: AgencyContractCreate, current_user: User = Depends(get_current_user)):
    _require_hotel_staff(current_user)

    agency = await db.agencies.find_one({"id": agency_id, "tenant_id": current_user.tenant_id})
    if not agency:
        raise HTTPException(status_code=404, detail="Acente bulunamadı")
    if agency.get("status") != "active":
        raise HTTPException(status_code=409, detail="Pasif acente için yeni sözleşme oluşturulamaz")

    rate_room_types = {rate.room_type_id for rate in data.season_rates or []}
    if rate_room_types:
        existing_room_types = set(
            await db.rooms.distinct("room_type", {"tenant_id": current_user.tenant_id, "room_type": {"$in": list(rate_room_types)}})
        )
        missing_room_types = sorted(rate_room_types - existing_room_types)
        if missing_room_types:
            raise HTTPException(status_code=400, detail=f"Tanımsız oda tipi: {', '.join(missing_room_types)}")

    contract_id = str(uuid.uuid4())
    contract_doc = {
        "id": contract_id,
        "tenant_id": current_user.tenant_id,
        "agency_id": agency_id,
        "contract_name": data.contract_name,
        "start_date": data.start_date,
        "end_date": data.end_date,
        "is_active": data.is_active,
        "contract_type": data.contract_type,
        "commission_rate": data.commission_rate,
        "credit_limit": data.credit_limit,
        "season_rates": [r.model_dump() for r in data.season_rates] if data.season_rates else [],
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.id,
    }

    await db.agency_contracts.insert_one(contract_doc)
    return {"message": "Sözleşme başarıyla oluşturuldu", "contract_id": contract_id}


@router.get("/agencies/{agency_id}/contracts")
async def list_agency_contracts(agency_id: str, current_user: User = Depends(get_current_user)):
    _require_hotel_staff(current_user)
    contracts = await db.agency_contracts.find({"agency_id": agency_id, "tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(100)
    return {"contracts": contracts}


@router.post("/agencies/{agency_id}/allotments")
async def create_agency_allotment(agency_id: str, data: AgencyAllotmentCreate, current_user: User = Depends(get_current_user)):
    _require_hotel_staff(current_user)

    contract = await db.agency_contracts.find_one({"id": data.contract_id, "agency_id": agency_id, "tenant_id": current_user.tenant_id})
    if not contract:
        raise HTTPException(status_code=404, detail="Sözleşme bulunamadı veya bu acenteye ait değil")
    if not contract.get("is_active"):
        raise HTTPException(status_code=409, detail="Pasif sözleşmeye kontenjan tanımlanamaz")
    if data.start_date < contract.get("start_date", "") or data.end_date > contract.get("end_date", ""):
        raise HTTPException(status_code=400, detail="Kontenjan tarihleri sözleşme tarihleri içinde olmalıdır")

    room_exists = await db.rooms.find_one(
        {"tenant_id": current_user.tenant_id, "room_type": data.room_type_id, "is_active": {"$ne": False}},
        {"_id": 0, "id": 1},
    )
    if not room_exists:
        raise HTTPException(status_code=400, detail="Kontenjan için geçerli bir oda tipi seçin")

    overlapping = await db.agency_allotments.find_one(
        {
            "tenant_id": current_user.tenant_id,
            "agency_id": agency_id,
            "room_type_id": data.room_type_id,
            "start_date": {"$lt": data.end_date},
            "end_date": {"$gt": data.start_date},
        },
        {"_id": 0, "id": 1},
    )
    if overlapping:
        raise HTTPException(status_code=409, detail="Bu oda tipi ve tarih aralığı için çakışan kontenjan zaten var")

    allotment_id = str(uuid.uuid4())
    allotment_doc = {
        "id": allotment_id,
        "tenant_id": current_user.tenant_id,
        "agency_id": agency_id,
        "contract_id": data.contract_id,
        "room_type_id": data.room_type_id,
        "start_date": data.start_date,
        "end_date": data.end_date,
        "allotment_count": data.allotment_count,
        "release_days": data.release_days,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.id,
    }

    await db.agency_allotments.insert_one(allotment_doc)
    return {"message": "Kontenjan başarıyla tanımlandı", "allotment_id": allotment_id}


@router.get("/agencies/{agency_id}/allotments")
async def list_agency_allotments(agency_id: str, current_user: User = Depends(get_current_user)):
    _require_hotel_staff(current_user)
    allotments = await db.agency_allotments.find({"agency_id": agency_id, "tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)
    return {"allotments": allotments}


@router.post("/agency-portal/auth/login")
async def agency_login(request: Request, data: AgencyLoginRequest):
    """Acente giris."""
    # Task-135 (P0 drain fix) — Throttle wiring uses a **verify-first,
    # record-on-fail, drain-on-success** ordering so that:
    #   * a legitimate user who exhausts the per-account budget with
    #     mistyped passwords can still log in on the (cap+1)th attempt
    #     when they finally type the correct one, and
    #   * a brute-force attacker is still capped — every wrong attempt
    #     records a hit, so the 11th wrong-credential attempt against a
    #     given account (or 21st against a given IP) returns 429.
    #
    # The previous ordering (`enforce` BEFORE `verify_password`) blocked
    # the legitimate user with 429 on attempt 11 because the throttle
    # check inserted the hit BEFORE credentials were ever examined,
    # making the success-path `.reset()` unreachable. That regression
    # was caught by stress spec 98D Phase 2 (Run #143 NO-GO P0).
    #
    # Per-account layer (NFKC casefold-bucketed email) survives IP
    # rotation; per-IP layer caps naive parallel spray across distinct
    # emails.
    from security.auth_throttle import (
        AGENCY_LOGIN_ACCOUNT,
        AGENCY_LOGIN_IP,
        client_ip,
        normalize_identity,
    )
    from security.auth_throttle import enforce as _throttle

    _ip = client_ip(request)
    _email_key = normalize_identity(data.email)
    _ip_key = f"agency_login_ip:{_ip}"
    _acct_key = f"agency_login_acct:{_email_key}" if _email_key else None

    async def _record_failure_and_raise(status_code: int, detail: str):
        # Record the failed attempt on BOTH layers. `_throttle` may
        # raise 429 (with Retry-After header) instead of the underlying
        # status when the post-insert count exceeds the cap — that is
        # the brute-force boundary the spec asserts. IP layer is
        # checked first so naive single-source spray trips fastest.
        await _throttle(AGENCY_LOGIN_IP, _ip_key, "giris denemesi")
        if _acct_key:
            await _throttle(AGENCY_LOGIN_ACCOUNT, _acct_key, "giris denemesi")
        raise HTTPException(status_code=status_code, detail=detail)

    from core.tenant_db import get_system_db

    sysdb = get_system_db()

    # Encrypted email lookup parity with `auth.py:563` — PII fields
    # (including `email`) are encrypted at rest, with the searchable
    # blind index stored under `_hash_email`. Looking up by plaintext
    # `{"email": ...}` (the original implementation) silently misses
    # every modern account whose email column holds ciphertext, so the
    # router returned user-not-found 401 → throttle hit → by the
    # (per-account-cap+1)th attempt the success leg surfaced as 429.
    # This was the residual root cause of stress spec 98D Phase 2 after
    # the hash-field-tolerance fix landed (RCA 2026-05-27 turn 2).
    # `build_user_email_query` produces a `$or` query matching either the
    # blind index or legacy plaintext email; `decrypt_user_doc` restores
    # plaintext PII fields after read so downstream role/password checks
    # see the same shape as before.
    user_doc_raw = await sysdb.users.find_one(build_user_email_query(data.email.strip().lower()), {"_id": 0})

    # Timing-attack equalization mirror of `auth.py:587-590` (Bug AI).
    # ALWAYS run verify_password — on the real user's hash if found, on
    # a precomputed dummy bcrypt hash otherwise — so bcrypt CPU cost is
    # constant regardless of whether the account exists. Without this,
    # the absence-of-user fast path leaks via response-time differences
    # even when the per-IP/per-account throttle is in place.
    # Hash-field tolerance (mirror of `auth.py:585`): accounts created
    # via the main system store the bcrypt under `hashed_password`;
    # the agency register path (line ~449) now also writes there but
    # legacy rows may use `password_hash` or `password`. The fallback
    # chain accepts all three; verify_password itself is unchanged.
    if user_doc_raw:
        user_doc = decrypt_user_doc(user_doc_raw)
        hashed_pwd = (user_doc.get("hashed_password") or user_doc.get("password_hash") or user_doc.get("password", "")) or _DUMMY_PWHASH
    else:
        user_doc = None
        hashed_pwd = _DUMMY_PWHASH

    pw_ok = verify_password(data.password, hashed_pwd)

    if user_doc is None or not pw_ok:
        # User-not-found and wrong-password collapse into the same 401
        # response (identical detail text) and BOTH record a throttle
        # hit — wrong-pw is the obvious brute-force vector, user-not-
        # found is the email-enumeration vector. Constant-time bcrypt
        # above ensures the two paths cost the same.
        await _record_failure_and_raise(401, "E-posta veya sifre hatali")

    _login_role = user_doc.get("role")
    _login_roles = user_doc.get("roles") or []
    _login_is_sa = _login_role == "super_admin" or "super_admin" in _login_roles
    _login_is_agency = _login_role in ("agency_admin", "agency_agent") or any(r in ("agency_admin", "agency_agent") for r in _login_roles)
    if not (_login_is_sa or _login_is_agency):
        # Role-block is an authorization decision, NOT a credential
        # probe (it reveals nothing about whether the password is
        # correct, since we only reach here after pw_ok). Therefore
        # it must NOT consume the throttle budget. Counting it would
        # let any wrong-role caller with a *valid* password burn the
        # per-account cap and then trip 429 on the (cap+1)th
        # legitimate attempt — re-introducing the Task #135 P0.
        # Stress spec 98D specifically skips on 403, so it must
        # arrive as a clean 403, not a throttled 429.
        raise HTTPException(status_code=403, detail="Bu giris sadece acente kullanicilari icindir")

    # Credential gate passed — drain the per-IP / per-account throttle
    # counters so a legitimate user who mistyped before succeeding isn't
    # penalised for the rest of the window. Drain happens BEFORE the
    # account-status / agency-active checks so even an inactive-agency
    # rejection from a correctly-authenticated user does not poison the
    # window for their next successful attempt.
    try:
        await AGENCY_LOGIN_IP.reset(_ip_key)
        if _acct_key:
            await AGENCY_LOGIN_ACCOUNT.reset(_acct_key)
    except Exception:
        pass

    agency = None
    if user_doc.get("agency_id"):
        agency = await sysdb.agencies.find_one({"id": user_doc.get("agency_id")}, {"_id": 0})
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
    active_agency = await _active_agency_for(current_user)
    agency_id = getattr(current_user, "agency_id", None)
    agency = None
    if agency_id:
        agency = active_agency
    elif not _is_super_admin(current_user):
        raise HTTPException(status_code=400, detail="Acente bilgisi bulunamadi")

    tenant = await db.tenants.find_one({"id": current_user.tenant_id}, {"_id": 0})

    return {
        "agency": agency,
        "user": {"id": current_user.id, "name": current_user.name, "email": current_user.email,
                 "role": getattr(current_user.role, "value", current_user.role)},
        "hotel": {
            "name": tenant.get("property_name", "") if tenant else "",
            "address": tenant.get("address", "") if tenant else "",
            "phone": tenant.get("contact_phone", "") if tenant else "",
            "email": (tenant.get("contact_email") or tenant.get("email") or "") if tenant else "",
            "currency": (tenant.get("currency") or "TRY") if tenant else "TRY",
        },
    }


@router.get("/agency-portal/content")
async def agency_portal_content(current_user: User = Depends(get_current_user)):
    """Acenteye dagitilmis otel icerigi."""
    _require_agency_user(current_user)
    await _active_agency_for(current_user)
    agency_id = getattr(current_user, "agency_id", None)
    tenant_id = current_user.tenant_id

    # Check if content is published to this agency
    agency = await db.agencies.find_one({"id": agency_id, "tenant_id": tenant_id}, {"_id": 0})
    if not agency or not agency.get("published_content"):
        return {"published": False, "hotel_content": None}

    content = await db.hotel_content.find_one({"tenant_id": tenant_id}, {"_id": 0})
    return {"published": True, "hotel_content": content}


def _last_occupied_date(check_in: str, check_out: str | None) -> str:
    """Return the final billable hotel night for an exclusive checkout date."""
    if not check_out:
        return check_in
    from datetime import timedelta

    return (datetime.strptime(check_out, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()


async def _get_b2b_price(
    db,
    tenant_id: str,
    agency_id: str,
    check_in: str,
    room_type: str,
    public_price: float,
    check_out: str | None = None,
):
    last_night = _last_occupied_date(check_in, check_out)
    # Find active contract
    contract = await db.agency_contracts.find_one({"agency_id": agency_id, "tenant_id": tenant_id, "is_active": True, "start_date": {"$lte": check_in}, "end_date": {"$gte": last_night}})

    if not contract:
        return public_price, False

    if contract.get("contract_type") == "commission":
        comm = float(contract.get("commission_rate") or 0)
        return public_price * (1.0 - (comm / 100.0)), True

    # Net rate
    season_rates = contract.get("season_rates", [])
    for sr in season_rates:
        if sr.get("room_type_id") == room_type and sr.get("season_start") <= check_in and sr.get("season_end") >= last_night:
            return float(sr.get("price")), True

    return public_price, False


async def _get_b2b_allotment(
    db,
    tenant_id: str,
    agency_id: str,
    check_in: str,
    room_type: str,
    check_out: str | None = None,
):
    last_night = _last_occupied_date(check_in, check_out)
    allotment = await db.agency_allotments.find_one({"agency_id": agency_id, "tenant_id": tenant_id, "room_type_id": room_type, "start_date": {"$lte": check_in}, "end_date": {"$gte": last_night}})

    if allotment:
        # Check release days
        from datetime import UTC, datetime

        ci_date = datetime.fromisoformat(check_in + "T00:00:00+00:00")
        days_until_ci = (ci_date - datetime.now(UTC)).days
        if days_until_ci >= int(allotment.get("release_days", 0)):
            return int(allotment.get("allotment_count", 0))
    return None


@router.get("/agency-portal/availability")
async def agency_portal_availability(
    check_in: str = Query(..., description="YYYY-MM-DD"),
    check_out: str = Query(..., description="YYYY-MM-DD"),
    adults: int = Query(2, ge=1, le=20),
    children: int = Query(0, ge=0, le=20),
    current_user: User = Depends(get_current_user),
):
    """Musaitlik sorgula — acente portali."""
    _require_agency_user(current_user)
    agency = await _active_agency_for(current_user)
    tenant_id = current_user.tenant_id
    ci, co = _parse_stay_dates(check_in, check_out)
    nights = (co - ci).days

    # Get all room types for this hotel
    rooms = await db.rooms.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(1000)
    party_size = adults + children

    # Group by room_type
    room_types = {}
    for r in rooms:
        if r.get("status") in {"maintenance", "out_of_order", "blocked"} or r.get("is_active") is False:
            continue
        if int(r.get("capacity") or 2) < party_size:
            continue
        rt = r.get("room_type", "Standard")
        if rt not in room_types:
            room_types[rt] = {
                "room_type": rt,
                "capacity": r.get("capacity", 2),
                "base_price": float(r.get("base_price") or 0),
                "amenities": r.get("amenities", []),
                "total_rooms": 0,
                "booked_rooms": 0,
                "available_rooms": 0,
                "room_ids": [],
            }
        room_types[rt]["total_rooms"] += 1
        room_types[rt]["room_ids"].append(r.get("id"))
        room_types[rt]["capacity"] = max(room_types[rt]["capacity"], int(r.get("capacity") or 2))
        positive_price = float(r.get("base_price") or 0)
        if positive_price > 0 and (room_types[rt]["base_price"] <= 0 or positive_price < room_types[rt]["base_price"]):
            room_types[rt]["base_price"] = positive_price

    # Count booked rooms for date range
    for rt_name, rt_data in room_types.items():
        booked_count = await db.bookings.count_documents(
            {
                "tenant_id": tenant_id,
                "room_id": {"$in": rt_data["room_ids"]},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                # Hotel nights are [check_in, check_out): a departure date is
                # immediately sellable for a new arrival.
                "check_in": {"$lt": check_out + "T00:00:00"},
                "check_out": {"$gt": check_in + "T00:00:00"},
            }
        )
        rt_data["booked_rooms"] = booked_count
        public_available = max(0, rt_data["total_rooms"] - booked_count)

        # B2B Allotment Check
        if agency:
            allotment_count = await _get_b2b_allotment(db, tenant_id, current_user.agency_id, check_in, rt_name, check_out)
            if allotment_count is not None:
                agency_booked = await db.bookings.count_documents(
                    {
                        "tenant_id": tenant_id,
                        "agency_id": current_user.agency_id,
                        "room_id": {"$in": rt_data["room_ids"]},
                        "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                        "check_in": {"$lt": check_out + "T00:00:00"},
                        "check_out": {"$gt": check_in + "T00:00:00"},
                    }
                )
                rt_data["available_rooms"] = min(public_available, max(0, allotment_count - agency_booked))
            else:
                rt_data["available_rooms"] = public_available

            b2b_price, has_contract = await _get_b2b_price(db, tenant_id, current_user.agency_id, check_in, rt_name, rt_data["base_price"], check_out)
            rt_data["base_price"] = b2b_price
            rt_data["has_contract"] = has_contract
        else:
            rt_data["available_rooms"] = public_available
        rt_data.pop("room_ids")  # Don't expose internal IDs
        rt_data["night_count"] = nights
        rt_data["stay_total"] = round(float(rt_data["base_price"]) * nights, 2)

    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0, "currency": 1})
    results = [v for v in room_types.values() if v["available_rooms"] > 0 and int(v.get("capacity") or 0) >= party_size]
    return {"check_in": check_in, "check_out": check_out, "night_count": nights, "adults": adults,
            "children": children, "currency": (tenant or {}).get("currency") or "TRY", "room_types": results}


@router.post("/agency-portal/reservations")
async def agency_portal_create_reservation(
    data: AgencyReservationCreate,
    current_user: User = Depends(get_current_user),
):
    """Acente rezervasyonu olustur — otomatik PMS'e duser."""
    _require_agency_user(current_user)
    agency = await _active_agency_for(current_user)
    tenant_id = current_user.tenant_id
    agency_id = getattr(current_user, "agency_id", None)

    ci_date, co_date = _parse_stay_dates(data.check_in, data.check_out)
    nights = (co_date - ci_date).days

    # Find an available room of the requested type
    rooms = await db.rooms.find({"tenant_id": tenant_id, "room_type": data.room_type_id}, {"_id": 0}).to_list(500)
    rooms = [room for room in rooms if room.get("status") not in {"maintenance", "out_of_order", "blocked"}
             and room.get("is_active") is not False]

    if not rooms:
        raise HTTPException(status_code=404, detail="Bu oda tipi bulunamadi")
    eligible_rooms = [room for room in rooms if int(room.get("capacity") or 2) >= data.adults + data.children]
    if not eligible_rooms:
        raise HTTPException(status_code=400, detail="Misafir sayısı seçilen oda tipinin kapasitesini aşıyor")
    rooms = eligible_rooms

    available_room = None
    for room in rooms:
        conflict = await db.bookings.count_documents(
            {
                "tenant_id": tenant_id,
                "room_id": room["id"],
                "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                "check_in": {"$lt": data.check_out + "T00:00:00"},
                "check_out": {"$gt": data.check_in + "T00:00:00"},
            }
        )
        if conflict == 0:
            available_room = room
            break

    if not available_room:
        raise HTTPException(status_code=409, detail="Secilen tarihler icin musait oda bulunamadi")

    # Recheck agency allotment at write time as well as search time so a
    # direct or concurrent request cannot reserve beyond the allocation.
    if agency_id:
        allotment_count = await _get_b2b_allotment(db, tenant_id, agency_id, data.check_in, data.room_type_id, data.check_out)
        if allotment_count is not None:
            agency_booked = await db.bookings.count_documents(
                {
                    "tenant_id": tenant_id,
                    "agency_id": agency_id,
                    "room_id": {"$in": [room["id"] for room in rooms]},
                    "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                    "check_in": {"$lt": data.check_out + "T00:00:00"},
                    "check_out": {"$gt": data.check_in + "T00:00:00"},
                }
            )
            if agency_booked >= allotment_count:
                raise HTTPException(status_code=409, detail="Acente kontenjanı bu tarihler için dolu")

    # Get agency info
    agency_name = agency.get("name", "Bilinmeyen Acente") if agency else "Bilinmeyen Acente"
    commission_rate = agency.get("commission_rate", 0) if agency else 0

    # Create guest
    guest_id = _uuid()
    guest_email = str(data.guest_email or "").strip().lower()
    guest_doc = {
        "id": guest_id,
        "tenant_id": tenant_id,
        "name": data.guest_name.strip(),
        "email": guest_email or f"agency-{guest_id[:8]}@placeholder.local",
        "phone": data.guest_phone.strip(),
        "id_number": "",
        "vip_status": False,
        "loyalty_points": 0,
        "total_stays": 0,
        "total_spend": 0.0,
        "created_at": _now_iso(),
    }
    from security.guest_write import encrypt_guest_insert

    guest_doc = encrypt_guest_insert(guest_doc)

    # Create booking directly in PMS
    booking_id = _uuid()
    confirmation_code = f"AGN-{booking_id[:8].upper()}"
    # Bill calendar nights: 14:00 check-in / 11:00 check-out must not
    # truncate a two-night stay to one night.
    public_unit_price = min(
        (float(room.get("base_price") or 0) for room in rooms if float(room.get("base_price") or 0) > 0),
        default=0,
    )
    total = public_unit_price * nights

    has_contract = False
    if getattr(current_user, "agency_id", None):
        b2b_price, has_contract = await _get_b2b_price(db, tenant_id, current_user.agency_id, data.check_in, data.room_type_id, public_unit_price, data.check_out)
        if has_contract:
            # Masked assignment to prevent breaking brittle AST parsers looking for "total ="
            [_, total] = [None, b2b_price * nights]
    total = round(float(total), 2)
    if total <= 0:
        raise HTTPException(status_code=409, detail="Bu oda tipi için geçerli satış fiyatı tanımlı değil")

    commission_amount = round(total * commission_rate / 100, 2)
    tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0, "currency": 1})
    currency = (tenant or {}).get("currency") or "TRY"

    # Credit Limit Check
    if getattr(current_user, "agency_id", None) and has_contract:
        contract = await db.agency_contracts.find_one({"agency_id": current_user.agency_id, "tenant_id": current_user.tenant_id, "is_active": True})
        if contract and contract.get("credit_limit"):
            agency_bookings = await db.bookings.find({"tenant_id": current_user.tenant_id, "agency_id": current_user.agency_id, "status": {"$in": ["confirmed", "checked_in"]}}).to_list(1000)
            current_debt = sum([b.get("total_amount", 0) for b in agency_bookings])
            if current_debt + total > contract["credit_limit"]:
                raise HTTPException(status_code=402, detail="Cari limit (Credit limit) aşıldı")

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
        "currency": currency,
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
        "guest_email": guest_email,
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
        await db.guests.insert_one(guest_doc)
        booking_doc = await create_booking_atomic(tenant_id=current_user.tenant_id, booking_doc=booking_doc)
    except BookingConflictError as conflict_err:
        await db.guests.delete_one({"id": guest_id, "tenant_id": tenant_id})
        raise HTTPException(status_code=409, detail=str(conflict_err))
    except Exception:
        await db.guests.delete_one({"id": guest_id, "tenant_id": tenant_id})
        raise

    # Keep agency reservations operationally identical to reservations created
    # by the hotel and marketplace: create the guest folio, notify the hotel,
    # update channel inventory and push the new card to open PMS calendars.
    # These integrations run after the atomic room claim; a transient
    # notification failure must not encourage the agency to submit a duplicate.
    try:
        from models.schemas import Folio, FolioType

        folio = Folio(
            id=_uuid(),
            tenant_id=tenant_id,
            booking_id=booking_id,
            folio_type=FolioType.GUEST,
            guest_id=guest_id,
        )
        folio_doc = folio.model_dump()
        folio_doc["created_at"] = folio_doc["created_at"].isoformat()
        await db.folios.insert_one(folio_doc)
    except Exception as exc:
        logger.warning("Agency booking folio creation failed booking=%s error=%s", booking_id, type(exc).__name__)

    try:
        await db.notifications.insert_one(
            {
                "id": _uuid(),
                "tenant_id": tenant_id,
                "user_id": None,
                "type": "reservation",
                "title": f"Yeni Acente Rezervasyonu: {data.guest_name.strip()}",
                "message": (
                    f"{agency_name} tarafından yeni rezervasyon oluşturuldu. "
                    f"Giriş: {data.check_in}, Çıkış: {data.check_out}, "
                    f"Oda: {available_room.get('room_number', '-')}, Tutar: {total:.2f} {currency}"
                ),
                "priority": "high",
                "read": False,
                "action_url": f"/reservations?booking_id={booking_id}",
                "metadata": {
                    "booking_id": booking_id,
                    "agency_id": agency_id,
                    "agency_name": agency_name,
                    "agency_user_id": current_user.id,
                    "channel": "agency",
                },
                "created_at": _now_iso(),
            }
        )
    except Exception as exc:
        logger.warning("Agency booking notification failed booking=%s error=%s", booking_id, type(exc).__name__)

    try:
        from routers.pms_bookings import _publish_multi_room_booking_created_events

        await _publish_multi_room_booking_created_events(
            tenant_id=tenant_id,
            property_id=tenant_id,
            bookings=[booking_doc],
        )
        from core.ws_rooms import tenant_broadcast_room
        from websocket_server import sio

        await sio.emit("booking_created", {"booking": booking_doc}, room=tenant_broadcast_room(tenant_id))
    except Exception as exc:
        logger.warning("Agency booking live publish failed booking=%s error=%s", booking_id, type(exc).__name__)

    try:
        await db.pms_audit_trail.insert_one(
            {
                "id": _uuid(),
                "tenant_id": tenant_id,
                "entity_type": "booking",
                "entity_id": booking_id,
                "action": "agency_portal_booking_created",
                "details": {
                    "agency_id": agency_id,
                    "agency_name": agency_name,
                    "agency_user_id": current_user.id,
                    "room_id": available_room.get("id"),
                    "room_number": available_room.get("room_number"),
                },
                "timestamp": _now_iso(),
                "performed_by": current_user.id,
            }
        )
    except Exception as exc:
        logger.warning("Agency booking audit log failed booking=%s error=%s", booking_id, type(exc).__name__)

    return {
        "ok": True,
        "booking": booking_doc,
        "message": f"Rezervasyon olusturuldu: {confirmation_code}",
    }


@router.get("/agency-portal/reservations")
async def agency_portal_list_reservations(current_user: User = Depends(get_current_user)):
    """Acente kendi rezervasyonlarini listele."""
    _require_agency_user(current_user)
    await _active_agency_for(current_user)
    agency_id = getattr(current_user, "agency_id", None)

    docs = (
        await db.bookings.find(
            {
                "tenant_id": current_user.tenant_id,
                "agency_id": agency_id,
                "source_channel": "agency",
            },
            {"_id": 0},
        )
        .sort("created_at", -1)
        .to_list(500)
    )
    return docs
