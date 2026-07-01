"""Tests for `core.transient_db_guard` — the shared streak tracker used by
background workers (import-retry, ARI push, KVKK id-photo alert) to demote
transient Atlas hiccups to WARNING while still escalating sustained
outages to ERROR for Sentry visibility.
"""
from __future__ import annotations

import logging

import pytest
from pymongo.errors import AutoReconnect, NetworkTimeout, ServerSelectionTimeoutError

from core.transient_db_guard import (
    TransientFailureTracker,
    is_transient_db_error,
)


def test_classification_recognises_atlas_and_network_errors():
    assert is_transient_db_error(AutoReconnect("x"))
    assert is_transient_db_error(NetworkTimeout("x"))
    assert is_transient_db_error(ServerSelectionTimeoutError("x"))
    assert is_transient_db_error(ConnectionError("x"))
    assert is_transient_db_error(OSError("x"))


def test_classification_rejects_programmer_errors():
    assert not is_transient_db_error(ValueError("x"))
    assert not is_transient_db_error(KeyError("x"))
    assert not is_transient_db_error(RuntimeError("x"))


def test_warning_then_error_after_threshold(caplog):
    caplog.set_level(logging.DEBUG, logger="test-w")
    logger = logging.getLogger("test-w")
    tracker = TransientFailureTracker("w", threshold=3)

    for _ in range(2):
        tracker.log_exception(logger, AutoReconnect("blip"), "t1")
    after_two = [r.levelname for r in caplog.records]
    assert after_two == ["WARNING", "WARNING"]

    caplog.clear()
    tracker.log_exception(logger, AutoReconnect("blip"), "t1")
    assert [r.levelname for r in caplog.records] == ["ERROR"]


def test_streak_stays_error_after_threshold(caplog):
    caplog.set_level(logging.DEBUG, logger="test-stay")
    logger = logging.getLogger("test-stay")
    tracker = TransientFailureTracker("w", threshold=2)

    for _ in range(5):
        tracker.log_exception(logger, AutoReconnect("blip"), "t1")
    levels = [r.levelname for r in caplog.records]
    # threshold=2 → first WARNING, next 4 all ERROR
    assert levels == ["WARNING", "ERROR", "ERROR", "ERROR", "ERROR"]


def test_reset_clears_streak(caplog):
    caplog.set_level(logging.DEBUG, logger="test-r")
    logger = logging.getLogger("test-r")
    tracker = TransientFailureTracker("w", threshold=3)

    for _ in range(2):
        tracker.log_exception(logger, AutoReconnect("blip"), "t1")
    assert tracker.streak("t1") == 2
    tracker.reset("t1")
    assert tracker.streak("t1") == 0

    caplog.clear()
    tracker.log_exception(logger, AutoReconnect("blip"), "t1")
    # streak rebuilt from 1 → WARNING, not ERROR
    assert caplog.records[0].levelname == "WARNING"


def test_per_key_streaks_are_independent(caplog):
    caplog.set_level(logging.DEBUG, logger="test-i")
    logger = logging.getLogger("test-i")
    tracker = TransientFailureTracker("w", threshold=3)

    for _ in range(3):
        tracker.log_exception(logger, AutoReconnect("blip"), "ta")
    # tb has zero streak — first hit should be WARNING
    caplog.clear()
    tracker.log_exception(logger, AutoReconnect("blip"), "tb")
    assert caplog.records[0].levelname == "WARNING"
    assert tracker.streak("ta") == 3
    assert tracker.streak("tb") == 1


def test_non_transient_error_stays_at_error_level(caplog):
    caplog.set_level(logging.DEBUG, logger="test-nt")
    logger = logging.getLogger("test-nt")
    tracker = TransientFailureTracker("w", threshold=3)

    tracker.log_exception(logger, ValueError("real bug"), "t1")
    assert caplog.records[0].levelname == "ERROR"
    # Non-transient must NOT consume the transient streak budget
    assert tracker.streak("t1") == 0


def test_non_transient_error_preserves_traceback(caplog):
    """Regression: replacing `logger.exception(...)` must not lose Sentry
    stack-trace fidelity for real bugs."""
    caplog.set_level(logging.DEBUG, logger="test-tb")
    logger = logging.getLogger("test-tb")
    tracker = TransientFailureTracker("w", threshold=3)

    try:
        raise ValueError("real bug")
    except ValueError as exc:
        tracker.log_exception(logger, exc, "t1")

    rec = caplog.records[0]
    assert rec.levelname == "ERROR"
    assert rec.exc_info is not None, "non-transient errors must carry exc_info"
    assert rec.exc_info[0] is ValueError


def test_prune_drops_stale_keys_preserves_outer_loop():
    tracker = TransientFailureTracker("w", threshold=3)
    logger = logging.getLogger("test-p")
    logger.addHandler(logging.NullHandler())

    tracker.log_exception(logger, AutoReconnect("x"), "t-gone")
    tracker.log_exception(logger, AutoReconnect("x"), "t-also-gone")
    tracker.log_exception(logger, AutoReconnect("x"), "t-active")
    tracker.log_exception(logger, AutoReconnect("x"), TransientFailureTracker.OUTER_LOOP_KEY)

    tracker.prune({"t-active"})
    snap = tracker.snapshot()
    assert "t-gone" not in snap
    assert "t-also-gone" not in snap
    assert snap.get("t-active") == 1
    # Outer loop key is reserved and must survive prune
    assert snap.get(TransientFailureTracker.OUTER_LOOP_KEY) == 1


def test_threshold_minimum_clamps_to_one():
    tracker = TransientFailureTracker("w", threshold=0)
    assert tracker.threshold == 1


def test_context_appears_in_log_message(caplog):
    caplog.set_level(logging.DEBUG, logger="test-c")
    logger = logging.getLogger("test-c")
    tracker = TransientFailureTracker("my-worker", threshold=3)

    tracker.log_exception(logger, AutoReconnect("blip"), "tx", context="tenant=tx")
    msg = caplog.records[0].getMessage()
    assert "my-worker" in msg
    assert "tenant=tx" in msg
