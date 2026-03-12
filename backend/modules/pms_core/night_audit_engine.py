"""
Night Audit Engine - Business date roll, room charge posting, pending arrival/departure control,
unbalanced folio detection, tax consistency, daily snapshot, exceptions queue.
"""
from datetime import datetime, timezone, timedelta, date
from typing import Dict, Optional, List
import uuid

from core.database import db


class NightAuditEngine:
    """Executes nightly audit operations for a hotel property."""

    async def run_night_audit(self, tenant_id: str, business_date: str, started_by: str) -> Dict:
        """Execute complete night audit for a business date."""
        audit_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        audit_record = {
            "id": audit_id,
            "tenant_id": tenant_id,
            "audit_date": business_date,
            "started_at": now.isoformat(),
            "started_by": started_by,
            "status": "in_progress",
            "steps": [],
            "exceptions": [],
            "warnings": [],
        }

        try:
            # Step 1: Pending arrivals control
            arrivals = await self._check_pending_arrivals(tenant_id, business_date)
            audit_record["steps"].append({"step": "pending_arrivals", "result": arrivals})
            audit_record["exceptions"].extend(arrivals.get("exceptions", []))

            # Step 2: Pending departures control
            departures = await self._check_pending_departures(tenant_id, business_date)
            audit_record["steps"].append({"step": "pending_departures", "result": departures})
            audit_record["exceptions"].extend(departures.get("exceptions", []))

            # Step 3: No-show processing
            no_shows = await self._process_no_shows(tenant_id, business_date, started_by)
            audit_record["steps"].append({"step": "no_show_processing", "result": no_shows})

            # Step 4: Room charge posting
            room_charges = await self._post_room_charges(tenant_id, business_date, started_by)
            audit_record["steps"].append({"step": "room_charge_posting", "result": room_charges})
            audit_record["exceptions"].extend(room_charges.get("exceptions", []))

            # Step 5: Unbalanced folio detection
            unbalanced = await self._detect_unbalanced_folios(tenant_id)
            audit_record["steps"].append({"step": "unbalanced_folios", "result": unbalanced})
            audit_record["warnings"].extend(unbalanced.get("warnings", []))

            # Step 6: Tax consistency check
            tax_check = await self._check_tax_consistency(tenant_id, business_date)
            audit_record["steps"].append({"step": "tax_consistency", "result": tax_check})
            audit_record["warnings"].extend(tax_check.get("warnings", []))

            # Step 7: Daily snapshot
            snapshot = await self._create_daily_snapshot(tenant_id, business_date, room_charges)
            audit_record["steps"].append({"step": "daily_snapshot", "result": {"snapshot_id": snapshot["id"]}})

            # Step 8: Business date roll
            await self._roll_business_date(tenant_id, business_date)
            audit_record["steps"].append({"step": "business_date_roll", "result": {"new_business_date": self._next_date(business_date)}})

            audit_record["status"] = "completed"
            audit_record["completed_at"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            audit_record["status"] = "failed"
            audit_record["error"] = str(e)
            audit_record["completed_at"] = datetime.now(timezone.utc).isoformat()

        await db.night_audit_records.insert_one(audit_record)

        # Store exceptions in queue
        for exc in audit_record["exceptions"]:
            await db.audit_exceptions.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "audit_id": audit_id,
                "audit_date": business_date,
                "exception_type": exc.get("type"),
                "description": exc.get("description"),
                "entity_type": exc.get("entity_type"),
                "entity_id": exc.get("entity_id"),
                "status": "open",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        audit_record.pop("_id", None)
        return audit_record

    async def _check_pending_arrivals(self, tenant_id: str, business_date: str) -> Dict:
        """Check for expected arrivals that haven't checked in."""
        arrivals = await db.bookings.find({
            "tenant_id": tenant_id,
            "status": {"$in": ["confirmed", "guaranteed"]},
            "check_in": {"$lte": business_date + "T23:59:59"},
        }, {"_id": 0, "id": 1, "guest_id": 1, "room_id": 1, "check_in": 1, "status": 1}).to_list(500)

        # Filter to today's arrivals
        today_arrivals = [a for a in arrivals if a["check_in"][:10] <= business_date]
        exceptions = [
            {"type": "pending_arrival", "description": f"Booking {a['id']} not checked in (arrival: {a['check_in'][:10]})",
             "entity_type": "booking", "entity_id": a["id"]}
            for a in today_arrivals
        ]

        return {"count": len(today_arrivals), "bookings": today_arrivals, "exceptions": exceptions}

    async def _check_pending_departures(self, tenant_id: str, business_date: str) -> Dict:
        """Check for guests who should have checked out but haven't."""
        overdue = await db.bookings.find({
            "tenant_id": tenant_id,
            "status": "checked_in",
            "check_out": {"$lte": business_date + "T23:59:59"},
        }, {"_id": 0, "id": 1, "guest_id": 1, "room_id": 1, "check_out": 1}).to_list(500)

        today_departures = [d for d in overdue if d["check_out"][:10] <= business_date]
        exceptions = [
            {"type": "pending_departure", "description": f"Booking {d['id']} not checked out (departure: {d['check_out'][:10]})",
             "entity_type": "booking", "entity_id": d["id"]}
            for d in today_departures
        ]

        return {"count": len(today_departures), "bookings": today_departures, "exceptions": exceptions}

    async def _process_no_shows(self, tenant_id: str, business_date: str, user_id: str) -> Dict:
        """Mark confirmed/guaranteed bookings with arrival <= business_date as no-show."""
        from modules.pms_core.reservation_state_machine import ReservationStateMachine
        rsm = ReservationStateMachine()

        candidates = await db.bookings.find({
            "tenant_id": tenant_id,
            "status": {"$in": ["confirmed", "guaranteed"]},
            "check_in": {"$lte": business_date + "T18:00:00"},  # 6 PM cutoff
        }, {"_id": 0}).to_list(500)

        # Only process arrivals from before today
        to_process = [c for c in candidates if c["check_in"][:10] < business_date]

        processed = 0
        for booking in to_process:
            result = await rsm.handle_no_show(tenant_id, booking, user_id)
            if result.get("success"):
                processed += 1

        return {"candidates": len(to_process), "processed": processed}

    async def _post_room_charges(self, tenant_id: str, business_date: str, user_id: str) -> Dict:
        """Post nightly room charges for all checked-in guests."""
        checked_in = await db.bookings.find({
            "tenant_id": tenant_id,
            "status": "checked_in",
        }, {"_id": 0}).to_list(1000)

        posted = 0
        failed = 0
        total_revenue = 0
        total_tax = 0
        exceptions = []

        for booking in checked_in:
            try:
                # Find open folio
                folio = await db.folios.find_one({
                    "booking_id": booking["id"], "tenant_id": tenant_id, "status": "open"
                }, {"_id": 0})

                if not folio:
                    exceptions.append({
                        "type": "no_open_folio",
                        "description": f"Booking {booking['id']} has no open folio",
                        "entity_type": "booking", "entity_id": booking["id"],
                    })
                    failed += 1
                    continue

                # Calculate nightly rate
                check_in_dt = datetime.fromisoformat(booking["check_in"].replace("Z", "+00:00"))
                check_out_dt = datetime.fromisoformat(booking["check_out"].replace("Z", "+00:00"))
                total_nights = max((check_out_dt - check_in_dt).days, 1)
                nightly_rate = round(booking.get("total_amount", 0) / total_nights, 2)

                # Check if already posted for this date
                existing = await db.folio_charges.find_one({
                    "folio_id": folio["id"], "tenant_id": tenant_id,
                    "charge_category": "room", "voided": False,
                    "night_audit_date": business_date,
                })
                if existing:
                    continue  # Already posted, skip

                tax_rate = 10  # default tax rate
                tax_amount = round(nightly_rate * tax_rate / 100, 2)
                total = round(nightly_rate + tax_amount, 2)

                # Get room number
                room = await db.rooms.find_one({"id": booking["room_id"], "tenant_id": tenant_id}, {"_id": 0, "room_number": 1})
                room_number = room.get("room_number", "N/A") if room else "N/A"

                charge_id = str(uuid.uuid4())
                now = datetime.now(timezone.utc)

                await db.folio_charges.insert_one({
                    "id": charge_id,
                    "tenant_id": tenant_id,
                    "folio_id": folio["id"],
                    "booking_id": booking["id"],
                    "charge_category": "room",
                    "description": f"Room {room_number} - Night {business_date}",
                    "unit_price": nightly_rate,
                    "quantity": 1.0,
                    "amount": nightly_rate,
                    "tax_rate": tax_rate,
                    "tax_amount": tax_amount,
                    "total": total,
                    "posted_by": "night_audit",
                    "date": now.isoformat(),
                    "night_audit_date": business_date,
                    "voided": False,
                })

                posted += 1
                total_revenue += nightly_rate
                total_tax += tax_amount

            except Exception as e:
                failed += 1
                exceptions.append({
                    "type": "room_charge_failure",
                    "description": f"Failed to post charge for booking {booking['id']}: {str(e)}",
                    "entity_type": "booking", "entity_id": booking["id"],
                })

        return {
            "posted": posted,
            "failed": failed,
            "total_revenue": round(total_revenue, 2),
            "total_tax": round(total_tax, 2),
            "exceptions": exceptions,
        }

    async def _detect_unbalanced_folios(self, tenant_id: str) -> Dict:
        """Find open folios with unusual balances."""
        open_folios = await db.folios.find({"tenant_id": tenant_id, "status": "open"}, {"_id": 0}).to_list(1000)
        warnings = []

        for folio in open_folios:
            charges = await db.folio_charges.find(
                {"folio_id": folio["id"], "tenant_id": tenant_id, "voided": False}, {"_id": 0}
            ).to_list(500)
            payments = await db.payments.find(
                {"folio_id": folio["id"], "tenant_id": tenant_id, "voided": False}, {"_id": 0}
            ).to_list(500)

            total_charges = sum(c.get("total", c.get("amount", 0)) for c in charges)
            total_payments = sum(p.get("amount", 0) for p in payments)
            balance = round(total_charges - total_payments, 2)

            if total_payments > total_charges + 0.01:
                warnings.append({
                    "folio_id": folio["id"],
                    "folio_number": folio.get("folio_number"),
                    "type": "overpayment",
                    "balance": balance,
                    "message": f"Folio {folio.get('folio_number')} has overpayment of {abs(balance)}",
                })
            elif balance > 10000:
                warnings.append({
                    "folio_id": folio["id"],
                    "folio_number": folio.get("folio_number"),
                    "type": "high_balance",
                    "balance": balance,
                    "message": f"Folio {folio.get('folio_number')} has high outstanding balance: {balance}",
                })

        return {"checked": len(open_folios), "warnings": warnings}

    async def _check_tax_consistency(self, tenant_id: str, business_date: str) -> Dict:
        """Check tax calculations for consistency."""
        charges = await db.folio_charges.find({
            "tenant_id": tenant_id,
            "voided": False,
            "date": {"$gte": business_date + "T00:00:00", "$lte": business_date + "T23:59:59"},
        }, {"_id": 0}).to_list(5000)

        warnings = []
        for charge in charges:
            amount = charge.get("amount", 0)
            tax_rate = charge.get("tax_rate", 0)
            tax_amount = charge.get("tax_amount", 0)
            expected_tax = round(amount * tax_rate / 100, 2) if tax_rate else 0

            if abs(tax_amount - expected_tax) > 0.02:
                warnings.append({
                    "charge_id": charge["id"],
                    "type": "tax_mismatch",
                    "expected_tax": expected_tax,
                    "actual_tax": tax_amount,
                    "message": f"Charge {charge['id']}: tax {tax_amount} != expected {expected_tax}",
                })

        return {"checked": len(charges), "warnings": warnings}

    async def _create_daily_snapshot(self, tenant_id: str, business_date: str, room_charges_result: Dict) -> Dict:
        """Create a daily audit snapshot for reporting."""
        rooms = await db.rooms.find({"tenant_id": tenant_id}, {"_id": 0, "status": 1}).to_list(2000)
        total_rooms = len(rooms)
        occupied = sum(1 for r in rooms if r.get("status") == "occupied")

        checked_in_count = await db.bookings.count_documents({"tenant_id": tenant_id, "status": "checked_in"})

        snapshot = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "business_date": business_date,
            "total_rooms": total_rooms,
            "occupied_rooms": occupied,
            "occupancy_rate": round(occupied / total_rooms * 100, 2) if total_rooms else 0,
            "room_revenue": room_charges_result.get("total_revenue", 0),
            "tax_revenue": room_charges_result.get("total_tax", 0),
            "total_revenue": room_charges_result.get("total_revenue", 0) + room_charges_result.get("total_tax", 0),
            "room_postings": room_charges_result.get("posted", 0),
            "failed_postings": room_charges_result.get("failed", 0),
            "in_house_guests": checked_in_count,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        await db.daily_audit_snapshots.insert_one(snapshot)
        snapshot.pop("_id", None)
        return snapshot

    async def _roll_business_date(self, tenant_id: str, current_date: str):
        """Advance the business date to the next day."""
        next_date = self._next_date(current_date)
        await db.tenant_settings.update_one(
            {"tenant_id": tenant_id},
            {"$set": {"business_date": next_date, "last_audit_date": current_date}},
            upsert=True,
        )

    def _next_date(self, date_str: str) -> str:
        d = date.fromisoformat(date_str)
        return (d + timedelta(days=1)).isoformat()

    async def get_business_date(self, tenant_id: str) -> str:
        """Get current business date for tenant."""
        settings = await db.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
        if settings and settings.get("business_date"):
            return settings["business_date"]
        return datetime.now(timezone.utc).date().isoformat()

    async def get_audit_exceptions(self, tenant_id: str, status: str = "open") -> List[Dict]:
        """Get audit exceptions queue."""
        return await db.audit_exceptions.find(
            {"tenant_id": tenant_id, "status": status}, {"_id": 0}
        ).sort("created_at", -1).to_list(200)

    async def resolve_exception(self, tenant_id: str, exception_id: str, resolved_by: str, resolution: str) -> Dict:
        """Resolve an audit exception."""
        now = datetime.now(timezone.utc)
        result = await db.audit_exceptions.update_one(
            {"id": exception_id, "tenant_id": tenant_id},
            {"$set": {"status": "resolved", "resolved_by": resolved_by, "resolution": resolution, "resolved_at": now.isoformat()}}
        )
        if result.modified_count == 0:
            return {"success": False, "error": "Exception not found"}
        return {"success": True, "exception_id": exception_id}

    async def get_daily_snapshot(self, tenant_id: str, business_date: str) -> Optional[Dict]:
        """Get daily snapshot for a specific date."""
        snapshot = await db.daily_audit_snapshots.find_one(
            {"tenant_id": tenant_id, "business_date": business_date}, {"_id": 0}
        )
        return snapshot
