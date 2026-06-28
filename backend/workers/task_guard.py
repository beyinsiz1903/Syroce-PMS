"""
Workers — Task Guard
Provides idempotency and deduplication for background tasks.
"""

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

logger = logging.getLogger(__name__)


class TaskGuard:
    """Ensures task idempotency and prevents duplicate execution."""

    DEDUP_TTL_SECONDS = 3600  # 1 hour dedup window

    @classmethod
    async def is_duplicate(cls, task_key: str) -> bool:
        """Check if a task with this key was already processed recently."""
        threshold = (datetime.now(UTC) - timedelta(seconds=cls.DEDUP_TTL_SECONDS)).isoformat()
        existing = await db.task_dedup_log.find_one(
            {
                "task_key": task_key,
                "processed_at": {"$gt": threshold},
            }
        )
        return existing is not None

    @classmethod
    async def mark_processed(cls, task_key: str, result: str | None = None) -> None:
        """Mark a task key as processed for deduplication."""
        await db.task_dedup_log.update_one(
            {"task_key": task_key},
            {
                "$set": {
                    "task_key": task_key,
                    "processed_at": datetime.now(UTC).isoformat(),
                    "result": result,
                }
            },
            upsert=True,
        )

    @staticmethod
    def generate_key(*parts) -> str:
        """Generate a deterministic dedup key from task parameters."""
        raw = ":".join(str(p) for p in parts)
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    async def execute_idempotent(cls, task_key: str, coroutine_fn, *args, **kwargs) -> dict[str, Any]:
        """Execute a task only if not already processed (idempotent guard)."""
        if await cls.is_duplicate(task_key):
            logger.info(f"Task dedup: {task_key[:16]}... already processed, skipping")
            return {"status": "skipped", "reason": "duplicate"}

        try:
            result = await coroutine_fn(*args, **kwargs)
            await cls.mark_processed(task_key, result="success")
            return {"status": "executed", "result": result}
        except Exception as e:
            await cls.mark_processed(task_key, result=f"error: {e}")
            raise

    @classmethod
    async def cleanup_expired(cls) -> int:
        """Remove expired dedup entries."""
        threshold = (datetime.now(UTC) - timedelta(seconds=cls.DEDUP_TTL_SECONDS * 2)).isoformat()
        result = await db.task_dedup_log.delete_many({"processed_at": {"$lt": threshold}})
        return result.deleted_count


task_guard = TaskGuard()
