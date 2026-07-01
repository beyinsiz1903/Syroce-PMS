"""
Reconciliation Truth Table
==========================

Defines the gold source of truth for each data type
and the rules for drift resolution.

This is the system's constitutional document for data ownership.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .data_model import DriftResolution, DriftType


class GoldSource(str, Enum):
    """Where the final truth lives for each data type."""

    RAW_EVENTS = "raw_channel_events"  # immutable truth
    RESERVATION_LINEAGE = "reservation_lineage"  # derived truth (current state)
    ARI_SYNC_STATE = "ari_drift_state"  # latest applied truth
    MAPPING_TABLE = "room_mappings"  # config truth
    PROVIDER_SNAPSHOT = "provider_snapshot"  # external truth


@dataclass
class TruthRule:
    """Resolution policy for a specific drift type."""

    drift_type: DriftType
    resolution: DriftResolution
    gold_source: GoldSource
    description: str
    auto_heal_action: str = ""
    requires_evidence: bool = True


# ══════════════════════════════════════════════════════════════════════
# TRUTH TABLE — Resolution rules for every drift type
# ══════════════════════════════════════════════════════════════════════

TRUTH_TABLE: dict[str, TruthRule] = {
    # ── Reservation Drifts ────────────────────────────────────
    DriftType.MISSING_LOCALLY: TruthRule(
        drift_type=DriftType.MISSING_LOCALLY,
        resolution=DriftResolution.MANUAL_REVIEW,
        gold_source=GoldSource.PROVIDER_SNAPSHOT,
        description="Reservation exists on provider but not in PMS lineage",
        auto_heal_action="",
        requires_evidence=True,
    ),
    DriftType.MISSING_REMOTELY: TruthRule(
        drift_type=DriftType.MISSING_REMOTELY,
        resolution=DriftResolution.MANUAL_REVIEW,
        gold_source=GoldSource.RESERVATION_LINEAGE,
        description="Reservation exists in PMS lineage but not on provider",
        auto_heal_action="",
        requires_evidence=True,
    ),
    DriftType.STALE_LOCALLY: TruthRule(
        drift_type=DriftType.STALE_LOCALLY,
        resolution=DriftResolution.SAFE_AUTO_HEAL,
        gold_source=GoldSource.PROVIDER_SNAPSHOT,
        description="PMS lineage has older version than provider",
        auto_heal_action="Re-ingest latest provider data",
        requires_evidence=True,
    ),
    DriftType.STALE_REMOTELY: TruthRule(
        drift_type=DriftType.STALE_REMOTELY,
        resolution=DriftResolution.SAFE_AUTO_HEAL,
        gold_source=GoldSource.RESERVATION_LINEAGE,
        description="Provider has older version than PMS lineage",
        auto_heal_action="Re-push latest PMS data to provider",
        requires_evidence=True,
    ),
    DriftType.STATUS_MISMATCH: TruthRule(
        drift_type=DriftType.STATUS_MISMATCH,
        resolution=DriftResolution.MANUAL_REVIEW,
        gold_source=GoldSource.RESERVATION_LINEAGE,
        description="Reservation status differs between PMS and provider",
        auto_heal_action="",
        requires_evidence=True,
    ),
    DriftType.FINANCIAL_MISMATCH: TruthRule(
        drift_type=DriftType.FINANCIAL_MISMATCH,
        resolution=DriftResolution.MANUAL_REVIEW,
        gold_source=GoldSource.RESERVATION_LINEAGE,
        description="Financial amounts differ between PMS and provider",
        auto_heal_action="",
        requires_evidence=True,
    ),
    # ── ARI / Inventory Drifts ────────────────────────────────
    DriftType.PAYLOAD_MISMATCH: TruthRule(
        drift_type=DriftType.PAYLOAD_MISMATCH,
        resolution=DriftResolution.RISKY_AUTO_HEAL,
        gold_source=GoldSource.ARI_SYNC_STATE,
        description="ARI data on provider doesn't match last pushed values",
        auto_heal_action="Re-push current ARI state",
        requires_evidence=True,
    ),
    # ── Mapping Drifts ────────────────────────────────────────
    DriftType.MAPPING_MISMATCH: TruthRule(
        drift_type=DriftType.MAPPING_MISMATCH,
        resolution=DriftResolution.MANUAL_REVIEW,
        gold_source=GoldSource.MAPPING_TABLE,
        description="Mapping configuration inconsistency detected",
        auto_heal_action="",
        requires_evidence=True,
    ),
}


def get_resolution_for_drift(drift_type: str) -> TruthRule:
    """Look up the truth table for a given drift type."""
    rule = TRUTH_TABLE.get(drift_type)
    if not rule:
        return TruthRule(
            drift_type=DriftType.PAYLOAD_MISMATCH,
            resolution=DriftResolution.MANUAL_REVIEW,
            gold_source=GoldSource.RESERVATION_LINEAGE,
            description=f"Unknown drift type: {drift_type}",
        )
    return rule


def can_auto_heal(drift_type: str) -> bool:
    """Check if a drift type can be auto-healed."""
    rule = get_resolution_for_drift(drift_type)
    return rule.resolution in (
        DriftResolution.SAFE_AUTO_HEAL,
        DriftResolution.RISKY_AUTO_HEAL,
    )


def get_truth_table_summary() -> list[dict[str, Any]]:
    """Return the full truth table as a serializable list."""
    return [
        {
            "drift_type": rule.drift_type.value,
            "resolution": rule.resolution.value,
            "gold_source": rule.gold_source.value,
            "description": rule.description,
            "auto_heal_action": rule.auto_heal_action,
            "requires_evidence": rule.requires_evidence,
            "can_auto_heal": rule.resolution
            in (
                DriftResolution.SAFE_AUTO_HEAL,
                DriftResolution.RISKY_AUTO_HEAL,
            ),
        }
        for rule in TRUTH_TABLE.values()
    ]
