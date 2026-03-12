"""
PMS / Front Desk — Production Router v2
Routes for enhanced front desk operations:
room_move, late_checkout, no_show, walk_in, post_charge, void_charge.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.security import get_current_user
from common.context import OperationContext
from common.response import from_service_result
from domains.pms.frontdesk_service_v2 import frontdesk_service_v2

router = APIRouter(prefix="/api/frontdesk/v2", tags=["Front Desk v2"])


# ── Schemas ──────────────────────────────────────────────────────────

class CheckinRequest(BaseModel):
    booking_id: str
    create_folio: bool = True
    idempotency_key: Optional[str] = None

class CheckoutRequest(BaseModel):
    booking_id: str
    force: bool = False
    auto_close_folios: bool = True
    reason: Optional[str] = None

class RoomMoveRequest(BaseModel):
    booking_id: str
    new_room_id: str
    reason: str
    transfer_keycards: bool = True

class LateCheckoutRequest(BaseModel):
    booking_id: str
    new_checkout_time: str
    charge_amount: float = 0.0
    reason: str

class NoShowRequest(BaseModel):
    booking_id: str
    charge_first_night: bool = True
    release_room: bool = True

class WalkInRequest(BaseModel):
    guest_name: str
    room_id: str
    nights: int = 1
    rate_amount: float = 0.0
    payment_method: str = "cash"
    guest_email: Optional[str] = None
    guest_phone: Optional[str] = None
    id_number: Optional[str] = None

class PostChargeRequest(BaseModel):
    booking_id: str
    charge_type: str
    description: str
    amount: float
    charge_category: str = "misc"
    idempotency_key: Optional[str] = None

class VoidChargeRequest(BaseModel):
    charge_id: str
    reason: str


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/checkin")
async def checkin(req: CheckinRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await frontdesk_service_v2.checkin(
        ctx, req.booking_id, req.create_folio, idempotency_key=req.idempotency_key
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)

@router.post("/checkout")
async def checkout(req: CheckoutRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await frontdesk_service_v2.checkout(
        ctx, req.booking_id, req.force, req.auto_close_folios, reason=req.reason
    )
    if not result.ok:
        code = 402 if result.code == "OUTSTANDING_BALANCE" else 400
        raise HTTPException(status_code=code, detail=from_service_result(result))
    return from_service_result(result)

@router.post("/room-move")
async def room_move(req: RoomMoveRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await frontdesk_service_v2.room_move(
        ctx, req.booking_id, req.new_room_id, reason=req.reason, transfer_keycards=req.transfer_keycards
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)

@router.post("/late-checkout")
async def late_checkout(req: LateCheckoutRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await frontdesk_service_v2.late_checkout(
        ctx, req.booking_id, req.new_checkout_time, req.charge_amount, reason=req.reason
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)

@router.post("/no-show")
async def process_no_show(req: NoShowRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await frontdesk_service_v2.process_no_show(
        ctx, req.booking_id, req.charge_first_night, req.release_room
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)

@router.post("/walk-in")
async def walk_in(req: WalkInRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await frontdesk_service_v2.walk_in(
        ctx, req.guest_name, req.room_id, req.nights, req.rate_amount,
        req.payment_method, req.guest_email, req.guest_phone, req.id_number
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)

@router.post("/post-charge")
async def post_charge(req: PostChargeRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await frontdesk_service_v2.post_charge(
        ctx, req.booking_id, req.charge_type, req.description,
        req.amount, req.charge_category, req.idempotency_key
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)

@router.post("/void-charge")
async def void_charge(req: VoidChargeRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await frontdesk_service_v2.void_charge(ctx, req.charge_id, reason=req.reason)
    if not result.ok:
        code = 403 if result.code == "FORBIDDEN" else 400
        raise HTTPException(status_code=code, detail=from_service_result(result))
    return from_service_result(result)
