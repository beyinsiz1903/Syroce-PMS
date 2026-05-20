"""F8N Task #224 — Scheduled auto-resolver Celery task.

Direct-call tests for `_rnl_duplicate_auto_resolve_async` (the async body of
the `celery_tasks.rnl_duplicate_auto_resolve_task` beat job). Skips
automatically when MongoDB is not reachable (conftest fixture binds Motor
to the session event loop).
"""
import uuid
from datetime import UTC, datetime

import pytest


pytestmark = pytest.mark.asyncio

TEST_TENANT_PREFIX = "f8n_rnl_beat_task_"


def _ts() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


async def _cleanup(tenant_id: str) -> None:
    from core.database import db
    await db.bookings.delete_many({"tenant_id": tenant_id})
    await db.room_night_locks.delete_many({"tenant_id": tenant_id})
    await db.audit_logs.delete_many({"tenant_id": tenant_id})


@pytest.fixture
async def isolated_tenant():
    tid = f"{TEST_TENANT_PREFIX}{_ts()}_{uuid.uuid4().hex[:8]}"
    yield tid
    try:
        await _cleanup(tid)
    except Exception:
        pass


async def _seed_lock(tenant_id, room_id, night, booking_id, lock_type="booking"):
    from core.database import db
    await db.room_night_locks.insert_one({
        "tenant_id": tenant_id,
        "room_id": room_id,
        "night_date": night,
        "booking_id": booking_id,
        "lock_type": lock_type,
        "created_at": datetime.now(UTC).isoformat(),
    })


async def _seed_booking(tenant_id, booking_id, status):
    from core.database import db
    await db.bookings.insert_one({
        "id": booking_id,
        "tenant_id": tenant_id,
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
    })


async def test_beat_task_resolves_auto_safe_and_rebuilds_index(isolated_tenant):
    """Active + cancelled lock on same night → resolved, index rebuild ran."""
    from celery_tasks import _rnl_duplicate_auto_resolve_async
    from core.database import db

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:8]}"
    night = "2030-10-01"
    active_id = str(uuid.uuid4())
    cancelled_id = str(uuid.uuid4())

    await _seed_booking(tid, active_id, "confirmed")
    await _seed_booking(tid, cancelled_id, "cancelled")
    await _seed_lock(tid, room_id, night, active_id)
    await _seed_lock(tid, room_id, night, cancelled_id)

    result = await _rnl_duplicate_auto_resolve_async(limit=50)
    assert result["success"] is True
    assert result["resolved_count"] >= 1
    # Index rebuild attempted because resolved_count > 0.
    assert result["index_rebuild"]["ran"] is True

    remaining = await db.room_night_locks.find(
        {"tenant_id": tid, "room_id": room_id, "night_date": night},
        {"_id": 0, "booking_id": 1},
    ).to_list(10)
    assert len(remaining) == 1
    assert remaining[0]["booking_id"] == active_id

    audit = await db.audit_logs.find_one(
        {"tenant_id": tid, "action": "AUTO_RESOLVE_RNL_DUPLICATE"}
    )
    assert audit is not None
    assert audit["user_id"] == "celery_beat"


async def test_beat_task_counts_manual_required(isolated_tenant):
    """Two active bookings → manual_required, nothing deleted, metric exposed."""
    from celery_tasks import _rnl_duplicate_auto_resolve_async
    from core.database import db

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:8]}"
    night = "2030-10-02"
    a, b = str(uuid.uuid4()), str(uuid.uuid4())

    await _seed_booking(tid, a, "confirmed")
    await _seed_booking(tid, b, "checked_in")
    await _seed_lock(tid, room_id, night, a)
    await _seed_lock(tid, room_id, night, b)

    result = await _rnl_duplicate_auto_resolve_async(limit=50)
    assert result["success"] is True
    assert result["manual_required_count"] >= 1

    remaining = await db.room_night_locks.count_documents(
        {"tenant_id": tid, "room_id": room_id, "night_date": night}
    )
    assert remaining == 2  # nothing deleted


async def test_beat_task_registered_in_beat_schedule():
    """Beat schedule must include the daily rnl-duplicate-auto-resolve entry."""
    from celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "rnl-duplicate-auto-resolve" in schedule
    entry = schedule["rnl-duplicate-auto-resolve"]
    assert entry["task"] == "celery_tasks.rnl_duplicate_auto_resolve_task"
