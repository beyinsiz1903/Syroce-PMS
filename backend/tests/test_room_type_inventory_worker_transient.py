"""Regression tests for RoomTypeInventoryWorker transient DB error handling.

Sentry production drop (pilot tenant):
    Reconciliation failed for tenant <tid>: No replica set members match
    selector "Primary()", Timeout: 3.0s
    ... NetworkTimeout('SSL handshake failed: ... timed out
    (configured timeouts: socketTimeoutMS: 20000.0ms, connectTimeoutMS: 5000.0ms)')

The 5-minute background worker must classify Atlas hiccups (no primary, SSL
handshake timeout, connection closed) as transient: log them at WARNING
(not ERROR) so Sentry stays clean, and let the next tick retry. Genuine
logic errors must still surface as ERROR.
"""
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import AutoReconnect, NetworkTimeout, ServerSelectionTimeoutError

from core import room_type_inventory_service as svc


class _FakeColl:
    def __init__(self, docs):
        self._docs = docs

    def find(self, *_a, **_kw):
        return self

    async def to_list(self, _n):
        return self._docs

    async def find_one(self, *_a, **_kw):
        return self._docs[0] if self._docs else None


class _FakeSysDB:
    def __init__(self, orgs, rooms=None):
        self.organizations = _FakeColl(orgs)
        self.rooms = _FakeColl(rooms or [])


@pytest.fixture(autouse=True)
def _silence_tenant_context(monkeypatch):
    from contextlib import contextmanager

    @contextmanager
    def _noop(_tid):
        yield

    monkeypatch.setattr(svc, "tenant_context", _noop)


async def _run_with_reconcile(monkeypatch, *, reconcile_impl, orgs=None):
    orgs = orgs if orgs is not None else [{"id": "t-pilot"}]
    monkeypatch.setattr(svc, "get_system_db", lambda: _FakeSysDB(orgs))
    monkeypatch.setattr(svc, "reconcile_date_range", reconcile_impl)
    worker = svc.RoomTypeInventoryWorker()
    await worker._run_once()


async def test_autoreconnect_logged_as_warning_not_error(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="core.room_type_inventory")
    reconcile = AsyncMock(side_effect=AutoReconnect("no primary"))
    await _run_with_reconcile(monkeypatch, reconcile_impl=reconcile)

    msgs = [(r.levelname, r.message) for r in caplog.records]
    assert any(lvl == "WARNING" and "transient db error" in msg for lvl, msg in msgs), msgs
    assert not any(lvl == "ERROR" for lvl, _ in msgs), msgs


async def test_server_selection_timeout_logged_as_warning(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="core.room_type_inventory")
    reconcile = AsyncMock(side_effect=ServerSelectionTimeoutError("3.0s"))
    await _run_with_reconcile(monkeypatch, reconcile_impl=reconcile)

    levels = [r.levelname for r in caplog.records]
    assert "WARNING" in levels
    assert "ERROR" not in levels


async def test_network_timeout_logged_as_warning(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="core.room_type_inventory")
    reconcile = AsyncMock(side_effect=NetworkTimeout("ssl handshake"))
    await _run_with_reconcile(monkeypatch, reconcile_impl=reconcile)

    assert any(r.levelname == "WARNING" for r in caplog.records)
    assert not any(r.levelname == "ERROR" for r in caplog.records)


async def test_oserror_connection_closed_logged_as_warning(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="core.room_type_inventory")
    reconcile = AsyncMock(side_effect=OSError("connection closed"))
    await _run_with_reconcile(monkeypatch, reconcile_impl=reconcile)

    assert any(r.levelname == "WARNING" for r in caplog.records)
    assert not any(r.levelname == "ERROR" for r in caplog.records)


async def test_non_transient_error_stays_at_error_level(monkeypatch, caplog):
    """Genuine bugs (ValueError, KeyError, ...) must still hit Sentry."""
    caplog.set_level(logging.WARNING, logger="core.room_type_inventory")
    reconcile = AsyncMock(side_effect=ValueError("bad date range"))
    await _run_with_reconcile(monkeypatch, reconcile_impl=reconcile)

    assert any(
        r.levelname == "ERROR" and "Reconciliation failed for tenant" in r.message
        for r in caplog.records
    )


async def test_one_transient_does_not_block_other_tenants(monkeypatch, caplog):
    """Per-tenant try/except: failure on tenant A must not skip tenant B."""
    caplog.set_level(logging.DEBUG, logger="core.room_type_inventory")
    call_order: list[str] = []

    async def _reconcile(tid, _start, _end):
        call_order.append(tid)
        if tid == "t-a":
            raise AutoReconnect("flap")
        return {"drift_detected": 0, "dates_processed": 1, "types_processed": 1}

    await _run_with_reconcile(
        monkeypatch,
        reconcile_impl=_reconcile,
        orgs=[{"id": "t-a"}, {"id": "t-b"}],
    )
    assert call_order == ["t-a", "t-b"]


async def test_successful_reconcile_logs_nothing_above_debug(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="core.room_type_inventory")
    reconcile = AsyncMock(return_value={
        "drift_detected": 0, "dates_processed": 31, "types_processed": 5,
    })
    await _run_with_reconcile(monkeypatch, reconcile_impl=reconcile)

    assert caplog.records == []


async def test_loop_transient_error_demoted_to_warning(monkeypatch, caplog):
    """Outer _loop try/except: transient error from _run_once → warning."""
    caplog.set_level(logging.WARNING, logger="core.room_type_inventory")

    worker = svc.RoomTypeInventoryWorker()
    worker._running = True
    worker._interval = 0  # tight loop

    iterations = {"n": 0}

    async def _run_once():
        iterations["n"] += 1
        if iterations["n"] == 1:
            raise AutoReconnect("no primary")
        worker._running = False  # stop after second iteration

    async def _no_sleep(_):
        return None

    monkeypatch.setattr(worker, "_run_once", _run_once)
    monkeypatch.setattr(svc.asyncio, "sleep", _no_sleep)

    await worker._loop()

    levels = [r.levelname for r in caplog.records]
    assert "WARNING" in levels
    assert "ERROR" not in levels


async def test_loop_non_transient_error_stays_at_error_level(monkeypatch, caplog):
    """Outer _loop try/except: real bugs (ValueError) must remain ERROR."""
    caplog.set_level(logging.WARNING, logger="core.room_type_inventory")

    worker = svc.RoomTypeInventoryWorker()
    worker._running = True
    worker._interval = 0

    iterations = {"n": 0}

    async def _run_once():
        iterations["n"] += 1
        if iterations["n"] == 1:
            raise ValueError("real bug in reconciler")
        worker._running = False

    async def _no_sleep(_):
        return None

    monkeypatch.setattr(worker, "_run_once", _run_once)
    monkeypatch.setattr(svc.asyncio, "sleep", _no_sleep)

    await worker._loop()

    levels = [r.levelname for r in caplog.records]
    assert "ERROR" in levels
    assert any("RoomTypeInventoryWorker error" in r.message for r in caplog.records)


def test_is_transient_db_error_classification():
    assert svc._is_transient_db_error(AutoReconnect("x"))
    assert svc._is_transient_db_error(NetworkTimeout("x"))
    assert svc._is_transient_db_error(ServerSelectionTimeoutError("x"))
    assert svc._is_transient_db_error(OSError("x"))
    assert svc._is_transient_db_error(ConnectionError("x"))
    assert not svc._is_transient_db_error(ValueError("x"))
    assert not svc._is_transient_db_error(KeyError("x"))
