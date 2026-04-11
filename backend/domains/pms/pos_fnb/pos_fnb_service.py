"""
PMS / POS & F&B — Service Layer
Orchestrates POS transactions, kitchen orders, table management,
F&B dashboards, stock management. No FastAPI dependencies.
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from common.audit_hook import SEVERITY_INFO, SEVERITY_WARNING, audited
from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)


class PosFnbService:
    """Business logic for POS & F&B operations."""

    def __init__(self):
        from core.database import db
        self._db = db

    # ------------------------------------------------------------------
    # Kitchen Orders
    # ------------------------------------------------------------------
    @audited("pos.complete_kitchen_order", "kitchen_order", severity=SEVERITY_INFO)
    async def complete_kitchen_order(self, ctx: OperationContext, order_id: str) -> ServiceResult:
        await self._db.kitchen_orders.update_one(
            {"id": order_id},
            {"$set": {"status": "ready", "ready_at": datetime.now(UTC).isoformat()}},
        )
        return ServiceResult.success({"success": True, "message": "Siparis hazir olarak isaretlendi"})

    async def get_kitchen_display(self, ctx: OperationContext, station: str | None = None, status: str | None = None) -> ServiceResult:
        match = {"tenant_id": ctx.tenant_id, "status": {"$in": ["pending", "preparing"]}}
        if station:
            match["station"] = station
        if status:
            match["status"] = status

        orders = []
        async for order in self._db.kitchen_orders.find(match).sort("ordered_at", 1):
            order.pop("_id", None)
            ordered_at = datetime.fromisoformat(order.get("ordered_at"))
            wait_minutes = (datetime.now(UTC) - ordered_at).total_seconds() / 60
            priority = "urgent" if wait_minutes > 15 else ("high" if wait_minutes > 10 else "normal")
            priority_color = "red" if priority == "urgent" else ("orange" if priority == "high" else "green")
            orders.append({
                "id": order.get("id"), "table_number": order.get("table_number"),
                "item_name": order.get("item_name"), "quantity": order.get("quantity"),
                "special_instructions": order.get("special_instructions"),
                "station": order.get("station"), "status": order.get("status"),
                "wait_minutes": int(wait_minutes), "priority": priority,
                "priority_color": priority_color, "ordered_at": order.get("ordered_at"),
            })

        return ServiceResult.success({
            "station": station or "all", "total_orders": len(orders),
            "pending": sum(1 for o in orders if o["status"] == "pending"),
            "preparing": sum(1 for o in orders if o["status"] == "preparing"),
            "urgent_count": sum(1 for o in orders if o["priority"] == "urgent"),
            "orders": orders,
        })

    @audited("pos.update_kitchen_order_status", "kitchen_order", severity=SEVERITY_INFO)
    async def update_kitchen_order_status(self, ctx: OperationContext, order_id: str, new_status: str) -> ServiceResult:
        updates: dict[str, Any] = {"status": new_status}
        if new_status == "ready":
            updates["ready_at"] = datetime.now(UTC).isoformat()
        elif new_status == "served":
            updates["served_at"] = datetime.now(UTC).isoformat()
        await self._db.kitchen_orders.update_one({"id": order_id, "tenant_id": ctx.tenant_id}, {"$set": updates})
        return ServiceResult.success({"success": True, "order_id": order_id, "new_status": new_status})

    # ------------------------------------------------------------------
    # POS Transactions
    # ------------------------------------------------------------------
    @audited("pos.create_transaction", "pos_transaction", severity=SEVERITY_INFO)
    async def create_pos_transaction(self, ctx: OperationContext, amount: float, payment_method: str, folio_id: str | None = None) -> ServiceResult:
        txn = {
            "id": str(uuid.uuid4()), "tenant_id": ctx.tenant_id,
            "transaction_date": datetime.now(UTC).date().isoformat(),
            "transaction_time": datetime.now(UTC).time().isoformat(),
            "amount": amount, "payment_method": payment_method,
            "folio_id": folio_id, "status": "completed",
            "processed_by": ctx.actor_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await self._db.pos_transactions.insert_one(txn.copy())
        return ServiceResult.success(txn)

    # ------------------------------------------------------------------
    # Table Layout
    # ------------------------------------------------------------------
    async def get_table_layout(self, ctx: OperationContext, outlet_id: str) -> ServiceResult:
        tables = []
        async for table in self._db.table_layouts.find({"tenant_id": ctx.tenant_id, "outlet_id": outlet_id}):
            table.pop("_id", None)
            txn = None
            if table.get("current_transaction_id"):
                txn = await self._db.pos_transactions.find_one({"id": table["current_transaction_id"]})
            tables.append({
                "id": table.get("id"), "table_number": table.get("table_number"),
                "seats": table.get("seats"),
                "position": {"x": table.get("position_x"), "y": table.get("position_y")},
                "shape": table.get("shape"), "width": table.get("width"), "height": table.get("height"),
                "status": table.get("status"), "server_assigned": table.get("server_assigned"),
                "current_bill": round(txn.get("total_amount", 0), 2) if txn else 0,
                "guest_count": txn.get("guests", 0) if txn else 0,
            })

        return ServiceResult.success({
            "outlet_id": outlet_id, "total_tables": len(tables),
            "available": sum(1 for t in tables if t["status"] == "available"),
            "occupied": sum(1 for t in tables if t["status"] == "occupied"),
            "reserved": sum(1 for t in tables if t["status"] == "reserved"),
            "tables": tables,
        })

    # ------------------------------------------------------------------
    # F&B Dashboard
    # ------------------------------------------------------------------
    async def get_fnb_dashboard(self, ctx: OperationContext, date_str: str | None = None) -> ServiceResult:
        if not date_str:
            date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        target = datetime.fromisoformat(date_str)
        start = target.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        charges = await self._db.folio_charges.find({
            "tenant_id": ctx.tenant_id, "voided": False,
            "charge_category": {"$in": ["food", "beverage"]},
            "date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
        }).to_list(10000)

        food_rev = sum(c.get("total", 0) for c in charges if c.get("charge_category") == "food")
        bev_rev = sum(c.get("total", 0) for c in charges if c.get("charge_category") == "beverage")
        total_rev = food_rev + bev_rev

        orders = await self._db.pos_orders.find({
            "tenant_id": ctx.tenant_id,
            "created_at": {"$gte": start.isoformat(), "$lte": end.isoformat()},
        }).to_list(10000)

        orders_count = len(orders)
        avg_val = round(total_rev / orders_count, 2) if orders_count > 0 else 0
        tables_used = len({o.get("table_number") for o in orders if o.get("table_number")})

        return ServiceResult.success({
            "date": date_str,
            "summary": {
                "total_revenue": round(total_rev, 2), "food_revenue": round(food_rev, 2),
                "beverage_revenue": round(bev_rev, 2), "orders_count": orders_count,
                "avg_order_value": avg_val, "tables_used": tables_used,
            },
        })

    # ------------------------------------------------------------------
    # F&B Sales Report
    # ------------------------------------------------------------------
    async def get_fnb_sales_report(self, ctx: OperationContext, start_date: str | None = None, end_date: str | None = None) -> ServiceResult:
        if start_date and end_date:
            start = datetime.fromisoformat(start_date)
            end = datetime.fromisoformat(end_date)
        else:
            end = datetime.now(UTC)
            start = end - timedelta(days=30)

        charges = await self._db.folio_charges.find({
            "tenant_id": ctx.tenant_id, "voided": False,
            "charge_category": {"$in": ["food", "beverage"]},
            "date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
        }).to_list(10000)

        daily: dict[str, dict[str, float]] = {}
        for c in charges:
            ds = c.get("date", "")[:10]
            if ds not in daily:
                daily[ds] = {"food": 0.0, "beverage": 0.0}
            daily[ds][c.get("charge_category", "food")] += c.get("total", 0)

        daily_data = [{"date": d, "food": round(v["food"], 2), "beverage": round(v["beverage"], 2), "total": round(v["food"] + v["beverage"], 2)} for d, v in sorted(daily.items())]
        total_food = sum(d["food"] for d in daily_data)
        total_bev = sum(d["beverage"] for d in daily_data)
        total_sales = total_food + total_bev

        return ServiceResult.success({
            "period": {"start_date": start.strftime("%Y-%m-%d"), "end_date": end.strftime("%Y-%m-%d")},
            "summary": {
                "total_sales": round(total_sales, 2),
                "food_sales": round(total_food, 2), "beverage_sales": round(total_bev, 2),
                "food_percentage": round(total_food / total_sales * 100, 2) if total_sales > 0 else 0,
                "beverage_percentage": round(total_bev / total_sales * 100, 2) if total_sales > 0 else 0,
            },
            "daily_sales": daily_data,
        })

    # ------------------------------------------------------------------
    # Active Orders (mobile)
    # ------------------------------------------------------------------
    async def get_active_orders(self, ctx: OperationContext, status: str | None = None, outlet_id: str | None = None) -> ServiceResult:
        query: dict[str, Any] = {"tenant_id": ctx.tenant_id, "status": {"$in": ["pending", "preparing", "ready"]}}
        if status:
            query["status"] = status
        if outlet_id:
            query["outlet_id"] = outlet_id

        orders = []
        async for order in self._db.pos_orders.find(query).sort("created_at", 1):
            order.pop("_id", None)
            created_at = order.get("created_at")
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            elapsed = (datetime.now(UTC) - created_at).total_seconds() / 60
            is_delayed = order.get("status") in ("pending", "preparing") and elapsed > 30
            orders.append({
                "id": order["id"],
                "order_number": order.get("order_number", order["id"][:8]),
                "status": order.get("status", "pending"),
                "outlet_name": order.get("outlet_name", "Main Restaurant"),
                "table_number": order.get("table_number", "N/A"),
                "guest_name": order.get("guest_name", "Walk-in"),
                "items_count": len(order.get("order_items", [])),
                "total_amount": order.get("total_amount", 0),
                "time_elapsed_minutes": int(elapsed),
                "is_delayed": is_delayed,
                "created_at": order.get("created_at"),
            })

        return ServiceResult.success({
            "orders": orders, "count": len(orders),
            "delayed_count": len([o for o in orders if o["is_delayed"]]),
        })

    # ------------------------------------------------------------------
    # Stock Management
    # ------------------------------------------------------------------
    async def get_stock_levels(self, ctx: OperationContext, category: str | None = None, low_stock_only: bool = False) -> ServiceResult:
        query: dict[str, Any] = {"tenant_id": ctx.tenant_id}
        if category:
            query["category"] = category

        items = []
        async for item in self._db.inventory.find(query):
            item.pop("_id", None)
            qty = item.get("quantity", 0)
            min_qty = item.get("minimum_quantity", 10)
            is_low = qty <= min_qty
            if low_stock_only and not is_low:
                continue
            status = "out_of_stock" if qty == 0 else ("low" if is_low else ("medium" if qty <= min_qty * 2 else "good"))
            color = {"out_of_stock": "red", "low": "orange", "medium": "yellow", "good": "green"}[status]
            items.append({
                "id": item.get("id", str(uuid.uuid4())),
                "product_name": item.get("product_name", item.get("name", "Unknown")),
                "category": item.get("category", "general"),
                "current_quantity": qty, "minimum_quantity": min_qty,
                "is_low_stock": is_low, "stock_status": status, "status_color": color,
            })

        return ServiceResult.success({
            "stock_items": items, "count": len(items),
            "low_stock_count": len([i for i in items if i["is_low_stock"]]),
        })

    @audited("pos.adjust_stock", "inventory", severity=SEVERITY_WARNING, capture_before=True)
    async def adjust_stock(self, ctx: OperationContext, product_id: str, adjustment_type: str, quantity: int, reason: str, notes: str | None = None) -> ServiceResult:
        allowed_roles = ("admin", "warehouse", "fnb_manager", "supervisor")
        if ctx.actor_role not in allowed_roles:
            return ServiceResult.fail("Insufficient permissions", "FORBIDDEN")

        product = await self._db.inventory.find_one({"id": product_id, "tenant_id": ctx.tenant_id})
        if not product:
            return ServiceResult.fail("Product not found", "NOT_FOUND")

        current_qty = product.get("quantity", 0)
        if adjustment_type == "in":
            new_qty = current_qty + quantity
        elif adjustment_type == "out":
            new_qty = current_qty - quantity
            if new_qty < 0:
                return ServiceResult.fail("Insufficient stock", "INSUFFICIENT_STOCK")
        else:
            new_qty = quantity

        await self._db.inventory.update_one(
            {"id": product_id, "tenant_id": ctx.tenant_id},
            {"$set": {"quantity": new_qty, "last_updated": datetime.now(UTC).isoformat()}},
        )

        movement = {
            "id": str(uuid.uuid4()), "tenant_id": ctx.tenant_id,
            "product_id": product_id, "product_name": product.get("product_name", "Unknown"),
            "movement_type": adjustment_type,
            "quantity": quantity if adjustment_type == "in" else -quantity,
            "previous_quantity": current_qty, "new_quantity": new_qty,
            "reason": reason, "notes": notes,
            "performed_by": ctx.actor_email,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await self._db.inventory_movements.insert_one(movement)

        return ServiceResult.success({
            "message": "Stock adjusted successfully",
            "product_id": product_id, "adjustment_type": adjustment_type,
            "previous_quantity": current_qty, "new_quantity": new_qty,
        })


pos_fnb_service = PosFnbService()
