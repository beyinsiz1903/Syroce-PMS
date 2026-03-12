"""
Dashboard Trends Service - Trend graphs data + date range filters.
Arrivals, departures, occupancy, housekeeping readiness, folio issues,
night audit exceptions, blocked check-ins trends.
"""
from datetime import timedelta, date
from typing import Dict, List

from core.database import db


class DashboardTrendsService:
    """Provides trend data for operational dashboard graphs."""

    async def get_trends(self, tenant_id: str, start_date: str, end_date: str) -> Dict:
        """Get all trend data for a date range."""
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
        days = (ed - sd).days + 1
        date_range = [(sd + timedelta(days=i)).isoformat() for i in range(days)]

        arrivals = await self._arrivals_trend(tenant_id, date_range)
        departures = await self._departures_trend(tenant_id, date_range)
        occupancy = await self._occupancy_trend(tenant_id, date_range)
        hk_readiness = await self._housekeeping_readiness_trend(tenant_id, date_range)
        folio_issues = await self._folio_issue_trend(tenant_id, date_range)
        audit_exceptions = await self._audit_exception_trend(tenant_id, date_range)
        blocked_checkins = await self._blocked_checkin_trend(tenant_id, date_range)

        return {
            "start_date": start_date,
            "end_date": end_date,
            "days": days,
            "trends": {
                "arrivals": arrivals,
                "departures": departures,
                "occupancy": occupancy,
                "housekeeping_readiness": hk_readiness,
                "folio_issues": folio_issues,
                "audit_exceptions": audit_exceptions,
                "blocked_checkins": blocked_checkins,
            },
        }

    async def _arrivals_trend(self, tenant_id: str, date_range: List[str]) -> List[Dict]:
        """Count arrivals per day."""
        result = []
        for d in date_range:
            count = await db.bookings.count_documents({
                "tenant_id": tenant_id,
                "check_in": {"$gte": d + "T00:00:00", "$lte": d + "T23:59:59"},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
            })
            result.append({"date": d, "count": count})
        return result

    async def _departures_trend(self, tenant_id: str, date_range: List[str]) -> List[Dict]:
        """Count departures per day."""
        result = []
        for d in date_range:
            count = await db.bookings.count_documents({
                "tenant_id": tenant_id,
                "check_out": {"$gte": d + "T00:00:00", "$lte": d + "T23:59:59"},
                "status": {"$in": ["checked_in", "checked_out"]},
            })
            result.append({"date": d, "count": count})
        return result

    async def _occupancy_trend(self, tenant_id: str, date_range: List[str]) -> List[Dict]:
        """Calculate occupancy rate per day from daily snapshots or live data."""
        total_rooms = await db.rooms.count_documents({
            "tenant_id": tenant_id,
            "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
        })
        if total_rooms == 0:
            return [{"date": d, "rate": 0, "occupied": 0, "total": 0} for d in date_range]

        result = []
        for d in date_range:
            # Try snapshot first
            snapshot = await db.daily_audit_snapshots.find_one(
                {"tenant_id": tenant_id, "business_date": d}, {"_id": 0}
            )
            if snapshot:
                result.append({
                    "date": d,
                    "rate": snapshot.get("occupancy_rate", 0),
                    "occupied": snapshot.get("occupied_rooms", 0),
                    "total": snapshot.get("total_rooms", total_rooms),
                })
            else:
                # Calculate from bookings
                occupied = await db.bookings.count_documents({
                    "tenant_id": tenant_id,
                    "status": {"$in": ["checked_in"]},
                    "check_in": {"$lte": d + "T23:59:59"},
                    "check_out": {"$gt": d},
                })
                rate = round(occupied / total_rooms * 100, 1) if total_rooms else 0
                result.append({"date": d, "rate": rate, "occupied": occupied, "total": total_rooms})
        return result

    async def _housekeeping_readiness_trend(self, tenant_id: str, date_range: List[str]) -> List[Dict]:
        """Housekeeping readiness: percentage of rooms in available/inspected state."""
        total_rooms = await db.rooms.count_documents({
            "tenant_id": tenant_id,
            "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
        })
        if total_rooms == 0:
            return [{"date": d, "rate": 0} for d in date_range]

        result = []
        for d in date_range:
            snapshot = await db.daily_audit_snapshots.find_one(
                {"tenant_id": tenant_id, "business_date": d}, {"_id": 0}
            )
            if snapshot:
                occupied = snapshot.get("occupied_rooms", 0)
                ready = total_rooms - occupied
                rate = round(ready / total_rooms * 100, 1)
            else:
                ready = await db.rooms.count_documents({
                    "tenant_id": tenant_id,
                    "status": {"$in": ["available", "inspected"]},
                    "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
                })
                rate = round(ready / total_rooms * 100, 1)
            result.append({"date": d, "rate": rate, "ready": ready, "total": total_rooms})
        return result

    async def _folio_issue_trend(self, tenant_id: str, date_range: List[str]) -> List[Dict]:
        """Count folio-related audit events per day."""
        result = []
        for d in date_range:
            count = await db.pms_audit_trail.count_documents({
                "tenant_id": tenant_id,
                "entity_type": {"$in": ["folio_charge", "payment", "refund", "folio"]},
                "action": {"$in": ["charge_voided", "payment_voided", "refund_posted", "folio_split"]},
                "timestamp": {"$gte": d + "T00:00:00", "$lte": d + "T23:59:59"},
            })
            result.append({"date": d, "count": count})
        return result

    async def _audit_exception_trend(self, tenant_id: str, date_range: List[str]) -> List[Dict]:
        """Count night audit exceptions per day."""
        result = []
        for d in date_range:
            count = await db.audit_exceptions.count_documents({
                "tenant_id": tenant_id,
                "audit_date": d,
            })
            result.append({"date": d, "count": count})
        return result

    async def _blocked_checkin_trend(self, tenant_id: str, date_range: List[str]) -> List[Dict]:
        """Count blocked check-ins per day (arrivals with unready rooms)."""
        result = []
        for d in date_range:
            arrivals = await db.bookings.find({
                "tenant_id": tenant_id,
                "status": {"$in": ["confirmed", "guaranteed"]},
                "check_in": {"$gte": d + "T00:00:00", "$lte": d + "T23:59:59"},
            }, {"_id": 0, "room_id": 1}).to_list(500)

            blocked = 0
            for a in arrivals:
                room = await db.rooms.find_one(
                    {"id": a.get("room_id"), "tenant_id": tenant_id},
                    {"_id": 0, "status": 1}
                )
                if room and room.get("status") not in {"available", "inspected"}:
                    blocked += 1

            result.append({"date": d, "count": blocked})
        return result
