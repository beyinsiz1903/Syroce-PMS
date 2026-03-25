"""
Reservation Ingest — Decision Engine (Production-Grade)
=======================================================

Determines what action to take for each incoming reservation event.

Decisions:
  create          — New reservation, no existing lineage
  update          — Existing lineage, newer version
  cancel          — Provider status = cancelled (always wins)
  skip            — Duplicate or same payload hash
  pending_mapping — Room or rate plan mapping missing (HARD FAIL)
  manual_review   — Anomaly detected

Mutation Detection:
  Compares incoming vs existing to classify the mutation type:
  new_booking, date_change, room_type_change, rate_change,
  guest_detail_change, partial_modification, cancellation, reinstatement
"""
import logging
from typing import Any

from domains.channel_manager.data_model import (
    MutationType,
    ReservationState,
    is_valid_transition,
)
from domains.channel_manager.mapping_validator import (
    validate_rate_plan_mapping,
    validate_room_mapping,
)

logger = logging.getLogger("ingest.decision_engine")


class IngestDecision:
    CREATE = "create"
    UPDATE = "update"
    CANCEL = "cancel"
    SKIP = "skip"
    PENDING_MAPPING = "pending_mapping"
    MANUAL_REVIEW = "manual_review"


def decide(
    canonical: dict[str, Any],
    existing_lineage: dict[str, Any] | None,
    room_mapping: dict[str, Any] | None,
    rate_mapping: dict[str, Any] | None,
    payload_hash: str,
) -> tuple[str, str]:
    """
    Returns (decision, reason) tuple.

    Args:
        canonical: Normalized reservation data
        existing_lineage: Current lineage record (or None)
        room_mapping: Resolved room mapping (or None)
        rate_mapping: Resolved rate plan mapping (or None)
        payload_hash: Hash of the canonical data
    """
    status = canonical.get("status", "")
    ext_id = canonical.get("external_reservation_id", "")

    # ── Cancellation always wins ──────────────────────────────────
    if status == "cancelled":
        if existing_lineage:
            return IngestDecision.CANCEL, f"Cancellation for {ext_id}"
        else:
            return IngestDecision.CANCEL, f"Cancellation without existing reservation {ext_id}"

    # ── Mapping check (HARD FAIL — no silent fallback) ────────────
    room_code = canonical.get("room_type_code", "")
    rate_code = canonical.get("rate_plan_code", "")

    room_error = validate_room_mapping(room_mapping, room_code)
    if room_error:
        return (
            IngestDecision.PENDING_MAPPING,
            f"[{room_error.failure_type.value}] {room_error.reason} | Action: {room_error.operator_action}",
        )

    rate_error = validate_rate_plan_mapping(rate_mapping, rate_code)
    if rate_error:
        return (
            IngestDecision.PENDING_MAPPING,
            f"[{rate_error.failure_type.value}] {rate_error.reason} | Action: {rate_error.operator_action}",
        )

    # ── No existing lineage → CREATE ──────────────────────────────
    if not existing_lineage:
        return IngestDecision.CREATE, f"New reservation {ext_id}"

    # ── Same payload hash → SKIP ──────────────────────────────────
    if existing_lineage.get("payload_hash") == payload_hash:
        return IngestDecision.SKIP, f"Same payload hash for {ext_id}"

    # ── Stale version check ───────────────────────────────────────
    incoming_version = canonical.get("provider_last_modified_at", "")
    existing_version = existing_lineage.get("provider_last_modified", "")
    if incoming_version and existing_version and incoming_version <= existing_version:
        return IngestDecision.SKIP, f"Stale version: incoming={incoming_version} <= existing={existing_version}"

    # ── Anomaly checks → MANUAL_REVIEW ────────────────────────────
    anomaly = _check_anomalies(canonical, existing_lineage)
    if anomaly:
        return IngestDecision.MANUAL_REVIEW, anomaly

    # ── State transition validation ────────────────────────────────
    existing_status = existing_lineage.get("status", "confirmed")
    incoming_status = _map_to_canonical_state(status)
    if not is_valid_transition(existing_status, incoming_status):
        return (
            IngestDecision.MANUAL_REVIEW,
            f"Invalid state transition: {existing_status} → {incoming_status} for {ext_id}",
        )

    # ── Normal update ─────────────────────────────────────────────
    return IngestDecision.UPDATE, f"Updated reservation {ext_id}"


def detect_mutation_type(
    canonical: dict[str, Any],
    existing_lineage: dict[str, Any] | None,
) -> str:
    """
    Compare incoming canonical data with existing lineage to determine
    what kind of mutation occurred.
    """
    if not existing_lineage:
        return MutationType.NEW_BOOKING

    status = canonical.get("status", "")
    if status == "cancelled":
        return MutationType.CANCELLATION

    existing_status = existing_lineage.get("status", "")
    if existing_status == "cancelled" and status != "cancelled":
        return MutationType.REINSTATEMENT

    changes = []

    # Date change
    if (canonical.get("check_in") != existing_lineage.get("arrival_date") or
            canonical.get("check_out") != existing_lineage.get("departure_date")):
        changes.append("date")

    # Room type change
    if canonical.get("room_type_code") != existing_lineage.get("room_type_code"):
        changes.append("room_type")

    # Rate change
    if canonical.get("rate_plan_code") != existing_lineage.get("rate_plan_code"):
        changes.append("rate")

    # Amount change
    if abs(canonical.get("total_amount", 0) - existing_lineage.get("total_amount", 0)) > 0.01:
        changes.append("amount")

    # Guest detail change
    if (canonical.get("guest_name") != existing_lineage.get("guest_name") or
            canonical.get("guest_email") != existing_lineage.get("guest_email") or
            canonical.get("guest_phone") != existing_lineage.get("guest_phone")):
        changes.append("guest")

    # Classify
    if not changes:
        return MutationType.PARTIAL_MODIFICATION

    if "date" in changes and len(changes) == 1:
        return MutationType.DATE_CHANGE
    if "room_type" in changes and len(changes) <= 2:
        return MutationType.ROOM_TYPE_CHANGE
    if "rate" in changes and len(changes) <= 2:
        return MutationType.RATE_CHANGE
    if changes == ["guest"]:
        return MutationType.GUEST_DETAIL_CHANGE

    return MutationType.PARTIAL_MODIFICATION


def _map_to_canonical_state(provider_status: str) -> str:
    """Map a normalized status string to canonical ReservationState."""
    mapping = {
        "confirmed": ReservationState.CONFIRMED,
        "modified": ReservationState.MODIFIED,
        "cancelled": ReservationState.CANCELLED,
        "pending": ReservationState.PENDING,
        "checked_in": ReservationState.CHECKED_IN,
        "checked_out": ReservationState.CHECKED_OUT,
        "no_show": ReservationState.NO_SHOW,
    }
    return mapping.get(provider_status, ReservationState.CONFIRMED)


def _check_anomalies(
    canonical: dict[str, Any],
    existing: dict[str, Any],
) -> str | None:
    """Check for anomalies that require manual review."""
    # Currency mismatch
    if (existing.get("currency") and canonical.get("currency") and
            existing["currency"] != canonical["currency"]):
        return f"Currency mismatch: existing={existing['currency']}, incoming={canonical['currency']}"

    # Amount anomaly (>100% change)
    existing_amount = existing.get("total_amount", 0)
    incoming_amount = canonical.get("total_amount", 0)
    if existing_amount > 0 and incoming_amount > 0:
        ratio = incoming_amount / existing_amount
        if ratio > 2.0 or ratio < 0.5:
            return f"Amount anomaly: {existing_amount} -> {incoming_amount} (ratio={ratio:.2f})"

    return None
