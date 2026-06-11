"""
Front Desk Workflow Service - Production-grade check-in, checkout, room move, walk-in flows.
Enforces room readiness, folio dependencies, and audit trail.
"""
import uuid
from datetime import UTC, datetime, timedelta

from core.database import db
from modules.pms_core.reservation_state_machine import ReservationStateMachine

rsm = ReservationStateMachine()


class FrontDeskService:
    """Handles all front desk operations with business rule enforcement."""

    # ── CHECK-IN ──

    async def check_in(self, tenant_id: str, booking_id: str, user_id: str, user_name: str, override_reason: str = None) -> dict:
        """Full check-in flow — delegates to atomic transaction."""
        from core.atomic_checkin_checkout import CheckInError, check_in_booking_atomic
        try:
            result = await check_in_booking_atomic(
                booking_id=booking_id,
                tenant_id=tenant_id,
                actor_id=user_id,
                actor_name=user_name,
                override_reason=override_reason,
            )
            return result
        except CheckInError as e:
            error_msg = str(e)
            resp = {"success": False, "error": error_msg}
            if "not ready" in error_msg:
                resp["blocker"] = "room_not_ready"
            return resp

    # ── CHECKOUT ──

    async def checkout(self, tenant_id: str, booking_id: str, user_id: str, user_name: str, force: bool = False) -> dict:
        """Full checkout flow — delegates to atomic transaction."""
        from core.atomic_checkin_checkout import CheckOutError, check_out_booking_atomic
        try:
            result = await check_out_booking_atomic(
                booking_id=booking_id,
                tenant_id=tenant_id,
                actor_id=user_id,
                actor_name=user_name,
                force=force,
            )
            return result
        except CheckOutError as e:
            error_msg = str(e)
            resp = {"success": False, "error": error_msg}
            if "unpaid balance" in error_msg:
                resp["blockers"] = [{"type": "unpaid_balance", "message": error_msg}]
            return resp

    async def get_checkout_blockers(self, tenant_id: str, booking_id: str) -> list[dict]:
        """Check for conditions that block checkout."""
        blockers = []

        # Check open folios with outstanding balance
        folios = await db.folios.find({"booking_id": booking_id, "tenant_id": tenant_id, "status": "open"}, {"_id": 0}).to_list(10)
        from core.utils import calculate_folio_balance
        for folio in folios:
            balance = await calculate_folio_balance(folio["id"], tenant_id)

            if balance > 0.01:
                blockers.append({
                    "type": "unpaid_balance",
                    "folio_id": folio["id"],
                    "folio_number": folio.get("folio_number"),
                    "balance": balance,
                    "message": f"Folio {folio.get('folio_number')} has unpaid balance of {balance}",
                })

        return blockers

    async def get_checkout_preview(self, tenant_id: str, booking_id: str) -> dict:
        """Generate checkout preview with folio summary."""
        booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
        if not booking:
            return {"error": "Booking not found"}

        folios = await db.folios.find({"booking_id": booking_id, "tenant_id": tenant_id}, {"_id": 0}).to_list(10)
        folio_summaries = []
        total_charges = 0
        total_payments = 0

        # Folio bazlı toplamlar (server-side $sum, limit yok)
        for folio in folios:
            ch_pipe = [
                {"$match": {"folio_id": folio["id"], "tenant_id": tenant_id, "voided": False}},
                {"$group": {"_id": None,
                            "total": {"$sum": {"$ifNull": ["$total", "$amount"]}},
                            "count": {"$sum": 1}}},
            ]
            pay_pipe = [
                {"$match": {"folio_id": folio["id"], "tenant_id": tenant_id, "voided": False}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
            ]
            ch_doc = await db.folio_charges.aggregate(ch_pipe).to_list(1)
            pay_doc = await db.payments.aggregate(pay_pipe).to_list(1)
            f_charges = float(ch_doc[0]["total"]) if ch_doc else 0.0
            f_count = int(ch_doc[0]["count"]) if ch_doc else 0
            f_payments = float(pay_doc[0]["total"]) if pay_doc else 0.0
            total_charges += f_charges
            total_payments += f_payments

            folio_summaries.append({
                "folio_id": folio["id"],
                "folio_number": folio.get("folio_number"),
                "folio_type": folio.get("folio_type"),
                "status": folio.get("status"),
                "charges_total": round(f_charges, 2),
                "payments_total": round(f_payments, 2),
                "balance": round(f_charges - f_payments, 2),
                "charge_count": f_count,
            })

        blockers = await self.get_checkout_blockers(tenant_id, booking_id)

        return {
            "booking_id": booking_id,
            "guest_id": booking.get("guest_id"),
            "room_id": booking.get("room_id"),
            "check_in": booking.get("check_in"),
            "check_out": booking.get("check_out"),
            "status": booking.get("status"),
            "folios": folio_summaries,
            "total_charges": round(total_charges, 2),
            "total_payments": round(total_payments, 2),
            "balance_due": round(total_charges - total_payments, 2),
            "blockers": blockers,
            "can_checkout": len(blockers) == 0,
        }

    # ── ROOM MOVE ──

    async def room_move(self, tenant_id: str, booking_id: str, new_room_id: str, reason: str, user_id: str, user_name: str) -> dict:
        """Move a checked-in guest to a different room."""
        booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
        if not booking:
            return {"success": False, "error": "Booking not found"}

        if booking["status"] != "checked_in":
            return {"success": False, "error": "Room move only allowed for checked-in reservations"}

        old_room_id = booking.get("room_id")
        if old_room_id == new_room_id:
            return {"success": False, "error": "New room is the same as current room"}

        new_room = await db.rooms.find_one({"id": new_room_id, "tenant_id": tenant_id}, {"_id": 0})
        if not new_room:
            return {"success": False, "error": "New room not found"}

        if new_room["status"] not in {"available", "inspected"}:
            return {"success": False, "error": f"New room is not ready (status: {new_room['status']})"}

        # Check overbooking on new room
        has_conflict, _ = await rsm.check_overbooking(
            tenant_id, new_room_id, booking["check_in"], booking["check_out"], exclude_booking_id=booking_id)
        if has_conflict:
            return {"success": False, "error": "New room has conflicting bookings"}

        now = datetime.now(UTC)

        # F8A tur-22 / CI #37 P1 race fix: target room → occupied via atomic CAS
        # FIRST (before booking/old-room mutations). Pre-check at line 158 is
        # TOCTOU vs the unconditional update_one that used to follow; two
        # parallel room-moves targeting the same vacant room both read
        # status="available" and both succeed under the old write pattern
        # (CI #37 03-D: r1=200 r2=200, double-occupancy). With CAS, the
        # second writer's filter does not match (status is already
        # "occupied"), modified_count==0 → return error before any other
        # mutation. Mirrors V2 frontdesk_service_v2 fix from tur-19.
        new_room_cas = await db.rooms.update_one(
            {
                "id": new_room_id,
                "tenant_id": tenant_id,
                "status": {"$in": ["available", "inspected"]},
            },
            {"$set": {"status": "occupied", "current_booking_id": booking_id}},
        )
        if new_room_cas.modified_count == 0:
            return {"success": False, "error": "New room is not available (concurrent state mutation)"}

        # Update booking (target now atomically claimed)
        await db.bookings.update_one(
            {"id": booking_id, "tenant_id": tenant_id},
            {"$set": {"room_id": new_room_id, "updated_at": now.isoformat()}}
        )

        # Old room goes to dirty
        if old_room_id:
            await db.rooms.update_one(
                {"id": old_room_id, "tenant_id": tenant_id},
                {"$set": {"status": "dirty", "current_booking_id": None}}
            )

        # Log room move history
        old_room = await db.rooms.find_one({"id": old_room_id, "tenant_id": tenant_id}, {"_id": 0}) if old_room_id else None
        await db.room_move_history.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "old_room": old_room.get("room_number", "N/A") if old_room else "N/A",
            "new_room": new_room["room_number"],
            "old_check_in": booking.get("check_in"),
            "new_check_in": booking.get("check_in"),
            "reason": reason,
            "moved_by": user_name,
            "timestamp": now.isoformat(),
        })

        await self._log_audit(tenant_id, "reservation", booking_id, "room_move", user_id,
                              {"old_room_id": old_room_id, "new_room_id": new_room_id, "reason": reason})

        return {"success": True, "booking_id": booking_id, "old_room": old_room.get("room_number") if old_room else None, "new_room": new_room["room_number"]}

    # ── WALK-IN ──

    async def walk_in(self, tenant_id: str, guest_data: dict, room_id: str, nights: int, rate: float, user_id: str, user_name: str) -> dict:
        """Create a walk-in reservation with immediate check-in (atomic)."""
        room = await db.rooms.find_one({"id": room_id, "tenant_id": tenant_id}, {"_id": 0})
        if not room:
            return {"success": False, "error": "Room not found"}

        if room["status"] not in {"available", "inspected"}:
            return {"success": False, "error": f"Room not available (status: {room['status']})"}

        now = datetime.now(UTC)
        check_in = now.isoformat()
        check_out = (now + timedelta(days=nights)).isoformat()

        # Check overbooking
        has_conflict, _ = await rsm.check_overbooking(tenant_id, room_id, check_in, check_out)
        if has_conflict:
            return {"success": False, "error": "Room has conflicting bookings for these dates"}

        # Create or find guest
        guest_id = guest_data.get("guest_id")
        if not guest_id:
            guest_id = str(uuid.uuid4())
            from security.guest_write import encrypt_guest_insert
            await db.guests.insert_one(encrypt_guest_insert({
                "id": guest_id,
                "tenant_id": tenant_id,
                "name": guest_data.get("name", "Walk-in Guest"),
                "email": guest_data.get("email", f"walkin-{guest_id[:8]}@hotel.local"),
                "phone": guest_data.get("phone", ""),
                "id_number": guest_data.get("id_number", ""),
                "created_at": now.isoformat(),
            }))

        booking_id = str(uuid.uuid4())
        total_amount = rate * nights

        # Create booking atomically (overbooking prevention)
        from core.atomic_booking import BookingConflictError, create_booking_atomic
        try:
            await create_booking_atomic({
                "id": booking_id,
                "tenant_id": tenant_id,
                "guest_id": guest_id,
                "room_id": room_id,
                "check_in": check_in,
                "check_out": check_out,
                "adults": guest_data.get("adults", 1),
                "children": 0,
                "guests_count": guest_data.get("adults", 1),
                "total_amount": total_amount,
                "base_rate": rate,
                "paid_amount": 0.0,
                "status": "confirmed",
                "channel": "direct",
                "source_channel": "walk_in",
                "origin": "ui",
                "rate_plan": "Walk-in",
                "market_segment": "leisure",
                "created_at": now.isoformat(),
            })
        except BookingConflictError as e:
            return {"success": False, "error": str(e)}

        # Atomic check-in (booking + room + folio + audit + outbox in one transaction)
        from core.atomic_checkin_checkout import CheckInError, check_in_booking_atomic
        try:
            result = await check_in_booking_atomic(
                booking_id=booking_id,
                tenant_id=tenant_id,
                actor_id=user_id,
                actor_name=user_name,
            )
        except CheckInError as e:
            return {"success": False, "error": f"Walk-in booking created but check-in failed: {e}"}

        return {
            "success": True,
            "booking_id": booking_id,
            "folio_id": result.get("folio_id"),
            "room_number": room["room_number"],
            "guest_id": guest_id,
        }

    # ── EARLY CHECK-IN / LATE CHECKOUT ──

    async def request_early_checkin(self, tenant_id: str, booking_id: str, requested_time: str, user_id: str) -> dict:
        """Request early check-in - checks room availability."""
        booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
        if not booking:
            return {"success": False, "error": "Booking not found"}

        room = await db.rooms.find_one({"id": booking.get("room_id"), "tenant_id": tenant_id}, {"_id": 0})
        room_ready = room and room["status"] in {"available", "inspected"} if room else False

        await db.bookings.update_one(
            {"id": booking_id, "tenant_id": tenant_id},
            {"$set": {"early_checkin_requested": True, "early_checkin_time": requested_time}}
        )

        return {"success": True, "room_ready": room_ready, "room_status": room["status"] if room else "unknown"}

    async def request_late_checkout(self, tenant_id: str, booking_id: str, requested_time: str, charge: float, user_id: str) -> dict:
        """Request late checkout with optional charge."""
        booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
        if not booking:
            return {"success": False, "error": "Booking not found"}

        if booking["status"] != "checked_in":
            return {"success": False, "error": "Late checkout only for checked-in reservations"}

        now = datetime.now(UTC)
        await db.bookings.update_one(
            {"id": booking_id, "tenant_id": tenant_id},
            {"$set": {
                "late_checkout_approved": True,
                "late_checkout_time": requested_time,
                "late_checkout_charge": charge,
                "updated_at": now.isoformat(),
            }}
        )

        # Post late checkout charge to folio if charge > 0
        if charge > 0:
            folio = await db.folios.find_one({"booking_id": booking_id, "tenant_id": tenant_id, "status": "open"}, {"_id": 0})
            if folio:
                await db.folio_charges.insert_one({
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "folio_id": folio["id"],
                    "booking_id": booking_id,
                    "charge_category": "room",
                    "description": f"Late checkout charge ({requested_time})",
                    "unit_price": charge,
                    "quantity": 1.0,
                    "amount": charge,
                    "tax_amount": 0.0,
                    "total": charge,
                    "posted_by": user_id,
                    "date": now.isoformat(),
                    "voided": False,
                })

        await self._log_audit(tenant_id, "reservation", booking_id, "late_checkout_approved", user_id,
                              {"charge": charge, "requested_time": requested_time})

        return {"success": True, "booking_id": booking_id, "charge": charge}

    # ── ROOM UPGRADE ──

    async def room_upgrade(self, tenant_id: str, booking_id: str, new_room_id: str, reason: str, rate_adjustment: float, user_id: str, user_name: str) -> dict:
        """Upgrade room (can be before or after check-in)."""
        booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
        if not booking:
            return {"success": False, "error": "Booking not found"}

        if booking["status"] in {"checked_out", "cancelled", "no_show"}:
            return {"success": False, "error": f"Cannot upgrade reservation in '{booking['status']}' state"}

        result = await self.room_move(tenant_id, booking_id, new_room_id, f"Upgrade: {reason}", user_id, user_name)
        if not result["success"]:
            # For non-checked-in bookings, we just update the room_id
            if booking["status"] != "checked_in":
                new_room = await db.rooms.find_one({"id": new_room_id, "tenant_id": tenant_id}, {"_id": 0})
                if not new_room:
                    return {"success": False, "error": "New room not found"}
                await db.bookings.update_one(
                    {"id": booking_id, "tenant_id": tenant_id},
                    {"$set": {"room_id": new_room_id, "updated_at": datetime.now(UTC).isoformat()}}
                )
                result = {"success": True, "booking_id": booking_id, "new_room": new_room["room_number"]}
            else:
                return result

        # Apply rate adjustment
        if rate_adjustment != 0:
            new_total = booking.get("total_amount", 0) + rate_adjustment
            await db.bookings.update_one(
                {"id": booking_id, "tenant_id": tenant_id},
                {"$set": {"total_amount": new_total}}
            )

        await self._log_audit(tenant_id, "reservation", booking_id, "room_upgrade", user_id,
                              {"new_room_id": new_room_id, "reason": reason, "rate_adjustment": rate_adjustment})

        return {**result, "rate_adjustment": rate_adjustment, "upgrade_reason": reason}

    # ── HELPERS ──

    async def _log_audit(self, tenant_id: str, entity_type: str, entity_id: str, action: str, user_id: str, metadata: dict = None):
        await db.pms_audit_trail.insert_one({
            "tenant_id": tenant_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "performed_by": user_id,
            "metadata": metadata or {},
            "timestamp": datetime.now(UTC).isoformat(),
        })
