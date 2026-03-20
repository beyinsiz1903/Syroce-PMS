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
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from domains.channel_manager import unified_repository as repo
from domains.channel_manager.data_model import (
    ConnectorProvider, CaseType, CaseSeverity, CaseStatus,
    ReconciliationCase, ReservationLineage, ProcessingStatus,
    MutationType,
)
from .normalizer import normalize, compute_canonical_hash
from .decision_engine import decide, detect_mutation_type, IngestDecision

logger = logging.getLogger("ingest.pipeline")

# Concurrency: lock TTL for reservation-scoped processing
LOCK_TTL_SECONDS = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineResult:
    def __init__(self, event_id: str):
        self.event_id = event_id
        self.decision: str = ""
        self.reason: str = ""
        self.status: str = "pending"
        self.error: Optional[str] = None
        self.lineage_id: Optional[str] = None
        self.case_id: Optional[str] = None
        self.mutation_type: Optional[str] = None
        self.trace_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
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


async def process_event(event: Dict[str, Any]) -> PipelineResult:
    """
    Process a single raw_channel_event through the full pipeline.
    The event must already be persisted in raw_channel_events.
    """
    result = PipelineResult(event["id"])
    result.trace_id = event.get("trace_id") or event.get("correlation_id", "")
    tenant_id = event["tenant_id"]
    property_id = event["property_id"]
    provider = event["provider"]
    existing_lineage = None

    try:
        # ── Stage 2: Duplicate Detection ──────────────────────────
        provider_event_id = event.get("provider_event_id", "")
        if provider_event_id:
            is_dup = await repo.check_provider_event_exists(
                tenant_id, provider, provider_event_id,
            )
            if is_dup:
                result.decision = IngestDecision.SKIP
                result.reason = f"Duplicate provider_event_id: {provider_event_id}"
                result.status = "duplicate"
                await _finalize_event(event["id"], "duplicate", result)
                logger.info(f"[{event['id']}] DUPLICATE: {provider_event_id}")
                return result

        # ── Stage 3: Payload Hash Check ───────────────────────────
        ext_res_id = event.get("external_reservation_id", "")
        payload_hash = event.get("payload_hash", "")
        if payload_hash and ext_res_id:
            hash_exists = await repo.check_payload_hash_exists(
                tenant_id, provider, ext_res_id, payload_hash,
            )
            if hash_exists:
                result.decision = IngestDecision.SKIP
                result.reason = f"Same payload hash already processed: {payload_hash}"
                result.status = "duplicate"
                await _finalize_event(event["id"], "duplicate", result)
                logger.info(f"[{event['id']}] HASH_DUP: {payload_hash}")
                return result

        # ── Stage 4: Stale Event Detection ────────────────────────
        incoming_version = event.get("provider_version", "")
        if ext_res_id:
            existing_lineage = await repo.get_lineage_by_external_id(
                tenant_id, provider, ext_res_id,
            )

        if existing_lineage and incoming_version:
            existing_version = existing_lineage.get("provider_version", "")
            if existing_version and incoming_version <= existing_version:
                result.decision = IngestDecision.SKIP
                result.reason = f"Stale: {incoming_version} <= {existing_version}"
                result.status = "stale"
                await _finalize_event(event["id"], "stale", result)
                logger.info(f"[{event['id']}] STALE: {incoming_version}")
                return result

        # ── Stage 5: Normalize Payload ────────────────────────────
        raw_payload = event.get("raw_payload", {})
        canonical = normalize(provider, raw_payload)
        canonical_hash = compute_canonical_hash(canonical)

        # ── Stage 6: Mapping Resolution (HARD FAIL) ──────────────
        room_code = canonical.get("room_type_code", "")
        rate_code = canonical.get("rate_plan_code", "")

        room_mapping = None
        rate_mapping = None

        if room_code:
            room_mapping = await repo.find_room_mapping_by_provider(
                tenant_id, property_id, provider, room_code,
            )
        if rate_code:
            rate_mapping = await repo.find_rate_plan_mapping_by_provider(
                tenant_id, property_id, provider, rate_code,
            )

        # ── Stage 7: Decision Engine + Mutation Detection ────────
        decision, reason = decide(
            canonical, existing_lineage, room_mapping, rate_mapping, canonical_hash,
        )
        result.decision = decision
        result.reason = reason

        mutation_type = detect_mutation_type(canonical, existing_lineage)
        result.mutation_type = mutation_type

        # ── Stage 8: Concurrency Control ──────────────────────────
        if decision in (IngestDecision.UPDATE, IngestDecision.CANCEL) and existing_lineage:
            lock_ok = await _acquire_reservation_lock(
                existing_lineage, event["id"],
            )
            if not lock_ok:
                result.decision = IngestDecision.SKIP
                result.reason = "Reservation locked by another worker"
                result.status = "retry_later"
                await _finalize_event(event["id"], "pending", result)
                logger.warning(f"[{event['id']}] LOCK_CONTENTION for {ext_res_id}")
                return result

        # ── Stage 9: Execute Decision ─────────────────────────────
        received_via = event.get("received_via", "webhook")

        if decision == IngestDecision.CREATE:
            lineage_id = await _create_lineage(
                tenant_id, property_id, provider, canonical,
                canonical_hash, received_via, mutation_type,
            )
            result.lineage_id = lineage_id
            result.status = "processed"

        elif decision == IngestDecision.UPDATE:
            lineage_id = await _update_lineage(
                existing_lineage, canonical, canonical_hash,
                received_via, mutation_type,
            )
            result.lineage_id = lineage_id
            result.status = "processed"

        elif decision == IngestDecision.CANCEL:
            if existing_lineage:
                lineage_id = await _cancel_lineage(existing_lineage, canonical)
                result.lineage_id = lineage_id
            else:
                case_id = await _create_recon_case(
                    tenant_id, property_id, provider,
                    CaseType.CANCELLATION_WITHOUT_RESERVATION,
                    CaseSeverity.MEDIUM,
                    f"Cancellation received for unknown reservation: {ext_res_id}",
                    ext_res_id,
                )
                result.case_id = case_id
            result.status = "processed"

        elif decision == IngestDecision.SKIP:
            result.status = "processed"

        elif decision == IngestDecision.PENDING_MAPPING:
            case_id = await _create_recon_case(
                tenant_id, property_id, provider,
                CaseType.MISSING_MAPPING,
                CaseSeverity.HIGH,
                reason,
                ext_res_id,
                suggested_action="Create missing mapping in Data Model dashboard",
            )
            result.case_id = case_id
            result.status = "failed"

        elif decision == IngestDecision.MANUAL_REVIEW:
            case_id = await _create_recon_case(
                tenant_id, property_id, provider,
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
            f"[{event['id']}] {decision}: {reason} "
            f"mutation={mutation_type} trace={result.trace_id}"
        )
        return result

    except Exception as e:
        result.status = "failed"
        result.error = str(e)
        await _finalize_event(event["id"], "failed", result)
        logger.error(f"[{event['id']}] PIPELINE ERROR: {e}")
        return result
    finally:
        # Release lock if held
        if existing_lineage and existing_lineage.get("lock_holder") == event["id"]:
            await _release_reservation_lock(existing_lineage)


# ══════════════════════════════════════════════════════════════════════
# Event Finalization (trace enrichment on raw event)
# ══════════════════════════════════════════════════════════════════════

async def _finalize_event(
    event_id: str,
    status: str,
    result: PipelineResult,
    canonical: Optional[Dict] = None,
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
    from core.database import db
    from domains.channel_manager.data_model import COLL_RAW_CHANNEL_EVENTS
    await db[COLL_RAW_CHANNEL_EVENTS].update_one(
        {"id": event_id},
        {"$set": {
            "decision_result": result.decision,
            "decision_reason": result.reason,
            "normalization_result": canonical,
        }},
    )


# ══════════════════════════════════════════════════════════════════════
# Concurrency Control (reservation-scoped optimistic locking)
# ══════════════════════════════════════════════════════════════════════

async def _acquire_reservation_lock(
    lineage: Dict, worker_id: str,
) -> bool:
    """
    Acquire a reservation-scoped lock using optimistic concurrency.
    Scope: tenant_id + provider + external_reservation_id
    """
    from core.database import db
    from domains.channel_manager.data_model import COLL_RESERVATION_LINEAGE

    now = datetime.now(timezone.utc)
    expires = (now + timedelta(seconds=LOCK_TTL_SECONDS)).isoformat()

    # Try to acquire: only succeed if no lock or lock expired
    result = await db[COLL_RESERVATION_LINEAGE].update_one(
        {
            "id": lineage["id"],
            "$or": [
                {"lock_holder": None},
                {"lock_holder": ""},
                {"lock_expires_at": {"$lt": now.isoformat()}},
            ],
        },
        {"$set": {
            "lock_holder": worker_id,
            "lock_acquired_at": now.isoformat(),
            "lock_expires_at": expires,
        }},
    )
    if result.modified_count > 0:
        lineage["lock_holder"] = worker_id
        return True

    logger.warning(
        f"Lock contention: lineage={lineage['id']} "
        f"held_by={lineage.get('lock_holder')}"
    )
    return False


async def _release_reservation_lock(lineage: Dict) -> None:
    """Release reservation-scoped lock."""
    from core.database import db
    from domains.channel_manager.data_model import COLL_RESERVATION_LINEAGE

    await db[COLL_RESERVATION_LINEAGE].update_one(
        {"id": lineage["id"]},
        {"$set": {
            "lock_holder": None,
            "lock_acquired_at": None,
            "lock_expires_at": None,
        }},
    )


# ══════════════════════════════════════════════════════════════════════
# Lineage Operations
# ══════════════════════════════════════════════════════════════════════

async def _create_lineage(
    tenant_id: str, property_id: str, provider: str,
    canonical: Dict, payload_hash: str, received_via: str,
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
    existing: Dict, canonical: Dict, payload_hash: str,
    received_via: str, mutation_type: str,
) -> str:
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
    return await repo.upsert_reservation_lineage(existing)


async def _cancel_lineage(existing: Dict, canonical: Dict) -> str:
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
    return await repo.upsert_reservation_lineage(existing)


# ══════════════════════════════════════════════════════════════════════
# Reconciliation Case Creation
# ══════════════════════════════════════════════════════════════════════

async def _create_recon_case(
    tenant_id: str, property_id: str, provider: str,
    case_type: CaseType, severity: CaseSeverity,
    description: str, ext_res_id: str,
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
