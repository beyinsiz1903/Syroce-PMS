"""
Exely Auto-Import Service
Automatically converts exely_reservations → PMS bookings + guests + room assignments.
Called after each successful pull.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from core.database import db

logger = logging.getLogger(__name__)


async def auto_import_reservation(tenant_id: str, channel_res: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a single exely_reservation into a PMS booking.
    Returns {"success": True/False, "pms_booking_id": ...}
    """
    external_id = channel_res.get("external_id", "")
    state = channel_res.get("state", "")

    # Skip non-confirmed or already imported
    if state == "cancelled":
        return {"success": False, "reason": "cancelled"}
    if channel_res.get("pms_status") == "imported" and channel_res.get("pms_booking_id"):
        return {"success": False, "reason": "already_imported"}

    # Room type mapping
    rooms_data = channel_res.get("rooms", [])
    first_room = rooms_data[0] if rooms_data else {}
    exely_room_code = first_room.get("room_type_code", "")

    pms_room_type = None
    if exely_room_code:
        mapping = await db.exely_room_mappings.find_one(
            {"tenant_id": tenant_id, "exely_room_code": exely_room_code},
            {"_id": 0},
        )
        if mapping:
            pms_room_type = mapping.get("pms_room_type")

    if not pms_room_type:
        pms_room_type = "Standard"

    # Find available room of matching type
    room = await db.rooms.find_one(
        {"tenant_id": tenant_id, "room_type": pms_room_type, "status": "available"},
        {"_id": 0},
    )
    if not room:
        room = await db.rooms.find_one(
            {"tenant_id": tenant_id, "status": "available"},
            {"_id": 0},
        )
    if not room:
        logger.warning(f"[EXELY-IMPORT] No available room for {external_id} ({pms_room_type})")
        return {"success": False, "reason": "no_available_room"}

    # Find or create guest
    guest_name = channel_res.get("guest_name", "")
    guest_first = channel_res.get("guest_firstname", "")
    guest_last = channel_res.get("guest_lastname", "")
    guest_email = channel_res.get("guest_email", "") or f"exely-{external_id}@channel.import"
    guest_phone = channel_res.get("guest_phone", "")

    guest = await db.guests.find_one(
        {"tenant_id": tenant_id, "email": guest_email},
        {"_id": 0},
    )
    if not guest:
        guest = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "first_name": guest_first or (guest_name.split()[0] if guest_name else "Misafir"),
            "last_name": guest_last or (guest_name.split()[-1] if len(guest_name.split()) > 1 else ""),
            "name": guest_name or "Kanal Misafiri",
            "email": guest_email,
            "phone": guest_phone or "",
            "id_number": "",
            "nationality": channel_res.get("guest_country", ""),
            "vip_level": "none",
            "loyalty_tier": "none",
            "total_stays": 0,
            "notes": f"Exely kanal rezervasyonu ({external_id})",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.guests.insert_one({**guest})
        guest.pop("_id", None)

    # Build PMS booking
    checkin = channel_res.get("checkin_date", "")
    checkout = channel_res.get("checkout_date", "")
    total_amount = float(channel_res.get("total", 0))
    adults = first_room.get("adults", 1) or 1
    children = first_room.get("children", 0) or 0
    nights = channel_res.get("nights", 1) or 1
    base_rate = total_amount / nights if nights > 0 else total_amount

    booking_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    booking = {
        "id": booking_id,
        "tenant_id": tenant_id,
        "guest_id": guest["id"],
        "room_id": room["id"],
        "guest_name": guest_name,
        "room_number": room.get("room_number", ""),
        "check_in": checkin,
        "check_out": checkout,
        "adults": adults,
        "children": children,
        "children_ages": [],
        "guests_count": adults + children,
        "total_amount": total_amount,
        "base_rate": base_rate,
        "paid_amount": 0.0,
        "status": "confirmed",
        "channel": "exely",
        "source_channel": "exely",
        "origin": "channel_import",
        "hold_status": "none",
        "allocation_source": "channel",
        "rate_plan": first_room.get("rate_plan_code", "Standard"),
        "special_requests": channel_res.get("note", ""),
        "group_booking_id": None,
        "company_id": None,
        "ota_channel": "exely",
        "ota_confirmation": external_id,
        "ota_reference_id": external_id,
        "created_at": now,
    }

    await db.bookings.insert_one({**booking})

    # Update room status based on check-in date
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    checkin_date = checkin[:10] if checkin else ""
    if checkin_date <= today:
        await db.rooms.update_one({"id": room["id"]}, {"$set": {"status": "occupied"}})

    # Update channel reservation
    await db.exely_reservations.update_one(
        {"tenant_id": tenant_id, "external_id": external_id},
        {"$set": {
            "pms_status": "imported",
            "pms_booking_id": booking_id,
            "imported_at": now,
        }},
    )

    # Create notification for the new booking
    try:
        notification = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "user_id": None,
            "type": "success",
            "title": "Yeni Rezervasyon",
            "message": f"{guest_name} - Oda {room.get('room_number', '')} ({pms_room_type}), {checkin} → {checkout}",
            "priority": "high",
            "category": "reservation",
            "read": False,
            "created_at": now,
            "action_url": "/bookings",
        }
        await db.notifications.insert_one({**notification})
    except Exception as e:
        logger.warning(f"[EXELY-IMPORT] Notification creation failed: {e}")

    logger.info(
        f"[EXELY-IMPORT] {external_id} -> booking {booking_id}, "
        f"room {room.get('room_number')}, guest {guest_name}"
    )

    return {
        "success": True,
        "pms_booking_id": booking_id,
        "guest_id": guest["id"],
        "room_number": room.get("room_number", ""),
        "room_type": pms_room_type,
    }


async def auto_import_pending(tenant_id: str) -> Dict[str, Any]:
    """Import all pending exely_reservations for a tenant."""
    pending = await db.exely_reservations.find(
        {"tenant_id": tenant_id, "pms_status": {"$in": ["pending", "updated"]}, "state": {"$ne": "cancelled"}},
        {"_id": 0},
    ).to_list(100)

    imported = 0
    errors = []
    for res in pending:
        result = await auto_import_reservation(tenant_id, res)
        if result.get("success"):
            imported += 1
        else:
            errors.append({"external_id": res.get("external_id"), "reason": result.get("reason")})

    logger.info(f"[EXELY-IMPORT] Tenant {tenant_id}: {imported}/{len(pending)} auto-imported")
    return {"imported": imported, "total": len(pending), "errors": errors}
