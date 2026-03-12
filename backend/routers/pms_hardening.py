"""
PMS Hardening Router - Production-grade API endpoints for all PMS core operations.
Covers: Reservation lifecycle, Front desk, Folio/Billing, Housekeeping, Night Audit, Dashboard.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.reservation_state_machine import ReservationStateMachine
from modules.pms_core.front_desk_service import FrontDeskService
from modules.pms_core.folio_hardening_service import FolioHardeningService
from modules.pms_core.housekeeping_state_service import HousekeepingStateService
from modules.pms_core.night_audit_engine import NightAuditEngine
from modules.pms_core.pms_dashboard_service import PMSDashboardService
from modules.pms_core.role_permission_service import RolePermissionService

router = APIRouter(prefix="/api/pms-core", tags=["pms-core"])

rsm = ReservationStateMachine()
front_desk = FrontDeskService()
folio_svc = FolioHardeningService()
hk_svc = HousekeepingStateService()
night_audit = NightAuditEngine()
dashboard_svc = PMSDashboardService()
perm_svc = RolePermissionService()


# ── REQUEST MODELS ──

class CheckInRequest(BaseModel):
    booking_id: str
    override_reason: Optional[str] = None

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
    department: Optional[str] = None

class PaymentPostRequest(BaseModel):
    folio_id: str
    booking_id: str
    amount: float
    method: str = "cash"
    payment_type: str = "final"
    reference: Optional[str] = None
    notes: Optional[str] = None

class RefundRequest(BaseModel):
    folio_id: str
    booking_id: str
    amount: float
    reason: str
    method: str = "cash"

class VoidRequest(BaseModel):
    charge_id: Optional[str] = None
    payment_id: Optional[str] = None
    reason: str

class SplitFolioRequest(BaseModel):
    source_folio_id: str
    charge_ids: List[str]
    target_folio_type: str = "guest"
    reason: str

class CityLedgerTransferRequest(BaseModel):
    folio_id: str
    account_id: str
    reason: str

class RoomStatusUpdateRequest(BaseModel):
    room_id: str
    new_status: str
    notes: Optional[str] = None
    force: bool = False

class InspectionApprovalRequest(BaseModel):
    room_id: str
    approved: bool

class NightAuditRequest(BaseModel):
    business_date: Optional[str] = None

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
    return result

@router.post("/checkout", tags=["front-desk"])
async def api_checkout(req: CheckoutRequest, current_user: User = Depends(get_current_user)):
    """Checkout a guest with folio balance validation."""
    perm_svc.enforce_permission(current_user.role, "checkout")
    result = await front_desk.checkout(current_user.tenant_id, req.booking_id, current_user.id, current_user.name, req.force)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
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
        raise HTTPException(status_code=400, detail=result)
    return result

@router.post("/room-upgrade", tags=["front-desk"])
async def api_room_upgrade(req: RoomUpgradeRequest, current_user: User = Depends(get_current_user)):
    """Upgrade a guest's room."""
    perm_svc.enforce_permission(current_user.role, "room_upgrade")
    result = await front_desk.room_upgrade(current_user.tenant_id, req.booking_id, req.new_room_id, req.reason, req.rate_adjustment, current_user.id, current_user.name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result

@router.post("/walk-in", tags=["front-desk"])
async def api_walk_in(req: WalkInRequest, current_user: User = Depends(get_current_user)):
    """Create a walk-in reservation with immediate check-in."""
    perm_svc.enforce_permission(current_user.role, "walk_in")
    guest_data = {
        "name": req.guest_name,
        "phone": req.guest_phone,
        "email": req.guest_email or f"walkin-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}@hotel.local",
        "id_number": req.guest_id_number,
        "adults": req.adults,
    }
    result = await front_desk.walk_in(current_user.tenant_id, guest_data, req.room_id, req.nights, req.rate, current_user.id, current_user.name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
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
    return result

@router.post("/late-checkout", tags=["front-desk"])
async def api_late_checkout(req: LateCheckoutRequest, current_user: User = Depends(get_current_user)):
    """Request late checkout with optional charge."""
    result = await front_desk.request_late_checkout(current_user.tenant_id, req.booking_id, req.requested_time, req.charge, current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result

@router.post("/early-checkin", tags=["front-desk"])
async def api_early_checkin(req: EarlyCheckinRequest, current_user: User = Depends(get_current_user)):
    """Request early check-in."""
    result = await front_desk.request_early_checkin(current_user.tenant_id, req.booking_id, req.requested_time, current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result

@router.get("/reservation-audit/{booking_id}", tags=["reservation"])
async def api_reservation_audit(booking_id: str, current_user: User = Depends(get_current_user)):
    """Get full audit trail for a reservation."""
    return await rsm.get_audit_trail(current_user.tenant_id, booking_id)

@router.get("/overbooking-check", tags=["reservation"])
async def api_overbooking_check(room_id: str, check_in: str, check_out: str, exclude_booking_id: Optional[str] = None, current_user: User = Depends(get_current_user)):
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
    return result

@router.post("/folio/payment", tags=["folio"])
async def api_post_payment(req: PaymentPostRequest, current_user: User = Depends(get_current_user)):
    """Post a payment to a folio."""
    perm_svc.enforce_permission(current_user.role, "post_payment")
    result = await folio_svc.post_payment(current_user.tenant_id, req.folio_id, req.booking_id, req.model_dump(), current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result

@router.post("/folio/refund", tags=["folio"])
async def api_post_refund(req: RefundRequest, current_user: User = Depends(get_current_user)):
    """Post a refund."""
    perm_svc.enforce_permission(current_user.role, "void_charge")
    result = await folio_svc.post_refund(current_user.tenant_id, req.folio_id, req.booking_id, req.amount, req.reason, req.method, current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result

@router.post("/folio/void-charge", tags=["folio"])
async def api_void_charge(req: VoidRequest, current_user: User = Depends(get_current_user)):
    """Void a charge."""
    perm_svc.enforce_permission(current_user.role, "void_charge")
    if not req.charge_id:
        raise HTTPException(status_code=400, detail="charge_id required")
    result = await folio_svc.void_charge(current_user.tenant_id, req.charge_id, req.reason, current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result

@router.post("/folio/void-payment", tags=["folio"])
async def api_void_payment(req: VoidRequest, current_user: User = Depends(get_current_user)):
    """Void a payment."""
    perm_svc.enforce_permission(current_user.role, "void_payment")
    if not req.payment_id:
        raise HTTPException(status_code=400, detail="payment_id required")
    result = await folio_svc.void_payment(current_user.tenant_id, req.payment_id, req.reason, current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result

@router.post("/folio/split", tags=["folio"])
async def api_split_folio(req: SplitFolioRequest, current_user: User = Depends(get_current_user)):
    """Split charges from one folio to a new one."""
    perm_svc.enforce_permission(current_user.role, "split_folio")
    result = await folio_svc.split_folio(current_user.tenant_id, req.source_folio_id, req.charge_ids, req.target_folio_type, req.reason, current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result

@router.get("/folio/tax-breakdown/{folio_id}", tags=["folio"])
async def api_tax_breakdown(folio_id: str, current_user: User = Depends(get_current_user)):
    """Get tax breakdown for a folio."""
    return await folio_svc.get_tax_breakdown(current_user.tenant_id, folio_id)

@router.post("/folio/city-ledger-transfer", tags=["folio"])
async def api_city_ledger_transfer(req: CityLedgerTransferRequest, current_user: User = Depends(get_current_user)):
    """Transfer folio balance to city ledger."""
    perm_svc.enforce_permission(current_user.role, "close_folio")
    result = await folio_svc.transfer_to_city_ledger(current_user.tenant_id, req.folio_id, req.account_id, req.reason, current_user.id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result)
    return result

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
async def api_inspection_approval(req: InspectionApprovalRequest, current_user: User = Depends(get_current_user)):
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
    return result

@router.get("/night-audit/business-date", tags=["night-audit"])
async def api_get_business_date(current_user: User = Depends(get_current_user)):
    """Get current business date."""
    bd = await night_audit.get_business_date(current_user.tenant_id)
    return {"business_date": bd}

@router.get("/night-audit/exceptions", tags=["night-audit"])
async def api_get_exceptions(status: str = "open", current_user: User = Depends(get_current_user)):
    """Get audit exceptions."""
    return await night_audit.get_audit_exceptions(current_user.tenant_id, status)

@router.post("/night-audit/resolve-exception", tags=["night-audit"])
async def api_resolve_exception(req: ExceptionResolveRequest, current_user: User = Depends(get_current_user)):
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
async def api_get_audit_trail(entity_type: Optional[str] = None, entity_id: Optional[str] = None, limit: int = 50, current_user: User = Depends(get_current_user)):
    """Get PMS audit trail with optional filters."""
    query = {"tenant_id": current_user.tenant_id}
    if entity_type:
        query["entity_type"] = entity_type
    if entity_id:
        query["entity_id"] = entity_id
    trail = await db.pms_audit_trail.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return {"count": len(trail), "trail": trail}
