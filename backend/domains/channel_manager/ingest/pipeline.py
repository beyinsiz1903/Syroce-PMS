"""
Reservation Ingest — Production-Grade Pipeline
================================================

Unified ingest pipeline with full traceability and hardening:

  Stage 1 → Persist raw event (already done before pipeline)
  Stage 2 → Duplicate detection (provider_event_id)
  Stage 3 → Payload hash check (canonical + raw)
  Stage 4 → Stale event detection (provider_timestamp vs received_timestamp)
  Stage 5 → Normalize payload → canonical reservation
  Stage 6 → Mapping resolution (HARD FAIL on unmapped)
  Stage 7 → Decision engine + mutation detection
  Stage 8 → Concurrency control (reservation-scoped optimistic lock)
  Stage 9 → Execute decision (lineage update + trace enrichment)

TIMELINE: Writes normalized, deduplicated, validated stages for end-to-end traceability.
"""

import asyncio
import logging
import uuid as _uuid
from collections.abc import Awaitable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any

from core.booking_realtime import publish_booking_change
from core.database import db
from domains.channel_manager import unified_repository as repo
from domains.channel_manager.data_model import (
    COLL_RAW_CHANNEL_EVENTS,
    COLL_RESERVATION_LINEAGE,
    CaseSeverity,
    CaseStatus,
    CaseType,
    ConnectorProvider,
    MutationType,
    ReconciliationCase,
    ReservationLineage,
)

from .decision_engine import IngestDecision, decide, detect_mutation_type
from .normalizer import compute_canonical_hash, normalize

logger = logging.getLogger("ingest.pipeline")

# Concurrency: lock TTL for reservation-scoped processing
LOCK_TTL_SECONDS = 30
LOCK_HEARTBEAT_SECONDS = 10


class ReservationLockLostError(RuntimeError):
    """Raised when a reservation mutation loses its ownership lease."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _timeline_append(**kwargs):
    """Fire-and-forget timeline write. Returns a coroutine."""
    try:
        from controlplane.timeline_writer import get_timeline_writer

        return get_timeline_writer().append(**kwargs)
    except Exception:

        async def _noop():
            return None

        return _noop()


def _safe_normalized_timeline_metadata(
    canonical: dict[str, Any],
    canonical_hash: str | None = None,
) -> dict[str, Any]:
    """Return operational fields without guest identity or monetary values."""
    return {
        "check_in": canonical.get("check_in", ""),
        "check_out": canonical.get("check_out", ""),
        "room_type_code": canonical.get("room_type_code", ""),
        "provider_room_number": canonical.get("provider_room_number", ""),
        "rate_plan_code": canonical.get("rate_plan_code", ""),
        "currency": canonical.get("currency", ""),
        "canonical_status": canonical.get("status", ""),
        "canonical_hash": canonical_hash or compute_canonical_hash(canonical),
    }


class PipelineResult:
    def __init__(self, event_id: str):
        self.event_id = event_id
        self.decision: str = ""
        self.reason: str = ""
        self.status: str = "pending"
        self.error: str | None = None
        self.lineage_id: str | None = None
        self.case_id: str | None = None
        self.mutation_type: str | None = None
        self.trace_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "decision": self.decision,
            "reason": self.reason,
            "status": self.status,
            "error": self.error,
            "lineage_id": self.lineage_id,
            "case_id": self.case_id,
            "mutation_type": self.mutation_type,
            "trace_id": self.trace_id,
        }


async def process_event(event: dict[str, Any]) -> PipelineResult:
    """
    Process a single raw_channel_event through the full pipeline.
    The event must already be persisted in raw_channel_events.

    Timeline stages written:
      - deduplicated — after dedup check (Stage 2/3/4)
      - normalized — after payload normalization (Stage 5)
      - validated — after mapping resolution (Stage 6)
    """
    result = PipelineResult(event["id"])
    result.trace_id = event.get("trace_id") or event.get("correlation_id", "")
    tenant_id = event["tenant_id"]
    property_id = event["property_id"]
    provider = event["provider"]
    existing_lineage = None
    lock_owner_token: str | None = None
    lock_lost = asyncio.Event()
    lock_heartbeat_task: asyncio.Task[None] | None = None
    correlation_id = event.get("correlation_id", "")
    ext_res_id = event.get("external_reservation_id", "")
    replay_of_failed = bool(event.get("replay_of_failed"))

    # Ensure tenant context is set for strict mode
    from core.tenant_db import set_tenant_context

    set_tenant_context(tenant_id)

    try:
        # ── Stage 2: Duplicate Detection ──────────────────────────
        provider_event_id = event.get("provider_event_id", "")
        if provider_event_id and not replay_of_failed:
            is_dup = await repo.check_provider_event_exists(
                tenant_id,
                provider,
                provider_event_id,
            )
            if is_dup:
                result.decision = IngestDecision.SKIP
                result.reason = "Duplicate provider event"
                result.status = "duplicate"
                await _finalize_event(event["id"], "duplicate", result)
                # Timeline: deduplicated (duplicate detected)
                await _timeline_append(
                    tenant_id=tenant_id,
                    correlation_id=correlation_id,
                    entity_type="reservation",
                    external_id=ext_res_id,
                    stage="deduplicated",
                    status="duplicate",
                    source="ingest_pipeline",
                    provider=provider,
                    metadata={
                        "duplicate_type": "provider_event_id",
                        "decision": "skip",
                        "reason": result.reason,
                    },
                )
                logger.info("[INGEST] Duplicate provider event skipped")
                return result

        # ── Stage 3: Payload Hash Check ───────────────────────────
        payload_hash = event.get("payload_hash", "")
        if payload_hash and ext_res_id and not replay_of_failed:
            hash_exists = await repo.check_payload_hash_exists(
                tenant_id,
                provider,
                ext_res_id,
                payload_hash,
            )
            if hash_exists:
                result.decision = IngestDecision.SKIP
                result.reason = "Duplicate payload hash"
                result.status = "duplicate"
                await _finalize_event(event["id"], "duplicate", result)
                # Timeline: deduplicated (hash duplicate)
                await _timeline_append(
                    tenant_id=tenant_id,
                    correlation_id=correlation_id,
                    entity_type="reservation",
                    external_id=ext_res_id,
                    stage="deduplicated",
                    status="duplicate",
                    source="ingest_pipeline",
                    provider=provider,
                    metadata={
                        "duplicate_type": "payload_hash",
                        "payload_hash": payload_hash,
                        "decision": "skip",
                        "reason": result.reason,
                    },
                )
                logger.info("[INGEST] Duplicate payload hash skipped")
                return result

        # ── Stage 4: Stale Event Detection ────────────────────────
        incoming_version = event.get("provider_version", "")
        if ext_res_id:
            existing_lineage = await repo.get_lineage_by_external_id(
                tenant_id,
                provider,
                ext_res_id,
            )

        if existing_lineage and incoming_version and not replay_of_failed:
            existing_version = existing_lineage.get("provider_version", "")
            if existing_version and incoming_version <= existing_version:
                result.decision = IngestDecision.SKIP
                result.reason = "Stale provider version"
                result.status = "stale"
                await _finalize_event(event["id"], "stale", result)
                # Timeline: deduplicated (stale version)
                await _timeline_append(
                    tenant_id=tenant_id,
                    correlation_id=correlation_id,
                    entity_type="reservation",
                    external_id=ext_res_id,
                    stage="deduplicated",
                    status="stale",
                    source="ingest_pipeline",
                    provider=provider,
                    metadata={
                        "duplicate_type": "stale_version",
                        "decision": "skip",
                    },
                )
                logger.info("[INGEST] Stale provider event skipped")
                return result

        # ── Timeline: deduplicated (passed — unique event) ────────
        await _timeline_append(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            entity_type="reservation",
            external_id=ext_res_id,
            stage="deduplicated",
            status="success",
            source="ingest_pipeline",
            provider=provider,
            metadata={
                "is_duplicate": False,
                "has_existing_lineage": existing_lineage is not None,
                "decision": "proceed",
            },
        )

        # ── Stage 5: Normalize Payload ────────────────────────────
        raw_payload = event.get("raw_payload", {})
        canonical = normalize(provider, raw_payload)
        canonical_hash = compute_canonical_hash(canonical)

        # ── Timeline: normalized ──────────────────────────────────
        await _timeline_append(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            entity_type="reservation",
            external_id=ext_res_id,
            stage="normalized",
            status="success",
            source="ingest_pipeline",
            provider=provider,
            metadata=_safe_normalized_timeline_metadata(canonical, canonical_hash),
        )

        # ── Stage 6: Mapping Resolution (HARD FAIL) ──────────────
        room_code = canonical.get("room_type_code", "")
        rate_code = canonical.get("rate_plan_code", "")

        room_mapping = None
        rate_mapping = None

        if room_code:
            room_mapping = await repo.find_room_mapping_by_provider(
                tenant_id,
                property_id,
                provider,
                room_code,
            )
        if rate_code:
            rate_mapping = await repo.find_rate_plan_mapping_by_provider(
                tenant_id,
                property_id,
                provider,
                rate_code,
            )

        # ── Timeline: validated (mapping result) ──────────────────
        room_mapped = room_mapping is not None if room_code else True
        rate_mapped = rate_mapping is not None if rate_code else True
        mapping_status = "success" if (room_mapped and rate_mapped) else "warning"
        await _timeline_append(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            entity_type="reservation",
            external_id=ext_res_id,
            stage="validated",
            status=mapping_status,
            source="ingest_pipeline",
            provider=provider,
            metadata={
                "room_type_code": room_code,
                "room_mapped": room_mapped,
                "room_mapping_target": room_mapping.get("pms_room_type_id", "") if room_mapping else None,
                "rate_plan_code": rate_code,
                "rate_mapped": rate_mapped,
                "rate_mapping_target": rate_mapping.get("pms_rate_plan_id", "") if rate_mapping else None,
            },
        )

        # ── Stage 7: Decision Engine + Mutation Detection ────────
        decision, reason = decide(
            canonical,
            existing_lineage,
            room_mapping,
            rate_mapping,
            canonical_hash,
        )
        result.decision = decision
        result.reason = reason

        mutation_type = detect_mutation_type(canonical, existing_lineage)
        result.mutation_type = mutation_type

        # ── Stage 8: Concurrency Control ──────────────────────────
        if decision in (IngestDecision.UPDATE, IngestDecision.CANCEL) and existing_lineage:
            lock_owner_token = await _acquire_reservation_lock(existing_lineage)
            if not lock_owner_token:
                result.decision = IngestDecision.SKIP
                result.reason = "Reservation locked by another worker"
                result.status = "retry_later"
                await _finalize_event(event["id"], "pending", result)
                logger.warning("Reservation lock contention; processing deferred")
                return result
            lock_heartbeat_task = asyncio.create_task(
                _reservation_lock_heartbeat(
                    existing_lineage["id"],
                    lock_owner_token,
                    lock_lost,
                )
            )

        # ── Stage 9: Execute Decision ─────────────────────────────
        received_via = event.get("received_via", "webhook")

        if decision == IngestDecision.CREATE:
            lineage_id = await _create_lineage(
                tenant_id,
                property_id,
                provider,
                canonical,
                canonical_hash,
                received_via,
                mutation_type,
            )
            result.lineage_id = lineage_id
            result.status = "processed"

            # ── DATA-001: Trigger import bridge for new reservations ──
            await _trigger_import_bridge(
                tenant_id,
                property_id,
                provider,
                lineage_id,
                canonical,
                room_mapping,
                rate_mapping,
                event.get("connection_id", ""),
            )

        elif decision == IngestDecision.UPDATE:
            lineage_id = await _run_reservation_mutation(
                _update_lineage(
                    existing_lineage,
                    canonical,
                    canonical_hash,
                    received_via,
                    mutation_type,
                    lock_owner_token,
                ),
                lock_lost,
            )
            result.lineage_id = lineage_id
            result.status = "processed"

        elif decision == IngestDecision.CANCEL:
            if existing_lineage:
                lineage_id = await _run_reservation_mutation(
                    _cancel_lineage(existing_lineage, canonical, lock_owner_token),
                    lock_lost,
                )
                result.lineage_id = lineage_id
                # Also propagate cancellation to bookings and imported_reservations
                cancellation_durable = await _run_reservation_mutation(
                    _propagate_cancellation_to_booking(
                        tenant_id,
                        ext_res_id,
                    ),
                    lock_lost,
                )
                if not cancellation_durable:
                    raise RuntimeError("PMS_CANCELLATION_NOT_DURABLE")
            else:
                case_id = await _create_recon_case(
                    tenant_id,
                    property_id,
                    provider,
                    CaseType.CANCELLATION_WITHOUT_RESERVATION,
                    CaseSeverity.MEDIUM,
                    f"Cancellation received for unknown reservation: {ext_res_id}",
                    ext_res_id,
                )
                result.case_id = case_id
            result.status = "processed" if existing_lineage else "failed"

        elif decision == IngestDecision.SKIP:
            if provider == ConnectorProvider.HOTELRUNNER and existing_lineage:
                await _trigger_import_bridge(
                    tenant_id,
                    property_id,
                    provider,
                    existing_lineage["id"],
                    canonical,
                    room_mapping,
                    rate_mapping,
                    event.get("connection_id", ""),
                )
            result.status = "processed"

        elif decision == IngestDecision.PENDING_MAPPING:
            lineage_id = existing_lineage.get("id") if existing_lineage else None
            if not lineage_id:
                lineage_id = await _create_lineage(
                    tenant_id,
                    property_id,
                    provider,
                    canonical,
                    canonical_hash,
                    received_via,
                    mutation_type,
                )
            result.lineage_id = lineage_id

            hold_durable = await _persist_mapping_hold(
                tenant_id=tenant_id,
                property_id=property_id,
                provider=provider,
                lineage_id=lineage_id,
                canonical=canonical,
                room_mapping=room_mapping,
                rate_mapping=rate_mapping,
                connector_id=event.get("connection_id", ""),
            )
            case_id = await _create_recon_case(
                tenant_id,
                property_id,
                provider,
                CaseType.MISSING_MAPPING,
                CaseSeverity.HIGH,
                reason,
                ext_res_id,
                suggested_action="Create missing mapping in Data Model dashboard",
            )
            result.case_id = case_id
            result.status = "failed"
            if not hold_durable:
                raise RuntimeError("MAPPING_HOLD_OR_ALARM_NOT_DURABLE")

        elif decision == IngestDecision.MANUAL_REVIEW:
            case_id = await _create_recon_case(
                tenant_id,
                property_id,
                provider,
                CaseType.RESERVATION_CONFLICT,
                CaseSeverity.HIGH,
                reason,
                ext_res_id,
                suggested_action="Review reservation details manually",
            )
            result.case_id = case_id
            result.status = "failed"

        # Enrich the raw event with decision trace
        await _finalize_event(event["id"], result.status, result, canonical)

        logger.info(
            "[INGEST] decision=%s mutation=%s status=%s",
            decision,
            mutation_type,
            result.status,
        )
        return result

    except ReservationLockLostError:
        result.status = "retry_later"
        result.error = "RESERVATION_LOCK_LOST"
        result.reason = "Reservation lock ownership lost"
        await _finalize_event(event["id"], "pending", result)
        logger.error("Reservation lock ownership lost; processing deferred")
        return result
    except Exception as exc:
        result.status = "failed"
        result.error = type(exc).__name__
        result.reason = "Pipeline processing failed"
        await _finalize_event(event["id"], "failed", result)
        logger.error("[INGEST] Pipeline failed exception_class=%s", type(exc).__name__)
        return result
    finally:
        if lock_heartbeat_task:
            lock_heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await lock_heartbeat_task
        if existing_lineage and lock_owner_token:
            await _release_reservation_lock(existing_lineage["id"], lock_owner_token)


# ══════════════════════════════════════════════════════════════════════
# Event Finalization (trace enrichment on raw event)
# ══════════════════════════════════════════════════════════════════════


async def _finalize_event(
    event_id: str,
    status: str,
    result: PipelineResult,
    canonical: dict | None = None,
) -> None:
    """Update raw event with decision trace for full traceability."""
    update = {
        "processing_status": status,
        "processed_at": _now(),
        "decision_result": result.decision,
        "decision_reason": result.reason,
    }
    if canonical:
        update["normalization_result"] = canonical
    if result.error:
        update["processing_error"] = result.error

    await repo.update_raw_event_status(event_id, status, result.error)
    # Also store decision trace fields
    await db[COLL_RAW_CHANNEL_EVENTS].update_one(
        {"id": event_id},
        {
            "$set": {
                "decision_result": result.decision,
                "decision_reason": result.reason,
                "normalization_result": canonical,
            }
        },
    )


# ══════════════════════════════════════════════════════════════════════
# Concurrency Control (reservation-scoped optimistic locking)
# ══════════════════════════════════════════════════════════════════════


async def _acquire_reservation_lock(
    lineage: dict,
) -> str | None:
    """
    Acquire a reservation-scoped lock using optimistic concurrency.
    Scope: tenant_id + provider + external_reservation_id
    """
    now = datetime.now(UTC)
    expires = (now + timedelta(seconds=LOCK_TTL_SECONDS)).isoformat()
    owner_token = _uuid.uuid4().hex

    # Try to acquire: only succeed if no lock or lock expired
    result = await db[COLL_RESERVATION_LINEAGE].update_one(
        {
            "id": lineage["id"],
            "$or": [
                {"lock_holder": None},
                {"lock_holder": ""},
                {"lock_holder": {"$exists": False}},
                {"lock_expires_at": {"$lt": now.isoformat()}},
            ],
        },
        {
            "$set": {
                "lock_holder": "ingest-pipeline",
                "lock_owner_token": owner_token,
                "lock_acquired_at": now.isoformat(),
                "lock_heartbeat_at": now.isoformat(),
                "lock_expires_at": expires,
            }
        },
    )
    if result.modified_count > 0:
        lineage["lock_holder"] = "ingest-pipeline"
        lineage["lock_owner_token"] = owner_token
        return owner_token

    return None


async def _extend_reservation_lock(lineage_id: str, owner_token: str) -> bool:
    """Extend a live reservation lease only for its current owner."""
    now = datetime.now(UTC)
    expires = (now + timedelta(seconds=LOCK_TTL_SECONDS)).isoformat()
    result = await db[COLL_RESERVATION_LINEAGE].update_one(
        {
            "id": lineage_id,
            "lock_owner_token": owner_token,
            "lock_expires_at": {"$gte": now.isoformat()},
        },
        {
            "$set": {
                "lock_heartbeat_at": now.isoformat(),
                "lock_expires_at": expires,
            }
        },
    )
    return result.matched_count == 1


async def _reservation_lock_heartbeat(
    lineage_id: str,
    owner_token: str,
    lock_lost: asyncio.Event,
) -> None:
    while True:
        await asyncio.sleep(LOCK_HEARTBEAT_SECONDS)
        try:
            if not await _extend_reservation_lock(lineage_id, owner_token):
                lock_lost.set()
                logger.error("Reservation lock heartbeat lost ownership")
                return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            lock_lost.set()
            logger.error(
                "Reservation lock heartbeat failed: %s",
                type(exc).__name__,
            )
            return


async def _run_reservation_mutation(
    mutation: Awaitable[Any],
    lock_lost: asyncio.Event,
) -> Any:
    """Cancel a mutation and fail closed as soon as its lease is lost."""
    if lock_lost.is_set():
        if hasattr(mutation, "close"):
            mutation.close()
        raise ReservationLockLostError("RESERVATION_LOCK_LOST")

    mutation_task = asyncio.ensure_future(mutation)
    lost_task = asyncio.create_task(lock_lost.wait())
    try:
        await asyncio.wait(
            {mutation_task, lost_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if lock_lost.is_set():
            mutation_task.cancel()
            with suppress(asyncio.CancelledError):
                await mutation_task
            raise ReservationLockLostError("RESERVATION_LOCK_LOST")
        return await mutation_task
    finally:
        if not mutation_task.done():
            mutation_task.cancel()
            with suppress(asyncio.CancelledError):
                await mutation_task
        lost_task.cancel()
        with suppress(asyncio.CancelledError):
            await lost_task


async def _release_reservation_lock(lineage_id: str, owner_token: str) -> bool:
    """Release a reservation lease only if the caller still owns it."""

    result = await db[COLL_RESERVATION_LINEAGE].update_one(
        {"id": lineage_id, "lock_owner_token": owner_token},
        {
            "$set": {
                "lock_holder": None,
                "lock_owner_token": None,
                "lock_acquired_at": None,
                "lock_heartbeat_at": None,
                "lock_expires_at": None,
            }
        },
    )
    return result.matched_count == 1


# ══════════════════════════════════════════════════════════════════════
# Lineage Operations
# ══════════════════════════════════════════════════════════════════════


async def _create_lineage(
    tenant_id: str,
    property_id: str,
    provider: str,
    canonical: dict,
    payload_hash: str,
    received_via: str,
    mutation_type: str,
) -> str:
    now = _now()
    lineage = ReservationLineage(
        tenant_id=tenant_id,
        property_id=property_id,
        provider=ConnectorProvider(provider),
        external_reservation_id=canonical["external_reservation_id"],
        provider_event_id=canonical.get("source_payload_ref", ""),
        provider_version=canonical.get("provider_last_modified_at", ""),
        provider_last_modified=canonical.get("provider_last_modified_at"),
        payload_hash=payload_hash,
        version=1,
        decision_version=1,
        confidence_score=1.0,
        source_system=canonical.get("source_system", ""),
        ingested_via=received_via,
        external_write_protected=True,
        guest_name=canonical.get("guest_name", ""),
        guest_email=canonical.get("guest_email", ""),
        guest_phone=canonical.get("guest_phone", ""),
        arrival_date=canonical.get("check_in", ""),
        departure_date=canonical.get("check_out", ""),
        room_type_code=canonical.get("room_type_code", ""),
        provider_room_number=canonical.get("provider_room_number", ""),
        rate_plan_code=canonical.get("rate_plan_code", ""),
        adults=canonical.get("adults", 1),
        children=canonical.get("children", 0),
        total_amount=canonical.get("total_amount", 0.0),
        currency=canonical.get("currency", "TRY"),
        status="confirmed",
        mutation_type=mutation_type,
        last_decision="create",
        decision_reason="New reservation",
        first_seen_at=now,
        last_seen_at=now,
        last_synced_at=now,
    )
    doc = lineage.to_doc()
    return await repo.upsert_reservation_lineage(doc)


async def _update_lineage(
    existing: dict,
    canonical: dict,
    payload_hash: str,
    received_via: str,
    mutation_type: str,
    owner_token: str | None,
) -> str:
    if not owner_token:
        raise ReservationLockLostError("RESERVATION_LOCK_OWNER_MISSING")
    now = _now()
    # Track previous status for transition auditing
    existing["previous_status"] = existing.get("status")
    existing["provider_event_id"] = canonical.get("source_payload_ref", "")
    existing["provider_version"] = canonical.get("provider_last_modified_at", "")
    existing["provider_last_modified"] = canonical.get("provider_last_modified_at")
    existing["payload_hash"] = payload_hash
    existing["ingested_via"] = received_via
    existing["guest_name"] = canonical.get("guest_name", existing.get("guest_name", ""))
    existing["guest_email"] = canonical.get("guest_email", existing.get("guest_email", ""))
    existing["guest_phone"] = canonical.get("guest_phone", existing.get("guest_phone", ""))
    existing["arrival_date"] = canonical.get("check_in", existing.get("arrival_date", ""))
    existing["departure_date"] = canonical.get("check_out", existing.get("departure_date", ""))
    existing["room_type_code"] = canonical.get("room_type_code", existing.get("room_type_code", ""))
    existing["provider_room_number"] = canonical.get(
        "provider_room_number", existing.get("provider_room_number", "")
    )
    existing["rate_plan_code"] = canonical.get("rate_plan_code", existing.get("rate_plan_code", ""))
    existing["adults"] = canonical.get("adults", existing.get("adults", 1))
    existing["children"] = canonical.get("children", existing.get("children", 0))
    existing["total_amount"] = canonical.get("total_amount", existing.get("total_amount", 0.0))
    existing["currency"] = canonical.get("currency", existing.get("currency", "TRY"))
    existing["status"] = "modified"
    existing["mutation_type"] = mutation_type
    existing["last_decision"] = "update"
    existing["decision_reason"] = f"Updated from provider ({mutation_type})"
    existing["decision_version"] = existing.get("decision_version", 0) + 1
    existing["last_seen_at"] = now
    existing["last_synced_at"] = now
    lineage_id = await repo.update_reservation_lineage_with_lock(existing, owner_token)
    if not lineage_id:
        raise ReservationLockLostError("RESERVATION_LOCK_LOST")
    return lineage_id


async def _cancel_lineage(
    existing: dict,
    canonical: dict,
    owner_token: str | None,
) -> str:
    if not owner_token:
        raise ReservationLockLostError("RESERVATION_LOCK_OWNER_MISSING")
    now = _now()
    existing["previous_status"] = existing.get("status")
    existing["status"] = "cancelled"
    existing["cancellation_reason"] = canonical.get("source_system", "Provider cancellation")
    existing["mutation_type"] = MutationType.CANCELLATION
    existing["last_decision"] = "cancel"
    existing["decision_reason"] = "Cancellation from provider"
    existing["decision_version"] = existing.get("decision_version", 0) + 1
    existing["last_seen_at"] = now
    existing["last_synced_at"] = now
    lineage_id = await repo.update_reservation_lineage_with_lock(existing, owner_token)
    if not lineage_id:
        raise ReservationLockLostError("RESERVATION_LOCK_LOST")
    return lineage_id


async def _propagate_cancellation_to_booking(tenant_id: str, ext_res_id: str) -> bool:
    """Propagate cancellation from lineage to bookings and imported_reservations collections."""
    now = _now()

    # Iptal: varsa eslesmeyen-tutmanin sentinel kilitlerini once serbest birak
    # (asagidaki toplu update tutmayi cancelled isaretlemeden once cagrilmali,
    # aksi halde release tutmayi bulamaz). Tutma degilse no-op.
    try:
        from domains.channel_manager.providers.unmatched_hold import (
            release_unmatched_reservation_hold,
        )

        await release_unmatched_reservation_hold(
            tenant_id=tenant_id,
            external_id=ext_res_id,
            reason="ota_cancelled",
            delete_hold=False,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[CANCEL-PROPAGATE] unmatched hold release hatasi %s: %s", ext_res_id, e)

    # Get booking info before cancelling (for notification)
    booking = await db.bookings.find_one(
        {
            "tenant_id": tenant_id,
            "external_reservation_id": ext_res_id,
            "booking_source": {"$ne": "ota_unmatched_hold"},
        },
        {"_id": 0, "id": 1, "guest_name": 1, "check_in": 1, "check_out": 1, "status": 1},
    )

    # Update booking status to cancelled
    result = await db.bookings.update_one(
        {
            "tenant_id": tenant_id,
            "external_reservation_id": ext_res_id,
            "booking_source": {"$ne": "ota_unmatched_hold"},
        },
        {"$set": {"status": "cancelled", "updated_at": now, "cancelled_at": now}},
    )
    if result.modified_count > 0:
        logger.info("[CANCEL-PROPAGATE] Booking %s cancelled", ext_res_id)

        # Create cancellation notification (with dedup)
        if booking and booking.get("status") != "cancelled":
            guest_name = booking.get("guest_name", "Misafir")
            check_in = (booking.get("check_in", "") or "")[:10]
            check_out = (booking.get("check_out", "") or "")[:10]
            dedup_key = f"cancel_{ext_res_id}"
            existing_notif = await db.notifications.find_one(
                {
                    "tenant_id": tenant_id,
                    "external_reservation_id": ext_res_id,
                    "dedup_key": dedup_key,
                }
            )
            if not existing_notif:
                try:
                    await db.notifications.insert_one(
                        {
                            "id": str(_uuid.uuid4()),
                            "tenant_id": tenant_id,
                            "type": "reservation_cancelled",
                            "priority": "high",
                            "category": "reservation",
                            "title": f"Rezervasyon Iptali - {guest_name}",
                            "message": f"{guest_name} adli misafirin {check_in} - {check_out} tarihli rezervasyonu iptal edildi.",
                            "booking_id": booking.get("id", ""),
                            "external_reservation_id": ext_res_id,
                            "read": False,
                            "dedup_key": dedup_key,
                            "created_at": now,
                        }
                    )
                except Exception as e:
                    logger.warning("[CANCEL-PROPAGATE] Notification creation failed: %s", e)

    # Update imported_reservations
    await db.imported_reservations.update_one(
        {"tenant_id": tenant_id, "external_reservation_id": ext_res_id},
        {"$set": {"status": "cancelled", "updated_at": now}},
    )
    durable_booking = await db.bookings.find_one(
        {
            "tenant_id": tenant_id,
            "external_reservation_id": ext_res_id,
            "booking_source": {"$ne": "ota_unmatched_hold"},
            "status": "cancelled",
        },
        {"_id": 0, "id": 1},
    )
    if durable_booking:
        await publish_booking_change(
            tenant_id=tenant_id,
            booking_id=durable_booking["id"],
            event_type="cancel",
            status="cancelled",
            source="channel_manager_ingest",
            external_reservation_id=ext_res_id,
        )
    return durable_booking is not None


# ══════════════════════════════════════════════════════════════════════
# Reconciliation Case Creation
# ══════════════════════════════════════════════════════════════════════


async def _trigger_import_bridge(
    tenant_id: str,
    property_id: str,
    provider: str,
    lineage_id: str,
    canonical: dict,
    room_mapping,
    rate_mapping,
    connector_id: str,
) -> None:
    """
    DATA-001: After a new lineage record is created, classify and enqueue
    for PMS booking import.
    """
    from core.tenant_db import set_tenant_context

    set_tenant_context(tenant_id)

    from core.import_bridge_service import create_import_record
    from core.import_decision import check_already_imported, classify_for_import

    ext_res_id = canonical.get("external_reservation_id", "")

    # Check if already imported
    already = await check_already_imported(tenant_id, connector_id, ext_res_id)
    if already:
        logger.info(
            "Import bridge: already imported ext=%s, skipping",
            ext_res_id,
        )
        return

    # Build lineage-like dict for classification
    lineage_data = {
        "id": lineage_id,
        "tenant_id": tenant_id,
        "property_id": property_id,
        "provider": provider,
        "external_reservation_id": ext_res_id,
        "connection_id": connector_id,
        "payload_hash": canonical.get("payload_hash", ""),
        "guest_name": canonical.get("guest_name", ""),
        "guest_email": canonical.get("guest_email", ""),
        "guest_phone": canonical.get("guest_phone", ""),
        "arrival_date": canonical.get("check_in", ""),
        "departure_date": canonical.get("check_out", ""),
        "room_type_code": canonical.get("room_type_code", ""),
        "provider_room_number": canonical.get("provider_room_number", ""),
        "rate_plan_code": canonical.get("rate_plan_code", ""),
        "adults": canonical.get("adults", 1),
        "children": canonical.get("children", 0),
        "total_amount": canonical.get("total_amount", 0.0),
        "currency": canonical.get("currency", "TRY"),
        "status": canonical.get("status", "confirmed"),
        "source_system": canonical.get("source_system", ""),
    }

    import_status, review_reason = classify_for_import(
        lineage_data,
        room_mapping,
        rate_mapping,
    )

    await create_import_record(
        lineage_data,
        import_status=import_status,
        review_reason=review_reason,
        connector_id=connector_id,
    )
    logger.info(
        "Import bridge: enqueued ext=%s status=%s reason=%s",
        ext_res_id,
        import_status,
        review_reason,
    )


async def _persist_mapping_hold(
    *,
    tenant_id: str,
    property_id: str,
    provider: str,
    lineage_id: str,
    canonical: dict[str, Any],
    room_mapping,
    rate_mapping,
    connector_id: str,
) -> bool:
    """Persist the review record, inventory hold, and tenant alarm."""
    await _trigger_import_bridge(
        tenant_id,
        property_id,
        provider,
        lineage_id,
        canonical,
        room_mapping,
        rate_mapping,
        connector_id,
    )

    from domains.channel_manager.providers.unmatched_hold import (
        create_unmatched_reservation_hold,
    )

    hold = await create_unmatched_reservation_hold(
        provider=provider,
        tenant_id=tenant_id,
        external_id=canonical.get("external_reservation_id", ""),
        check_in=canonical.get("check_in", ""),
        check_out=canonical.get("check_out", ""),
        guest_name=canonical.get("guest_name", ""),
        room_type_code=canonical.get("room_type_code", ""),
        rate_plan_code=canonical.get("rate_plan_code", ""),
        total_amount=float(canonical.get("total_amount", 0) or 0),
        currency=canonical.get("currency", "TRY"),
        adults=canonical.get("adults", 1) or 1,
        children=canonical.get("children", 0) or 0,
        channel=canonical.get("source_system", "") or provider,
        property_id=property_id,
    )
    return bool(hold.get("booking_id") and hold.get("alarm_raised"))


async def _create_recon_case(
    tenant_id: str,
    property_id: str,
    provider: str,
    case_type: CaseType,
    severity: CaseSeverity,
    description: str,
    ext_res_id: str,
    suggested_action: str = "",
) -> str:
    case = ReconciliationCase(
        tenant_id=tenant_id,
        property_id=property_id,
        provider=ConnectorProvider(provider),
        case_type=case_type,
        severity=severity,
        status=CaseStatus.OPEN,
        external_reservation_id=ext_res_id,
        description=description,
        suggested_action=suggested_action,
    )
    return await repo.create_reconciliation_case(case.to_doc())
