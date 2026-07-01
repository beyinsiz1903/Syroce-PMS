"""Tests for ws_redis_adapter rolling metrics history (Task #47).

The adapter records a snapshot of its cumulative counters at most once
per ``_snapshot_interval_s``. We freeze ``_now`` to verify both that
the cadence guard works and that snapshots roll off after the buffer
fills.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from infra.ws_redis_adapter import WebSocketRedisAdapter


@pytest.fixture
def adapter() -> WebSocketRedisAdapter:
    a = WebSocketRedisAdapter()
    a._snapshot_interval_s = 60.0
    a._snapshot_max = 5
    # ``_snapshots`` is recreated to honor the smaller maxlen for tests.
    from collections import deque

    a._snapshots = deque(maxlen=a._snapshot_max)
    return a


def _at(adapter: WebSocketRedisAdapter, ts: datetime) -> None:
    """Pin the adapter's clock to a fixed instant."""
    adapter._now = lambda: ts  # type: ignore[assignment]


def test_first_read_records_a_snapshot(adapter: WebSocketRedisAdapter):
    t0 = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)
    _at(adapter, t0)
    adapter._metrics["publish_errors"] = 3
    adapter._metrics["messages_published"] = 10
    history = adapter.get_metrics_history()
    assert len(history) == 1
    assert history[0]["publish_errors"] == 3
    assert history[0]["messages_published"] == 10
    assert history[0]["at"] == t0.isoformat()


def test_snapshots_respect_minimum_interval(adapter: WebSocketRedisAdapter):
    t0 = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)
    _at(adapter, t0)
    adapter.get_metrics()  # snapshot #1

    # Same minute → should NOT add a new snapshot, even after counters move.
    _at(adapter, t0 + timedelta(seconds=30))
    adapter._metrics["publish_errors"] = 5
    adapter.get_metrics()
    assert len(adapter.get_metrics_history()) == 1

    # 60s elapsed → second snapshot lands.
    _at(adapter, t0 + timedelta(seconds=60))
    adapter._metrics["publish_errors"] = 7
    history = adapter.get_metrics_history()
    assert len(history) == 2
    assert history[-1]["publish_errors"] == 7


def test_buffer_rolls_over_at_max_capacity(adapter: WebSocketRedisAdapter):
    base = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)
    # Push 8 minute-spaced reads into a buffer sized at 5; oldest 3 drop off.
    for i in range(8):
        _at(adapter, base + timedelta(minutes=i))
        adapter._metrics["publish_errors"] = i
        adapter.get_metrics()
    history = adapter.get_metrics_history()
    assert len(history) == 5
    # Oldest retained sample is i=3 (since 0,1,2 rolled off).
    assert history[0]["publish_errors"] == 3
    assert history[-1]["publish_errors"] == 7
