"""
Domain Router: Online Check-in & Pre-Arrival

Extracted from legacy_routes.py — online check-in submission,
upsell acceptance, pre-arrival communications.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import MODULE_ROLES  # v97 DW
from modules.pms_core.role_permission_service import require_module as require_module_v97  # v97 DW

router = APIRouter(prefix="/api", tags=["checkin-domain"])


def _allow_frontdesk_or_guest(current_user: User = Depends(get_current_user)) -> User:
    """Allow staff with frontdesk module access OR a guest_app user (own check-in)."""
    role = getattr(current_user.role, "value", str(current_user.role))
    allowed = {getattr(r, "value", str(r)) for r in MODULE_ROLES.get("frontdesk", set())}
    allowed.add("guest_app")
    if role not in allowed:
        from core.security import _is_super_admin
        if not _is_super_admin(current_user):
            raise HTTPException(status_code=403, detail="Online check-in yetkisi yok")
    return current_user


@router.post("/checkin/online")
async def submit_online_checkin(
    checkin_data: dict,
    current_user: User = Depends(_allow_frontdesk_or_guest),
):
    """Online check-in submission"""
    from domains.guest.online_checkin_models import OnlineCheckinRequest

    request = OnlineCheckinRequest(**checkin_data)

    booking = await db.bookings.find_one(
        {"id": request.booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    # Guest-app callers may only submit for their own booking, with the canonical
    # 06:00-on-check-in-day eligibility gate (mirror of the mobile UI rule).
    role = getattr(current_user.role, "value", str(current_user.role))
    if role == "guest_app":
        guest_doc = await db.guests.find_one(
            {"email": current_user.email, "tenant_id": current_user.tenant_id}, {"_id": 0, "id": 1}
        )
        if not guest_doc or booking.get("guest_id") != guest_doc.get("id"):
            raise HTTPException(status_code=403, detail="Bu rezervasyon size ait değil")
        # Digital-signature contract: typed name + explicit consent both required.
        if not (request.signature_consent and (request.signature_text or "").strip()):
            raise HTTPException(status_code=400, detail="Dijital imza onayı gerekli")
        # 06:00 eligibility: online check-in opens at 06:00 on the check-in
        # day in the property's local timezone. Mobile uses device-local time
        # (Turkish guests in Türkiye), so we evaluate the gate in
        # Europe/Istanbul to keep client and server consistent.
        ci_raw = booking.get("check_in")
        if ci_raw:
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo("Europe/Istanbul")
            except Exception:
                tz = None
            try:
                ci_str = ci_raw if isinstance(ci_raw, str) else ci_raw.isoformat()
                ci_date = datetime.fromisoformat(ci_str.replace("Z", "+00:00")).date()
            except Exception:
                ci_date = None
            if ci_date is not None:
                now_local = datetime.now(tz) if tz else datetime.now(UTC)
                today = now_local.date()
                if today < ci_date or (today == ci_date and now_local.hour < 6):
                    raise HTTPException(
                        status_code=400,
                        detail="Online check-in giriş günü saat 06:00'dan itibaren açılır",
                    )

    checkin_record = {
        "id": str(uuid.uuid4()),
        "booking_id": request.booking_id,
        "tenant_id": current_user.tenant_id,
        "guest_id": booking["guest_id"],
        "passport_number": request.passport_number,
        "passport_expiry": request.passport_expiry,
        "nationality": request.nationality,
        "estimated_arrival_time": request.estimated_arrival_time,
        "flight_number": request.flight_number,
        "coming_from": request.coming_from,
        "room_view": request.room_view,
        "floor_preference": request.floor_preference,
        "bed_type": request.bed_type,
        "pillow_type": request.pillow_type,
        "room_temperature": request.room_temperature,
        "special_requests": request.special_requests,
        "dietary_restrictions": request.dietary_restrictions,
        "accessibility_needs": request.accessibility_needs,
        "newspaper_preference": request.newspaper_preference,
        "smoking_preference": request.smoking_preference,
        "connecting_rooms": request.connecting_rooms,
        "quiet_room": request.quiet_room,
        "mobile_number": request.mobile_number,
        "whatsapp_number": request.whatsapp_number,
        # Identity & digital signature
        "id_photo_base64": request.id_photo_base64,
        "id_photo_uploaded": bool(request.id_photo_base64),
        "signature_text": (request.signature_text or "").strip() or None,
        "signature_consent": bool(request.signature_consent),
        "signed_at": datetime.now(UTC).isoformat() if request.signature_consent else None,
        "status": "pending",
        "submitted_at": datetime.now(UTC).isoformat(),
        "processed": False,
    }
    await db.online_checkins.insert_one(checkin_record)

    await db.bookings.update_one(
        {"id": request.booking_id, "tenant_id": current_user.tenant_id},
        {
            "$set": {
                "online_checkin_completed": True,
                "online_checkin_at": datetime.now(UTC).isoformat(),
                "special_requests": request.special_requests,
                "estimated_arrival_time": request.estimated_arrival_time,
            }
        },
    )

    upsell_offers = []
    current_room = await db.rooms.find_one(
        {"id": booking["room_id"], "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if current_room and current_room["room_type"] == "Standard":
        upsell_offers.append({
            "id": str(uuid.uuid4()),
            "type": "room_upgrade",
            "title": "Deluxe Oda Upgrade",
            "description": "Konaklama deneyiminizi Deluxe odamiza yukseltin! Daha genis alan, daha iyi manzara.",
            "original_price": 100.0,
            "discounted_price": 75.0,
            "savings": 25.0,
        })

    if request.estimated_arrival_time:
        try:
            arrival_hour = int(request.estimated_arrival_time.split(":")[0])
            if arrival_hour < 14:
                upsell_offers.append({
                    "id": str(uuid.uuid4()),
                    "type": "early_checkin",
                    "title": "Erken Check-in Garantisi",
                    "description": f"Odaniz {request.estimated_arrival_time} saatinde hazir olacak.",
                    "original_price": 50.0,
                    "discounted_price": 35.0,
                    "savings": 15.0,
                })
        except Exception:
            pass

    for offer in upsell_offers:
        offer_doc = {
            **offer,
            "booking_id": request.booking_id,
            "tenant_id": current_user.tenant_id,
            "guest_id": booking["guest_id"],
            "status": "pending",
            "offered_at": datetime.now(UTC).isoformat(),
        }
        await db.upsell_offers.insert_one(offer_doc)

    return {
        "checkin_id": checkin_record["id"],
        "booking_id": request.booking_id,
        "status": "approved",
        "room_number": current_room.get("room_number") if current_room else None,
        "estimated_ready_time": "14:00",
        "upsell_offers": upsell_offers,
        "check_in_instructions": "Lutfen resepsiyona geldiginizde kimliginizi ibraz edin.",
        "message": "Online check-in basariyla tamamlandi!",
    }


@router.get("/checkin/online/{booking_id}")
async def get_online_checkin_status(
    booking_id: str, current_user: User = Depends(get_current_user)
):
    """Online check-in durumunu getir"""
    checkin = await db.online_checkins.find_one(
        {"booking_id": booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not checkin:
        return {"completed": False, "checkin": None}
    return {"completed": True, "checkin": checkin}


@router.post("/upsell/accept")
async def accept_upsell_offer(
    data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Upsell teklifini kabul et"""
    offer_id = data.get("offer_id")
    action = data.get("action")

    offer = await db.upsell_offers.find_one(
        {"id": offer_id, "tenant_id": current_user.tenant_id}
    )
    if not offer:
        raise HTTPException(status_code=404, detail="Teklif bulunamadi")

    await db.upsell_offers.update_one(
        {"id": offer_id},
        {"$set": {"status": "accepted" if action == "accept" else "rejected", "responded_at": datetime.now(UTC).isoformat()}},
    )

    if action == "accept":
        booking_id = offer.get("booking_id")
        charge = {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "booking_id": booking_id,
            "charge_category": "upsell",
            "description": offer.get("title"),
            "amount": offer.get("discounted_price") or offer.get("original_price"),
            "posted_at": datetime.now(UTC).isoformat(),
            "voided": False,
        }

        folio = await db.folios.find_one(
            {"booking_id": booking_id, "folio_type": "guest"}, {"_id": 0}
        )
        if folio:
            charge["folio_id"] = folio["id"]
            await db.folio_charges.insert_one(charge)

        return {
            "success": True,
            "message": f'{offer.get("title")} basariyla eklendi!',
            "charge_added": True,
            "amount": charge["amount"],
        }
    else:
        return {"success": True, "message": "Teklif reddedildi", "charge_added": False}


@router.get("/pre-arrival/communications/{booking_id}")
async def get_pre_arrival_communications(
    booking_id: str, current_user: User = Depends(get_current_user)
):
    """Pre-arrival iletisim gecmisi"""
    communications = await db.pre_arrival_communications.find(
        {"booking_id": booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    ).to_list(100)

    return {"booking_id": booking_id, "communications": communications, "total": len(communications)}
