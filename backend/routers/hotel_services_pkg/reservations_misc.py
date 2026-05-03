"""Auto-split from hotel_services.py — backward-compatible sub-router."""
import asyncio
import html as _html
import logging
import re as _re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from models.schemas import User, _ensure_hotel_context
from modules.pms_core.role_permission_service import require_module as require_module_v97
from modules.pms_core.role_permission_service import require_module as require_module_v99
from modules.pms_core.role_permission_service import require_module as require_module_v101
from modules.pms_core.role_permission_service import require_op

from ._common import (
    _e, _safe_logo_src, _clean_doc,
    RoomStatusUpdate,
    WakeUpCallCreate, WakeUpCallUpdate, _fire_due_wake_up_alerts, _annotate_due,
    LostFoundCreate, LostFoundUpdate,
    HotelSettingsUpdate,
    GroupFolioMerge, GroupPaymentRequest, GroupBulkPaymentRequest,
    CancelReservationRequest,
    InvoiceItemSelection,
    CreateCariAccount,
)

logger = logging.getLogger(__name__)
sub_router = APIRouter()

@sub_router.post("/reservations/{booking_id}/cancel")
async def cancel_reservation(
    booking_id: str,
    body: CancelReservationRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    update_data = {
        "status": "no_show" if body.apply_noshow else "cancelled",
        "cancelled_at": datetime.now(UTC).isoformat(),
        "cancellation_reason": body.reason,
        "cancel_type": body.cancel_type,
    }

    if body.apply_noshow and body.noshow_charge_amount and body.noshow_charge_amount > 0:
        charge_id = str(uuid.uuid4())
        await db.folios.insert_one({
            "id": charge_id,
            "tenant_id": tid,
            "booking_id": booking_id,
            "type": "charge",
            "category": "no_show",
            "description": f"No-Show Ucreti ({body.noshow_charge_type or 'ozel'})",
            "amount": body.noshow_charge_amount,
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": current_user.name,
        })
        update_data["noshow_charge"] = body.noshow_charge_amount

    await db.bookings.update_one({"id": booking_id, "tenant_id": tid}, {"$set": update_data})

    # Inventory release: iptal/no-show sonrası odanın gece kilitleri serbest bırakılır.
    # No-show'da first night charge tutulsa da inventory release edilir (misafir gelmediği için).
    # release_booking_nights audit timeline'ına 'lock_released' event'i de yazar (INV-6).
    try:
        from core.atomic_booking import release_booking_nights
        released_count = await release_booking_nights(
            tenant_id=tid,
            booking_id=booking_id,
            reason=update_data["status"],
        )
        logger.info(
            "Released %s room-night locks after %s of booking %s",
            released_count, update_data["status"], booking_id,
        )
    except Exception as exc:
        logger.error("Lock release failed for booking %s: %s", booking_id, exc)

    # Channel availability auto-sync: iptal sonrası müsaitlik güncelle
    try:
        import asyncio

        from domains.channel_manager.availability_auto_sync import sync_availability_after_booking
        asyncio.create_task(sync_availability_after_booking(
            tenant_id=tid,
            room_id=booking.get("room_id", ""),
            check_in=booking.get("check_in", ""),
            check_out=booking.get("check_out", ""),
        ))
    except Exception:
        pass

    await db.reservation_history.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "action": "cancelled" if not body.apply_noshow else "marked_noshow",
        "actor": current_user.name,
        "details": {
            "reason": body.reason,
            "cancel_type": body.cancel_type,
            "noshow": body.apply_noshow,
            "noshow_charge": body.noshow_charge_amount if body.apply_noshow else None,
        },
        "created_at": datetime.now(UTC).isoformat(),
    })

    return {"success": True, "status": update_data["status"], "message": "Rezervasyon iptal edildi"}


# ═══════════════════════════════════════════════════
# 11. VOUCHER GENERATION
# ═══════════════════════════════════════════════════

@sub_router.get("/available-rooms-by-type")
async def get_available_rooms_by_type(
    check_in: str | None = None,
    check_out: str | None = None,
    current_user: User = Depends(get_current_user),
):
    # Tur 3: defaults — today / today+1 when omitted
    from datetime import date as _d
    from datetime import timedelta as _td
    if not check_in:
        check_in = _d.today().isoformat()
    if not check_out:
        check_out = (_d.today() + _td(days=1)).isoformat()
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    all_rooms = []
    async for r in db.rooms.find({"tenant_id": tid, "is_active": True}, {"_id": 0}).sort("room_number", 1):
        all_rooms.append(r)

    conflicting_room_ids = set()
    async for b in db.bookings.find({
        "tenant_id": tid,
        "status": {"$nin": ["cancelled", "checked_out", "no_show"]},
        "check_in": {"$lt": check_out},
        "check_out": {"$gt": check_in},
    }, {"_id": 0, "room_id": 1}):
        if b.get("room_id"):
            conflicting_room_ids.add(b["room_id"])

    room_types = {}
    for r in all_rooms:
        rt = r.get("room_type", "Standard")
        if rt not in room_types:
            room_types[rt] = {"type": rt, "rooms": [], "base_price": r.get("base_price", 0)}
        is_available = r["id"] not in conflicting_room_ids
        room_types[rt]["rooms"].append({**r, "is_available": is_available})

    return {"room_types": list(room_types.values())}


# ═══════════════════════════════════════════════════
# 15. CREATE CARI ACCOUNT
# ═══════════════════════════════════════════════════


@sub_router.post("/cari-accounts/create")
async def create_cari_account(
    body: CreateCariAccount,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v101 DW
):
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    account_id = str(uuid.uuid4())
    account = {
        "id": account_id,
        "tenant_id": tid,
        "name": body.name,
        "account_type": body.account_type,
        "tax_id": body.tax_id,
        "tax_office": body.tax_office,
        "address": body.address,
        "phone": body.phone,
        "email": body.email,
        "balance": 0,
        "is_active": True,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.name,
    }
    await db.cari_accounts.insert_one(account)
    account.pop("_id", None)

    return {"success": True, "account": account}

