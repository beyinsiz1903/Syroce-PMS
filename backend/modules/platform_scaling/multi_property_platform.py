"""
Multi-Property Platform - Central reservation service, central revenue management,
multi-property dashboard, and global alert system.
"""
import uuid
from datetime import datetime, timezone, timedelta, date
from typing import Dict, Any, List, Optional
from core.database import db


class CentralReservationService:
    """Central reservation management across multiple properties."""

    async def get_portfolio_overview(self, tenant_id: str) -> Dict[str, Any]:
        """Get portfolio-wide reservation overview across all properties."""
        properties = await db.tenants.find(
            {"$or": [{"id": tenant_id}, {"parent_tenant_id": tenant_id}]},
            {"_id": 0, "id": 1, "name": 1, "hotel_name": 1},
        ).to_list(100)

        if not properties:
            properties = [{"id": tenant_id, "name": "Ana Otel", "hotel_name": "Ana Otel"}]

        today = date.today().isoformat()
        portfolio_data = []

        for prop in properties:
            pid = prop["id"]
            total_rooms = await db.rooms.count_documents({
                "tenant_id": pid,
                "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
            })
            if total_rooms == 0:
                total_rooms = 1

            today_booked = await db.bookings.count_documents({
                "tenant_id": pid,
                "check_in": {"$lte": today},
                "check_out": {"$gt": today},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
            })

            arrivals = await db.bookings.count_documents({
                "tenant_id": pid, "check_in": today,
                "status": {"$in": ["confirmed", "guaranteed"]},
            })
            departures = await db.bookings.count_documents({
                "tenant_id": pid, "check_out": today, "status": "checked_in",
            })

            occ = round((today_booked / total_rooms) * 100, 1)

            portfolio_data.append({
                "property_id": pid,
                "property_name": prop.get("hotel_name") or prop.get("name", pid),
                "total_rooms": total_rooms,
                "occupied": today_booked,
                "available": total_rooms - today_booked,
                "occupancy_pct": occ,
                "arrivals_today": arrivals,
                "departures_today": departures,
            })

        total_rooms_all = sum(p["total_rooms"] for p in portfolio_data)
        total_occupied = sum(p["occupied"] for p in portfolio_data)
        portfolio_occ = round((total_occupied / total_rooms_all) * 100, 1) if total_rooms_all > 0 else 0

        return {
            "tenant_id": tenant_id,
            "date": today,
            "portfolio_occupancy_pct": portfolio_occ,
            "total_rooms": total_rooms_all,
            "total_occupied": total_occupied,
            "total_available": total_rooms_all - total_occupied,
            "properties": portfolio_data,
        }

    async def search_availability_cross_property(self, tenant_id: str,
                                                   check_in: str, check_out: str,
                                                   room_type: Optional[str] = None,
                                                   guests: int = 2) -> Dict[str, Any]:
        """Search availability across all properties in the portfolio."""
        properties = await db.tenants.find(
            {"$or": [{"id": tenant_id}, {"parent_tenant_id": tenant_id}]},
            {"_id": 0, "id": 1, "name": 1, "hotel_name": 1},
        ).to_list(100)

        if not properties:
            properties = [{"id": tenant_id, "name": "Ana Otel", "hotel_name": "Ana Otel"}]

        results = []
        for prop in properties:
            pid = prop["id"]
            room_query = {
                "tenant_id": pid,
                "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
            }
            if room_type:
                room_query["room_type"] = room_type

            rooms = await db.rooms.find(room_query, {"_id": 0}).to_list(1000)

            booked_rooms = set()
            bookings = await db.bookings.find({
                "tenant_id": pid,
                "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
                "check_in": {"$lt": check_out},
                "check_out": {"$gt": check_in},
            }, {"_id": 0, "room_id": 1}).to_list(5000)

            for b in bookings:
                if b.get("room_id"):
                    booked_rooms.add(b["room_id"])

            available_rooms = [r for r in rooms if r.get("id") not in booked_rooms
                               and r.get("max_occupancy", 2) >= guests]

            if available_rooms:
                results.append({
                    "property_id": pid,
                    "property_name": prop.get("hotel_name") or prop.get("name", pid),
                    "available_rooms": len(available_rooms),
                    "room_types": list(set(r.get("room_type", "Standard") for r in available_rooms)),
                    "min_rate": min(r.get("base_price", 0) for r in available_rooms) if available_rooms else 0,
                    "max_rate": max(r.get("base_price", 0) for r in available_rooms) if available_rooms else 0,
                })

        return {
            "check_in": check_in, "check_out": check_out,
            "room_type": room_type, "guests": guests,
            "total_available": sum(r["available_rooms"] for r in results),
            "properties": results,
        }

    async def transfer_reservation(self, tenant_id: str, booking_id: str,
                                    target_property_id: str, user_id: str,
                                    reason: Optional[str] = None) -> Dict[str, Any]:
        """Transfer a reservation between properties."""
        booking = await db.bookings.find_one(
            {"id": booking_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not booking:
            return {"success": False, "error": "Booking not found"}

        transfer_record = {
            "id": str(uuid.uuid4()),
            "booking_id": booking_id,
            "source_property": tenant_id,
            "target_property": target_property_id,
            "reason": reason,
            "transferred_by": user_id,
            "transferred_at": datetime.now(timezone.utc).isoformat(),
            "original_booking": {k: v for k, v in booking.items() if k != "_id"},
        }
        await db.reservation_transfers.insert_one(transfer_record)

        # Update booking tenant_id
        await db.bookings.update_one(
            {"id": booking_id},
            {"$set": {
                "tenant_id": target_property_id,
                "transferred_from": tenant_id,
                "transfer_id": transfer_record["id"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )

        return {"success": True, "transfer_id": transfer_record["id"],
                "source": tenant_id, "target": target_property_id}


class CentralRevenueManagement:
    """Central revenue management across the portfolio."""

    async def get_portfolio_revenue(self, tenant_id: str, days: int = 30) -> Dict[str, Any]:
        """Get portfolio-wide revenue metrics."""
        properties = await db.tenants.find(
            {"$or": [{"id": tenant_id}, {"parent_tenant_id": tenant_id}]},
            {"_id": 0, "id": 1, "name": 1, "hotel_name": 1},
        ).to_list(100)

        if not properties:
            properties = [{"id": tenant_id, "name": "Ana Otel", "hotel_name": "Ana Otel"}]

        cutoff = (date.today() - timedelta(days=days)).isoformat()
        portfolio_revenue = []

        for prop in properties:
            pid = prop["id"]
            charges = await db.folio_charges.find(
                {"tenant_id": pid, "posted_at": {"$gte": cutoff}, "voided": {"$ne": True}},
                {"_id": 0, "amount": 1, "category": 1},
            ).to_list(10000)

            total_rev = sum(c.get("amount", 0) for c in charges)
            room_rev = sum(c.get("amount", 0) for c in charges if c.get("category") == "room")
            fnb_rev = sum(c.get("amount", 0) for c in charges if c.get("category") in ("food", "beverage", "fnb"))

            total_rooms = await db.rooms.count_documents({
                "tenant_id": pid,
                "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
            })
            room_nights = await db.bookings.count_documents({
                "tenant_id": pid, "check_in": {"$gte": cutoff},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
            })

            adr = round(room_rev / room_nights, 2) if room_nights > 0 else 0
            revpar = round(room_rev / (max(total_rooms, 1) * days), 2)

            portfolio_revenue.append({
                "property_id": pid,
                "property_name": prop.get("hotel_name") or prop.get("name", pid),
                "total_revenue": round(total_rev, 2),
                "room_revenue": round(room_rev, 2),
                "fnb_revenue": round(fnb_rev, 2),
                "adr": adr,
                "revpar": revpar,
                "room_nights_sold": room_nights,
            })

        total_rev_all = sum(p["total_revenue"] for p in portfolio_revenue)
        avg_adr = round(sum(p["adr"] for p in portfolio_revenue) / len(portfolio_revenue), 2) if portfolio_revenue else 0

        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "total_portfolio_revenue": round(total_rev_all, 2),
            "average_adr": avg_adr,
            "properties": portfolio_revenue,
        }

    async def apply_global_rate_adjustment(self, tenant_id: str, adjustment_pct: float,
                                            room_type: Optional[str] = None,
                                            user_id: str = "") -> Dict[str, Any]:
        """Apply a rate adjustment across all properties."""
        properties = await db.tenants.find(
            {"$or": [{"id": tenant_id}, {"parent_tenant_id": tenant_id}]},
            {"_id": 0, "id": 1},
        ).to_list(100)

        if not properties:
            properties = [{"id": tenant_id}]

        adjustments = []
        for prop in properties:
            pid = prop["id"]
            room_query = {"tenant_id": pid}
            if room_type:
                room_query["room_type"] = room_type

            rooms = await db.rooms.find(room_query, {"_id": 0, "id": 1, "base_price": 1, "room_type": 1}).to_list(1000)
            for room in rooms:
                old_price = room.get("base_price", 0)
                new_price = round(old_price * (1 + adjustment_pct / 100), 2)
                await db.rooms.update_one(
                    {"id": room["id"], "tenant_id": pid},
                    {"$set": {"base_price": new_price}},
                )
                adjustments.append({
                    "property_id": pid,
                    "room_id": room["id"],
                    "room_type": room.get("room_type"),
                    "old_price": old_price,
                    "new_price": new_price,
                })

        # Audit
        await db.global_rate_adjustments.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "adjustment_pct": adjustment_pct,
            "room_type": room_type,
            "applied_by": user_id,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "rooms_affected": len(adjustments),
        })

        return {"success": True, "adjustment_pct": adjustment_pct,
                "rooms_affected": len(adjustments), "details": adjustments[:20]}


class GlobalAlertSystem:
    """Global alert system across all properties."""

    async def get_global_alerts(self, tenant_id: str) -> Dict[str, Any]:
        """Get global alerts across all properties."""
        properties = await db.tenants.find(
            {"$or": [{"id": tenant_id}, {"parent_tenant_id": tenant_id}]},
            {"_id": 0, "id": 1, "hotel_name": 1, "name": 1},
        ).to_list(100)

        if not properties:
            properties = [{"id": tenant_id, "hotel_name": "Ana Otel"}]

        today = date.today().isoformat()
        alerts = []

        for prop in properties:
            pid = prop["id"]
            prop_name = prop.get("hotel_name") or prop.get("name", pid)

            # Occupancy alert
            total_rooms = await db.rooms.count_documents({
                "tenant_id": pid,
                "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
            })
            booked = await db.bookings.count_documents({
                "tenant_id": pid,
                "check_in": {"$lte": today}, "check_out": {"$gt": today},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
            })
            occ = round((booked / max(total_rooms, 1)) * 100, 1)

            if occ >= 95:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "property_id": pid, "property_name": prop_name,
                    "type": "occupancy_critical", "priority": "critical",
                    "message": f"{prop_name}: Doluluk %{occ} - Overbooking riski!",
                    "value": occ,
                })
            elif occ < 30:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "property_id": pid, "property_name": prop_name,
                    "type": "occupancy_low", "priority": "high",
                    "message": f"{prop_name}: Doluluk %{occ} - Acil promosyon gerekli",
                    "value": occ,
                })

            # Open complaints
            open_complaints = await db.guest_requests.count_documents({
                "tenant_id": pid, "request_type": "complaint",
                "status": {"$in": ["open", "assigned"]},
            })
            if open_complaints > 3:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "property_id": pid, "property_name": prop_name,
                    "type": "complaints_high", "priority": "high",
                    "message": f"{prop_name}: {open_complaints} acik sikayet - Eskalasyon gerekli",
                    "value": open_complaints,
                })

            # HK overdue
            overdue_tasks = await db.housekeeping_tasks.count_documents({
                "tenant_id": pid, "status": {"$in": ["pending", "assigned"]},
            })
            if overdue_tasks > 10:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "property_id": pid, "property_name": prop_name,
                    "type": "housekeeping_overdue", "priority": "medium",
                    "message": f"{prop_name}: {overdue_tasks} bekleyen HK gorev",
                    "value": overdue_tasks,
                })

        alerts.sort(key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x["priority"], 4))
        return {"tenant_id": tenant_id, "count": len(alerts), "alerts": alerts}

    async def get_multi_property_dashboard(self, tenant_id: str) -> Dict[str, Any]:
        """Comprehensive multi-property dashboard."""
        crs = CentralReservationService()
        crm = CentralRevenueManagement()

        portfolio = await crs.get_portfolio_overview(tenant_id)
        revenue = await crm.get_portfolio_revenue(tenant_id, 30)
        alerts = await self.get_global_alerts(tenant_id)

        return {
            "portfolio": portfolio,
            "revenue": revenue,
            "alerts": alerts,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
