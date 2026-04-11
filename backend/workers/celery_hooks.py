"""
Workers — Celery Hooks
Pre/post task hooks for audit logging, idempotency enforcement,
and failure routing to dead-letter archive.
"""
import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db
from workers.failure_archive import failure_archive
from workers.task_guard import task_guard

logger = logging.getLogger(__name__)


async def pre_task_hook(
    task_type: str,
    task_data: dict[str, Any],
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """
    Pre-task hook: idempotency check + audit log.
    Returns {"proceed": True/False, "reason": ...}
    """
    # Generate dedup key
    dedup_key = task_guard.generate_key(task_type, tenant_id or "", str(task_data))

    if await task_guard.is_duplicate(dedup_key):
        logger.info(f"Pre-task hook: duplicate detected for {task_type}")
        return {"proceed": False, "reason": "duplicate", "dedup_key": dedup_key}

    # Log task start
    await db.task_queue.insert_one({
        "id": dedup_key[:16],
        "task_type": task_type,
        "tenant_id": tenant_id,
        "status": "processing",
        "started_at": datetime.now(UTC).isoformat(),
        "task_data_summary": str(task_data)[:500],
    })

    return {"proceed": True, "dedup_key": dedup_key}


async def post_task_hook(
    dedup_key: str,
    task_type: str,
    success: bool,
    result: Any = None,
    error: str | None = None,
    attempts: int = 1,
    tenant_id: str | None = None,
) -> None:
    """Post-task hook: mark processed, archive failures."""
    now = datetime.now(UTC).isoformat()

    if success:
        await task_guard.mark_processed(dedup_key, result="success")
        await db.task_queue.update_one(
            {"id": dedup_key[:16]},
            {"$set": {"status": "completed", "completed_at": now}},
        )
    else:
        await task_guard.mark_processed(dedup_key, result=f"error: {error}")
        await db.task_queue.update_one(
            {"id": dedup_key[:16]},
            {"$set": {"status": "failed", "error": error, "updated_at": now}},
        )
        # Archive to dead letter if max retries exceeded
        if attempts >= 3:
            await failure_archive.archive(
                task_type=task_type,
                task_data={"dedup_key": dedup_key},
                error=error or "Unknown error",
                attempts=attempts,
                tenant_id=tenant_id,
            )
