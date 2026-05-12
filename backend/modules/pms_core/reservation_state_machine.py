"""
Reservation State Machine - Enforces valid state transitions for the reservation lifecycle.
Hospitality-standard states: pending, confirmed, guaranteed, checked_in, checked_out, no_show, cancelled
"""
import logging
from datetime import UTC, datetime

from core.database import db

logger = logging.getLogger("pms_core.reservation_state_machine")

# Valid state transitions
VALID_TRANSITIONS: dict[str, list[str]] = {
    "pending": ["confirmed", "guaranteed", "cancelled"],
    "confirmed": ["checked_in", "cancelled", "no_show", "guaranteed"],
    "guaranteed": ["checked_in", "cancelled", "no_show"],
    "checked_in": ["checked_out"],  # checked_in cannot be cancelled directly
    "checked_out": [],  # terminal
    "cancelled": [],    # terminal
    "no_show": [],      # terminal
}

# States that block cancellation
NON_CANCELLABLE_STATES = {"checked_in", "checked_out", "cancelled", "no_show"}

# States that block no-show transition (terminal + occupied lifecycle states).
# Symmetric with NON_CANCELLABLE_STATES — production hardening, May 2026.
# Without this guard, a second no-show call on an already-no_show booking
# silently accumulated audit rows because validate_transition treats
# current==new as ("no_change", True) for idempotency at the wire layer.
NON_NOSHOWABLE_STATES = {"checked_in", "checked_out", "cancelled", "no_show"}

# States that count as "active" for availability
ACTIVE_BOOKING_STATES = {"pending", "confirmed", "guaranteed", "checked_in"}


class ReservationStateMachine:
    """Enforces reservation lifecycle transitions with business rules."""

    def validate_transition(self, current_status: str, new_status: str) -> tuple[bool, str]:
        """Check if a state transition is valid. Returns (is_valid, reason)."""
        if current_status == new_status:
            return True, "no_change"

        allowed = VALID_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            return False, f"Transition from '{current_status}' to '{new_status}' is not allowed. Valid targets: {allowed}"
        return True, "ok"

    async def check_overbooking(self, tenant_id: str, room_id: str, check_in: str, check_out: str, exclude_booking_id: str = None) -> tuple[bool, list[dict]]:
        """Check if the room has overlapping active bookings. Returns (has_conflict, conflicting_bookings)."""
        query = {
            "tenant_id": tenant_id,
            "room_id": room_id,
            "status": {"$in": list(ACTIVE_BOOKING_STATES)},
            "check_in": {"$lt": check_out},
            "check_out": {"$gt": check_in},
        }
        if exclude_booking_id:
            query["id"] = {"$ne": exclude_booking_id}

        conflicts = await db.bookings.find(query, {"_id": 0, "id": 1, "check_in": 1, "check_out": 1, "status": 1, "guest_id": 1}).to_list(10)
        return len(conflicts) > 0, conflicts

    async def check_duplicate_reservation(self, tenant_id: str, guest_id: str, room_id: str, check_in: str, check_out: str) -> dict | None:
        """Detect duplicate reservation: same guest, same room, same dates."""
        existing = await db.bookings.find_one({
            "tenant_id": tenant_id,
            "guest_id": guest_id,
            "room_id": room_id,
            "check_in": check_in,
            "check_out": check_out,
            "status": {"$in": list(ACTIVE_BOOKING_STATES)},
        }, {"_id": 0, "id": 1, "status": 1})
        return existing

    async def handle_cancellation(self, tenant_id: str, booking: dict, cancelled_by: str, reason: str = None) -> dict:
        """Cancel a reservation with inventory release, notification, and audit trail."""
        current_status = booking.get("status")
        if current_status in NON_CANCELLABLE_STATES:
            return {"success": False, "error": f"Cannot cancel reservation in '{current_status}' state"}

        now = datetime.now(UTC)
        update_fields = {
            "status": "cancelled",
            "cancelled_at": now.isoformat(),
            "cancelled_by": cancelled_by,
            "cancellation_reason": reason or "No reason provided",
            "updated_at": now.isoformat(),
        }

        await db.bookings.update_one(
            {"id": booking["id"], "tenant_id": tenant_id},
            {"$set": update_fields}
        )

        # Release room-night locks for overbooking prevention (INV-6: audit trail)
        try:
            from core.atomic_booking import release_booking_nights
            await release_booking_nights(
                tenant_id, booking["id"],
                reason=f"cancelled:{reason or 'no_reason'}",
                correlation_id=booking.get("correlation_id"),
            )
        except Exception as e:
            logger.warning("Failed to release night locks for %s: %s", booking["id"], e)

        # Release the room if it was assigned
        room_id = booking.get("room_id")
        if room_id:
            room = await db.rooms.find_one({"id": room_id, "tenant_id": tenant_id}, {"_id": 0, "status": 1})
            if room and room.get("status") == "occupied" and booking.get("status") == "checked_in":
                pass  # checked_in cannot be cancelled
            # For non-checked-in bookings, room doesn't need status change (it's not occupied yet)

        # Restore availability in rate_calendar if applicable
        try:
            check_in = booking.get("check_in", "")[:10]
            check_out = booking.get("check_out", "")[:10]
            room_doc = await db.rooms.find_one({"id": room_id, "tenant_id": tenant_id}, {"_id": 0, "room_type": 1}) if room_id else None
            if room_doc and check_in and check_out:
                room_type = room_doc.get("room_type", "")
                # Find matching exely mapping for room_type_code
                mapping = await db.exely_room_mappings.find_one(
                    {"tenant_id": tenant_id, "pms_room_type": room_type}, {"_id": 0, "exely_room_code": 1}
                )
                if mapping:
                    room_type_code = mapping["exely_room_code"]
                    await db.rate_calendar.update_many(
                        {
                            "tenant_id": tenant_id,
                            "room_type_code": room_type_code,
                            "date": {"$gte": check_in, "$lt": check_out},
                            "availability": {"$exists": True},
                        },
                        {"$inc": {"availability": 1}},
                    )
        except Exception:
            pass  # Non-critical: availability update failure should not block cancellation

        # Create notification for cancellation
        try:
            import uuid as _uuid
            guest_id = booking.get("guest_id")
            guest_name = booking.get("guest_name", "")
            if not guest_name and guest_id:
                guest_doc = await db.guests.find_one({"id": guest_id}, {"_id": 0, "name": 1})
                guest_name = guest_doc.get("name", "Misafir") if guest_doc else "Misafir"

            room_number = booking.get("room_number", "")
            if not room_number and room_id:
                room_doc2 = await db.rooms.find_one({"id": room_id}, {"_id": 0, "room_number": 1})
                room_number = room_doc2.get("room_number", "") if room_doc2 else ""

            await db.notifications.insert_one({
                "id": str(_uuid.uuid4()),
                "tenant_id": tenant_id,
                "type": "reservation_cancelled",
                "severity": "warning",
                "title": f"Rezervasyon İptal Edildi - Oda {room_number}",
                "message": f"{guest_name} adlı misafirin {booking.get('check_in', '')[:10]} - {booking.get('check_out', '')[:10]} tarihli rezervasyonu iptal edildi. Sebep: {reason or 'Belirtilmedi'}",
                "related_entity": "reservation",
                "related_id": booking["id"],
                "read": False,
                "created_at": now.isoformat(),
            })
        except Exception:
            pass  # Non-critical

        # Audit trail
        await db.pms_audit_trail.insert_one({
            "tenant_id": tenant_id,
            "entity_type": "reservation",
            "entity_id": booking["id"],
            "action": "cancellation",
            "previous_status": current_status,
            "new_status": "cancelled",
            "performed_by": cancelled_by,
            "reason": reason,
            "timestamp": now.isoformat(),
        })

        # OTA-002: Enqueue outbox event for guaranteed OTA delivery on cancellation
        try:
            from core.outbox_service import BOOKING_CANCELLED, enqueue_outbox_event
            await enqueue_outbox_event(
                db,
                tenant_id=tenant_id,
                event_type=BOOKING_CANCELLED,
                entity_type="booking",
                entity_id=booking["id"],
                property_id=tenant_id,
                payload={
                    "booking_id": booking["id"],
                    "guest_id": booking.get("guest_id"),
                    "room_id": booking.get("room_id"),
                    "check_in": booking.get("check_in"),
                    "check_out": booking.get("check_out"),
                    "property_id": tenant_id,
                    "previous_status": current_status,
                    "cancellation_reason": reason or "No reason provided",
                    "cancelled_by": cancelled_by,
                },
            )
        except Exception as cancel_outbox_err:
            logger.warning("Outbox enqueue failed for cancellation %s: %s", booking["id"], cancel_outbox_err)

        return {"success": True, "booking_id": booking["id"], "previous_status": current_status}

    async def handle_no_show(self, tenant_id: str, booking: dict, marked_by: str) -> dict:
        """Mark a reservation as no-show. Only confirmed/guaranteed bookings can be no-showed."""
        current_status = booking.get("status")
        # Terminal-state guard (symmetric with handle_cancellation).
        # Without this, current==no_show falls into validate_transition's
        # "no_change" branch and silently writes a duplicate audit row.
        if current_status in NON_NOSHOWABLE_STATES:
            return {"success": False, "error": f"Cannot mark reservation as no_show in '{current_status}' state"}
        valid, msg = self.validate_transition(current_status, "no_show")
        if not valid:
            return {"success": False, "error": msg}

        now = datetime.now(UTC)
        await db.bookings.update_one(
            {"id": booking["id"], "tenant_id": tenant_id},
            {"$set": {
                "status": "no_show",
                "no_show_at": now.isoformat(),
                "no_show_marked_by": marked_by,
                "updated_at": now.isoformat(),
            }}
        )

        # Release room-night locks (INV-6 symmetry with handle_cancellation).
        # Production hardening mini-tur, May 2026: previously no-show left
        # room_night_locks in place even though the booking is terminal,
        # which could artificially constrain availability for the same
        # date range until manual cleanup.
        try:
            from core.atomic_booking import release_booking_nights
            await release_booking_nights(
                tenant_id, booking["id"],
                reason=f"no_show:{marked_by or 'system'}",
                correlation_id=booking.get("correlation_id"),
            )
        except Exception as e:
            logger.warning("Failed to release night locks for no-show %s: %s", booking["id"], e)

        await db.pms_audit_trail.insert_one({
            "tenant_id": tenant_id,
            "entity_type": "reservation",
            "entity_id": booking["id"],
            "action": "no_show",
            "previous_status": current_status,
            "new_status": "no_show",
            "performed_by": marked_by,
            "timestamp": now.isoformat(),
        })

        # CM-Hardening Turu #3a (May 2026): no-show outbox parity with cancel.
        # Symmetric with handle_cancellation L183-206. Enqueued AFTER
        # release_booking_nights so payload.inventory_released is truthful.
        # Terminal-state guard (line 216) prevents double-enqueue at the
        # business layer; idempotency_key (tenant+event+entity+payload_hash)
        # gives a second line of defence inside the outbox.
        # Provider handler is deferred (Turu #3b HotelRunner, #3c Exely) —
        # dispatcher logs an unsupported-event warning until then but does
        # NOT mark the row failed/DLQ (graceful no-op).
        try:
            from core.outbox_service import BOOKING_NOSHOW, enqueue_outbox_event
            await enqueue_outbox_event(
                db,
                tenant_id=tenant_id,
                event_type=BOOKING_NOSHOW,
                entity_type="booking",
                entity_id=booking["id"],
                property_id=tenant_id,
                payload={
                    "booking_id": booking["id"],
                    "guest_id": booking.get("guest_id"),
                    "room_id": booking.get("room_id"),
                    "check_in": booking.get("check_in"),
                    "check_out": booking.get("check_out"),
                    "property_id": tenant_id,
                    "previous_status": current_status,
                    "new_status": "no_show",
                    "marked_by": marked_by,
                    "no_show_at": now.isoformat(),
                    "inventory_released": True,
                },
            )
        except Exception as noshow_outbox_err:
            logger.warning("Outbox enqueue failed for no-show %s: %s", booking["id"], noshow_outbox_err)

        return {"success": True, "booking_id": booking["id"]}

    async def recalculate_availability_after_modification(self, tenant_id: str, old_room_id: str, new_room_id: str, booking_id: str):
        """After a booking modification (room change or date change), ensure room statuses are correct."""
        if old_room_id and old_room_id != new_room_id:
            # Check if old room still has active bookings
            active_on_old = await db.bookings.count_documents({
                "tenant_id": tenant_id,
                "room_id": old_room_id,
                "status": "checked_in",
                "id": {"$ne": booking_id},
            })
            if active_on_old == 0:
                old_room = await db.rooms.find_one({"id": old_room_id, "tenant_id": tenant_id}, {"_id": 0, "status": 1})
                if old_room and old_room.get("status") == "occupied":
                    await db.rooms.update_one(
                        {"id": old_room_id, "tenant_id": tenant_id},
                        {"$set": {"status": "dirty", "current_booking_id": None}}
                    )

    async def get_audit_trail(self, tenant_id: str, booking_id: str) -> list[dict]:
        """Get full audit trail for a reservation."""
        trail = await db.pms_audit_trail.find(
            {"tenant_id": tenant_id, "entity_id": booking_id, "entity_type": "reservation"},
            {"_id": 0}
        ).sort("timestamp", -1).to_list(100)
        return trail
