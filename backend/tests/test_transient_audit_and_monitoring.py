"""Regression tests for transient DB error handling in two paths that
previously flooded Sentry during a pilot Atlas hiccup (no-primary / SSL
handshake timeout):

  * secret-access audit log writer (`core/secrets/audit.py`)
  * operational monitoring worker
    (`domains/channel_manager/monitoring/monitoring_worker.py`)

Both must classify Atlas hiccups as transient: WARNING below the streak
threshold, escalate to ERROR once sustained (so prolonged outages stay
visible), reset on success, and keep ERROR + traceback for genuine bugs.
"""
import logging
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import AutoReconnect

from core.secrets import audit as audit_mod
from core.secrets.audit import SecretAuditLogger
from core.transient_db_guard import TransientFailureTracker
from domains.channel_manager.monitoring import monitoring_worker as mw

_KEY = TransientFailureTracker.OUTER_LOOP_KEY


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------
class _FailingColl:
    def __init__(self, exc):
        self._exc = exc

    async def insert_one(self, _record):
        raise self._exc


class _OkColl:
    async def insert_one(self, _record):
        return None


class _FakeDB:
    def __init__(self, coll):
        self._coll = coll

    def __getitem__(self, _name):
        return self._coll


# --------------------------------------------------------------------------
# Fixtures — each test starts with clean module-level streak counters
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_trackers():
    audit_mod._transient_tracker._counts.clear()
    mw._transient_tracker._counts.clear()
    yield
    audit_mod._transient_tracker._counts.clear()
    mw._transient_tracker._counts.clear()


async def _audit_log(monkeypatch, logger_inst, coll):
    monkeypatch.setattr(logger_inst, "_get_db", lambda: _FakeDB(coll))
    await logger_inst.log("read", "some/secret/path", "success")


# --------------------------------------------------------------------------
# Secret audit log writer
# --------------------------------------------------------------------------
async def test_audit_transient_below_threshold_is_warning(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="core.secrets.audit")
    al = SecretAuditLogger()
    await _audit_log(monkeypatch, al, _FailingColl(AutoReconnect("no primary")))

    msgs = [(r.levelname, r.message) for r in caplog.records]
    assert any(lvl == "WARNING" and "transient db error" in msg for lvl, msg in msgs), msgs
    assert not any(lvl == "ERROR" for lvl, _ in msgs), msgs


async def test_audit_transient_escalates_to_error_at_threshold(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="core.secrets.audit")
    al = SecretAuditLogger()
    coll = _FailingColl(AutoReconnect("no primary"))
    for _ in range(audit_mod._transient_tracker.threshold):
        await _audit_log(monkeypatch, al, coll)

    levels = [r.levelname for r in caplog.records]
    assert "ERROR" in levels, levels
    assert levels.count("WARNING") == audit_mod._transient_tracker.threshold - 1, levels


async def test_audit_reset_on_success(monkeypatch):
    al = SecretAuditLogger()
    for _ in range(3):
        await _audit_log(monkeypatch, al, _FailingColl(AutoReconnect("x")))
    assert audit_mod._transient_tracker.streak(_KEY) == 3

    await _audit_log(monkeypatch, al, _OkColl())
    assert audit_mod._transient_tracker.streak(_KEY) == 0


async def test_audit_non_transient_is_error(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="core.secrets.audit")
    al = SecretAuditLogger()
    await _audit_log(monkeypatch, al, _FailingColl(ValueError("real bug")))

    levels = [r.levelname for r in caplog.records]
    assert "ERROR" in levels, levels
    # non-transient errors must not increment the transient streak
    assert audit_mod._transient_tracker.streak(_KEY) == 0


# --------------------------------------------------------------------------
# Operational monitoring worker
# --------------------------------------------------------------------------
async def test_monitoring_transient_below_threshold_is_warning(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="monitoring.worker")
    monkeypatch.setattr(mw, "collect_all_metrics", AsyncMock(side_effect=AutoReconnect("no primary")))

    result = await mw.monitoring_run_once()
    assert result["status"] == "error"

    msgs = [(r.levelname, r.message) for r in caplog.records]
    assert any(lvl == "WARNING" and "transient db error" in msg for lvl, msg in msgs), msgs
    assert not any(lvl == "ERROR" for lvl, _ in msgs), msgs


async def test_monitoring_transient_escalates_to_error_at_threshold(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="monitoring.worker")
    monkeypatch.setattr(mw, "collect_all_metrics", AsyncMock(side_effect=AutoReconnect("no primary")))

    for _ in range(mw._transient_tracker.threshold):
        await mw.monitoring_run_once()

    levels = [r.levelname for r in caplog.records]
    assert "ERROR" in levels, levels


async def test_monitoring_reset_on_success(monkeypatch):
    mw._transient_tracker._record(_KEY)
    mw._transient_tracker._record(_KEY)
    assert mw._transient_tracker.streak(_KEY) == 2

    monkeypatch.setattr(mw, "collect_all_metrics", AsyncMock(return_value={"system_health": "ok"}))
    monkeypatch.setattr(mw, "evaluate_alerts", AsyncMock(return_value=[]))
    monkeypatch.setattr(mw, "process_alerts", AsyncMock(return_value={"created": 0, "resolved": 0}))
    monkeypatch.setattr(mw, "_store_metrics_snapshot", AsyncMock(return_value=None))

    result = await mw.monitoring_run_once()
    assert result["status"] == "completed"
    assert mw._transient_tracker.streak(_KEY) == 0


async def test_monitoring_non_transient_is_error(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="monitoring.worker")
    monkeypatch.setattr(mw, "collect_all_metrics", AsyncMock(side_effect=ValueError("real bug")))

    await mw.monitoring_run_once()

    levels = [r.levelname for r in caplog.records]
    assert "ERROR" in levels, levels
    assert mw._transient_tracker.streak(_KEY) == 0
