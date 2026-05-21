"""
GraphQL Schema for Hotel PMS
Optimized field-level queries for frontend performance
"""
from datetime import datetime
from enum import Enum
from typing import Any

import strawberry


def _safe_datetime(value: Any) -> datetime | None:
    """Defensive datetime coercion for GraphQL resolvers.

    MongoDB documents may hold a check_in/check_out as a real ``datetime``
    (BSON Date) OR as an ISO-8601 string (legacy imports, channel-manager
    pulls that store wire format, or fixtures that serialize before insert).
    Strawberry's serializer calls ``.isoformat()`` on the field value, so a
    bare ``str`` triggers ``'str' object has no attribute 'isoformat'`` and
    the whole resolver returns an error (Task #216).

    Behavior:
      * ``datetime`` → returned as-is
      * ``str`` → parsed with ``fromisoformat`` (handles trailing ``Z`` as UTC)
      * anything else (None, int, dict) → ``None`` so the caller can decide
        to skip the field instead of crashing the whole list resolver
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            s = value.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s)
        except (ValueError, TypeError):
            return None
    return None


def _safe_get(doc: Any, key: str, default: Any = None) -> Any:
    """``dict.get`` that tolerates ``None`` / non-dict docs.

    Resolvers occasionally receive ``None`` from cache misses, partial
    materialized-view payloads, or documents that fail validation downstream.
    Without this guard, ``result.get(...)`` raises
    ``'NoneType' object has no attribute 'get'`` (Task #216).
    """
    if doc is None or not isinstance(doc, dict):
        return default
    return doc.get(key, default)


def _safe_room_status(value: Any) -> "RoomStatus":
    """Coerce a string to ``RoomStatus``; fall back to ``CLEAN`` on unknown."""
    try:
        return RoomStatus(value) if value is not None else RoomStatus.CLEAN
    except ValueError:
        return RoomStatus.CLEAN


def _safe_booking_status(value: Any) -> "BookingStatus":
    """Coerce a string to ``BookingStatus``; fall back to ``PENDING``."""
    try:
        return BookingStatus(value) if value is not None else BookingStatus.PENDING
    except ValueError:
        return BookingStatus.PENDING


# Enums
@strawberry.enum
class BookingStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"

@strawberry.enum
class RoomStatus(Enum):
    CLEAN = "clean"
    DIRTY = "dirty"
    INSPECTED = "inspected"
    OUT_OF_ORDER = "out_of_order"

# Types
@strawberry.type
class Room:
    id: str
    room_number: str
    room_type: str
    floor: int
    capacity: int
    base_price: float
    status: RoomStatus
    amenities: list[str]

@strawberry.type
class Guest:
    id: str
    name: str
    email: str
    phone: str | None = None
    id_number: str | None = None
    tags: list[str] | None = None

@strawberry.type
class Booking:
    id: str
    guest_id: str
    room_id: str
    check_in: datetime
    check_out: datetime
    status: BookingStatus
    adults: int
    children: int
    total_amount: float
    channel: str

    @strawberry.field
    async def guest(self, info: strawberry.Info) -> Guest | None:
        """Lazy load guest data.

        Task #254 (F8M § 40 P1): explicit tenant_id filter — even if the
        TenantAwareDBProxy context isn't set, the nested resolver MUST NOT
        load a guest from another tenant. Filter is additive; UNKNOWN tenant
        -> None.
        """
        db = info.context["db"]
        tenant_id = info.context.get("tenant_id")
        if not tenant_id:
            return None
        guest_doc = await db.guests.find_one({"_id": self.guest_id, "tenant_id": tenant_id})
        if not guest_doc or not isinstance(guest_doc, dict):
            return None
        return Guest(
            id=str(_safe_get(guest_doc, "_id", "")),
            name=_safe_get(guest_doc, "name", "") or "",
            email=_safe_get(guest_doc, "email", "") or "",
            phone=_safe_get(guest_doc, "phone"),
            id_number=_safe_get(guest_doc, "id_number"),
            tags=_safe_get(guest_doc, "tags", []) or [],
        )

    @strawberry.field
    async def room(self, info: strawberry.Info) -> Room | None:
        """Lazy load room data.

        Task #254: explicit tenant_id filter (see Booking.guest docstring).
        """
        db = info.context["db"]
        tenant_id = info.context.get("tenant_id")
        if not tenant_id:
            return None
        room_doc = await db.rooms.find_one({"_id": self.room_id, "tenant_id": tenant_id})
        if not room_doc or not isinstance(room_doc, dict):
            return None
        return Room(
            id=str(_safe_get(room_doc, "_id", "")),
            room_number=_safe_get(room_doc, "room_number", "") or "",
            room_type=_safe_get(room_doc, "room_type", "") or "",
            floor=_safe_get(room_doc, "floor", 0) or 0,
            capacity=_safe_get(room_doc, "capacity", 0) or 0,
            base_price=_safe_get(room_doc, "base_price", 0) or 0,
            status=_safe_room_status(_safe_get(room_doc, "status", "clean")),
            amenities=_safe_get(room_doc, "amenities", []) or [],
        )

@strawberry.type
class DashboardMetrics:
    occupancy_rate: float
    occupied_rooms: int
    total_rooms: int
    available_rooms: int
    today_arrivals: int
    today_departures: int
    today_revenue: float
    adr: float
    revpar: float

@strawberry.type
class OccupancyTrend:
    date: str
    occupancy: float
    occupied_rooms: int

@strawberry.type
class RevenueTrend:
    date: str
    revenue: float

@strawberry.type
class DashboardTrends:
    weekly_occupancy: list[OccupancyTrend]
    monthly_revenue: list[RevenueTrend]

# Input types for mutations
@strawberry.input
class BookingFilter:
    status: BookingStatus | None = None
    check_in_from: datetime | None = None
    check_in_to: datetime | None = None
    guest_id: str | None = None
    room_id: str | None = None
    limit: int = 100
    skip: int = 0

@strawberry.input
class RoomFilter:
    status: RoomStatus | None = None
    room_type: str | None = None
    floor: int | None = None
    min_capacity: int | None = None
    limit: int = 100
    skip: int = 0

# Queries
@strawberry.type
class Query:
    @strawberry.field
    async def dashboard_metrics(self, info: strawberry.Info) -> DashboardMetrics:
        """Get pre-computed dashboard metrics from materialized views.

        Defensive: ``materialized_views`` may be ``None`` in environments
        where the materialized-view service is not wired into the GraphQL
        context (e.g. current server.py bootstrap). In that case we return
        a zeroed metrics payload instead of raising
        ``'NoneType' object has no attribute 'get_view'``.
        """
        empty = DashboardMetrics(
            occupancy_rate=0, occupied_rooms=0, total_rooms=0,
            available_rooms=0, today_arrivals=0, today_departures=0,
            today_revenue=0, adr=0, revpar=0,
        )
        materialized_views = info.context.get("materialized_views")
        if materialized_views is None:
            return empty

        metrics = await materialized_views.get_view("dashboard_metrics", max_age_seconds=60)
        if not metrics:
            await materialized_views.refresh_dashboard_metrics()
            metrics = await materialized_views.get_view("dashboard_metrics", max_age_seconds=60)
        if not metrics:
            return empty

        occ = _safe_get(metrics, "occupancy", {}) or {}
        today = _safe_get(metrics, "today", {}) or {}
        financial = _safe_get(metrics, "financial", {}) or {}

        return DashboardMetrics(
            occupancy_rate=_safe_get(occ, "rate", 0) or 0,
            occupied_rooms=_safe_get(occ, "occupied_rooms", 0) or 0,
            total_rooms=_safe_get(occ, "total_rooms", 0) or 0,
            available_rooms=_safe_get(occ, "available_rooms", 0) or 0,
            today_arrivals=_safe_get(today, "arrivals", 0) or 0,
            today_departures=_safe_get(today, "departures", 0) or 0,
            today_revenue=_safe_get(today, "revenue", 0) or 0,
            adr=_safe_get(financial, "adr", 0) or 0,
            revpar=_safe_get(financial, "revpar", 0) or 0,
        )

    @strawberry.field
    async def dashboard_trends(self, info: strawberry.Info) -> DashboardTrends | None:
        """Get dashboard trends from materialized views.

        Defensive: returns ``None`` when materialized_views service is not
        configured in the context, instead of attribute-erroring.
        """
        materialized_views = info.context.get("materialized_views")
        if materialized_views is None:
            return None

        metrics = await materialized_views.get_view("dashboard_metrics", max_age_seconds=300)
        if not metrics:
            return None

        trends = _safe_get(metrics, "trends", {}) or {}

        weekly_occ = [
            OccupancyTrend(
                date=_safe_get(item, "date", "") or "",
                occupancy=_safe_get(item, "occupancy", 0) or 0,
                occupied_rooms=_safe_get(item, "occupied_rooms", 0) or 0,
            )
            for item in (_safe_get(trends, "weekly_occupancy", []) or [])
            if isinstance(item, dict)
        ]

        monthly_rev = [
            RevenueTrend(
                date=_safe_get(item, "date", "") or "",
                revenue=_safe_get(item, "revenue", 0) or 0,
            )
            for item in (_safe_get(trends, "monthly_revenue", []) or [])
            if isinstance(item, dict)
        ]

        return DashboardTrends(
            weekly_occupancy=weekly_occ,
            monthly_revenue=monthly_rev,
        )

    @strawberry.field
    async def bookings(
        self,
        info: strawberry.Info,
        filter: BookingFilter | None = None
    ) -> list[Booking]:
        """Get bookings with optional filtering.

        Defensive: each booking doc may have ``check_in``/``check_out``
        stored as ISO string (legacy/import path) or BSON datetime. The
        previous resolver assumed datetime and crashed on str. Now both
        are coerced via ``_safe_datetime``; unparseable values become
        ``None`` instead of failing the whole query.
        """
        db = info.context["db"]
        tenant_id = info.context.get("tenant_id")
        # Task #254 (F8M § 40 P1): explicit tenant_id filter. Without
        # tenant context the resolver MUST return empty rather than
        # potentially fall back to an unscoped read.
        if not tenant_id:
            return []

        query: dict = {"tenant_id": tenant_id}
        if filter:
            if filter.status:
                query["status"] = filter.status.value
            if filter.guest_id:
                query["guest_id"] = filter.guest_id
            if filter.room_id:
                query["room_id"] = filter.room_id
            if filter.check_in_from or filter.check_in_to:
                query["check_in"] = {}
                if filter.check_in_from:
                    query["check_in"]["$gte"] = filter.check_in_from
                if filter.check_in_to:
                    query["check_in"]["$lte"] = filter.check_in_to

        limit = filter.limit if filter else 100
        skip = filter.skip if filter else 0

        cursor = db.bookings.find(query).skip(skip).limit(limit)
        bookings = await cursor.to_list(limit)
        if not bookings:
            return []

        result: list[Booking] = []
        for b in bookings:
            if not isinstance(b, dict):
                continue
            ci = _safe_datetime(_safe_get(b, "check_in"))
            co = _safe_datetime(_safe_get(b, "check_out"))
            # Schema contract: check_in/check_out are non-null datetime fields.
            # Records with unparseable / missing datetimes are skipped rather
            # than returned with null (which would either break the contract
            # or require a schema change). This preserves the resolver from
            # the Task #216 crashes while keeping the public API stable.
            if ci is None or co is None:
                continue
            result.append(Booking(
                id=str(_safe_get(b, "_id", "")),
                guest_id=str(_safe_get(b, "guest_id", "") or ""),
                room_id=str(_safe_get(b, "room_id", "") or ""),
                check_in=ci,
                check_out=co,
                status=_safe_booking_status(_safe_get(b, "status", "pending")),
                adults=_safe_get(b, "adults", 1) or 1,
                children=_safe_get(b, "children", 0) or 0,
                total_amount=_safe_get(b, "total_amount", 0) or 0,
                channel=_safe_get(b, "channel", "direct") or "direct",
            ))
        return result

    @strawberry.field
    async def rooms(
        self,
        info: strawberry.Info,
        filter: RoomFilter | None = None
    ) -> list[Room]:
        """Get rooms with optional filtering.

        Defensive:
          * ``cache`` may be ``None`` (current server.py bootstrap passes
            ``None``). Previously this caused
            ``'NoneType' object has no attribute 'get'``. Now cache is
            treated as best-effort and silently bypassed when missing.
          * DB cursor results / cached entries that are ``None`` or
            non-dict are skipped rather than crashing the resolver.
        """
        db = info.context["db"]
        cache = info.context.get("cache")
        tenant_id = info.context.get("tenant_id")
        # Task #254 (F8M § 40 P1): explicit tenant_id filter. Without
        # tenant context the resolver MUST return empty.
        if not tenant_id:
            return []

        # Task #254: cache key MUST be tenant-scoped, otherwise the first
        # tenant to populate the cache leaks rooms to every subsequent
        # tenant that queries with the same filter shape.
        cache_key = f"rooms:{tenant_id}:{filter}" if filter else f"rooms:{tenant_id}:all"
        cached = None
        if cache is not None:
            try:
                cached = await cache.get(cache_key, "L2")
            except Exception:
                # Cache read failures must never break the resolver — fall
                # through to DB read.
                cached = None
        if cached:
            out: list[Room] = []
            for r in cached:
                if not isinstance(r, dict):
                    continue
                out.append(Room(
                    id=_safe_get(r, "id", "") or "",
                    room_number=_safe_get(r, "room_number", "") or "",
                    room_type=_safe_get(r, "room_type", "") or "",
                    floor=_safe_get(r, "floor", 0) or 0,
                    capacity=_safe_get(r, "capacity", 0) or 0,
                    base_price=_safe_get(r, "base_price", 0) or 0,
                    status=_safe_room_status(_safe_get(r, "status", "clean")),
                    amenities=_safe_get(r, "amenities", []) or [],
                ))
            return out

        # Task #254 (F8M § 40 P1): explicit tenant_id filter.
        query: dict = {"tenant_id": tenant_id}
        if filter:
            if filter.status:
                query["status"] = filter.status.value
            if filter.room_type:
                query["room_type"] = filter.room_type
            if filter.floor:
                query["floor"] = filter.floor
            if filter.min_capacity:
                query["capacity"] = {"$gte": filter.min_capacity}

        limit = filter.limit if filter else 100
        skip = filter.skip if filter else 0

        cursor = db.rooms.find(query).skip(skip).limit(limit)
        rooms = await cursor.to_list(limit)
        if not rooms:
            return []

        result: list[Room] = []
        for r in rooms:
            if not isinstance(r, dict):
                continue
            result.append(Room(
                id=str(_safe_get(r, "_id", "")),
                room_number=_safe_get(r, "room_number", "") or "",
                room_type=_safe_get(r, "room_type", "") or "",
                floor=_safe_get(r, "floor", 0) or 0,
                capacity=_safe_get(r, "capacity", 0) or 0,
                base_price=_safe_get(r, "base_price", 0) or 0,
                status=_safe_room_status(_safe_get(r, "status", "clean")),
                amenities=_safe_get(r, "amenities", []) or [],
            ))

        if cache is not None:
            try:
                cache_data = [
                    {
                        "id": r.id,
                        "room_number": r.room_number,
                        "room_type": r.room_type,
                        "floor": r.floor,
                        "capacity": r.capacity,
                        "base_price": r.base_price,
                        "status": r.status.value,
                        "amenities": r.amenities,
                    }
                    for r in result
                ]
                await cache.set(cache_key, cache_data, "L2")
            except Exception:
                # Cache write failures must never break the resolver.
                pass

        return result

# Schema
from strawberry.extensions import QueryDepthLimiter

schema = strawberry.Schema(
    query=Query,
    extensions=[QueryDepthLimiter(max_depth=10)],
)
