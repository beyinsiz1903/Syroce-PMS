"""Task #362 — Per-tenant, local-time night audit Celery flow.

Direct-call tests for the two task bodies in `celery_tasks`:

  * `_night_audit_dispatch_async`   — the once-a-minute beat dispatcher that
    matches each tenant's LOCAL configured time (DST-aware) and atomically
    claims it for the local day before enqueueing the worker task.
  * `_night_audit_for_tenant_async` — runs the hardened engine under
    `tenant_context` and records the outcome (the engine itself is mocked here;
    it has its own dedicated tests and needs a replica set for transactions).

Mongo is bound to the session loop by conftest; tests skip automatically when
it is unreachable. The dispatcher's wall clock is pinned via `_now_utc` so the
local-time matching is deterministic.
"""
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.asyncio

TEST_TENANT_PREFIX = "task362_na_celery_"
_SCHED_COLL = "night_audit_schedules"
_LOG_COLL = "night_audit_schedule_logs"


def _ts() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


async def _cleanup(tenant_id: str) -> None:
    from core.database import db
    await db[_SCHED_COLL].delete_many({"tenant_id": tenant_id})
    await db[_LOG_COLL].delete_many({"tenant_id": tenant_id})
    await db.tenant_settings.delete_many({"tenant_id": tenant_id})


@pytest.fixture
async def isolated_tenant():
    tid = f"{TEST_TENANT_PREFIX}{_ts()}_{uuid.uuid4().hex[:8]}"
    yield tid
    try:
        await _cleanup(tid)
    except Exception:
        pass


async def _seed_schedule(tenant_id, *, hour, minute, tz, enabled=True, last_auto_run=None):
    from core.database import db
    doc = {
        "tenant_id": tenant_id,
        "enabled": enabled,
        "scheduled_hour": hour,
        "scheduled_minute": minute,
        "timezone": tz,
        "last_auto_run": last_auto_run,
        "last_auto_run_status": None,
    }
    await db[_SCHED_COLL].update_one(
        {"tenant_id": tenant_id}, {"$set": doc}, upsert=True
    )


def _local_now(tz_name: str) -> datetime:
    return datetime.now(UTC).astimezone(ZoneInfo(tz_name))


# ── Dispatcher: local-time matching ────────────────────────────────────


async def test_dispatch_queues_when_local_time_matches(isolated_tenant):
    """A tenant whose LOCAL hour:minute == now is queued exactly once."""
    from celery_tasks import _night_audit_dispatch_async

    tz = "Asia/Tokyo"
    pinned = datetime.now(UTC)
    local = pinned.astimezone(ZoneInfo(tz))
    await _seed_schedule(isolated_tenant, hour=local.hour, minute=local.minute, tz=tz)

    with patch("celery_tasks._now_utc", return_value=pinned), \
         patch("celery_tasks.night_audit_for_tenant.delay") as mock_delay:
        result = await _night_audit_dispatch_async()

    assert result["success"] is True
    assert isolated_tenant in result["queued"]
    mock_delay.assert_called_once_with(isolated_tenant)


async def test_dispatch_skips_when_local_time_does_not_match(isolated_tenant):
    """A tenant whose configured minute is not the current local minute is
    not queued — the +/- 1 minute case must not fire early."""
    from celery_tasks import _night_audit_dispatch_async

    tz = "Europe/London"
    pinned = datetime.now(UTC)
    local = pinned.astimezone(ZoneInfo(tz))
    off_minute = (local.minute + 5) % 60
    await _seed_schedule(isolated_tenant, hour=local.hour, minute=off_minute, tz=tz)

    with patch("celery_tasks._now_utc", return_value=pinned), \
         patch("celery_tasks.night_audit_for_tenant.delay") as mock_delay:
        result = await _night_audit_dispatch_async()

    assert isolated_tenant not in result["queued"]
    mock_delay.assert_not_called()


async def test_dispatch_is_dst_aware(isolated_tenant):
    """London in July is BST (UTC+1). A schedule set to the BST wall-clock
    hour must fire — proving zoneinfo DST handling, not a fixed offset."""
    from celery_tasks import _night_audit_dispatch_async

    tz = "Europe/London"
    # 2026-07-15 12:30 UTC -> 13:30 BST (DST active).
    pinned = datetime(2026, 7, 15, 12, 30, tzinfo=UTC)
    local = pinned.astimezone(ZoneInfo(tz))
    assert local.hour == 13 and local.minute == 30  # guard: DST applied

    await _seed_schedule(isolated_tenant, hour=13, minute=30, tz=tz)

    with patch("celery_tasks._now_utc", return_value=pinned), \
         patch("celery_tasks.night_audit_for_tenant.delay") as mock_delay:
        result = await _night_audit_dispatch_async()

    assert isolated_tenant in result["queued"]
    mock_delay.assert_called_once_with(isolated_tenant)


async def test_dispatch_unknown_timezone_falls_back_to_utc(isolated_tenant):
    """An invalid IANA name must fall back to UTC (not silently to Istanbul):
    the schedule fires when the UTC wall-clock matches."""
    from celery_tasks import _night_audit_dispatch_async

    pinned = datetime(2026, 1, 15, 9, 45, tzinfo=UTC)
    await _seed_schedule(isolated_tenant, hour=9, minute=45, tz="Not/AZone")

    with patch("celery_tasks._now_utc", return_value=pinned), \
         patch("celery_tasks.night_audit_for_tenant.delay") as mock_delay:
        result = await _night_audit_dispatch_async()

    assert isolated_tenant in result["queued"]
    mock_delay.assert_called_once_with(isolated_tenant)


async def test_dispatch_skips_disabled_schedule(isolated_tenant):
    """A disabled schedule is never queued even when the time matches."""
    from celery_tasks import _night_audit_dispatch_async

    tz = "UTC"
    pinned = datetime.now(UTC)
    local = pinned.astimezone(ZoneInfo(tz))
    await _seed_schedule(
        isolated_tenant, hour=local.hour, minute=local.minute, tz=tz, enabled=False
    )

    with patch("celery_tasks._now_utc", return_value=pinned), \
         patch("celery_tasks.night_audit_for_tenant.delay") as mock_delay:
        result = await _night_audit_dispatch_async()

    assert isolated_tenant not in result["queued"]
    mock_delay.assert_not_called()


async def test_dispatch_dedups_within_local_day(isolated_tenant):
    """Two dispatcher ticks in the same matching minute must enqueue the
    tenant only ONCE — the atomic claim closes the read-then-write race."""
    from celery_tasks import _night_audit_dispatch_async
    from core.database import db

    tz = "Asia/Tokyo"
    pinned = datetime.now(UTC)
    local = pinned.astimezone(ZoneInfo(tz))
    await _seed_schedule(isolated_tenant, hour=local.hour, minute=local.minute, tz=tz)

    with patch("celery_tasks._now_utc", return_value=pinned), \
         patch("celery_tasks.night_audit_for_tenant.delay") as mock_delay:
        r1 = await _night_audit_dispatch_async()
        r2 = await _night_audit_dispatch_async()

    assert isolated_tenant in r1["queued"]
    assert isolated_tenant not in r2["queued"]
    mock_delay.assert_called_once_with(isolated_tenant)

    sched = await db[_SCHED_COLL].find_one({"tenant_id": isolated_tenant})
    assert sched["last_auto_run_status"] == "dispatched"
    assert sched["last_auto_run"] is not None


async def test_dispatch_requeues_on_next_local_day(isolated_tenant):
    """A tenant that already ran yesterday (last_auto_run before today's local
    midnight) is claimed again today."""
    from celery_tasks import _night_audit_dispatch_async

    tz = "Asia/Tokyo"
    pinned = datetime.now(UTC)
    local = pinned.astimezone(ZoneInfo(tz))
    # last run = last year, definitely before today's local-midnight boundary.
    stale = datetime(pinned.year - 1, 1, 1, tzinfo=UTC).isoformat()
    await _seed_schedule(
        isolated_tenant, hour=local.hour, minute=local.minute, tz=tz, last_auto_run=stale
    )

    with patch("celery_tasks._now_utc", return_value=pinned), \
         patch("celery_tasks.night_audit_for_tenant.delay") as mock_delay:
        result = await _night_audit_dispatch_async()

    assert isolated_tenant in result["queued"]
    mock_delay.assert_called_once_with(isolated_tenant)


# ── Per-tenant worker task wiring ──────────────────────────────────────


async def test_for_tenant_runs_engine_and_records_outcome(isolated_tenant):
    """The worker task runs the hardened engine under tenant_context and
    persists a completed schedule log + last_auto_run on success."""
    from celery_tasks import _night_audit_for_tenant_async
    from core.database import db

    run_id = str(uuid.uuid4())
    fake_result = {"success": True, "run": {"id": run_id, "business_date": "2026-02-01"}}

    with patch(
        "core.night_audit_hardened.start_night_audit",
        new=AsyncMock(return_value=fake_result),
    ) as mock_engine:
        result = await _night_audit_for_tenant_async(isolated_tenant)

    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["run_id"] == run_id
    mock_engine.assert_awaited_once()
    _, kwargs = mock_engine.await_args
    assert kwargs["tenant_id"] == isolated_tenant
    assert kwargs["trigger_source"] == "scheduler"

    log = await db[_LOG_COLL].find_one(
        {"tenant_id": isolated_tenant}, sort=[("triggered_at", -1)]
    )
    assert log is not None
    assert log["status"] == "completed"
    assert log["trigger_type"] == "automatic"
    assert log["run_id"] == run_id


async def test_for_tenant_records_failure(isolated_tenant):
    """An engine business-failure (returns success=False) is recorded as a
    failed schedule log with the error, not raised."""
    from celery_tasks import _night_audit_for_tenant_async
    from core.database import db

    fake_result = {"success": False, "error": "open folios block close"}

    with patch(
        "core.night_audit_hardened.start_night_audit",
        new=AsyncMock(return_value=fake_result),
    ):
        result = await _night_audit_for_tenant_async(isolated_tenant)

    assert result["success"] is False
    assert result["status"] == "failed"

    log = await db[_LOG_COLL].find_one(
        {"tenant_id": isolated_tenant}, sort=[("triggered_at", -1)]
    )
    assert log is not None
    assert log["status"] == "failed"
    assert log["error"] == "open folios block close"


async def test_for_tenant_restores_engine_globals(isolated_tenant):
    """The temporary rebind of engine.client/engine.db must be restored even
    when the engine raises — otherwise later tasks use a dead client."""
    import core.night_audit_hardened as engine
    from celery_tasks import _night_audit_for_tenant_async

    saved_client, saved_db = engine.client, engine.db

    with patch(
        "core.night_audit_hardened.start_night_audit",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(RuntimeError):
            await _night_audit_for_tenant_async(isolated_tenant)

    assert engine.client is saved_client
    assert engine.db is saved_db


# ── Beat registration ──────────────────────────────────────────────────


async def test_dispatch_registered_in_beat_schedule():
    """Beat schedule must run the dispatcher every minute and the old fixed
    global night-audit cron must be gone."""
    from celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "night-audit-dispatch" in schedule
    assert schedule["night-audit-dispatch"]["task"] == (
        "celery_tasks.night_audit_dispatch_task"
    )
    assert "night-audit" not in schedule  # legacy fixed-02:00 cron removed
