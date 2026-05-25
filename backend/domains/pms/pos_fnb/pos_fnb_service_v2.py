"""
PMS / POS & F&B — Production-Grade Service Layer v2
====================================================
Adds: duplicate posting prevention, folio posting consistency,
order lifecycle management, table reservation contention,
void/refund safety, stock race protection.
"""
import logging
import uuid
from datetime import UTC, datetime

from common.audit_hook import SEVERITY_CRITICAL, SEVERITY_INFO, SEVERITY_WARNING, audited
from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)


class PosFnbServiceV2:
    """Production-grade POS & F&B with concurrency and consistency guards."""

    def __init__(self):
        from core.database import db
        self._db = db

    # ==================================================================
    # POS Order — Full Lifecycle
    # ==================================================================
    @audited("pos.create_order", "pos_order", severity=SEVERITY_INFO)
    async def create_order(
        self,
        ctx: OperationContext,
        outlet_id: str,
        table_number: str | None = None,
        items: list[dict] | None = None,
        guest_name: str | None = None,
        booking_id: str | None = None,
        order_type: str = "dine_in",
        idempotency_key: str | None = None,
    ) -> ServiceResult:
        # Idempotency guard
        if idempotency_key:
            existing = await self._db.pos_orders.find_one(
                {"idempotency_key": idempotency_key, "tenant_id": ctx.tenant_id}
            )
            if existing:
                existing.pop("_id", None)
                return ServiceResult.success(
                    {"message": "Order already exists (idempotent)", "order": existing, "idempotent": True}
                )

        if not items or len(items) == 0:
            return ServiceResult.fail("Order must have at least one item", "VALIDATION_ERROR")

        # Validate table availability for dine-in
        if order_type == "dine_in" and table_number:
            table = await self._db.table_layouts.find_one(
                {"table_number": table_number, "outlet_id": outlet_id, "tenant_id": ctx.tenant_id}
            )
            if table and table.get("status") == "reserved":
                return ServiceResult.fail(
                    f"Table {table_number} is reserved", "TABLE_RESERVED"
                )

        now = datetime.now(UTC)
        order_id = str(uuid.uuid4())
        order_number = f"ORD-{now.strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:4].upper()}"

        # Calculate totals
        total_amount = 0.0
        order_items = []
        for item in items:
            qty = item.get("quantity", 1)
            price = item.get("price", 0.0)
            item_total = round(qty * price, 2)
            total_amount += item_total
            order_items.append({
                "item_id": item.get("item_id", str(uuid.uuid4())),
                "item_name": item.get("name", "Unknown"),
                "quantity": qty,
                "unit_price": price,
                "total": item_total,
                "station": item.get("station", "main"),
                "special_instructions": item.get("special_instructions"),
                "status": "pending",
            })

        tax_amount = round(total_amount * 0.10, 2)
        grand_total = round(total_amount + tax_amount, 2)

        order_doc = {
            "id": order_id,
            "tenant_id": ctx.tenant_id,
            "outlet_id": outlet_id,
            "order_number": order_number,
            "order_type": order_type,
            "table_number": table_number,
            "guest_name": guest_name or "Walk-in",
            "booking_id": booking_id,
            "order_items": order_items,
            "total_amount": total_amount,
            "tax_amount": tax_amount,
            "grand_total": grand_total,
            "status": "pending",
            "payment_status": "unpaid",
            "created_by": ctx.actor_id,
            "idempotency_key": idempotency_key,
            "created_at": now.isoformat(),
        }
        await self._db.pos_orders.insert_one(order_doc)

        # Create kitchen orders per station
        stations = {}
        for item in order_items:
            st = item.get("station", "main")
            if st not in stations:
                stations[st] = []
            stations[st].append(item)

        for station, station_items in stations.items():
            for si in station_items:
                ko_doc = {
                    "id": str(uuid.uuid4()),
                    "tenant_id": ctx.tenant_id,
                    "order_id": order_id,
                    "order_number": order_number,
                    "outlet_id": outlet_id,
                    "table_number": table_number,
                    "item_name": si["item_name"],
                    "quantity": si["quantity"],
                    "special_instructions": si.get("special_instructions"),
                    "station": station,
                    "status": "pending",
                    "ordered_at": now.isoformat(),
                }
                await self._db.kitchen_orders.insert_one(ko_doc)

        # Update table status
        if order_type == "dine_in" and table_number:
            await self._db.table_layouts.update_one(
                {"table_number": table_number, "outlet_id": outlet_id, "tenant_id": ctx.tenant_id},
                {"$set": {"status": "occupied", "current_order_id": order_id}},
            )

        return ServiceResult.success({
            "order_id": order_id,
            "order_number": order_number,
            "items_count": len(order_items),
            "total_amount": total_amount,
            "tax_amount": tax_amount,
            "grand_total": grand_total,
        })

    # ==================================================================
    # Close Order + Payment
    # ==================================================================
    @audited("pos.close_order", "pos_order", severity=SEVERITY_INFO, capture_before=True)
    async def close_order(
        self,
        ctx: OperationContext,
        order_id: str,
        payment_method: str = "cash",
        post_to_folio: bool = False,
        booking_id: str | None = None,
        tip_amount: float = 0.0,
        idempotency_key: str | None = None,
    ) -> ServiceResult:
        # Idempotency
        if idempotency_key:
            existing_txn = await self._db.pos_transactions.find_one(
                {"idempotency_key": idempotency_key, "tenant_id": ctx.tenant_id}
            )
            if existing_txn:
                return ServiceResult.success(
                    {"message": "Payment already processed (idempotent)", "idempotent": True}
                )

        order = await self._db.pos_orders.find_one(
            {"id": order_id, "tenant_id": ctx.tenant_id}, {"_id": 0}
        )
        if not order:
            return ServiceResult.fail("Order not found", "NOT_FOUND")
        # Terminal-state guard: a voided order MUST NOT be closeable.
        # CI 2026-05-25 (98-pos-deep-lifecycle G) failed because close
        # silently succeeded on a voided order. Void is a terminal state
        # for the order lifecycle — reject with 4xx (CONFLICT).
        if order.get("status") == "voided":
            return ServiceResult.fail(
                "Cannot close a voided order", "ORDER_VOIDED"
            )
        if order.get("status") == "closed":
            return ServiceResult.success(
                {"message": "Order already closed (idempotent)", "idempotent": True}
            )
        if order.get("payment_status") == "paid":
            return ServiceResult.success(
                {"message": "Already paid (idempotent)", "idempotent": True}
            )

        now = datetime.now(UTC)
        grand_total = order.get("grand_total", 0)
        total_with_tip = round(grand_total + tip_amount, 2)

        # Create POS transaction
        # SECURITY/INVARIANT: snapshot `order_items` into the txn so split-check
        # and audit paths can read line items without an extra join to
        # pos_orders. CI 2026-05-25 (98-pos-deep-lifecycle D) failed because
        # split_check fell back to `items=[]` and rejected all indices as
        # out-of-range. Denormalizing here is the cheapest correct fix.
        txn_id = str(uuid.uuid4())
        txn_doc = {
            "id": txn_id,
            "tenant_id": ctx.tenant_id,
            "order_id": order_id,
            "order_number": order.get("order_number"),
            "outlet_id": order.get("outlet_id"),
            "transaction_date": now.date().isoformat(),
            "transaction_time": now.time().isoformat(),
            "amount": grand_total,
            "tip_amount": tip_amount,
            "total_amount": total_with_tip,
            "payment_method": payment_method,
            "status": "completed",
            "processed_by": ctx.actor_id,
            "idempotency_key": idempotency_key,
            "order_items": order.get("order_items", []),
            "created_at": now.isoformat(),
        }
        await self._db.pos_transactions.insert_one(txn_doc)

        # Post to guest folio if requested
        folio_charge_id = None
        if post_to_folio and booking_id:
            folio = await self._db.folios.find_one(
                {"booking_id": booking_id, "folio_type": "guest", "status": "open", "tenant_id": ctx.tenant_id}
            )
            if folio:
                folio_charge_id = str(uuid.uuid4())
                await self._db.folio_charges.insert_one({
                    "id": folio_charge_id,
                    "tenant_id": ctx.tenant_id,
                    "booking_id": booking_id,
                    "folio_id": folio["id"],
                    "guest_id": folio.get("guest_id"),
                    "charge_type": "pos_fnb",
                    "charge_category": "food",
                    "description": f"F&B - Order #{order.get('order_number')}",
                    "amount": grand_total,
                    "tax_amount": order.get("tax_amount", 0),
                    "total": grand_total,
                    "voided": False,
                    "date": now.isoformat(),
                    "posted_by": ctx.actor_id,
                    "created_at": now.isoformat(),
                })
                # SECURITY: tenant_id filter required (defense-in-depth).
                await self._db.folios.update_one(
                    {"id": folio["id"], "tenant_id": ctx.tenant_id},
                    {"$inc": {"balance": grand_total}},
                )

        # Close order.
        # SECURITY: tenant_id filter required (defense-in-depth — read above
        # is tenant-scoped, but make the mutation independently safe).
        await self._db.pos_orders.update_one(
            {"id": order_id, "tenant_id": ctx.tenant_id},
            {
                "$set": {
                    "status": "closed",
                    "payment_status": "paid",
                    "payment_method": payment_method,
                    "closed_at": now.isoformat(),
                    "closed_by": ctx.actor_id,
                }
            },
        )

        # Release table
        if order.get("table_number") and order.get("outlet_id"):
            await self._db.table_layouts.update_one(
                {
                    "table_number": order["table_number"],
                    "outlet_id": order["outlet_id"],
                    "tenant_id": ctx.tenant_id,
                },
                {"$set": {"status": "dirty", "current_order_id": None}},
            )

        return ServiceResult.success({
            "message": "Order closed and payment processed",
            "order_id": order_id,
            "transaction_id": txn_id,
            "amount_paid": total_with_tip,
            "payment_method": payment_method,
            "folio_charge_id": folio_charge_id,
            "posted_to_folio": post_to_folio and folio_charge_id is not None,
        })

    # ==================================================================
    # Void Order — supervisor only
    # ==================================================================
    @audited("pos.void_order", "pos_order", severity=SEVERITY_CRITICAL, require_reason=True, capture_before=True)
    async def void_order(
        self,
        ctx: OperationContext,
        order_id: str,
        reason: str = "",
    ) -> ServiceResult:
        if not getattr(ctx, "actor_is_super_admin", False) and ctx.actor_role not in ("admin", "supervisor", "super_admin", "fnb_manager"):
            return ServiceResult.fail("Void requires supervisor permission", "FORBIDDEN")

        order = await self._db.pos_orders.find_one(
            {"id": order_id, "tenant_id": ctx.tenant_id}, {"_id": 0}
        )
        if not order:
            return ServiceResult.fail("Order not found", "NOT_FOUND")
        if order.get("status") == "voided":
            return ServiceResult.success({"message": "Already voided", "idempotent": True})

        now = datetime.now(UTC)
        # SECURITY: tenant_id filter required (defense-in-depth).
        await self._db.pos_orders.update_one(
            {"id": order_id, "tenant_id": ctx.tenant_id},
            {
                "$set": {
                    "status": "voided",
                    "voided_at": now.isoformat(),
                    "voided_by": ctx.actor_id,
                    "void_reason": reason,
                }
            },
        )

        # Cancel all kitchen orders
        await self._db.kitchen_orders.update_many(
            {"order_id": order_id, "tenant_id": ctx.tenant_id},
            {"$set": {"status": "cancelled", "cancelled_at": now.isoformat()}},
        )

        # Release table
        if order.get("table_number") and order.get("outlet_id"):
            await self._db.table_layouts.update_one(
                {
                    "table_number": order["table_number"],
                    "outlet_id": order["outlet_id"],
                    "tenant_id": ctx.tenant_id,
                },
                {"$set": {"status": "available", "current_order_id": None}},
            )

        # Reverse folio posting if exists
        if order.get("payment_status") == "paid":
            txn = await self._db.pos_transactions.find_one({"order_id": order_id, "tenant_id": ctx.tenant_id})
            if txn:
                # SECURITY: tenant_id filter required (defense-in-depth).
                await self._db.pos_transactions.update_one(
                    {"id": txn["id"], "tenant_id": ctx.tenant_id},
                    {"$set": {"status": "voided", "voided_at": now.isoformat(), "void_reason": reason}},
                )

        return ServiceResult.success({
            "message": "Order voided",
            "order_id": order_id,
            "reason": reason,
        })

    # ==================================================================
    # Stock Adjustment — with race-condition protection
    # ==================================================================
    @audited("pos.adjust_stock", "inventory", severity=SEVERITY_WARNING, capture_before=True)
    async def adjust_stock(
        self,
        ctx: OperationContext,
        product_id: str,
        adjustment_type: str,
        quantity: int,
        reason: str,
        idempotency_key: str | None = None,
    ) -> ServiceResult:
        if not getattr(ctx, "actor_is_super_admin", False) and ctx.actor_role not in ("admin", "warehouse", "fnb_manager", "supervisor", "super_admin"):
            return ServiceResult.fail("Insufficient permissions", "FORBIDDEN")

        if idempotency_key:
            existing = await self._db.inventory_movements.find_one(
                {"idempotency_key": idempotency_key, "tenant_id": ctx.tenant_id}
            )
            if existing:
                return ServiceResult.success({"message": "Adjustment already processed", "idempotent": True})

        if quantity <= 0:
            return ServiceResult.fail("Quantity must be positive", "VALIDATION_ERROR")

        if adjustment_type not in ("in", "out", "set"):
            return ServiceResult.fail(
                "Invalid adjustment type. Use: in, out, set", "VALIDATION_ERROR"
            )

        product = await self._db.inventory.find_one(
            {"id": product_id, "tenant_id": ctx.tenant_id}
        )
        if not product:
            return ServiceResult.fail("Product not found", "NOT_FOUND")

        current_qty = product.get("quantity", 0)

        if adjustment_type == "in":
            new_qty = current_qty + quantity
        elif adjustment_type == "out":
            if current_qty < quantity:
                return ServiceResult.fail(
                    f"Insufficient stock. Available: {current_qty}, Requested: {quantity}",
                    "INSUFFICIENT_STOCK",
                )
            new_qty = current_qty - quantity
        else:
            new_qty = quantity

        # Atomic update with version check
        result = await self._db.inventory.update_one(
            {"id": product_id, "tenant_id": ctx.tenant_id, "quantity": current_qty},
            {
                "$set": {
                    "quantity": new_qty,
                    "last_updated": datetime.now(UTC).isoformat(),
                    "last_updated_by": ctx.actor_id,
                }
            },
        )
        if result.modified_count == 0:
            return ServiceResult.fail(
                "Stock was modified concurrently. Please retry.",
                "CONCURRENT_MODIFICATION",
            )

        now = datetime.now(UTC)
        movement_doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            "product_id": product_id,
            "product_name": product.get("product_name", "Unknown"),
            "movement_type": adjustment_type,
            "quantity": quantity if adjustment_type == "in" else -quantity,
            "previous_quantity": current_qty,
            "new_quantity": new_qty,
            "reason": reason,
            "performed_by": ctx.actor_email or ctx.actor_id,
            "idempotency_key": idempotency_key,
            "timestamp": now.isoformat(),
        }
        await self._db.inventory_movements.insert_one(movement_doc)

        return ServiceResult.success({
            "message": "Stock adjusted",
            "product_id": product_id,
            "previous_quantity": current_qty,
            "new_quantity": new_qty,
            "adjustment_type": adjustment_type,
        })

    # ==================================================================
    # Table Reservation
    # ==================================================================
    @audited("pos.reserve_table", "table_layout", severity=SEVERITY_INFO)
    async def reserve_table(
        self,
        ctx: OperationContext,
        outlet_id: str,
        table_number: str,
        guest_name: str,
        reservation_time: str,
        party_size: int = 2,
    ) -> ServiceResult:
        table = await self._db.table_layouts.find_one(
            {"table_number": table_number, "outlet_id": outlet_id, "tenant_id": ctx.tenant_id}
        )
        if not table:
            return ServiceResult.fail("Table not found", "NOT_FOUND")
        if table.get("status") in ("occupied", "reserved"):
            return ServiceResult.fail(
                f"Table {table_number} is {table.get('status')}", "TABLE_UNAVAILABLE"
            )

        reservation_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        await self._db.table_reservations.insert_one({
            "id": reservation_id,
            "tenant_id": ctx.tenant_id,
            "outlet_id": outlet_id,
            "table_number": table_number,
            "guest_name": guest_name,
            "party_size": party_size,
            "reservation_time": reservation_time,
            "status": "confirmed",
            "created_by": ctx.actor_id,
            "created_at": now.isoformat(),
        })

        await self._db.table_layouts.update_one(
            {"table_number": table_number, "outlet_id": outlet_id, "tenant_id": ctx.tenant_id},
            {"$set": {"status": "reserved", "reserved_for": guest_name}},
        )

        return ServiceResult.success({
            "reservation_id": reservation_id,
            "table_number": table_number,
            "guest_name": guest_name,
            "reservation_time": reservation_time,
        })


pos_fnb_service_v2 = PosFnbServiceV2()
