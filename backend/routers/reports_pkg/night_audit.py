"""Auto-split from reports.py — backward-compatible sub-router."""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()

from core.business_date_service import ensure_business_date_initialized
from core.channel_room_charge_pricing import calculate_room_charge
from core.database import db
from core.security import get_current_user
from models.enums import ChargeCategory
from models.schemas import FolioCharge, User
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import load_stay_night_metrics

try:
    from domains.pms.night_audit_module import AuditStatus, AutomaticPosting, NightAuditRecord
except ImportError:
    NightAuditRecord = None
    AuditStatus = None
    AutomaticPosting = None

from core.utils import (
    calculate_folio_balance,
    night_audit_calculate_revenue,
    night_audit_housekeeping_rollup,
    night_audit_ota_reconciliation,
    night_audit_post_room_charges,
    night_audit_recalculate_ar,
)

try:
    from infra.logging_service import get_logging_service
except ImportError:
    get_logging_service = None

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


logger = logging.getLogger(__name__)
sub_router = APIRouter()


def _night_audit_charge_query(
    tenant_id: str,
    booking_id: str,
    folio_id: str,
    audit_date: str,
    charge_category: str,
) -> dict:
    """Build the idempotency key for a nightly folio posting.

    Each booking/folio/category can have one active posting per PMS business
    date.  A voided entry deliberately does not block a replacement posting.
    """
    return {
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "folio_id": folio_id,
        "business_date": audit_date,
        "charge_category": charge_category,
        "voided": {"$ne": True},
    }


@sub_router.post("/night-audit/post-room-charges")
async def post_room_charges(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_night_audit")),  # v90 DW
):
    """Night audit: Post room charges to all active bookings"""
    import time

    start_time = time.time()

    logging_service = get_logging_service(db)
    business_state = await ensure_business_date_initialized(db, current_user.tenant_id)
    audit_date = str(business_state["business_date"])[:10]
    errors = []

    try:
        # Get all checked-in bookings
        bookings = await db.bookings.find({"tenant_id": current_user.tenant_id, "status": "checked_in"}).to_list(1000)

        charges_posted = 0
        total_amount = 0.0
        total_amount_by_currency: dict[str, float] = {}

        # N+1 fix: tum folios tek $in
        na_booking_ids = [b["id"] for b in bookings if b.get("id")]
        na_folios_map: dict = {}
        if na_booking_ids:
            async for f in db.folios.find(
                {
                    "booking_id": {"$in": na_booking_ids},
                    "folio_type": "guest",
                    "status": "open",
                }
            ):
                na_folios_map[f["booking_id"]] = f

        for booking in bookings:
            try:
                if booking.get("is_complimentary"):
                    continue
                folio = na_folios_map.get(booking["id"])

                if folio:
                    existing_charge = await db.folio_charges.find_one(
                        {
                            "tenant_id": current_user.tenant_id,
                            "booking_id": booking["id"],
                            "business_date": audit_date,
                            "charge_category": "room",
                            "voided": {"$ne": True},
                        },
                        {"_id": 0, "id": 1},
                    )
                    if existing_charge:
                        continue
                    pricing = calculate_room_charge(booking, audit_date)
                    currency = str(booking.get("currency") or "TRY").strip().upper() or "TRY"
                    charge = FolioCharge(
                        tenant_id=current_user.tenant_id,
                        folio_id=folio["id"],
                        booking_id=booking["id"],
                        charge_category=ChargeCategory.ROOM,
                        description=f"Room {booking.get('room_id', 'N/A')} - Night Charge",
                        unit_price=pricing["unit_price"],
                        quantity=1.0,
                        amount=pricing["amount"],
                        tax_amount=pricing["tax_amount"],
                        total=pricing["total"],
                        posted_by="SYSTEM",
                    )

                    charge_dict = charge.model_dump()
                    charge_dict["date"] = charge_dict["date"].isoformat()
                    charge_dict.update(
                        {
                            "business_date": audit_date,
                            "night_audit_date": audit_date,
                            "charge_type": "room_charge",
                            "currency": currency,
                            "tax_breakdown": pricing["tax_breakdown"],
                        }
                    )
                    await db.folio_charges.insert_one(charge_dict)

                    # Update folio balance — v109 round-9 IDOR (defense-in-depth).
                    balance = await calculate_folio_balance(folio["id"], current_user.tenant_id)
                    await db.folios.update_one({"id": folio["id"], "tenant_id": current_user.tenant_id}, {"$set": {"balance": balance}})

                    from core.audit import log_audit_event

                    await log_audit_event(
                        tenant_id=current_user.tenant_id,
                        user_id=current_user.id,
                        action="post_charge",
                        entity_type="folio",
                        entity_id=folio["id"],
                        details=f"Night Audit: Added Room Charge of {pricing['total']} {currency}",
                        after_value=charge_dict,
                    )

                    charges_posted += 1
                    total_amount += pricing["total"]
                    total_amount_by_currency[currency] = total_amount_by_currency.get(currency, 0.0) + pricing["total"]
            except Exception as e:
                errors.append(f"Booking {booking.get('id')}: {str(e)}")

        duration = time.time() - start_time
        status = "completed" if len(errors) == 0 else "partial" if charges_posted > 0 else "failed"

        # Log night audit
        await logging_service.log_night_audit(
            tenant_id=current_user.tenant_id,
            audit_date=audit_date,
            user_id=current_user.id,
            user_name=current_user.name,
            status=status,
            rooms_processed=len(bookings),
            charges_posted=charges_posted,
            total_amount=round(total_amount, 2) if len(total_amount_by_currency) <= 1 else 0.0,
            duration_seconds=duration,
            errors=errors if errors else None,
            metadata={"total_amount_by_currency": {currency: round(amount, 2) for currency, amount in total_amount_by_currency.items()}},
        )

        return {
            "message": "Night audit completed",
            "charges_posted": charges_posted,
            "bookings_processed": len(bookings),
            "total_amount": round(total_amount, 2) if len(total_amount_by_currency) <= 1 else None,
            "total_amount_by_currency": {currency: round(amount, 2) for currency, amount in total_amount_by_currency.items()},
            "status": status,
            "errors": errors if errors else None,
        }
    except Exception as e:
        duration = time.time() - start_time

        # Log failed audit
        await logging_service.log_night_audit(
            tenant_id=current_user.tenant_id,
            audit_date=audit_date,
            user_id=current_user.id,
            user_name=current_user.name,
            status="failed",
            rooms_processed=0,
            charges_posted=0,
            total_amount=0.0,
            duration_seconds=duration,
            errors=[str(e)],
        )

        raise HTTPException(status_code=500, detail=f"Night audit failed: {str(e)}")


@sub_router.post("/night-audit/run-night-audit")
async def run_night_audit(
    audit_date: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_night_audit")),  # v90 DW
):
    """
    Run complete night audit
    - Day closure
    - Revenue calculation
    - AR recalculation
    - Housekeeping roll-up
    - OTA reconciliation
    """
    audit_date_str = audit_date or datetime.now().date().isoformat()
    datetime.fromisoformat(audit_date_str)

    audit_results = {"audit_id": str(uuid.uuid4()), "audit_date": audit_date_str, "started_at": datetime.now(UTC).isoformat(), "status": "in_progress", "steps": []}

    # Step 1: Post room charges
    step1_result = await night_audit_post_room_charges(current_user.tenant_id, audit_date_str)
    audit_results["steps"].append({"step": 1, "name": "Post Room Charges", "status": "completed", "details": step1_result})

    # Step 2: Calculate daily revenue
    step2_result = await night_audit_calculate_revenue(current_user.tenant_id, audit_date_str)
    audit_results["steps"].append({"step": 2, "name": "Calculate Revenue", "status": "completed", "details": step2_result})

    # Step 3: AR recalculation
    step3_result = await night_audit_recalculate_ar(current_user.tenant_id)
    audit_results["steps"].append({"step": 3, "name": "Recalculate AR", "status": "completed", "details": step3_result})

    # Step 4: Housekeeping roll-up
    step4_result = await night_audit_housekeeping_rollup(current_user.tenant_id, audit_date_str)
    audit_results["steps"].append({"step": 4, "name": "Housekeeping Roll-up", "status": "completed", "details": step4_result})

    # Step 5: OTA reconciliation
    step5_result = await night_audit_ota_reconciliation(current_user.tenant_id, audit_date_str)
    audit_results["steps"].append({"step": 5, "name": "OTA Reconciliation", "status": "completed", "details": step5_result})

    # Complete audit
    audit_results["status"] = "completed"
    audit_results["completed_at"] = datetime.now(UTC).isoformat()

    # Store audit record (Bug AA fix: insert mutates dict adding _id;
    # recursively strip ObjectId / _id so JSON encoder doesn't crash)
    def _clean_bson(obj):
        try:
            from bson import ObjectId
        except Exception:
            ObjectId = None  # type: ignore
        if isinstance(obj, dict):
            return {k: _clean_bson(v) for k, v in obj.items() if k != "_id"}
        if isinstance(obj, list):
            return [_clean_bson(v) for v in obj]
        if ObjectId is not None and isinstance(obj, ObjectId):
            return str(obj)
        return obj

    await db.night_audit_logs.insert_one(dict(audit_results))
    return _clean_bson(audit_results)


@sub_router.post("/night-audit/start-audit")
async def start_night_audit(
    audit_date: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_night_audit")),  # v88 DW
):
    """Start night audit process for specified date"""
    current_user = await get_current_user(credentials)

    # Check if audit already exists for this date
    existing_audit = await db.night_audits.find_one({"tenant_id": current_user.tenant_id, "audit_date": audit_date, "status": {"$in": ["in_progress", "completed"]}})

    if existing_audit:
        raise HTTPException(status_code=400, detail=f"Night audit for {audit_date} already exists or is in progress")

    # Create audit record
    audit = NightAuditRecord(tenant_id=current_user.tenant_id, audit_date=audit_date, started_by=current_user.name, status=AuditStatus.IN_PROGRESS)

    # Use the same stay-night engine as occupancy, ADR and RevPAR reports.
    # This prevents duplicate room assignments from inflating occupancy and
    # keeps complimentary rooms occupied but outside sold-room denominators.
    target_day = datetime.fromisoformat(audit_date).date()
    metric_rows = await load_stay_night_metrics(db, current_user.tenant_id, target_day, target_day, actual_only=True)
    metric = metric_rows[0] if metric_rows else {"total_rooms": 0, "occupied_rooms": 0, "sold_rooms": 0}
    total_rooms = int(metric.get("total_rooms") or 0)
    occupied_rooms = int(metric.get("occupied_rooms") or 0)

    audit.total_rooms = total_rooms
    audit.occupied_rooms = occupied_rooms
    audit.vacant_rooms = total_rooms - occupied_rooms

    revenue = await night_audit_calculate_revenue(current_user.tenant_id, audit_date)
    # Legacy scalar model fields are retained only for single-currency clients.
    # Mixed-currency reports use the explicit breakdown fields below.
    audit.total_revenue = float(revenue.get("total_revenue") or 0)
    audit.room_revenue = float(revenue.get("room_revenue") or 0)
    audit.tax_revenue = float(revenue.get("tax_revenue") or 0)
    audit.other_revenue = float(revenue.get("other_revenue") or 0)

    # Save audit record
    audit_doc = audit.model_dump()
    audit_doc.update(
        {
            "sold_rooms": int(metric.get("sold_rooms") or 0),
            "total_revenue_by_currency": revenue.get("total_revenue_by_currency", {}),
            "room_revenue_by_currency": revenue.get("room_revenue_by_currency", {}),
            "tax_revenue_by_currency": revenue.get("tax_revenue_by_currency", {}),
            "other_revenue_by_currency": revenue.get("other_revenue_by_currency", {}),
            "mixed_currency": revenue.get("mixed_currency", False),
            "revenue_basis": revenue.get("basis"),
        }
    )
    await db.night_audits.insert_one(audit_doc)

    return {
        "success": True,
        "audit_id": audit.id,
        "audit_date": audit_date,
        "status": audit.status,
        "statistics": {
            "total_rooms": audit.total_rooms,
            "occupied_rooms": audit.occupied_rooms,
            "occupancy_pct": round(min((occupied_rooms / total_rooms * 100), 100.0), 1) if total_rooms > 0 else 0,
            "total_revenue": audit.total_revenue,
            "total_revenue_by_currency": revenue.get("total_revenue_by_currency", {}),
            "room_revenue": audit.room_revenue,
            "room_revenue_by_currency": revenue.get("room_revenue_by_currency", {}),
            "sold_rooms": int(metric.get("sold_rooms") or 0),
            "revenue_basis": revenue.get("basis"),
        },
    }


@sub_router.post("/night-audit/end-of-day")
async def end_of_day_audit(
    audit_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_night_audit")),  # v88 DW
):
    """Complete end-of-day audit process"""
    current_user = await get_current_user(credentials)

    # Get audit record
    audit = await db.night_audits.find_one({"id": audit_id, "tenant_id": current_user.tenant_id})

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    if audit["status"] == "completed":
        raise HTTPException(status_code=400, detail="Audit already completed")

    # Process no-shows
    no_shows = await db.bookings.count_documents({"tenant_id": current_user.tenant_id, "check_in": audit["audit_date"], "status": "confirmed"})

    # Update status
    await db.night_audits.update_one({"id": audit_id}, {"$set": {"status": "completed", "completed_at": datetime.now(UTC).isoformat(), "no_shows_processed": no_shows}})

    return {
        "success": True,
        "audit_id": audit_id,
        "completed_at": datetime.now(UTC).isoformat(),
        "summary": {
            "total_revenue": audit.get("total_revenue", 0),
            "total_revenue_by_currency": audit.get("total_revenue_by_currency", {}),
            "revenue_basis": audit.get("revenue_basis"),
            "no_shows": no_shows,
            "occupied_rooms": audit.get("occupied_rooms", 0),
        },
    }


@sub_router.post("/night-audit/automatic-posting")
async def automatic_posting(
    audit_date: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_night_audit")),  # v88 DW
):
    """Post tax-inclusive nightly room charges for all in-house guests."""
    current_user = await get_current_user(credentials)

    posted_count = 0
    failed_count = 0
    total_posted = 0.0
    total_posted_by_currency: dict[str, float] = {}

    # Get all checked-in bookings for this date
    bookings = await db.bookings.find({"tenant_id": current_user.tenant_id, "status": "checked_in", "check_in": {"$lte": audit_date}, "check_out": {"$gt": audit_date}}).to_list(10000)

    # N+1 fix: tum folios tek $in (bookings ID listesinden)
    na2_booking_ids = [b["id"] for b in bookings if b.get("id")]
    na2_folios_map: dict = {}
    if na2_booking_ids:
        async for f in db.folios.find(
            {
                "tenant_id": current_user.tenant_id,
                "booking_id": {"$in": na2_booking_ids},
                "folio_type": "guest",
            }
        ):
            na2_folios_map[f["booking_id"]] = f

    for booking in bookings:
        try:
            if booking.get("is_complimentary"):
                continue
            folio = na2_folios_map.get(booking["id"])

            if not folio:
                # Create folio
                folio = {
                    "id": str(uuid.uuid4()),
                    "tenant_id": current_user.tenant_id,
                    "booking_id": booking["id"],
                    "folio_type": "guest",
                    "status": "open",
                    "created_at": datetime.now(UTC).isoformat(),
                }
                await db.folios.insert_one(folio)

            existing_charge = await db.folio_charges.find_one(
                _night_audit_charge_query(
                    current_user.tenant_id, booking["id"], folio["id"], audit_date, "room"
                ),
                {"_id": 0, "id": 1},
            )
            if existing_charge:
                continue

            # Reservation total is the confirmed guest-payable amount. Extract
            # taxes from that total; never add a second hard-coded tax posting.
            pricing = calculate_room_charge(booking, audit_date)
            currency = str(booking.get("currency") or "TRY").strip().upper() or "TRY"
            room_charge = {
                "id": str(uuid.uuid4()),
                "tenant_id": current_user.tenant_id,
                "folio_id": folio["id"],
                "booking_id": booking["id"],
                "charge_category": "room",
                "description": f"Room {booking.get('room_number', 'TBD')} - {audit_date}",
                "unit_price": pricing["unit_price"],
                "quantity": 1.0,
                "amount": pricing["amount"],
                "tax_amount": pricing["tax_amount"],
                "tax_breakdown": pricing["tax_breakdown"],
                "total": pricing["total"],
                "currency": currency,
                "business_date": audit_date,
                "night_audit_date": audit_date,
                "charge_type": "room_charge",
                "date": datetime.now(UTC).isoformat(),
                "posted_at": datetime.now(UTC).isoformat(),
                "posted_by": "night_audit_system",
                "voided": False,
            }

            await db.folio_charges.insert_one(room_charge)

            from core.audit import log_audit_event
            from core.utils import calculate_folio_balance

            new_balance = await calculate_folio_balance(folio["id"], current_user.tenant_id)
            await db.folios.update_one({"id": folio["id"], "tenant_id": current_user.tenant_id}, {"$set": {"balance": new_balance}})

            await log_audit_event(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                action="post_charge",
                entity_type="folio",
                entity_id=folio["id"],
                details=f"Night Audit: Added Room Charge of {pricing['total']} {currency}",
                after_value=room_charge,
            )

            posted_count += 1
            total_posted += room_charge["total"]
            total_posted_by_currency[currency] = total_posted_by_currency.get(currency, 0.0) + room_charge["total"]

        except Exception:
            failed_count += 1

    return {
        "success": True,
        "audit_date": audit_date,
        "posted_count": posted_count,
        "failed_count": failed_count,
        "total_amount_posted": round(total_posted, 2) if len(total_posted_by_currency) <= 1 else None,
        "total_amount_posted_by_currency": {currency: round(amount, 2) for currency, amount in total_posted_by_currency.items()},
        "message": f"Automatic posting completed: {posted_count} bookings processed",
    }


@sub_router.get("/night-audit/audit-report")
async def get_audit_report(audit_date: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get comprehensive night audit report"""
    # Tur 3: default — today when omitted
    if not audit_date:
        from datetime import date as _d

        audit_date = _d.today().isoformat()
    current_user = await get_current_user(credentials)

    # Get audit record
    audit = await db.night_audits.find_one({"tenant_id": current_user.tenant_id, "audit_date": audit_date}, {"_id": 0})

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found for this date")

    # Get detailed breakdown
    bookings_summary = await db.bookings.aggregate(
        [
            {"$match": {"tenant_id": current_user.tenant_id, "check_in": {"$lte": audit_date}, "check_out": {"$gt": audit_date}}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}, "revenue": {"$sum": "$total_amount"}}},
        ]
    ).to_list(100)

    return {"audit": audit, "bookings_by_status": bookings_summary, "generated_at": datetime.now(UTC).isoformat()}


@sub_router.post("/night-audit/no-show-handling")
async def handle_no_shows(
    audit_date: str,
    charge_no_show_fee: bool = True,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_night_audit")),  # v88 DW
):
    """Process no-shows for the audit date
    - Marks eligible bookings as no_show
    - Optionally posts no-show fee charges to guest folios
    - Writes detailed audit trail into night_audit_logs
    """
    current_user = await get_current_user(credentials)
    logging_service = get_logging_service(db)

    no_show_fee = 50.0
    processed_count = 0
    total_charges = 0.0
    no_show_details = []

    # Find bookings that should have checked in but didn't
    no_show_bookings = await db.bookings.find({"tenant_id": current_user.tenant_id, "check_in": audit_date, "status": "confirmed"}).to_list(1000)

    for booking in no_show_bookings:
        booking_id = booking.get("id")
        guest_id = booking.get("guest_id")
        room_id = booking.get("room_id")
        room_number = booking.get("room_number")

        fee_posted = False
        folio_id = None
        folio_number = None

        try:
            from modules.reservations.repository import ReservationsRepository
            from modules.reservations.services.update_reservation_service import UpdateReservationService
            from shared_kernel.tenancy_context import PropertyContext, TenantContext

            repo = ReservationsRepository(db)
            service = UpdateReservationService(repo)

            tenant_ctx = TenantContext(tenant_id=current_user.tenant_id, role=current_user.role)
            property_ctx = PropertyContext(property_id=None)

            # This handles audit_log, inventory release, af_sadakat/capx events, etc.
            await service.update_reservation(
                booking_id=booking_id,
                update_data={"status": "no_show", "no_show_date": audit_date},
                tenant_context=tenant_ctx,
                property_context=property_ctx,
                current_user=current_user,
                correlation_id=str(uuid.uuid4()),
            )

            # Post no-show fee if configured
            if charge_no_show_fee:
                folio = await db.folios.find_one({"booking_id": booking_id, "folio_type": "guest"})

                if folio:
                    from core.audit import log_audit_event
                    from core.utils import calculate_folio_balance

                    folio_id = folio.get("id")
                    folio_number = folio.get("folio_number")
                    charge = {
                        "id": str(uuid.uuid4()),
                        "tenant_id": current_user.tenant_id,
                        "folio_id": folio_id,
                        "booking_id": booking_id,
                        "charge_category": "no_show_fee",
                        "description": f"No-Show Fee - {audit_date}",
                        "unit_price": no_show_fee,
                        "quantity": 1.0,
                        "amount": no_show_fee,
                        "tax_amount": 0.0,
                        "total": no_show_fee,
                        "date": datetime.now(UTC).isoformat(),
                        "posted_by": "SYSTEM",
                        "voided": False,
                    }
                    await db.folio_charges.insert_one(charge)

                    # Ensure balance is updated
                    new_balance = await calculate_folio_balance(folio_id, current_user.tenant_id)
                    await db.folios.update_one({"id": folio_id, "tenant_id": current_user.tenant_id}, {"$set": {"balance": new_balance}})

                    # Emit audit log for the charge
                    await log_audit_event(
                        tenant_id=current_user.tenant_id,
                        user_id=current_user.id,
                        action="post_charge",
                        entity_type="folio",
                        entity_id=folio_id,
                        details=f"Night Audit: Added No-Show fee of {no_show_fee}",
                        after_value=charge,
                    )

                    total_charges += no_show_fee
                    fee_posted = True
        except Exception as e:
            logger.error(f"Failed to process no_show for booking {booking_id}: {e}")
            continue

        processed_count += 1

        no_show_details.append(
            {
                "booking_id": booking_id,
                "reservation_number": booking.get("reservation_number") or booking.get("booking_reference"),
                "guest_id": guest_id,
                "room_id": room_id,
                "room_number": room_number,
                "folio_id": folio_id,
                "folio_number": folio_number,
                "fee_posted": fee_posted,
                "fee_amount": no_show_fee if fee_posted else 0.0,
            }
        )

    # Write detailed night audit log entry
    await logging_service.log_night_audit(
        tenant_id=current_user.tenant_id,
        audit_date=audit_date,
        user_id=current_user.id,
        user_name=current_user.name,
        status="completed",
        rooms_processed=processed_count,
        charges_posted=processed_count if charge_no_show_fee else 0,
        total_amount=total_charges,
        duration_seconds=None,
        metadata={
            "action": "no_show_handling",
            "no_show_count": processed_count,
            "no_show_fee_enabled": charge_no_show_fee,
            "no_show_details": no_show_details,
        },
    )

    return {"success": True, "audit_date": audit_date, "no_shows_processed": processed_count, "total_no_show_charges": round(total_charges, 2), "fee_per_booking": no_show_fee}


@sub_router.get("/night-audit/legacy-status")
async def get_night_audit_status_legacy(audit_date: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Legacy night audit status (use /api/night-audit/status for hardened version)"""
    current_user = await get_current_user(credentials)

    if not audit_date:
        audit_date = datetime.now(UTC).strftime("%Y-%m-%d")

    audit = await db.night_audits.find_one({"tenant_id": current_user.tenant_id, "audit_date": audit_date}, {"_id": 0})

    if not audit:
        return {"audit_date": audit_date, "status": "not_started", "message": "Night audit not yet started for this date"}

    return audit


@sub_router.post("/night-audit/room-rate-posting")
async def post_room_rates(
    audit_date: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_night_audit")),  # v88 DW
):
    """Post room rates for all in-house guests"""
    current_user = await get_current_user(credentials)

    posted = 0
    total_amount = 0.0

    bookings = await db.bookings.find({"tenant_id": current_user.tenant_id, "status": "checked_in", "check_in": {"$lte": audit_date}, "check_out": {"$gt": audit_date}}).to_list(10000)

    # N+1 fix: tum folios tek $in
    na3_ids = [b["id"] for b in bookings if b.get("id")]
    na3_folios_map: dict = {}
    if na3_ids:
        async for f in db.folios.find(
            {"tenant_id": current_user.tenant_id, "booking_id": {"$in": na3_ids}, "folio_type": "guest"}
        ):
            na3_folios_map[f["booking_id"]] = f

    for booking in bookings:
        folio = na3_folios_map.get(booking["id"])

        if folio:
            existing_charge = await db.folio_charges.find_one(
                _night_audit_charge_query(
                    current_user.tenant_id, booking["id"], folio["id"], audit_date, "room"
                ),
                {"_id": 0, "id": 1},
            )
            if existing_charge:
                continue
            rate = booking.get("base_rate", 0)
            charge = {
                "id": str(uuid.uuid4()),
                "tenant_id": current_user.tenant_id,
                "folio_id": folio["id"],
                "booking_id": booking["id"],
                "charge_category": "room",
                "description": f"Room Charge - {audit_date}",
                "unit_price": rate,
                "quantity": 1.0,
                "amount": rate,
                "tax_amount": 0.0,
                "total": rate,
                "business_date": audit_date,
                "night_audit_date": audit_date,
                "date": datetime.now(UTC).isoformat(),
                "posted_at": datetime.now(UTC).isoformat(),
                "posted_by": "night_audit_system",
                "voided": False,
            }
            await db.folio_charges.insert_one(charge)

            from core.audit import log_audit_event
            from core.utils import calculate_folio_balance

            new_balance = await calculate_folio_balance(folio["id"], current_user.tenant_id)
            await db.folios.update_one({"id": folio["id"], "tenant_id": current_user.tenant_id}, {"$set": {"balance": new_balance}})

            await log_audit_event(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                action="post_charge",
                entity_type="folio",
                entity_id=folio["id"],
                details=f"Night Audit: Added Room Charge of {rate}",
                after_value=charge,
            )

            posted += 1
            total_amount += rate

    return {"success": True, "posted_count": posted, "total_amount": round(total_amount, 2)}


@sub_router.post("/night-audit/tax-posting")
async def post_taxes(
    audit_date: str,
    tax_rate: float = 0.10,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_night_audit")),  # v88 DW
):
    """Post tax charges for all in-house guests"""
    current_user = await get_current_user(credentials)

    posted = 0
    total_tax = 0.0

    bookings = await db.bookings.find({"tenant_id": current_user.tenant_id, "status": "checked_in", "check_in": {"$lte": audit_date}, "check_out": {"$gt": audit_date}}).to_list(10000)

    # N+1 fix: tum folios tek $in
    na4_ids = [b["id"] for b in bookings if b.get("id")]
    na4_folios_map: dict = {}
    if na4_ids:
        async for f in db.folios.find(
            {"tenant_id": current_user.tenant_id, "booking_id": {"$in": na4_ids}, "folio_type": "guest"}
        ):
            na4_folios_map[f["booking_id"]] = f

    for booking in bookings:
        folio = na4_folios_map.get(booking["id"])

        if folio:
            existing_charge = await db.folio_charges.find_one(
                _night_audit_charge_query(
                    current_user.tenant_id, booking["id"], folio["id"], audit_date, "tax"
                ),
                {"_id": 0, "id": 1},
            )
            if existing_charge:
                continue
            rate = booking.get("base_rate", 0)
            tax_amount = rate * tax_rate

            charge = {
                "id": str(uuid.uuid4()),
                "tenant_id": current_user.tenant_id,
                "folio_id": folio["id"],
                "booking_id": booking["id"],
                "charge_category": "tax",
                "description": f"Room Tax ({tax_rate * 100}%) - {audit_date}",
                "unit_price": tax_amount,
                "quantity": 1.0,
                "amount": tax_amount,
                "tax_amount": 0.0,
                "total": tax_amount,
                "business_date": audit_date,
                "night_audit_date": audit_date,
                "date": datetime.now(UTC).isoformat(),
                "posted_at": datetime.now(UTC).isoformat(),
                "posted_by": "night_audit_system",
                "voided": False,
            }
            await db.folio_charges.insert_one(charge)

            from core.audit import log_audit_event
            from core.utils import calculate_folio_balance

            new_balance = await calculate_folio_balance(folio["id"], current_user.tenant_id)
            await db.folios.update_one({"id": folio["id"], "tenant_id": current_user.tenant_id}, {"$set": {"balance": new_balance}})

            await log_audit_event(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                action="post_charge",
                entity_type="folio",
                entity_id=folio["id"],
                details=f"Night Audit: Added Tax Charge of {tax_amount}",
                after_value=charge,
            )

            posted += 1
            total_tax += tax_amount

    return {"success": True, "posted_count": posted, "total_tax": round(total_tax, 2), "tax_rate": tax_rate}


@sub_router.get("/night-audit/audit-trail")
async def get_audit_trail(start_date: str | None = None, end_date: str | None = None, limit: int = 100, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get audit trail of all system changes"""
    current_user = await get_current_user(credentials)

    query = {"tenant_id": current_user.tenant_id}

    if start_date and end_date:
        query["timestamp"] = {"$gte": datetime.fromisoformat(start_date).isoformat(), "$lte": datetime.fromisoformat(end_date).isoformat()}

    trail = await db.audit_trail.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)

    return {"audit_trail": trail, "total_entries": len(trail)}


@sub_router.post("/night-audit/rollback")
async def rollback_audit(
    audit_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_night_audit")),  # v88 DW
):
    """Rollback a completed audit (emergency use)"""
    current_user = await get_current_user(credentials)

    audit = await db.night_audits.find_one({"id": audit_id, "tenant_id": current_user.tenant_id})

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    # Update status
    await db.night_audits.update_one(
        {"id": audit_id}, {"$set": {"status": "pending", "completed_at": None}, "$push": {"warnings": f"Audit rolled back by {current_user.name} at {datetime.now(UTC).isoformat()}"}}
    )

    return {"success": True, "message": "Audit rolled back successfully", "audit_id": audit_id}


@sub_router.get("/night-audit/audit-history")
async def get_audit_history(limit: int = 30, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get night audit history for last N days"""
    current_user = await get_current_user(credentials)

    audits = await db.night_audits.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).sort("audit_date", -1).limit(limit).to_list(limit)

    return {"audits": audits, "total_count": len(audits)}
