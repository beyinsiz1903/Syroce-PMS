"""Regression tests for stress.cleanup transient DB error retry.

Sentry production drop (POST /api/admin/stress/cleanup):
    OSError: connection closed
    pymongo AutoReconnect: ac-...mongodb.net:27017: connection closed

The cleanup loop iterates over many STRESS_COLLECTIONS and calls delete_many.
A single transient Atlas drop in the middle of the loop must NOT 500 the
whole endpoint — the wrapper retries each call up to 4 times with
exponential backoff before propagating.
"""
from types import SimpleNamespace

import pytest
from pymongo.errors import AutoReconnect, NetworkTimeout, ServerSelectionTimeoutError

from domains.admin.router import stress as stress_mod


class _FlakyColl:
    """Fails N times with a transient error then succeeds."""
    def __init__(self, fail_times: int, exc: BaseException):
        self.fail_times = fail_times
        self.exc = exc
        self.calls = 0

    async def delete_many(self, _flt):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return SimpleNamespace(deleted_count=7)


class _AlwaysFailColl:
    def __init__(self, exc: BaseException):
        self.exc = exc
        self.calls = 0

    async def delete_many(self, _flt):
        self.calls += 1
        raise self.exc


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    async def _no_sleep(_):
        return None
    monkeypatch.setattr(stress_mod.asyncio, "sleep", _no_sleep)


async def test_retry_succeeds_after_transient_autoreconnect():
    col = _FlakyColl(fail_times=2, exc=AutoReconnect("conn closed"))
    res = await stress_mod._delete_many_with_retry(col, {}, col_name="bookings")
    assert res.deleted_count == 7
    assert col.calls == 3


async def test_retry_succeeds_after_oserror_connection_closed():
    col = _FlakyColl(fail_times=1, exc=OSError("connection closed"))
    res = await stress_mod._delete_many_with_retry(col, {}, col_name="folio_charges")
    assert res.deleted_count == 7
    assert col.calls == 2


async def test_retry_succeeds_after_network_timeout():
    col = _FlakyColl(fail_times=3, exc=NetworkTimeout("socket timeout"))
    res = await stress_mod._delete_many_with_retry(col, {}, col_name="guests")
    assert res.deleted_count == 7
    assert col.calls == 4


async def test_retry_exhausts_and_raises_original_error():
    col = _AlwaysFailColl(AutoReconnect("permanently down"))
    with pytest.raises(AutoReconnect):
        await stress_mod._delete_many_with_retry(col, {}, col_name="rooms")
    assert col.calls == 4


async def test_non_transient_error_is_not_retried():
    """ValueError (logic bug) must surface immediately — no retry hides it."""
    class _LogicBugColl:
        def __init__(self):
            self.calls = 0
        async def delete_many(self, _flt):
            self.calls += 1
            raise ValueError("bad filter")

    col = _LogicBugColl()
    with pytest.raises(ValueError):
        await stress_mod._delete_many_with_retry(col, {}, col_name="audit_logs")
    assert col.calls == 1


async def test_retry_succeeds_after_server_selection_timeout():
    col = _FlakyColl(fail_times=1, exc=ServerSelectionTimeoutError("no primary"))
    res = await stress_mod._delete_many_with_retry(col, {}, col_name="payments")
    assert res.deleted_count == 7
    assert col.calls == 2


async def test_retry_backoff_schedule_locked(monkeypatch):
    """Lock the documented backoff cadence (0.25 -> 0.5 -> 1.0) against drift."""
    sleeps: list[float] = []

    async def _record_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(stress_mod.asyncio, "sleep", _record_sleep)
    col = _FlakyColl(fail_times=3, exc=AutoReconnect("flap"))
    await stress_mod._delete_many_with_retry(col, {}, col_name="invoices")
    assert sleeps == [0.25, 0.5, 1.0]


async def test_first_call_succeeds_no_retry_overhead():
    class _OkColl:
        def __init__(self):
            self.calls = 0
        async def delete_many(self, _flt):
            self.calls += 1
            return SimpleNamespace(deleted_count=42)

    col = _OkColl()
    res = await stress_mod._delete_many_with_retry(col, {}, col_name="reservations")
    assert res.deleted_count == 42
    assert col.calls == 1
