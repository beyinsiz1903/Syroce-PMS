"""
Cockpit Snapshot Worker — Real-time Cockpit Data Stream
========================================================

Background task that periodically computes and broadcasts
cockpit metrics via WebSocket to connected cockpit clients.

Streams only critical metrics every 3 seconds:
  - verify_ratio
  - hard_fail_blocked
  - quarantine_count
  - drift_count
  - queue_size
  - is_production_ready
  - last_verify_timestamp
"""
import asyncio
import logging
from typing import Any

logger = logging.getLogger("cockpit.snapshot_worker")

_running = False
_task = None


async def _compute_snapshot(tenant_id: str) -> dict[str, Any]:
    """Compute a lightweight cockpit snapshot (critical metrics only)."""
    from core.database import db
    from domains.channel_manager.ari.hard_fail_gate import get_hard_fail_stats
    from domains.channel_manager.ari.push_loop_worker import get_push_worker
    from domains.channel_manager.quarantine_service import get_quarantine_overview

    worker = get_push_worker()
    metrics = worker.metrics.to_dict()
    hf_stats = await get_hard_fail_stats(tenant_id)
    quarantine = await get_quarantine_overview(tenant_id)

    drift_count = await db["channel_reconciliation_cases"].count_documents({
        "tenant_id": tenant_id,
        "status": {"$in": ["open", "investigating"]},
        "drift_type": {"$exists": True, "$ne": None},
    })

    is_ready = (
        hf_stats["hard_fail_change_sets"] == 0
        and hf_stats["open_hard_fail_incidents"] == 0
        and quarantine["total_quarantined"] == 0
    )

    return {
        "verify_ratio": metrics["verify_success_ratio"],
        "hard_fail_blocked": metrics["hard_fail_blocked"],
        "quarantine_count": quarantine["total_quarantined"],
        "drift_count": drift_count,
        "queue_size": metrics["queued_changes"],
        "is_production_ready": is_ready,
        "last_cycle_at": metrics["last_cycle_at"],
        "push_loop_status": worker.status,
        "emitted": metrics["emitted_payloads"],
        "verify_success_count": metrics["verify_success_count"],
        "verify_fail_count": metrics["verify_fail_count"],
    }


async def _snapshot_loop(tenant_id: str, interval: float = 3.0):
    """Main loop: compute snapshot and broadcast every N seconds."""
    global _running
    logger.info(f"Cockpit snapshot worker started (interval={interval}s)")

    while _running:
        try:
            from websocket_server import broadcast_cockpit_snapshot, connected_clients

            # Only compute if someone is listening
            if len(connected_clients.get("cockpit", set())) > 0:
                snapshot = await _compute_snapshot(tenant_id)
                await broadcast_cockpit_snapshot(snapshot, tenant_id)
        except Exception as e:
            logger.warning(f"Cockpit snapshot error: {e}")

        await asyncio.sleep(interval)

    logger.info("Cockpit snapshot worker stopped")


def start_cockpit_worker(tenant_id: str, interval: float = 3.0):
    """Start the cockpit snapshot background worker."""
    global _running, _task
    if _running:
        return

    _running = True
    _task = asyncio.ensure_future(_snapshot_loop(tenant_id, interval))
    logger.info("Cockpit snapshot worker scheduled")


def stop_cockpit_worker():
    """Stop the cockpit snapshot worker."""
    global _running, _task
    _running = False
    if _task:
        _task.cancel()
        _task = None
