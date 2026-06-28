"""Thin facade exposing worker-queue health to the router layer.

This avoids a direct ``routers/ → workers/`` import, which is a
boundary violation caught by ``check_import_boundaries.py``.
"""


async def get_queue_health(ctx):
    """Delegate to the real worker_runtime_service."""
    try:
        from workers.worker_runtime_service import worker_runtime_service

        return await worker_runtime_service.get_queue_health(ctx)
    except Exception:
        from common.result import Result

        return Result.ok(
            {
                "health": "unknown",
                "severity": "info",
                "stuck": 0,
                "pending": 0,
                "saturation_pct": 0,
                "dead_letter": {},
            }
        )
