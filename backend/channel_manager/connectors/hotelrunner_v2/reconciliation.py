"""
HotelRunner v2 — Reconciliation Job
=====================================

Daily reconciliation: PMS state vs HotelRunner state.
Detects drift, logs mismatches, creates ops cases.
Optional auto-fix for simple drifts.
"""
import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db

from .feature_flags import get_flags
from .mapper import reservation_to_canonical
from .metrics import record_metric

logger = logging.getLogger("hrv2.reconciliation")

COLL_RECON_RUNS = "connector_reconciliation_runs"
COLL_RECON_DRIFTS = "connector_reconciliation_drifts"
_NO_ID = {"_id": 0}


async def run_reconciliation(
    tenant_id: str,
    property_id: str,
    *,
    since_hours: int = 24,
    auto_fix: bool = False,
) -> dict[str, Any]:
    """
    Run reconciliation between PMS lineage and HotelRunner API state.

    Steps:
      1. Pull recent reservations from HotelRunner
      2. Load corresponding PMS lineage records
      3. Compare field-by-field
      4. Record mismatches as drift entries
      5. Optionally auto-fix simple drifts

    Returns summary of mismatches found.
    """
    import time
    import uuid as _uuid

    from .service import HotelRunnerV2Service

    start = time.time()
    run_id = str(_uuid.uuid4())[:12]
    now = datetime.now(UTC).isoformat()

    flags = await get_flags(tenant_id)
    if not flags.get("reconciliation_enabled", True):
        return {"success": False, "error": "Reconciliation disabled for tenant", "run_id": run_id}

    auto_fix = auto_fix and flags.get("auto_fix_enabled", False)

    try:
        svc = await HotelRunnerV2Service.create(tenant_id, property_id)
    except Exception as e:
        logger.error("[HRv2 recon] credential error: %s", e)
        return {"success": False, "error": str(e), "run_id": run_id}

    # 1. Pull from HotelRunner
    from datetime import timedelta
    since_date = (datetime.now(UTC) - timedelta(hours=since_hours)).strftime("%Y-%m-%d")

    pull_result = await svc.pull_reservations(undelivered=False, from_date=since_date)
    if not pull_result.get("success"):
        return {"success": False, "error": "Pull failed", "run_id": run_id}

    hr_reservations = pull_result.get("canonical_reservations", [])

    # 2. Load PMS lineage
    from domains.channel_manager.data_model import COLL_RESERVATION_LINEAGE
    pms_records = await db[COLL_RESERVATION_LINEAGE].find(
        {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "provider": "hotelrunner",
            "last_seen_at": {"$gte": since_date},
        },
        _NO_ID,
    ).to_list(1000)

    # 3. Compare
    from domains.channel_manager.reconciliation_engine.comparison_engine import compare_reservations
    mismatches = compare_reservations(pms_records, hr_reservations, "hotelrunner")

    # 4. Store drift entries
    drift_ids = []
    for mm in mismatches:
        drift_id = str(_uuid.uuid4())[:12]
        drift_doc = {
            "id": drift_id,
            "run_id": run_id,
            "tenant_id": tenant_id,
            "property_id": property_id,
            "provider": "hotelrunner_v2",
            "case_type": mm.get("case_type", "unknown"),
            "severity": mm.get("severity", "medium"),
            "external_reservation_id": mm.get("external_reservation_id", ""),
            "description": mm.get("description", ""),
            "pms_value": mm.get("pms_value"),
            "provider_value": mm.get("provider_value"),
            "suggested_action": mm.get("suggested_action", ""),
            "auto_fixed": False,
            "created_at": now,
        }
        await db[COLL_RECON_DRIFTS].insert_one(drift_doc)
        drift_ids.append(drift_id)

    # 5. Auto-fix (if enabled and simple drift)
    auto_fixed_count = 0
    if auto_fix:
        for mm in mismatches:
            if mm.get("case_type") == "missing_reservation":
                # Auto-import missing reservation
                provider_val = mm.get("provider_value")
                if provider_val and isinstance(provider_val, dict):
                    try:
                        # Re-ingest the missing reservation
                        raw = provider_val.get("raw_provider_data", provider_val)
                        await svc.ingest_reservation(raw, received_via="reconciliation_auto_fix")
                        auto_fixed_count += 1
                        await db[COLL_RECON_DRIFTS].update_one(
                            {"external_reservation_id": mm.get("external_reservation_id", ""), "run_id": run_id},
                            {"$set": {"auto_fixed": True}},
                        )
                    except Exception as e:
                        logger.warning("[HRv2 recon] auto-fix failed: %s", e)

    # 6. Store run summary
    duration_ms = int((time.time() - start) * 1000)
    run_doc = {
        "id": run_id,
        "tenant_id": tenant_id,
        "property_id": property_id,
        "provider": "hotelrunner_v2",
        "hr_count": len(hr_reservations),
        "pms_count": len(pms_records),
        "mismatch_count": len(mismatches),
        "auto_fixed_count": auto_fixed_count,
        "drift_ids": drift_ids,
        "duration_ms": duration_ms,
        "since_hours": since_hours,
        "created_at": now,
    }
    await db[COLL_RECON_RUNS].insert_one(run_doc)

    await record_metric(
        tenant_id, "reconciliation",
        success=True, duration_ms=duration_ms,
        metadata={"mismatches": len(mismatches), "auto_fixed": auto_fixed_count},
    )

    logger.info("[HRv2 recon] run=%s HR=%d PMS=%d mismatches=%d auto_fixed=%d (%dms)",
                run_id, len(hr_reservations), len(pms_records), len(mismatches),
                auto_fixed_count, duration_ms)

    return {
        "success": True,
        "run_id": run_id,
        "hr_count": len(hr_reservations),
        "pms_count": len(pms_records),
        "mismatch_count": len(mismatches),
        "auto_fixed_count": auto_fixed_count,
        "mismatches": [
            {
                "type": m.get("case_type"),
                "severity": m.get("severity"),
                "reservation": m.get("external_reservation_id"),
                "description": m.get("description"),
            }
            for m in mismatches
        ],
        "duration_ms": duration_ms,
    }


async def get_recent_drifts(tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Get recent drift entries for ops dashboard."""
    return await db[COLL_RECON_DRIFTS].find(
        {"tenant_id": tenant_id, "provider": "hotelrunner_v2"},
        _NO_ID,
    ).sort("created_at", -1).to_list(limit)


async def get_reconciliation_history(tenant_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Get recent reconciliation runs."""
    return await db[COLL_RECON_RUNS].find(
        {"tenant_id": tenant_id, "provider": "hotelrunner_v2"},
        _NO_ID,
    ).sort("created_at", -1).to_list(limit)
