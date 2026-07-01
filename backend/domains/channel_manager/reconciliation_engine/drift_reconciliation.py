"""
Channel Manager — Drift-Based Reconciliation Engine
Auto-reconciles inventory discrepancies between PMS and OTA channels.

Moved from the standalone reconciliation_engine.py to resolve the
file/package naming conflict (Python package shadows the .py file).
"""

import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db
from domains.channel_manager.drift_detector import drift_detector

logger = logging.getLogger(__name__)


class ReconciliationEngine:
    """Automatically resolves inventory drift between PMS and OTAs."""

    @staticmethod
    async def reconcile(tenant_id: str, *, auto_fix: bool = True) -> dict[str, Any]:
        """Run drift scan and optionally auto-reconcile discrepancies."""
        scan = await drift_detector.scan_drift(tenant_id)
        drifts = scan.get("drifts", [])

        if not drifts:
            return {
                "tenant_id": tenant_id,
                "status": "clean",
                "message": "No drift detected — PMS and OTAs are in sync",
                "reconciled_at": datetime.now(UTC).isoformat(),
            }

        actions = []
        for drift in drifts:
            if drift["type"] == "availability":
                action = {
                    "drift_type": "availability",
                    "channel": drift["channel"],
                    "room_type": drift["room_type"],
                    "action": "push_pms_availability",
                    "pms_value": drift["pms_value"],
                    "ota_value": drift["ota_value"],
                    "status": "pending",
                }
                if auto_fix:
                    action["status"] = "queued_for_sync"
                actions.append(action)

            elif drift["type"] == "rate":
                action = {
                    "drift_type": "rate",
                    "channel": drift["channel"],
                    "room_type": drift["room_type"],
                    "action": "push_pms_rate",
                    "pms_value": drift["pms_value"],
                    "ota_value": drift["ota_value"],
                    "status": "pending",
                }
                if auto_fix and drift.get("pct_diff", 0) <= 10:
                    action["status"] = "queued_for_sync"
                elif auto_fix:
                    action["status"] = "requires_manual_review"
                    action["reason"] = f"Rate difference > 10% ({drift.get('pct_diff')}%)"
                actions.append(action)

        result = {
            "tenant_id": tenant_id,
            "status": "reconciled" if auto_fix else "drift_detected",
            "total_drifts": len(drifts),
            "actions": actions,
            "auto_fixed": sum(1 for a in actions if a["status"] == "queued_for_sync"),
            "manual_review": sum(1 for a in actions if a["status"] == "requires_manual_review"),
            "reconciled_at": datetime.now(UTC).isoformat(),
        }

        await db.reconciliation_results.insert_one(
            {
                **result,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        logger.info(f"Reconciliation for tenant {tenant_id}: {result['auto_fixed']} auto-fixed, {result['manual_review']} need manual review")

        return result

    @staticmethod
    async def get_reconciliation_history(
        tenant_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return (
            await db.reconciliation_results.find(
                {"tenant_id": tenant_id},
                {"_id": 0},
            )
            .sort("timestamp", -1)
            .limit(limit)
            .to_list(limit)
        )


# Singleton
reconciliation_engine = ReconciliationEngine()
