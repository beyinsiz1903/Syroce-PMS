"""
Channel Manager — Drift Detector
Compares PMS inventory with OTA-reported availability to detect discrepancies.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db

logger = logging.getLogger(__name__)


class DriftDetector:
    """Detects inventory/rate drift between PMS and OTA channels."""

    @staticmethod
    async def scan_drift(tenant_id: str) -> dict[str, Any]:
        """Full drift scan: compare PMS state with last-known OTA state."""
        now = datetime.now(UTC)

        # Get PMS availability
        rooms = await db.rooms.find(
            {"tenant_id": tenant_id},
            {"_id": 0, "id": 1, "room_type": 1, "status": 1, "base_price": 1},
        ).to_list(1000)

        pms_availability = {}
        pms_rates = {}
        for room in rooms:
            rt = room.get("room_type", "unknown")
            if rt not in pms_availability:
                pms_availability[rt] = {"total": 0, "available": 0}
            pms_availability[rt]["total"] += 1
            if room.get("status") == "available":
                pms_availability[rt]["available"] += 1
            pms_rates[rt] = room.get("base_price", 0)

        # Get OTA snapshots (last reported state)
        ota_snapshots = (
            await db.ota_inventory_snapshots.find(
                {"tenant_id": tenant_id},
                {"_id": 0},
            )
            .sort("timestamp", -1)
            .to_list(50)
        )

        # Group by channel
        channel_snapshots: dict[str, dict] = {}
        for snap in ota_snapshots:
            ch = snap.get("channel")
            if ch and ch not in channel_snapshots:
                channel_snapshots[ch] = snap

        # Detect drifts
        drifts = []
        for channel, snapshot in channel_snapshots.items():
            ota_avail = snapshot.get("availability", {})
            ota_rates = snapshot.get("rates", {})
            snapshot_time = snapshot.get("timestamp", "")

            for rt, pms_data in pms_availability.items():
                ota_data = ota_avail.get(rt, {})
                ota_count = ota_data.get("available", -1)
                pms_count = pms_data["available"]

                if ota_count >= 0 and ota_count != pms_count:
                    drifts.append(
                        {
                            "type": "availability",
                            "channel": channel,
                            "room_type": rt,
                            "pms_value": pms_count,
                            "ota_value": ota_count,
                            "delta": pms_count - ota_count,
                            "snapshot_time": snapshot_time,
                            "severity": "critical" if abs(pms_count - ota_count) > 5 else "warning",
                        }
                    )

                ota_rate = ota_rates.get(rt, -1)
                pms_rate = pms_rates.get(rt, 0)
                if ota_rate >= 0 and abs(ota_rate - pms_rate) > 0.01:
                    pct_diff = abs(ota_rate - pms_rate) / max(pms_rate, 1) * 100
                    drifts.append(
                        {
                            "type": "rate",
                            "channel": channel,
                            "room_type": rt,
                            "pms_value": pms_rate,
                            "ota_value": ota_rate,
                            "delta": round(pms_rate - ota_rate, 2),
                            "pct_diff": round(pct_diff, 1),
                            "snapshot_time": snapshot_time,
                            "severity": "critical" if pct_diff > 10 else "warning",
                        }
                    )

        scan_result = {
            "tenant_id": tenant_id,
            "scanned_at": now.isoformat(),
            "pms_room_types": list(pms_availability.keys()),
            "channels_checked": list(channel_snapshots.keys()),
            "drifts_found": len(drifts),
            "critical_drifts": sum(1 for d in drifts if d["severity"] == "critical"),
            "drifts": drifts,
        }

        # Store scan result
        await db.drift_scan_results.insert_one(
            {
                **scan_result,
                "timestamp": now.isoformat(),
            }
        )

        if drifts:
            logger.warning(f"Drift detected for tenant {tenant_id}: {len(drifts)} drifts ({scan_result['critical_drifts']} critical)")

        return scan_result

    @staticmethod
    async def get_drift_history(
        tenant_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent drift scan results."""
        return (
            await db.drift_scan_results.find(
                {"tenant_id": tenant_id},
                {"_id": 0},
            )
            .sort("timestamp", -1)
            .limit(limit)
            .to_list(limit)
        )


# Convenience instance
drift_detector = DriftDetector()
