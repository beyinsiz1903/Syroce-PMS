"""
Dashboard Trends Service - Trend graphs data + date range filters.
Arrivals, departures, occupancy, housekeeping readiness, folio issues,
night audit exceptions, blocked check-ins trends.
"""
from datetime import date, timedelta

from core.database import db


async def _count_by_day(coll, match: dict, date_field: str, date_range: list[str], iso_datetime: bool = True) -> dict:
    """Tek aggregation ile gunluk count.

    iso_datetime=True ise date_field 'YYYY-MM-DDTHH:MM:SS' formatindadir → ilk 10 char.
    iso_datetime=False ise date_field zaten 'YYYY-MM-DD' formatinda.
    """
    if not date_range:
        return {}
    lo, hi = date_range[0], date_range[-1]
    if iso_datetime:
        rng = {"$gte": lo + "T00:00:00", "$lte": hi + "T23:59:59"}
    else:
        rng = {"$gte": lo, "$lte": hi}
    pipeline = [
        {"$match": {**match, date_field: rng}},
        {"$group": {"_id": {"$substr": [f"${date_field}", 0, 10]}, "count": {"$sum": 1}}},
    ]
    out = {}
    async for r in coll.aggregate(pipeline):
        out[r["_id"]] = r["count"]
    return out


class DashboardTrendsService:
    """Provides trend data for operational dashboard graphs."""

    async def get_trends(self, tenant_id: str, start_date: str, end_date: str) -> dict:
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

    async def _arrivals_trend(self, tenant_id: str, date_range: list[str]) -> list[dict]:
        cmap = await _count_by_day(db.bookings, {
            "tenant_id": tenant_id,
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
        }, "check_in", date_range)
        return [{"date": d, "count": cmap.get(d, 0)} for d in date_range]

    async def _departures_trend(self, tenant_id: str, date_range: list[str]) -> list[dict]:
        cmap = await _count_by_day(db.bookings, {
            "tenant_id": tenant_id,
            "status": {"$in": ["checked_in", "checked_out"]},
        }, "check_out", date_range)
        return [{"date": d, "count": cmap.get(d, 0)} for d in date_range]

    async def _occupancy_trend(self, tenant_id: str, date_range: list[str]) -> list[dict]:
        """Calculate occupancy rate per day from daily snapshots or live data."""
        total_rooms = await db.rooms.count_documents({
            "tenant_id": tenant_id,
            "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
        })
        if total_rooms == 0:
            return [{"date": d, "rate": 0, "occupied": 0, "total": 0} for d in date_range]

        # Tek sorguda tum snapshotlar
        snaps = await db.daily_audit_snapshots.find(
            {"tenant_id": tenant_id, "business_date": {"$in": date_range}}, {"_id": 0},
        ).to_list(len(date_range))
        snap_map = {s["business_date"]: s for s in snaps}

        # Snapshot olmayan gunler icin tek aggregation: her gun icin "live" occupied
        # ($facet ile gunlere bol)
        missing_days = [d for d in date_range if d not in snap_map]
        live_map: dict[str, int] = {}
        if missing_days:
            facet = {}
            for d in missing_days:
                facet[d] = [
                    {"$match": {
                        "tenant_id": tenant_id,
                        "status": {"$in": ["checked_in"]},
                        "check_in": {"$lte": d + "T23:59:59"},
                        "check_out": {"$gt": d},
                    }},
                    {"$count": "n"},
                ]
            agg = await db.bookings.aggregate([{"$facet": facet}]).to_list(1)
            row = agg[0] if agg else {}
            for d in missing_days:
                arr = row.get(d, [])
                live_map[d] = (arr[0]["n"] if arr else 0)

        result = []
        for d in date_range:
            snap = snap_map.get(d)
            if snap:
                result.append({
                    "date": d,
                    "rate": snap.get("occupancy_rate", 0),
                    "occupied": snap.get("occupied_rooms", 0),
                    "total": snap.get("total_rooms", total_rooms),
                })
            else:
                occupied = live_map.get(d, 0)
                rate = round(occupied / total_rooms * 100, 1)
                result.append({"date": d, "rate": rate, "occupied": occupied, "total": total_rooms})
        return result

    async def _housekeeping_readiness_trend(self, tenant_id: str, date_range: list[str]) -> list[dict]:
        """Housekeeping readiness: percentage of rooms in available/inspected state."""
        total_rooms = await db.rooms.count_documents({
            "tenant_id": tenant_id,
            "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
        })
        if total_rooms == 0:
            return [{"date": d, "rate": 0} for d in date_range]

        snaps = await db.daily_audit_snapshots.find(
            {"tenant_id": tenant_id, "business_date": {"$in": date_range}}, {"_id": 0},
        ).to_list(len(date_range))
        snap_map = {s["business_date"]: s for s in snaps}

        # Geriye kalan gunler icin live ready count tek sefer hesaplanir (bugun durumu)
        ready_now = None
        if any(d not in snap_map for d in date_range):
            ready_now = await db.rooms.count_documents({
                "tenant_id": tenant_id,
                "status": {"$in": ["available", "inspected"]},
                "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
            })

        result = []
        for d in date_range:
            snap = snap_map.get(d)
            if snap:
                occupied = snap.get("occupied_rooms", 0)
                ready = total_rooms - occupied
            else:
                ready = ready_now or 0
            rate = round(ready / total_rooms * 100, 1)
            result.append({"date": d, "rate": rate, "ready": ready, "total": total_rooms})
        return result

    async def _folio_issue_trend(self, tenant_id: str, date_range: list[str]) -> list[dict]:
        cmap = await _count_by_day(db.pms_audit_trail, {
            "tenant_id": tenant_id,
            "entity_type": {"$in": ["folio_charge", "payment", "refund", "folio"]},
            "action": {"$in": ["charge_voided", "payment_voided", "refund_posted", "folio_split"]},
        }, "timestamp", date_range)
        return [{"date": d, "count": cmap.get(d, 0)} for d in date_range]

    async def _audit_exception_trend(self, tenant_id: str, date_range: list[str]) -> list[dict]:
        # audit_date 'YYYY-MM-DD' string
        pipeline = [
            {"$match": {"tenant_id": tenant_id, "audit_date": {"$in": date_range}}},
            {"$group": {"_id": "$audit_date", "count": {"$sum": 1}}},
        ]
        cmap = {}
        async for r in db.audit_exceptions.aggregate(pipeline):
            cmap[r["_id"]] = r["count"]
        return [{"date": d, "count": cmap.get(d, 0)} for d in date_range]

    async def _blocked_checkin_trend(self, tenant_id: str, date_range: list[str]) -> list[dict]:
        """Count blocked check-ins per day (arrivals with unready rooms)."""
        if not date_range:
            return []
        lo, hi = date_range[0], date_range[-1]
        # Tum range icin arrivals'i tek sorguda al
        arrivals = await db.bookings.find({
            "tenant_id": tenant_id,
            "status": {"$in": ["confirmed", "guaranteed"]},
            "check_in": {"$gte": lo + "T00:00:00", "$lte": hi + "T23:59:59"},
        }, {"_id": 0, "room_id": 1, "check_in": 1}).to_list(5000)

        # Tum room_id'leri tek sefer cek
        room_ids = list({a.get("room_id") for a in arrivals if a.get("room_id")})
        room_status_map: dict[str, str] = {}
        if room_ids:
            async for r in db.rooms.find(
                {"tenant_id": tenant_id, "id": {"$in": room_ids}}, {"_id": 0, "id": 1, "status": 1},
            ):
                room_status_map[r["id"]] = r.get("status", "")

        counts: dict[str, int] = dict.fromkeys(date_range, 0)
        ready_set = {"available", "inspected"}
        for a in arrivals:
            day = (a.get("check_in") or "")[:10]
            if day not in counts:
                continue
            st = room_status_map.get(a.get("room_id"))
            if st and st not in ready_set:
                counts[day] += 1
        return [{"date": d, "count": counts[d]} for d in date_range]
