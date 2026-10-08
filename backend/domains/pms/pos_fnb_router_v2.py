"""
PMS / POS & F&B — Production Router v2
Routes for enhanced POS operations:
create_order, close_order, void_order, stock_adjust, table_reserve.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from common.context import OperationContext
from common.response import from_service_result
from core.security import get_current_user
from domains.pms.pos_fnb.pos_fnb_service_v2 import pos_fnb_service_v2
from modules.pms_core.role_permission_service import require_module as require_module_v99  # v99 DW
from modules.pms_core.role_permission_service import require_module as require_module_v101  # v101 DW
from modules.pms_core.role_permission_service import require_op  # v98 DW


def _ok_payload(result):
    """Return service data dict directly so callers see top-level fields
    (e.g. `order_id`, `transaction_id`). Falls back to the envelope only
    when the service returned no data dict."""
    data = result.data
    if isinstance(data, dict):
        return data
    return from_service_result(result)


router = APIRouter(prefix="/api/pos/v2", tags=["POS & F&B v2"])


# ── Schemas ──────────────────────────────────────────────────────────


class OrderItemSchema(BaseModel):
    item_id: str | None = None
    name: str
    quantity: int = 1
    price: float
    tax_rate: float = 0.10
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


class PaymentPart(BaseModel):
    method: str
    amount: float


class CloseOrderRequest(BaseModel):
    order_id: str
    payment_method: str = "cash"
    post_to_folio: bool = False
    booking_id: str | None = None
    tip_amount: float = 0.0
    idempotency_key: str | None = None
    guest_signature: str | None = None
    payments: list[PaymentPart] | None = None


class VoidOrderItemRequest(BaseModel):
    line_index: int
    reason: str


class RefundOrderRequest(BaseModel):
    amount: float | None = None
    reason: str
    idempotency_key: str | None = None


class VoidOrderRequest(BaseModel):
    order_id: str
    reason: str


class AddOrderItemsRequest(BaseModel):
    items: list[OrderItemSchema]
    idempotency_key: str | None = None


class TransferOrderTableRequest(BaseModel):
    to_table_number: str


class OrderAdjustmentRequest(BaseModel):
    adjustment_type: str = Field(pattern="^(discount|service_charge)$")
    calculation: str = Field(pattern="^(percentage|fixed)$")
    value: float = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)


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


class OpenTabRequest(BaseModel):
    outlet_id: str
    table_number: str
    items: list[OrderItemSchema] = []
    guest_name: str | None = None
    guests: int = 1
    idempotency_key: str | None = None


class CloseTabRequest(BaseModel):
    transaction_id: str
    payment_method: str = "cash"


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("/orders")
async def create_order(
    req: CreateOrderRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    ctx = OperationContext.from_user(user)
    items_dicts = [item.model_dump() for item in req.items]
    result = await pos_fnb_service_v2.create_order(ctx, req.outlet_id, req.table_number, items_dicts, req.guest_name, req.booking_id, req.order_type, req.idempotency_key)
    if not result.ok:
        status_code = 409 if result.code == "TABLE_UNAVAILABLE" else 400
        raise HTTPException(status_code=status_code, detail=from_service_result(result))
    return _ok_payload(result)


@router.post("/orders/close")
async def close_order(
    req: CloseOrderRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.close_order(
        ctx,
        req.order_id,
        req.payment_method,
        req.post_to_folio,
        req.booking_id,
        req.tip_amount,
        req.idempotency_key,
        req.guest_signature,
        [part.model_dump() for part in req.payments] if req.payments else None,
    )
    if not result.ok:
        # Terminal-state conflicts → 409; everything else → 400.
        status_code = 409 if result.code in {"ORDER_VOIDED", "FOLIO_NOT_OPEN", "BOOKING_NOT_IN_HOUSE"} else 400
        raise HTTPException(status_code=status_code, detail=from_service_result(result))
    return _ok_payload(result)


@router.post("/orders/{order_id}/items/void")
async def void_order_item(
    order_id: str,
    req: VoidOrderItemRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),
):
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.void_order_item(ctx, order_id, req.line_index, req.reason)
    if not result.ok:
        status_code = 403 if result.code == "FORBIDDEN" else 409 if result.code == "ORDER_NOT_OPEN" else 400
        raise HTTPException(status_code=status_code, detail=from_service_result(result))
    return _ok_payload(result)


@router.post("/orders/{order_id}/refund")
async def refund_order(
    order_id: str,
    req: RefundOrderRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),
):
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.refund_order(ctx, order_id, req.amount, req.reason, req.idempotency_key)
    if not result.ok:
        status_code = 403 if result.code == "FORBIDDEN" else 409 if result.code in {"ORDER_NOT_CLOSED", "REFUND_LIMIT"} else 400
        raise HTTPException(status_code=status_code, detail=from_service_result(result))
    return _ok_payload(result)


@router.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    user=Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),
):
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.get_order(ctx, order_id)
    if not result.ok:
        raise HTTPException(status_code=404, detail=from_service_result(result))
    return _ok_payload(result)


@router.post("/orders/{order_id}/items")
async def add_order_items(
    order_id: str,
    req: AddOrderItemsRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),
):
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.add_order_items(
        ctx,
        order_id,
        [item.model_dump() for item in req.items],
        req.idempotency_key,
    )
    if not result.ok:
        status_code = 409 if result.code == "ORDER_NOT_OPEN" else 400
        raise HTTPException(status_code=status_code, detail=from_service_result(result))
    return _ok_payload(result)


@router.post("/orders/{order_id}/transfer-table")
async def transfer_order_table(
    order_id: str,
    req: TransferOrderTableRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),
):
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.transfer_order_table(ctx, order_id, req.to_table_number)
    if not result.ok:
        status_code = 409 if result.code in {"ORDER_NOT_OPEN", "TABLE_UNAVAILABLE"} else 400
        raise HTTPException(status_code=status_code, detail=from_service_result(result))
    return _ok_payload(result)


@router.post("/orders/{order_id}/adjustment")
async def adjust_order_total(
    order_id: str,
    req: OrderAdjustmentRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),
):
    """Apply a manager-authorized discount or service charge to an open check."""
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.apply_order_adjustment(
        ctx, order_id, req.adjustment_type, req.calculation, req.value, req.reason
    )
    if not result.ok:
        status_code = 403 if result.code == "FORBIDDEN" else 409 if result.code == "ORDER_NOT_OPEN" else 400
        raise HTTPException(status_code=status_code, detail=from_service_result(result))
    return _ok_payload(result)


@router.get("/operations/summary")
async def pos_operations_summary(
    outlet_id: str | None = None,
    user=Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),
):
    """Live manager board: open checks, kitchen SLA and cashier reconciliation."""
    from datetime import UTC, datetime

    from core.database import db

    tenant_id = user.tenant_id
    settings = await db.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0, "business_date": 1})
    business_date = str((settings or {}).get("business_date") or datetime.now(UTC).date().isoformat())
    order_query = {"tenant_id": tenant_id, "status": {"$in": ["pending", "preparing", "ready"]}, "payment_status": {"$ne": "paid"}}
    tx_query = {"tenant_id": tenant_id, "transaction_date": business_date, "status": {"$in": ["completed", "refunded"]}}
    kitchen_query = {"tenant_id": tenant_id, "status": {"$in": ["pending", "preparing", "ready"]}}
    if outlet_id:
        order_query["outlet_id"] = outlet_id
        tx_query["outlet_id"] = outlet_id
        kitchen_query["outlet_id"] = outlet_id
    open_orders = await db.pos_orders.find(order_query, {"_id": 0}).sort("created_at", 1).limit(500).to_list(500)
    transactions = await db.pos_transactions.find(tx_query, {"_id": 0}).limit(5000).to_list(5000)
    kitchen = await db.kitchen_orders.find(kitchen_query, {"_id": 0}).sort("ordered_at", 1).limit(1000).to_list(1000)
    now = datetime.now(UTC)
    overdue_kitchen = 0
    for ticket in kitchen:
        try:
            ordered = datetime.fromisoformat(str(ticket.get("ordered_at", "")).replace("Z", "+00:00"))
            overdue_kitchen += int((now - ordered).total_seconds() > 20 * 60)
        except ValueError:
            continue
    payments: dict[str, float] = {}
    refunds = 0.0
    for transaction in transactions:
        amount = float(transaction.get("total_amount") or transaction.get("amount") or 0)
        if transaction.get("status") == "refunded" or transaction.get("payment_type") == "refund":
            refunds += abs(amount)
            continue
        breakdown = transaction.get("payment_breakdown") or [{"method": transaction.get("payment_method") or "unknown", "amount": amount}]
        for part in breakdown:
            method = str(part.get("method") or "unknown")
            payments[method] = round(payments.get(method, 0) + float(part.get("amount") or 0), 2)
    return {
        "business_date": business_date,
        "open_orders": open_orders,
        "open_check_count": len(open_orders),
        "open_check_total": round(sum(float(row.get("grand_total") or 0) for row in open_orders), 2),
        "kitchen_open_count": len(kitchen),
        "kitchen_overdue_count": overdue_kitchen,
        "payment_methods": payments,
        "refund_total": round(refunds, 2),
        "net_collected": round(sum(payments.values()) - refunds, 2),
    }


@router.post("/orders/void")
async def void_order(
    req: VoidOrderRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v99 DW
):
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.void_order(ctx, req.order_id, reason=req.reason)
    if not result.ok:
        if result.code == "FORBIDDEN":
            status_code = 403
        elif result.code == "ORDER_CLOSED":
            # Terminal-state conflict — closed orders require refund flow.
            status_code = 409
        else:
            status_code = 400
        raise HTTPException(status_code=status_code, detail=from_service_result(result))
    return _ok_payload(result)


@router.post("/stock/adjust")
async def adjust_stock(
    req: StockAdjustRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v98 DW
):
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.adjust_stock(ctx, req.product_id, req.adjustment_type, req.quantity, req.reason, req.idempotency_key)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


@router.post("/tables/reserve")
async def reserve_table(
    req: TableReserveRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_module_v101("pos")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.reserve_table(ctx, req.outlet_id, req.table_number, req.guest_name, req.reservation_time, req.party_size)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


@router.post("/tabs/open")
async def open_tab(
    req: OpenTabRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    ctx = OperationContext.from_user(user)
    items_dicts = [item.model_dump() for item in req.items]
    result = await pos_fnb_service_v2.open_tab(ctx, req.outlet_id, req.table_number, items_dicts, req.guest_name, req.guests, req.idempotency_key)
    if not result.ok:
        # Duplicate open tab on the same table → 409 conflict; else 400.
        status_code = 409 if result.code == "TAB_ALREADY_OPEN" else 400
        raise HTTPException(status_code=status_code, detail=from_service_result(result))
    return _ok_payload(result)


@router.post("/tabs/close")
async def close_tab(
    req: CloseTabRequest,
    user=Depends(get_current_user),
    _perm=Depends(require_module_v99("pos")),  # v99 DW
):
    ctx = OperationContext.from_user(user)
    result = await pos_fnb_service_v2.close_tab(ctx, req.transaction_id, req.payment_method)
    if not result.ok:
        status_code = 404 if result.code == "NOT_FOUND" else 400
        raise HTTPException(status_code=status_code, detail=from_service_result(result))
    return _ok_payload(result)
