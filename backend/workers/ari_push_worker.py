"""
ARI Push Worker.

Background task that periodically processes pending change sets.
Integrated with FailureTracker for wire-level failure visibility.
"""
import asyncio
import logging

from controlplane.failure_tracker import get_failure_tracker
from core.database import db
from core.transient_db_guard import TransientFailureTracker, is_transient_db_error
from domains.channel_manager.ari.outbound_service import push_pending_changes

logger = logging.getLogger(__name__)

PUSH_INTERVAL_SECONDS = 5  # Check every 5 seconds

# Per-tenant + outer-loop streak tracker so transient Atlas hiccups
# (AutoReconnect / NoPrimary / SSL timeout) do not flood Sentry on every
# 5-second tick. See `core.transient_db_guard`.
_transient_tracker = TransientFailureTracker("ari-push-worker")


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

            active_tids = {str(t["_id"]) for t in tenants if t.get("_id")}
            _transient_tracker.prune(active_tids)

            for t in tenants:
                tenant_id = t["_id"]
                tenant_key = str(tenant_id or "")
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
                    _transient_tracker.reset(tenant_key)
                except Exception as e:
                    _transient_tracker.log_exception(
                        logger, e, tenant_key,
                        context=f"tenant={tenant_id}",
                        non_transient_msg="%s error: %s",
                    )
                    # Only record non-transient failures to the wire tracker;
                    # a transient Atlas blip is not a real provider failure.
                    if not is_transient_db_error(e):
                        await tracker.record(
                            tenant_id=tenant_id or "",
                            provider="ari_push",
                            operation_type="ari_outbound_push",
                            error_code="ARI_PUSH_ERROR",
                            error_message=str(e)[:500],
                        )

        except Exception as e:
            _transient_tracker.log_exception(
                logger, e, TransientFailureTracker.OUTER_LOOP_KEY,
                context="loop tick",
                non_transient_msg="%s loop error: %s",
            )
        else:
            _transient_tracker.reset(TransientFailureTracker.OUTER_LOOP_KEY)

        await asyncio.sleep(PUSH_INTERVAL_SECONDS)


async def start_push_worker():
    """Start the push worker as a background task."""
    asyncio.create_task(ari_push_worker_loop())
    logger.info("ARI push worker task created")
