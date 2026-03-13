"""
ARI Drift Worker.

Background task that periodically checks for inventory drift
between PMS and providers.
"""
import asyncio
import logging

from domains.channel_manager.ari.drift_worker import check_drift
from core.database import db

logger = logging.getLogger(__name__)

DRIFT_CHECK_INTERVAL = 120  # Every 2 minutes


async def ari_drift_worker_loop():
    """Main drift worker loop. Checks all active provider connections for drift."""
    logger.info("ARI drift worker started")
    while True:
        try:
            # In production, this would load active connections from DB
            # For now, it's a placeholder that gets triggered via API
            await asyncio.sleep(DRIFT_CHECK_INTERVAL)

        except Exception as e:
            logger.error(f"ARI drift worker error: {e}")
            await asyncio.sleep(DRIFT_CHECK_INTERVAL)


async def start_drift_worker():
    """Start the drift worker as a background task."""
    asyncio.create_task(ari_drift_worker_loop())
    logger.info("ARI drift worker task created")
