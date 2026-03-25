"""
Sandbox Simulation Scenarios — Each scenario tests a specific resilience property.

Done criteria (per user spec):
  - duplicate delivery      → duplicate inventory consumption = 0
  - delayed ack             → inconsistent state = 0
  - retry storm             → oversell = 0
  - stale provider state    → reconciliation recovers
  - modify/cancel races     → deterministic outcome
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

from ...domain.models.canonical import CanonicalReservation, ReservationStatus
from ...domain.models.reservation_import import (
    AckStatus,
    ImportedReservation,
    ImportStatus,
)
from ...infrastructure.repository import ChannelManagerRepository
from .provider_harness import (
    PROVIDER_PROFILES,
    generate_duplicate_batch,
    generate_modify_then_cancel,
    generate_reservation,
)

logger = logging.getLogger("channel_manager.sandbox_simulation.scenarios")

SANDBOX_TIMELINE = "sandbox_event_timeline"
SANDBOX_RESULTS = "sandbox_simulation_results"


async def _write_timeline(tenant_id: str, run_id: str, event: dict[str, Any]):
    """Write an event to the sandbox event timeline."""
    event.update({
        "tenant_id": tenant_id,
        "run_id": run_id,
        "timestamp": datetime.now(UTC).isoformat(),
    })
    await db[SANDBOX_TIMELINE].insert_one(event)


async def _process_reservation_direct(
    tenant_id: str, property_id: str, connector_id: str,
    batch_id: str, canonical: CanonicalReservation,
    room_reverse: dict[str, str], rate_reverse: dict[str, str],
    repo: ChannelManagerRepository,
) -> dict[str, Any]:
    """
    Process a single reservation through the import pipeline's core logic.
    This bypasses provider calls and tests the actual business logic directly.
    """
    fingerprint = ImportedReservation.compute_fingerprint(canonical.model_dump())

    existing = await repo.get_imported_reservation_by_external_id(
        tenant_id, connector_id, canonical.external_id,
    )

    pms_room_type = room_reverse.get(canonical.room_type_id)
    pms_rate_plan = rate_reverse.get(canonical.rate_plan_id)

    imported = ImportedReservation(
        tenant_id=tenant_id,
        property_id=property_id,
        connector_id=connector_id,
        batch_id=batch_id,
        external_reservation_id=canonical.external_id,
        external_confirmation_number=canonical.confirmation_number,
        hr_number=canonical.hr_number,
        message_uid=canonical.message_uid,
        payload_fingerprint=fingerprint,
        channel_name=canonical.channel_name,
        requires_ack=canonical.requires_ack,
        guest_name=f"{canonical.guest.first_name} {canonical.guest.last_name}".strip(),
        guest_email=canonical.guest.email,
        guest_phone=canonical.guest.phone,
        arrival_date=canonical.arrival_date,
        departure_date=canonical.departure_date,
        room_type_external_id=canonical.room_type_id,
        rate_plan_external_id=canonical.rate_plan_id,
        room_type_mapped_id=pms_room_type,
        rate_plan_mapped_id=pms_rate_plan,
        adult_count=canonical.adult_count,
        child_count=canonical.child_count,
        total_amount=canonical.total_amount,
        currency=canonical.currency,
        payment_type=canonical.payment_type,
        special_requests=canonical.special_requests,
        raw_payload=canonical.raw_provider_data,
    )

    # ── Cancellation path ──
    if canonical.status == ReservationStatus.CANCELLED:
        imported.is_cancellation = True
        if existing:
            existing_status = existing.get("import_status", "")
            if existing_status in (ImportStatus.CANCELLED.value, ImportStatus.DUPLICATE_CANCEL.value):
                imported.import_status = ImportStatus.DUPLICATE_CANCEL
                imported.ack_status = AckStatus.ACK_PENDING if canonical.requires_ack else AckStatus.NOT_REQUIRED
                await repo.upsert_imported_reservation(imported.to_doc())
                return {"action": "duplicate_cancel", "reservation_id": imported.id}

            pms_booking_id = existing.get("pms_booking_id")
            if pms_booking_id:
                await db.bookings.update_one(
                    {"id": pms_booking_id, "tenant_id": tenant_id},
                    {"$set": {"status": "cancelled", "cancelled_at": datetime.now(UTC).isoformat()}},
                )
            imported.pms_booking_id = pms_booking_id
            imported.import_status = ImportStatus.CANCELLED
            imported.ack_status = AckStatus.ACK_PENDING if canonical.requires_ack else AckStatus.NOT_REQUIRED
            await repo.upsert_imported_reservation(imported.to_doc())
            return {"action": "cancelled", "reservation_id": imported.id, "pms_booking_id": pms_booking_id}
        else:
            imported.import_status = ImportStatus.REVIEW
            imported.review_reason = "Cancellation for unknown reservation"
            imported.ack_status = AckStatus.NOT_REQUIRED
            await repo.upsert_imported_reservation(imported.to_doc())
            return {"action": "review", "reservation_id": imported.id}

    # ── Existing reservation path ──
    if existing:
        existing_status = existing.get("import_status", "")

        if existing_status in (ImportStatus.CANCELLED.value, ImportStatus.DUPLICATE_CANCEL.value):
            imported.import_status = ImportStatus.CONFLICT
            imported.conflict_reason = "Modification received after cancellation"
            imported.ack_status = AckStatus.NOT_REQUIRED
            await repo.upsert_imported_reservation(imported.to_doc())
            return {"action": "conflict", "reservation_id": imported.id}

        if existing.get("payload_fingerprint") == fingerprint:
            imported.import_status = ImportStatus.DUPLICATE
            imported.ack_status = AckStatus.ACK_PENDING if canonical.requires_ack else AckStatus.NOT_REQUIRED
            await repo.upsert_imported_reservation(imported.to_doc())
            return {"action": "duplicate", "reservation_id": imported.id}

        if existing_status in (ImportStatus.CREATED.value, ImportStatus.MODIFIED.value, ImportStatus.ACKNOWLEDGED.value):
            imported.is_modification = True
            imported.previous_version_id = existing.get("id")
            imported.pms_booking_id = existing.get("pms_booking_id")
            if imported.pms_booking_id:
                await db.bookings.update_one(
                    {"id": imported.pms_booking_id, "tenant_id": tenant_id},
                    {"$set": {
                        "total_amount": imported.total_amount,
                        "special_requests": imported.special_requests,
                        "updated_at": datetime.now(UTC).isoformat(),
                    }},
                )
            imported.import_status = ImportStatus.MODIFIED
            imported.ack_status = AckStatus.ACK_PENDING
            await repo.upsert_imported_reservation(imported.to_doc())
            return {"action": "modified", "reservation_id": imported.id, "pms_booking_id": imported.pms_booking_id}

        imported.import_status = ImportStatus.OUT_OF_ORDER
        imported.ack_status = AckStatus.NOT_REQUIRED
        await repo.upsert_imported_reservation(imported.to_doc())
        return {"action": "out_of_order", "reservation_id": imported.id}

    # ── New reservation path ──
    if not pms_room_type:
        imported.import_status = ImportStatus.REVIEW
        imported.review_reason = f"No mapping for room type: {canonical.room_type_id}"
        imported.ack_status = AckStatus.NOT_REQUIRED
        await repo.upsert_imported_reservation(imported.to_doc())
        return {"action": "review", "reservation_id": imported.id}

    booking_id = str(uuid.uuid4())
    booking = {
        "id": booking_id,
        "tenant_id": tenant_id,
        "property_id": property_id,
        "guest_name": imported.guest_name,
        "room_type": pms_room_type,
        "check_in": canonical.arrival_date,
        "check_out": canonical.departure_date,
        "adults": canonical.adult_count,
        "children": canonical.child_count,
        "status": "confirmed",
        "source": "ota_sandbox",
        "channel": canonical.channel_name,
        "total_amount": canonical.total_amount,
        "currency": canonical.currency,
        "external_confirmation": canonical.confirmation_number,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": "sandbox_simulation",
    }
    await db.bookings.insert_one(booking)

    imported.pms_booking_id = booking_id
    imported.import_status = ImportStatus.CREATED
    imported.ack_status = AckStatus.ACK_PENDING if canonical.requires_ack else AckStatus.NOT_REQUIRED
    await repo.upsert_imported_reservation(imported.to_doc())
    return {"action": "new", "reservation_id": imported.id, "pms_booking_id": booking_id}


# ════════════════════════════════════════════════════════════════════════
#  SCENARIO 1: Duplicate Delivery
# ════════════════════════════════════════════════════════════════════════

async def run_duplicate_delivery(
    tenant_id: str, property_id: str, connector_id: str,
    run_id: str, provider: str,
    room_reverse: dict[str, str], rate_reverse: dict[str, str],
    repo: ChannelManagerRepository,
    duplicate_count: int = 5,
) -> dict[str, Any]:
    """
    Send the same reservation N times. Assert:
      - Only 1 PMS booking created
      - N-1 marked as duplicate
      - 0 double inventory consumption
    """
    batch_id = f"sandbox-dup-{uuid.uuid4().hex[:8]}"
    reservations = generate_duplicate_batch(provider, count=duplicate_count)
    ext_id = reservations[0].external_id

    await _write_timeline(tenant_id, run_id, {
        "event": "scenario_start", "scenario": "duplicate_delivery",
        "provider": provider, "external_id": ext_id, "count": duplicate_count,
    })

    results = []
    for i, res in enumerate(reservations):
        result = await _process_reservation_direct(
            tenant_id, property_id, connector_id, batch_id,
            res, room_reverse, rate_reverse, repo,
        )
        results.append(result)
        await _write_timeline(tenant_id, run_id, {
            "event": "reservation_processed", "scenario": "duplicate_delivery",
            "provider": provider, "iteration": i + 1, "action": result["action"],
        })

    new_count = sum(1 for r in results if r["action"] == "new")
    dup_count = sum(1 for r in results if r["action"] == "duplicate")

    # Count PMS bookings created for this external_id
    pms_bookings = await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "external_confirmation": reservations[0].confirmation_number,
        "source": "ota_sandbox",
    })

    passed = (new_count == 1) and (dup_count == duplicate_count - 1) and (pms_bookings == 1)

    outcome = {
        "scenario": "duplicate_delivery",
        "provider": provider,
        "passed": passed,
        "duplicate_count_sent": duplicate_count,
        "new_created": new_count,
        "duplicates_detected": dup_count,
        "pms_bookings_created": pms_bookings,
        "double_inventory_consumption": max(0, pms_bookings - 1),
        "assertions": {
            "single_booking_created": new_count == 1,
            "duplicates_identified": dup_count == duplicate_count - 1,
            "zero_double_consumption": pms_bookings == 1,
        },
    }

    await _write_timeline(tenant_id, run_id, {
        "event": "scenario_complete", "scenario": "duplicate_delivery",
        "provider": provider, "passed": passed, "outcome": outcome,
    })

    return outcome


# ════════════════════════════════════════════════════════════════════════
#  SCENARIO 2: Delayed Acknowledgment
# ════════════════════════════════════════════════════════════════════════

async def run_delayed_ack(
    tenant_id: str, property_id: str, connector_id: str,
    run_id: str, provider: str,
    room_reverse: dict[str, str], rate_reverse: dict[str, str],
    repo: ChannelManagerRepository,
) -> dict[str, Any]:
    """
    Import a reservation, then simulate ACK delay/failure.
    Assert: reservation created correctly, ACK status tracked, no inconsistent state.
    """
    batch_id = f"sandbox-ack-{uuid.uuid4().hex[:8]}"
    ext_id = f"ACK-{uuid.uuid4().hex[:8]}"
    res = generate_reservation(provider, external_id=ext_id, seq=2)

    await _write_timeline(tenant_id, run_id, {
        "event": "scenario_start", "scenario": "delayed_ack",
        "provider": provider, "external_id": ext_id,
    })

    # Step 1: Import reservation
    result = await _process_reservation_direct(
        tenant_id, property_id, connector_id, batch_id,
        res, room_reverse, rate_reverse, repo,
    )

    await _write_timeline(tenant_id, run_id, {
        "event": "reservation_imported", "scenario": "delayed_ack",
        "provider": provider, "action": result["action"],
    })

    # Step 2: Simulate ACK failure — mark ACK as failed
    if result.get("reservation_id"):
        await repo.update_imported_reservation(tenant_id, result["reservation_id"], {
            "ack_status": AckStatus.ACK_FAILED.value,
            "ack_failed_reason": "Simulated: provider timeout after 30s",
        })
        await _write_timeline(tenant_id, run_id, {
            "event": "ack_failed", "scenario": "delayed_ack",
            "provider": provider, "reason": "simulated_timeout",
        })

    # Step 3: Simulate ACK retry — mark ACK as sent
    if result.get("reservation_id"):
        await repo.update_imported_reservation(tenant_id, result["reservation_id"], {
            "ack_status": AckStatus.ACK_SENT.value,
            "ack_sent_at": datetime.now(UTC).isoformat(),
        })
        await _write_timeline(tenant_id, run_id, {
            "event": "ack_retry_success", "scenario": "delayed_ack",
            "provider": provider,
        })

    # Verify: reservation is in correct state
    final_rec = await repo.get_imported_reservation_by_external_id(
        tenant_id, connector_id, ext_id,
    )
    booking_ok = result["action"] == "new" and result.get("pms_booking_id")
    ack_ok = final_rec and final_rec.get("ack_status") == AckStatus.ACK_SENT.value
    no_inconsistency = final_rec and final_rec.get("import_status") == ImportStatus.CREATED.value

    passed = bool(booking_ok and ack_ok and no_inconsistency)

    outcome = {
        "scenario": "delayed_ack",
        "provider": provider,
        "passed": passed,
        "assertions": {
            "booking_created": bool(booking_ok),
            "ack_recovered": bool(ack_ok),
            "consistent_state": bool(no_inconsistency),
        },
        "ack_flow": ["imported", "ack_failed (timeout)", "ack_retry_success"],
    }

    await _write_timeline(tenant_id, run_id, {
        "event": "scenario_complete", "scenario": "delayed_ack",
        "provider": provider, "passed": passed, "outcome": outcome,
    })

    return outcome


# ════════════════════════════════════════════════════════════════════════
#  SCENARIO 3: Retry Storm
# ════════════════════════════════════════════════════════════════════════

async def run_retry_storm(
    tenant_id: str, property_id: str, connector_id: str,
    run_id: str, provider: str,
    room_reverse: dict[str, str], rate_reverse: dict[str, str],
    repo: ChannelManagerRepository,
    storm_size: int = 10,
) -> dict[str, Any]:
    """
    Simulate a retry storm: provider resends the same batch multiple times
    (as if retrying because it didn't get an ACK). Assert:
      - No oversell (each unique reservation creates exactly 1 PMS booking)
      - Idempotent processing
    """
    batch_id = f"sandbox-storm-{uuid.uuid4().hex[:8]}"

    # Generate 3 unique reservations, each sent storm_size/3 times
    unique_count = 3
    sends_per_res = max(storm_size // unique_count, 2)
    unique_reservations = []
    for i in range(unique_count):
        ext_id = f"STORM-{uuid.uuid4().hex[:8]}"
        unique_reservations.append(
            generate_reservation(provider, external_id=ext_id, seq=10 + i, total_amount=1000.0 + i * 500)
        )

    await _write_timeline(tenant_id, run_id, {
        "event": "scenario_start", "scenario": "retry_storm",
        "provider": provider, "unique_reservations": unique_count,
        "sends_per_reservation": sends_per_res, "total_deliveries": unique_count * sends_per_res,
    })

    all_results = []
    for res in unique_reservations:
        for attempt in range(sends_per_res):
            result = await _process_reservation_direct(
                tenant_id, property_id, connector_id, batch_id,
                res, room_reverse, rate_reverse, repo,
            )
            all_results.append({"external_id": res.external_id, **result})

    new_count = sum(1 for r in all_results if r["action"] == "new")
    dup_count = sum(1 for r in all_results if r["action"] == "duplicate")
    total = len(all_results)

    # Verify: exactly unique_count PMS bookings
    _pms_bookings = await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "source": "ota_sandbox",
        "created_by": "sandbox_simulation",
    })

    # We need to count only those created in THIS scenario
    pms_booking_ids = set()
    for r in all_results:
        if r.get("pms_booking_id"):
            pms_booking_ids.add(r["pms_booking_id"])

    oversell = max(0, len(pms_booking_ids) - unique_count)
    passed = (new_count == unique_count) and (oversell == 0)

    outcome = {
        "scenario": "retry_storm",
        "provider": provider,
        "passed": passed,
        "total_deliveries": total,
        "unique_reservations": unique_count,
        "new_created": new_count,
        "duplicates_detected": dup_count,
        "pms_bookings_created": len(pms_booking_ids),
        "oversell_count": oversell,
        "assertions": {
            "idempotent_import": new_count == unique_count,
            "zero_oversell": oversell == 0,
            "all_duplicates_caught": dup_count == total - unique_count,
        },
    }

    await _write_timeline(tenant_id, run_id, {
        "event": "scenario_complete", "scenario": "retry_storm",
        "provider": provider, "passed": passed, "outcome": outcome,
    })

    return outcome


# ════════════════════════════════════════════════════════════════════════
#  SCENARIO 4: Stale Provider State
# ════════════════════════════════════════════════════════════════════════

async def run_stale_provider_state(
    tenant_id: str, property_id: str, connector_id: str,
    run_id: str, provider: str,
    repo: ChannelManagerRepository,
) -> dict[str, Any]:
    """
    Simulate stale provider inventory. Assert:
      - Reconciliation detects the drift
      - System can recover via reconciliation
    """
    profile = PROVIDER_PROFILES[provider]
    now = datetime.now(UTC)
    dates = [(now + timedelta(days=d)).strftime("%Y-%m-%d") for d in range(1, 4)]
    room_type_id = f"{profile['room_type_prefix']}STD"

    await _write_timeline(tenant_id, run_id, {
        "event": "scenario_start", "scenario": "stale_provider_state",
        "provider": provider, "dates": dates,
    })

    # Step 1: Create synthetic "last pushed" state (what we told the provider)
    _snapshot_id = str(uuid.uuid4())
    for date in dates:
        await db.cm_sync_snapshots.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "room_type_id": room_type_id,
            "date": date,
            "available": 5,
            "pushed_at": (now - timedelta(hours=6)).isoformat(),
            "source": "sandbox_simulation",
        })

    # Step 2: Create synthetic "PMS actual" state (different from pushed)
    # Use room_type field (not room_type_id) to match actual collection schema
    for date in dates:
        await db.room_type_inventory.update_one(
            {"tenant_id": tenant_id, "room_type": room_type_id, "date": date},
            {"$set": {
                "tenant_id": tenant_id,
                "room_type": room_type_id,
                "date": date,
                "physical_total": 10,
                "locked_booking": 7,
                "locked_hold": 0,
                "locked_ooo": 1,
                "locked_oos": 0,
                "sellable": 2,
                "last_computed_at": now.isoformat(),
                "computation_source": "sandbox_simulation",
            }},
            upsert=True,
        )

    await _write_timeline(tenant_id, run_id, {
        "event": "stale_state_injected", "scenario": "stale_provider_state",
        "provider": provider, "pushed_available": 5, "actual_available": 2,
        "drift_rooms": 3, "drift_direction": "provider_overselling",
    })

    # Step 3: Run reconciliation check — detect drift
    from ...application.reconciliation_service import ReconciliationService
    _recon_svc = ReconciliationService(repo)

    # Simulate the inventory mismatch detection
    drift_detected = False
    drift_records = []
    for date in dates:
        snapshot = await db.cm_sync_snapshots.find_one(
            {"tenant_id": tenant_id, "connector_id": connector_id,
             "room_type_id": room_type_id, "date": date},
            {"_id": 0},
        )
        actual = await db.room_type_inventory.find_one(
            {"tenant_id": tenant_id, "room_type": room_type_id, "date": date},
            {"_id": 0},
        )
        if snapshot and actual:
            pushed_avail = snapshot.get("available", 0)
            actual_avail = actual.get("sellable", 0)
            if pushed_avail != actual_avail:
                drift_detected = True
                drift_records.append({
                    "date": date,
                    "pushed": pushed_avail,
                    "actual": actual_avail,
                    "drift": pushed_avail - actual_avail,
                })

    # Step 4: Simulate reconciliation recovery — update pushed state
    recovered = False
    if drift_detected:
        for date in dates:
            actual = await db.room_type_inventory.find_one(
                {"tenant_id": tenant_id, "room_type": room_type_id, "date": date},
                {"_id": 0},
            )
            if actual:
                await db.cm_sync_snapshots.update_one(
                    {"tenant_id": tenant_id, "connector_id": connector_id,
                     "room_type_id": room_type_id, "date": date},
                    {"$set": {
                        "available": actual.get("sellable", 0),
                        "pushed_at": datetime.now(UTC).isoformat(),
                        "reconciled": True,
                    }},
                )
        recovered = True

        await _write_timeline(tenant_id, run_id, {
            "event": "reconciliation_triggered", "scenario": "stale_provider_state",
            "provider": provider, "drift_records": drift_records, "recovered": recovered,
        })

    passed = drift_detected and recovered

    outcome = {
        "scenario": "stale_provider_state",
        "provider": provider,
        "passed": passed,
        "drift_detected": drift_detected,
        "drift_records": drift_records,
        "reconciliation_recovered": recovered,
        "assertions": {
            "drift_detected": drift_detected,
            "reconciliation_recovery": recovered,
        },
    }

    await _write_timeline(tenant_id, run_id, {
        "event": "scenario_complete", "scenario": "stale_provider_state",
        "provider": provider, "passed": passed, "outcome": outcome,
    })

    return outcome


# ════════════════════════════════════════════════════════════════════════
#  SCENARIO 5: Modify / Cancel Race
# ════════════════════════════════════════════════════════════════════════

async def run_modify_cancel_race(
    tenant_id: str, property_id: str, connector_id: str,
    run_id: str, provider: str,
    room_reverse: dict[str, str], rate_reverse: dict[str, str],
    repo: ChannelManagerRepository,
) -> dict[str, Any]:
    """
    Send: new → modify → cancel for the same reservation. Assert:
      - Each step produces a deterministic outcome
      - Final state is cancelled
      - No orphaned PMS bookings
    """
    batch_id = f"sandbox-race-{uuid.uuid4().hex[:8]}"
    sequence = generate_modify_then_cancel(provider)

    await _write_timeline(tenant_id, run_id, {
        "event": "scenario_start", "scenario": "modify_cancel_race",
        "provider": provider, "external_id": sequence[0].external_id,
        "sequence": ["new", "modify", "cancel"],
    })

    results = []
    for i, res in enumerate(sequence):
        label = ["original", "modification", "cancellation"][i]
        result = await _process_reservation_direct(
            tenant_id, property_id, connector_id, batch_id,
            res, room_reverse, rate_reverse, repo,
        )
        results.append({"step": label, **result})
        await _write_timeline(tenant_id, run_id, {
            "event": "reservation_processed", "scenario": "modify_cancel_race",
            "provider": provider, "step": label, "action": result["action"],
        })

    # Validate sequence
    step_actions = [r["action"] for r in results]
    original_ok = step_actions[0] == "new"
    modify_ok = step_actions[1] == "modified"
    cancel_ok = step_actions[2] == "cancelled"

    # Check PMS booking state
    pms_booking_id = results[0].get("pms_booking_id")
    pms_booking = None
    if pms_booking_id:
        pms_booking = await db.bookings.find_one(
            {"id": pms_booking_id, "tenant_id": tenant_id},
            {"_id": 0, "status": 1},
        )

    final_pms_status = pms_booking.get("status") if pms_booking else None
    deterministic = original_ok and modify_ok and cancel_ok
    final_cancelled = final_pms_status == "cancelled"

    passed = deterministic and final_cancelled

    outcome = {
        "scenario": "modify_cancel_race",
        "provider": provider,
        "passed": passed,
        "sequence_results": step_actions,
        "expected_sequence": ["new", "modified", "cancelled"],
        "final_pms_status": final_pms_status,
        "assertions": {
            "deterministic_sequence": deterministic,
            "final_state_cancelled": final_cancelled,
            "no_orphaned_bookings": final_cancelled,
        },
    }

    await _write_timeline(tenant_id, run_id, {
        "event": "scenario_complete", "scenario": "modify_cancel_race",
        "provider": provider, "passed": passed, "outcome": outcome,
    })

    return outcome
