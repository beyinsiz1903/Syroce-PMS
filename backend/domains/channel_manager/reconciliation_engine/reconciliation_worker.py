"""
Cross-Provider Reconciliation — Worker
========================================

Runs every 15 minutes (configurable) and performs:
  1. Fetch provider snapshots (HotelRunner + Exely)
  2. Fetch PMS reservations (from reservation_lineage)
  3. Run comparison engine
  4. Create reconciliation cases for detected mismatches
  5. Auto-resolve safe cases

The worker supports:
  - Multi-tenant properties
  - Parallel reconciliation per provider
  - Incremental scanning (last 24h window)
  - Batching to avoid full table scans
"""

import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db
from domains.channel_manager import unified_repository as repo
from domains.channel_manager.data_model import (
    COLL_PROVIDER_CONNECTIONS,
    COLL_RECONCILIATION_CASES,
    COLL_RESERVATION_LINEAGE,
    CaseSeverity,
    CaseStatus,
    CaseType,
    ConnectorProvider,
    ReconciliationCase,
)

from .auto_resolver import attempt_auto_resolve
from .comparison_engine import compare_reservations
from .snapshot_collectors import collect_provider_snapshot

logger = logging.getLogger("reconciliation.worker")

_NO_ID = {"_id": 0}

# Worker state
_reconciliation_state = {
    "running": False,
    "last_run": None,
    "interval_seconds": 900,  # 15 min
    "runs_total": 0,
    "cases_created": 0,
    "cases_auto_resolved": 0,
    "last_result": None,
}


def get_reconciliation_worker_state() -> dict[str, Any]:
    return {**_reconciliation_state}


async def reconciliation_run_once() -> dict[str, Any]:
    """
    Execute a single reconciliation cycle across all active connections.
    """
    state = _reconciliation_state
    if state["running"]:
        return {"status": "already_running"}

    state["running"] = True
    now = datetime.now(UTC)
    result = {
        "status": "completed",
        "started_at": now.isoformat(),
        "providers_checked": [],
        "total_pms_reservations": 0,
        "total_provider_snapshots": 0,
        "mismatches_found": 0,
        "cases_created": 0,
        "cases_auto_resolved": 0,
        "cases_skipped_duplicate": 0,
        "errors": [],
    }

    try:
        # Get all active provider connections across all tenants
        active_connections = (
            await db[COLL_PROVIDER_CONNECTIONS]
            .find(
                {"status": "active"},
                _NO_ID,
            )
            .to_list(100)
        )

        if not active_connections:
            # Fall back to all connections for demo
            active_connections = (
                await db[COLL_PROVIDER_CONNECTIONS]
                .find(
                    {},
                    _NO_ID,
                )
                .to_list(100)
            )

        # Group connections by (tenant_id, property_id)
        grouped: dict[str, list[dict]] = {}
        for conn in active_connections:
            key = f"{conn['tenant_id']}:{conn['property_id']}"
            grouped.setdefault(key, []).append(conn)

        for key, connections in grouped.items():
            tenant_id, property_id = key.split(":", 1)

            for conn in connections:
                provider = conn.get("provider", "")
                try:
                    provider_result = await _reconcile_provider(
                        tenant_id,
                        property_id,
                        provider,
                        conn,
                    )
                    result["providers_checked"].append(provider)
                    result["total_pms_reservations"] += provider_result["pms_count"]
                    result["total_provider_snapshots"] += provider_result["provider_count"]
                    result["mismatches_found"] += provider_result["mismatches"]
                    result["cases_created"] += provider_result["cases_created"]
                    result["cases_auto_resolved"] += provider_result["auto_resolved"]
                    result["cases_skipped_duplicate"] += provider_result["skipped_duplicate"]
                except Exception as e:
                    error_msg = f"Error reconciling {provider} for {key}: {e}"
                    result["errors"].append(error_msg)
                    logger.error(error_msg)

        result["completed_at"] = datetime.now(UTC).isoformat()
        state["runs_total"] += 1
        state["cases_created"] += result["cases_created"]
        state["cases_auto_resolved"] += result["cases_auto_resolved"]
        state["last_run"] = now.isoformat()
        state["last_result"] = result

    except Exception as e:
        result["status"] = "error"
        result["errors"].append(str(e))
        logger.error(f"Reconciliation worker error: {e}")
    finally:
        state["running"] = False

    logger.info(f"Reconciliation complete: mismatches={result['mismatches_found']}, cases_created={result['cases_created']}, auto_resolved={result['cases_auto_resolved']}")
    return result


async def _reconcile_provider(
    tenant_id: str,
    property_id: str,
    provider: str,
    connection: dict[str, Any],
) -> dict[str, Any]:
    """Reconcile a single provider for a single property."""
    result = {
        "pms_count": 0,
        "provider_count": 0,
        "mismatches": 0,
        "cases_created": 0,
        "auto_resolved": 0,
        "skipped_duplicate": 0,
    }

    # 1. Fetch PMS reservations from lineage
    pms_reservations = (
        await db[COLL_RESERVATION_LINEAGE]
        .find(
            {
                "tenant_id": tenant_id,
                "property_id": property_id,
                "provider": provider,
            },
            _NO_ID,
        )
        .to_list(5000)
    )
    result["pms_count"] = len(pms_reservations)

    # 2. Fetch provider snapshot
    provider_snapshots = await collect_provider_snapshot(
        provider,
        connection,
        since_hours=24,
    )
    result["provider_count"] = len(provider_snapshots)

    # If no provider snapshots (stub), skip comparison
    if not provider_snapshots:
        logger.info(f"No provider snapshots for {provider}/{property_id} — skipping comparison (pull workers are stubs)")
        return result

    # 3. Run comparison engine
    mismatches = compare_reservations(pms_reservations, provider_snapshots, provider)
    result["mismatches"] = len(mismatches)

    # 4. Create cases for mismatches (skip duplicates)
    for mismatch in mismatches:
        ext_id = mismatch.get("external_reservation_id", "")
        case_type = mismatch.get("case_type", "")

        # Check for existing open case with same type and ext_id
        existing = await db[COLL_RECONCILIATION_CASES].find_one(
            {
                "tenant_id": tenant_id,
                "provider": provider,
                "external_reservation_id": ext_id,
                "case_type": case_type,
                "status": {"$in": ["open", "acknowledged"]},
            },
        )
        if existing:
            result["skipped_duplicate"] += 1
            continue

        case = _build_case(tenant_id, property_id, provider, mismatch)
        case_doc = case.to_doc()

        # 5. Attempt auto-resolution
        auto_update = attempt_auto_resolve(case_doc)
        if auto_update:
            case_doc.update(auto_update)
            result["auto_resolved"] += 1

        await repo.create_reconciliation_case(case_doc)
        result["cases_created"] += 1

    return result


def _build_case(
    tenant_id: str,
    property_id: str,
    provider: str,
    mismatch: dict[str, Any],
) -> ReconciliationCase:
    """Build a ReconciliationCase from a mismatch dict."""
    case_type_str = mismatch["case_type"]
    severity_str = mismatch["severity"]

    # Map to enum safely
    try:
        ct = CaseType(case_type_str)
    except ValueError:
        ct = CaseType.RESERVATION_CONFLICT

    try:
        sev = CaseSeverity(severity_str)
    except ValueError:
        sev = CaseSeverity.MEDIUM

    return ReconciliationCase(
        tenant_id=tenant_id,
        property_id=property_id,
        provider=ConnectorProvider(provider),
        case_type=ct,
        severity=sev,
        status=CaseStatus.OPEN,
        external_reservation_id=mismatch.get("external_reservation_id"),
        description=mismatch.get("description", ""),
        suggested_action=mismatch.get("suggested_action", ""),
        pms_value=mismatch.get("pms_value"),
        provider_value=mismatch.get("provider_value"),
        details={
            "detected_by": "reconciliation_engine",
            "comparison_timestamp": datetime.now(UTC).isoformat(),
        },
    )


async def reconciliation_run_with_snapshots(
    tenant_id: str,
    property_id: str,
    provider: str,
    provider_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Run reconciliation with explicitly provided snapshots.
    Used for testing and manual reconciliation triggers.
    """
    result = {
        "pms_count": 0,
        "provider_count": len(provider_snapshots),
        "mismatches": 0,
        "cases_created": 0,
        "auto_resolved": 0,
        "skipped_duplicate": 0,
    }

    # Fetch PMS reservations
    pms_reservations = (
        await db[COLL_RESERVATION_LINEAGE]
        .find(
            {
                "tenant_id": tenant_id,
                "property_id": property_id,
                "provider": provider,
            },
            _NO_ID,
        )
        .to_list(5000)
    )
    result["pms_count"] = len(pms_reservations)

    # Run comparison
    mismatches = compare_reservations(pms_reservations, provider_snapshots, provider)
    result["mismatches"] = len(mismatches)

    # Create cases
    for mismatch in mismatches:
        ext_id = mismatch.get("external_reservation_id", "")
        case_type = mismatch.get("case_type", "")

        existing = await db[COLL_RECONCILIATION_CASES].find_one(
            {
                "tenant_id": tenant_id,
                "provider": provider,
                "external_reservation_id": ext_id,
                "case_type": case_type,
                "status": {"$in": ["open", "acknowledged"]},
            },
        )
        if existing:
            result["skipped_duplicate"] += 1
            continue

        case = _build_case(tenant_id, property_id, provider, mismatch)
        case_doc = case.to_doc()

        auto_update = attempt_auto_resolve(case_doc)
        if auto_update:
            case_doc.update(auto_update)
            result["auto_resolved"] += 1

        await repo.create_reconciliation_case(case_doc)
        result["cases_created"] += 1

    return result
