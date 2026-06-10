"""
GM dashboard — daily metric snapshots.

The GM dashboard compares today vs. yesterday vs. last week. Most metrics
(occupancy, revenue, arrivals, departures, complaints) can be reconstructed
for a past date from bookings/payments/feedback, but the *pending maintenance
task* backlog only exists as a point-in-time count — there is no per-date
history to reconstruct. To make that comparison real, the night audit records
a tiny daily snapshot of the high/urgent pending-task backlog per tenant, and
the dashboard reads the past values from those snapshots instead of repeating
today's current backlog.
"""
import logging
import uuid
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

PENDING_TASK_SNAPSHOTS = "pending_task_snapshots"


async def _count_high_urgent_pending(db, tenant_id: str) -> int:
    """Current high/urgent pending maintenance backlog for a tenant."""
    return await db.maintenance_tasks.count_documents({
        "tenant_id": tenant_id,
        "status": "pending",
        "priority": {"$in": ["high", "urgent"]},
    })


async def record_pending_task_snapshot(
    tenant_id: str, db=None, snapshot_date: str | None = None,
) -> int | None:
    """Record (idempotently) the current high/urgent pending-task backlog for a
    tenant, keyed by UTC calendar date.

    Best-effort: any failure is logged and swallowed so it can never break the
    caller (e.g. the night audit). Returns the recorded count, or None on
    failure.
    """
    if db is None:
        from core.database import db as _db
        db = _db
    sd = snapshot_date or datetime.now(UTC).date().isoformat()
    try:
        count = await _count_high_urgent_pending(db, tenant_id)
        await db[PENDING_TASK_SNAPSHOTS].update_one(
            {"tenant_id": tenant_id, "snapshot_date": sd},
            {
                "$set": {
                    "pending_tasks": count,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "snapshot_date": sd,
                    "created_at": datetime.now(UTC).isoformat(),
                },
            },
            upsert=True,
        )
        return count
    except Exception as exc:
        logger.warning(
            "pending-task snapshot failed for tenant=%s date=%s: %s",
            tenant_id, sd, exc,
        )
        return None


async def get_pending_task_snapshot(
    tenant_id: str, snapshot_date: str, db=None,
) -> int | None:
    """Return the recorded high/urgent pending-task backlog for a tenant on a
    given UTC date, or None if no snapshot exists for that date.
    """
    if db is None:
        from core.database import db as _db
        db = _db
    try:
        doc = await db[PENDING_TASK_SNAPSHOTS].find_one(
            {"tenant_id": tenant_id, "snapshot_date": snapshot_date},
            {"_id": 0, "pending_tasks": 1},
        )
        if doc is None:
            return None
        return int(doc.get("pending_tasks", 0))
    except Exception as exc:
        logger.warning(
            "pending-task snapshot read failed for tenant=%s date=%s: %s",
            tenant_id, snapshot_date, exc,
        )
        return None
