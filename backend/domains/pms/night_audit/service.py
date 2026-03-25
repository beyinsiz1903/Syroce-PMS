"""
Night Audit — Core Service (Production-Grade)
Orchestrates the nightly audit process: business date roll, room charge posting,
no-show handling, folio balancing, tax validation, and exception management.
"""
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from common.audit_hook import SEVERITY_CRITICAL, audited
from common.context import OperationContext
from common.result import ServiceResult
from domains.pms.night_audit.validations import validate_pre_audit

logger = logging.getLogger(__name__)

# Tax rates (Turkey)
DEFAULT_VAT_RATE = 0.10
ACCOMMODATION_TAX_RATE = 0.02


class NightAuditCoreService:
    """Production-grade night audit engine."""

    def __init__(self):
        from core.database import db
        self._db = db
        self._lock_collection = "night_audit_locks"

    # ── Idempotency guard ──────────────────────────────────────────────
    async def _acquire_lock(self, tenant_id: str, business_date: str) -> str | None:
        lock_id = str(uuid.uuid4())
        try:
            result = await self._db[self._lock_collection].update_one(
                {"tenant_id": tenant_id, "business_date": business_date, "released": False},
                {"$setOnInsert": {
                    "id": lock_id,
                    "tenant_id": tenant_id,
                    "business_date": business_date,
                    "acquired_at": datetime.now(UTC).isoformat(),
                    "released": False,
                }},
                upsert=True,
            )
            if result.upserted_id is not None:
                return lock_id
            return None
        except Exception:
            return None

    async def _release_lock(self, tenant_id: str, business_date: str):
        await self._db[self._lock_collection].update_one(
            {"tenant_id": tenant_id, "business_date": business_date},
            {"$set": {"released": True, "released_at": datetime.now(UTC).isoformat()}},
        )

    # ── Main entry point ───────────────────────────────────────────────
    @audited("night_audit.run", "night_audit_run", severity=SEVERITY_CRITICAL, capture_before=False)
    async def run_night_audit(
        self,
        ctx: OperationContext,
        business_date: str | None = None,
        force_rerun: bool = False,
        skip_validations: bool = False,
        dry_run: bool = False,
        reason: str | None = None,
    ) -> ServiceResult:
        start_ts = time.monotonic()
        bd = business_date or datetime.now(UTC).date().isoformat()

        # 1. Idempotency: check previous successful run
        if not force_rerun:
            prev = await self._db.night_audit_runs.find_one({
                "tenant_id": ctx.tenant_id,
                "business_date": bd,
                "status": {"$in": ["completed", "completed_with_exceptions"]},
            })
            if prev:
                return ServiceResult.fail(
                    f"Night audit already completed for {bd}. Use force_rerun=true to re-run.",
                    "ALREADY_COMPLETED",
                )

        # 2. Acquire lock (concurrent guard)
        lock_id = await self._acquire_lock(ctx.tenant_id, bd)
        if not lock_id:
            return ServiceResult.fail(
                "Night audit is already running for this business date",
                "CONCURRENT_LOCK",
            )

        audit_id = str(uuid.uuid4())
        exceptions: list[dict[str, Any]] = []

        try:
            # 3. Pre-audit validations
            if not skip_validations:
                validation = await validate_pre_audit(self._db, ctx.tenant_id, bd)
                if not validation["passed"]:
                    await self._release_lock(ctx.tenant_id, bd)
                    return ServiceResult.fail(
                        "Pre-audit validation failed",
                        "VALIDATION_FAILED",
                        blockers=validation["blockers"],
                        warnings=validation["warnings"],
                    )
                # Store warnings as exceptions
                for w in validation.get("warnings", []):
                    exceptions.append(self._make_exception(
                        audit_id, ctx.tenant_id, "warning", "pre_validation",
                        "system", None, w["message"], w,
                    ))

            # 4. Create audit run record
            run_doc = {
                "id": audit_id,
                "tenant_id": ctx.tenant_id,
                "business_date": bd,
                "status": "running",
                "is_rerun": force_rerun,
                "is_dry_run": dry_run,
                "initiated_by": ctx.actor_id,
                "reason": reason,
                "started_at": datetime.now(UTC).isoformat(),
                "rooms_processed": 0,
                "charges_posted": 0,
                "total_room_revenue": 0.0,
                "total_tax_amount": 0.0,
                "no_shows_processed": 0,
                "arrivals_pending": 0,
                "departures_pending": 0,
                "folios_balanced": 0,
                "folios_unbalanced": 0,
            }
            if not dry_run:
                await self._db.night_audit_runs.insert_one({**run_doc})

            # 5. Execute audit steps
            rooms_processed, charges_posted, total_rev, total_tax = await self._post_room_charges(
                ctx, bd, audit_id, exceptions, dry_run
            )
            no_shows = await self._process_no_shows(ctx, bd, audit_id, exceptions, dry_run)
            arrivals_pending = await self._validate_pending_arrivals(ctx, bd, audit_id, exceptions)
            departures_pending = await self._validate_pending_departures(ctx, bd, audit_id, exceptions)
            balanced, unbalanced = await self._check_folio_balances(ctx, audit_id, exceptions)
            await self._validate_tax_consistency(ctx, bd, audit_id, exceptions)

            # 6. Business date roll
            if not dry_run:
                await self._roll_business_date(ctx, bd)

            # 7. Finalize
            duration_ms = int((time.monotonic() - start_ts) * 1000)
            status = "completed" if len([e for e in exceptions if e["severity"] in ("error", "critical")]) == 0 else "completed_with_exceptions"

            summary = {
                "audit_id": audit_id,
                "tenant_id": ctx.tenant_id,
                "business_date": bd,
                "status": status,
                "duration_ms": duration_ms,
                "rooms_processed": rooms_processed,
                "charges_posted": charges_posted,
                "total_room_revenue": round(total_rev, 2),
                "total_tax_amount": round(total_tax, 2),
                "no_shows_processed": no_shows,
                "arrivals_pending": arrivals_pending,
                "departures_pending": departures_pending,
                "folios_balanced": balanced,
                "folios_unbalanced": unbalanced,
                "exceptions_count": len(exceptions),
                "is_rerun": force_rerun,
                "is_dry_run": dry_run,
                "initiated_by": ctx.actor_id,
            }

            if not dry_run:
                await self._db.night_audit_runs.update_one(
                    {"id": audit_id},
                    {"$set": {
                        **summary,
                        "completed_at": datetime.now(UTC).isoformat(),
                        "exception_details": exceptions,
                    }},
                )
                # Persist exceptions
                if exceptions:
                    await self._db.night_audit_exceptions.insert_many(
                        [{**e} for e in exceptions]
                    )

            return ServiceResult.success(summary)

        except Exception as exc:
            logger.exception("Night audit failed: %s", exc)
            if not dry_run:
                await self._db.night_audit_runs.update_one(
                    {"id": audit_id},
                    {"$set": {
                        "status": "failed",
                        "error": str(exc),
                        "completed_at": datetime.now(UTC).isoformat(),
                    }},
                )
            return ServiceResult.fail(f"Night audit failed: {exc}", "AUDIT_FAILED")
        finally:
            await self._release_lock(ctx.tenant_id, bd)

    # ── Step: Post Room Charges ────────────────────────────────────────
    async def _post_room_charges(
        self, ctx: OperationContext, bd: str, audit_id: str,
        exceptions: list, dry_run: bool,
    ) -> tuple[int, int, float, float]:
        """Post nightly room charges to folios for all checked-in bookings."""
        rooms_processed = 0
        charges_posted = 0
        total_revenue = 0.0
        total_tax = 0.0

        cursor = self._db.bookings.find({
            "tenant_id": ctx.tenant_id,
            "status": "checked_in",
        }, {"_id": 0})

        async for booking in cursor:
            rooms_processed += 1
            room_rate = booking.get("room_rate") or booking.get("rate") or 0.0
            if room_rate <= 0:
                exceptions.append(self._make_exception(
                    audit_id, ctx.tenant_id, "warning", "room_charge",
                    "booking", booking.get("id"),
                    f"Booking {booking.get('id')} has zero/missing room rate",
                    {"booking_id": booking.get("id"), "room_rate": room_rate},
                ))
                continue

            vat = round(room_rate * DEFAULT_VAT_RATE, 2)
            accommodation_tax = round(room_rate * ACCOMMODATION_TAX_RATE, 2)
            total_charge = round(room_rate + vat + accommodation_tax, 2)

            if not dry_run:
                charge_id = str(uuid.uuid4())
                charge_doc = {
                    "id": charge_id,
                    "tenant_id": ctx.tenant_id,
                    "booking_id": booking.get("id"),
                    "folio_id": booking.get("folio_id"),
                    "charge_category": "room",
                    "description": f"Room charge - {bd}",
                    "date": bd,
                    "quantity": 1,
                    "unit_price": room_rate,
                    "amount": room_rate,
                    "tax_amount": vat + accommodation_tax,
                    "total": total_charge,
                    "tax_breakdown": {
                        "vat": vat,
                        "accommodation_tax": accommodation_tax,
                    },
                    "voided": False,
                    "posted_by": "night_audit",
                    "audit_id": audit_id,
                    "created_at": datetime.now(UTC).isoformat(),
                }
                await self._db.folio_charges.insert_one({**charge_doc})

                # Update folio balance
                if booking.get("folio_id"):
                    await self._db.folios.update_one(
                        {"id": booking["folio_id"]},
                        {"$inc": {"balance": total_charge}},
                    )

            charges_posted += 1
            total_revenue += room_rate
            total_tax += vat + accommodation_tax

        return rooms_processed, charges_posted, total_revenue, total_tax

    # ── Step: Process No-Shows ─────────────────────────────────────────
    async def _process_no_shows(
        self, ctx: OperationContext, bd: str, audit_id: str,
        exceptions: list, dry_run: bool,
    ) -> int:
        """Mark confirmed arrivals that didn't check in as no-show."""
        no_show_count = 0
        cursor = self._db.bookings.find({
            "tenant_id": ctx.tenant_id,
            "check_in": bd,
            "status": {"$in": ["confirmed", "guaranteed"]},
        }, {"_id": 0})

        async for booking in cursor:
            no_show_count += 1
            if not dry_run:
                await self._db.bookings.update_one(
                    {"id": booking["id"]},
                    {"$set": {
                        "status": "no_show",
                        "no_show_date": datetime.now(UTC).isoformat(),
                        "no_show_processed_by": "night_audit",
                    }},
                )
                # Release room
                if booking.get("room_id"):
                    await self._db.rooms.update_one(
                        {"id": booking["room_id"]},
                        {"$set": {"status": "available", "current_booking_id": None}},
                    )

            no_show_fee = booking.get("cancellation_policy", {}).get("no_show_fee", 0)
            if no_show_fee > 0 and not dry_run:
                await self._db.folio_charges.insert_one({
                    "id": str(uuid.uuid4()),
                    "tenant_id": ctx.tenant_id,
                    "booking_id": booking["id"],
                    "charge_category": "no_show_fee",
                    "description": f"No-show fee - {bd}",
                    "date": bd,
                    "amount": no_show_fee,
                    "total": no_show_fee,
                    "tax_amount": 0,
                    "voided": False,
                    "posted_by": "night_audit",
                    "audit_id": audit_id,
                    "created_at": datetime.now(UTC).isoformat(),
                })

            exceptions.append(self._make_exception(
                audit_id, ctx.tenant_id, "info", "no_show",
                "booking", booking.get("id"),
                f"No-show: {booking.get('guest_name', 'Unknown')} (booking {booking.get('id', '')[:8]})",
                {"booking_id": booking.get("id"), "no_show_fee": no_show_fee},
            ))

        return no_show_count

    # ── Step: Validate pending arrivals ────────────────────────────────
    async def _validate_pending_arrivals(
        self, ctx: OperationContext, bd: str, audit_id: str, exceptions: list,
    ) -> int:
        tomorrow = (datetime.fromisoformat(bd) + timedelta(days=1)).date().isoformat()
        pending = await self._db.bookings.count_documents({
            "tenant_id": ctx.tenant_id,
            "check_in": tomorrow,
            "status": {"$in": ["confirmed", "guaranteed"]},
        })
        if pending > 0:
            # Check room readiness
            rooms_not_ready = 0
            cursor = self._db.bookings.find({
                "tenant_id": ctx.tenant_id,
                "check_in": tomorrow,
                "status": {"$in": ["confirmed", "guaranteed"]},
            }, {"_id": 0})
            async for b in cursor:
                if b.get("room_id"):
                    room = await self._db.rooms.find_one({"id": b["room_id"]}, {"_id": 0})
                    if room and room.get("status") not in ("available", "inspected", "clean"):
                        rooms_not_ready += 1
            if rooms_not_ready > 0:
                exceptions.append(self._make_exception(
                    audit_id, ctx.tenant_id, "warning", "arrival_validation",
                    "booking", None,
                    f"{rooms_not_ready} rooms not ready for tomorrow's {pending} arrivals",
                    {"pending_arrivals": pending, "rooms_not_ready": rooms_not_ready},
                ))
        return pending

    # ── Step: Validate pending departures ──────────────────────────────
    async def _validate_pending_departures(
        self, ctx: OperationContext, bd: str, audit_id: str, exceptions: list,
    ) -> int:
        pending = await self._db.bookings.count_documents({
            "tenant_id": ctx.tenant_id,
            "check_out": bd,
            "status": "checked_in",
        })
        if pending > 0:
            exceptions.append(self._make_exception(
                audit_id, ctx.tenant_id, "warning", "departure_validation",
                "booking", None,
                f"{pending} guests still checked in past their checkout date",
                {"pending_departures": pending},
            ))
        return pending

    # ── Step: Check folio balances ─────────────────────────────────────
    async def _check_folio_balances(
        self, ctx: OperationContext, audit_id: str, exceptions: list,
    ) -> tuple[int, int]:
        balanced = 0
        unbalanced = 0
        cursor = self._db.folios.find({
            "tenant_id": ctx.tenant_id,
            "status": "open",
        }, {"_id": 0})
        async for folio in cursor:
            balance = folio.get("balance", 0.0)
            if abs(balance) <= 0.01:
                balanced += 1
            else:
                unbalanced += 1
                if abs(balance) > 500:
                    exceptions.append(self._make_exception(
                        audit_id, ctx.tenant_id, "error", "folio_balance",
                        "folio", folio.get("id"),
                        f"High unbalanced folio {folio.get('folio_number')}: ${balance:.2f}",
                        {"folio_id": folio.get("id"), "balance": balance},
                    ))
        return balanced, unbalanced

    # ── Step: Tax consistency check ────────────────────────────────────
    async def _validate_tax_consistency(
        self, ctx: OperationContext, bd: str, audit_id: str, exceptions: list,
    ):
        cursor = self._db.folio_charges.find({
            "tenant_id": ctx.tenant_id,
            "date": bd,
            "charge_category": "room",
            "voided": False,
        }, {"_id": 0})
        inconsistent = 0
        async for charge in cursor:
            amount = charge.get("amount", 0)
            tax = charge.get("tax_amount", 0)
            if amount > 0 and abs(tax - amount * (DEFAULT_VAT_RATE + ACCOMMODATION_TAX_RATE)) > 0.05:
                inconsistent += 1
        if inconsistent > 0:
            exceptions.append(self._make_exception(
                audit_id, ctx.tenant_id, "error", "tax_consistency",
                "folio_charge", None,
                f"{inconsistent} room charges with inconsistent tax amounts",
                {"inconsistent_count": inconsistent},
            ))

    # ── Step: Business date roll ───────────────────────────────────────
    async def _roll_business_date(self, ctx: OperationContext, current_bd: str):
        next_bd = (datetime.fromisoformat(current_bd) + timedelta(days=1)).date().isoformat()
        await self._db.tenant_settings.update_one(
            {"tenant_id": ctx.tenant_id},
            {"$set": {
                "business_date": next_bd,
                "previous_business_date": current_bd,
                "business_date_updated_at": datetime.now(UTC).isoformat(),
            }},
            upsert=True,
        )

    # ── Get audit history ──────────────────────────────────────────────
    async def get_audit_history(
        self, ctx: OperationContext,
        limit: int = 20, skip: int = 0,
    ) -> ServiceResult:
        runs = []
        cursor = self._db.night_audit_runs.find(
            {"tenant_id": ctx.tenant_id}, {"_id": 0},
        ).sort("started_at", -1).skip(skip).limit(limit)
        async for run in cursor:
            runs.append(run)
        total = await self._db.night_audit_runs.count_documents({"tenant_id": ctx.tenant_id})
        return ServiceResult.success({"runs": runs, "total": total, "limit": limit, "skip": skip})

    # ── Get exceptions for a run ───────────────────────────────────────
    async def get_audit_exceptions(
        self, ctx: OperationContext, audit_id: str,
    ) -> ServiceResult:
        excs = await self._db.night_audit_exceptions.find(
            {"audit_id": audit_id, "tenant_id": ctx.tenant_id}, {"_id": 0},
        ).to_list(500)
        return ServiceResult.success({"exceptions": excs, "count": len(excs)})

    # ── Get current business date ──────────────────────────────────────
    async def get_business_date(self, ctx: OperationContext) -> ServiceResult:
        settings = await self._db.tenant_settings.find_one(
            {"tenant_id": ctx.tenant_id}, {"_id": 0},
        )
        bd = (settings or {}).get("business_date", datetime.now(UTC).date().isoformat())
        return ServiceResult.success({
            "business_date": bd,
            "previous_business_date": (settings or {}).get("previous_business_date"),
            "updated_at": (settings or {}).get("business_date_updated_at"),
        })

    # ── Schedule CRUD ────────────────────────────────────────────────
    async def get_schedule(self, ctx: OperationContext) -> ServiceResult:
        doc = await self._db.night_audit_schedules.find_one(
            {"tenant_id": ctx.tenant_id}, {"_id": 0}
        )
        if not doc:
            doc = {
                "tenant_id": ctx.tenant_id,
                "enabled": False,
                "scheduled_hour": 0,
                "scheduled_minute": 0,
                "timezone": "Europe/Istanbul",
                "skip_validations": False,
                "auto_retry": True,
                "max_retries": 2,
                "notify_on_complete": True,
                "notify_on_failure": True,
                "last_auto_run": None,
                "last_auto_run_status": None,
                "next_scheduled_run": None,
            }
        return ServiceResult.success(doc)

    async def update_schedule(self, ctx: OperationContext, schedule_data: dict) -> ServiceResult:
        now = datetime.now(UTC).isoformat()
        update_doc = {
            "tenant_id": ctx.tenant_id,
            "enabled": schedule_data.get("enabled", False),
            "scheduled_hour": schedule_data.get("scheduled_hour", 0),
            "scheduled_minute": schedule_data.get("scheduled_minute", 0),
            "timezone": schedule_data.get("timezone", "Europe/Istanbul"),
            "skip_validations": schedule_data.get("skip_validations", False),
            "auto_retry": schedule_data.get("auto_retry", True),
            "max_retries": schedule_data.get("max_retries", 2),
            "notify_on_complete": schedule_data.get("notify_on_complete", True),
            "notify_on_failure": schedule_data.get("notify_on_failure", True),
            "updated_at": now,
            "updated_by": ctx.actor_id,
        }
        await self._db.night_audit_schedules.update_one(
            {"tenant_id": ctx.tenant_id},
            {"$set": update_doc},
            upsert=True,
        )
        update_doc.pop("_id", None)
        return ServiceResult.success(update_doc)

    async def get_schedule_status(self, ctx: OperationContext) -> ServiceResult:
        schedule = await self._db.night_audit_schedules.find_one(
            {"tenant_id": ctx.tenant_id}, {"_id": 0}
        )
        logs = await self._db.night_audit_schedule_logs.find(
            {"tenant_id": ctx.tenant_id},
            {"_id": 0},
        ).sort("triggered_at", -1).limit(10).to_list(10)

        return ServiceResult.success({
            "enabled": (schedule or {}).get("enabled", False),
            "scheduled_hour": (schedule or {}).get("scheduled_hour", 0),
            "scheduled_minute": (schedule or {}).get("scheduled_minute", 0),
            "timezone": (schedule or {}).get("timezone", "Europe/Istanbul"),
            "last_auto_run": (schedule or {}).get("last_auto_run"),
            "last_auto_run_status": (schedule or {}).get("last_auto_run_status"),
            "recent_logs": logs,
        })

    async def run_scheduled_audit(self, tenant_id: str) -> dict:
        """Called by the scheduler background task."""
        schedule = await self._db.night_audit_schedules.find_one(
            {"tenant_id": tenant_id}, {"_id": 0}
        )
        if not schedule or not schedule.get("enabled"):
            return {"skipped": True, "reason": "Schedule not enabled"}

        now = datetime.now(UTC)
        log_id = str(uuid.uuid4())

        # Create a system context
        ctx = OperationContext(
            tenant_id=tenant_id,
            actor_id="system_scheduler",
            actor_role="system",
        )

        # Get current business date
        bd_result = await self.get_business_date(ctx)
        bd = bd_result.data.get("business_date", now.date().isoformat())

        # Log the attempt
        log_entry = {
            "id": log_id,
            "tenant_id": tenant_id,
            "triggered_at": now.isoformat(),
            "business_date": bd,
            "trigger_type": "automatic",
            "status": "running",
        }
        await self._db.night_audit_schedule_logs.insert_one({**log_entry})

        try:
            result = await self.run_night_audit(
                ctx,
                business_date=bd,
                force_rerun=False,
                skip_validations=schedule.get("skip_validations", False),
                dry_run=False,
                reason="Otomatik zamanlama ile calistirildi",
            )

            status = "completed" if result.ok else "failed"
            error_msg = None if result.ok else result.error

            # Retry logic
            if not result.ok and schedule.get("auto_retry") and result.code not in ("ALREADY_COMPLETED",):
                max_retries = schedule.get("max_retries", 2)
                for attempt in range(1, max_retries + 1):
                    logger.info(f"Retry {attempt}/{max_retries} for tenant {tenant_id}")
                    result = await self.run_night_audit(
                        ctx, business_date=bd, force_rerun=True,
                        skip_validations=schedule.get("skip_validations", False),
                        dry_run=False,
                        reason=f"Otomatik yeniden deneme #{attempt}",
                    )
                    if result.ok:
                        status = "completed"
                        error_msg = None
                        break
                    error_msg = result.error

            await self._db.night_audit_schedule_logs.update_one(
                {"id": log_id},
                {"$set": {
                    "status": status,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "error": error_msg,
                    "audit_result": result.data if result.ok else None,
                }},
            )
            await self._db.night_audit_schedules.update_one(
                {"tenant_id": tenant_id},
                {"$set": {
                    "last_auto_run": now.isoformat(),
                    "last_auto_run_status": status,
                }},
            )

            return {"status": status, "audit_id": result.data.get("audit_id") if result.ok else None}

        except Exception as e:
            logger.exception(f"Scheduled audit failed for tenant {tenant_id}: {e}")
            await self._db.night_audit_schedule_logs.update_one(
                {"id": log_id},
                {"$set": {
                    "status": "failed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "error": str(e),
                }},
            )
            await self._db.night_audit_schedules.update_one(
                {"tenant_id": tenant_id},
                {"$set": {
                    "last_auto_run": now.isoformat(),
                    "last_auto_run_status": "failed",
                }},
            )
            return {"status": "failed", "error": str(e)}

    # ── Helper ─────────────────────────────────────────────────────────
    @staticmethod
    def _make_exception(
        audit_id: str, tenant_id: str, severity: str, category: str,
        entity_type: str, entity_id: str | None, message: str,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "audit_id": audit_id,
            "tenant_id": tenant_id,
            "severity": severity,
            "category": category,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "message": message,
            "details": details,
            "auto_resolved": False,
            "created_at": datetime.now(UTC).isoformat(),
        }


night_audit_core_service = NightAuditCoreService()
