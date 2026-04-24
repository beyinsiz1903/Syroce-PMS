"""
Virtual Credit Card (VCC) Router — Secure card viewing with 3-view limit.

OTA/Agency virtual credit cards are stored encrypted (AES-256-GCM).
Hoteliers can view card details a maximum of 3 times, enforced at the API level.
Every view is logged in the activity log for audit trail.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from models.schemas import User, _ensure_hotel_context
from modules.pms_core.role_permission_service import (
    RolePermissionService,
    require_op,  # v97 DW
)
from security.field_encryption import get_field_encryption_service

_role_perm = RolePermissionService()


def _enforce_perm(role: str, op: str):
    """Bug CS (v58) — PCI VCC endpoint'leri için RBAC zorunlu."""
    _role_perm.enforce_permission(role, op)

router = APIRouter(prefix="/api/pms", tags=["vcc"])

MAX_VCC_VIEWS = 3

_enc_svc = None


def _get_enc():
    global _enc_svc
    if _enc_svc is None:
        _enc_svc = get_field_encryption_service()
    return _enc_svc


class VCCStore(BaseModel):
    card_holder: str
    card_number: str
    expiry: str
    cvv: str | None = None
    card_type: str = "virtual"  # virtual, credit, debit


class VCCManualStore(BaseModel):
    card_holder: str
    card_number: str
    expiry: str
    cvv: str | None = None
    card_type: str = "virtual"


def _mask_card(number: str) -> str:
    """Mask card number: show first 6 and last 4 digits."""
    clean = number.replace(" ", "").replace("-", "")
    if len(clean) <= 10:
        return clean[:2] + "*" * (len(clean) - 4) + clean[-2:]
    return clean[:6] + "*" * (len(clean) - 10) + clean[-4:]


@router.post("/reservations/{booking_id}/vcc")
async def store_vcc(
    booking_id: str,
    data: VCCStore,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v97 DW
):
    """Store a virtual/credit card for a booking (encrypted at rest)."""
    _ensure_hotel_context(current_user)
    _enforce_perm(current_user.role, "store_card")  # Bug CS
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    enc = _get_enc()

    existing = await db.vcc_cards.find_one(
        {"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}
    )
    if existing:
        raise HTTPException(status_code=409, detail="Bu rezervasyon icin zaten kart bilgisi mevcut")

    card_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "card_holder_enc": enc.encrypt_value(data.card_holder),
        "card_number_enc": enc.encrypt_value(data.card_number),
        "expiry_enc": enc.encrypt_value(data.expiry),
        "cvv_enc": enc.encrypt_value(data.cvv) if data.cvv else None,
        "card_type": data.card_type,
        "card_mask": _mask_card(data.card_number),
        "view_count": 0,
        "max_views": MAX_VCC_VIEWS,
        "locked": False,
        "stored_by": current_user.name or current_user.email,
        "source": booking.get("source_channel", "manual"),
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.vcc_cards.insert_one({**card_doc})
    card_doc.pop("_id", None)

    # Activity log
    await db.reservation_activity_log.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "action": "vcc_stored",
        "actor": current_user.name or current_user.email,
        "details": {"card_type": data.card_type, "card_mask": card_doc["card_mask"]},
        "created_at": datetime.now(UTC).isoformat(),
    })

    return {
        "success": True,
        "vcc": {
            "id": card_doc["id"],
            "card_mask": card_doc["card_mask"],
            "card_type": card_doc["card_type"],
            "view_count": 0,
            "max_views": MAX_VCC_VIEWS,
            "locked": False,
        },
    }


@router.get("/reservations/{booking_id}/vcc/status")
async def get_vcc_status(
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get VCC status without consuming a view."""
    _ensure_hotel_context(current_user)
    _enforce_perm(current_user.role, "view_card_status")  # Bug CS
    tid = current_user.tenant_id

    card = await db.vcc_cards.find_one(
        {"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}
    )
    if not card:
        return {"has_vcc": False}

    return {
        "has_vcc": True,
        "vcc": {
            "id": card["id"],
            "card_mask": card.get("card_mask", "****"),
            "card_type": card.get("card_type", "virtual"),
            "view_count": card.get("view_count", 0),
            "max_views": card.get("max_views", MAX_VCC_VIEWS),
            "locked": card.get("locked", False) or card.get("view_count", 0) >= card.get("max_views", MAX_VCC_VIEWS),
            "source": card.get("source", ""),
            "stored_by": card.get("stored_by", ""),
            "created_at": card.get("created_at", ""),
        },
    }


@router.post("/reservations/{booking_id}/vcc/reveal")
async def reveal_vcc(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v97 DW
):
    """Reveal full card details. Consumes 1 of 3 views. Enforced at API level."""
    _ensure_hotel_context(current_user)
    _enforce_perm(current_user.role, "reveal_card")  # Bug CS — PCI critical
    tid = current_user.tenant_id

    card = await db.vcc_cards.find_one(
        {"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}
    )
    if not card:
        raise HTTPException(status_code=404, detail="Kart bilgisi bulunamadi")

    current_views = card.get("view_count", 0)
    max_views = card.get("max_views", MAX_VCC_VIEWS)

    if card.get("locked") or current_views >= max_views:
        raise HTTPException(
            status_code=403,
            detail=f"Kart bilgisi goruntuleme hakki doldu ({max_views}/{max_views}). Daha fazla goruntuleyemezsiniz.",
        )

    # Increment view count atomically
    result = await db.vcc_cards.update_one(
        {
            "booking_id": booking_id,
            "tenant_id": tid,
            "view_count": {"$lt": max_views},
        },
        {
            "$inc": {"view_count": 1},
            "$set": {
                "last_viewed_at": datetime.now(UTC).isoformat(),
                "last_viewed_by": current_user.name or current_user.email,
            },
        },
    )

    if result.modified_count == 0:
        raise HTTPException(
            status_code=403,
            detail="Kart bilgisi goruntuleme hakki doldu. Eszamanli istek engellendi.",
        )

    new_view_count = current_views + 1

    # Lock if final view
    if new_view_count >= max_views:
        await db.vcc_cards.update_one(
            {"booking_id": booking_id, "tenant_id": tid},
            {"$set": {"locked": True, "locked_at": datetime.now(UTC).isoformat()}},
        )

    # Decrypt card details
    enc = _get_enc()
    card_holder = enc.decrypt_value(card.get("card_holder_enc", ""))
    card_number = enc.decrypt_value(card.get("card_number_enc", ""))
    expiry = enc.decrypt_value(card.get("expiry_enc", ""))
    cvv = enc.decrypt_value(card.get("cvv_enc", "")) if card.get("cvv_enc") else None

    # Activity log
    await db.reservation_activity_log.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "action": "vcc_revealed",
        "actor": current_user.name or current_user.email,
        "details": {
            "view_number": new_view_count,
            "remaining_views": max_views - new_view_count,
            "card_mask": card.get("card_mask", "****"),
        },
        "created_at": datetime.now(UTC).isoformat(),
    })

    return {
        "success": True,
        "card": {
            "card_holder": card_holder,
            "card_number": card_number,
            "expiry": expiry,
            "cvv": cvv,
            "card_type": card.get("card_type", "virtual"),
        },
        "view_count": new_view_count,
        "max_views": max_views,
        "remaining_views": max_views - new_view_count,
        "locked": new_view_count >= max_views,
    }


@router.delete("/reservations/{booking_id}/vcc")
async def delete_vcc(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v97 DW
):
    """Delete VCC data (admin only or after checkout)."""
    _ensure_hotel_context(current_user)
    _enforce_perm(current_user.role, "delete_card")  # Bug CS — prevents view-counter reset abuse
    tid = current_user.tenant_id

    card = await db.vcc_cards.find_one(
        {"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}
    )
    if not card:
        raise HTTPException(status_code=404, detail="Kart bilgisi bulunamadi")

    await db.vcc_cards.delete_one({"booking_id": booking_id, "tenant_id": tid})

    await db.reservation_activity_log.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "action": "vcc_deleted",
        "actor": current_user.name or current_user.email,
        "details": {"card_mask": card.get("card_mask", "****")},
        "created_at": datetime.now(UTC).isoformat(),
    })

    return {"success": True, "message": "Kart bilgisi silindi"}
