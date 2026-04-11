"""
ARI Push Worker.

Background task that periodically processes pending change sets.
Integrated with FailureTracker for wire-level failure visibility.
"""
import asyncio
import logging

from controlplane.failure_tracker import get_failure_tracker
from core.database import db
from domains.channel_manager.ari.outbound_service import push_pending_changes

logger = logging.getLogger(__name__)

PUSH_INTERVAL_SECONDS = 5  # Check every 5 seconds


async def ari_push_worker_loop():
    """Main push worker loop. Processes pending change sets for all tenants."""
    logger.info("ARI push worker started")
    tracker = get_failure_tracker()

    while True:
        try:
            # Get distinct tenants with pending work
            pipeline = [
                {"$match": {"status": {"$in": ["pending", "failed_retryable"]}}},
                {"$group": {"_id": "$tenant_id"}},
            ]
            tenants = await db["ari_change_sets"].aggregate(pipeline).to_list(100)

            for t in tenants:
                tenant_id = t["_id"]
                try:
                    result = await push_pending_changes(tenant_id, limit=20)
                    if result["pushed"] > 0 or result["failed"] > 0:
                        logger.info(f"ARI push worker [{tenant_id}]: {result}")

                    # Record failures to tracker for wire visibility
                    if result.get("failed", 0) > 0:
                        await tracker.record(
                            tenant_id=tenant_id or "",
                            provider="ari_push",
                            operation_type="ari_outbound_push",
                            error_code="ARI_PUSH_PARTIAL_FAIL",
                            error_message=f"ARI push: {result['failed']} of {result['pushed'] + result['failed']} change sets failed",
                            context={"result": result},
                        )
                except Exception as e:
                    logger.error(f"ARI push worker error [{tenant_id}]: {e}")
                    await tracker.record(
                        tenant_id=tenant_id or "",
                        provider="ari_push",
                        operation_type="ari_outbound_push",
                        error_code="ARI_PUSH_ERROR",
                        error_message=str(e)[:500],
                    )

        except Exception as e:
            logger.error(f"ARI push worker loop error: {e}")

        await asyncio.sleep(PUSH_INTERVAL_SECONDS)


async def start_push_worker():
    """Start the push worker as a background task."""
    asyncio.create_task(ari_push_worker_loop())
    logger.info("ARI push worker task created")
