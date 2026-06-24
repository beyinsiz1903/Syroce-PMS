"""
PMS Hardening Router - Production-grade API endpoints for all PMS core operations.
Covers: Reservation lifecycle, Front desk, Folio/Billing, Housekeeping, Night Audit, Dashboard.
"""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from cache_manager import cached  # Tur 3: tenant-aware cache for slow trends
from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.auto_housekeeping_service import AutoHousekeepingService
from modules.pms_core.dashboard_trends_service import DashboardTrendsService
from modules.pms_core.folio_detail_service import FolioDetailService
from modules.pms_core.folio_hardening_service import FolioHardeningService
from modules.pms_core.front_desk_service import FrontDeskService
from modules.pms_core.housekeeping_state_service import HousekeepingStateService
from modules.pms_core.multi_property_audit_service import MultiPropertyAuditService
from modules.pms_core.night_audit_engine import NightAuditEngine
from modules.pms_core.pms_dashboard_service import PMSDashboardService
from modules.pms_core.reservation_state_machine import ReservationStateMachine
from modules.pms_core.role_permission_service import (
    RolePermissionService,
    require_op,  # v90 DW
)
from modules.pms_core.role_permission_service import require_module as require_module_v101  # v101 DW
from shared_kernel.idempotency import (
    claim_idempotency,
    complete_idempotency,
    get_idempotency_key,
    release_idempotency,
)

router = APIRouter(prefix="/api/pms-core", tags=["pms-core"])

rsm = ReservationStateMachine()
front_desk = FrontDeskService()
folio_svc = FolioHardeningService()
hk_svc = HousekeepingStateService()
night_audit = NightAuditEngine()
dashboard_svc = PMSDashboardService()
perm_svc = RolePermissionService()
folio_detail_svc = FolioDetailService()
trends_svc = DashboardTrendsService()
mp_audit_svc = MultiPropertyAuditService()
auto_hk_svc = AutoHousekeepingService()


# ── REQUEST MODELS ──

class CheckInRequest(BaseModel):
    booking_id: str
    override_reason: str | None = None

class CheckoutRequest(BaseModel):
    booking_id: str
    force: bool = False

class RoomMoveRequest(BaseModel):
    booking_id: str
    new_room_id: str
    reason: str

class RoomUpgradeRequest(BaseModel):
    booking_id: str
    new_room_id: str
    reason: str
    rate_adjustment: float = 0.0

class WalkInRequest(BaseModel):
    room_id: str
    nights: int = 1
    rate: float
    guest_name: str
    guest_phone: str = ""
    guest_email: str = ""
    guest_id_number: str = ""
    adults: int = 1

class CancellationRequest(BaseModel):
    booking_id: str
    reason: str

class NoShowRequest(BaseModel):
    booking_id: str

class LateCheckoutRequest(BaseModel):
    booking_id: str
    requested_time: str
    charge: float = 0.0

class EarlyCheckinRequest(BaseModel):
    booking_id: str
    requested_time: str

class ChargePostRequest(BaseModel):
    folio_id: str
    booking_id: str
    category: str = "other"
    description: str
    amount: float
    quantity: float = 1.0
    tax_rate: float = 0.0
    department: str | None = None

class PaymentPostRequest(BaseModel):
    folio_id: str
    booking_id: str
    amount: float
    method: str = "cash"
    payment_type: str = "final"
    reference: str | None = None
    notes: str | None = None

class RefundRequest(BaseModel):
    folio_id: str
    booking_id: str
    amount: float
    reason: str
    method: str = "cash"

class VoidRequest(BaseModel):
    charge_id: str | None = None
    payment_id: str | None = None
    reason: str

class SplitFolioRequest(BaseModel):
    source_folio_id: str
    charge_ids: list[str]
    target_folio_type: str = "guest"
    reason: str

class FolioSplitItem(BaseModel):
    amount: float
    target_folio_type: str = "guest"

class SplitFolioByAmountRequest(BaseModel):
    source_folio_id: str
    splits: list[FolioSplitItem]
    reason: str

class CityLedgerTransferRequest(BaseModel):
    folio_id: str
    account_id: str
    reason: str

class RoomStatusUpdateRequest(BaseModel):
    room_id: str
    new_status: str
    notes: str | None = None
    force: bool = False

class InspectionApprovalRequest(BaseModel):
    room_id: str
    approved: bool

class NightAuditRequest(BaseModel):
    business_date: str | None = None

class ExceptionResolveRequest(BaseModel):
    exception_id: str
    resolution: str


# ══════════════════════════════════════════════
# RESERVATION LIFECYCLE
# ══════════════════════════════════════════════

@router.post("/check-in", tags=["front-desk"])
async def api_check_in(req: CheckInRequest, current_user: User = Depends(get_current_user)):
    """Check-in a guest with room readiness validation."""
    perm_svc.enforce_permission(current_user.role, "check_in")
    result = await front_desk.check_in(current_user.tenant_id, req.booking_id, current_user.id, current_user.name, req.override_reason)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    # Fire reservation.updated to subscribed agency webhooks (non-blocking, GC-safe).
    from routers.webhook_retry_service import schedule_emit_reservation_updated
    schedule_emit_reservation_updated(current_user.tenant_id, req.booking_id, "checked_in")
    return result

@router.post("/checkout", tags=["front-desk"])
async def api_checkout(req: CheckoutRequest, current_user: User = Depends(get_current_user)):
    """Checkout a guest with folio balance validation."""
    perm_svc.enforce_permission(current_user.role, "checkout")
    result = await front_desk.checkout(current_user.tenant_id, req.booking_id, current_user.id, current_user.name, req.force)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    # Folio finalization shifts revenue/payment buckets → drop dashboards.
    from domains.pms.night_audit.router import invalidate_finance_cache
    invalidate_finance_cache(current_user.tenant_id)
    # Fire reservation.updated to subscribed agency webhooks (non-blocking, GC-safe).
    from routers.webhook_retry_service import schedule_emit_reservation_updated
    schedule_emit_reservation_updated(current_user.tenant_id, req.booking_id, "checked_out")
    return result

@router.get("/checkout-preview/{booking_id}", tags=["front-desk"])
async def api_checkout_preview(booking_id: str, current_user: User = Depends(get_current_user)):
    """Get checkout preview with folio summary and blockers."""
    return await front_desk.get_checkout_preview(current_user.tenant_id, booking_id)

@router.post("/room-move", tags=["front-desk"])
async def api_room_move(req: RoomMoveRequest, current_user: User = Depends(get_current_user)):
    """Move a checked-in guest to a different room."""
    perm_svc.enforce_permission(current_user.role, "room_move")
    result = await front_desk.room_move(current_user.tenant_id, req.booking_id, req.new_room_id, req.reason, current_user.id, current_user.name)
    if not result["success"]:
        raise HTTPException(status_code=409 if result.get("conflict") else 400, detail=result)
    from routers.webhook_retry_service import schedule_emit_reservation_updated
    schedule_emit_reservation_updated(
        current_user.tenant_id, req.booking_id, "room_moved",
        {"new_room_id": req.new_room_id, "reason": req.reason},
    )
    return result

@router.post("/room-upgrade", tags=["front-desk"])
async def api_room_upgrade(req: RoomUpgradeRequest, current_user: User = Depends(get_current_user)):
    """Upgrade a guest's room."""
    perm_svc.enforce_permission(current_user.role, "room_upgrade")
    result = await front_desk.room_upgrade(current_user.tenant_id, req.booking_id, req.new_room_id, req.reason, req.rate_adjustment, current_user.id, current_user.name)
    if not result["success"]:
        raise HTTPException(status_code=409 if result.get("conflict") else 400, detail=result)
    from routers.webhook_retry_service import schedule_emit_reservation_updated
    schedule_emit_reservation_updated(
        current_user.tenant_id, req.booking_id, "room_upgraded",
        {"new_room_id": req.new_room_id, "rate_adjustment": req.rate_adjustment},
    )
    return result

@router.post("/walk-in", tags=["front-desk"])
async def api_walk_in(req: WalkInRequest, http_request: Request, current_user: User = Depends(get_current_user)):
    """Create a walk-in reservation with immediate check-in."""
    from shared_kernel.idempotency import begin_idempotency
    perm_svc.enforce_permission(current_user.role, "walk_in")
    # Idempotency-Key request-replay (additive: no-op without the header).
    guard, replay = await begin_idempotency(
        db, http_request, tenant_id=current_user.tenant_id,
        scope="pms_core.walk_in", payload=req.model_dump(),
    )
    if replay is not None:
        return replay
    guest_data = {
        "name": req.guest_name,
        "phone": req.guest_phone,
        "email": req.guest_email or f"walkin-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}@hotel.local",
        "id_number": req.guest_id_number,
        "adults": req.adults,
    }
    result = await front_desk.walk_in(current_user.tenant_id, guest_data, req.room_id, req.nights, req.rate, current_user.id, current_user.name)
    if not result["success"]:
        # Logical failure with no durable booking -> release so the same key
        # can be retried.
        await guard.release()
        raise HTTPException(status_code=400, detail=result)
    await guard.complete(result)
    return result

@router.post("/cancel", tags=["reservation"])
async def api_cancel_booking(req: CancellationRequest, current_user: User = Depends(get_current_user)):
    """Cancel a reservation with state machine validation."""
    perm_svc.enforce_permission(current_user.role, "cancel_booking")
    booking = await db.bookings.find_one({"id": req.booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    result = await rsm.handle_cancellation(current_user.tenant_id, booking, current_user.id, req.reason)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)

    # Channel availability auto-sync: iptal sonrası müsaitlik güncelle
    try:
        import asyncio

        from domains.channel_manager.availability_auto_sync import sync_availability_after_booking
        asyncio.create_task(sync_availability_after_booking(
            tenant_id=current_user.tenant_id,
            room_id=booking.get("room_id", ""),
            check_in=booking.get("check_in", ""),
            check_out=booking.get("check_out", ""),
        ))
    except Exception:
        pass

    return result

@router.post("/no-show", tags=["reservation"])
async def api_no_show(req: NoShowRequest, current_user: User = Depends(get_current_user)):
    """Mark a reservation as no-show."""
    perm_svc.enforce_permission(current_user.role, "edit_booking")
    booking = await db.bookings.find_one({"id": req.booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    result = await rsm.handle_no_show(current_user.tenant_id, booking, current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)

    # Channel availability auto-sync: no-show sonrası müsaitlik güncelle
    try:
        import asyncio

        from domains.channel_manager.availability_auto_sync import sync_availability_after_booking
        asyncio.create_task(sync_availability_after_booking(
            tenant_id=current_user.tenant_id,
            room_id=booking.get("room_id", ""),
            check_in=booking.get("check_in", ""),
            check_out=booking.get("check_out", ""),
        ))
    except Exception:
        pass

    return result

@router.post("/late-checkout", tags=["front-desk"])
async def api_late_checkout(req: LateCheckoutRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    """Request late checkout with optional charge."""
    result = await front_desk.request_late_checkout(current_user.tenant_id, req.booking_id, req.requested_time, req.charge, current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    from routers.webhook_retry_service import schedule_emit_reservation_updated
    schedule_emit_reservation_updated(
        current_user.tenant_id, req.booking_id, "late_checkout_approved",
        {"requested_time": req.requested_time, "charge": req.charge},
    )
    return result

@router.post("/early-checkin", tags=["front-desk"])
async def api_early_checkin(req: EarlyCheckinRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    """Request early check-in."""
    result = await front_desk.request_early_checkin(current_user.tenant_id, req.booking_id, req.requested_time, current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    from routers.webhook_retry_service import schedule_emit_reservation_updated
    schedule_emit_reservation_updated(
        current_user.tenant_id, req.booking_id, "early_checkin_approved",
        {"requested_time": req.requested_time},
    )
    return result

@router.get("/reservation-audit/{booking_id}", tags=["reservation"])
async def api_reservation_audit(booking_id: str, current_user: User = Depends(get_current_user)):
    """Get full audit trail for a reservation."""
    return await rsm.get_audit_trail(current_user.tenant_id, booking_id)

@router.get("/overbooking-check", tags=["reservation"])
async def api_overbooking_check(room_id: str, check_in: str, check_out: str, exclude_booking_id: str | None = None, current_user: User = Depends(get_current_user)):
    """Check for overbooking on a specific room and date range."""
    has_conflict, conflicts = await rsm.check_overbooking(current_user.tenant_id, room_id, check_in, check_out, exclude_booking_id)
    return {"has_conflict": has_conflict, "conflicts": conflicts}


# ══════════════════════════════════════════════
# FOLIO / BILLING
# ══════════════════════════════════════════════

@router.post("/folio/charge", tags=["folio"])
async def api_post_charge(req: ChargePostRequest, current_user: User = Depends(get_current_user)):
    """Post a charge to a folio."""
    perm_svc.enforce_permission(current_user.role, "post_charge")
    result = await folio_svc.post_charge(current_user.tenant_id, req.folio_id, req.booking_id, req.model_dump(), current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    from domains.pms.night_audit.router import invalidate_finance_cache
    invalidate_finance_cache(current_user.tenant_id)
    return result

@router.post("/folio/payment", tags=["folio"])
async def api_post_payment(req: PaymentPostRequest, current_user: User = Depends(get_current_user)):
    """Post a payment to a folio."""
    perm_svc.enforce_permission(current_user.role, "post_payment")
    result = await folio_svc.post_payment(current_user.tenant_id, req.folio_id, req.booking_id, req.model_dump(), current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    from domains.pms.night_audit.router import invalidate_finance_cache
    invalidate_finance_cache(current_user.tenant_id)
    return result

@router.post("/folio/refund", tags=["folio"])
async def api_post_refund(req: RefundRequest, request: Request, current_user: User = Depends(get_current_user)):
    """Post a refund."""
    perm_svc.enforce_permission(current_user.role, "void_charge")

    # Idempotency-Key replay protection — task #80 (mirrors charge/payment).
    idem_key = get_idempotency_key(request)
    idem_lock_id = None
    if idem_key:
        claim = await claim_idempotency(
            db,
            tenant_id=current_user.tenant_id,
            scope=f"folio_refund:{req.folio_id}",
            idempotency_key=idem_key,
        )
        if claim["status"] == "replay":
            return claim["response"]
        if claim["status"] == "in_flight":
            raise HTTPException(
                status_code=409,
                detail="Ayni Idempotency-Key ile baska bir istek isleniyor",
            )
        idem_lock_id = claim["lock_id"]

    try:
        result = await folio_svc.post_refund(current_user.tenant_id, req.folio_id, req.booking_id, req.amount, req.reason, req.method, current_user.id)
        if not result["success"]:
            if idem_lock_id:
                await release_idempotency(db, lock_id=idem_lock_id)
                idem_lock_id = None
            raise HTTPException(status_code=400, detail=result)
        # Cache the replay body right after the durable insert / before
        # best-effort side-effects, so a retry replays the cached row.
        if idem_lock_id:
            await complete_idempotency(db, lock_id=idem_lock_id, response_body=result)
            idem_lock_id = None
        from domains.pms.night_audit.router import invalidate_finance_cache
        invalidate_finance_cache(current_user.tenant_id)
        return result
    except HTTPException:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id)
        raise
    except Exception as exc:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id, error=str(exc))
        raise

@router.post("/folio/void-charge", tags=["folio"])
async def api_void_charge(req: VoidRequest, request: Request, current_user: User = Depends(get_current_user)):
    """Void a charge."""
    perm_svc.enforce_permission(current_user.role, "void_charge")
    if not req.charge_id:
        raise HTTPException(status_code=400, detail="charge_id required")

    # Idempotency-Key replay protection — task #80. Scoped per charge_id so
    # a double-tap on the same Void button cannot flip the row twice.
    idem_key = get_idempotency_key(request)
    idem_lock_id = None
    if idem_key:
        claim = await claim_idempotency(
            db,
            tenant_id=current_user.tenant_id,
            scope=f"folio_void_charge:{req.charge_id}",
            idempotency_key=idem_key,
        )
        if claim["status"] == "replay":
            return claim["response"]
        if claim["status"] == "in_flight":
            raise HTTPException(
                status_code=409,
                detail="Ayni Idempotency-Key ile baska bir istek isleniyor",
            )
        idem_lock_id = claim["lock_id"]

    try:
        result = await folio_svc.void_charge(current_user.tenant_id, req.charge_id, req.reason, current_user.id)
        if not result["success"]:
            if idem_lock_id:
                await release_idempotency(db, lock_id=idem_lock_id)
                idem_lock_id = None
            raise HTTPException(status_code=400, detail=result)
        if idem_lock_id:
            await complete_idempotency(db, lock_id=idem_lock_id, response_body=result)
            idem_lock_id = None
        from domains.pms.night_audit.router import invalidate_finance_cache
        invalidate_finance_cache(current_user.tenant_id)
        return result
    except HTTPException:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id)
        raise
    except Exception as exc:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id, error=str(exc))
        raise

@router.post("/folio/void-payment", tags=["folio"])
async def api_void_payment(req: VoidRequest, request: Request, current_user: User = Depends(get_current_user)):
    """Void a payment."""
    perm_svc.enforce_permission(current_user.role, "void_payment")
    if not req.payment_id:
        raise HTTPException(status_code=400, detail="payment_id required")

    # Idempotency-Key replay protection — task #80.
    idem_key = get_idempotency_key(request)
    idem_lock_id = None
    if idem_key:
        claim = await claim_idempotency(
            db,
            tenant_id=current_user.tenant_id,
            scope=f"folio_void_payment:{req.payment_id}",
            idempotency_key=idem_key,
        )
        if claim["status"] == "replay":
            return claim["response"]
        if claim["status"] == "in_flight":
            raise HTTPException(
                status_code=409,
                detail="Ayni Idempotency-Key ile baska bir istek isleniyor",
            )
        idem_lock_id = claim["lock_id"]

    try:
        result = await folio_svc.void_payment(current_user.tenant_id, req.payment_id, req.reason, current_user.id)
        if not result["success"]:
            if idem_lock_id:
                await release_idempotency(db, lock_id=idem_lock_id)
                idem_lock_id = None
            raise HTTPException(status_code=400, detail=result)
        if idem_lock_id:
            await complete_idempotency(db, lock_id=idem_lock_id, response_body=result)
            idem_lock_id = None
        from domains.pms.night_audit.router import invalidate_finance_cache
        invalidate_finance_cache(current_user.tenant_id)
        return result
    except HTTPException:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id)
        raise
    except Exception as exc:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id, error=str(exc))
        raise

@router.post("/folio/split", tags=["folio"])
async def api_split_folio(req: SplitFolioRequest, request: Request, current_user: User = Depends(get_current_user)):
    """Split charges from one folio to a new one."""
    perm_svc.enforce_permission(current_user.role, "split_folio")

    # Idempotency-Key replay protection — task #102. Scoped per source folio so
    # a double-tap on Split cannot produce two ghost folios from the same click.
    idem_key = get_idempotency_key(request)
    idem_lock_id = None
    if idem_key:
        claim = await claim_idempotency(
            db,
            tenant_id=current_user.tenant_id,
            scope=f"folio_split:{req.source_folio_id}",
            idempotency_key=idem_key,
        )
        if claim["status"] == "replay":
            return claim["response"]
        if claim["status"] == "in_flight":
            raise HTTPException(
                status_code=409,
                detail="Ayni Idempotency-Key ile baska bir istek isleniyor",
            )
        idem_lock_id = claim["lock_id"]

    try:
        result = await folio_svc.split_folio(current_user.tenant_id, req.source_folio_id, req.charge_ids, req.target_folio_type, req.reason, current_user.id)
        if not result["success"]:
            if idem_lock_id:
                await release_idempotency(db, lock_id=idem_lock_id)
                idem_lock_id = None
            raise HTTPException(status_code=400, detail=result)
        if idem_lock_id:
            await complete_idempotency(db, lock_id=idem_lock_id, response_body=result)
            idem_lock_id = None
        return result
    except HTTPException:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id)
        raise
    except Exception as exc:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id, error=str(exc))
        raise

@router.post("/folio/split-by-amount", tags=["folio"])
async def api_split_folio_by_amount(req: SplitFolioByAmountRequest, request: Request, current_user: User = Depends(get_current_user)):
    """Split a folio by transferring monetary amounts (even or custom)."""
    perm_svc.enforce_permission(current_user.role, "split_folio")

    # Idempotency-Key replay protection — task #102. Per-source-folio scope
    # prevents a double-tap from creating two sets of target folios and
    # transferring the same balance twice.
    idem_key = get_idempotency_key(request)
    idem_lock_id = None
    if idem_key:
        claim = await claim_idempotency(
            db,
            tenant_id=current_user.tenant_id,
            scope=f"folio_split_by_amount:{req.source_folio_id}",
            idempotency_key=idem_key,
        )
        if claim["status"] == "replay":
            return claim["response"]
        if claim["status"] == "in_flight":
            raise HTTPException(
                status_code=409,
                detail="Ayni Idempotency-Key ile baska bir istek isleniyor",
            )
        idem_lock_id = claim["lock_id"]

    try:
        splits = [s.model_dump() for s in req.splits]
        result = await folio_svc.split_folio_by_amounts(
            current_user.tenant_id, req.source_folio_id, splits, req.reason, current_user.id
        )
        if not result["success"]:
            if idem_lock_id:
                await release_idempotency(db, lock_id=idem_lock_id)
                idem_lock_id = None
            raise HTTPException(status_code=400, detail=result)
        if idem_lock_id:
            await complete_idempotency(db, lock_id=idem_lock_id, response_body=result)
            idem_lock_id = None
        return result
    except HTTPException:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id)
        raise
    except Exception as exc:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id, error=str(exc))
        raise

@router.get("/folio/tax-breakdown/{folio_id}", tags=["folio"])
async def api_tax_breakdown(folio_id: str, current_user: User = Depends(get_current_user)):
    """Get tax breakdown for a folio."""
    return await folio_svc.get_tax_breakdown(current_user.tenant_id, folio_id)

@router.post("/folio/city-ledger-transfer", tags=["folio"])
async def api_city_ledger_transfer(req: CityLedgerTransferRequest, request: Request, current_user: User = Depends(get_current_user)):
    """Transfer folio balance to city ledger."""
    perm_svc.enforce_permission(current_user.role, "close_folio")

    # Idempotency-Key replay protection — task #102. Per-source-folio scope so
    # a double-tap cannot transfer the same balance twice (which would also
    # try to close an already-closed folio).
    idem_key = get_idempotency_key(request)
    idem_lock_id = None
    if idem_key:
        claim = await claim_idempotency(
            db,
            tenant_id=current_user.tenant_id,
            scope=f"folio_city_ledger:{req.folio_id}",
            idempotency_key=idem_key,
        )
        if claim["status"] == "replay":
            return claim["response"]
        if claim["status"] == "in_flight":
            raise HTTPException(
                status_code=409,
                detail="Ayni Idempotency-Key ile baska bir istek isleniyor",
            )
        idem_lock_id = claim["lock_id"]

    try:
        result = await folio_svc.transfer_to_city_ledger(current_user.tenant_id, req.folio_id, req.account_id, req.reason, current_user.id)
        if not result["success"]:
            if idem_lock_id:
                await release_idempotency(db, lock_id=idem_lock_id)
                idem_lock_id = None
            raise HTTPException(status_code=400, detail=result)
        if idem_lock_id:
            await complete_idempotency(db, lock_id=idem_lock_id, response_body=result)
            idem_lock_id = None
        return result
    except HTTPException:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id)
        raise
    except Exception as exc:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id, error=str(exc))
        raise

@router.get("/folio/audit/{folio_id}", tags=["folio"])
async def api_folio_audit(folio_id: str, current_user: User = Depends(get_current_user)):
    """Get audit trail for a folio."""
    return await folio_svc.get_folio_audit_trail(current_user.tenant_id, folio_id)


# ══════════════════════════════════════════════
# HOUSEKEEPING
# ══════════════════════════════════════════════

@router.post("/housekeeping/room-status", tags=["housekeeping"])
async def api_update_room_status(req: RoomStatusUpdateRequest, current_user: User = Depends(get_current_user)):
    """Update room status with state machine validation."""
    perm_svc.enforce_permission(current_user.role, "update_room_status")
    result = await hk_svc.update_room_status(current_user.tenant_id, req.room_id, req.new_status, current_user.id, req.notes, req.force)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result

@router.post("/housekeeping/inspection-approval", tags=["housekeeping"])
async def api_inspection_approval(req: InspectionApprovalRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v99 DW
):
    """Approve or reject room inspection."""
    result = await hk_svc.approve_room_inspection(current_user.tenant_id, req.room_id, current_user.id, req.approved)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result

@router.get("/housekeeping/room-readiness/{room_id}", tags=["housekeeping"])
async def api_room_readiness(room_id: str, current_user: User = Depends(get_current_user)):
    """Check if a room is ready for check-in."""
    return await hk_svc.check_room_readiness(current_user.tenant_id, room_id)

@router.get("/housekeeping/room-summary", tags=["housekeeping"])
async def api_room_summary(current_user: User = Depends(get_current_user)):
    """Get room status summary."""
    return await hk_svc.get_room_status_summary(current_user.tenant_id)

@router.get("/housekeeping/maintenance-impact", tags=["housekeeping"])
async def api_maintenance_impact(room_id: str, start_date: str, end_date: str, current_user: User = Depends(get_current_user)):
    """Check maintenance impact on active bookings."""
    return await hk_svc.maintenance_impact_on_availability(current_user.tenant_id, room_id, start_date, end_date)


# ══════════════════════════════════════════════
# NIGHT AUDIT
# ══════════════════════════════════════════════

@router.post("/night-audit/run", tags=["night-audit"])
async def api_run_night_audit(req: NightAuditRequest, current_user: User = Depends(get_current_user)):
    """Run night audit for the current or specified business date."""
    perm_svc.enforce_permission(current_user.role, "run_night_audit")
    business_date = req.business_date or await night_audit.get_business_date(current_user.tenant_id)
    result = await night_audit.run_night_audit(current_user.tenant_id, business_date, current_user.id)
    # Concurrency guard: a second simultaneous run for the same business date is
    # rejected by the engine with code "already_running" -> surface as HTTP 409.
    if isinstance(result, dict) and result.get("code") == "already_running":
        raise HTTPException(status_code=409, detail=result)
    return result

@router.get("/night-audit/business-date", tags=["night-audit"])
async def api_get_business_date(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports"))  # v103 DX
):
    """Get current business date."""
    bd = await night_audit.get_business_date(current_user.tenant_id)
    return {"business_date": bd}

@router.get("/night-audit/exceptions", tags=["night-audit"])
async def api_get_exceptions(status: str = "open", current_user: User = Depends(get_current_user)):
    """Get audit exceptions."""
    return await night_audit.get_audit_exceptions(current_user.tenant_id, status)

@router.post("/night-audit/resolve-exception", tags=["night-audit"])
async def api_resolve_exception(req: ExceptionResolveRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_night_audit")),  # v90 DW
):
    """Resolve an audit exception."""
    result = await night_audit.resolve_exception(current_user.tenant_id, req.exception_id, current_user.id, req.resolution)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result

@router.get("/night-audit/snapshot/{business_date}", tags=["night-audit"])
async def api_get_snapshot(business_date: str, current_user: User = Depends(get_current_user)):
    """Get daily audit snapshot."""
    snapshot = await night_audit.get_daily_snapshot(current_user.tenant_id, business_date)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found for this date")
    return snapshot


# ══════════════════════════════════════════════
# OPERATIONAL DASHBOARD
# ══════════════════════════════════════════════

@router.get("/dashboard/operational", tags=["dashboard"])
async def api_operational_dashboard(current_user: User = Depends(get_current_user)):
    """Get comprehensive operational dashboard data."""
    return await dashboard_svc.get_operational_snapshot(current_user.tenant_id)


# ══════════════════════════════════════════════
# ROLE / PERMISSIONS
# ══════════════════════════════════════════════

@router.get("/permissions/me", tags=["permissions"])
async def api_my_permissions(current_user: User = Depends(get_current_user)):
    """Get current user's permissions."""
    return {
        "role": current_user.role,
        "permissions": perm_svc.get_user_permissions(current_user.role),
    }

@router.get("/audit-trail", tags=["audit"])
async def api_get_audit_trail(entity_type: str | None = None, entity_id: str | None = None, limit: int = 50, current_user: User = Depends(get_current_user)):
    """Get PMS audit trail with optional filters."""
    query = {"tenant_id": current_user.tenant_id}
    if entity_type:
        query["entity_type"] = entity_type
    if entity_id:
        query["entity_id"] = entity_id
    trail = await db.pms_audit_trail.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return {"count": len(trail), "trail": trail}


# ══════════════════════════════════════════════
# FOLIO DETAIL VIEW
# ══════════════════════════════════════════════

@router.get("/folio/detail/{folio_id}", tags=["folio"])
async def api_folio_detail(folio_id: str, current_user: User = Depends(get_current_user)):
    """Get comprehensive folio detail: timeline, running balance, splits, tax, audit."""
    result = await folio_detail_svc.get_folio_detail(current_user.tenant_id, folio_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Folio not found"))
    return result


# ══════════════════════════════════════════════
# DASHBOARD TRENDS + DATE RANGE FILTERS
# ══════════════════════════════════════════════

@router.get("/dashboard/trends", tags=["dashboard"])
@cached(ttl=300, key_prefix="pms_dashboard_trends")  # Tur 3: tenant-aware cache (was timeout)
async def api_dashboard_trends(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get operational trends for date range (arrivals, departures, occupancy, etc.)."""
    from datetime import date as date_cls
    from datetime import timedelta as _td
    # Tur 3: default range = last 7 days (30 caused timeout)
    if not end_date:
        end_date = date_cls.today().isoformat()
    if not start_date:
        start_date = (date_cls.today() - _td(days=7)).isoformat()
    try:
        sd = date_cls.fromisoformat(start_date)
        ed = date_cls.fromisoformat(end_date)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    if (ed - sd).days > 90:
        raise HTTPException(status_code=400, detail="Max 90 day range")
    if ed < sd:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")
    return await trends_svc.get_trends(current_user.tenant_id, start_date, end_date)


# ══════════════════════════════════════════════
# MULTI-PROPERTY NIGHT AUDIT COORDINATION
# ══════════════════════════════════════════════

@router.get("/multi-property/audit-board", tags=["multi-property"])
async def api_audit_status_board(current_user: User = Depends(get_current_user)):
    """Get multi-property night audit status board."""
    return await mp_audit_svc.get_audit_status_board(current_user.tenant_id)

@router.get("/multi-property/exception-summary", tags=["multi-property"])
async def api_exception_summary(current_user: User = Depends(get_current_user)):
    """Get aggregated exception summary across properties."""
    return await mp_audit_svc.get_exception_summary(current_user.tenant_id)

@router.get("/multi-property/unresolved-blockers", tags=["multi-property"])
async def api_unresolved_blockers(current_user: User = Depends(get_current_user)):
    """Get unresolved blockers across properties."""
    return await mp_audit_svc.get_unresolved_blockers(current_user.tenant_id)

@router.get("/multi-property/readiness-score", tags=["multi-property"])
async def api_readiness_score(current_user: User = Depends(get_current_user)):
    """Get multi-property audit readiness score."""
    return await mp_audit_svc.get_readiness_score(current_user.tenant_id)


class EscalateRequest(BaseModel):
    exception_id: str
    note: str

@router.post("/multi-property/escalate", tags=["multi-property"])
async def api_escalate_exception(req: EscalateRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Escalate an audit exception."""
    result = await mp_audit_svc.escalate_exception(current_user.tenant_id, req.exception_id, current_user.id, req.note)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result


# ══════════════════════════════════════════════
# AUTO HOUSEKEEPING TASK ASSIGNMENT
# ══════════════════════════════════════════════

class AutoAssignRequest(BaseModel):
    booking_id: str

@router.post("/housekeeping/auto-assign", tags=["housekeeping"])
async def api_auto_assign_after_checkout(req: AutoAssignRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v99 DW
):
    """Auto-assign housekeeping task after checkout."""
    result = await auto_hk_svc.auto_assign_after_checkout(current_user.tenant_id, req.booking_id, current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result

@router.get("/housekeeping/assignment-suggestions", tags=["housekeeping"])
async def api_assignment_suggestions(current_user: User = Depends(get_current_user)):
    """Get housekeeping task assignment suggestions."""
    return await auto_hk_svc.get_assignment_suggestions(current_user.tenant_id)

@router.get("/housekeeping/room-eta/{room_id}", tags=["housekeeping"])
async def api_room_readiness_eta(room_id: str, current_user: User = Depends(get_current_user)):
    """Get room readiness ETA."""
    return await auto_hk_svc.get_room_readiness_eta(current_user.tenant_id, room_id)


class ManualOverrideRequest(BaseModel):
    task_id: str
    new_assignee_id: str
    reason: str

@router.post("/housekeeping/manual-override", tags=["housekeeping"])
async def api_manual_override(req: ManualOverrideRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v99 DW
):
    """Manually override a housekeeping task assignment."""
    result = await auto_hk_svc.manual_override_assignment(
        current_user.tenant_id, req.task_id, req.new_assignee_id, req.reason, current_user.id
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result
