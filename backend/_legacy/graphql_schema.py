"""
GraphQL Schema for Hotel PMS
Optimized field-level queries for frontend performance
"""
import strawberry
from typing import List, Optional
from datetime import datetime
from enum import Enum

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
    amenities: List[str]

@strawberry.type
class Guest:
    id: str
    name: str
    email: str
    phone: Optional[str] = None
    id_number: Optional[str] = None
    tags: Optional[List[str]] = None

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
    async def guest(self, info) -> Optional[Guest]:
        """Lazy load guest data"""
        db = info.context["db"]
        guest_doc = await db.guests.find_one({"_id": self.guest_id})
        if guest_doc:
            return Guest(
                id=str(guest_doc["_id"]),
                name=guest_doc["name"],
                email=guest_doc["email"],
                phone=guest_doc.get("phone"),
                id_number=guest_doc.get("id_number"),
                tags=guest_doc.get("tags", [])
            )
        return None
    
    @strawberry.field
    async def room(self, info) -> Optional[Room]:
        """Lazy load room data"""
        db = info.context["db"]
        room_doc = await db.rooms.find_one({"_id": self.room_id})
        if room_doc:
            return Room(
                id=str(room_doc["_id"]),
                room_number=room_doc["room_number"],
                room_type=room_doc["room_type"],
                floor=room_doc["floor"],
                capacity=room_doc["capacity"],
                base_price=room_doc["base_price"],
                status=RoomStatus(room_doc.get("status", "clean")),
                amenities=room_doc.get("amenities", [])
            )
        return None

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
    weekly_occupancy: List[OccupancyTrend]
    monthly_revenue: List[RevenueTrend]

# Input types for mutations
@strawberry.input
class BookingFilter:
    status: Optional[BookingStatus] = None
    check_in_from: Optional[datetime] = None
    check_in_to: Optional[datetime] = None
    guest_id: Optional[str] = None
    room_id: Optional[str] = None
    limit: int = 100
    skip: int = 0

@strawberry.input
class RoomFilter:
    status: Optional[RoomStatus] = None
    room_type: Optional[str] = None
    floor: Optional[int] = None
    min_capacity: Optional[int] = None
    limit: int = 100
    skip: int = 0

# Queries
@strawberry.type
class Query:
    @strawberry.field
    async def dashboard_metrics(self, info) -> DashboardMetrics:
        """Get pre-computed dashboard metrics from materialized views"""
        materialized_views = info.context["materialized_views"]
        metrics = await materialized_views.get_view("dashboard_metrics", max_age_seconds=60)
        
        if not metrics:
            # Fallback: refresh and get
            await materialized_views.refresh_dashboard_metrics()
            metrics = await materialized_views.get_view("dashboard_metrics", max_age_seconds=60)
        
        if not metrics:
            # Return empty metrics
            return DashboardMetrics(
                occupancy_rate=0,
                occupied_rooms=0,
                total_rooms=0,
                available_rooms=0,
                today_arrivals=0,
                today_departures=0,
                today_revenue=0,
                adr=0,
                revpar=0
            )
        
        occ = metrics.get("occupancy", {})
        today = metrics.get("today", {})
        financial = metrics.get("financial", {})
        
        return DashboardMetrics(
            occupancy_rate=occ.get("rate", 0),
            occupied_rooms=occ.get("occupied_rooms", 0),
            total_rooms=occ.get("total_rooms", 0),
            available_rooms=occ.get("available_rooms", 0),
            today_arrivals=today.get("arrivals", 0),
            today_departures=today.get("departures", 0),
            today_revenue=today.get("revenue", 0),
            adr=financial.get("adr", 0),
            revpar=financial.get("revpar", 0)
        )
    
    @strawberry.field
    async def dashboard_trends(self, info) -> Optional[DashboardTrends]:
        """Get dashboard trends from materialized views"""
        materialized_views = info.context["materialized_views"]
        metrics = await materialized_views.get_view("dashboard_metrics", max_age_seconds=300)
        
        if not metrics:
            return None
        
        trends = metrics.get("trends", {})
        
        weekly_occ = [
            OccupancyTrend(
                date=item["date"],
                occupancy=item["occupancy"],
                occupied_rooms=item["occupied_rooms"]
            )
            for item in trends.get("weekly_occupancy", [])
        ]
        
        monthly_rev = [
            RevenueTrend(
                date=item["date"],
                revenue=item["revenue"]
            )
            for item in trends.get("monthly_revenue", [])
        ]
        
        return DashboardTrends(
            weekly_occupancy=weekly_occ,
            monthly_revenue=monthly_rev
        )
    
    @strawberry.field
    async def bookings(
        self,
        info,
        filter: Optional[BookingFilter] = None
    ) -> List[Booking]:
        """Get bookings with optional filtering"""
        db = info.context["db"]
        
        # Build query
        query = {}
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
        
        # Query database
        cursor = db.bookings.find(query).skip(skip).limit(limit)
        bookings = await cursor.to_list(limit)
        
        return [
            Booking(
                id=str(b["_id"]),
                guest_id=str(b["guest_id"]),
                room_id=str(b["room_id"]),
                check_in=b["check_in"],
                check_out=b["check_out"],
                status=BookingStatus(b["status"]),
                adults=b.get("adults", 1),
                children=b.get("children", 0),
                total_amount=b.get("total_amount", 0),
                channel=b.get("channel", "direct")
            )
            for b in bookings
        ]
    
    @strawberry.field
    async def rooms(
        self,
        info,
        filter: Optional[RoomFilter] = None
    ) -> List[Room]:
        """Get rooms with optional filtering"""
        db = info.context["db"]
        cache = info.context["cache"]
        
        # Try cache first
        cache_key = f"rooms:{filter}" if filter else "rooms:all"
        cached = await cache.get(cache_key, "L2")
        if cached:
            return [
                Room(
                    id=r["id"],
                    room_number=r["room_number"],
                    room_type=r["room_type"],
                    floor=r["floor"],
                    capacity=r["capacity"],
                    base_price=r["base_price"],
                    status=RoomStatus(r["status"]),
                    amenities=r["amenities"]
                )
                for r in cached
            ]
        
        # Build query
        query = {}
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
        
        # Query database
        cursor = db.rooms.find(query).skip(skip).limit(limit)
        rooms = await cursor.to_list(limit)
        
        result = [
            Room(
                id=str(r["_id"]),
                room_number=r["room_number"],
                room_type=r["room_type"],
                floor=r["floor"],
                capacity=r["capacity"],
                base_price=r["base_price"],
                status=RoomStatus(r.get("status", "clean")),
                amenities=r.get("amenities", [])
            )
            for r in rooms
        ]
        
        # Cache result
        cache_data = [
            {
                "id": r.id,
                "room_number": r.room_number,
                "room_type": r.room_type,
                "floor": r.floor,
                "capacity": r.capacity,
                "base_price": r.base_price,
                "status": r.status.value,
                "amenities": r.amenities
            }
            for r in result
        ]
        await cache.set(cache_key, cache_data, "L2")
        
        return result

# Schema
schema = strawberry.Schema(query=Query)
