"""
PMS / Front Desk — Production-Grade Service Layer v2
=====================================================
Adds: room_move, late_checkout, no_show, walk_in, concurrent operation guard,
folio mutation safety, idempotency, supervisor override, housekeeping interaction.
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from common.audit_hook import SEVERITY_INFO, SEVERITY_WARNING, audited
from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)

# Concurrency lock TTL
_LOCK_TTL_SECONDS = 30


class FrontdeskServiceV2:
    """Production-grade front desk operations with concurrency protection."""

    def __init__(self):
        from core.database import db
        self._db = db

    # ==================================================================
    # Concurrency Guard
    # ==================================================================
    async def _acquire_lock(self, lock_key: str, holder: str) -> bool:
        now = datetime.now(UTC)
        expiry = now + timedelta(seconds=_LOCK_TTL_SECONDS)
        try:
            result = await self._db.operation_locks.update_one(
                {
                    "lock_key": lock_key,
                    "$or": [
                        {"expires_at": {"$lt": now.isoformat()}},
                        {"expires_at": {"$exists": False}},
                    ],
                },
                {
                    "$set": {
                        "lock_key": lock_key,
                        "holder": holder,
                        "acquired_at": now.isoformat(),
                        "expires_at": expiry.isoformat(),
                    }
                },
                upsert=True,
            )
            return result.modified_count > 0 or result.upserted_id is not None
        except Exception:
            return False

    async def _release_lock(self, lock_key: str, holder: str):
        try:
            await self._db.operation_locks.delete_one(
                {"lock_key": lock_key, "holder": holder}
            )
        except Exception:
            pass

    # ==================================================================
    # Check-in — Production Grade
    # ==================================================================
    @audited("frontdesk.checkin", "booking", severity=SEVERITY_INFO, capture_before=True)
    async def checkin(
        self,
        ctx: OperationContext,
        booking_id: str,
        create_folio: bool = True,
        idempotency_key: str | None = None,
    ) -> ServiceResult:
        lock_key = f"frontdesk:checkin:{booking_id}"
        holder = idempotency_key or str(uuid.uuid4())

        if not await self._acquire_lock(lock_key, holder):
            return ServiceResult.fail(
                "Concurrent check-in in progress for this booking",
                "CONCURRENT_OPERATION",
            )
        try:
            return await self._do_checkin(ctx, booking_id, create_folio, holder)
        finally:
            await self._release_lock(lock_key, holder)

    async def _do_checkin(
        self, ctx: OperationContext, booking_id: str, create_folio: bool, holder: str
    ) -> ServiceResult:
        booking = await self._db.bookings.find_one(
            {"id": booking_id, "tenant_id": ctx.tenant_id}, {"_id": 0}
        )
        if not booking:
            return ServiceResult.fail("Booking not found", "NOT_FOUND")

        # Idempotency: already checked in
        if booking["status"] == "checked_in":
            return ServiceResult.success(
                {
                    "message": "Already checked in (idempotent)",
                    "checked_in_at": booking.get("checked_in_at"),
                    "idempotent": True,
                }
            )

        if booking["status"] not in ("confirmed", "guaranteed"):
            return ServiceResult.fail(
                f"Cannot check in from status: {booking['status']}",
                "INVALID_STATUS",
            )

        # Room readiness validation
        room = await self._db.rooms.find_one(
            {"id": booking.get("room_id"), "tenant_id": ctx.tenant_id}, {"_id": 0}
        )
        if not room:
            return ServiceResult.fail("No room assigned to booking", "NO_ROOM")

        if room["status"] not in ("available", "inspected", "clean"):
            # Check pending HK tasks
            pending_hk = await self._db.housekeeping_tasks.count_documents(
                {
                    "room_id": room["id"],
                    "tenant_id": ctx.tenant_id,
                    "status": {"$in": ["new", "in_progress"]},
                }
            )
            if pending_hk > 0:
                return ServiceResult.fail(
                    f"Room {room.get('room_number')} has {pending_hk} pending housekeeping task(s). Status: {room['status']}",
                    "ROOM_NOT_READY",
                )
            if room["status"] == "dirty":
                return ServiceResult.fail(
                    f"Room {room.get('room_number')} is dirty and needs cleaning",
                    "ROOM_NOT_READY",
                )
            if room["status"] == "maintenance":
                return ServiceResult.fail(
                    f"Room {room.get('room_number')} is under maintenance",
                    "ROOM_MAINTENANCE",
                )
            if room["status"] == "occupied":
                return ServiceResult.fail(
                    f"Room {room.get('room_number')} is currently occupied",
                    "ROOM_OCCUPIED",
                )

        # Create guest folio
        folio_id = None
        if create_folio:
            existing_folio = await self._db.folios.find_one(
                {"booking_id": booking_id, "folio_type": "guest", "tenant_id": ctx.tenant_id}
            )
            if not existing_folio:
                folio_id = str(uuid.uuid4())
                folio_number = f"F-{datetime.now().year}-{uuid.uuid4().hex[:5].upper()}"
                folio_doc = {
                    "id": folio_id,
                    "tenant_id": ctx.tenant_id,
                    "booking_id": booking_id,
                    "folio_number": folio_number,
                    "folio_type": "guest",
                    "guest_id": booking["guest_id"],
                    "status": "open",
                    "balance": 0.0,
                    "currency": booking.get("currency", "TRY"),
                    "created_at": datetime.now(UTC).isoformat(),
                    "created_by": ctx.actor_id,
                }
                await self._db.folios.insert_one(folio_doc)
            else:
                folio_id = existing_folio.get("id")

        checked_in_at = datetime.now(UTC)
        await self._db.bookings.update_one(
            {"id": booking_id},
            {
                "$set": {
                    "status": "checked_in",
                    "checked_in_at": checked_in_at.isoformat(),
                    "checked_in_by": ctx.actor_id,
                }
            },
        )
        await self._db.rooms.update_one(
            {"id": booking["room_id"]},
            {"$set": {"status": "occupied", "current_booking_id": booking_id}},
        )
        await self._db.guests.update_one(
            {"id": booking["guest_id"]}, {"$inc": {"total_stays": 1}}
        )

        return ServiceResult.success(
            {
                "message": "Check-in completed successfully",
                "booking_id": booking_id,
                "checked_in_at": checked_in_at.isoformat(),
                "room_number": room.get("room_number"),
                "folio_id": folio_id,
            }
        )

    # ==================================================================
    # Check-out — Production Grade
    # ==================================================================
    @audited("frontdesk.checkout", "booking", severity=SEVERITY_INFO, capture_before=True)
    async def checkout(
        self,
        ctx: OperationContext,
        booking_id: str,
        force: bool = False,
        auto_close_folios: bool = True,
        reason: str | None = None,
    ) -> ServiceResult:
        lock_key = f"frontdesk:checkout:{booking_id}"
        holder = str(uuid.uuid4())

        if not await self._acquire_lock(lock_key, holder):
            return ServiceResult.fail(
                "Concurrent checkout in progress", "CONCURRENT_OPERATION"
            )
        try:
            return await self._do_checkout(
                ctx, booking_id, force, auto_close_folios, reason
            )
        finally:
            await self._release_lock(lock_key, holder)

    async def _do_checkout(
        self,
        ctx: OperationContext,
        booking_id: str,
        force: bool,
        auto_close_folios: bool,
        reason: str | None,
    ) -> ServiceResult:
        booking = await self._db.bookings.find_one(
            {"id": booking_id, "tenant_id": ctx.tenant_id}, {"_id": 0}
        )
        if not booking:
            return ServiceResult.fail("Booking not found", "NOT_FOUND")

        if booking["status"] == "checked_out":
            return ServiceResult.success(
                {
                    "message": "Already checked out (idempotent)",
                    "checked_out_at": booking.get("checked_out_at"),
                    "idempotent": True,
                }
            )

        if booking["status"] != "checked_in":
            return ServiceResult.fail(
                f"Cannot check out from status: {booking['status']}",
                "INVALID_STATUS",
            )

        # ── Auto-post Konaklama Vergisi (Türkiye) ──────────────────────
        # Tenant config'inde `auto_post=True` ise checkout sırasında, balance
        # kontrolünden ÖNCE konaklama vergisini folio'ya idempotent olarak
        # düş. Böylece outstanding-balance kontrolü doğru tutarı görür ve
        # tahsil edilmemiş vergi unutulmaz. Hata olursa checkout'u
        # bloklamaz — KVB posting'i bağımsız olarak tekrar denenebilir.
        try:
            from routers.finance.konaklama_vergisi_core import (
                load_tax_config,
                post_konaklama_vergisi_to_folio,
            )
            kvb_cfg = await load_tax_config(ctx.tenant_id)
            if kvb_cfg.get("active", True) and kvb_cfg.get("auto_post"):
                open_folios = await self._db.folios.find(
                    {
                        "booking_id": booking_id,
                        "tenant_id": ctx.tenant_id,
                        "status": "open",
                    },
                    {"_id": 0, "id": 1, "folio_type": 1},
                ).to_list(100)
                for f in open_folios:
                    # Sadece misafir folyosuna (varsa) — incidental/extra
                    # folyolarına konaklama vergisi düşmez.
                    if f.get("folio_type") and f["folio_type"] not in (
                        "guest", "primary", "main",
                    ):
                        continue
                    posting = await post_konaklama_vergisi_to_folio(
                        tenant_id=ctx.tenant_id,
                        folio_id=f["id"],
                        posted_by=f"checkout:{ctx.actor_id}",
                        raise_on_error=False,
                    )
                    if posting.get("posted"):
                        try:
                            from core.helpers import create_audit_log
                            await create_audit_log(
                                tenant_id=ctx.tenant_id,
                                user=None,
                                action="POST_KONAKLAMA_VERGISI",
                                entity_type="folio_charge",
                                entity_id=posting.get("charge_id"),
                                changes={
                                    "folio_id": f["id"],
                                    "base": posting.get("base_amount"),
                                    "tax": posting.get("tax_amount"),
                                    "rate": posting.get("rate_percent"),
                                    "trigger": "checkout_auto_post",
                                    "actor_id": ctx.actor_id,
                                },
                            )
                        except Exception:
                            pass
        except Exception as exc:
            logger.warning(
                "konaklama_vergisi auto_post failed for booking=%s: %s",
                booking_id, exc,
            )

        # Folio balance check
        folios = await self._db.folios.find(
            {"booking_id": booking_id, "tenant_id": ctx.tenant_id, "status": "open"},
            {"_id": 0},
        ).to_list(100)

        total_balance = 0.0
        folio_details = []
        for folio in folios:
            balance = folio.get("balance", 0.0)
            total_balance += balance
            folio_details.append(
                {
                    "folio_number": folio.get("folio_number"),
                    "folio_type": folio.get("folio_type"),
                    "balance": round(balance, 2),
                }
            )

        if total_balance > 0.01 and not force:
            return ServiceResult.fail(
                f"Outstanding balance: {total_balance:.2f}",
                "OUTSTANDING_BALANCE",
                folio_details=folio_details,
                total_balance=round(total_balance, 2),
            )

        # Force checkout requires reason and supervisor role
        if force and total_balance > 0.01:
            if not reason:
                return ServiceResult.fail(
                    "Force checkout with balance requires a reason",
                    "REASON_REQUIRED",
                )
            if not ctx.actor_is_super_admin and ctx.actor_role not in ("admin", "supervisor", "super_admin", "gm"):
                return ServiceResult.fail(
                    "Force checkout requires supervisor or admin role",
                    "INSUFFICIENT_PERMISSION",
                )

        # Close folios
        if auto_close_folios and total_balance <= 0.01:
            for folio in folios:
                await self._db.folios.update_one(
                    {"id": folio["id"]},
                    {
                        "$set": {
                            "status": "closed",
                            "balance": 0.0,
                            "closed_at": datetime.now(UTC).isoformat(),
                            "closed_by": ctx.actor_id,
                        }
                    },
                )

        # Deactivate active keycards
        active_keycards = await self._db.keycards.find(
            {"booking_id": booking_id, "status": "active", "tenant_id": ctx.tenant_id}
        ).to_list(20)
        for kc in active_keycards:
            await self._db.keycards.update_one(
                {"id": kc["id"]},
                {
                    "$set": {
                        "status": "deactivated",
                        "deactivated_at": datetime.now(UTC).isoformat(),
                        "deactivation_reason": "checkout",
                    }
                },
            )

        checked_out_at = datetime.now(UTC)
        await self._db.bookings.update_one(
            {"id": booking_id},
            {
                "$set": {
                    "status": "checked_out",
                    "checked_out_at": checked_out_at.isoformat(),
                    "checked_out_by": ctx.actor_id,
                    "force_checkout": force,
                    "checkout_reason": reason,
                }
            },
        )

        room_id = booking.get("room_id")
        if room_id:
            await self._db.rooms.update_one(
                {"id": room_id},
                {"$set": {"status": "dirty", "current_booking_id": None}},
            )
            # Auto-create departure clean HK task
            hk_task = {
                "id": str(uuid.uuid4()),
                "tenant_id": ctx.tenant_id,
                "room_id": room_id,
                "task_type": "departure_clean",
                "priority": "high",
                "status": "new",
                "notes": f"Departure clean - Booking {booking_id}",
                "created_at": datetime.now(UTC).isoformat(),
                "created_by": "system",
            }
            await self._db.housekeeping_tasks.insert_one(hk_task)

        return ServiceResult.success(
            {
                "message": "Check-out completed",
                "booking_id": booking_id,
                "checked_out_at": checked_out_at.isoformat(),
                "total_balance": round(total_balance, 2),
                "folios_closed": len(folios) if auto_close_folios and total_balance <= 0.01 else 0,
                "keycards_deactivated": len(active_keycards),
                "force_checkout": force,
            }
        )

    # ==================================================================
    # Room Move — NEW
    # ==================================================================
    @audited("frontdesk.room_move", "booking", severity=SEVERITY_WARNING, capture_before=True, require_reason=True)
    async def room_move(
        self,
        ctx: OperationContext,
        booking_id: str,
        new_room_id: str,
        reason: str = "",
        transfer_keycards: bool = True,
    ) -> ServiceResult:
        lock_key = f"frontdesk:room_move:{booking_id}"
        holder = str(uuid.uuid4())
        if not await self._acquire_lock(lock_key, holder):
            return ServiceResult.fail("Concurrent room move", "CONCURRENT_OPERATION")

        try:
            booking = await self._db.bookings.find_one(
                {"id": booking_id, "tenant_id": ctx.tenant_id}, {"_id": 0}
            )
            if not booking:
                return ServiceResult.fail("Booking not found", "NOT_FOUND")
            if booking["status"] != "checked_in":
                return ServiceResult.fail(
                    "Room move only for checked-in guests", "INVALID_STATUS"
                )

            old_room_id = booking.get("room_id")
            if old_room_id == new_room_id:
                return ServiceResult.fail("Same room selected", "SAME_ROOM")

            new_room = await self._db.rooms.find_one(
                {"id": new_room_id, "tenant_id": ctx.tenant_id}, {"_id": 0}
            )
            if not new_room:
                return ServiceResult.fail("Target room not found", "NOT_FOUND")
            if new_room["status"] not in ("available", "inspected", "clean"):
                return ServiceResult.fail(
                    f"Target room not available. Status: {new_room['status']}",
                    "ROOM_NOT_AVAILABLE",
                )

            # Release old room
            if old_room_id:
                await self._db.rooms.update_one(
                    {"id": old_room_id},
                    {"$set": {"status": "dirty", "current_booking_id": None}},
                )
                # HK task for old room
                await self._db.housekeeping_tasks.insert_one(
                    {
                        "id": str(uuid.uuid4()),
                        "tenant_id": ctx.tenant_id,
                        "room_id": old_room_id,
                        "task_type": "room_move_clean",
                        "priority": "medium",
                        "status": "new",
                        "notes": f"Room move clean - guest moved to {new_room.get('room_number')}",
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                )

            # Assign new room
            await self._db.rooms.update_one(
                {"id": new_room_id},
                {"$set": {"status": "occupied", "current_booking_id": booking_id}},
            )
            await self._db.bookings.update_one(
                {"id": booking_id},
                {
                    "$set": {
                        "room_id": new_room_id,
                        "previous_room_ids": booking.get("previous_room_ids", [])
                        + [old_room_id]
                        if old_room_id
                        else [],
                        "room_moved_at": datetime.now(UTC).isoformat(),
                        "room_move_reason": reason,
                    }
                },
            )

            # Transfer/deactivate keycards
            if transfer_keycards and old_room_id:
                active_cards = await self._db.keycards.find(
                    {
                        "booking_id": booking_id,
                        "status": "active",
                        "tenant_id": ctx.tenant_id,
                    }
                ).to_list(10)
                for card in active_cards:
                    await self._db.keycards.update_one(
                        {"id": card["id"]},
                        {
                            "$set": {
                                "status": "deactivated",
                                "deactivated_at": datetime.now(UTC).isoformat(),
                                "deactivation_reason": "room_move",
                            }
                        },
                    )

            old_room = await self._db.rooms.find_one(
                {"id": old_room_id}, {"_id": 0, "room_number": 1}
            ) if old_room_id else None

            return ServiceResult.success(
                {
                    "message": "Room move completed",
                    "booking_id": booking_id,
                    "from_room": old_room.get("room_number") if old_room else None,
                    "to_room": new_room.get("room_number"),
                    "keycards_deactivated": True if transfer_keycards else False,
                    "reason": reason,
                }
            )
        finally:
            await self._release_lock(lock_key, holder)

    # ==================================================================
    # Late Checkout — NEW
    # ==================================================================
    @audited("frontdesk.late_checkout", "booking", severity=SEVERITY_WARNING, require_reason=True)
    async def late_checkout(
        self,
        ctx: OperationContext,
        booking_id: str,
        new_checkout_time: str,
        charge_amount: float = 0.0,
        reason: str = "",
    ) -> ServiceResult:
        booking = await self._db.bookings.find_one(
            {"id": booking_id, "tenant_id": ctx.tenant_id}, {"_id": 0}
        )
        if not booking:
            return ServiceResult.fail("Booking not found", "NOT_FOUND")
        if booking["status"] != "checked_in":
            return ServiceResult.fail("Guest must be checked in", "INVALID_STATUS")

        original_checkout = booking.get("check_out")

        await self._db.bookings.update_one(
            {"id": booking_id},
            {
                "$set": {
                    "check_out": new_checkout_time,
                    "original_checkout": original_checkout,
                    "late_checkout": True,
                    "late_checkout_approved_by": ctx.actor_id,
                    "late_checkout_reason": reason,
                    "late_checkout_at": datetime.now(UTC).isoformat(),
                }
            },
        )

        # Post late checkout charge if applicable
        if charge_amount > 0:
            charge_id = str(uuid.uuid4())
            await self._db.folio_charges.insert_one(
                {
                    "id": charge_id,
                    "tenant_id": ctx.tenant_id,
                    "booking_id": booking_id,
                    "guest_id": booking.get("guest_id"),
                    "charge_type": "late_checkout",
                    "charge_category": "room",
                    "description": f"Late checkout fee - {reason}",
                    "amount": charge_amount,
                    "tax_amount": round(charge_amount * 0.10, 2),
                    "total": round(charge_amount * 1.10, 2),
                    "voided": False,
                    "date": datetime.now(UTC).isoformat(),
                    "posted_by": ctx.actor_id,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            # Update folio balance
            folio = await self._db.folios.find_one(
                {"booking_id": booking_id, "folio_type": "guest", "status": "open", "tenant_id": ctx.tenant_id}
            )
            if folio:
                await self._db.folios.update_one(
                    {"id": folio["id"]},
                    {"$inc": {"balance": round(charge_amount * 1.10, 2)}},
                )

        return ServiceResult.success(
            {
                "message": "Late checkout approved",
                "booking_id": booking_id,
                "original_checkout": original_checkout,
                "new_checkout": new_checkout_time,
                "charge_posted": charge_amount if charge_amount > 0 else 0,
            }
        )

    # ==================================================================
    # No-Show Processing — NEW
    # ==================================================================
    @audited("frontdesk.no_show", "booking", severity=SEVERITY_WARNING, capture_before=True)
    async def process_no_show(
        self,
        ctx: OperationContext,
        booking_id: str,
        charge_first_night: bool = True,
        release_room: bool = True,
    ) -> ServiceResult:
        lock_key = f"frontdesk:noshow:{booking_id}"
        holder = str(uuid.uuid4())
        if not await self._acquire_lock(lock_key, holder):
            return ServiceResult.fail("Concurrent no-show processing", "CONCURRENT_OPERATION")

        try:
            booking = await self._db.bookings.find_one(
                {"id": booking_id, "tenant_id": ctx.tenant_id}, {"_id": 0}
            )
            if not booking:
                return ServiceResult.fail("Booking not found", "NOT_FOUND")

            if booking["status"] == "no_show":
                return ServiceResult.success(
                    {"message": "Already marked as no-show (idempotent)", "idempotent": True}
                )

            if booking["status"] not in ("confirmed", "guaranteed"):
                return ServiceResult.fail(
                    f"Cannot no-show from status: {booking['status']}",
                    "INVALID_STATUS",
                )

            charge_posted = 0.0
            if charge_first_night and booking.get("rate_amount"):
                rate = booking["rate_amount"]
                tax = round(rate * 0.10, 2)
                total = round(rate + tax, 2)
                charge_posted = total
                await self._db.folio_charges.insert_one(
                    {
                        "id": str(uuid.uuid4()),
                        "tenant_id": ctx.tenant_id,
                        "booking_id": booking_id,
                        "guest_id": booking.get("guest_id"),
                        "charge_type": "no_show_fee",
                        "charge_category": "room",
                        "description": "No-show fee - first night charge",
                        "amount": rate,
                        "tax_amount": tax,
                        "total": total,
                        "voided": False,
                        "date": datetime.now(UTC).isoformat(),
                        "posted_by": "system",
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                )

            # Release room
            room_released = False
            if release_room and booking.get("room_id"):
                await self._db.rooms.update_one(
                    {"id": booking["room_id"]},
                    {"$set": {"status": "available", "current_booking_id": None}},
                )
                room_released = True

            await self._db.bookings.update_one(
                {"id": booking_id},
                {
                    "$set": {
                        "status": "no_show",
                        "no_show_at": datetime.now(UTC).isoformat(),
                        "no_show_processed_by": ctx.actor_id,
                        "no_show_charge": charge_posted,
                    }
                },
            )

            return ServiceResult.success(
                {
                    "message": "No-show processed",
                    "booking_id": booking_id,
                    "charge_posted": charge_posted,
                    "room_released": room_released,
                }
            )
        finally:
            await self._release_lock(lock_key, holder)

    # ==================================================================
    # Walk-In Booking — NEW
    # ==================================================================
    @audited("frontdesk.walk_in", "booking", severity=SEVERITY_INFO)
    async def walk_in(
        self,
        ctx: OperationContext,
        guest_name: str,
        room_id: str,
        nights: int = 1,
        rate_amount: float = 0.0,
        payment_method: str = "cash",
        guest_email: str | None = None,
        guest_phone: str | None = None,
        id_number: str | None = None,
    ) -> ServiceResult:
        room = await self._db.rooms.find_one(
            {"id": room_id, "tenant_id": ctx.tenant_id}, {"_id": 0}
        )
        if not room:
            return ServiceResult.fail("Room not found", "NOT_FOUND")
        if room["status"] not in ("available", "inspected", "clean"):
            return ServiceResult.fail(
                f"Room not available. Status: {room['status']}", "ROOM_NOT_AVAILABLE"
            )

        now = datetime.now(UTC)
        guest_id = str(uuid.uuid4())
        booking_id = str(uuid.uuid4())
        folio_id = str(uuid.uuid4())

        # Create guest record
        guest_doc = {
            "id": guest_id,
            "tenant_id": ctx.tenant_id,
            "name": guest_name,
            "email": guest_email,
            "phone": guest_phone,
            "id_number": id_number,
            "total_stays": 1,
            "source": "walk_in",
            "created_at": now.isoformat(),
        }
        await self._db.guests.insert_one(guest_doc)

        # Create booking
        checkout_date = (now + timedelta(days=nights)).date().isoformat()
        booking_doc = {
            "id": booking_id,
            "tenant_id": ctx.tenant_id,
            "guest_id": guest_id,
            "room_id": room_id,
            "reservation_number": f"WI-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}",
            "status": "checked_in",
            "source": "walk_in",
            "check_in": now.date().isoformat(),
            "check_out": checkout_date,
            "nights": nights,
            "rate_amount": rate_amount,
            "payment_method": payment_method,
            "checked_in_at": now.isoformat(),
            "checked_in_by": ctx.actor_id,
            "created_at": now.isoformat(),
        }
        from core.atomic_booking import BookingConflictError, create_booking_atomic
        try:
            await create_booking_atomic(booking_doc)
        except BookingConflictError as e:
            return ServiceResult.fail(str(e), "ROOM_CONFLICT")

        # Create folio
        folio_doc = {
            "id": folio_id,
            "tenant_id": ctx.tenant_id,
            "booking_id": booking_id,
            "folio_number": f"F-{now.year}-{uuid.uuid4().hex[:5].upper()}",
            "folio_type": "guest",
            "guest_id": guest_id,
            "status": "open",
            "balance": 0.0,
            "currency": "TRY",
            "created_at": now.isoformat(),
        }
        await self._db.folios.insert_one(folio_doc)

        # Occupy room
        await self._db.rooms.update_one(
            {"id": room_id},
            {"$set": {"status": "occupied", "current_booking_id": booking_id}},
        )

        return ServiceResult.success(
            {
                "message": "Walk-in check-in completed",
                "booking_id": booking_id,
                "guest_id": guest_id,
                "folio_id": folio_id,
                "room_number": room.get("room_number"),
                "reservation_number": booking_doc["reservation_number"],
                "check_out": checkout_date,
            }
        )

    # ==================================================================
    # Early Checkout — NEW
    # ==================================================================
    @audited("frontdesk.early_checkout", "booking", severity=SEVERITY_INFO, capture_before=True)
    async def early_checkout(
        self,
        ctx: OperationContext,
        booking_id: str,
        waive_remaining_nights: bool = False,
    ) -> ServiceResult:
        booking = await self._db.bookings.find_one(
            {"id": booking_id, "tenant_id": ctx.tenant_id}, {"_id": 0}
        )
        if not booking:
            return ServiceResult.fail("Booking not found", "NOT_FOUND")
        if booking["status"] != "checked_in":
            return ServiceResult.fail("Guest must be checked in", "INVALID_STATUS")

        now = datetime.now(UTC)
        original_checkout = booking.get("check_out")

        await self._db.bookings.update_one(
            {"id": booking_id},
            {
                "$set": {
                    "check_out": now.date().isoformat(),
                    "original_checkout": original_checkout,
                    "early_checkout": True,
                    "early_checkout_waived": waive_remaining_nights,
                }
            },
        )

        # Proceed with normal checkout flow
        return await self.checkout(ctx, booking_id, force=waive_remaining_nights)

    # ==================================================================
    # Folio Post Charge — Production Grade
    # ==================================================================
    @audited("frontdesk.post_charge", "folio_charge", severity=SEVERITY_INFO)
    async def post_charge(
        self,
        ctx: OperationContext,
        booking_id: str,
        charge_type: str,
        description: str,
        amount: float,
        charge_category: str = "misc",
        idempotency_key: str | None = None,
    ) -> ServiceResult:
        if amount <= 0:
            return ServiceResult.fail("Charge amount must be positive", "VALIDATION_ERROR")

        # Idempotency check
        if idempotency_key:
            existing = await self._db.folio_charges.find_one(
                {"idempotency_key": idempotency_key, "tenant_id": ctx.tenant_id}
            )
            if existing:
                return ServiceResult.success(
                    {"message": "Charge already posted (idempotent)", "charge_id": existing.get("id"), "idempotent": True}
                )

        booking = await self._db.bookings.find_one(
            {"id": booking_id, "tenant_id": ctx.tenant_id}, {"_id": 0}
        )
        if not booking:
            return ServiceResult.fail("Booking not found", "NOT_FOUND")
        if booking["status"] not in ("checked_in", "confirmed", "guaranteed"):
            return ServiceResult.fail("Cannot post to inactive booking", "INVALID_STATUS")

        folio = await self._db.folios.find_one(
            {"booking_id": booking_id, "folio_type": "guest", "status": "open", "tenant_id": ctx.tenant_id}
        )
        if not folio:
            return ServiceResult.fail("No open folio for booking", "NO_OPEN_FOLIO")

        tax_rate = 0.10 if charge_category in ("room", "food", "beverage") else 0.20
        tax_amount = round(amount * tax_rate, 2)
        total = round(amount + tax_amount, 2)

        charge_id = str(uuid.uuid4())
        charge_doc = {
            "id": charge_id,
            "tenant_id": ctx.tenant_id,
            "booking_id": booking_id,
            "folio_id": folio["id"],
            "guest_id": booking.get("guest_id"),
            "charge_type": charge_type,
            "charge_category": charge_category,
            "description": description,
            "amount": amount,
            "tax_amount": tax_amount,
            "total": total,
            "voided": False,
            "date": datetime.now(UTC).isoformat(),
            "posted_by": ctx.actor_id,
            "idempotency_key": idempotency_key,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await self._db.folio_charges.insert_one(charge_doc)

        # Update folio balance
        await self._db.folios.update_one(
            {"id": folio["id"]}, {"$inc": {"balance": total}}
        )

        return ServiceResult.success(
            {
                "charge_id": charge_id,
                "folio_id": folio["id"],
                "amount": amount,
                "tax_amount": tax_amount,
                "total": total,
            }
        )

    # ==================================================================
    # Void Charge — NEW
    # ==================================================================
    @audited("frontdesk.void_charge", "folio_charge", severity=SEVERITY_WARNING, require_reason=True, capture_before=True)
    async def void_charge(
        self,
        ctx: OperationContext,
        charge_id: str,
        reason: str = "",
    ) -> ServiceResult:
        if not ctx.actor_is_super_admin and ctx.actor_role not in ("admin", "supervisor", "super_admin", "gm"):
            return ServiceResult.fail("Insufficient permission to void charge", "FORBIDDEN")

        charge = await self._db.folio_charges.find_one(
            {"id": charge_id, "tenant_id": ctx.tenant_id}, {"_id": 0}
        )
        if not charge:
            return ServiceResult.fail("Charge not found", "NOT_FOUND")
        if charge.get("voided"):
            return ServiceResult.success({"message": "Already voided (idempotent)", "idempotent": True})

        await self._db.folio_charges.update_one(
            {"id": charge_id},
            {
                "$set": {
                    "voided": True,
                    "voided_at": datetime.now(UTC).isoformat(),
                    "voided_by": ctx.actor_id,
                    "void_reason": reason,
                }
            },
        )

        # Reverse folio balance
        if charge.get("folio_id"):
            await self._db.folios.update_one(
                {"id": charge["folio_id"]},
                {"$inc": {"balance": -charge.get("total", 0)}},
            )

        # v95.1 — revenue raporu cache'ini geçersiz kıl (charge void)
        try:
            from cache_manager import cache as _cache
            if _cache:
                _cache.invalidate_tenant_cache(ctx.tenant_id, "folio_revenue_by_category")
        except ImportError:
            pass

        return ServiceResult.success(
            {
                "message": "Charge voided",
                "charge_id": charge_id,
                "amount_reversed": charge.get("total", 0),
                "reason": reason,
            }
        )


frontdesk_service_v2 = FrontdeskServiceV2()
