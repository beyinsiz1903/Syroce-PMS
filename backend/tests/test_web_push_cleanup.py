"""
Tests: Task #31 — Periyodik web push abonelik temizliği.

`prune_inactive_subscriptions` saf bir fonksiyon olduğu için motor/Mongo
event-loop sorunu yaşamaz; CI'da da çalışır. Worker scheduler kısmı
testin dışında — startup.py wiring'i manuel doğrulanır.
"""
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domains.guest.messaging import web_push_cleanup as wpc
from domains.guest.messaging.web_push_cleanup import (
    _is_enabled,
    _worker_loop,
    prune_inactive_subscriptions,
    start_web_push_cleanup_worker,
    stop_web_push_cleanup_worker,
)


def _mock_db(deleted_count: int = 0):
    db = MagicMock()
    db.web_push_subscriptions = MagicMock()
    db.web_push_subscriptions.delete_many = AsyncMock(
        return_value=MagicMock(deleted_count=deleted_count),
    )
    return db


@pytest.mark.asyncio
async def test_prune_uses_correct_cutoff_iso():
    """Cutoff 60 gün öncesinin ISO biçimi olmalı; fixed `now` ile
    deterministik test."""
    db = _mock_db(deleted_count=3)
    now = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)

    deleted = await prune_inactive_subscriptions(
        db=db, max_age_days=60, now=now,
    )
    assert deleted == 3

    db.web_push_subscriptions.delete_many.assert_awaited_once()
    args, _ = db.web_push_subscriptions.delete_many.call_args
    query = args[0]
    assert "$or" in query
    expected_iso = (now - timedelta(days=60)).isoformat()
    # ISO ve datetime eşleşmelerinin ikisi de mevcut olmalı.
    iso_clauses = [c for c in query["$or"] if c.get("updated_at") == {"$lt": expected_iso}]
    assert iso_clauses, query


@pytest.mark.asyncio
async def test_prune_skips_when_max_age_invalid():
    """max_age_days <= 0 verilirse delete_many çağrılmamalı (emniyet supabı)."""
    db = _mock_db(deleted_count=10)
    deleted = await prune_inactive_subscriptions(db=db, max_age_days=0)
    assert deleted == 0
    db.web_push_subscriptions.delete_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_prune_returns_zero_on_clean_state():
    db = _mock_db(deleted_count=0)
    deleted = await prune_inactive_subscriptions(db=db, max_age_days=60)
    assert deleted == 0


@pytest.mark.asyncio
async def test_prune_query_includes_legacy_no_updated_at():
    """`updated_at` alanı hiç olmayan eski kayıtların created_at fallback
    ile yine de yakalandığını doğrula."""
    db = _mock_db()
    await prune_inactive_subscriptions(db=db, max_age_days=30)
    query = db.web_push_subscriptions.delete_many.call_args[0][0]
    legacy_clause = next(
        (
            c for c in query["$or"]
            if c.get("updated_at") == {"$exists": False}
        ),
        None,
    )
    assert legacy_clause is not None
    assert "$or" in legacy_clause


@pytest.mark.asyncio
async def test_env_default_max_age_60_days(monkeypatch):
    """max_age_days verilmediğinde env default'u (60) kullanılır."""
    monkeypatch.delenv("WEB_PUSH_CLEANUP_MAX_AGE_DAYS", raising=False)
    db = _mock_db()
    now = datetime(2026, 4, 27, tzinfo=UTC)
    await prune_inactive_subscriptions(db=db, now=now)
    query = db.web_push_subscriptions.delete_many.call_args[0][0]
    expected_iso = (now - timedelta(days=60)).isoformat()
    assert any(
        c.get("updated_at") == {"$lt": expected_iso}
        for c in query["$or"]
    )


@pytest.mark.asyncio
async def test_env_override_max_age(monkeypatch):
    monkeypatch.setenv("WEB_PUSH_CLEANUP_MAX_AGE_DAYS", "7")
    db = _mock_db()
    now = datetime(2026, 4, 27, tzinfo=UTC)
    await prune_inactive_subscriptions(db=db, now=now)
    query = db.web_push_subscriptions.delete_many.call_args[0][0]
    expected_iso = (now - timedelta(days=7)).isoformat()
    assert any(
        c.get("updated_at") == {"$lt": expected_iso}
        for c in query["$or"]
    )


# ──────────────────────────────────────────────────────────────────
# Worker lifecycle / env gate / interval clamp testleri
# ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
async def _ensure_worker_stopped():
    """Her testten önce/sonra worker handle'ı temiz olsun."""
    await stop_web_push_cleanup_worker()
    yield
    await stop_web_push_cleanup_worker()


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, True),
        ("", True),
        ("1", True),
        ("true", True),
        ("yes", True),
        ("0", False),
        ("false", False),
        ("FALSE", False),
        ("no", False),
        ("off", False),
    ],
)
def test_is_enabled_env_gate(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("WEB_PUSH_CLEANUP_ENABLED", raising=False)
    else:
        monkeypatch.setenv("WEB_PUSH_CLEANUP_ENABLED", value)
    assert _is_enabled() is expected


@pytest.mark.asyncio
async def test_start_worker_disabled_via_env(monkeypatch):
    monkeypatch.setenv("WEB_PUSH_CLEANUP_ENABLED", "0")
    start_web_push_cleanup_worker()
    assert wpc._worker_task is None


@pytest.mark.asyncio
async def test_start_worker_idempotent(monkeypatch):
    """İkinci start çağrısı aynı task'ı korumalı (no-op)."""
    monkeypatch.setenv("WEB_PUSH_CLEANUP_ENABLED", "1")
    monkeypatch.setenv("WEB_PUSH_CLEANUP_INTERVAL_SECONDS", "60")
    start_web_push_cleanup_worker()
    first = wpc._worker_task
    assert first is not None
    start_web_push_cleanup_worker()
    assert wpc._worker_task is first  # aynı handle, yeni task açılmadı


@pytest.mark.asyncio
async def test_stop_worker_cancels_cleanly(monkeypatch):
    monkeypatch.setenv("WEB_PUSH_CLEANUP_ENABLED", "1")
    monkeypatch.setenv("WEB_PUSH_CLEANUP_INTERVAL_SECONDS", "60")
    start_web_push_cleanup_worker()
    task = wpc._worker_task
    assert task is not None and not task.done()
    await stop_web_push_cleanup_worker()
    assert wpc._worker_task is None
    assert task.done()  # cancelled veya bitmiş


@pytest.mark.asyncio
async def test_stop_worker_when_not_started():
    """Hiç başlatılmadıysa stop çağrısı sessizce no-op olmalı."""
    await stop_web_push_cleanup_worker()  # raise etmemeli


@pytest.mark.asyncio
async def test_interval_clamped_to_minimum(monkeypatch, caplog):
    """Sub-60s aralık verilirse 60'a clamp edilmeli + uyarı loglanmalı."""
    monkeypatch.setenv("WEB_PUSH_CLEANUP_ENABLED", "1")
    monkeypatch.setenv("WEB_PUSH_CLEANUP_INTERVAL_SECONDS", "5")
    with caplog.at_level("WARNING", logger="domains.guest.messaging.web_push_cleanup"):
        start_web_push_cleanup_worker()
    assert any("clamping" in r.getMessage().lower() for r in caplog.records)
    assert wpc._worker_task is not None


@pytest.mark.asyncio
async def test_invalid_env_int_falls_back_to_default(monkeypatch, caplog):
    monkeypatch.setenv("WEB_PUSH_CLEANUP_MAX_AGE_DAYS", "not-a-number")
    db = _mock_db()
    now = datetime(2026, 4, 27, tzinfo=UTC)
    with caplog.at_level("WARNING", logger="domains.guest.messaging.web_push_cleanup"):
        await prune_inactive_subscriptions(db=db, now=now)
    expected_iso = (now - timedelta(days=60)).isoformat()
    query = db.web_push_subscriptions.delete_many.call_args[0][0]
    assert any(
        c.get("updated_at") == {"$lt": expected_iso}
        for c in query["$or"]
    )
    assert any("invalid" in r.getMessage().lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_worker_loop_cancels_during_initial_sleep():
    """`_worker_loop` ilk sleep aşamasında iptal edilebilir olmalı."""
    task = asyncio.create_task(_worker_loop(interval_seconds=3600))
    await asyncio.sleep(0)  # loop'un sleep'e girmesine fırsat ver
    task.cancel()
    # Coroutine cancel'ı yakalayıp sessizce return ediyor — exception
    # propagate etmemeli.
    await task
    assert task.done()
