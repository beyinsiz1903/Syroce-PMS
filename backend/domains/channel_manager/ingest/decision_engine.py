"""
Reservation Ingest — Decision Engine
=====================================

Determines what action to take for each incoming reservation event.

Decisions:
  create          — New reservation, no existing lineage
  update          — Existing lineage, newer version
  cancel          — Provider status = cancelled (always wins)
  skip            — Duplicate or same payload hash
  pending_mapping — Room or rate plan mapping missing
  manual_review   — Anomaly detected
"""
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("ingest.decision_engine")


class IngestDecision:
    CREATE = "create"
    UPDATE = "update"
    CANCEL = "cancel"
    SKIP = "skip"
    PENDING_MAPPING = "pending_mapping"
    MANUAL_REVIEW = "manual_review"


def decide(
    canonical: Dict[str, Any],
    existing_lineage: Optional[Dict[str, Any]],
    room_mapping: Optional[Dict[str, Any]],
    rate_mapping: Optional[Dict[str, Any]],
    payload_hash: str,
) -> Tuple[str, str]:
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

    # ── Mapping check ─────────────────────────────────────────────
    if not room_mapping:
        return (
            IngestDecision.PENDING_MAPPING,
            f"Room mapping missing for code: {canonical.get('room_type_code', '')}"
        )
    if not rate_mapping:
        return (
            IngestDecision.PENDING_MAPPING,
            f"Rate plan mapping missing for code: {canonical.get('rate_plan_code', '')}"
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

    # ── Normal update ─────────────────────────────────────────────
    return IngestDecision.UPDATE, f"Updated reservation {ext_id}"


def _check_anomalies(
    canonical: Dict[str, Any],
    existing: Dict[str, Any],
) -> Optional[str]:
    """Check for anomalies that require manual review."""
    # Currency mismatch
    if (existing.get("currency") and canonical.get("currency") and
            existing["currency"] != canonical["currency"]):
        return f"Currency mismatch: existing={existing['currency']}, incoming={canonical['currency']}"

    # Amount anomaly (>50% change)
    existing_amount = existing.get("total_amount", 0)
    incoming_amount = canonical.get("total_amount", 0)
    if existing_amount > 0 and incoming_amount > 0:
        ratio = incoming_amount / existing_amount
        if ratio > 2.0 or ratio < 0.5:
            return f"Amount anomaly: {existing_amount} → {incoming_amount} (ratio={ratio:.2f})"

    # Date conflict (check-in changed to past while check-out in future)
    existing_checkin = existing.get("arrival_date", "")
    incoming_checkin = canonical.get("check_in", "")
    if existing_checkin and incoming_checkin and existing_checkin != incoming_checkin:
        existing_checkout = existing.get("departure_date", "")
        incoming_checkout = canonical.get("check_out", "")
        if existing_checkout and incoming_checkout and existing_checkout != incoming_checkout:
            # Both dates changed — flag for review if substantial
            pass  # Not flagging date changes as anomaly by default

    return None
