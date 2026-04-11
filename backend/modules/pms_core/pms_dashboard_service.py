"""
PMS Dashboard Service - Aggregates operational data for the PMS dashboard.
Arrivals, departures, in-house, room status, folio issues, audit exceptions.
"""
from datetime import UTC, datetime, timedelta

from core.database import db


class PMSDashboardService:
    """Aggregates real-time operational data for the PMS dashboard."""

    async def get_operational_snapshot(self, tenant_id: str) -> dict:
        """Get comprehensive operational snapshot for today."""
        today = datetime.now(UTC).date().isoformat()
        (datetime.now(UTC).date() + timedelta(days=1)).isoformat()

        # Parallel data collection
        arrivals = await self._get_arrivals_today(tenant_id, today)
        departures = await self._get_departures_today(tenant_id, today)
        in_house = await self._get_in_house_guests(tenant_id)
        room_summary = await self._get_room_status_summary(tenant_id)
        folio_issues = await self._get_pending_folio_issues(tenant_id)
        audit_exceptions = await self._get_open_audit_exceptions(tenant_id)
        blocked_checkins = await self._get_blocked_checkins(tenant_id, today)

        return {
            "business_date": today,
            "arrivals_today": arrivals,
            "departures_today": departures,
            "in_house_guests": in_house,
            "room_status": room_summary,
            "pending_folio_issues": folio_issues,
            "audit_exceptions": audit_exceptions,
            "blocked_checkins": blocked_checkins,
        }

    async def _get_arrivals_today(self, tenant_id: str, today: str) -> dict:
        arrivals = await db.bookings.find({
            "tenant_id": tenant_id,
            "status": {"$in": ["confirmed", "guaranteed", "pending"]},
            "check_in": {"$gte": today + "T00:00:00", "$lte": today + "T23:59:59"},
        }, {"_id": 0, "id": 1, "guest_id": 1, "room_id": 1, "check_in": 1, "status": 1}).to_list(500)

        total = len(arrivals)
        # Enrich with room readiness
        enriched = []
        for a in arrivals[:50]:  # Limit enrichment
            room = await db.rooms.find_one({"id": a.get("room_id"), "tenant_id": tenant_id}, {"_id": 0, "room_number": 1, "status": 1})
            guest = await db.guests.find_one({"id": a.get("guest_id"), "tenant_id": tenant_id}, {"_id": 0, "name": 1})
            enriched.append({
                **a,
                "room_number": room.get("room_number") if room else "Unassigned",
                "room_status": room.get("status") if room else "unknown",
                "room_ready": room.get("status") in {"available", "inspected"} if room else False,
                "guest_name": guest.get("name") if guest else "Unknown",
            })

        return {"total": total, "arrivals": enriched}

    async def _get_departures_today(self, tenant_id: str, today: str) -> dict:
        departures = await db.bookings.find({
            "tenant_id": tenant_id,
            "status": "checked_in",
            "check_out": {"$gte": today + "T00:00:00", "$lte": today + "T23:59:59"},
        }, {"_id": 0, "id": 1, "guest_id": 1, "room_id": 1, "check_out": 1}).to_list(500)

        enriched = []
        for d in departures[:50]:
            room = await db.rooms.find_one({"id": d.get("room_id"), "tenant_id": tenant_id}, {"_id": 0, "room_number": 1})
            guest = await db.guests.find_one({"id": d.get("guest_id"), "tenant_id": tenant_id}, {"_id": 0, "name": 1})

            # Check folio balance
            folio = await db.folios.find_one({"booking_id": d["id"], "tenant_id": tenant_id, "status": "open"}, {"_id": 0})
            balance = 0
            if folio:
                balance = folio.get("balance", 0)

            enriched.append({
                **d,
                "room_number": room.get("room_number") if room else "N/A",
                "guest_name": guest.get("name") if guest else "Unknown",
                "folio_balance": balance,
                "has_balance": balance > 0.01,
            })

        return {"total": len(departures), "departures": enriched}

    async def _get_in_house_guests(self, tenant_id: str) -> dict:
        count = await db.bookings.count_documents({"tenant_id": tenant_id, "status": "checked_in"})
        return {"count": count}

    async def _get_room_status_summary(self, tenant_id: str) -> dict:
        pipeline = [
            {"$match": {"tenant_id": tenant_id, "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        results = await db.rooms.aggregate(pipeline).to_list(20)
        summary = {r["_id"]: r["count"] for r in results}
        total = sum(summary.values())

        return {
            "total": total,
            "available": summary.get("available", 0),
            "occupied": summary.get("occupied", 0),
            "dirty": summary.get("dirty", 0),
            "cleaning": summary.get("cleaning", 0),
            "inspected": summary.get("inspected", 0),
            "out_of_order": summary.get("out_of_order", 0),
            "out_of_service": summary.get("out_of_service", 0) + summary.get("maintenance", 0),
            "ready": summary.get("available", 0) + summary.get("inspected", 0),
        }

    async def _get_pending_folio_issues(self, tenant_id: str) -> dict:
        """Get open folios with high or negative balances."""
        open_folios = await db.folios.find(
            {"tenant_id": tenant_id, "status": "open"}, {"_id": 0}
        ).to_list(1000)

        issues = []
        for folio in open_folios:
            balance = folio.get("balance", 0)
            if balance < -0.01:
                issues.append({
                    "folio_id": folio["id"],
                    "folio_number": folio.get("folio_number"),
                    "issue": "overpayment",
                    "balance": balance,
                })
            elif balance > 5000:
                issues.append({
                    "folio_id": folio["id"],
                    "folio_number": folio.get("folio_number"),
                    "issue": "high_balance",
                    "balance": balance,
                })

        return {"count": len(issues), "issues": issues}

    async def _get_open_audit_exceptions(self, tenant_id: str) -> dict:
        count = await db.audit_exceptions.count_documents({"tenant_id": tenant_id, "status": "open"})
        exceptions = await db.audit_exceptions.find(
            {"tenant_id": tenant_id, "status": "open"}, {"_id": 0}
        ).sort("created_at", -1).limit(10).to_list(10)
        return {"count": count, "exceptions": exceptions}

    async def _get_blocked_checkins(self, tenant_id: str, today: str) -> dict:
        """Find today's arrivals where room is not ready."""
        arrivals = await db.bookings.find({
            "tenant_id": tenant_id,
            "status": {"$in": ["confirmed", "guaranteed"]},
            "check_in": {"$gte": today + "T00:00:00", "$lte": today + "T23:59:59"},
        }, {"_id": 0, "id": 1, "room_id": 1, "guest_id": 1}).to_list(500)

        blocked = []
        for a in arrivals:
            room = await db.rooms.find_one({"id": a.get("room_id"), "tenant_id": tenant_id}, {"_id": 0, "room_number": 1, "status": 1})
            if room and room.get("status") not in {"available", "inspected"}:
                guest = await db.guests.find_one({"id": a.get("guest_id"), "tenant_id": tenant_id}, {"_id": 0, "name": 1})
                blocked.append({
                    "booking_id": a["id"],
                    "room_number": room.get("room_number"),
                    "room_status": room.get("status"),
                    "guest_name": guest.get("name") if guest else "Unknown",
                    "reason": f"Room {room.get('room_number')} status: {room.get('status')}",
                })

        return {"count": len(blocked), "blocked": blocked}
