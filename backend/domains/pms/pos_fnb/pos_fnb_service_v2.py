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

from fastapi import HTTPException

from common.audit_hook import SEVERITY_CRITICAL, SEVERITY_INFO, SEVERITY_WARNING, audited
from common.context import OperationContext
from common.result import ServiceResult
from core.booking_atomicity import (
    is_replica_set_unavailable,
    standalone_fallback_allowed,
    with_resource_locks,
)
from core.outbox_service import (
    POS_CHARGE_POSTED,
    POS_CHARGE_REVERSED,
    enqueue_outbox_event,
)

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
            existing = await self._db.pos_orders.find_one({"idempotency_key": idempotency_key, "tenant_id": ctx.tenant_id})
            if existing:
                existing.pop("_id", None)
                return ServiceResult.success({"message": "Order already exists (idempotent)", "order": existing, "idempotent": True})

        if not items or len(items) == 0:
            return ServiceResult.fail("Order must have at least one item", "VALIDATION_ERROR")

        # Validate table availability for dine-in
        if order_type == "dine_in" and table_number:
            table = await self._db.table_layouts.find_one({"table_number": table_number, "outlet_id": outlet_id, "tenant_id": ctx.tenant_id})
            if table and table.get("status") == "reserved":
                return ServiceResult.fail(f"Table {table_number} is reserved", "TABLE_RESERVED")

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
            order_items.append(
                {
                    "item_id": item.get("item_id", str(uuid.uuid4())),
                    "item_name": item.get("name", "Unknown"),
                    "quantity": qty,
                    "unit_price": price,
                    "total": item_total,
                    "station": item.get("station", "main"),
                    "special_instructions": item.get("special_instructions"),
                    "status": "pending",
                }
            )

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

        return ServiceResult.success(
            {
                "order_id": order_id,
                "order_number": order_number,
                "items_count": len(order_items),
                "total_amount": total_amount,
                "tax_amount": tax_amount,
                "grand_total": grand_total,
            }
        )

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
            existing_txn = await self._db.pos_transactions.find_one({"idempotency_key": idempotency_key, "tenant_id": ctx.tenant_id})
            if existing_txn:
                return ServiceResult.success({"message": "Payment already processed (idempotent)", "idempotent": True})

        order = await self._db.pos_orders.find_one({"id": order_id, "tenant_id": ctx.tenant_id}, {"_id": 0})
        if not order:
            return ServiceResult.fail("Order not found", "NOT_FOUND")
        # Terminal-state guard: a voided order MUST NOT be closeable.
        # CI 2026-05-25 (98-pos-deep-lifecycle G) failed because close
        # silently succeeded on a voided order. Void is a terminal state
        # for the order lifecycle — reject with 4xx (CONFLICT).
        if order.get("status") == "voided":
            return ServiceResult.fail("Cannot close a voided order", "ORDER_VOIDED")
        if order.get("status") == "closed":
            return ServiceResult.success({"message": "Order already closed (idempotent)", "idempotent": True})
        if order.get("payment_status") == "paid":
            return ServiceResult.success({"message": "Already paid (idempotent)", "idempotent": True})

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
        # Task #389 — Outbox/Compensation. Resolve the target folio (if any)
        # BEFORE the write so the IC folio-posting event is enqueued ATOMICALLY
        # with the transaction record (intent durable). The async, guaranteed,
        # idempotent consumer (core.pos_folio_consumer) applies the folio charge
        # + recalculates the balance from the ledger (single strategy, never
        # $inc) and guards a non-open folio at apply time.
        folio_charge_id = None
        outbox_payload = None
        if post_to_folio and booking_id:
            folio = await self._db.folios.find_one({"booking_id": booking_id, "folio_type": "guest", "status": "open", "tenant_id": ctx.tenant_id})
            if folio:
                folio_charge_id = str(uuid.uuid4())
                charge_doc = {
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
                    # Dedup key for the consumer's partial unique index
                    # ux_folio_charges_pos_source (tenant, source_pos_order_id, line_no).
                    "source_pos_order_id": order_id,
                    "line_no": 0,
                }
                outbox_payload = {
                    "tenant_id": ctx.tenant_id,
                    "folio_id": folio["id"],
                    "source_pos_order_id": order_id,
                    "booking_id": booking_id,
                    "charges": [charge_doc],
                }

        # Atomic intent: transaction record + IC outbox event in ONE Mongo txn.
        await self._persist_txn_and_intent(ctx.tenant_id, txn_doc, order_id, outbox_payload)

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

        # Recipe/BOM consumption: decrement ingredient stock for recipe-linked
        # menu items. Best-effort — stock wiring must never roll back a
        # completed payment — but each decrement is individually atomic,
        # tenant-scoped and overdraft-safe. Runs exactly once per order because
        # the idempotency/terminal-state guards above return early on re-close.
        try:
            await self._consume_recipe_stock(ctx, order)
        except Exception:  # noqa: BLE001 — never break payment on stock failure
            logger.exception(
                "Recipe stock consumption failed for order %s (tenant %s)",
                order_id,
                ctx.tenant_id,
            )

        return ServiceResult.success(
            {
                "message": "Order closed and payment processed",
                "order_id": order_id,
                "transaction_id": txn_id,
                "amount_paid": total_with_tip,
                "payment_method": payment_method,
                "folio_charge_id": folio_charge_id,
                "posted_to_folio": post_to_folio and folio_charge_id is not None,
            }
        )

    # ==================================================================
    # Atomic intent persistence — Task #389
    # ==================================================================
    async def _persist_txn_and_intent(
        self,
        tenant_id: str,
        txn_doc: dict,
        order_id: str,
        outbox_payload: dict | None,
    ) -> None:
        """Write the POS transaction record + IC outbox event in ONE Mongo txn.

        Either both land or neither does — the order's payment record and the
        durable intent to post the folio charge stay consistent. When there is
        no folio target (``outbox_payload is None``) only the transaction record
        is written.
        """

        async def _txn(session) -> None:
            await self._db.pos_transactions.insert_one(txn_doc, session=session)
            if outbox_payload:
                await enqueue_outbox_event(
                    self._db,
                    session=session,
                    tenant_id=tenant_id,
                    event_type=POS_CHARGE_POSTED,
                    entity_type="folio",
                    entity_id=order_id,
                    payload=outbox_payload,
                )

        try:
            await with_resource_locks(
                client=self._db.client,
                db=self._db,
                tenant_id=tenant_id,
                locks_collection="folio_locks",
                resources=[],
                callback=_txn,
            )
        except Exception as exc:  # noqa: BLE001
            if not is_replica_set_unavailable(exc):
                raise
            if not standalone_fallback_allowed():
                raise HTTPException(
                    status_code=503,
                    detail=("POS işlem yazımı atomik garanti sağlayamıyor (Mongo replica set gerekli)."),
                )
            # Dev opt-in: best-effort non-transactional fallback. The outbox
            # idempotency_key still dedups the enqueue; only all-or-nothing is
            # relaxed.
            await _txn(None)

    async def _publish_charge_reversal(
        self,
        tenant_id: str,
        order_id: str,
        folio_id: str | None,
        reason: str,
    ) -> None:
        """Publish the IC compensation event that idempotently reverses a prior
        POS folio posting for ``order_id`` (Task #389)."""
        await enqueue_outbox_event(
            self._db,
            tenant_id=tenant_id,
            event_type=POS_CHARGE_REVERSED,
            entity_type="folio",
            entity_id=order_id,
            payload={
                "tenant_id": tenant_id,
                "folio_id": folio_id,
                "source_pos_order_id": order_id,
                "reason": reason,
            },
        )

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

        order = await self._db.pos_orders.find_one({"id": order_id, "tenant_id": ctx.tenant_id}, {"_id": 0})
        if not order:
            return ServiceResult.fail("Order not found", "NOT_FOUND")
        if order.get("status") == "voided":
            return ServiceResult.success({"message": "Already voided", "idempotent": True})
        # Terminal-state guard: a closed (paid) order MUST NOT be voided.
        # Architect review 2026-05-25: void of a closed order would regress
        # lifecycle state and bypass the dedicated refund/reversal workflow,
        # leaving folio/ledger invariants inconsistent. Reject with CONFLICT
        # and require an explicit refund flow for post-close reversals.
        if order.get("status") == "closed":
            return ServiceResult.fail("Cannot void a closed order; use refund/reversal flow", "ORDER_CLOSED")

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
            # Task #389 — Compensation. Publish the IC reversal event so the
            # async consumer idempotently voids any POS folio charge posted for
            # this order and recalculates the balance from the ledger
            # (double-reversal safe). Resolve the folio for the recalc target.
            folio_id = None
            booking_id = order.get("booking_id")
            if booking_id:
                folio = await self._db.folios.find_one(
                    {"booking_id": booking_id, "folio_type": "guest", "tenant_id": ctx.tenant_id},
                    {"_id": 0, "id": 1},
                )
                folio_id = folio["id"] if folio else None
            await self._publish_charge_reversal(ctx.tenant_id, order_id, folio_id, reason or "POS order voided")

        # Restore any ingredient stock this order consumed at close time.
        # Best-effort and idempotent (per-record reversal flag). For the
        # current lifecycle a closed order can only be reversed via the
        # dedicated refund flow (void rejects closed orders above), so this is
        # a safe no-op for the normal pending→void path while keeping the
        # consume/restore pair symmetric and reusable by any reversal flow.
        try:
            await self._restore_recipe_stock(ctx, order_id)
        except Exception:  # noqa: BLE001 — never break void on stock failure
            logger.exception(
                "Recipe stock restore failed for order %s (tenant %s)",
                order_id,
                ctx.tenant_id,
            )

        return ServiceResult.success(
            {
                "message": "Order voided",
                "order_id": order_id,
                "reason": reason,
            }
        )

    # ==================================================================
    # Recipe/BOM Stock Consumption — close → decrement, void → restore
    # ==================================================================
    async def _consume_recipe_stock(self, ctx: OperationContext, order: dict) -> None:
        """Decrement ingredient stock for recipe-linked menu items on close.

        For every ordered item that maps to a recipe, each recipe ingredient
        line is decremented by ``bom_qty * ordered_qty`` from
        ``db.ingredients.current_stock``. Each decrement uses the same atomic,
        overdraft-safe guard as ``POST /api/accounting/inventory/movement``
        (conditional ``$gte`` update → stock can never go negative) and is
        tenant-scoped. A ``stock_consumptions`` record is written per ingredient
        so the consumption can be reversed on void.
        """
        order_items = order.get("order_items") or []
        if not order_items:
            return

        recipes = await self._db.recipes.find({"tenant_id": ctx.tenant_id}, {"_id": 0}).to_list(1000)
        if not recipes:
            return

        # Index recipes by every plausible join key so we can resolve an
        # ordered item whether the client referenced the recipe by id, by
        # menu_item_id, or only by the displayed dish/menu-item name.
        by_id: dict[str, dict] = {}
        by_name: dict[str, dict] = {}
        for r in recipes:
            for key in (r.get("id"), r.get("menu_item_id")):
                if key:
                    by_id[str(key)] = r
            for nm in (r.get("dish_name"), r.get("menu_item_name")):
                if nm:
                    by_name[str(nm).strip().lower()] = r

        # Aggregate required quantity per ingredient across the whole order so
        # an ingredient shared by multiple lines is decremented once.
        required: dict[str, dict] = {}
        for item in order_items:
            ordered_qty = item.get("quantity", 1) or 0
            if ordered_qty <= 0:
                continue
            recipe = by_id.get(str(item.get("recipe_id"))) or by_id.get(str(item.get("item_id"))) or by_name.get((item.get("item_name") or "").strip().lower())
            if not recipe:
                continue
            for line in recipe.get("ingredients", []):
                ing_id = line.get("ingredient_id")
                if not ing_id:
                    continue
                bom_qty = line.get("quantity", 0) or 0
                if bom_qty <= 0:
                    continue
                agg = required.setdefault(ing_id, {"qty": 0.0, "name": line.get("ingredient_name")})
                agg["qty"] += bom_qty * ordered_qty

        if not required:
            return

        now = datetime.now(UTC)
        for ing_id, info in required.items():
            need = round(info["qty"], 4)
            if need <= 0:
                continue

            # Atomic overdraft-safe decrement: only succeeds if enough stock is
            # available, so current_stock can never go negative.
            res = await self._db.ingredients.update_one(
                {
                    "id": ing_id,
                    "tenant_id": ctx.tenant_id,
                    "current_stock": {"$gte": need},
                },
                {
                    "$inc": {"current_stock": -need},
                    "$set": {"updated_at": now.isoformat()},
                },
            )
            if res.modified_count == 1:
                applied, overdraft = need, 0.0
            else:
                # Insufficient stock (or ingredient missing). Never go negative:
                # leave stock untouched and record the shortfall for visibility.
                applied, overdraft = 0.0, need
                logger.warning(
                    "Ingredient %s short on stock for order %s (tenant %s): needed %s, not decremented (overdraft guard)",
                    ing_id,
                    order.get("id"),
                    ctx.tenant_id,
                    need,
                )

            await self._db.stock_consumptions.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": ctx.tenant_id,
                    "order_id": order.get("id"),
                    "ingredient_id": ing_id,
                    "ingredient_name": info.get("name"),
                    "required_quantity": need,
                    "consumed_quantity": applied,
                    "overdraft_quantity": overdraft,
                    "reversed": False,
                    "created_by": ctx.actor_id,
                    "created_at": now.isoformat(),
                }
            )

    async def _restore_recipe_stock(self, ctx: OperationContext, order_id: str) -> None:
        """Restore ingredient stock consumed by an order when it is reversed.

        Reads the order's non-reversed ``stock_consumptions`` records and adds
        the actually-consumed quantity back to ``db.ingredients.current_stock``.
        Idempotent: the reversal flag is flipped atomically before the restore
        so a concurrent/duplicate reversal cannot double-credit stock.
        """
        records = await self._db.stock_consumptions.find(
            {
                "order_id": order_id,
                "tenant_id": ctx.tenant_id,
                "reversed": {"$ne": True},
            },
            {"_id": 0},
        ).to_list(1000)
        if not records:
            return

        now = datetime.now(UTC)
        for rec in records:
            # Flip the reversal flag first; only restore if WE flipped it.
            flip = await self._db.stock_consumptions.update_one(
                {
                    "id": rec.get("id"),
                    "tenant_id": ctx.tenant_id,
                    "reversed": {"$ne": True},
                },
                {
                    "$set": {
                        "reversed": True,
                        "reversed_at": now.isoformat(),
                        "reversed_by": ctx.actor_id,
                    }
                },
            )
            if flip.modified_count != 1:
                continue
            qty = rec.get("consumed_quantity", 0) or 0
            if qty > 0:
                await self._db.ingredients.update_one(
                    {"id": rec.get("ingredient_id"), "tenant_id": ctx.tenant_id},
                    {
                        "$inc": {"current_stock": qty},
                        "$set": {"updated_at": now.isoformat()},
                    },
                )

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
            existing = await self._db.inventory_movements.find_one({"idempotency_key": idempotency_key, "tenant_id": ctx.tenant_id})
            if existing:
                return ServiceResult.success({"message": "Adjustment already processed", "idempotent": True})

        if quantity <= 0:
            return ServiceResult.fail("Quantity must be positive", "VALIDATION_ERROR")

        if adjustment_type not in ("in", "out", "set"):
            return ServiceResult.fail("Invalid adjustment type. Use: in, out, set", "VALIDATION_ERROR")

        product = await self._db.inventory.find_one({"id": product_id, "tenant_id": ctx.tenant_id})
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

        return ServiceResult.success(
            {
                "message": "Stock adjusted",
                "product_id": product_id,
                "previous_quantity": current_qty,
                "new_quantity": new_qty,
                "adjustment_type": adjustment_type,
            }
        )

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
        table = await self._db.table_layouts.find_one({"table_number": table_number, "outlet_id": outlet_id, "tenant_id": ctx.tenant_id})
        if not table:
            return ServiceResult.fail("Table not found", "NOT_FOUND")
        if table.get("status") in ("occupied", "reserved"):
            return ServiceResult.fail(f"Table {table_number} is {table.get('status')}", "TABLE_UNAVAILABLE")

        reservation_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        await self._db.table_reservations.insert_one(
            {
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
            }
        )

        await self._db.table_layouts.update_one(
            {"table_number": table_number, "outlet_id": outlet_id, "tenant_id": ctx.tenant_id},
            {"$set": {"status": "reserved", "reserved_for": guest_name}},
        )

        return ServiceResult.success(
            {
                "reservation_id": reservation_id,
                "table_number": table_number,
                "guest_name": guest_name,
                "reservation_time": reservation_time,
            }
        )

    # ==================================================================
    # Open Tab — running bill on a table (status='open')
    # ==================================================================
    # The transfer-table endpoint (`/api/pos/transfer-table`) operates on
    # `pos_transactions` rows with status='open'. `create_order` writes
    # pos_orders (status='pending') and `close_order` writes pos_transactions
    # with status='completed' — neither ever produces an OPEN transaction.
    # This minimal "open tab" surface is the missing production write path:
    # it opens a running bill so a table can be transferred (or settled)
    # before payment.
    @audited("pos.open_tab", "pos_transaction", severity=SEVERITY_INFO)
    async def open_tab(
        self,
        ctx: OperationContext,
        outlet_id: str,
        table_number: str,
        items: list[dict] | None = None,
        guest_name: str | None = None,
        guests: int = 1,
        idempotency_key: str | None = None,
    ) -> ServiceResult:
        if not table_number:
            return ServiceResult.fail("table_number is required to open a tab", "VALIDATION_ERROR")

        # Idempotency guard.
        if idempotency_key:
            existing = await self._db.pos_transactions.find_one({"idempotency_key": idempotency_key, "tenant_id": ctx.tenant_id}, {"_id": 0})
            if existing:
                return ServiceResult.success(
                    {
                        "message": "Tab already open (idempotent)",
                        "transaction_id": existing.get("id"),
                        "status": existing.get("status"),
                        "idempotent": True,
                    }
                )

        # One open tab per (tenant, outlet, table) — a second open tab on the
        # same table would make transfer/check-split ambiguous.
        dup = await self._db.pos_transactions.find_one(
            {
                "tenant_id": ctx.tenant_id,
                "outlet_id": outlet_id,
                "table_number": table_number,
                "status": "open",
            }
        )
        if dup:
            return ServiceResult.fail(f"Table {table_number} already has an open tab", "TAB_ALREADY_OPEN")

        now = datetime.now(UTC)
        txn_id = str(uuid.uuid4())
        line_items = []
        total_amount = 0.0
        for item in items or []:
            qty = item.get("quantity", 1)
            price = item.get("price", 0.0)
            line_total = round(qty * price, 2)
            total_amount += line_total
            line_items.append(
                {
                    "item_id": item.get("item_id", str(uuid.uuid4())),
                    "item_name": item.get("name", "Unknown"),
                    "quantity": qty,
                    "unit_price": price,
                    "total": line_total,
                    "station": item.get("station", "main"),
                }
            )
        total_amount = round(total_amount, 2)

        txn_doc = {
            "id": txn_id,
            "tenant_id": ctx.tenant_id,
            "outlet_id": outlet_id,
            "table_number": table_number,
            "guest_name": guest_name or "Walk-in",
            "guests": guests,
            "order_items": line_items,
            "amount": total_amount,
            "total_amount": total_amount,
            "status": "open",
            "opened_by": ctx.actor_id,
            "idempotency_key": idempotency_key,
            "created_at": now.isoformat(),
        }
        await self._db.pos_transactions.insert_one(txn_doc)

        # Mark table occupied (best-effort — table_layouts row may not exist).
        await self._db.table_layouts.update_one(
            {"table_number": table_number, "outlet_id": outlet_id, "tenant_id": ctx.tenant_id},
            {"$set": {"status": "occupied", "current_transaction_id": txn_id}},
        )

        return ServiceResult.success(
            {
                "transaction_id": txn_id,
                "table_number": table_number,
                "outlet_id": outlet_id,
                "total_amount": total_amount,
                "status": "open",
            }
        )

    # ==================================================================
    # Close Tab — settle an open tab (status open → completed)
    # ==================================================================
    @audited("pos.close_tab", "pos_transaction", severity=SEVERITY_INFO, capture_before=True)
    async def close_tab(
        self,
        ctx: OperationContext,
        transaction_id: str,
        payment_method: str = "cash",
    ) -> ServiceResult:
        txn = await self._db.pos_transactions.find_one({"id": transaction_id, "tenant_id": ctx.tenant_id}, {"_id": 0})
        if not txn:
            return ServiceResult.fail("Open tab not found", "NOT_FOUND")
        if txn.get("status") == "completed":
            return ServiceResult.success(
                {
                    "message": "Tab already closed (idempotent)",
                    "transaction_id": transaction_id,
                    "idempotent": True,
                }
            )
        if txn.get("status") != "open":
            return ServiceResult.fail(f"Tab is in terminal state '{txn.get('status')}'", "TAB_NOT_OPEN")

        now = datetime.now(UTC)
        # SECURITY: tenant_id filter required (defense-in-depth).
        await self._db.pos_transactions.update_one(
            {"id": transaction_id, "tenant_id": ctx.tenant_id},
            {
                "$set": {
                    "status": "completed",
                    "payment_method": payment_method,
                    "closed_at": now.isoformat(),
                    "closed_by": ctx.actor_id,
                }
            },
        )

        # Release table.
        if txn.get("table_number") and txn.get("outlet_id"):
            await self._db.table_layouts.update_one(
                {"table_number": txn["table_number"], "outlet_id": txn["outlet_id"], "tenant_id": ctx.tenant_id},
                {"$set": {"status": "dirty", "current_transaction_id": None}},
            )

        return ServiceResult.success(
            {
                "message": "Tab closed",
                "transaction_id": transaction_id,
                "status": "completed",
                "payment_method": payment_method,
            }
        )


pos_fnb_service_v2 = PosFnbServiceV2()
