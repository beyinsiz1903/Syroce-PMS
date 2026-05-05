"""Tests: KVKK ID photo view alert worker (Task #105).

Mock-only tests — they replace the system DB with `MagicMock`/`AsyncMock`
collections so we never touch the real Mongo event loop. Every test
exercises `_run_once` end-to-end: aggregation → config resolution →
cooldown gate → audit + notification dispatch.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _AsyncIter:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


def _fake_db(rows, *, configs=None, state=None, recount=0):
    """Build a mock DB driving the worker.

    - `rows`     : aggregation result list (worker shape, NOT raw Mongo `_id` form).
    - `configs`  : per-tenant config docs returned by `kvkk_id_photo_alert_config.find`.
    - `state`    : last-alerted state doc returned by `find_one` (None = never alerted).
    - `recount`  : value returned by `audit_logs.count_documents` (per-tenant recount path).
    """
    configs = configs or []
    db = MagicMock()

    raw_rows = [
        {
            "_id": {"tenant_id": r["tenant_id"], "actor_id": r["actor_id"]},
            "count": r["count"],
            "last_view_at": r.get("last_view_at"),
        }
        for r in rows
    ]

    db.audit_logs = MagicMock()
    db.audit_logs.aggregate = MagicMock(return_value=_AsyncIter(raw_rows))
    db.audit_logs.count_documents = AsyncMock(return_value=recount)
    db.audit_logs.insert_one = AsyncMock()

    config_coll = MagicMock()
    config_coll.find = MagicMock(return_value=_AsyncIter(configs))
    config_coll.create_index = AsyncMock()

    state_coll = MagicMock()
    state_coll.find_one = AsyncMock(return_value=state)
    state_coll.update_one = AsyncMock()
    state_coll.create_index = AsyncMock()

    coll_map = {
        "kvkk_id_photo_alert_config": config_coll,
        "kvkk_id_photo_alert_state": state_coll,
    }
    db.__getitem__ = MagicMock(side_effect=lambda name: coll_map[name])

    db.notifications = MagicMock()
    db.notifications.insert_one = AsyncMock()

    return db


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── Aggregation pipeline shape ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_aggregation_pipeline_matches_view_action():
    from workers import id_photo_view_alert as worker

    db = _fake_db([])
    with patch.object(worker, "_system_db", return_value=db):
        await worker._run_once()

    pipeline = db.audit_logs.aggregate.call_args.args[0]
    assert pipeline[0]["$match"]["operation_name"] == "view_online_checkin_id_photo"
    assert "$gte" in pipeline[0]["$match"]["timestamp"]
    group = pipeline[1]["$group"]
    assert group["_id"] == {"tenant_id": "$tenant_id", "actor_id": "$actor_id"}


# ── Threshold gating ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fires_when_default_threshold_exceeded():
    from workers import id_photo_view_alert as worker

    rows = [{"tenant_id": "t1", "actor_id": "u-a", "count": 25, "last_view_at": _now_iso()}]
    db = _fake_db(rows)
    with patch.object(worker, "_system_db", return_value=db):
        summary = await worker._run_once()

    assert summary == {"rows_scanned": 1, "alerts_fired": 1}

    db.audit_logs.insert_one.assert_awaited_once()
    audit_doc = db.audit_logs.insert_one.await_args.args[0]
    assert audit_doc["operation_name"] == "id_photo_view_burst_alert"
    assert audit_doc["severity"] == "critical"
    assert audit_doc["tenant_id"] == "t1"
    assert audit_doc["actor_id"] == "u-a"
    assert audit_doc["after_snapshot"]["view_count"] == 25
    assert audit_doc["after_snapshot"]["threshold"] == worker.DEFAULT_THRESHOLD

    db.notifications.insert_one.assert_awaited_once()
    notif = db.notifications.insert_one.await_args.args[0]
    assert notif["type"] == "kvkk_id_photo_alert"
    assert notif["priority"] == "high"
    assert notif["tenant_id"] == "t1"
    assert notif["user_id"] is None  # tenant-broadcast within manager roles
    # Manager/admin gating — notifications router filters by target_roles
    # so clerks and front-desk staff don't see this entry.
    assert "admin" in notif["target_roles"]
    assert "super_admin" in notif["target_roles"]
    assert "supervisor" in notif["target_roles"]
    assert notif["context"]["actor_id"] == "u-a"


@pytest.mark.asyncio
async def test_skips_when_below_default_threshold():
    from workers import id_photo_view_alert as worker

    rows = [{"tenant_id": "t1", "actor_id": "u-a", "count": 5, "last_view_at": _now_iso()}]
    db = _fake_db(rows)
    with patch.object(worker, "_system_db", return_value=db):
        summary = await worker._run_once()

    assert summary == {"rows_scanned": 1, "alerts_fired": 0}
    db.audit_logs.insert_one.assert_not_awaited()
    db.notifications.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_per_tenant_threshold_overrides_default():
    """Strict tenant config (threshold=3) fires for a count that the
    default threshold (20) would ignore. Recount path is exercised
    because the tenant window (30) is shorter than the global scan
    window (max=60)."""
    from workers import id_photo_view_alert as worker

    rows = [{"tenant_id": "strict", "actor_id": "u-a", "count": 5, "last_view_at": _now_iso()}]
    configs = [{"tenant_id": "strict", "threshold": 3, "window_minutes": 30}]
    db = _fake_db(rows, configs=configs, recount=5)

    with patch.object(worker, "_system_db", return_value=db):
        summary = await worker._run_once()

    assert summary == {"rows_scanned": 1, "alerts_fired": 1}
    db.audit_logs.count_documents.assert_awaited_once()
    db.audit_logs.insert_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_per_tenant_recount_can_drop_below_threshold():
    """Even if global scan saw many events, the tenant's smaller window
    may contain fewer. The recount must take precedence."""
    from workers import id_photo_view_alert as worker

    rows = [{"tenant_id": "strict", "actor_id": "u-a", "count": 50, "last_view_at": _now_iso()}]
    configs = [{"tenant_id": "strict", "threshold": 10, "window_minutes": 5}]
    db = _fake_db(rows, configs=configs, recount=2)

    with patch.object(worker, "_system_db", return_value=db):
        summary = await worker._run_once()

    assert summary == {"rows_scanned": 1, "alerts_fired": 0}
    db.audit_logs.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_tenant_does_not_alert_even_for_high_counts():
    from workers import id_photo_view_alert as worker

    rows = [{"tenant_id": "off", "actor_id": "u-a", "count": 100, "last_view_at": _now_iso()}]
    configs = [{"tenant_id": "off", "enabled": False}]
    db = _fake_db(rows, configs=configs)

    with patch.object(worker, "_system_db", return_value=db):
        summary = await worker._run_once()

    assert summary == {"rows_scanned": 1, "alerts_fired": 0}
    db.audit_logs.insert_one.assert_not_awaited()
    db.notifications.insert_one.assert_not_awaited()


# ── Cooldown ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cooldown_suppresses_repeat_alert_within_window():
    from workers import id_photo_view_alert as worker

    rows = [{"tenant_id": "t1", "actor_id": "u-a", "count": 25, "last_view_at": _now_iso()}]
    db = _fake_db(rows, state={"last_alerted_at": _now_iso()})

    with patch.object(worker, "_system_db", return_value=db):
        summary = await worker._run_once()

    assert summary == {"rows_scanned": 1, "alerts_fired": 0}
    db.audit_logs.insert_one.assert_not_awaited()
    db.notifications.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_cooldown_expired_allows_new_alert():
    from workers import id_photo_view_alert as worker

    rows = [{"tenant_id": "t1", "actor_id": "u-a", "count": 25, "last_view_at": _now_iso()}]
    long_ago = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    db = _fake_db(rows, state={"last_alerted_at": long_ago})

    with patch.object(worker, "_system_db", return_value=db):
        summary = await worker._run_once()

    assert summary == {"rows_scanned": 1, "alerts_fired": 1}
    db.audit_logs.insert_one.assert_awaited_once()
    db.notifications.insert_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_alert_records_state_with_timestamp():
    from workers import id_photo_view_alert as worker

    rows = [{"tenant_id": "t1", "actor_id": "u-a", "count": 30, "last_view_at": _now_iso()}]
    db = _fake_db(rows)

    with patch.object(worker, "_system_db", return_value=db):
        await worker._run_once()

    state_coll = db["kvkk_id_photo_alert_state"]
    state_coll.update_one.assert_awaited_once()
    filt, update = state_coll.update_one.await_args.args[:2]
    assert filt == {"tenant_id": "t1", "actor_id": "u-a"}
    assert update["$set"]["tenant_id"] == "t1"
    assert update["$set"]["actor_id"] == "u-a"
    assert "last_alerted_at" in update["$set"]
    assert state_coll.update_one.await_args.kwargs.get("upsert") is True


# ── Robustness ─────────────────────────────────────────────────────────


def test_resolve_config_clamps_invalid_values():
    from workers import id_photo_view_alert as worker

    cfg = worker._resolve_config(
        {
            "threshold": -5,
            "window_minutes": 0,
            "cooldown_minutes": 999_999_999,
        },
        "tenant-x",
    )
    # Negative threshold is non-falsy → kept as int then clamped to 1.
    assert cfg["threshold"] == 1
    # window_minutes=0 is falsy → falls back to default.
    assert cfg["window_minutes"] == worker.DEFAULT_WINDOW_MINUTES
    # Excessive cooldown is clamped to the 7-day upper bound.
    assert cfg["cooldown_minutes"] == 7 * 24 * 60
    assert cfg["enabled"] is True


def test_resolve_config_respects_explicit_disable():
    from workers import id_photo_view_alert as worker

    cfg = worker._resolve_config({"enabled": False}, "tenant-x")
    assert cfg["enabled"] is False


def test_resolve_config_defaults_when_empty():
    from workers import id_photo_view_alert as worker

    cfg = worker._resolve_config(None, "tenant-x")
    assert cfg["threshold"] == worker.DEFAULT_THRESHOLD
    assert cfg["window_minutes"] == worker.DEFAULT_WINDOW_MINUTES
    assert cfg["cooldown_minutes"] == worker.DEFAULT_COOLDOWN_MINUTES
    assert cfg["enabled"] is True


@pytest.mark.asyncio
async def test_evaluate_failure_does_not_kill_cycle():
    """One bad row must not block other tenants in the same tick."""
    from workers import id_photo_view_alert as worker

    rows = [
        {"tenant_id": "broken", "actor_id": "u-a", "count": 25, "last_view_at": _now_iso()},
        {"tenant_id": "ok", "actor_id": "u-b", "count": 25, "last_view_at": _now_iso()},
    ]
    db = _fake_db(rows)

    original = worker._write_high_severity_audit
    call_count = {"n": 0}

    async def flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("audit insert exploded")
        return await original(*args, **kwargs)

    with patch.object(worker, "_system_db", return_value=db), \
         patch.object(worker, "_write_high_severity_audit", side_effect=flaky):
        summary = await worker._run_once()

    assert summary["rows_scanned"] == 2
    assert summary["alerts_fired"] == 1  # second row succeeded
    db.notifications.insert_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_rows_with_missing_keys_are_skipped():
    from workers import id_photo_view_alert as worker

    db = MagicMock()
    db.audit_logs = MagicMock()
    db.audit_logs.aggregate = MagicMock(
        return_value=_AsyncIter([
            {"_id": None, "count": 99},
            {"_id": {"tenant_id": "t1"}, "count": 99},  # missing actor_id
            {"_id": {"actor_id": "u-a"}, "count": 99},  # missing tenant_id
        ])
    )
    db.audit_logs.count_documents = AsyncMock(return_value=0)
    db.audit_logs.insert_one = AsyncMock()
    config_coll = MagicMock()
    config_coll.find = MagicMock(return_value=_AsyncIter([]))
    state_coll = MagicMock()
    state_coll.find_one = AsyncMock(return_value=None)
    state_coll.update_one = AsyncMock()
    db.__getitem__ = MagicMock(side_effect=lambda n: {
        "kvkk_id_photo_alert_config": config_coll,
        "kvkk_id_photo_alert_state": state_coll,
    }[n])
    db.notifications = MagicMock()
    db.notifications.insert_one = AsyncMock()

    with patch.object(worker, "_system_db", return_value=db):
        summary = await worker._run_once()

    assert summary == {"rows_scanned": 0, "alerts_fired": 0}
    db.audit_logs.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_max_window_minutes_uses_largest_tenant_window():
    from workers import id_photo_view_alert as worker

    configs = {
        "a": worker._resolve_config({"window_minutes": 15}, "a"),
        "b": worker._resolve_config({"window_minutes": 240}, "b"),
    }
    assert worker._max_window_minutes(configs) == 240


def test_default_constants_are_documented():
    """Lock the documented defaults so doc + code stay in sync."""
    from workers import id_photo_view_alert as worker

    assert worker.DEFAULT_THRESHOLD == 20
    assert worker.DEFAULT_WINDOW_MINUTES == 60
    assert worker.DEFAULT_COOLDOWN_MINUTES == 60
    assert worker.VIEW_ACTION == "view_online_checkin_id_photo"
    assert worker.ALERT_ACTION == "id_photo_view_burst_alert"
    assert worker.CONFIG_COLLECTION == "kvkk_id_photo_alert_config"
    assert worker.STATE_COLLECTION == "kvkk_id_photo_alert_state"
    # Default notification targeting — only managers see the bell entry.
    assert set(worker.DEFAULT_ALERT_ROLES) == {"super_admin", "admin", "supervisor"}


# ── Config robustness against malformed docs ───────────────────────────


def test_safe_int_handles_non_numeric_values():
    from workers import id_photo_view_alert as worker

    assert worker._safe_int("abc", 99) == 99
    assert worker._safe_int(None, 99) == 99
    assert worker._safe_int("", 99) == 99
    assert worker._safe_int(True, 99) == 99  # bool rejected
    assert worker._safe_int(False, 99) == 99
    assert worker._safe_int("42", 99) == 42
    assert worker._safe_int(42, 99) == 42
    assert worker._safe_int(3.7, 99) == 3  # float coerced


def test_resolve_config_survives_garbage_strings():
    """A tenant doc with non-numeric junk must NOT raise — it must
    fall back to defaults so the worker keeps running."""
    from workers import id_photo_view_alert as worker

    cfg = worker._resolve_config(
        {"threshold": "abc", "window_minutes": "xyz", "cooldown_minutes": None},
        "tenant-junk",
    )
    assert cfg["threshold"] == worker.DEFAULT_THRESHOLD
    assert cfg["window_minutes"] == worker.DEFAULT_WINDOW_MINUTES
    assert cfg["cooldown_minutes"] == worker.DEFAULT_COOLDOWN_MINUTES


def test_resolve_config_accepts_custom_alert_roles():
    from workers import id_photo_view_alert as worker

    cfg = worker._resolve_config({"alert_roles": ["admin", "owner"]}, "t1")
    assert cfg["alert_roles"] == ("admin", "owner")


def test_resolve_config_falls_back_for_invalid_alert_roles():
    from workers import id_photo_view_alert as worker

    # Wrong type → defaults
    cfg = worker._resolve_config({"alert_roles": "not-a-list"}, "t1")
    assert cfg["alert_roles"] == worker.DEFAULT_ALERT_ROLES
    # Empty list of garbage entries → defaults
    cfg = worker._resolve_config({"alert_roles": [None, 5, ""]}, "t1")
    assert cfg["alert_roles"] == worker.DEFAULT_ALERT_ROLES


@pytest.mark.asyncio
async def test_load_configs_isolates_bad_documents():
    """One malformed config doc must NOT prevent the others from loading.

    Earlier behaviour raised inside the async iteration, swallowing all
    tenants' configs. The hardened loader catches per-doc and continues.
    """
    from workers import id_photo_view_alert as worker

    class _ExplodingDict(dict):
        def __init__(self):
            super().__init__(tenant_id="boom", threshold=1)  # non-empty so `raw or {}` keeps it

        def get(self, key, default=None):
            if key == "tenant_id":
                return "boom"
            raise RuntimeError("simulated parse error")

    docs = [
        {"tenant_id": "good-1", "threshold": 5},
        _ExplodingDict(),
        "totally-not-a-dict",
        {"tenant_id": "good-2", "threshold": 7, "window_minutes": "junk"},
    ]

    db = MagicMock()
    config_coll = MagicMock()
    config_coll.find = MagicMock(return_value=_AsyncIter(docs))
    db.__getitem__ = MagicMock(side_effect=lambda n: {
        "kvkk_id_photo_alert_config": config_coll,
    }[n])

    out = await worker._load_configs(db)

    assert "good-1" in out
    assert out["good-1"]["threshold"] == 5
    assert "good-2" in out
    # Garbage window_minutes coerced to default — tenant still gets a config.
    assert out["good-2"]["window_minutes"] == worker.DEFAULT_WINDOW_MINUTES
    assert "boom" not in out  # exploding doc skipped
    assert len(out) == 2


@pytest.mark.asyncio
async def test_run_once_completes_when_one_config_is_garbage():
    """Full _run_once must process good tenants even when a sibling
    tenant has a malformed config doc."""
    from workers import id_photo_view_alert as worker

    class _ExplodingDict(dict):
        def get(self, key, default=None):
            if key == "tenant_id":
                return "broken"
            raise RuntimeError("config parse error")

    rows = [
        {"tenant_id": "ok", "actor_id": "u-a", "count": 30, "last_view_at": _now_iso()},
    ]
    configs = [_ExplodingDict(), {"tenant_id": "ok"}]
    db = _fake_db(rows, configs=configs)

    with patch.object(worker, "_system_db", return_value=db):
        summary = await worker._run_once()

    assert summary == {"rows_scanned": 1, "alerts_fired": 1}
    db.audit_logs.insert_one.assert_awaited_once()
    db.notifications.insert_one.assert_awaited_once()


# ── Manager-only notification targeting ─────────────────────────────────


@pytest.mark.asyncio
async def test_notification_carries_default_target_roles():
    from workers import id_photo_view_alert as worker

    rows = [{"tenant_id": "t1", "actor_id": "u-a", "count": 30, "last_view_at": _now_iso()}]
    db = _fake_db(rows)
    with patch.object(worker, "_system_db", return_value=db):
        await worker._run_once()

    notif = db.notifications.insert_one.await_args.args[0]
    assert isinstance(notif["target_roles"], list)
    assert set(notif["target_roles"]) == set(worker.DEFAULT_ALERT_ROLES)


@pytest.mark.asyncio
async def test_notification_uses_tenant_custom_alert_roles():
    from workers import id_photo_view_alert as worker

    rows = [{"tenant_id": "t1", "actor_id": "u-a", "count": 30, "last_view_at": _now_iso()}]
    configs = [{"tenant_id": "t1", "alert_roles": ["owner", "admin"]}]
    db = _fake_db(rows, configs=configs)

    with patch.object(worker, "_system_db", return_value=db):
        await worker._run_once()

    notif = db.notifications.insert_one.await_args.args[0]
    assert notif["target_roles"] == ["owner", "admin"]
