"""
QR Rozet endpoint'leri.

Yollar
------
Misafir tarafı (current_user.role == GUEST):
  GET  /api/guest/qr/me?booking_id=...   — token üret/yenile
  GET  /api/guest/qr/charges/pending     — bekleyen şarj listesi
  POST /api/guest/qr/charges/{id}/approve — onayla
  POST /api/guest/qr/charges/{id}/reject  — reddet

Personel tarafı (front_desk / pos / supervisor / admin):
  POST /api/qr-badge/validate    — taranan token bilgi döner (charge yok)
  POST /api/qr-badge/charge      — token + tutar ile pending charge oluştur
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from models.enums import UserRole
from models.schemas import User
from modules.pms_core.role_permission_service import require_role

from . import service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Guest / QR Badge"])

# Şarj oluşturmaya izinli personel rolleri (front desk + POS + yönetim).
_STAFF_CHARGE_ROLES = (
    UserRole.SUPER_ADMIN,
    UserRole.ADMIN,
    UserRole.SUPERVISOR,
    UserRole.FRONT_DESK,
    UserRole.STAFF,
)


# ── Pydantic models ───────────────────────────────────────────────────────

class QrTokenResponse(BaseModel):
    token: str
    expires_at: str
    ttl_seconds: int
    booking_id: str


class QrValidateRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=32)


class QrChargeItem(BaseModel):
    name: str = Field(..., max_length=120)
    qty: float = Field(default=1.0, gt=0, le=999)
    price: float = Field(..., ge=0, le=50000)


class QrChargeRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=32)
    outlet: str = Field(..., max_length=40)
    amount: float = Field(..., gt=0, le=50000)
    description: str = Field(default="", max_length=240)
    items: list[QrChargeItem] | None = None
    currency: str = Field(default="TRY", min_length=3, max_length=3)
    outlet_name: str | None = Field(default=None, max_length=120)


class QrRejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=240)


# ── Helpers ───────────────────────────────────────────────────────────────

async def _resolve_guest_active_booking(
    *,
    user: User,
    booking_id_hint: str | None,
) -> tuple[str, str]:
    """Misafire ait aktif (in_house veya checked_in) booking'i bulur.
    `booking_id_hint` verilmişse onu doğrular, yoksa ilk aktifi seçer.

    Tenant izolasyonu: misafir hesabının `user.tenant_id` alanına bağlı
    kalınır — e-posta paylaşan başka bir tenant'taki guest/booking
    kazara seçilemez (architect Tur-15 bulgusu).

    Returns (tenant_id, booking_id).
    """
    if not user.tenant_id:
        raise HTTPException(400, "Misafir hesabının tenant'ı yok")

    # Misafir kayıtlarını e-posta + KENDİ tenant'ı içinde ara.
    guest_records = []
    async for g in db.guests.find({"email": user.email, "tenant_id": user.tenant_id}):
        guest_records.append(g)
    if not guest_records:
        raise HTTPException(404, "Bu hesaba bağlı misafir kaydı bulunamadı")

    guest_ids = [g["id"] for g in guest_records]

    query: dict[str, Any] = {
        "tenant_id": user.tenant_id,
        "guest_id": {"$in": guest_ids},
        "status": {"$in": ["checked_in", "in_house"]},
    }
    if booking_id_hint:
        query["id"] = booking_id_hint

    # En son oluşturulan aktif booking — birden fazla varsa deterministik.
    booking = await db.bookings.find_one(
        query, {"_id": 0}, sort=[("created_at", -1)]
    )
    if not booking:
        raise HTTPException(404, "Aktif (check-in) rezervasyon bulunamadı")

    return booking["tenant_id"], booking["id"]


# ── Misafir endpoint'leri ────────────────────────────────────────────────

@router.get("/guest/qr/me", response_model=QrTokenResponse)
async def get_my_qr_token(
    booking_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
):
    """Misafir kendi aktif booking'i için yeni QR token alır.

    Mobil bu endpoint'i 30 sn'de bir çağırır. Eski tokenlar otomatik
    `rotated` olur.
    """
    if current_user.role != UserRole.GUEST:
        raise HTTPException(403, "Sadece misafir hesapları QR rozet alabilir")

    tenant_id, bid = await _resolve_guest_active_booking(
        user=current_user, booking_id_hint=booking_id
    )

    result = await svc.issue_or_refresh_token(
        tenant_id=tenant_id,
        booking_id=bid,
        guest_user_id=current_user.id,
    )
    return QrTokenResponse(**result)


@router.get("/guest/qr/charges/pending")
async def get_my_pending_charges(
    current_user: User = Depends(get_current_user),
):
    """Misafirin onayını bekleyen (ve son 50) QR şarjları."""
    if current_user.role != UserRole.GUEST:
        raise HTTPException(403, "Sadece misafir hesapları kendi şarjını görebilir")

    # Tenant'ı bulmak için aktif booking'i kullanırız; tenant izolasyonu için.
    try:
        tenant_id, _ = await _resolve_guest_active_booking(
            user=current_user, booking_id_hint=None
        )
    except HTTPException:
        # Aktif booking yok → boş liste.
        return {"charges": [], "pending_count": 0}

    rows = await svc.list_pending_charges_for_guest(
        tenant_id=tenant_id, guest_user_id=current_user.id
    )
    pending = sum(1 for r in rows if r.get("status") == "pending_approval")
    return {"charges": rows, "pending_count": pending}


@router.post("/guest/qr/charges/{charge_id}/approve")
async def approve_my_charge(
    charge_id: str,
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.GUEST:
        raise HTTPException(403, "Sadece misafir hesapları onaylayabilir")

    tenant_id, _ = await _resolve_guest_active_booking(
        user=current_user, booking_id_hint=None
    )

    try:
        return await svc.approve_pending_charge(
            tenant_id=tenant_id,
            charge_id=charge_id,
            guest_user_id=current_user.id,
        )
    except ValueError as e:
        code = str(e)
        msg_map = {
            "not_found": (404, "Şarj bulunamadı"),
            "not_yours": (403, "Bu şarj size ait değil"),
            "not_pending": (409, "Bu şarj artık onaylanamaz"),
            "expired": (410, "Şarjın süresi doldu, personelden tekrar isteyin"),
            "folio_missing": (409, "Folyonuz açık değil — resepsiyona başvurun"),
            "folio_post_failed": (500, "Folyoya yazılamadı, lütfen tekrar deneyin"),
        }
        status, msg = msg_map.get(code, (400, code))
        raise HTTPException(status, msg) from None


@router.post("/guest/qr/charges/{charge_id}/reject")
async def reject_my_charge(
    charge_id: str,
    body: QrRejectRequest = QrRejectRequest(),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.GUEST:
        raise HTTPException(403, "Sadece misafir hesapları reddedebilir")

    tenant_id, _ = await _resolve_guest_active_booking(
        user=current_user, booking_id_hint=None
    )

    try:
        return await svc.reject_pending_charge(
            tenant_id=tenant_id,
            charge_id=charge_id,
            guest_user_id=current_user.id,
            reason=body.reason,
        )
    except ValueError as e:
        code = str(e)
        msg_map = {
            "not_found": (404, "Şarj bulunamadı"),
            "not_yours": (403, "Bu şarj size ait değil"),
            "not_pending": (409, "Bu şarj artık reddedilemez"),
        }
        status, msg = msg_map.get(code, (400, code))
        raise HTTPException(status, msg) from None


# ── Personel endpoint'leri ───────────────────────────────────────────────

@router.post("/qr-badge/validate")
async def staff_validate_qr(
    body: QrValidateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_role(*_STAFF_CHARGE_ROLES)),
):
    """POS/personel taranan QR'i doğrular. Şarj oluşturmaz —
    sadece misafir adı + oda + booking_id döner."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(400, "Personelin tenant_id'si yok")

    try:
        return await svc.validate_token(tenant_id=tenant_id, token=body.token.upper())
    except ValueError as e:
        code = str(e)
        msg_map = {
            "invalid": (404, "QR kodu geçersiz"),
            "expired": (410, "QR kodu süresi doldu, misafirden ekranı yenilemesini isteyin"),
            "not_in_house": (409, "Misafir şu an check-in olmamış"),
        }
        status, msg = msg_map.get(code, (400, code))
        raise HTTPException(status, msg) from None


@router.post("/qr-badge/charge")
async def staff_create_charge(
    body: QrChargeRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_role(*_STAFF_CHARGE_ROLES)),
):
    """POS/personel pending charge oluşturur. Misafire push gider.

    Misafir 5 dakika içinde onaylamazsa şarj otomatik expired olur.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(400, "Personelin tenant_id'si yok")

    items_payload = [i.model_dump() for i in body.items] if body.items else None

    try:
        result = await svc.create_pending_charge(
            tenant_id=tenant_id,
            token=body.token.upper(),
            outlet=body.outlet,
            amount=body.amount,
            description=body.description,
            items=items_payload,
            currency=body.currency.upper(),
            outlet_name=body.outlet_name,
            created_by_user_id=current_user.id,
        )
    except ValueError as e:
        code = str(e)
        msg_map = {
            "invalid_token": (404, "QR kodu geçersiz"),
            "expired_token": (410, "QR kodu süresi doldu"),
            "invalid_amount": (400, "Tutar geçersiz"),
            "amount_too_high": (400, "Tek seferde 50.000 üstü şarj kabul edilmiyor"),
            "invalid_outlet": (400, "Geçersiz outlet"),
        }
        status, msg = msg_map.get(code, (400, code))
        raise HTTPException(status, msg) from None

    return {
        "charge_id": result["id"],
        "status": result["status"],
        "amount": result["amount"],
        "currency": result["currency"],
        "expires_at": result["expires_at"],
        "outlet": result["outlet"],
        "outlet_name": result["outlet_name"],
    }
