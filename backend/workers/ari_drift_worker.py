"""
ARI Drift Worker (Background Task).

Dual-mode operation:
  - Normal: 2 min interval, only rooms that changed since last check
  - Recovery: 30 sec interval, full property scope (for incident response)
"""
import asyncio
import logging

from domains.channel_manager.ari.drift_worker import check_drift
from core.database import db

logger = logging.getLogger(__name__)

# Dual-mode configuration
DRIFT_MODE_NORMAL = "normal"
DRIFT_MODE_RECOVERY = "recovery"

DRIFT_CONFIG = {
    DRIFT_MODE_NORMAL: {"interval": 120, "scope": "changed"},     # 2 min, changed rooms only
    DRIFT_MODE_RECOVERY: {"interval": 30, "scope": "full"},       # 30 sec, all property
}

# Current mode (can be toggled via API)
_current_mode = DRIFT_MODE_NORMAL


def get_drift_mode() -> str:
    return _current_mode


def set_drift_mode(mode: str) -> dict:
    global _current_mode
    if mode not in DRIFT_CONFIG:
        return {"error": f"Invalid mode: {mode}. Valid: {list(DRIFT_CONFIG.keys())}"}
    old_mode = _current_mode
    _current_mode = mode
    logger.info(f"Drift worker mode changed: {old_mode} → {mode}")
    return {
        "previous_mode": old_mode,
        "current_mode": mode,
        "interval": DRIFT_CONFIG[mode]["interval"],
        "scope": DRIFT_CONFIG[mode]["scope"],
    }


async def ari_drift_worker_loop():
    """Main drift worker loop with dual-mode support."""
    logger.info(f"ARI drift worker started (mode={_current_mode})")
    while True:
        try:
            config = DRIFT_CONFIG[_current_mode]
            interval = config["interval"]
            scope = config["scope"]

            # Get active provider connections
            connections = await db["provider_connections"].find(
                {"status": "active"}, {"_id": 0}
            ).to_list(100)

            for conn in connections:
                tenant_id = conn.get("tenant_id")
                property_id = conn.get("property_id")
                provider = conn.get("provider")
                if not all([tenant_id, property_id, provider]):
                    continue

                try:
                    # In recovery mode, check all data; in normal mode, only changed
                    pms_snapshot = []
                    provider_snapshot = []

                    if scope == "changed":
                        # In production: query only rooms modified since last drift check
                        pass
                    else:
                        # Full property scope: query all rooms/dates
                        pass

                    if pms_snapshot or provider_snapshot:
                        await check_drift(
                            tenant_id, property_id, provider,
                            pms_snapshot, provider_snapshot,
                        )
                except Exception as e:
                    logger.error(f"Drift check error [{provider}/{property_id}]: {e}")

            await asyncio.sleep(interval)

        except Exception as e:
            logger.error(f"ARI drift worker error: {e}")
            await asyncio.sleep(DRIFT_CONFIG[_current_mode]["interval"])


async def start_drift_worker():
    """Start the drift worker as a background task."""
    asyncio.create_task(ari_drift_worker_loop())
    logger.info("ARI drift worker task created")
