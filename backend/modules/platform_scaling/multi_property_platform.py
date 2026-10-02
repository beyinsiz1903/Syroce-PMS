"""
Multi-Property Platform - Central reservation service, central revenue management,
multi-property dashboard, and global alert system.
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
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
logger = logging.getLogger(__name__)


def _money(value: object) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _payment_totals(payments: list[dict], fallback_currency: str) -> dict[str, float]:
    totals: dict[str, Decimal] = {}
    for payment in payments:
        currency = str(payment.get("currency") or fallback_currency or "TRY").upper()
        totals[currency] = totals.get(currency, Decimal("0.00")) + _money(payment.get("amount"))
    return {
        currency: float(amount)
        for currency, amount in sorted(totals.items())
        if amount > 0
    }


def _property_name(property_doc: dict, fallback: str) -> str:
    return str(
        property_doc.get("property_name")
        or property_doc.get("hotel_name")
        or property_doc.get("name")
        or fallback
    )


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
        financial_handling: str = "reject",
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

        source_property = next((prop for prop in properties if tenant_id_from_document(prop) == tenant_id), {})
        target_property = next((prop for prop in properties if tenant_id_from_document(prop) == target_property_id), {})
        source_property_name = _property_name(source_property, tenant_id)
        target_property_name = _property_name(target_property, target_property_id)

        folios = await db.folios.find(
            {"tenant_id": tenant_id, "booking_id": booking_id},
            {"_id": 0, "id": 1},
        ).to_list(100)
        folio_ids = [folio.get("id") for folio in folios if folio.get("id")]
        # Historical deposit/import paths may use reservation_id rather than
        # booking_id.  Missing that alias allowed a paid reservation to move
        # without a settlement trail.
        financial_scope: list[dict[str, Any]] = [
            {"booking_id": booking_id},
            {"reservation_id": booking_id},
        ]
        if folio_ids:
            financial_scope.append({"folio_id": {"$in": folio_ids}})
        active_financial_query = {
            "tenant_id": tenant_id,
            "$or": financial_scope,
            "voided": {"$ne": True},
            "status": {"$nin": ["cancelled", "voided", "refunded", "reversed"]},
        }
        payment_count = await db.payments.count_documents(active_financial_query)
        charge_count = 0
        for collection_name in ("folio_charges", "extra_charges"):
            charge_count += await getattr(db, collection_name).count_documents(active_financial_query)
        payments = []
        if payment_count:
            payments = await db.payments.find(
                active_financial_query,
                {"_id": 0, "id": 1, "amount": 1, "currency": 1, "method": 1, "reference": 1},
            ).to_list(1000)
        payment_totals = _payment_totals(payments, str(booking.get("currency") or "TRY"))

        # Charges mean service/revenue has already been recognised by the
        # source hotel.  That is not a simple prepayment transfer and must be
        # corrected there before the reservation can move.
        if charge_count:
            return {
                "success": False,
                "error": "Bu rezervasyonda tahakkuk veya ek ücret var. Tesis değişikliğinden önce kaynak tesiste finansal düzeltme yapılmalıdır.",
            }
        if payment_count and financial_handling != "retain_and_settle":
            return {
                "success": False,
                "error_code": "financial_handling_required",
                "error": "Kaynak tesiste tahsilat var. İade edin veya tahsilatı kaynak tesiste tutup zincir içi mahsuplaşma oluşturun.",
                "payment_totals": payment_totals,
            }
        if payment_count and not payment_totals:
            return {
                "success": False,
                "error": "Tahsilat kayıtlarının para birimi veya tutarı doğrulanamadı; transfer uygulanmadı.",
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
        # IDs are useful to services but not to a finance user reconciling two
        # hotels. Keep one immutable, human-readable reference on every
        # booking, settlement, notification and audit entry in this transfer.
        transfer_reference = f"TRF-{datetime.now(UTC):%Y%m%d}-{transfer_id[:8].upper()}"
        settlement_id = str(uuid.uuid4()) if payment_totals else None
        target_booking_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        target_booking = None
        last_conflict: Exception | None = None
        excluded_fields = {
            "_id", "id", "tenant_id", "room_id", "room_number", "guest_id", "company_id",
            "folio_id", "cancelled_at", "cancelled_by", "cancellation_reason", "transfer_id",
            "transferred_from", "transferred_to_tenant_id", "transferred_to_booking_id",
            "source_booking_id", "source_tenant_id", "source_property_id", "source_property_name",
            "transfer_financial_handling", "transfer_settlement_id", "transferred_prepayments",
            "transfer_reference",
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
                "source_property_id": tenant_id,
                "source_property_name": source_property_name,
                "property_transfer_status": "received",
                "transfer_id": transfer_id,
                "transfer_reference": transfer_reference,
                "transfer_reason": (reason or "").strip(),
                "transfer_financial_handling": "retain_and_settle" if payment_totals else "no_financial_activity",
                "transfer_settlement_id": settlement_id,
                "transferred_prepayments": [
                    {"currency": currency, "amount": amount}
                    for currency, amount in payment_totals.items()
                ],
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
            "transfer_reference": transfer_reference,
            "guest_name": booking.get("guest_name"),
            "confirmation_number": booking.get("confirmation_number") or booking.get("reservation_number"),
            "booking_id": booking_id,
            "source_booking_id": booking_id,
            "target_booking_id": target_booking_id,
            "source_property": tenant_id,
            "source_property_name": source_property_name,
            "target_property": target_property_id,
            "target_property_name": target_property_name,
            "reason": (reason or "").strip(),
            "status": "completed",
            "transfer_type": "chain_direct",
            "transferred_by": current_user.id,
            "transferred_at": now,
            "financial_handling": "retain_and_settle" if payment_totals else "no_financial_activity",
            "payment_totals": payment_totals,
            "collection_property_id": tenant_id if payment_totals else None,
            "service_property_id": target_property_id,
            "settlement_id": settlement_id,
            "settlement_status": "open" if payment_totals else "not_required",
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
                    "transfer_reference": transfer_reference,
                    "transfer_financial_handling": "retain_and_settle" if payment_totals else "no_financial_activity",
                    "transfer_settlement_id": settlement_id,
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

        if settlement_id:
            await db.chain_transfer_settlements.insert_one(
                {
                    "id": settlement_id,
                    "transfer_id": transfer_id,
                    "transfer_reference": transfer_reference,
                    "chain_id": source_property.get("chain_id") or target_property.get("chain_id"),
                    "source_property_id": tenant_id,
                    "source_property_name": source_property_name,
                    "target_property_id": target_property_id,
                    "target_property_name": target_property_name,
                    "collection_property_id": tenant_id,
                    "service_property_id": target_property_id,
                    "source_booking_id": booking_id,
                    "target_booking_id": target_booking_id,
                    "currency_lines": [
                        {
                            "currency": currency,
                            "amount": amount,
                            "source_position": "payable",
                            "target_position": "receivable",
                        }
                        for currency, amount in payment_totals.items()
                    ],
                    "source_payment_ids": [payment.get("id") for payment in payments if payment.get("id")],
                    "status": "open",
                    "accounting_status": "pending_reconciliation",
                    "created_by": current_user.id,
                    "created_at": now,
                    "updated_at": now,
                }
            )

        activity_details = {
            "transfer_id": transfer_id,
            "transfer_reference": transfer_reference,
            "source_property_id": tenant_id,
            "source_property_name": source_property_name,
            "target_property_id": target_property_id,
            "target_property_name": target_property_name,
            "source_booking_id": booking_id,
            "target_booking_id": target_booking_id,
            "reason": (reason or "").strip(),
            "payment_totals": payment_totals,
            "settlement_id": settlement_id,
        }
        for activity_tenant_id, activity_booking_id, action in (
            (tenant_id, booking_id, "property_transfer_sent"),
            (target_property_id, target_booking_id, "property_transfer_received"),
        ):
            await db.reservation_activity_log.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": activity_tenant_id,
                    "booking_id": activity_booking_id,
                    "action": action,
                    "actor": getattr(current_user, "name", None) or getattr(current_user, "email", None) or current_user.id,
                    "details": activity_details,
                    "created_at": now,
                }
            )

        notifications = [
            {
                "id": str(uuid.uuid4()),
                "tenant_id": target_property_id,
                "user_id": None,
                "type": "cross_property_transfer",
                "title": "Zincirden yeni rezervasyon geldi",
                "message": f"{source_property_name} tesisinden {booking.get('guest_name') or 'bir misafir'} için rezervasyon aktarıldı ({transfer_reference}).",
                "priority": "high",
                "target_roles": ["admin", "supervisor", "front_desk", "finance"],
                "read": False,
                "action_url": "/app/reservation-calendar",
                "related_entity": "booking",
                "related_id": target_booking_id,
                "metadata": activity_details,
                "created_at": now,
            }
        ]
        if settlement_id:
            for finance_tenant_id, counterparty_name in (
                (tenant_id, target_property_name),
                (target_property_id, source_property_name),
            ):
                notifications.append(
                    {
                        "id": str(uuid.uuid4()),
                        "tenant_id": finance_tenant_id,
                        "user_id": None,
                        "type": "chain_transfer_settlement",
                        "title": "Zincir içi mahsuplaşma bekliyor",
                        "message": f"{counterparty_name} ile rezervasyon transferi tahsilatı için mutabakat gerekli ({transfer_reference}).",
                        "priority": "high",
                        "target_roles": ["admin", "finance"],
                        "read": False,
                        "action_url": "/app/general-ledger",
                        "related_entity": "chain_transfer_settlement",
                        "related_id": settlement_id,
                        "metadata": activity_details,
                        "created_at": now,
                    }
                )
        try:
            for notification in notifications:
                await db.notifications.insert_one(notification)
        except Exception:
            # The reservation and settlement are durable; leave a loud server
            # trace for retry/repair instead of rolling back a completed room
            # move and risking double inventory.
            logger.exception("Chain transfer notification write failed transfer=%s", transfer_id)

        return {
            "success": True,
            "transfer_id": transfer_id,
            "transfer_reference": transfer_reference,
            "source": tenant_id,
            "target": target_property_id,
            "source_property_name": source_property_name,
            "target_property_name": target_property_name,
            "source_booking_id": booking_id,
            "target_booking_id": target_booking_id,
            "target_room_id": target_booking.get("room_id"),
            "target_room_number": target_booking.get("room_number"),
            "payment_totals": payment_totals,
            "settlement_id": settlement_id,
            "settlement_status": "open" if settlement_id else "not_required",
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
                    "property_name": prop.get("property_name") or prop.get("hotel_name") or prop.get("name", pid),
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
            prop_name = prop.get("property_name") or prop.get("hotel_name") or prop.get("name", pid)
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
