"""
GM dashboard — pending-task daily snapshot tests.

Covers the snapshot helper that lets the GM dashboard show a real day-over-day
delta for the high/urgent pending-maintenance backlog:
  A. record_pending_task_snapshot writes the current high/urgent backlog
  B. it is idempotent per (tenant, date) — re-run updates, never duplicates
  C. get_pending_task_snapshot returns the recorded value, None when missing
  D. only high/urgent pending tasks are counted (status/priority filtering)
"""
import os
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from domains.pms.dashboard_router.snapshots import (
    PENDING_TASK_SNAPSHOTS,
    get_pending_task_snapshot,
    record_pending_task_snapshot,
)

TENANT = f"test_pts_{uuid.uuid4().hex[:8]}"
DATE = "2026-06-09"


async def _get_db():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017/hotel_pms")
    db_name = os.environ.get("DB_NAME", "hotel_pms")
    c = AsyncIOMotorClient(mongo_url)
    return c, c[db_name]


async def _cleanup(db):
    await db.maintenance_tasks.delete_many({"tenant_id": TENANT})
    await db[PENDING_TASK_SNAPSHOTS].delete_many({"tenant_id": TENANT})


async def _seed_task(db, status="pending", priority="high"):
    await db.maintenance_tasks.insert_one({
        "id": str(uuid.uuid4()), "tenant_id": TENANT,
        "status": status, "priority": priority,
    })


@pytest.mark.asyncio
async def test_record_and_read_snapshot():
    client, db = await _get_db()
    await _cleanup(db)
    try:
        # 2 high + 1 urgent pending = 3 counted; the others must be excluded.
        await _seed_task(db, priority="high")
        await _seed_task(db, priority="high")
        await _seed_task(db, priority="urgent")
        await _seed_task(db, priority="low")            # excluded: low priority
        await _seed_task(db, status="completed", priority="high")  # excluded: done

        recorded = await record_pending_task_snapshot(TENANT, db, snapshot_date=DATE)
        assert recorded == 3

        # C: read back the recorded value
        assert await get_pending_task_snapshot(TENANT, DATE, db) == 3
        # C: missing date → None (so the dashboard can fall back honestly)
        assert await get_pending_task_snapshot(TENANT, "2026-01-01", db) is None
    finally:
        await _cleanup(db)
        client.close()


@pytest.mark.asyncio
async def test_snapshot_is_idempotent_per_day():
    client, db = await _get_db()
    await _cleanup(db)
    try:
        await _seed_task(db, priority="high")
        first = await record_pending_task_snapshot(TENANT, db, snapshot_date=DATE)
        assert first == 1

        # backlog grows, same day → snapshot updates in place, no duplicate doc
        await _seed_task(db, priority="urgent")
        second = await record_pending_task_snapshot(TENANT, db, snapshot_date=DATE)
        assert second == 2

        docs = await db[PENDING_TASK_SNAPSHOTS].find(
            {"tenant_id": TENANT, "snapshot_date": DATE}
        ).to_list(10)
        assert len(docs) == 1
        assert docs[0]["pending_tasks"] == 2
        assert await get_pending_task_snapshot(TENANT, DATE, db) == 2
    finally:
        await _cleanup(db)
        client.close()
