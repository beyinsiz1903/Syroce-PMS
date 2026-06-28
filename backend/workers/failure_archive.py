"""
Workers — Failure Archive (Dead Letter)
Archives permanently failed tasks for post-mortem analysis.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from core.tenant_db import LazyCollection

logger = logging.getLogger(__name__)


class FailureArchive:
    """Dead letter archive for tasks that failed all retries."""

    collection = LazyCollection("dead_letter_tasks")

    @classmethod
    async def archive(
        cls,
        task_type: str,
        task_data: dict[str, Any],
        error: str,
        attempts: int,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Archive a failed task for later analysis or manual replay."""
        import uuid

        entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "task_type": task_type,
            "task_data": task_data,
            "error": error,
            "attempts": attempts,
            "status": "archived",
            "archived_at": datetime.now(UTC).isoformat(),
        }
        await cls.collection.insert_one(entry)
        logger.warning(f"Task archived to dead letter: {task_type} ({entry['id'][:8]})")
        return entry

    @classmethod
    async def get_archived(
        cls,
        *,
        tenant_id: str | None = None,
        task_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if tenant_id:
            query["tenant_id"] = tenant_id
        if task_type:
            query["task_type"] = task_type
        return await cls.collection.find(query, {"_id": 0}).sort("archived_at", -1).limit(limit).to_list(limit)

    @classmethod
    async def replay(cls, archive_id: str) -> dict[str, Any]:
        """Mark an archived task for replay."""
        result = await cls.collection.update_one(
            {"id": archive_id, "status": "archived"},
            {"$set": {"status": "pending_replay", "replay_requested_at": datetime.now(UTC).isoformat()}},
        )
        if result.modified_count > 0:
            return {"status": "queued_for_replay", "id": archive_id}
        return {"status": "not_found_or_already_replayed", "id": archive_id}

    @classmethod
    async def get_stats(cls) -> dict[str, Any]:
        pipeline = [
            {
                "$group": {
                    "_id": {"task_type": "$task_type", "status": "$status"},
                    "count": {"$sum": 1},
                }
            },
        ]
        stats = {}
        async for doc in cls.collection.aggregate(pipeline):
            key = f"{doc['_id']['task_type']}:{doc['_id']['status']}"
            stats[key] = doc["count"]
        return {
            "total": await cls.collection.count_documents({}),
            "breakdown": stats,
        }


failure_archive = FailureArchive()
