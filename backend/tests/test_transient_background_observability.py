"""Regression coverage for background Atlas failover handling."""

from __future__ import annotations

import logging

import pytest
from pymongo.errors import AutoReconnect


def test_hold_sweeper_demotes_first_atlas_failover(monkeypatch, caplog):
    from core import booking_hold_service as holds
    from core.transient_db_guard import TransientFailureTracker

    tracker = TransientFailureTracker("test-hold", threshold=3)
    monkeypatch.setattr(holds, "_sweeper_failures", tracker)
    caplog.set_level(logging.DEBUG, logger="core.booking_hold")

    holds._record_sweeper_error(AutoReconnect("primary election"))

    assert tracker.streak(TransientFailureTracker.OUTER_LOOP_KEY) == 1
    assert caplog.records[-1].levelname == "WARNING"
    assert "booking-hold-sweeper" not in caplog.records[-1].getMessage()


@pytest.mark.asyncio
async def test_trace_flush_demotes_first_atlas_failover(monkeypatch, caplog):
    from core import database
    from modules.observability.distributed_tracing import TracingService

    class TraceCollection:
        async def insert_many(self, _docs):
            raise AutoReconnect("primary election")

    class FakeDatabase:
        observability_traces = TraceCollection()

    service = TracingService()
    service._completed_traces.append({"trace_id": "trace-1"})
    monkeypatch.setattr(database, "db", FakeDatabase())
    caplog.set_level(logging.DEBUG, logger="observability.tracing")

    assert await service.flush_to_db() == 0
    assert service._completed_traces == [{"trace_id": "trace-1"}]
    assert service._flush_failures.streak("__loop__") == 1
    assert caplog.records[-1].levelname == "WARNING"
