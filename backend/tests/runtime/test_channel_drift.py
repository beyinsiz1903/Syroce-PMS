"""
Runtime Test — Channel Drift Detection
Tests the drift detector's ability to identify inventory discrepancies.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

import os
import pytest
if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
    pytest.skip("Motor event loop conflict in CI", allow_module_level=True)

from core.database import db


async def simulate_channel_drift(tenant_id: str) -> Dict[str, Any]:
    """
    Creates intentional drift between PMS and OTA snapshots,
    then verifies the drift detector catches it.
    """
    # Create fake OTA snapshot with intentional discrepancies
    test_snapshot = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "channel": "test_ota",
        "availability": {
            "standard": {"available": 999},   # Intentionally wrong
            "deluxe": {"available": 0},
        },
        "rates": {
            "standard": 50.0,   # Intentionally different from PMS
            "deluxe": 999.99,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "drift_test",
    }
    await db.ota_inventory_snapshots.insert_one(test_snapshot)

    # Run drift detection
    from domains.channel_manager.drift_detector import drift_detector
    scan_result = await drift_detector.scan_drift(tenant_id)

    # Cleanup
    await db.ota_inventory_snapshots.delete_many({"tenant_id": tenant_id, "source": "drift_test"})
    await db.drift_scan_results.delete_many({"tenant_id": tenant_id})

    drifts = scan_result.get("drifts", [])
    test_ota_drifts = [d for d in drifts if d.get("channel") == "test_ota"]

    results = {
        "total_drifts_detected": len(drifts),
        "test_ota_drifts": len(test_ota_drifts),
        "test_passed": len(test_ota_drifts) > 0,
        "drift_details": test_ota_drifts,
        "message": (
            f"PASS: Detected {len(test_ota_drifts)} drifts for test_ota"
            if test_ota_drifts
            else "FAIL: Drift detector did not catch the intentional discrepancy"
        ),
    }
    return results


async def run_test(tenant_id: str) -> Dict[str, Any]:
    return await simulate_channel_drift(tenant_id)
