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

router = APIRouter(prefix="/api", tags=["checkin-domain"])


@router.post("/checkin/online")
async def submit_online_checkin(
    checkin_data: dict,
    current_user: User = Depends(get_current_user),
):
    """Online check-in submission"""
    from domains.guest.online_checkin_models import OnlineCheckinRequest

    request = OnlineCheckinRequest(**checkin_data)

    booking = await db.bookings.find_one(
        {"id": request.booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

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
        "status": "pending",
        "submitted_at": datetime.now(UTC).isoformat(),
        "processed": False,
    }
    await db.online_checkins.insert_one(checkin_record)

    await db.bookings.update_one(
        {"id": request.booking_id},
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
    current_room = await db.rooms.find_one({"id": booking["room_id"]}, {"_id": 0})
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
    data: dict, current_user: User = Depends(get_current_user)
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
