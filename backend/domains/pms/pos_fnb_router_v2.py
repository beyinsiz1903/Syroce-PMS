"""
PMS / POS & F&B — Production Router v2
Routes for enhanced POS operations:
create_order, close_order, void_order, stock_adjust, table_reserve.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from common.context import OperationContext
from common.response import from_service_result
from core.security import get_current_user
from domains.pms.pos_fnb.pos_fnb_service_v2 import pos_fnb_service_v2

router = APIRouter(prefix="/api/pos/v2", tags=["POS & F&B v2"])


# ── Schemas ──────────────────────────────────────────────────────────

class OrderItemSchema(BaseModel):
    item_id: str | None = None
    name: str
    quantity: int = 1
    price: float
    station: str = "main"
    special_instructions: str | None = None

class CreateOrderRequest(BaseModel):
    outlet_id: str
    table_number: str | None = None
    items: list[OrderItemSchema]
    guest_name: str | None = None
    booking_id: str | None = None
    order_type: str = "dine_in"
    idempotency_key: str | None = None

class CloseOrderRequest(BaseModel):
    order_id: str
    payment_method: str = "cash"
    post_to_folio: bool = False
    booking_id: str | None = None
    tip_amount: float = 0.0
    idempotency_key: str | None = None

class VoidOrderRequest(BaseModel):
    order_id: str
    reason: str

class StockAdjustRequest(BaseModel):
    product_id: str
    adjustment_type: str  # in, out, set
    quantity: int
    reason: str
    idempotency_key: str | None = None

class TableReserveRequest(BaseModel):
    outlet_id: str
    table_number: str
    guest_name: str
    reservation_time: str
    party_size: int = 2


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/orders")
async def create_order(req: CreateOrderRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    items_dicts = [item.model_dump() for item in req.items]
    result = await pos_fnb_service_v2.create_order(
        ctx, req.outlet_id, req.table_number, items_dicts,
        req.guest_name, req.booking_id, req.order_type, req.idempotency_key
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)

@router.post("/orders/close")
async def close_order(req: CloseOrderRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.close_order(
        ctx, req.order_id, req.payment_method, req.post_to_folio,
        req.booking_id, req.tip_amount, req.idempotency_key
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)

@router.post("/orders/void")
async def void_order(req: VoidOrderRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.void_order(ctx, req.order_id, reason=req.reason)
    if not result.ok:
        code = 403 if result.code == "FORBIDDEN" else 400
        raise HTTPException(status_code=code, detail=from_service_result(result))
    return from_service_result(result)

@router.post("/stock/adjust")
async def adjust_stock(req: StockAdjustRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.adjust_stock(
        ctx, req.product_id, req.adjustment_type, req.quantity,
        req.reason, req.idempotency_key
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)

@router.post("/tables/reserve")
async def reserve_table(req: TableReserveRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.reserve_table(
        ctx, req.outlet_id, req.table_number, req.guest_name,
        req.reservation_time, req.party_size
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)
