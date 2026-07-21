"""
Exely Auto-Import Service
Automatically converts exely_reservations → PMS bookings + guests + room assignments.
Called after each successful pull.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core.database import db

logger = logging.getLogger(__name__)


async def auto_import_reservation(tenant_id: str, channel_res: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a single exely_reservation into a PMS booking, or update an existing one.
    Returns {"success": True/False, "pms_booking_id": ...}
    """
    external_id = channel_res.get("external_id", "")
    state = channel_res.get("state", "")

    # Skip cancelled
    if state == "cancelled":
        return {"success": False, "reason": "cancelled"}

    # If already imported AND status is "updated", route to modification handler
    pms_booking_id = channel_res.get("pms_booking_id")
    if pms_booking_id and channel_res.get("pms_status") == "updated":
        return await _update_existing_booking(tenant_id, channel_res)

    # Skip already imported (no changes)
    if channel_res.get("pms_status") == "imported" and pms_booking_id:
        return {"success": False, "reason": "already_imported"}

    # Room type mapping
    rooms_data = channel_res.get("rooms", [])
    first_room = rooms_data[0] if rooms_data else {}
    exely_room_code = first_room.get("room_type_code", "")

    pms_room_type = None
    mapping_resolved = False
    if exely_room_code:
        mapping = await db.exely_room_mappings.find_one(
            {"tenant_id": tenant_id, "exely_room_code": exely_room_code},
            {"_id": 0},
        )
        if mapping and mapping.get("pms_room_type"):
            pms_room_type = mapping.get("pms_room_type")
            mapping_resolved = True

    # HARD-FAIL korunur: eslestirilemeyen rezervasyonu "Standard" olarak
    # sessizce iceri ALMAYIZ. Tutma (hold) + ACIL alarm olusturulur,
    # rezervasyon action-needed kalir; teslimat (delivery) ONAYLANMAZ.
    if channel_res.get("pms_status") == "pending_mapping" and exely_room_code and not mapping_resolved:
        from domains.channel_manager.providers.unmatched_hold import (
            create_unmatched_reservation_hold,
        )

        try:
            hold = await create_unmatched_reservation_hold(
                provider="exely",
                tenant_id=tenant_id,
                external_id=external_id,
                check_in=channel_res.get("checkin_date", ""),
                check_out=channel_res.get("checkout_date", ""),
                guest_name=channel_res.get("guest_name", ""),
                room_type_code=exely_room_code,
                rate_plan_code=first_room.get("rate_plan_code", ""),
                total_amount=float(channel_res.get("total", 0) or 0),
                currency=channel_res.get("currency", "TRY"),
                adults=first_room.get("adults", 1) or 1,
                children=first_room.get("children", 0) or 0,
                channel=channel_res.get("channel", "exely"),
                property_id=tenant_id,
            )
            if hold.get("booking_id"):
                await db.exely_reservations.update_one(
                    {"tenant_id": tenant_id, "external_id": external_id},
                    {
                        "$set": {
                            "pms_booking_id": hold["booking_id"],
                            "pms_status": "pending_mapping",
                        }
                    },
                )
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[EXELY-IMPORT] unmatched hold olusturma hatasi {external_id}: {e}")
        return {"success": False, "reason": "pending_mapping"}

    if not pms_room_type:
        pms_room_type = "Standard"

    # Eslestirme cozuldu -> varsa onceki tutmayi rebind ile serbest birak
    # (sentinel kilitler + tutma kaydi silinir) ki cift sayim olmasin.
    if mapping_resolved:
        from domains.channel_manager.providers.unmatched_hold import (
            release_unmatched_reservation_hold,
        )

        try:
            await release_unmatched_reservation_hold(
                tenant_id=tenant_id,
                external_id=external_id,
                reason="mapping_resolved",
                delete_hold=True,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[EXELY-IMPORT] unmatched hold rebind hatasi {external_id}: {e}")

    # Find or create guest
    guest_name = channel_res.get("guest_name", "")
    guest_first = channel_res.get("guest_firstname", "")
    guest_last = channel_res.get("guest_lastname", "")
    guest_email = channel_res.get("guest_email", "") or f"exely-{external_id}@channel.import"
    guest_phone = channel_res.get("guest_phone", "")

    from security.encrypted_lookup import build_guest_pii_query

    guest = await db.guests.find_one(
        {"tenant_id": tenant_id, **build_guest_pii_query("email", guest_email)},
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
            "created_at": datetime.now(UTC).isoformat(),
        }
        from security.guest_write import encrypt_guest_insert

        await db.guests.insert_one(encrypt_guest_insert({**guest}))
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
    now = datetime.now(UTC).isoformat()

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

    from core.atomic_booking import BookingConflictError, assert_pending_assignment, create_booking_atomic

    try:
        await create_booking_atomic(tenant_id=tenant_id, booking_doc={**booking})
    except BookingConflictError:
        logger.warning("OTA import conflict for %s room=%s, creating as unassigned", external_id, booking.get("room_id"))
        booking["room_id"] = None
        booking["status"] = "confirmed"
        booking["allocation_source"] = "pending_assignment"
        assert_pending_assignment(booking)
        await db.bookings.insert_one({**booking})
        booking.pop("_id", None)

    # Update channel reservation
    await db.exely_reservations.update_one(
        {"tenant_id": tenant_id, "external_id": external_id},
        {
            "$set": {
                "pms_status": "imported",
                "pms_booking_id": booking_id,
                "imported_at": now,
            }
        },
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

    logger.info(f"[EXELY-IMPORT] {external_id} -> booking {booking_id}, type {pms_room_type} (unassigned), guest {guest_name}")

    return {
        "success": True,
        "pms_booking_id": booking_id,
        "guest_id": guest["id"],
        "room_number": None,
        "room_type": pms_room_type,
    }


async def _update_existing_booking(tenant_id: str, channel_res: dict[str, Any]) -> dict[str, Any]:
    """
    Update an existing PMS booking when the Exely reservation has been modified
    (guest name change, date change, room type change, etc.).
    """
    external_id = channel_res.get("external_id", "")
    pms_booking_id = channel_res.get("pms_booking_id")
    now = datetime.now(UTC).isoformat()

    # Get existing PMS booking
    existing_booking = await db.bookings.find_one(
        {"id": pms_booking_id, "tenant_id": tenant_id},
        {"_id": 0},
    )
    if not existing_booking:
        logger.warning(f"[EXELY-IMPORT] PMS booking {pms_booking_id} not found for update")
        return {"success": False, "reason": "pms_booking_not_found"}

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
        pms_room_type = existing_booking.get("room_type", "Standard")

    # Gather new values from channel reservation
    new_guest_name = channel_res.get("guest_name", "")
    new_checkin = channel_res.get("checkin_date", "")
    new_checkout = channel_res.get("checkout_date", "")
    new_total = float(channel_res.get("total", 0))
    adults = first_room.get("adults", 1) or 1
    children = first_room.get("children", 0) or 0
    nights = channel_res.get("nights", 1) or 1
    base_rate = new_total / nights if nights > 0 else new_total

    # Detect what changed for the notification
    changes = []
    old_name = existing_booking.get("guest_name", "")
    old_checkin = (existing_booking.get("check_in", "") or "")[:10]
    old_checkout = (existing_booking.get("check_out", "") or "")[:10]
    old_room_type = existing_booking.get("room_type", "")

    if new_guest_name and new_guest_name != old_name:
        changes.append(f"İsim: {old_name} → {new_guest_name}")
    if new_checkin[:10] != old_checkin:
        changes.append(f"Giriş: {old_checkin} → {new_checkin[:10]}")
    if new_checkout[:10] != old_checkout:
        changes.append(f"Çıkış: {old_checkout} → {new_checkout[:10]}")
    if pms_room_type != old_room_type:
        changes.append(f"Oda Tipi: {old_room_type} → {pms_room_type}")

    # Build update fields
    update_fields = {
        "guest_name": new_guest_name or old_name,
        "check_in": new_checkin or existing_booking.get("check_in"),
        "check_out": new_checkout or existing_booking.get("check_out"),
        "room_type": pms_room_type,
        "total_amount": new_total if new_total > 0 else existing_booking.get("total_amount", 0),
        "base_rate": base_rate if new_total > 0 else existing_booking.get("base_rate", 0),
        "adults": adults,
        "children": children,
        "guests_count": adults + children,
        "updated_at": now,
        "last_modified_by": "channel_manager",
    }

    # If room type changed, clear room assignment (needs re-assignment)
    if pms_room_type != old_room_type:
        update_fields["room_id"] = None
        update_fields["room_number"] = None

    # Update PMS booking
    await db.bookings.update_one(
        {"id": pms_booking_id, "tenant_id": tenant_id},
        {"$set": update_fields},
    )

    # Update guest record if name changed
    guest_id = existing_booking.get("guest_id")
    if guest_id and new_guest_name and new_guest_name != old_name:
        name_parts = new_guest_name.split()
        from security.search_normalize import normalized_set_for_update

        _guest_set = {
            "name": new_guest_name,
            "first_name": name_parts[0] if name_parts else "",
            "last_name": " ".join(name_parts[1:]) if len(name_parts) > 1 else "",
        }
        _guest_set.update(normalized_set_for_update(_guest_set, collection="guests"))
        await db.guests.update_one(
            {"id": guest_id, "tenant_id": tenant_id},
            {"$set": _guest_set},
        )

    # Mark exely_reservation as imported again
    await db.exely_reservations.update_one(
        {"tenant_id": tenant_id, "external_id": external_id},
        {"$set": {"pms_status": "imported", "updated_at": now}},
    )

    # Create notification
    if changes:
        change_text = ", ".join(changes)
        try:
            await db.notifications.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "type": "reservation_modified",
                    "severity": "info",
                    "title": f"Rezervasyon Güncellendi - {new_guest_name or old_name}",
                    "message": f"OTA değişiklik: {change_text}",
                    "related_entity": "reservation",
                    "related_id": pms_booking_id,
                    "read": False,
                    "created_at": now,
                }
            )
        except Exception as e:
            logger.warning(f"[EXELY-IMPORT] Modification notification failed: {e}")

    logger.info(f"[EXELY-IMPORT] Updated PMS booking {pms_booking_id} for {external_id}: {', '.join(changes) if changes else 'minor update'}")

    return {
        "success": True,
        "pms_booking_id": pms_booking_id,
        "action": "updated",
        "changes": changes,
    }


async def auto_import_pending(tenant_id: str, provider=None) -> dict[str, Any]:
    """Import all pending exely_reservations for a tenant.
    If provider is given, also confirm delivery to Exely after each successful import."""
    pending = await db.exely_reservations.find(
        {"tenant_id": tenant_id, "pms_status": {"$in": ["pending", "updated", "pending_mapping"]}, "state": {"$ne": "cancelled"}},
        {"_id": 0},
    ).to_list(100)

    imported = 0
    updated = 0
    errors = []
    for res in pending:
        result = await auto_import_reservation(tenant_id, res)
        if result.get("success"):
            if result.get("action") == "updated":
                updated += 1
            else:
                imported += 1

            # Confirm delivery to Exely so it marks the reservation as delivered
            if provider and result.get("pms_booking_id"):
                try:
                    external_id = res.get("external_id", "")
                    pms_booking_id = result["pms_booking_id"]
                    create_dt = res.get("provider_last_modified_at") or res.get("created_at")
                    modify_dt = res.get("provider_last_modified_at")
                    confirm_result = await provider.confirm_delivery(
                        external_id,
                        pms_booking_id,
                        create_datetime=create_dt,
                        last_modify_datetime=modify_dt,
                        res_status="Reserved",
                    )
                    if confirm_result.success:
                        await db.exely_reservations.update_one(
                            {"tenant_id": tenant_id, "external_id": external_id},
                            {"$set": {"delivery_confirmed": True, "delivery_confirmed_at": datetime.now(UTC).isoformat()}},
                        )
                        logger.info(f"[EXELY-IMPORT] Delivery confirmed for {external_id} -> PMS {pms_booking_id}")
                    else:
                        logger.warning(f"[EXELY-IMPORT] Delivery confirm failed for {external_id}: {confirm_result.error}")
                except Exception as e:
                    logger.warning(f"[EXELY-IMPORT] Delivery confirm error for {res.get('external_id')}: {e}")
        else:
            errors.append({"external_id": res.get("external_id"), "reason": result.get("reason")})

    # Also process pending cancellations
    cancelled = await process_pending_cancellations(tenant_id)

    logger.info(f"[EXELY-IMPORT] Tenant {tenant_id}: {imported}/{len(pending)} imported, {updated} updated")
    return {"imported": imported, "updated": updated, "total": len(pending), "errors": errors, "cancelled": cancelled}


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
    now = datetime.now(UTC).isoformat()

    from domains.channel_manager.providers.unmatched_hold import (
        release_unmatched_reservation_hold,
    )

    for res in pending_cancels:
        pms_booking_id = res.get("pms_booking_id")
        if not pms_booking_id:
            continue

        # Iptal: varsa eslesmeyen-tutmanin sentinel kilitlerini serbest birak
        # (tutma kaydi cancelled olarak isaretlenir). Tutma degilse no-op.
        try:
            await release_unmatched_reservation_hold(
                tenant_id=tenant_id,
                external_id=res["external_id"],
                reason="ota_cancelled",
                delete_hold=False,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[EXELY-IMPORT] unmatched hold iptal release hatasi {res.get('external_id')}: {e}")

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
            {
                "$set": {
                    "status": "cancelled",
                    "cancelled_at": now,
                    "cancelled_by": "channel_manager",
                }
            },
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
            await db.notifications.insert_one(
                {
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
                }
            )
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
