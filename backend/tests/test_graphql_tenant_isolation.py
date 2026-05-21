"""Unit tests for GraphQL tenant isolation (Task #256).

Task #254 closed a GraphQL cross-tenant leak by adding explicit
``tenant_id`` filters to the ``bookings`` / ``rooms`` resolvers (plus
nested ``Booking.guest`` / ``Booking.room``) and by scoping the rooms
cache key per-tenant. These tests pin that behavior so a future
resolver change cannot silently regress.

Guarantees verified here:
  * Two tenants querying the same resolver receive only their own docs.
  * Cache populated by tenant A is NOT served to tenant B (cache key is
    tenant-scoped).
  * When ``tenant_id`` is missing from the GraphQL context, every
    resolver returns an empty list / None instead of falling back to an
    unscoped read.
  * Nested ``Booking.guest`` / ``Booking.room`` resolvers refuse to load
    a doc whose ``tenant_id`` does not match the request context.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from graphql_api.schema import Booking, Query


# ── Fake mongo plumbing ───────────────────────────────────────────────────
class _FakeCursor:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    def skip(self, _n: int) -> "_FakeCursor":
        return self

    def limit(self, _n: int) -> "_FakeCursor":
        return self

    async def to_list(self, _n: int) -> list[dict]:
        return list(self._docs)


class _TenantFilteredCollection:
    """Mimics motor: ``find(query)`` honors the ``tenant_id`` filter; a
    resolver that forgets the filter would see every tenant's docs.
    """

    def __init__(self, docs: list[dict]):
        self._docs = docs
        self.last_query: dict | None = None

    def find(self, query: dict) -> _FakeCursor:
        self.last_query = dict(query)
        matched = [
            d for d in self._docs
            if all(d.get(k) == v for k, v in query.items())
        ]
        return _FakeCursor(matched)

    async def find_one(self, query: dict) -> dict | None:
        self.last_query = dict(query)
        for d in self._docs:
            if all(d.get(k) == v for k, v in query.items()):
                return d
        return None


class _FakeDB:
    def __init__(
        self,
        bookings: list[dict] | None = None,
        rooms: list[dict] | None = None,
        guests: list[dict] | None = None,
    ):
        self.bookings = _TenantFilteredCollection(bookings or [])
        self.rooms = _TenantFilteredCollection(rooms or [])
        self.guests = _TenantFilteredCollection(guests or [])


class _FakeInfo:
    def __init__(self, context: dict):
        self.context = context


def _ctx(db: _FakeDB, *, tenant_id: str | None, cache: Any = None) -> _FakeInfo:
    return _FakeInfo({
        "db": db,
        "cache": cache,
        "materialized_views": None,
        "tenant_id": tenant_id,
    })


# ── Fixtures: two-tenant dataset ──────────────────────────────────────────
def _make_db() -> _FakeDB:
    bookings = [
        {
            "_id": f"b-{tid}-{i}", "tenant_id": tid,
            "guest_id": f"g-{tid}-{i}", "room_id": f"r-{tid}-{i}",
            "check_in": datetime(2026, 5, 20),
            "check_out": datetime(2026, 5, 22),
            "status": "confirmed", "adults": 2, "children": 0,
            "total_amount": 100.0, "channel": "direct",
        }
        for tid in ("tenant-A", "tenant-B")
        for i in (1, 2)
    ]
    rooms = [
        {
            "_id": f"r-{tid}-{i}", "tenant_id": tid,
            "room_number": f"{tid[-1]}0{i}", "room_type": "double",
            "floor": 1, "capacity": 2, "base_price": 100.0,
            "status": "clean", "amenities": [],
        }
        for tid in ("tenant-A", "tenant-B")
        for i in (1, 2)
    ]
    guests = [
        {
            "_id": f"g-{tid}-{i}", "tenant_id": tid,
            "name": f"Guest {tid} {i}", "email": f"{tid}{i}@x.test",
        }
        for tid in ("tenant-A", "tenant-B")
        for i in (1, 2)
    ]
    return _FakeDB(bookings=bookings, rooms=rooms, guests=guests)


# ── bookings resolver ────────────────────────────────────────────────────
class TestBookingsTenantIsolation:
    @pytest.mark.asyncio
    async def test_each_tenant_sees_only_own_bookings(self):
        db = _make_db()

        a = await Query().bookings(_ctx(db, tenant_id="tenant-A"))
        b = await Query().bookings(_ctx(db, tenant_id="tenant-B"))

        assert {x.id for x in a} == {"b-tenant-A-1", "b-tenant-A-2"}
        assert {x.id for x in b} == {"b-tenant-B-1", "b-tenant-B-2"}
        # The mongo-level query MUST carry the tenant_id filter.
        assert db.bookings.last_query is not None
        assert db.bookings.last_query.get("tenant_id") == "tenant-B"

    @pytest.mark.asyncio
    async def test_missing_tenant_id_returns_empty(self):
        db = _make_db()
        result = await Query().bookings(_ctx(db, tenant_id=None))
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_string_tenant_id_returns_empty(self):
        db = _make_db()
        result = await Query().bookings(_ctx(db, tenant_id=""))
        assert result == []


# ── rooms resolver ───────────────────────────────────────────────────────
class TestRoomsTenantIsolation:
    @pytest.mark.asyncio
    async def test_each_tenant_sees_only_own_rooms(self):
        db = _make_db()

        a = await Query().rooms(_ctx(db, tenant_id="tenant-A"))
        b = await Query().rooms(_ctx(db, tenant_id="tenant-B"))

        assert {x.id for x in a} == {"r-tenant-A-1", "r-tenant-A-2"}
        assert {x.id for x in b} == {"r-tenant-B-1", "r-tenant-B-2"}
        assert db.rooms.last_query is not None
        assert db.rooms.last_query.get("tenant_id") == "tenant-B"

    @pytest.mark.asyncio
    async def test_missing_tenant_id_returns_empty(self):
        db = _make_db()
        result = await Query().rooms(_ctx(db, tenant_id=None))
        assert result == []

    @pytest.mark.asyncio
    async def test_cache_key_is_tenant_scoped(self):
        """Regression: cache populated by tenant A must NOT leak to
        tenant B. A shared in-memory cache exercises the key scoping.
        """
        class _MemCache:
            def __init__(self):
                self.store: dict = {}

            async def get(self, key: str, _tier: str):
                return self.store.get(key)

            async def set(self, key: str, value: Any, _tier: str):
                self.store[key] = value

        cache = _MemCache()
        db = _make_db()

        a = await Query().rooms(_ctx(db, tenant_id="tenant-A", cache=cache))
        assert {x.id for x in a} == {"r-tenant-A-1", "r-tenant-A-2"}
        # Tenant A populated the cache; tenant B must still get its own
        # docs from DB (different cache key) — not A's cached rooms.
        b = await Query().rooms(_ctx(db, tenant_id="tenant-B", cache=cache))
        assert {x.id for x in b} == {"r-tenant-B-1", "r-tenant-B-2"}
        # Both tenants now have separate cache entries.
        keys = list(cache.store.keys())
        assert any("tenant-A" in k for k in keys)
        assert any("tenant-B" in k for k in keys)
        # No cache key may contain BOTH tenant ids.
        for k in keys:
            assert not ("tenant-A" in k and "tenant-B" in k)


# ── nested Booking.guest / Booking.room resolvers ────────────────────────
class TestNestedResolverTenantIsolation:
    @pytest.mark.asyncio
    async def test_guest_resolver_refuses_other_tenant(self):
        db = _make_db()
        # Booking belongs to tenant-A but request context is tenant-B.
        bk = Booking(
            id="b-tenant-A-1", guest_id="g-tenant-A-1", room_id="r-tenant-A-1",
            check_in=datetime(2026, 5, 20), check_out=datetime(2026, 5, 22),
            status=__import__(
                "graphql_api.schema", fromlist=["BookingStatus"]
            ).BookingStatus.CONFIRMED,
            adults=1, children=0, total_amount=1.0, channel="direct",
        )
        out = await bk.guest(_ctx(db, tenant_id="tenant-B"))
        assert out is None
        # Sanity: same query under tenant-A returns the guest.
        out_ok = await bk.guest(_ctx(db, tenant_id="tenant-A"))
        assert out_ok is not None and out_ok.id == "g-tenant-A-1"

    @pytest.mark.asyncio
    async def test_room_resolver_refuses_other_tenant(self):
        db = _make_db()
        bk = Booking(
            id="b-tenant-A-1", guest_id="g-tenant-A-1", room_id="r-tenant-A-1",
            check_in=datetime(2026, 5, 20), check_out=datetime(2026, 5, 22),
            status=__import__(
                "graphql_api.schema", fromlist=["BookingStatus"]
            ).BookingStatus.CONFIRMED,
            adults=1, children=0, total_amount=1.0, channel="direct",
        )
        out = await bk.room(_ctx(db, tenant_id="tenant-B"))
        assert out is None
        out_ok = await bk.room(_ctx(db, tenant_id="tenant-A"))
        assert out_ok is not None and out_ok.id == "r-tenant-A-1"

    @pytest.mark.asyncio
    async def test_nested_resolvers_without_tenant_return_none(self):
        db = _make_db()
        bk = Booking(
            id="b-tenant-A-1", guest_id="g-tenant-A-1", room_id="r-tenant-A-1",
            check_in=datetime(2026, 5, 20), check_out=datetime(2026, 5, 22),
            status=__import__(
                "graphql_api.schema", fromlist=["BookingStatus"]
            ).BookingStatus.CONFIRMED,
            adults=1, children=0, total_amount=1.0, channel="direct",
        )
        assert await bk.guest(_ctx(db, tenant_id=None)) is None
        assert await bk.room(_ctx(db, tenant_id=None)) is None
