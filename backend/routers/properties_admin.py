"""
Properties Admin Router
=======================
Grup yöneticisinin kendi zincirindeki (chain) otelleri yönetmesi için uçlar.

Mevcut süper-admin paneli (`/api/admin/tenants`) tüm sistemi yönetir; bu router
ise yetkili tenant kullanıcısının yalnızca kendi chain'indeki otellere erişmesini
sağlar:

* GET    /api/properties/chain           — chain'deki otelleri listele
* POST   /api/properties                  — yeni otel ekle (chain'e otomatik bağla)
* PUT    /api/properties/{tenant_id}     — chain'deki otelin bilgilerini güncelle
* DELETE /api/properties/{tenant_id}     — soft archive (subscription_status="archived")

Chain otomasyonu:
- Mevcut yönetici tenant'ında `chain_id` yoksa, ilk yeni otel eklendiğinde
  yeni UUID üretilir; hem mevcut hem yeni tenant'a yazılır → "ilk grup
  oluşumu". Sonraki eklemelerde aynı chain_id kullanılır.
- Yetki: `admin` ya da üstü rol (admin/super_admin/owner). Süper-admin tüm
  sistemde işlem yapabilir.

Cross-tenant okuma/yazma için `_sys_db` (raw motor) kullanılır; her işlemden önce
hedef tenant'ın chain üyeliği `_chain_tenant_ids` ile kontrol edilir.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from core.audit import log_audit_event
from core.security import _is_super_admin, get_current_user
from core.tenant_db import get_system_db
from models.schemas import User

router = APIRouter(prefix="/api/properties", tags=["properties-admin"])

_sys_db = get_system_db()


# ── Pydantic models ─────────────────────────────────────────────────


class PropertyCreate(BaseModel):
    property_name: str = Field(..., min_length=2, max_length=120)
    property_type: str | None = "hotel"
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    address: str | None = None
    location: str | None = None
    total_rooms: int | None = Field(default=50, ge=1, le=10000)
    plan: str | None = "core_small_hotel"
    subscription_tier: str | None = "basic"


class PropertyUpdate(BaseModel):
    property_name: str | None = Field(default=None, min_length=2, max_length=120)
    property_type: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    address: str | None = None
    location: str | None = None
    total_rooms: int | None = Field(default=None, ge=1, le=10000)


# ── Helpers ─────────────────────────────────────────────────────────


def _require_admin(user: User):
    """Sadece admin/super_admin/owner rolleri otel yönetimi yapabilir."""
    if _is_super_admin(user):
        return
    role = getattr(user, "role", None)
    role_name = role.value if hasattr(role, "value") else str(role or "").lower()
    allowed = {"admin", "owner", "super_admin"}
    roles_list = [(r.value if hasattr(r, "value") else str(r)).lower() for r in (getattr(user, "roles", None) or [])]
    if role_name in allowed or any(r in allowed for r in roles_list):
        return
    raise HTTPException(
        status_code=403,
        detail="Bu işlem için otel yöneticisi yetkisi gerekiyor",
    )


async def _chain_tenant_ids(current_user: User) -> list[str]:
    """Kullanıcının chain'indeki tenant_id'leri getir."""
    own_tid = current_user.tenant_id
    if _is_super_admin(current_user):
        cursor = _sys_db.tenants.find({}, {"_id": 0, "tenant_id": 1, "id": 1})
        ids: list[str] = []
        async for t in cursor:
            tid = t.get("tenant_id") or t.get("id")
            if tid:
                ids.append(tid)
        if own_tid and own_tid not in ids:
            ids.insert(0, own_tid)
        return ids
    own = await _sys_db.tenants.find_one(
        {"$or": [{"tenant_id": own_tid}, {"id": own_tid}]},
        {"_id": 0, "chain_id": 1},
    )
    chain_id = (own or {}).get("chain_id")
    if not chain_id:
        return [own_tid]
    cursor = _sys_db.tenants.find({"chain_id": chain_id}, {"_id": 0, "tenant_id": 1, "id": 1})
    ids = []
    async for t in cursor:
        tid = t.get("tenant_id") or t.get("id")
        if tid:
            ids.append(tid)
    if own_tid and own_tid not in ids:
        ids.insert(0, own_tid)
    return ids


def _serialize_tenant(doc: dict, current_tid: str) -> dict:
    """Tenant doc'unu UI'a uygun forma getir."""
    tid = doc.get("tenant_id") or doc.get("id")
    return {
        "tenant_id": tid,
        "hotel_id": doc.get("hotel_id"),
        "property_name": doc.get("property_name") or doc.get("hotel_name") or doc.get("name") or "",
        "property_type": doc.get("property_type", "hotel"),
        "contact_email": doc.get("contact_email") or doc.get("email"),
        "contact_phone": doc.get("contact_phone") or doc.get("phone"),
        "address": doc.get("address"),
        "location": doc.get("location"),
        "total_rooms": doc.get("total_rooms"),
        "plan": doc.get("plan"),
        "subscription_tier": doc.get("subscription_tier"),
        "subscription_status": doc.get("subscription_status", "active"),
        "chain_id": doc.get("chain_id"),
        "created_at": doc.get("created_at"),
        "is_current": tid == current_tid,
    }


async def _generate_unique_hotel_id() -> str:
    """6-haneli unique hotel_id üret (auth.py'deki helper'ın yalın versiyonu)."""
    import random

    for _ in range(50):
        candidate = str(random.randint(100000, 999999))
        existing = await _sys_db.tenants.find_one({"hotel_id": candidate}, {"_id": 1})
        if not existing:
            return candidate
    # Çok düşük olasılık — fallback: UUID prefix
    return uuid.uuid4().hex[:6]


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/chain")
async def list_chain_properties(current_user: User = Depends(get_current_user)):
    """Kullanıcının zincirindeki tüm otelleri döndür.

    - Süper-admin → sistemdeki tüm oteller
    - chain_id varsa → kardeş tesisler
    - chain_id yoksa → sadece kendi tesisi
    """
    tenant_ids = await _chain_tenant_ids(current_user)
    cursor = _sys_db.tenants.find(
        {
            "$or": [
                {"tenant_id": {"$in": tenant_ids}},
                {"id": {"$in": tenant_ids}},
            ]
        },
        {"_id": 0},
    )
    docs = [d async for d in cursor]
    properties = [_serialize_tenant(d, current_user.tenant_id) for d in docs]
    # Mevcut tenant en üstte
    properties.sort(key=lambda p: (not p.get("is_current"), p.get("property_name") or ""))
    own = next((p for p in properties if p.get("is_current")), None)
    chain_id = own.get("chain_id") if own else None
    active_count = sum(1 for p in properties if p.get("subscription_status") != "archived")
    return {
        "current_tenant_id": current_user.tenant_id,
        "chain_id": chain_id,
        "is_super_admin": _is_super_admin(current_user),
        "total": len(properties),
        "active_count": active_count,
        "properties": properties,
    }


@router.post("")
async def create_property(
    payload: PropertyCreate,
    current_user: User = Depends(get_current_user),
):
    """Mevcut yöneticinin zincirine yeni bir otel ekle.

    İlk eklemede mevcut tenant'ta chain_id yoksa otomatik üretilir ve hem
    eski hem yeni tenant'a yazılır. Aynı isimde otel varsa kabul edilir
    (UI'da uyarı verilir, backend bloklamaz — chain'de aynı isim mümkün).
    """
    _require_admin(current_user)

    # Mevcut tenant doc'u (chain_id öğrenmek için)
    own = await _sys_db.tenants.find_one(
        {"$or": [{"tenant_id": current_user.tenant_id}, {"id": current_user.tenant_id}]},
        {"_id": 0},
    )
    if not own:
        # Süper-admin'in legacy seed'inde tenant doc eksik olabilir; yeni oluştur
        own = {
            "id": current_user.tenant_id,
            "tenant_id": current_user.tenant_id,
            "property_name": "Ana Otel",
        }
        await _sys_db.tenants.insert_one({**own, "created_at": datetime.now(UTC).isoformat()})

    chain_id = own.get("chain_id")
    new_chain = False
    if not chain_id:
        chain_id = str(uuid.uuid4())
        new_chain = True
        await _sys_db.tenants.update_one(
            {"$or": [{"tenant_id": current_user.tenant_id}, {"id": current_user.tenant_id}]},
            {"$set": {"chain_id": chain_id}},
        )

    new_tid = str(uuid.uuid4())
    hotel_id = await _generate_unique_hotel_id()
    now = datetime.now(UTC).isoformat()

    new_doc = {
        "id": new_tid,
        "tenant_id": new_tid,
        "hotel_id": hotel_id,
        "chain_id": chain_id,
        "property_name": payload.property_name,
        "property_type": payload.property_type or "hotel",
        "contact_email": payload.contact_email,
        "contact_phone": payload.contact_phone,
        "address": payload.address or "",
        "location": payload.location or "",
        "total_rooms": payload.total_rooms or 50,
        "plan": payload.plan or "core_small_hotel",
        "subscription_tier": payload.subscription_tier or "basic",
        "subscription_status": "active",
        "created_at": now,
        "modules": {"pms": True, "reports": True, "invoices": True, "ai": True},
    }
    await _sys_db.tenants.insert_one(new_doc)

    try:
        await log_audit_event(
            db=_sys_db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action="property_added",
            resource_type="tenant",
            resource_id=new_tid,
            details={
                "chain_id": chain_id,
                "new_chain": new_chain,
                "property_name": payload.property_name,
                "hotel_id": hotel_id,
            },
        )
    except Exception:  # pragma: no cover — audit failure must not block creation
        pass

    return {
        "ok": True,
        "new_chain": new_chain,
        "chain_id": chain_id,
        "property": _serialize_tenant(new_doc, current_user.tenant_id),
    }


@router.put("/{tenant_id}")
async def update_property(
    tenant_id: str,
    payload: PropertyUpdate,
    current_user: User = Depends(get_current_user),
):
    """Chain içindeki bir otelin bilgilerini güncelle."""
    _require_admin(current_user)

    chain_ids = await _chain_tenant_ids(current_user)
    if tenant_id not in chain_ids:
        raise HTTPException(status_code=403, detail="Bu otel sizin grup zincirinizde değil")

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")

    res = await _sys_db.tenants.update_one(
        {"$or": [{"tenant_id": tenant_id}, {"id": tenant_id}]},
        {"$set": {**updates, "updated_at": datetime.now(UTC).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Otel bulunamadı")

    try:
        await log_audit_event(
            db=_sys_db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action="property_updated",
            resource_type="tenant",
            resource_id=tenant_id,
            details={"fields": list(updates.keys())},
        )
    except Exception:
        pass

    doc = await _sys_db.tenants.find_one(
        {"$or": [{"tenant_id": tenant_id}, {"id": tenant_id}]},
        {"_id": 0},
    )
    return {"ok": True, "property": _serialize_tenant(doc or {}, current_user.tenant_id)}


@router.delete("/{tenant_id}")
async def archive_property(
    tenant_id: str,
    current_user: User = Depends(get_current_user),
):
    """Bir oteli soft-archive et (subscription_status='archived').

    Mevcut yöneticinin kendi tenant'ı arşivlenemez (kendini kilitlemeyi önle).
    Veriler silinmez; gerekirse tekrar 'active' yapılabilir.
    """
    _require_admin(current_user)

    if tenant_id == current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Kendi otelinizi arşivleyemezsiniz")

    chain_ids = await _chain_tenant_ids(current_user)
    if tenant_id not in chain_ids:
        raise HTTPException(status_code=403, detail="Bu otel sizin grup zincirinizde değil")

    res = await _sys_db.tenants.update_one(
        {"$or": [{"tenant_id": tenant_id}, {"id": tenant_id}]},
        {
            "$set": {
                "subscription_status": "archived",
                "archived_at": datetime.now(UTC).isoformat(),
            }
        },
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Otel bulunamadı")

    try:
        await log_audit_event(
            db=_sys_db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action="property_archived",
            resource_type="tenant",
            resource_id=tenant_id,
        )
    except Exception:
        pass

    return {"ok": True, "tenant_id": tenant_id, "status": "archived"}


@router.post("/{tenant_id}/restore")
async def restore_property(
    tenant_id: str,
    current_user: User = Depends(get_current_user),
):
    """Arşivlenmiş bir oteli tekrar aktif yap."""
    _require_admin(current_user)

    chain_ids = await _chain_tenant_ids(current_user)
    if tenant_id not in chain_ids:
        raise HTTPException(status_code=403, detail="Bu otel sizin grup zincirinizde değil")

    res = await _sys_db.tenants.update_one(
        {"$or": [{"tenant_id": tenant_id}, {"id": tenant_id}]},
        {"$set": {"subscription_status": "active"}, "$unset": {"archived_at": ""}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Otel bulunamadı")

    try:
        await log_audit_event(
            db=_sys_db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action="property_restored",
            resource_type="tenant",
            resource_id=tenant_id,
        )
    except Exception:
        pass

    return {"ok": True, "tenant_id": tenant_id, "status": "active"}
