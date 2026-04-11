"""
Cross-Provider Reconciliation — Comparison Engine
===================================================

Compares PMS reservations (from reservation_lineage) against provider
snapshots (HotelRunner / Exely) and detects mismatches.

Mismatch types:
  - missing_reservation   (provider has it, PMS doesn't)
  - ghost_reservation     (PMS has it, provider doesn't)
  - amount_mismatch       (total_amount differs)
  - date_conflict         (check_in / check_out differs)
  - status_conflict       (status differs — critical)
  - duplicate_reservation (multiple with same external_reservation_id)
"""
import logging
from typing import Any

logger = logging.getLogger("reconciliation.comparison_engine")


class MismatchType:
    MISSING_RESERVATION = "missing_reservation"
    GHOST_RESERVATION = "ghost_reservation"
    AMOUNT_MISMATCH = "amount_mismatch"
    DATE_CONFLICT = "date_conflict"
    STATUS_CONFLICT = "status_conflict"
    DUPLICATE_RESERVATION = "duplicate_reservation"


SEVERITY_MAP = {
    MismatchType.MISSING_RESERVATION: "high",
    MismatchType.GHOST_RESERVATION: "medium",
    MismatchType.AMOUNT_MISMATCH: "medium",
    MismatchType.DATE_CONFLICT: "high",
    MismatchType.STATUS_CONFLICT: "critical",
    MismatchType.DUPLICATE_RESERVATION: "medium",
}

SUGGESTED_ACTIONS = {
    MismatchType.MISSING_RESERVATION: "Import reservation from provider into PMS",
    MismatchType.GHOST_RESERVATION: "Verify with provider — reservation may have been cancelled externally",
    MismatchType.AMOUNT_MISMATCH: "Review pricing and contact provider if discrepancy persists",
    MismatchType.DATE_CONFLICT: "Compare check-in/check-out dates and update accordingly",
    MismatchType.STATUS_CONFLICT: "Critical: resolve status difference immediately to avoid overbooking",
    MismatchType.DUPLICATE_RESERVATION: "Merge or remove duplicate reservation entries",
}


def compare_reservations(
    pms_reservations: list[dict[str, Any]],
    provider_snapshots: list[dict[str, Any]],
    provider: str,
) -> list[dict[str, Any]]:
    """
    Compare PMS reservations against provider snapshots for a single provider.
    Returns a list of mismatch dicts ready for case creation.
    """
    mismatches: list[dict[str, Any]] = []

    # Index PMS by external_reservation_id
    pms_by_ext_id: dict[str, dict] = {}
    for res in pms_reservations:
        ext_id = res.get("external_reservation_id", "")
        if ext_id:
            if ext_id in pms_by_ext_id:
                # Duplicate in PMS
                mismatches.append(_build_mismatch(
                    MismatchType.DUPLICATE_RESERVATION,
                    provider, ext_id,
                    pms_value=pms_by_ext_id[ext_id],
                    provider_value=res,
                    description=f"Duplicate PMS reservation for {ext_id}",
                ))
            pms_by_ext_id[ext_id] = res

    # Index provider snapshots by external_reservation_id
    provider_by_ext_id: dict[str, dict] = {}
    for snap in provider_snapshots:
        ext_id = snap.get("external_reservation_id", "")
        if ext_id:
            if ext_id in provider_by_ext_id:
                mismatches.append(_build_mismatch(
                    MismatchType.DUPLICATE_RESERVATION,
                    provider, ext_id,
                    pms_value=None,
                    provider_value=snap,
                    description=f"Duplicate provider reservation for {ext_id}",
                ))
            provider_by_ext_id[ext_id] = snap

    # 1. Missing reservations: provider has, PMS doesn't
    for ext_id, snap in provider_by_ext_id.items():
        if ext_id not in pms_by_ext_id:
            mismatches.append(_build_mismatch(
                MismatchType.MISSING_RESERVATION,
                provider, ext_id,
                pms_value=None,
                provider_value=snap,
                description=f"Provider reservation {ext_id} not found in PMS",
            ))

    # 2. Ghost reservations: PMS has, provider doesn't
    for ext_id, pms_res in pms_by_ext_id.items():
        if ext_id not in provider_by_ext_id:
            mismatches.append(_build_mismatch(
                MismatchType.GHOST_RESERVATION,
                provider, ext_id,
                pms_value=pms_res,
                provider_value=None,
                description=f"PMS reservation {ext_id} not found in provider",
            ))

    # 3. Field-level comparison for matched reservations
    for ext_id in set(pms_by_ext_id.keys()) & set(provider_by_ext_id.keys()):
        pms_res = pms_by_ext_id[ext_id]
        snap = provider_by_ext_id[ext_id]
        mismatches.extend(_compare_fields(provider, ext_id, pms_res, snap))

    logger.info(
        f"Comparison [{provider}]: PMS={len(pms_by_ext_id)}, "
        f"Provider={len(provider_by_ext_id)}, Mismatches={len(mismatches)}"
    )
    return mismatches


def _compare_fields(
    provider: str, ext_id: str,
    pms: dict[str, Any], snap: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare individual fields between matched PMS and provider reservation."""
    mismatches = []

    # Amount mismatch
    pms_amount = float(pms.get("total_amount", 0))
    snap_amount = float(snap.get("total_amount", 0))
    if pms_amount > 0 and snap_amount > 0 and abs(pms_amount - snap_amount) > 0.01:
        mismatches.append(_build_mismatch(
            MismatchType.AMOUNT_MISMATCH,
            provider, ext_id,
            pms_value={"total_amount": pms_amount, "currency": pms.get("currency", "")},
            provider_value={"total_amount": snap_amount, "currency": snap.get("currency", "")},
            description=f"Amount mismatch: PMS={pms_amount} vs Provider={snap_amount}",
        ))

    # Date conflict
    pms_ci = pms.get("arrival_date") or pms.get("check_in", "")
    pms_co = pms.get("departure_date") or pms.get("check_out", "")
    snap_ci = snap.get("check_in", "")
    snap_co = snap.get("check_out", "")
    if (pms_ci and snap_ci and pms_ci != snap_ci) or (pms_co and snap_co and pms_co != snap_co):
        mismatches.append(_build_mismatch(
            MismatchType.DATE_CONFLICT,
            provider, ext_id,
            pms_value={"check_in": pms_ci, "check_out": pms_co},
            provider_value={"check_in": snap_ci, "check_out": snap_co},
            description=f"Date conflict: PMS={pms_ci}/{pms_co} vs Provider={snap_ci}/{snap_co}",
        ))

    # Status conflict
    pms_status = _normalize_status(pms.get("status", ""))
    snap_status = _normalize_status(snap.get("status", ""))
    if pms_status and snap_status and pms_status != snap_status:
        mismatches.append(_build_mismatch(
            MismatchType.STATUS_CONFLICT,
            provider, ext_id,
            pms_value={"status": pms.get("status", "")},
            provider_value={"status": snap.get("status", "")},
            description=f"Status conflict: PMS={pms.get('status','')} vs Provider={snap.get('status','')}",
        ))

    return mismatches


def _normalize_status(status: str) -> str:
    """Normalize reservation status for comparison."""
    s = status.lower().strip()
    mapping = {
        "confirmed": "confirmed",
        "modified": "confirmed",
        "imported": "confirmed",
        "pending": "confirmed",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "no_show": "cancelled",
    }
    return mapping.get(s, s)


def _build_mismatch(
    mismatch_type: str,
    provider: str,
    external_reservation_id: str,
    pms_value: Any = None,
    provider_value: Any = None,
    description: str = "",
) -> dict[str, Any]:
    return {
        "case_type": mismatch_type,
        "severity": SEVERITY_MAP.get(mismatch_type, "medium"),
        "provider": provider,
        "external_reservation_id": external_reservation_id,
        "pms_value": pms_value,
        "provider_value": provider_value,
        "description": description,
        "suggested_action": SUGGESTED_ACTIONS.get(mismatch_type, ""),
    }
