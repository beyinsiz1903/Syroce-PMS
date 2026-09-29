"""
Multi-Property Platform - Central reservation service, central revenue management,
multi-property dashboard, and global alert system.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from core.atomic_booking import BookingConflictError, create_booking_atomic
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.chain_access import resolve_chain_properties, tenant_id_from_document
from security.encrypted_lookup import decrypt_booking_doc

# Every query in this module is first constrained by ``resolve_chain_properties``
# and then carries an explicit tenant id from that verified set.  A request-
# scoped database proxy is intentionally not used here because it correctly
# rejects sibling-tenant reads; the central-office service is the audited,
# chain-scoped exception.
db = get_system_db()


async def _properties_for_central_user(current_user: User) -> tuple[str, list[dict]]:
    """Resolve a chain once; legacy ``parent_tenant_id`` is never authority."""
    own, properties = await resolve_chain_properties(current_user, require_headquarters=True)
    tenant_id = tenant_id_from_document(own)
    if not tenant_id:  # pragma: no cover - resolver guarantees an identifier
        raise ValueError("Tenant document has no identifier")
    return tenant_id, properties


async def _properties_for_transfer_user(current_user: User) -> tuple[str, list[dict]]:
    """Resolve verified siblings for an operational chain transfer.

    A reservation transfer is a front-desk operation rather than a central
    reporting action.  Any authorised hotel user may therefore see sibling
    availability, while the shared resolver still prevents access outside the
    caller's persisted ``chain_id``.
    """
    own, properties = await resolve_chain_properties(current_user, require_headquarters=False)
    tenant_id = tenant_id_from_document(own)
    if not tenant_id:  # pragma: no cover - resolver guarantees an identifier
        raise ValueError("Tenant document has no identifier")
    return tenant_id, properties


class CentralReservationService:
    """Central reservation management across multiple properties."""

    async def get_portfolio_overview(self, current_user: User) -> dict[str, Any]:
        """Get portfolio-wide reservation overview across all properties."""
        tenant_id, properties = await _properties_for_central_user(current_user)

        today = date.today().isoformat()
        portfolio_data = []

        # N+1 fix: tum property'ler icin tek aggregation
        pids = [tenant_id_from_document(p) for p in properties]
        pids = [pid for pid in pids if pid]
        rooms_total_map: dict = {}
        booked_map: dict = {}
        arrivals_map: dict = {}
        departures_map: dict = {}
        if pids:
            async for r in db.rooms.aggregate(
                [
                    {"$match": {"tenant_id": {"$in": pids}, "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]}},
                    {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}},
                ]
            ):
                rooms_total_map[r["_id"]] = r["n"]
            async for r in db.bookings.aggregate(
                [
                    {"$match": {"tenant_id": {"$in": pids}, "check_in": {"$lte": today}, "check_out": {"$gt": today}, "status": {"$in": ["confirmed", "guaranteed", "checked_in"]}}},
                    {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}},
                ]
            ):
                booked_map[r["_id"]] = r["n"]
            async for r in db.bookings.aggregate(
                [
                    {"$match": {"tenant_id": {"$in": pids}, "check_in": today, "status": {"$in": ["confirmed", "guaranteed"]}}},
                    {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}},
                ]
            ):
                arrivals_map[r["_id"]] = r["n"]
            async for r in db.bookings.aggregate(
                [
                    {"$match": {"tenant_id": {"$in": pids}, "check_out": today, "status": "checked_in"}},
                    {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}},
                ]
            ):
                departures_map[r["_id"]] = r["n"]

        for prop in properties:
            pid = tenant_id_from_document(prop) or tenant_id
            total_rooms = rooms_total_map.get(pid, 0) or 1
            today_booked = booked_map.get(pid, 0)
            arrivals = arrivals_map.get(pid, 0)
            departures = departures_map.get(pid, 0)
            occ = round((today_booked / total_rooms) * 100, 1)

            portfolio_data.append(
                {
                    "property_id": pid,
                    "property_name": prop.get("property_name") or prop.get("hotel_name") or prop.get("name", pid),
                    "total_rooms": total_rooms,
                    "occupied": today_booked,
                    "available": total_rooms - today_booked,
                    "occupancy_pct": occ,
                    "arrivals_today": arrivals,
                    "departures_today": departures,
                }
            )

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

    async def search_availability_cross_property(self, current_user: User, check_in: str, check_out: str, room_type: str | None = None, guests: int = 2) -> dict[str, Any]:
        """Search availability across all properties in the portfolio."""
        source_tenant_id, properties = await _properties_for_transfer_user(current_user)

        results = []
        for prop in properties:
            pid = tenant_id_from_document(prop)
            if not pid or pid == source_tenant_id:
                continue
            room_query = {
                "tenant_id": pid,
                "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
            }
            if room_type:
                room_query["room_type"] = room_type

            rooms = await db.rooms.find(room_query, {"_id": 0}).to_list(1000)

            booked_rooms = set()
            bookings = await db.bookings.find(
                {
                    "tenant_id": pid,
                    "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
                    "check_in": {"$lt": check_out},
                    "check_out": {"$gt": check_in},
                },
                {"_id": 0, "room_id": 1},
            ).to_list(5000)

            for b in bookings:
                if b.get("room_id"):
                    booked_rooms.add(b["room_id"])

            available_rooms = [r for r in rooms if r.get("id") not in booked_rooms and r.get("max_occupancy", 2) >= guests]

            if available_rooms:
                results.append(
                    {
                        "property_id": pid,
                        "property_name": prop.get("property_name") or prop.get("hotel_name") or prop.get("name", pid),
                        "available_rooms": len(available_rooms),
                        "room_types": sorted({r.get("room_type", "Standard") for r in available_rooms}),
                        "min_rate": min(r.get("base_price", 0) for r in available_rooms) if available_rooms else 0,
                        "max_rate": max(r.get("base_price", 0) for r in available_rooms) if available_rooms else 0,
                    }
                )

        return {
            "check_in": check_in,
            "check_out": check_out,
            "room_type": room_type,
            "guests": guests,
            "total_available": sum(r["available_rooms"] for r in results),
            "properties": results,
        }

    async def transfer_reservation(
        self,
        current_user: User,
        booking_id: str,
        target_property_id: str,
        reason: str | None = None,
        target_room_type: str | None = None,
    ) -> dict[str, Any]:
        """Move a future reservation to a verified sibling property safely.

        The old implementation only changed ``bookings.tenant_id``.  That left
        the source room-night locks behind and pointed the booking at a room id
        that did not exist in the target hotel.  The safe flow first creates a
        new target booking through the atomic inventory guard, then closes the
        source booking and releases only its own locks.
        """
        tenant_id, properties = await _properties_for_transfer_user(current_user)
        allowed_tenants = {tenant_id_from_document(prop) for prop in properties}
        if target_property_id not in allowed_tenants:
            return {"success": False, "error": "Hedef tesis aktif zincirin dışında"}
        if target_property_id == tenant_id:
            return {"success": False, "error": "Kaynak ve hedef tesis farklı olmalıdır"}
        booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
        if not booking:
            return {"success": False, "error": "Rezervasyon bulunamadı"}
        booking = decrypt_booking_doc(booking)
        if str(booking.get("status") or "").lower() not in {"pending", "confirmed", "guaranteed"}:
            return {"success": False, "error": "Yalnız giriş yapılmamış aktif rezervasyonlar başka tesise aktarılabilir"}

        folios = await db.folios.find(
            {"tenant_id": tenant_id, "booking_id": booking_id},
            {"_id": 0, "id": 1},
        ).to_list(100)
        folio_ids = [folio.get("id") for folio in folios if folio.get("id")]
        financial_scope: list[dict[str, Any]] = [{"booking_id": booking_id}]
        if folio_ids:
            financial_scope.append({"folio_id": {"$in": folio_ids}})
        financial_activity = 0
        for collection_name in ("payments", "folio_charges", "extra_charges"):
            financial_activity += await getattr(db, collection_name).count_documents({
                "tenant_id": tenant_id,
                "$or": financial_scope,
                "voided": {"$ne": True},
                "status": {"$nin": ["cancelled", "voided"]},
            })
        if financial_activity:
            return {
                "success": False,
                "error": "Bu rezervasyonda finansal hareket var. Tesis değişikliğinden önce folyo ve ödemeleri kaynak tesiste kapatın veya iade edin.",
            }

        requested_room_type = str(target_room_type or booking.get("room_type") or "").strip()
        room_query: dict[str, Any] = {
            "tenant_id": target_property_id,
            "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
            "status": {"$nin": ["maintenance", "out_of_order", "blocked"]},
        }
        if requested_room_type:
            room_query["room_type"] = requested_room_type
        rooms = await db.rooms.find(room_query, {"_id": 0}).to_list(1000)
        guest_count = max(1, int(booking.get("adults") or 0) + int(booking.get("children") or 0))
        rooms = [room for room in rooms if int(room.get("max_occupancy") or 2) >= guest_count]
        if not rooms:
            return {"success": False, "error": "Hedef tesiste seçilen oda tipinde aktif oda bulunamadı"}

        transfer_id = str(uuid.uuid4())
        target_booking_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        target_booking = None
        last_conflict: Exception | None = None
        excluded_fields = {
            "_id", "id", "tenant_id", "room_id", "room_number", "guest_id", "company_id",
            "folio_id", "cancelled_at", "cancelled_by", "cancellation_reason", "transfer_id",
            "transferred_from", "transferred_to_tenant_id", "transferred_to_booking_id",
        }
        booking_payload = {key: value for key, value in booking.items() if key not in excluded_fields}
        for room in rooms:
            candidate = {
                **booking_payload,
                "id": target_booking_id,
                "tenant_id": target_property_id,
                "room_id": room.get("id"),
                "room_number": room.get("room_number"),
                "room_type": room.get("room_type") or requested_room_type,
                "status": booking.get("status") or "confirmed",
                "source_booking_id": booking_id,
                "source_tenant_id": tenant_id,
                "property_transfer_status": "received",
                "transfer_id": transfer_id,
                "transfer_reason": (reason or "").strip(),
                "created_at": now,
                "updated_at": now,
            }
            try:
                target_booking = await create_booking_atomic(tenant_id=target_property_id, booking_doc=candidate)
                break
            except BookingConflictError as exc:
                last_conflict = exc
        if not target_booking:
            return {"success": False, "error": f"Hedef tesiste uygun oda kalmadı: {last_conflict or 'müsaitlik değişti'}"}

        transfer_record = {
            "id": transfer_id,
            "booking_id": booking_id,
            "source_booking_id": booking_id,
            "target_booking_id": target_booking_id,
            "source_property": tenant_id,
            "target_property": target_property_id,
            "reason": (reason or "").strip(),
            "status": "completed",
            "transfer_type": "chain_direct",
            "transferred_by": current_user.id,
            "transferred_at": now,
            "original_booking": {k: v for k, v in booking.items() if k != "_id"},
        }
        source_update = await db.bookings.update_one(
            {"id": booking_id, "tenant_id": tenant_id, "status": {"$in": ["pending", "confirmed", "guaranteed"]}},
            {
                "$set": {
                    "status": "cancelled",
                    "property_transfer_status": "completed",
                    "transferred_to_tenant_id": target_property_id,
                    "transferred_to_booking_id": target_booking_id,
                    "transfer_id": transfer_id,
                    "cancellation_reason": "Zincir içi tesis değişikliği",
                    "cancelled_at": now,
                    "cancelled_by": current_user.id,
                    "updated_at": now,
                }
            },
        )
        if source_update.modified_count != 1:
            await db.bookings.delete_one({"id": target_booking_id, "tenant_id": target_property_id})
            await db.room_night_locks.delete_many({"booking_id": target_booking_id, "tenant_id": target_property_id})
            return {"success": False, "error": "Rezervasyon bu sırada değişti; tesis aktarımı uygulanmadı"}

        await db.room_night_locks.delete_many({"booking_id": booking_id, "tenant_id": tenant_id})
        await db.reservation_transfers.insert_one(transfer_record)

        target_property = next((prop for prop in properties if tenant_id_from_document(prop) == target_property_id), {})
        return {
            "success": True,
            "transfer_id": transfer_id,
            "source": tenant_id,
            "target": target_property_id,
            "target_property_name": target_property.get("property_name") or target_property.get("hotel_name") or target_property.get("name"),
            "source_booking_id": booking_id,
            "target_booking_id": target_booking_id,
            "target_room_id": target_booking.get("room_id"),
            "target_room_number": target_booking.get("room_number"),
        }


class CentralRevenueManagement:
    """Central revenue management across the portfolio."""

    async def get_portfolio_revenue(self, current_user: User, days: int = 30) -> dict[str, Any]:
        """Get portfolio-wide revenue metrics."""
        tenant_id, properties = await _properties_for_central_user(current_user)

        cutoff = (date.today() - timedelta(days=days)).isoformat()
        portfolio_revenue = []

        # N+1 fix: charges/rooms/bookings tek aggregation
        rev_pids = [tenant_id_from_document(p) for p in properties]
        rev_pids = [pid for pid in rev_pids if pid]
        rev_charges_map: dict = {}
        rev_rooms_map: dict = {}
        rev_nights_map: dict = {}
        if rev_pids:
            async for r in db.folio_charges.aggregate(
                [
                    {"$match": {"tenant_id": {"$in": rev_pids}, "posted_at": {"$gte": cutoff}, "voided": {"$ne": True}}},
                    {
                        "$group": {
                            "_id": "$tenant_id",
                            "total": {"$sum": "$amount"},
                            "room": {"$sum": {"$cond": [{"$eq": ["$category", "room"]}, "$amount", 0]}},
                            "fnb": {"$sum": {"$cond": [{"$in": ["$category", ["food", "beverage", "fnb"]]}, "$amount", 0]}},
                        }
                    },
                ]
            ):
                rev_charges_map[r["_id"]] = r
            async for r in db.rooms.aggregate(
                [
                    {"$match": {"tenant_id": {"$in": rev_pids}, "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]}},
                    {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}},
                ]
            ):
                rev_rooms_map[r["_id"]] = r["n"]
            async for r in db.bookings.aggregate(
                [
                    {"$match": {"tenant_id": {"$in": rev_pids}, "check_in": {"$gte": cutoff}, "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]}}},
                    {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}},
                ]
            ):
                rev_nights_map[r["_id"]] = r["n"]

        for prop in properties:
            pid = tenant_id_from_document(prop) or tenant_id
            ch = rev_charges_map.get(pid, {})
            total_rev = ch.get("total", 0)
            room_rev = ch.get("room", 0)
            fnb_rev = ch.get("fnb", 0)
            total_rooms = rev_rooms_map.get(pid, 0)
            room_nights = rev_nights_map.get(pid, 0)
            adr = round(room_rev / room_nights, 2) if room_nights > 0 else 0
            revpar = round(room_rev / (max(total_rooms, 1) * days), 2)

            portfolio_revenue.append(
                {
                    "property_id": pid,
                    "property_name": prop.get("hotel_name") or prop.get("name", pid),
                    "total_revenue": round(total_rev, 2),
                    "room_revenue": round(room_rev, 2),
                    "fnb_revenue": round(fnb_rev, 2),
                    "adr": adr,
                    "revpar": revpar,
                    "room_nights_sold": room_nights,
                }
            )

        total_rev_all = sum(p["total_revenue"] for p in portfolio_revenue)
        avg_adr = round(sum(p["adr"] for p in portfolio_revenue) / len(portfolio_revenue), 2) if portfolio_revenue else 0

        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "total_portfolio_revenue": round(total_rev_all, 2),
            "average_adr": avg_adr,
            "properties": portfolio_revenue,
        }

    async def apply_global_rate_adjustment(self, current_user: User, adjustment_pct: float, room_type: str | None = None) -> dict[str, Any]:
        """Apply a rate adjustment across all properties."""
        tenant_id, properties = await _properties_for_central_user(current_user)

        adjustments = []
        for prop in properties:
            pid = tenant_id_from_document(prop)
            if not pid:
                continue
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
                adjustments.append(
                    {
                        "property_id": pid,
                        "room_id": room["id"],
                        "room_type": room.get("room_type"),
                        "old_price": old_price,
                        "new_price": new_price,
                    }
                )

        # Audit
        await db.global_rate_adjustments.insert_one(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "adjustment_pct": adjustment_pct,
                "room_type": room_type,
                "applied_by": current_user.id,
                "applied_at": datetime.now(UTC).isoformat(),
                "rooms_affected": len(adjustments),
            }
        )

        return {"success": True, "adjustment_pct": adjustment_pct, "rooms_affected": len(adjustments), "details": adjustments[:20]}


class GlobalAlertSystem:
    """Global alert system across all properties."""

    async def get_global_alerts(self, current_user: User) -> dict[str, Any]:
        """Get global alerts across all properties."""
        tenant_id, properties = await _properties_for_central_user(current_user)

        today = date.today().isoformat()
        alerts = []

        # N+1 fix: rooms / bookings / complaints / housekeeping tek aggregation
        a_pids = [tenant_id_from_document(p) for p in properties]
        a_pids = [pid for pid in a_pids if pid]
        a_rooms_map: dict = {}
        a_booked_map: dict = {}
        a_complaints_map: dict = {}
        a_overdue_map: dict = {}
        if a_pids:
            async for r in db.rooms.aggregate(
                [
                    {"$match": {"tenant_id": {"$in": a_pids}, "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]}},
                    {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}},
                ]
            ):
                a_rooms_map[r["_id"]] = r["n"]
            async for r in db.bookings.aggregate(
                [
                    {"$match": {"tenant_id": {"$in": a_pids}, "check_in": {"$lte": today}, "check_out": {"$gt": today}, "status": {"$in": ["confirmed", "guaranteed", "checked_in"]}}},
                    {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}},
                ]
            ):
                a_booked_map[r["_id"]] = r["n"]
            async for r in db.guest_requests.aggregate(
                [
                    {"$match": {"tenant_id": {"$in": a_pids}, "request_type": "complaint", "status": {"$in": ["open", "assigned"]}}},
                    {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}},
                ]
            ):
                a_complaints_map[r["_id"]] = r["n"]
            async for r in db.housekeeping_tasks.aggregate(
                [
                    {"$match": {"tenant_id": {"$in": a_pids}, "status": {"$in": ["pending", "assigned"]}}},
                    {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}},
                ]
            ):
                a_overdue_map[r["_id"]] = r["n"]

        for prop in properties:
            pid = tenant_id_from_document(prop) or tenant_id
            prop_name = prop.get("hotel_name") or prop.get("name", pid)
            total_rooms = a_rooms_map.get(pid, 0)
            booked = a_booked_map.get(pid, 0)
            occ = round((booked / max(total_rooms, 1)) * 100, 1)

            if occ >= 95:
                alerts.append(
                    {
                        "id": str(uuid.uuid4()),
                        "property_id": pid,
                        "property_name": prop_name,
                        "type": "occupancy_critical",
                        "priority": "critical",
                        "message": f"{prop_name}: Doluluk %{occ} - Overbooking riski!",
                        "value": occ,
                    }
                )
            elif occ < 30:
                alerts.append(
                    {
                        "id": str(uuid.uuid4()),
                        "property_id": pid,
                        "property_name": prop_name,
                        "type": "occupancy_low",
                        "priority": "high",
                        "message": f"{prop_name}: Doluluk %{occ} - Acil promosyon gerekli",
                        "value": occ,
                    }
                )

            # Open complaints
            open_complaints = a_complaints_map.get(pid, 0)
            if open_complaints > 3:
                alerts.append(
                    {
                        "id": str(uuid.uuid4()),
                        "property_id": pid,
                        "property_name": prop_name,
                        "type": "complaints_high",
                        "priority": "high",
                        "message": f"{prop_name}: {open_complaints} acik sikayet - Eskalasyon gerekli",
                        "value": open_complaints,
                    }
                )

            # HK overdue
            overdue_tasks = a_overdue_map.get(pid, 0)
            if overdue_tasks > 10:
                alerts.append(
                    {
                        "id": str(uuid.uuid4()),
                        "property_id": pid,
                        "property_name": prop_name,
                        "type": "housekeeping_overdue",
                        "priority": "medium",
                        "message": f"{prop_name}: {overdue_tasks} bekleyen HK gorev",
                        "value": overdue_tasks,
                    }
                )

        alerts.sort(key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x["priority"], 4))
        return {"tenant_id": tenant_id, "count": len(alerts), "alerts": alerts}

    async def get_multi_property_dashboard(self, current_user: User) -> dict[str, Any]:
        """Comprehensive multi-property dashboard."""
        crs = CentralReservationService()
        crm = CentralRevenueManagement()

        portfolio = await crs.get_portfolio_overview(current_user)
        revenue = await crm.get_portfolio_revenue(current_user, 30)
        alerts = await self.get_global_alerts(current_user)

        return {
            "portfolio": portfolio,
            "revenue": revenue,
            "alerts": alerts,
            "generated_at": datetime.now(UTC).isoformat(),
        }
