"""
Atomic Check-in / Check-out — Transaction Safety
=================================================
Single entry point for ALL check-in and check-out operations.

Uses MongoDB transactions to guarantee:
  - Booking status, room status, folio, housekeeping, audit, and outbox
    are updated atomically — ALL succeed or ALL roll back.

Every code path that performs a check-in or check-out MUST call these functions.
Direct db.bookings.update_one({status: "checked_in/checked_out"}) is FORBIDDEN
outside this module.
"""
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pymongo import ReadPreference
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from core.database import client, db

logger = logging.getLogger("core.atomic_checkin_checkout")

CHECKIN_ELIGIBLE_STATUSES = ["confirmed", "guaranteed", "pending"]
ROOM_BLOCKED_STATUSES = ["out_of_order", "out_of_service", "maintenance"]


class CheckInError(Exception):
    """Raised when check-in fails validation."""


class CheckOutError(Exception):
    """Raised when check-out fails validation."""


# ═══════════════════════════════════════════════════════════
#  CHECK-IN (ATOMIC)
# ═══════════════════════════════════════════════════════════

async def check_in_booking_atomic(
    booking_id: str,
    tenant_id: str,
    actor_id: str,
    actor_name: str = "",
    override_reason: str | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Atomically check in a booking.

    Inside ONE transaction:
      1. Validate booking exists & status eligible
      2. Validate room not blocked
      3. Ensure folio exists (create if missing)
      4. Update booking → checked_in
      5. Update room → occupied
      6. Insert audit log
      7. Insert outbox event

    Returns dict with success info.
    Raises CheckInError on validation failure (no partial state).
    """
    now = datetime.now(UTC)
    now_iso = now.isoformat()

    async with await client.start_session() as session:
        async with session.start_transaction(
            read_concern=ReadConcern("snapshot"),
            write_concern=WriteConcern("majority"),
            read_preference=ReadPreference.PRIMARY,
        ):
            # ── 1. Load & validate booking ──
            booking = await db.bookings.find_one(
                {"id": booking_id, "tenant_id": tenant_id},
                {"_id": 0},
                session=session,
            )
            if not booking:
                raise CheckInError("Booking not found")

            current_status = booking.get("status", "")
            if current_status not in CHECKIN_ELIGIBLE_STATUSES:
                raise CheckInError(
                    f"Cannot check in booking with status '{current_status}'. "
                    f"Eligible statuses: {CHECKIN_ELIGIBLE_STATUSES}"
                )

            room_id = booking.get("room_id")
            if not room_id:
                raise CheckInError("No room assigned to this booking")

            # ── 2. Validate room ──
            room = await db.rooms.find_one(
                {"id": room_id, "tenant_id": tenant_id},
                {"_id": 0},
                session=session,
            )
            if not room:
                raise CheckInError("Assigned room not found")

            room_status = room.get("status", "")
            allowed_room_statuses = {"available", "inspected", "clean"}
            if room_status in ROOM_BLOCKED_STATUSES:
                raise CheckInError(
                    f"Room {room.get('room_number')} is {room_status} and cannot be used for check-in"
                )
            if room_status not in allowed_room_statuses and not override_reason:
                raise CheckInError(
                    f"Room {room.get('room_number')} is not ready (status: {room_status}). "
                    f"Provide override_reason to force check-in."
                )

            # ── 3. Ensure folio exists ──
            folio = await db.folios.find_one(
                {"booking_id": booking_id, "tenant_id": tenant_id},
                {"_id": 0},
                session=session,
            )
            if not folio:
                folio_id = str(uuid.uuid4())
                folio_count = await db.folios.count_documents(
                    {"tenant_id": tenant_id}, session=session
                )
                folio_number = f"F-{now.year}-{(folio_count + 1):05d}"
                folio_doc = {
                    "id": folio_id,
                    "tenant_id": tenant_id,
                    "booking_id": booking_id,
                    "folio_number": folio_number,
                    "folio_type": "guest",
                    "status": "open",
                    "guest_id": booking.get("guest_id"),
                    "balance": 0.0,
                    "created_at": now_iso,
                }
                await db.folios.insert_one(folio_doc, session=session)
                logger.info("Auto-created folio %s for booking %s", folio_id, booking_id)

            # ── 4. Update booking → checked_in ──
            booking_update = {
                "status": "checked_in",
                "checked_in_at": now_iso,
                "checked_in_by": actor_name or actor_id,
                "updated_at": now_iso,
            }
            if override_reason:
                booking_update["check_in_override_reason"] = override_reason
            if extra_fields:
                booking_update.update(extra_fields)

            await db.bookings.update_one(
                {"id": booking_id, "tenant_id": tenant_id},
                {"$set": booking_update},
                session=session,
            )

            # ── 5. Update room → occupied (atomic CAS — F8A tur-22 / CI #37
            #        P0 fix: line-104 pre-check is TOCTOU vs the unconditional
            #        update_one that used to live here; concurrent OOO/maintenance
            #        marks could change room.status between find_one and
            #        update_one, leading to walk-in/check-in succeeding on a
            #        blocked room and returning success=true with a fresh booking
            #        — overbook + maintenance-risk. CAS filter requires status
            #        to STILL be in the allowed set at write time; if not,
            #        modified_count==0 → raise CheckInError → transaction
            #        rollback → no booking persisted, no audit, no outbox).
            if override_reason:
                # Override path: any non-blocked status is acceptable.
                cas_status_filter = {"$nin": ROOM_BLOCKED_STATUSES}
            else:
                cas_status_filter = {"$in": list(allowed_room_statuses)}
            room_update_result = await db.rooms.update_one(
                {
                    "id": room_id,
                    "tenant_id": tenant_id,
                    "status": cas_status_filter,
                },
                {"$set": {"status": "occupied", "current_booking_id": booking_id}},
                session=session,
            )
            if room_update_result.modified_count == 0:
                raise CheckInError(
                    f"Room {room.get('room_number')} status changed during check-in "
                    f"(concurrent state mutation; check-in aborted to prevent overbook)"
                )

            # ── 6. Audit log ──
            audit_doc = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "entity_type": "booking",
                "entity_id": booking_id,
                "action": "check_in_completed",
                "performed_by": actor_id,
                "metadata": {
                    "room_id": room_id,
                    "room_number": room.get("room_number"),
                    "override_reason": override_reason,
                },
                "timestamp": now_iso,
            }
            await db.pms_audit_trail.insert_one(audit_doc, session=session)

            # ── 7. Outbox event ──
            outbox_doc = {
                "id": str(uuid.uuid4()),
                "event_id": str(uuid.uuid4()),
                "event_type": "guest.checked_in.v1",
                "tenant_id": tenant_id,
                "payload": {
                    "booking_id": booking_id,
                    "room_id": room_id,
                    "guest_id": booking.get("guest_id"),
                    "checked_in_at": now_iso,
                },
                "status": "pending",
                "created_at": now_iso,
                "retry_count": 0,
            }
            await db.outbox_events.insert_one(outbox_doc, session=session)

    logger.info(
        "Atomic check-in completed: booking=%s room=%s actor=%s",
        booking_id, room_id, actor_id,
    )

    # KBS auto-enqueue (transaction sonrası, non-blocking).
    # Hata olursa log'lar; check-in başarısız olmaz.
    try:
        from core.kbs_auto_enqueue import auto_enqueue_kbs
        await auto_enqueue_kbs(
            tenant_id, booking_id, action="checkin",
            actor=f"system:checkin:{actor_id}",
        )
    except Exception as e:
        logger.warning("KBS auto-enqueue (checkin) failed: %s", e)

    return {
        "success": True,
        "booking_id": booking_id,
        "room_id": room_id,
        "room_number": room.get("room_number"),
        "checked_in_at": now_iso,
    }


# ═══════════════════════════════════════════════════════════
#  CHECK-OUT (ATOMIC)
# ═══════════════════════════════════════════════════════════

async def check_out_booking_atomic(
    booking_id: str,
    tenant_id: str,
    actor_id: str,
    actor_name: str = "",
    force: bool = False,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Atomically check out a booking.

    Inside ONE transaction:
      1. Validate booking exists & status = checked_in
      2. Load folio & validate balance (unless force=True)
      3. Update booking → checked_out
      4. Update room → dirty
      5. Close folio
      6. Create housekeeping task (deduplicated)
      7. Insert audit log
      8. Insert outbox event

    Returns dict with success info.
    Raises CheckOutError on validation failure (no partial state).
    """
    now = datetime.now(UTC)
    now_iso = now.isoformat()

    async with await client.start_session() as session:
        async with session.start_transaction(
            read_concern=ReadConcern("snapshot"),
            write_concern=WriteConcern("majority"),
            read_preference=ReadPreference.PRIMARY,
        ):
            # ── 1. Load & validate booking ──
            booking = await db.bookings.find_one(
                {"id": booking_id, "tenant_id": tenant_id},
                {"_id": 0},
                session=session,
            )
            if not booking:
                raise CheckOutError("Booking not found")

            current_status = booking.get("status", "")
            if current_status != "checked_in":
                raise CheckOutError(
                    f"Cannot check out booking with status '{current_status}'. "
                    f"Only 'checked_in' bookings can be checked out."
                )

            room_id = booking.get("room_id")

            # ── 2. Folio balance validation ──
            if not force:
                folios = await db.folios.find(
                    {"booking_id": booking_id, "tenant_id": tenant_id, "status": "open"},
                    {"_id": 0},
                    session=session,
                ).to_list(10)

                for folio in folios:
                    charges = await db.folio_charges.find(
                        {"folio_id": folio["id"], "tenant_id": tenant_id, "voided": False},
                        {"_id": 0, "total": 1, "amount": 1},
                        session=session,
                    ).to_list(500)
                    payments = await db.payments.find(
                        {"folio_id": folio["id"], "tenant_id": tenant_id, "voided": False},
                        {"_id": 0, "amount": 1},
                        session=session,
                    ).to_list(500)

                    total_charges = sum(c.get("total", c.get("amount", 0)) for c in charges)
                    total_payments = sum(p.get("amount", 0) for p in payments)
                    balance = round(total_charges - total_payments, 2)

                    if balance > 0.01:
                        raise CheckOutError(
                            f"Folio {folio.get('folio_number')} has unpaid balance of {balance}. "
                            f"Use force=True to override."
                        )

            # ── 3. Update booking → checked_out ──
            booking_update = {
                "status": "checked_out",
                "checked_out_at": now_iso,
                "checked_out_by": actor_name or actor_id,
                "updated_at": now_iso,
            }
            if extra_fields:
                booking_update.update(extra_fields)

            await db.bookings.update_one(
                {"id": booking_id, "tenant_id": tenant_id},
                {"$set": booking_update},
                session=session,
            )

            # ── 4. Update room → dirty ──
            if room_id:
                await db.rooms.update_one(
                    {"id": room_id, "tenant_id": tenant_id},
                    {"$set": {
                        "status": "dirty",
                        "current_booking_id": None,
                        "housekeeping_status": "dirty",
                        "housekeeping_updated_at": now_iso,
                        "housekeeping_updated_by": f"Sistem (Check-out by {actor_name or actor_id})",
                    }},
                    session=session,
                )

            # ── 5. Close open folios ──
            await db.folios.update_many(
                {"booking_id": booking_id, "tenant_id": tenant_id, "status": "open"},
                {"$set": {"status": "closed", "closed_at": now_iso}},
                session=session,
            )

            # ── 5b. Release room_night_locks (F8A tur-21 perf: inline single
            #        round-trip inside transaction; replaces post-commit
            #        release_booking_nights helper which did 3 RTs and
            #        regressed force-checkout latency from ~700ms to ~2000ms,
            #        causing CI #36 02-B 180s timeout. Atomic with state
            #        transition; audit captured in step-7 metadata below).
            locks_release_result = await db.room_night_locks.delete_many(
                {"tenant_id": tenant_id, "booking_id": booking_id},
                session=session,
            )
            released_locks_count = locks_release_result.deleted_count

            # ── 6. Create housekeeping task (deduplicated) ──
            if room_id:
                existing_hk = await db.housekeeping_tasks.find_one(
                    {
                        "tenant_id": tenant_id,
                        "booking_id": booking_id,
                        "task_type": "checkout_cleaning",
                        "status": {"$nin": ["cancelled"]},
                    },
                    {"_id": 0, "id": 1},
                    session=session,
                )
                if not existing_hk:
                    hk_doc = {
                        "id": str(uuid.uuid4()),
                        "tenant_id": tenant_id,
                        "room_id": room_id,
                        "booking_id": booking_id,
                        "task_type": "checkout_cleaning",
                        "status": "pending",
                        "priority": "high",
                        "created_at": now_iso,
                        "created_by": "system",
                        "notes": f"Auto-created on checkout of booking {booking_id}",
                    }
                    await db.housekeeping_tasks.insert_one(hk_doc, session=session)

            # ── 7. Audit log ──
            audit_doc = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "entity_type": "booking",
                "entity_id": booking_id,
                "action": "check_out_completed",
                "performed_by": actor_id,
                "metadata": {
                    "room_id": room_id,
                    "forced": force,
                    "released_locks_count": released_locks_count,
                },
                "timestamp": now_iso,
            }
            await db.pms_audit_trail.insert_one(audit_doc, session=session)

            # ── 8. Outbox event ──
            outbox_doc = {
                "id": str(uuid.uuid4()),
                "event_id": str(uuid.uuid4()),
                "event_type": "guest.checked_out.v1",
                "tenant_id": tenant_id,
                "payload": {
                    "booking_id": booking_id,
                    "room_id": room_id,
                    "guest_id": booking.get("guest_id"),
                    "checked_out_at": now_iso,
                },
                "status": "pending",
                "created_at": now_iso,
                "retry_count": 0,
            }
            await db.outbox_events.insert_one(outbox_doc, session=session)

    # Af-sadakat marketplace integration: outbound olay (transaction sonrası)
    try:
        from core.afsadakat_outbound import EV_GUEST_CHECKED_OUT, emit_event
        await emit_event(
            tenant_id,
            EV_GUEST_CHECKED_OUT,
            {
                "booking_id": booking_id,
                "room_id": room_id,
                "guest_id": booking.get("guest_id"),
                "checked_out_at": now_iso,
                "actor_id": actor_id,
            },
        )
    except Exception:
        pass

    # KBS auto-enqueue (transaction sonrası, non-blocking).
    try:
        from core.kbs_auto_enqueue import auto_enqueue_kbs
        await auto_enqueue_kbs(
            tenant_id, booking_id, action="checkout",
            actor=f"system:checkout:{actor_id}",
        )
    except Exception as e:
        logger.warning("KBS auto-enqueue (checkout) failed: %s", e)

    logger.info(
        "Atomic check-out completed: booking=%s room=%s actor=%s forced=%s",
        booking_id, room_id, actor_id, force,
    )
    return {
        "success": True,
        "booking_id": booking_id,
        "room_id": room_id,
        "checked_out_at": now_iso,
    }


# ═══════════════════════════════════════════════════════════
#  INDEX CREATION
# ═══════════════════════════════════════════════════════════

async def ensure_checkin_checkout_indexes() -> None:
    """Create indexes required for safe check-in/check-out operations."""
    indexes = [
        {
            "collection": "bookings",
            "keys": [("tenant_id", 1), ("id", 1)],
            "name": "idx_booking_tenant_id",
            "kwargs": {"unique": True},
        },
        {
            "collection": "folios",
            "keys": [("tenant_id", 1), ("booking_id", 1)],
            "name": "idx_folio_tenant_booking",
            "kwargs": {},
        },
        {
            "collection": "housekeeping_tasks",
            "keys": [("tenant_id", 1), ("booking_id", 1), ("task_type", 1), ("status", 1)],
            "name": "idx_hk_task_dedup",
            "kwargs": {},
        },
        {
            "collection": "outbox_events",
            "keys": [("tenant_id", 1), ("status", 1), ("created_at", 1)],
            "name": "idx_outbox_tenant_status",
            "kwargs": {},
        },
    ]
    for idx in indexes:
        try:
            coll = db[idx["collection"]]
            await coll.create_index(
                idx["keys"], name=idx["name"], background=True, **idx["kwargs"]
            )
        except Exception as e:
            if "IndexOptionsConflict" in str(e) or "already exists" in str(e):
                logger.info("Index %s already exists, skipping", idx["name"])
            else:
                logger.warning("Index creation failed for %s: %s", idx["name"], e)
    logger.info("Check-in/check-out indexes ensured")
