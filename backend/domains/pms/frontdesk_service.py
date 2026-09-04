"""
PMS / Front Desk — Service Layer
Orchestrates check-in, check-out, walk-in bookings, guest alerts,
keycard management, and unified arrivals/departures. No FastAPI dependencies.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from common.audit_hook import SEVERITY_INFO, SEVERITY_WARNING, audited
from common.context import OperationContext
from common.result import ServiceResult
from core.business_date_transition_guard import enforce_business_date_transition
from core.kbs_auto_enqueue import auto_enqueue_kbs
from domains.pms.frontdesk_financials import calculate_departure_balance
from domains.pms.lock_bridge.service import CMD_ENCODE, CMD_REVOKE, enqueue_lock_command

logger = logging.getLogger(__name__)


async def _enqueue_kbs_after_frontdesk_transition(
    ctx: OperationContext,
    booking_id: str,
    action: str,
) -> dict | None:
    """Best-effort KBS hand-off after the PMS transition is durable.

    A temporary browser-extension/KBS problem must never roll back a room
    movement that has already completed. The queue itself is idempotent for
    ``booking + action``, so UI retries remain safe.
    """
    try:
        return await auto_enqueue_kbs(
            ctx.tenant_id,
            booking_id,
            action,
            actor=f"user:{ctx.actor_id}",
        )
    except Exception:  # pragma: no cover - defensive; helper is fail-open by contract
        logger.exception(
            "KBS auto-enqueue failed after front-desk transition: booking=%s action=%s",
            booking_id,
            action,
        )
        return None


class FrontdeskService:
    """Business logic for front desk operations."""

    def __init__(self):
        from core.database import db

        self._db = db

    # ------------------------------------------------------------------
    # Arrivals
    # ------------------------------------------------------------------
    async def get_todays_arrivals(self, ctx: OperationContext) -> ServiceResult:
        today = datetime.now(UTC).date()
        today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=UTC)
        today_end = datetime.combine(today, datetime.max.time()).replace(tzinfo=UTC)

        arrivals = await self._db.bookings.find(
            {
                "tenant_id": ctx.tenant_id,
                "check_in": {"$gte": today_start.isoformat(), "$lte": today_end.isoformat()},
                "status": {"$in": ["confirmed", "guaranteed"]},
            },
            {"_id": 0},
        ).to_list(100)

        from core.guest_name_utils import display_guest_name

        enriched = []
        for b in arrivals:
            guest = await self._db.guests.find_one({"id": b["guest_id"]}, {"_id": 0})
            room = await self._db.rooms.find_one({"id": b.get("room_id")}, {"_id": 0}) if b.get("room_id") else None
            # Walk-in placeholder ("C4", "V4 Refund") tespit edilirse "Misafir <ID8>" fallback.
            raw_name = guest.get("name") if guest else None
            enriched.append(
                {
                    **b,
                    "guest_name": display_guest_name(raw_name, b.get("guest_id")),
                    "guest_email": guest.get("email") if guest else None,
                    "room_number": room.get("room_number") if room else None,
                    "vip_status": guest.get("vip_status", False) if guest else False,
                }
            )

        enriched.sort(
            key=lambda x: (
                -1 if x.get("vip_status") else 0,
                -1 if x.get("group_block_id") else 0,
            ),
            reverse=True,
        )

        return ServiceResult.success(
            {
                "arrivals": enriched,
                "total": len(enriched),
                "vip_count": len([a for a in enriched if a.get("vip_status")]),
                "group_count": len([a for a in enriched if a.get("group_block_id")]),
                "online_checkin_count": len([a for a in enriched if a.get("online_checkin_completed")]),
            }
        )

    # ------------------------------------------------------------------
    # Check-in
    # ------------------------------------------------------------------
    @audited("frontdesk.checkin", "booking", severity=SEVERITY_INFO, capture_before=True)
    async def checkin(self, ctx: OperationContext, booking_id: str, create_folio: bool = True, force_clean: bool = False) -> ServiceResult:
        booking = await self._db.bookings.find_one({"id": booking_id, "tenant_id": ctx.tenant_id}, {"_id": 0})
        if not booking:
            return ServiceResult.fail("Booking not found", "NOT_FOUND")
        booking_status = booking.get("status")
        if booking_status == "checked_in":
            return ServiceResult.fail("Guest already checked in", "ALREADY_CHECKED_IN")
        if booking_status not in {"confirmed", "guaranteed"}:
            return ServiceResult.fail("Booking status is not eligible for check-in", "INVALID_BOOKING_STATUS")

        room_id = booking.get("room_id")
        if not room_id:
            return ServiceResult.fail("Assign a room before check-in", "ROOM_ASSIGNMENT_REQUIRED")

        try:
            await enforce_business_date_transition(
                self._db,
                tenant_id=ctx.tenant_id,
                booking=booking,
                operation="check_in",
                error_cls=ValueError,
            )
        except ValueError as exc:
            return ServiceResult.fail(str(exc), "BUSINESS_DATE_MISMATCH")

        room = await self._db.rooms.find_one(
            {"id": room_id, "tenant_id": ctx.tenant_id},
            {"_id": 0},
        )
        if not room:
            return ServiceResult.fail("Assigned room was not found for this hotel", "ROOM_ASSIGNMENT_REQUIRED")

        # If room is dirty/cleaning and force_clean requested, clean it first
        room_status = room.get("status")
        if room_status in ("dirty", "cleaning") and force_clean:
            await self._db.rooms.update_one(
                {"id": room["id"], "tenant_id": ctx.tenant_id},
                {"$set": {"status": "available"}},
            )
        elif room_status == "occupied":
            # Use room's own current_booking_id for authoritative occupancy check
            blocker_id = room.get("current_booking_id")
            if blocker_id and blocker_id != booking_id:
                blocker = await self._db.bookings.find_one(
                    {
                        "id": blocker_id,
                        "tenant_id": ctx.tenant_id,
                        "status": "checked_in",
                    }
                )
                if blocker:
                    return ServiceResult.fail("Room is occupied by another guest", "ROOM_NOT_READY")
            # Stale occupied status or no active blocker — allow check-in
        elif room_status not in ("available", "inspected"):
            return ServiceResult.fail("Room is not ready for check-in", "ROOM_NOT_READY")

        if create_folio:
            existing_folio = await self._db.folios.find_one(
                {
                    "booking_id": booking_id,
                    "tenant_id": ctx.tenant_id,
                    "folio_type": "guest",
                }
            )
            if not existing_folio:
                folio_number = f"F-{datetime.now().year}-{uuid.uuid4().hex[:5].upper()}"
                folio_id = str(uuid.uuid4())
                folio_doc = {
                    "id": folio_id,
                    "tenant_id": ctx.tenant_id,
                    "booking_id": booking_id,
                    "folio_number": folio_number,
                    "folio_type": "guest",
                    "guest_id": booking.get("guest_id"),
                    "status": "open",
                    "balance": 0.0,
                    "created_at": datetime.now(UTC).isoformat(),
                }
                await self._db.folios.insert_one(folio_doc)

        checked_in_time = datetime.now(UTC)
        booking_result = await self._db.bookings.update_one(
            {
                "id": booking_id,
                "tenant_id": ctx.tenant_id,
                "status": {"$in": ["confirmed", "guaranteed"]},
            },
            {"$set": {"status": "checked_in", "checked_in_at": checked_in_time.isoformat()}},
        )
        if booking_result.modified_count != 1:
            return ServiceResult.fail("Booking state changed during check-in", "CHECKIN_STATE_CONFLICT")

        room_result = await self._db.rooms.update_one(
            {"id": room_id, "tenant_id": ctx.tenant_id},
            {"$set": {"status": "occupied", "current_booking_id": booking_id}},
        )
        if room_result.matched_count != 1:
            return ServiceResult.fail("Assigned room changed during check-in", "CHECKIN_STATE_CONFLICT")

        guest_id = booking.get("guest_id")
        if guest_id:
            await self._db.guests.update_one(
                {"id": guest_id, "tenant_id": ctx.tenant_id},
                {"$inc": {"total_stays": 1}},
            )

        kbs_job = await _enqueue_kbs_after_frontdesk_transition(
            ctx,
            booking_id,
            "checkin",
        )

        return ServiceResult.success(
            {
                "message": "Check-in completed successfully",
                "checked_in_at": checked_in_time.isoformat(),
                "room_number": room.get("room_number"),
                "kbs_queued": bool(kbs_job),
                "kbs_job_id": (kbs_job or {}).get("id"),
            }
        )

    # ------------------------------------------------------------------
    # Check-out
    # ------------------------------------------------------------------
    @audited("frontdesk.checkout", "booking", severity=SEVERITY_INFO, capture_before=True)
    async def checkout(
        self,
        ctx: OperationContext,
        booking_id: str,
        force: bool = False,
        auto_close_folios: bool = True,
    ) -> ServiceResult:
        booking = await self._db.bookings.find_one({"id": booking_id, "tenant_id": ctx.tenant_id}, {"_id": 0})
        if not booking:
            return ServiceResult.fail("Booking not found", "NOT_FOUND")
        if booking["status"] == "checked_out":
            return ServiceResult.fail("Guest already checked out", "ALREADY_CHECKED_OUT")

        # Finalise room revenue before evaluating the departure balance.  A
        # full prepayment must not leave a negative folio merely because the
        # last nightly charge has not run yet.
        try:
            from core.folio_checkout_reconciliation import reconcile_unposted_room_charge

            await reconcile_unposted_room_charge(
                self._db,
                tenant_id=ctx.tenant_id,
                booking=booking,
                posted_by=f"checkout:{ctx.actor_id}",
            )
        except ValueError as exc:
            return ServiceResult.fail(str(exc), "ROOM_CHARGE_RECONCILIATION_FAILED")

        folios = await self._db.folios.find(
            {
                "booking_id": booking_id,
                "tenant_id": ctx.tenant_id,
                "status": "open",
            }
        ).to_list(100)

        # v95.7: KVB auto_post — config'te aktifse, balance hesabı yapılmadan
        # ÖNCE konaklama vergisi satırı folio'ya idempotent eklensin; aksi
        # halde checkbox açık olsa bile satır hiç oluşmuyordu.
        try:
            from routers.finance.konaklama_vergisi_core import (
                load_tax_config,
                post_konaklama_vergisi_to_folio,
            )

            cfg = await load_tax_config(ctx.tenant_id)
            if cfg.get("active", True) and cfg.get("auto_post"):
                for f in folios:
                    await post_konaklama_vergisi_to_folio(
                        tenant_id=ctx.tenant_id,
                        folio_id=f["id"],
                        posted_by=f"system:checkout:{ctx.actor_id}",
                        raise_on_error=False,
                    )
                # Balance değişmiş olabilir — folio doc'larını yenile.
                folios = await self._db.folios.find(
                    {
                        "booking_id": booking_id,
                        "tenant_id": ctx.tenant_id,
                        "status": "open",
                    }
                ).to_list(100)
        except Exception as exc:  # pragma: no cover
            logger.warning("KVB auto_post (checkout) failed: %s", exc)

        cached_folio_balance = 0.0
        folio_details = []
        for folio in folios:
            balance = folio.get("balance", 0.0)
            cached_folio_balance += balance
            folio_details.append(
                {
                    "folio_number": folio.get("folio_number"),
                    "folio_type": folio.get("folio_type"),
                    "balance": balance,
                }
            )

        # Cached folio/booking totals can drift after charge splits and legacy
        # imports. Rebuild the checkout balance from the durable rows used by
        # the reservation summary and departure queue.
        ledger_filter = {"booking_id": booking_id, "tenant_id": ctx.tenant_id}
        charges = await self._db.folio_charges.find(ledger_filter, {"_id": 0}).to_list(10_000)
        payments = await self._db.payments.find(ledger_filter, {"_id": 0}).to_list(10_000)
        extra_charges = await self._db.extra_charges.find(ledger_filter, {"_id": 0}).to_list(10_000)
        effective_balance = round(
            calculate_departure_balance(
                charges,
                payments,
                extra_charges,
                booking_total=booking.get("total_amount", 0),
            ),
            2,
        )

        if effective_balance > 0.01 and not force:
            return ServiceResult.fail(
                f"Outstanding balance: {effective_balance:.2f}",
                "OUTSTANDING_BALANCE",
                folio_details=folio_details,
                durable_balance=effective_balance,
                cached_folio_balance=round(cached_folio_balance, 2),
            )

        if auto_close_folios and effective_balance <= 0.01:
            for folio in folios:
                await self._db.folios.update_one(
                    {"id": folio["id"], "tenant_id": ctx.tenant_id},
                    {"$set": {"status": "closed", "balance": 0.0, "closed_at": datetime.now(UTC).isoformat()}},
                )

        checked_out_time = datetime.now(UTC)
        await self._db.bookings.update_one(
            {"id": booking_id, "tenant_id": ctx.tenant_id},
            {"$set": {"status": "checked_out", "checked_out_at": checked_out_time.isoformat()}},
        )
        await self._db.rooms.update_one(
            {"id": booking["room_id"], "tenant_id": ctx.tenant_id},
            {"$set": {"status": "dirty", "current_booking_id": None}},
        )

        hk_task = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            "room_id": booking["room_id"],
            "task_type": "cleaning",
            "priority": "high",
            "status": "new",
            "notes": "Guest checked out - departure clean required",
            "created_at": datetime.now(UTC).isoformat(),
        }
        await self._db.housekeeping_tasks.insert_one(hk_task)

        kbs_job = await _enqueue_kbs_after_frontdesk_transition(
            ctx,
            booking_id,
            "checkout",
        )

        return ServiceResult.success(
            {
                "message": "Check-out completed successfully",
                "checked_out_at": checked_out_time.isoformat(),
                "total_balance": effective_balance,
                "folios_closed": len(folios) if auto_close_folios else 0,
                "folio_details": folio_details,
                "kbs_queued": bool(kbs_job),
                "kbs_job_id": (kbs_job or {}).get("id"),
            }
        )

    # ------------------------------------------------------------------
    # Express / Kiosk Check-in
    # ------------------------------------------------------------------
    @audited("frontdesk.express_checkin", "booking", severity=SEVERITY_INFO)
    async def express_checkin(self, ctx: OperationContext, qr_code: str) -> ServiceResult:
        booking = await self._db.bookings.find_one(
            {"express_checkin_code": qr_code, "tenant_id": ctx.tenant_id},
            {"_id": 0},
        )
        if not booking:
            return ServiceResult.fail("QR code gecersiz", "INVALID_QR")
        if booking.get("status") not in {"confirmed", "guaranteed"}:
            return ServiceResult.fail("Rezervasyon check-in için uygun durumda değil", "INVALID_BOOKING_STATUS")
        try:
            await enforce_business_date_transition(
                self._db,
                tenant_id=ctx.tenant_id,
                booking=booking,
                operation="check_in",
                error_cls=ValueError,
            )
        except ValueError as exc:
            return ServiceResult.fail(str(exc), "BUSINESS_DATE_MISMATCH")
        await self._db.bookings.update_one(
            {"id": booking["id"], "tenant_id": ctx.tenant_id},
            {"$set": {"status": "checked_in", "checked_in_at": datetime.now(UTC).isoformat()}},
        )
        kbs_job = await _enqueue_kbs_after_frontdesk_transition(
            ctx,
            booking["id"],
            "checkin",
        )
        return ServiceResult.success(
            {
                "success": True,
                "message": "Express check-in tamamlandi",
                "booking": booking,
                "kbs_queued": bool(kbs_job),
                "kbs_job_id": (kbs_job or {}).get("id"),
            }
        )

    # ------------------------------------------------------------------
    # Audit Checklist
    # ------------------------------------------------------------------
    async def get_audit_checklist(self, ctx: OperationContext) -> ServiceResult:
        today = datetime.now(UTC).date()
        today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=UTC)
        today_end = datetime.combine(today, datetime.max.time()).replace(tzinfo=UTC)

        unchecked = []
        async for b in self._db.bookings.find(
            {
                "tenant_id": ctx.tenant_id,
                "check_in": {"$gte": today_start.isoformat(), "$lte": today_end.isoformat()},
                "status": {"$in": ["confirmed", "guaranteed"]},
            },
            {"_id": 0},
        ):
            if b.get("checked_in_at"):
                continue
            guest = await self._db.guests.find_one({"id": b.get("guest_id")}, {"_id": 0})
            room = await self._db.rooms.find_one({"id": b.get("room_id")}, {"_id": 0}) if b.get("room_id") else None
            from core.guest_name_utils import display_guest_name

            raw_name = guest.get("name") if guest else None
            unchecked.append(
                {
                    "booking_id": b.get("id"),
                    "reservation_number": b.get("reservation_number"),
                    "guest_name": display_guest_name(raw_name, b.get("guest_id")),
                    "guest_email": guest.get("email") if guest else None,
                    "room_number": room.get("room_number") if room else None,
                    "vip_status": guest.get("vip_status", False) if guest else False,
                    "check_in": b.get("check_in"),
                    "check_out": b.get("check_out"),
                }
            )

        open_folios = await self._db.folios.find({"tenant_id": ctx.tenant_id, "status": "open"}, {"_id": 0}).to_list(2000)
        open_with_balance = []
        unbalanced = []
        overdue = []

        for folio in open_folios:
            balance = folio.get("balance", 0.0)
            if not balance or abs(balance) <= 0.01:
                continue
            owner_name = None
            if folio.get("folio_type") == "guest" and folio.get("guest_id"):
                g = await self._db.guests.find_one({"id": folio["guest_id"]}, {"_id": 0})
                if g:
                    from core.guest_name_utils import display_guest_name

                    owner_name = display_guest_name(g.get("name"), folio["guest_id"])
            item = {
                "folio_id": folio.get("id"),
                "folio_number": folio.get("folio_number"),
                "folio_type": folio.get("folio_type"),
                "owner_name": owner_name,
                "balance": round(balance, 2),
                "status": folio.get("status"),
                "booking_id": folio.get("booking_id"),
            }
            open_with_balance.append(item)

            try:
                created_at = folio.get("created_at")
                days_open = None
                if created_at:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    days_open = (datetime.now(UTC) - dt).days
            except Exception:
                days_open = None
            if days_open and days_open > 2 and balance > 0:
                unbalanced.append({**item, "days_open": days_open})

        summary = {
            "unchecked_in_count": len(unchecked),
            "open_folio_count": len(open_with_balance),
            "total_open_balance": round(sum(f["balance"] for f in open_with_balance), 2),
            "unbalanced_folio_count": len(unbalanced),
            "overdue_departures_count": len(overdue),
        }
        return ServiceResult.success(
            {
                "date": today.isoformat(),
                "tenant_id": ctx.tenant_id,
                "unchecked_in_arrivals": unchecked,
                "open_folios": open_with_balance,
                "unbalanced_folios": unbalanced,
                "overdue_departures": overdue,
                "summary": summary,
            }
        )

    # ------------------------------------------------------------------
    # Guest Alerts
    # ------------------------------------------------------------------
    async def get_guest_alerts(self, ctx: OperationContext, guest_id: str) -> ServiceResult:
        guest = await self._db.guests.find_one({"id": guest_id, "tenant_id": ctx.tenant_id}, {"_id": 0})
        if not guest:
            return ServiceResult.fail("Guest not found", "NOT_FOUND")

        alerts: list[dict[str, Any]] = []
        if guest.get("vip_status"):
            alerts.append({"type": "vip", "priority": "high", "title": "VIP Guest", "description": f"{guest.get('name')} is a VIP guest.", "color": "gold"})

        current_booking = await self._db.bookings.find_one(
            {
                "guest_id": guest_id,
                "tenant_id": ctx.tenant_id,
                "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
            },
            sort=[("created_at", -1)],
        )
        if current_booking and current_booking.get("special_requests"):
            alerts.append({"type": "special_request", "priority": "high", "title": "Special Request", "description": current_booking["special_requests"], "color": "blue"})

        if guest.get("loyalty_points", 0) > 1000:
            tier = "Gold" if guest["loyalty_points"] > 5000 else "Silver"
            alerts.append(
                {
                    "type": "loyalty",
                    "priority": "normal",
                    "title": f"{tier} Member",
                    "description": f"Loyalty member with {guest['loyalty_points']} points",
                    "color": "gold" if tier == "Gold" else "silver",
                }
            )

        custom = []
        async for a in self._db.guest_alerts.find(
            {
                "guest_id": guest_id,
                "tenant_id": ctx.tenant_id,
                "is_active": True,
            }
        ):
            custom.append({"type": a.get("alert_type"), "priority": a.get("priority"), "title": a.get("title"), "description": a.get("description"), "color": "orange"})
        alerts.extend(custom)

        priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
        alerts.sort(key=lambda x: priority_order.get(x.get("priority", "normal"), 2))

        from core.guest_name_utils import display_guest_name

        return ServiceResult.success(
            {
                "guest_id": guest_id,
                "guest_name": display_guest_name(guest.get("name"), guest_id),
                "total_alerts": len(alerts),
                "alerts": alerts,
            }
        )

    # ------------------------------------------------------------------
    # Unified Arrivals / Departures / In-House
    # ------------------------------------------------------------------
    async def get_unified_arrivals(self, ctx: OperationContext) -> ServiceResult:
        today = datetime.now(UTC).date().isoformat()
        bookings = await self._db.bookings.find(
            {
                "check_in": today,
                "status": {"$in": ["confirmed", "guaranteed"]},
                "tenant_id": ctx.tenant_id,
            },
            {"_id": 0},
        ).to_list(100)
        enriched = await self._enrich_bookings(bookings, ctx.tenant_id)
        return ServiceResult.success({"arrivals": enriched, "count": len(enriched), "date": today})

    async def get_unified_departures(self, ctx: OperationContext) -> ServiceResult:
        today = datetime.now(UTC).date().isoformat()
        bookings = await self._db.bookings.find(
            {
                "check_out": today,
                "status": "checked_in",
                "tenant_id": ctx.tenant_id,
            },
            {"_id": 0},
        ).to_list(100)
        enriched = await self._enrich_bookings(bookings, ctx.tenant_id)
        return ServiceResult.success({"departures": enriched, "count": len(enriched), "date": today})

    async def get_unified_inhouse(self, ctx: OperationContext) -> ServiceResult:
        bookings = await self._db.bookings.find(
            {
                "status": "checked_in",
                "tenant_id": ctx.tenant_id,
            },
            {"_id": 0},
        ).to_list(500)
        enriched = await self._enrich_bookings(bookings, ctx.tenant_id)
        return ServiceResult.success({"in_house": enriched, "count": len(enriched)})

    # ------------------------------------------------------------------
    # Folio
    # ------------------------------------------------------------------
    async def get_folio(self, ctx: OperationContext, booking_id: str) -> ServiceResult:
        booking = await self._db.bookings.find_one(
            {"id": booking_id, "tenant_id": ctx.tenant_id},
            {"_id": 0, "id": 1},
        )
        if not booking:
            return ServiceResult.fail("Booking not found", "NOT_FOUND")
        charges = await self._db.folio_charges.find({"booking_id": booking_id, "tenant_id": ctx.tenant_id}, {"_id": 0}).to_list(1000)
        payments = await self._db.payments.find({"booking_id": booking_id, "tenant_id": ctx.tenant_id}, {"_id": 0}).to_list(1000)
        total_charges = sum(c["total"] for c in charges)
        total_paid = sum(p["amount"] for p in payments if p["status"] == "paid")
        return ServiceResult.success(
            {
                "charges": charges,
                "payments": payments,
                "total_charges": total_charges,
                "total_paid": total_paid,
                "balance": total_charges - total_paid,
            }
        )

    async def get_arrivals(self, ctx: OperationContext, date_str: str | None = None) -> ServiceResult:
        target_date = datetime.fromisoformat(date_str).date() if date_str else datetime.now(UTC).date()
        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())
        bookings = await self._db.bookings.find(
            {
                "tenant_id": ctx.tenant_id,
                "status": {"$in": ["confirmed", "checked_in"]},
                "check_in": {"$gte": start.isoformat(), "$lte": end.isoformat()},
            },
            {"_id": 0},
        ).to_list(1000)
        if not bookings:
            return ServiceResult.success([])

        guest_ids = list({b["guest_id"] for b in bookings if b.get("guest_id")})
        room_ids = list({b["room_id"] for b in bookings if b.get("room_id")})
        guest_map, room_map = {}, {}
        if guest_ids:
            async for g in self._db.guests.find({"id": {"$in": guest_ids}, "tenant_id": ctx.tenant_id}, {"_id": 0}):
                guest_map[g["id"]] = g
        if room_ids:
            async for r in self._db.rooms.find({"id": {"$in": room_ids}, "tenant_id": ctx.tenant_id}, {"_id": 0}):
                room_map[r["id"]] = r

        enriched = [{**b, "guest": guest_map.get(b.get("guest_id")), "room": room_map.get(b.get("room_id"))} for b in bookings]
        return ServiceResult.success(enriched)

    async def get_departures(self, ctx: OperationContext, date_str: str | None = None) -> ServiceResult:
        target_date = datetime.fromisoformat(date_str).date() if date_str else datetime.now(UTC).date()
        start = target_date.isoformat()
        end = (target_date + timedelta(days=1)).isoformat()
        bookings = await self._db.bookings.find(
            {
                "tenant_id": ctx.tenant_id,
                "status": "checked_in",
                "check_out": {"$gte": start, "$lt": end},
            },
            {"_id": 0},
        ).to_list(1000)
        if not bookings:
            return ServiceResult.success([])

        booking_ids = [b["id"] for b in bookings if b.get("id")]
        guest_ids = list({b["guest_id"] for b in bookings if b.get("guest_id")})
        room_ids = list({b["room_id"] for b in bookings if b.get("room_id")})

        guest_map, room_map = {}, {}
        charges_by_booking, payments_by_booking, extras_by_booking = {}, {}, {}

        if guest_ids:
            async for g in self._db.guests.find({"id": {"$in": guest_ids}, "tenant_id": ctx.tenant_id}, {"_id": 0}):
                guest_map[g["id"]] = g
        if room_ids:
            async for r in self._db.rooms.find({"id": {"$in": room_ids}, "tenant_id": ctx.tenant_id}, {"_id": 0}):
                room_map[r["id"]] = r
        if booking_ids:
            async for c in self._db.folio_charges.find({"booking_id": {"$in": booking_ids}, "tenant_id": ctx.tenant_id}, {"_id": 0}):
                charges_by_booking.setdefault(c["booking_id"], []).append(c)
            async for p in self._db.payments.find({"booking_id": {"$in": booking_ids}, "tenant_id": ctx.tenant_id}, {"_id": 0}):
                payments_by_booking.setdefault(p["booking_id"], []).append(p)
            async for charge in self._db.extra_charges.find(
                {"booking_id": {"$in": booking_ids}, "tenant_id": ctx.tenant_id},
                {"_id": 0},
            ):
                extras_by_booking.setdefault(charge["booking_id"], []).append(charge)

        enriched = []
        for b in bookings:
            charges = charges_by_booking.get(b["id"], [])
            payments = payments_by_booking.get(b["id"], [])
            extras = extras_by_booking.get(b["id"], [])
            balance = calculate_departure_balance(
                charges,
                payments,
                extras,
                booking_total=b.get("total_amount", 0),
            )
            guest = guest_map.get(b.get("guest_id")) or {}
            room = room_map.get(b.get("room_id")) or {}
            guest_name = guest.get("name") or f"{guest.get('first_name', '')} {guest.get('last_name', '')}".strip()
            enriched.append(
                {
                    **b,
                    "guest": guest or None,
                    "room": room or None,
                    "guest_name": guest_name or b.get("guest_name"),
                    "room_number": room.get("room_number") or b.get("room_number"),
                    "balance": balance,
                }
            )
        return ServiceResult.success(enriched)

    async def get_inhouse(self, ctx: OperationContext) -> ServiceResult:
        bookings = await self._db.bookings.find({"tenant_id": ctx.tenant_id, "status": "checked_in"}, {"_id": 0}).to_list(1000)
        if not bookings:
            return ServiceResult.success([])

        booking_ids = [b["id"] for b in bookings if b.get("id")]
        guest_ids = list({b["guest_id"] for b in bookings if b.get("guest_id")})
        room_ids = list({b["room_id"] for b in bookings if b.get("room_id")})
        guest_map, room_map = {}, {}
        charges_by_booking, payments_by_booking, extras_by_booking = {}, {}, {}

        if guest_ids:
            async for g in self._db.guests.find({"id": {"$in": guest_ids}, "tenant_id": ctx.tenant_id}, {"_id": 0}):
                guest_map[g["id"]] = g
        if room_ids:
            async for r in self._db.rooms.find({"id": {"$in": room_ids}, "tenant_id": ctx.tenant_id}, {"_id": 0}):
                room_map[r["id"]] = r
        if booking_ids:
            async for charge in self._db.folio_charges.find(
                {"booking_id": {"$in": booking_ids}, "tenant_id": ctx.tenant_id},
                {"_id": 0},
            ):
                charges_by_booking.setdefault(charge["booking_id"], []).append(charge)
            async for payment in self._db.payments.find(
                {"booking_id": {"$in": booking_ids}, "tenant_id": ctx.tenant_id},
                {"_id": 0},
            ):
                payments_by_booking.setdefault(payment["booking_id"], []).append(payment)
            async for charge in self._db.extra_charges.find(
                {"booking_id": {"$in": booking_ids}, "tenant_id": ctx.tenant_id},
                {"_id": 0},
            ):
                extras_by_booking.setdefault(charge["booking_id"], []).append(charge)

        enriched = []
        for booking in bookings:
            booking_id = booking["id"]
            guest = guest_map.get(booking.get("guest_id")) or {}
            room = room_map.get(booking.get("room_id")) or {}
            guest_name = guest.get("name") or f"{guest.get('first_name', '')} {guest.get('last_name', '')}".strip()
            balance = calculate_departure_balance(
                charges_by_booking.get(booking_id, []),
                payments_by_booking.get(booking_id, []),
                extras_by_booking.get(booking_id, []),
                booking_total=booking.get("total_amount", 0),
            )
            enriched.append(
                {
                    **booking,
                    "guest": guest or None,
                    "room": room or None,
                    "guest_name": guest_name or booking.get("guest_name"),
                    "room_number": room.get("room_number") or booking.get("room_number"),
                    "balance": balance,
                }
            )
        return ServiceResult.success(enriched)

    # ------------------------------------------------------------------
    # Keycard
    # ------------------------------------------------------------------
    @audited("frontdesk.issue_keycard", "keycard", severity=SEVERITY_INFO)
    async def issue_keycard(self, ctx: OperationContext, booking_id: str, card_type: str = "physical", validity_hours: int = 72) -> ServiceResult:
        booking = await self._db.bookings.find_one({"id": booking_id, "tenant_id": ctx.tenant_id})
        if not booking:
            return ServiceResult.fail("Booking not found", "NOT_FOUND")
        if booking["status"] not in ("confirmed", "guaranteed", "checked_in"):
            return ServiceResult.fail("Booking must be confirmed or checked-in", "INVALID_STATUS")

        room = await self._db.rooms.find_one({"id": booking.get("room_id")})
        if not room:
            return ServiceResult.fail("Room not assigned", "NO_ROOM")

        keycard_id = str(uuid.uuid4())
        issue_time = datetime.now(UTC)
        expiry_time = issue_time + timedelta(hours=validity_hours)

        keycard_data = {
            "id": keycard_id,
            "booking_id": booking_id,
            "room_id": booking["room_id"],
            "room_number": room["room_number"],
            "guest_id": booking["guest_id"],
            "guest_name": booking.get("guest_name", ""),
            "card_type": card_type,
            "issued_at": issue_time.isoformat(),
            "expires_at": expiry_time.isoformat(),
            "issued_by": ctx.actor_id,
            "status": "active",
            "access_areas": ["room", "elevator", "gym", "pool"],
            "tenant_id": ctx.tenant_id,
        }
        if card_type == "physical":
            keycard_data["card_number"] = f"RFID-{room['room_number']}-{datetime.now().strftime('%Y%m%d%H%M')}"
        elif card_type == "mobile":
            keycard_data["mobile_key_token"] = f"MOB-{keycard_id[:16]}"
        elif card_type == "qr":
            keycard_data["qr_code"] = f"QR-{keycard_id}"

        await self._db.keycards.insert_one(keycard_data)
        if card_type == "physical":
            # Drive the physical lock: ask the on-prem connector to encode the card.
            await enqueue_lock_command(
                self._db,
                tenant_id=ctx.tenant_id,
                command=CMD_ENCODE,
                keycard_id=keycard_id,
                booking_id=booking_id,
                room_number=room["room_number"],
                card_number=keycard_data.get("card_number"),
                valid_from=issue_time.isoformat(),
                valid_until=expiry_time.isoformat(),
            )
        return ServiceResult.success(
            {
                "message": f"{card_type.capitalize()} keycard issued successfully",
                "keycard_id": keycard_id,
                "card_type": card_type,
                "room_number": room["room_number"],
                "issued_at": issue_time.isoformat(),
                "expires_at": expiry_time.isoformat(),
                "validity_hours": validity_hours,
            }
        )

    @audited("frontdesk.deactivate_keycard", "keycard", severity=SEVERITY_WARNING)
    async def deactivate_keycard(self, ctx: OperationContext, keycard_id: str, reason: str = "checkout") -> ServiceResult:
        keycard = await self._db.keycards.find_one({"id": keycard_id, "tenant_id": ctx.tenant_id})
        if not keycard:
            return ServiceResult.fail("Keycard not found", "NOT_FOUND")
        await self._db.keycards.update_one(
            {"id": keycard_id},
            {"$set": {"status": "deactivated", "deactivated_at": datetime.now(UTC).isoformat(), "deactivated_by": ctx.actor_id, "deactivation_reason": reason}},
        )
        if keycard.get("card_type") == "physical":
            # Revoke the physical card on the lock via the on-prem connector.
            await enqueue_lock_command(
                self._db,
                tenant_id=ctx.tenant_id,
                command=CMD_REVOKE,
                keycard_id=keycard_id,
                booking_id=keycard.get("booking_id"),
                room_number=keycard.get("room_number"),
                card_number=keycard.get("card_number"),
            )
        return ServiceResult.success({"message": "Keycard deactivated", "keycard_id": keycard_id, "reason": reason})

    async def get_booking_keycards(self, ctx: OperationContext, booking_id: str) -> ServiceResult:
        keycards = await self._db.keycards.find({"booking_id": booking_id, "tenant_id": ctx.tenant_id}).sort("issued_at", -1).to_list(20)
        for k in keycards:
            k.pop("_id", None)
        return ServiceResult.success({"keycards": keycards, "count": len(keycards), "active_count": len([k for k in keycards if k.get("status") == "active"])})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _enrich_bookings(self, bookings: list, tenant_id: str) -> list:
        if not bookings:
            return []
        guest_ids = list({b["guest_id"] for b in bookings if b.get("guest_id")})
        room_ids = list({b["room_id"] for b in bookings if b.get("room_id")})
        guest_map = {}
        if guest_ids:
            from security.encrypted_lookup import decrypt_guest_doc

            async for g in self._db.guests.find(
                {"tenant_id": tenant_id, "id": {"$in": guest_ids}},
                {"_id": 0, "id": 1, "name": 1, "phone": 1, "email": 1},
            ):
                g = decrypt_guest_doc(g)
                guest_map[g["id"]] = g
        room_map = {}
        if room_ids:
            async for r in self._db.rooms.find(
                {"tenant_id": tenant_id, "id": {"$in": room_ids}},
                {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "status": 1},
            ):
                room_map[r["id"]] = r
        from core.guest_name_utils import display_guest_name

        for b in bookings:
            guest = guest_map.get(b.get("guest_id"))
            if guest:
                b["guest_name"] = display_guest_name(guest.get("name"), b.get("guest_id"))
                b["guest_phone"] = guest.get("phone")
                b["guest_email"] = guest.get("email")
            room = room_map.get(b.get("room_id"))
            if room:
                b["room_number"] = room.get("room_number")
                b["room_type"] = room.get("room_type")
                b["room_status"] = room.get("status")
        return bookings


frontdesk_service = FrontdeskService()
