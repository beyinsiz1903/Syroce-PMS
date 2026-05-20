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


async def _reset_alert_state() -> None:
    from core.database import db
    await db.rnl_duplicate_alert_state.delete_many({"state_key": "manual_required"})


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


async def test_beat_task_dispatches_alert_on_first_detection_then_suppresses(isolated_tenant):
    """Task #228: first non-zero manual_required → alert sent; next run suppresses."""
    from unittest.mock import AsyncMock, patch

    from celery_tasks import _rnl_duplicate_auto_resolve_async
    from core.database import db

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:8]}"
    night = "2030-10-03"
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    await _seed_booking(tid, a, "confirmed")
    await _seed_booking(tid, b, "checked_in")
    await _seed_lock(tid, room_id, night, a)
    await _seed_lock(tid, room_id, night, b)

    await _reset_alert_state()
    try:
        with patch(
            "domains.channel_manager.monitoring.alert_dispatch.dispatch_alert",
            new=AsyncMock(return_value={"dashboard": True, "slack": False, "email": False}),
        ) as mock_dispatch:
            result1 = await _rnl_duplicate_auto_resolve_async(limit=50)
            assert result1["manual_required_count"] >= 1
            assert result1["alert_dispatched"]["sent"] is True
            assert result1["alert_dispatched"]["reason"] == "first_detection"
            assert mock_dispatch.await_count == 1
            payload = mock_dispatch.await_args.args[0]
            assert payload["severity"] == "high"
            assert payload["alert_type"] == "rnl_duplicate_manual_required"
            assert payload["context"]["sample_tenant_id"] == tid
            assert payload["context"]["sample_room_id"] == room_id
            assert payload["context"]["sample_night_date"] == night

            result2 = await _rnl_duplicate_auto_resolve_async(limit=50)
            assert result2["alert_dispatched"]["sent"] is False
            assert result2["alert_dispatched"]["suppressed"] is True
            assert result2["alert_dispatched"]["reason"] == "streak_active"
            assert mock_dispatch.await_count == 1  # no new dispatch

        state = await db.rnl_duplicate_alert_state.find_one(
            {"state_key": "manual_required"}
        )
        assert state is not None
        assert state["active"] is True
        assert state["last_alert_count"] >= 1
    finally:
        await _reset_alert_state()


async def test_beat_task_retries_when_dispatch_fails(isolated_tenant):
    """Task #228 reliability: dispatch failure must NOT enter suppression
    state — the next run must retry dispatch instead of silently being quiet."""
    from unittest.mock import AsyncMock, patch

    from celery_tasks import _rnl_duplicate_auto_resolve_async
    from core.database import db

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:8]}"
    night = "2030-10-04"
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    await _seed_booking(tid, a, "confirmed")
    await _seed_booking(tid, b, "checked_in")
    await _seed_lock(tid, room_id, night, a)
    await _seed_lock(tid, room_id, night, b)

    await _reset_alert_state()
    try:
        # Run 1: dispatcher raises.
        with patch(
            "domains.channel_manager.monitoring.alert_dispatch.dispatch_alert",
            new=AsyncMock(side_effect=RuntimeError("slack down")),
        ) as mock_fail:
            r1 = await _rnl_duplicate_auto_resolve_async(limit=50)
            assert r1["alert_dispatched"]["sent"] is False
            assert r1["alert_dispatched"]["reason"] == "dispatch_failed"
            assert mock_fail.await_count == 1

        state = await db.rnl_duplicate_alert_state.find_one(
            {"state_key": "manual_required"}
        )
        # active must NOT be set — otherwise next run would be suppressed.
        assert state is not None
        assert state.get("active") is not True
        assert "last_dispatch_failed_at" in state

        # Run 2: dispatcher recovers — must actually dispatch again.
        with patch(
            "domains.channel_manager.monitoring.alert_dispatch.dispatch_alert",
            new=AsyncMock(return_value={"dashboard": True}),
        ) as mock_ok:
            r2 = await _rnl_duplicate_auto_resolve_async(limit=50)
            assert r2["alert_dispatched"]["sent"] is True
            assert r2["alert_dispatched"]["reason"] == "first_detection"
            assert mock_ok.await_count == 1

        state2 = await db.rnl_duplicate_alert_state.find_one(
            {"state_key": "manual_required"}
        )
        assert state2["active"] is True
        assert "last_dispatch_failed_at" not in state2
    finally:
        await _reset_alert_state()


async def test_beat_task_clears_alert_state_when_count_drops_to_zero(isolated_tenant):
    """Task #228: when manual_required returns to zero, state is cleared so a
    subsequent re-occurrence re-alerts (no permanent suppression)."""
    from unittest.mock import AsyncMock, patch

    from celery_tasks import _rnl_duplicate_auto_resolve_async
    from core.database import db

    # Pre-seed an "active streak" state doc — emulates a previous run that
    # already alerted; this run has zero duplicates and must clear it.
    await db.rnl_duplicate_alert_state.update_one(
        {"state_key": "manual_required"},
        {"$set": {
            "state_key": "manual_required",
            "active": True,
            "last_count": 3,
            "last_alert_count": 3,
        }},
        upsert=True,
    )
    try:
        with patch(
            "domains.channel_manager.monitoring.alert_dispatch.dispatch_alert",
            new=AsyncMock(return_value={"dashboard": True}),
        ) as mock_dispatch:
            # No seeded duplicates → scan returns 0 manual_required.
            result = await _rnl_duplicate_auto_resolve_async(limit=50)
            assert result["manual_required_count"] == 0
            assert result["alert_dispatched"]["sent"] is False
            assert result["alert_dispatched"]["reason"] == "count_zero"
            assert mock_dispatch.await_count == 0

        state = await db.rnl_duplicate_alert_state.find_one(
            {"state_key": "manual_required"}
        )
        assert state is not None
        assert state["active"] is False
        assert state["last_count"] == 0
    finally:
        await _reset_alert_state()


async def test_beat_task_registered_in_beat_schedule():
    """Beat schedule must include the daily rnl-duplicate-auto-resolve entry."""
    from celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "rnl-duplicate-auto-resolve" in schedule
    entry = schedule["rnl-duplicate-auto-resolve"]
    assert entry["task"] == "celery_tasks.rnl_duplicate_auto_resolve_task"


async def test_beat_task_persists_run_history(isolated_tenant):
    """Each run must persist a summary row into rnl_auto_resolve_runs.

    The super-admin panel reads this collection to surface scheduled-job
    behaviour without log-diving (Task #229).
    """
    from celery_tasks import _rnl_duplicate_auto_resolve_async
    from core.database import db

    tid = isolated_tenant
    room_id = f"room_{uuid.uuid4().hex[:8]}"
    night = "2030-10-03"
    active_id = str(uuid.uuid4())
    cancelled_id = str(uuid.uuid4())

    await _seed_booking(tid, active_id, "confirmed")
    await _seed_booking(tid, cancelled_id, "cancelled")
    await _seed_lock(tid, room_id, night, active_id)
    await _seed_lock(tid, room_id, night, cancelled_id)

    before = await db.rnl_auto_resolve_runs.count_documents({"actor_id": "celery_beat"})
    result = await _rnl_duplicate_auto_resolve_async(limit=50)
    after = await db.rnl_auto_resolve_runs.count_documents({"actor_id": "celery_beat"})

    assert result["success"] is True
    assert after == before + 1

    last = await db.rnl_auto_resolve_runs.find_one(
        {"actor_id": "celery_beat"},
        sort=[("started_at", -1)],
    )
    assert last is not None
    for key in (
        "started_at", "finished_at", "scanned",
        "resolved_count", "skipped_count", "manual_required_count",
        "index_rebuild", "limit",
    ):
        assert key in last, f"missing key in persisted run: {key}"
    assert last["limit"] == 50
    assert last["resolved_count"] == result["resolved_count"]
