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

    # Build PMS booking (room_id intentionally omitted – user assigns rooms via drag-and-drop)
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
        "room_id": None,
        "guest_name": guest_name,
        "room_number": None,
        "room_type": pms_room_type,
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
            "title": "Yeni Rezervasyon (Atanmamış)",
            "message": f"{guest_name} - {pms_room_type}, {checkin} → {checkout}. Oda ataması bekleniyor.",
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
        f"type {pms_room_type} (unassigned), guest {guest_name}"
    )

    return {
        "success": True,
        "pms_booking_id": booking_id,
        "guest_id": guest["id"],
        "room_number": None,
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

    # Also process pending cancellations
    cancelled = await process_pending_cancellations(tenant_id)

    logger.info(f"[EXELY-IMPORT] Tenant {tenant_id}: {imported}/{len(pending)} auto-imported")
    return {"imported": imported, "total": len(pending), "errors": errors, "cancelled": cancelled}


async def process_pending_cancellations(tenant_id: str) -> int:
    """
    Find exely_reservations with pms_status=cancellation_pending that have a linked
    PMS booking, cancel the PMS booking, and create a notification.
    """
    pending_cancels = await db.exely_reservations.find(
        {"tenant_id": tenant_id, "pms_status": "cancellation_pending", "pms_booking_id": {"$ne": None}},
        {"_id": 0},
    ).to_list(100)

    count = 0
    now = datetime.now(timezone.utc).isoformat()

    for res in pending_cancels:
        pms_booking_id = res.get("pms_booking_id")
        if not pms_booking_id:
            continue

        # Get the PMS booking before cancelling
        booking = await db.bookings.find_one(
            {"id": pms_booking_id, "tenant_id": tenant_id},
            {"_id": 0, "guest_name": 1, "room_id": 1, "check_in": 1, "check_out": 1, "status": 1},
        )
        if not booking or booking.get("status") == "cancelled":
            # Already cancelled or not found – mark as done
            await db.exely_reservations.update_one(
                {"tenant_id": tenant_id, "external_id": res["external_id"]},
                {"$set": {"pms_status": "cancellation_done"}},
            )
            continue

        # Cancel the PMS booking
        await db.bookings.update_one(
            {"id": pms_booking_id, "tenant_id": tenant_id},
            {"$set": {
                "status": "cancelled",
                "cancelled_at": now,
                "cancelled_by": "channel_manager",
            }},
        )

        # Free the room if assigned
        room_id = booking.get("room_id")
        if room_id:
            await db.rooms.update_one({"id": room_id}, {"$set": {"status": "available"}})

        # Create notification
        guest_name = booking.get("guest_name", "Misafir")
        check_in = (booking.get("check_in", "") or "")[:10]
        check_out = (booking.get("check_out", "") or "")[:10]
        try:
            await db.notifications.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "type": "reservation_cancelled",
                "severity": "warning",
                "title": f"OTA İptali - {guest_name}",
                "message": f"{guest_name} adlı misafirin {check_in} - {check_out} tarihli OTA rezervasyonu kanal tarafından iptal edildi.",
                "related_entity": "reservation",
                "related_id": pms_booking_id,
                "read": False,
                "created_at": now,
            })
        except Exception:
            pass

        # Mark the exely_reservation as cancellation done
        await db.exely_reservations.update_one(
            {"tenant_id": tenant_id, "external_id": res["external_id"]},
            {"$set": {"pms_status": "cancellation_done"}},
        )

        count += 1
        logger.info(f"[EXELY-IMPORT] Cancelled PMS booking {pms_booking_id} via OTA cancellation")

    return count
