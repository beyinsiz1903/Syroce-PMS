"""Unit tests for GraphQL resolver defensive serialization (Task #216).

Covers the two production-observed crashes:
  * ``bookings[0].checkIn`` → ``'str' object has no attribute 'isoformat'``
    when ``check_in`` is stored as ISO string instead of BSON datetime.
  * ``rooms`` → ``'NoneType' object has no attribute 'get'`` when the
    GraphQL context exposes ``cache=None`` (current server.py bootstrap).

For each resolver three cases are exercised: (a) normal happy path,
(b) empty DB / cache result, (c) datetime-as-str edge case.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from graphql_api.schema import (
    BookingStatus,
    Query,
    RoomStatus,
    _safe_booking_status,
    _safe_datetime,
    _safe_get,
    _safe_room_status,
)


# ── _safe_datetime ────────────────────────────────────────────────────────
class TestSafeDatetime:
    def test_datetime_passthrough(self):
        now = datetime(2026, 5, 20, 12, 0, 0)
        assert _safe_datetime(now) is now

    def test_iso_string(self):
        out = _safe_datetime("2026-05-20T12:00:00")
        assert isinstance(out, datetime)
        assert out.year == 2026 and out.month == 5 and out.day == 20

    def test_iso_string_with_z_suffix(self):
        out = _safe_datetime("2026-05-20T12:00:00Z")
        assert isinstance(out, datetime)
        assert out.tzinfo is not None

    def test_iso_string_with_offset(self):
        out = _safe_datetime("2026-05-20T12:00:00+03:00")
        assert isinstance(out, datetime)

    def test_none_returns_none(self):
        assert _safe_datetime(None) is None

    def test_invalid_string_returns_none(self):
        assert _safe_datetime("not-a-date") is None

    def test_other_types_return_none(self):
        assert _safe_datetime(12345) is None
        assert _safe_datetime({"x": 1}) is None
        assert _safe_datetime([]) is None


# ── _safe_get ─────────────────────────────────────────────────────────────
class TestSafeGet:
    def test_dict_hit(self):
        assert _safe_get({"a": 1}, "a") == 1

    def test_dict_miss_default(self):
        assert _safe_get({"a": 1}, "b", 9) == 9

    def test_none_doc(self):
        assert _safe_get(None, "a", "fallback") == "fallback"

    def test_non_dict_doc(self):
        assert _safe_get("oops", "a", "fb") == "fb"
        assert _safe_get([1, 2], "a", "fb") == "fb"


# ── Enum coercion helpers ─────────────────────────────────────────────────
class TestStatusCoercion:
    def test_room_status_valid(self):
        assert _safe_room_status("dirty") == RoomStatus.DIRTY

    def test_room_status_unknown_falls_back(self):
        assert _safe_room_status("space-station") == RoomStatus.CLEAN

    def test_room_status_none_falls_back(self):
        assert _safe_room_status(None) == RoomStatus.CLEAN

    def test_booking_status_valid(self):
        assert _safe_booking_status("checked_in") == BookingStatus.CHECKED_IN

    def test_booking_status_unknown_falls_back(self):
        assert _safe_booking_status("???") == BookingStatus.PENDING


# ── Fake mongo + context plumbing ─────────────────────────────────────────
class _FakeCursor:
    def __init__(self, docs: list[Any]):
        self._docs = docs

    def skip(self, _n: int) -> "_FakeCursor":
        return self

    def limit(self, _n: int) -> "_FakeCursor":
        return self

    async def to_list(self, _n: int) -> list[Any]:
        return list(self._docs)


class _FakeCollection:
    def __init__(self, docs: list[Any]):
        self._docs = docs

    def find(self, _query: dict) -> _FakeCursor:
        return _FakeCursor(self._docs)


class _FakeDB:
    def __init__(self, bookings: list[Any] | None = None, rooms: list[Any] | None = None):
        self.bookings = _FakeCollection(bookings or [])
        self.rooms = _FakeCollection(rooms or [])


class _FakeInfo:
    """Minimal stand-in for ``strawberry.Info`` — only ``.context`` is used."""

    def __init__(self, context: dict):
        self.context = context


def _ctx(db: _FakeDB, *, cache: Any = None, mv: Any = None) -> _FakeInfo:
    return _FakeInfo({"db": db, "cache": cache, "materialized_views": mv})


# ── bookings resolver ─────────────────────────────────────────────────────
class TestBookingsResolver:
    @pytest.mark.asyncio
    async def test_normal_case(self):
        docs = [{
            "_id": "b1", "guest_id": "g1", "room_id": "r1",
            "check_in": datetime(2026, 5, 20), "check_out": datetime(2026, 5, 22),
            "status": "confirmed", "adults": 2, "children": 1,
            "total_amount": 500.0, "channel": "direct",
        }]
        result = await Query().bookings(_ctx(_FakeDB(bookings=docs)))
        assert len(result) == 1
        assert result[0].id == "b1"
        assert result[0].check_in == datetime(2026, 5, 20)
        assert result[0].status == BookingStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_empty_result(self):
        result = await Query().bookings(_ctx(_FakeDB(bookings=[])))
        assert result == []

    @pytest.mark.asyncio
    async def test_check_in_as_string_does_not_crash(self):
        """Regression: ``'str' object has no attribute 'isoformat'``."""
        docs = [{
            "_id": "b2", "guest_id": "g2", "room_id": "r2",
            "check_in": "2026-05-20T14:00:00",
            "check_out": "2026-05-22T11:00:00Z",
            "status": "pending",
        }]
        result = await Query().bookings(_ctx(_FakeDB(bookings=docs)))
        assert len(result) == 1
        assert isinstance(result[0].check_in, datetime)
        assert isinstance(result[0].check_out, datetime)
        assert result[0].check_out.tzinfo is not None

    @pytest.mark.asyncio
    async def test_unparseable_datetime_record_is_skipped(self):
        """Schema contract: check_in/check_out are non-null. Records with
        unparseable datetimes are skipped (not returned with null), so
        Strawberry never crashes on serialization."""
        good = {
            "_id": "ok", "guest_id": "g", "room_id": "r",
            "check_in": datetime(2026, 5, 20),
            "check_out": datetime(2026, 5, 21),
            "status": "pending",
        }
        bad = {
            "_id": "bad", "guest_id": "g", "room_id": "r",
            "check_in": "garbage-string", "check_out": None,
            "status": "pending",
        }
        result = await Query().bookings(_ctx(_FakeDB(bookings=[bad, good])))
        ids = [b.id for b in result]
        assert ids == ["ok"]

    @pytest.mark.asyncio
    async def test_partial_doc_without_dates_is_skipped(self):
        """Missing check_in/check_out → record skipped (non-null contract)."""
        docs = [{"_id": "b4"}]
        result = await Query().bookings(_ctx(_FakeDB(bookings=docs)))
        assert result == []

    @pytest.mark.asyncio
    async def test_non_dict_doc_is_skipped(self):
        good = {
            "_id": "ok", "guest_id": "g", "room_id": "r",
            "check_in": datetime(2026, 5, 20),
            "check_out": datetime(2026, 5, 21),
            "status": "pending",
        }
        docs: list[Any] = [None, "weird", good]
        result = await Query().bookings(_ctx(_FakeDB(bookings=docs)))
        assert len(result) == 1
        assert result[0].id == "ok"

    @pytest.mark.asyncio
    async def test_schema_contract_check_in_non_null(self):
        """Regression-guard the schema contract: Booking.check_in /
        check_out must remain non-null datetime fields (Task #216 review)."""
        from graphql_api.schema import Booking
        ann = Booking.__annotations__
        assert ann["check_in"] is datetime
        assert ann["check_out"] is datetime


# ── rooms resolver ────────────────────────────────────────────────────────
class TestRoomsResolver:
    @pytest.mark.asyncio
    async def test_normal_case_cache_none(self):
        """Regression: ``'NoneType' object has no attribute 'get'`` when
        ``cache`` is None in the GraphQL context (current server.py wiring).
        """
        docs = [{
            "_id": "r1", "room_number": "101", "room_type": "double",
            "floor": 1, "capacity": 2, "base_price": 100.0,
            "status": "clean", "amenities": ["wifi"],
        }]
        result = await Query().rooms(_ctx(_FakeDB(rooms=docs), cache=None))
        assert len(result) == 1
        assert result[0].room_number == "101"
        assert result[0].status == RoomStatus.CLEAN

    @pytest.mark.asyncio
    async def test_empty_result(self):
        result = await Query().rooms(_ctx(_FakeDB(rooms=[]), cache=None))
        assert result == []

    @pytest.mark.asyncio
    async def test_unknown_status_falls_back(self):
        docs = [{
            "_id": "r2", "room_number": "202", "room_type": "suite",
            "floor": 2, "capacity": 4, "base_price": 300.0,
            "status": "moon-base",
        }]
        result = await Query().rooms(_ctx(_FakeDB(rooms=docs), cache=None))
        assert result[0].status == RoomStatus.CLEAN

    @pytest.mark.asyncio
    async def test_partial_doc_does_not_crash(self):
        docs = [{"_id": "r3"}]
        result = await Query().rooms(_ctx(_FakeDB(rooms=docs), cache=None))
        assert len(result) == 1
        assert result[0].room_number == ""
        assert result[0].amenities == []

    @pytest.mark.asyncio
    async def test_none_and_non_dict_entries_skipped(self):
        docs: list[Any] = [None, 42, {"_id": "ok", "room_number": "1"}]
        result = await Query().rooms(_ctx(_FakeDB(rooms=docs), cache=None))
        assert len(result) == 1
        assert result[0].id == "ok"

    @pytest.mark.asyncio
    async def test_cache_read_exception_falls_through_to_db(self):
        class _BrokenCache:
            async def get(self, *_a, **_kw):
                raise RuntimeError("redis down")

            async def set(self, *_a, **_kw):
                raise RuntimeError("redis down")

        docs = [{"_id": "rx", "room_number": "9", "status": "dirty"}]
        result = await Query().rooms(_ctx(_FakeDB(rooms=docs), cache=_BrokenCache()))
        assert len(result) == 1
        assert result[0].status == RoomStatus.DIRTY


# ── dashboard resolvers (materialized_views=None safety) ──────────────────
class TestDashboardResolvers:
    @pytest.mark.asyncio
    async def test_dashboard_metrics_no_materialized_views(self):
        """Regression: avoid AttributeError when mv service is unwired."""
        result = await Query().dashboard_metrics(_ctx(_FakeDB(), mv=None))
        assert result.total_rooms == 0
        assert result.occupancy_rate == 0

    @pytest.mark.asyncio
    async def test_dashboard_trends_no_materialized_views(self):
        result = await Query().dashboard_trends(_ctx(_FakeDB(), mv=None))
        assert result is None

    @pytest.mark.asyncio
    async def test_dashboard_metrics_empty_view(self):
        class _MV:
            async def get_view(self, *_a, **_kw):
                return None

            async def refresh_dashboard_metrics(self):
                return None

        result = await Query().dashboard_metrics(_ctx(_FakeDB(), mv=_MV()))
        assert result.total_rooms == 0
