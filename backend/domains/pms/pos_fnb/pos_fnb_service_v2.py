"""
PMS / POS & F&B — Production-Grade Service Layer v2
====================================================
Adds: duplicate posting prevention, folio posting consistency,
order lifecycle management, table reservation contention,
void/refund safety, stock race protection.
"""

import hashlib
import logging
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

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


class PosOrderStateChanged(RuntimeError):
    """The order left its payable state while checkout was in flight."""


class PosTableUnavailable(RuntimeError):
    """A table could not be atomically claimed for a new dine-in order."""


class PosFnbServiceV2:
    """Production-grade POS & F&B with concurrency and consistency guards."""

    def __init__(self):
        from core.database import db

        self._db = db

    async def _broadcast_kitchen_queue(self, tenant_id: str) -> None:
        """Push the current queue after waiter-side writes.

        KitchenDisplay also polls, so a websocket failure must never roll back
        a valid order.  The push merely removes the otherwise visible delay.
        """
        try:
            from websocket_server import broadcast_kitchen_orders

            orders = await self._db.kitchen_orders.find(
                {
                    "tenant_id": tenant_id,
                    "status": {"$in": ["pending", "preparing", "ready"]},
                },
                {"_id": 0},
            ).sort("ordered_at", 1).to_list(length=200)
            await broadcast_kitchen_orders(tenant_id, orders)
        except Exception:  # noqa: BLE001 -- realtime is best effort
            logger.warning("Kitchen queue broadcast failed for tenant=%s", tenant_id, exc_info=True)

    async def _enqueue_kot(self, tenant_id: str, order: dict, lines: list[dict], actor_id: str) -> None:
        """Create one idempotent KOT print job per station for v2 orders."""
        try:
            from domains.pms.pos_extensions.pos_print_spool import enqueue_print_job, resolve_kot_printer

            by_station: dict[str, list[dict]] = {}
            for line in lines:
                by_station.setdefault(str(line.get("station") or "main"), []).append(line)
            for station, station_lines in by_station.items():
                routing = await resolve_kot_printer(tenant_id, order.get("outlet_id"), station)
                # An order can receive several append batches.  The old key only
                # used the order and station, so the spool correctly deduplicated
                # a retry *and incorrectly deduplicated every later batch*.  Line
                # IDs are immutable server-generated identifiers, making this key
                # stable for a retry while allowing a genuine append to print.
                line_fingerprint = hashlib.sha256(
                    ":".join(sorted(str(line.get("line_id") or "") for line in station_lines)).encode()
                ).hexdigest()[:16]
                await enqueue_print_job(
                    tenant_id=tenant_id,
                    kind="kitchen",
                    payload={
                        "station": station,
                        "table": order.get("table_number"),
                        "order_number": order.get("order_number"),
                        "business_date": order.get("business_date"),
                        "items": station_lines,
                    },
                    idempotency_key=f"kot-v2-{order['id']}-{station}-{line_fingerprint}",
                    printer_id=routing["printer_id"],
                    created_by=actor_id,
                    auto_dispatch=True,
                    routing_warning=None if routing.get("matched") else "Bu istasyon için yazıcı eşlemesi bulunamadı.",
                )
        except Exception:
            # The durable kitchen queue remains the source of truth and the
            # print-spool marks retries/operators' remediation separately.
            logger.warning("KOT enqueue failed for order=%s", order.get("id"), exc_info=True)

    async def _business_date(self, tenant_id: str, now: datetime) -> str:
        """Use the hotel operating day, never the server's calendar day."""
        settings_collection = getattr(self._db, "tenant_settings", None)
        if settings_collection is None:
            return now.date().isoformat()
        settings = await settings_collection.find_one({"tenant_id": tenant_id}, {"_id": 0, "business_date": 1})
        return str((settings or {}).get("business_date") or now.date().isoformat())

    async def _catalog_lines(
        self, ctx: OperationContext, outlet_id: str, items: list[dict], now: datetime
    ) -> tuple[list[dict], float, float]:
        """Build immutable order lines from the tenant's menu catalog.

        Price, tax, display name and kitchen station are financial master data.
        Requests may provide quantities and kitchen notes only; accepting their
        prices would let a browser create an arbitrary checkout total.
        """
        catalog = getattr(self._db, "pos_menu_items", None)
        if catalog is None:
            raise HTTPException(status_code=503, detail="POS menu catalog is unavailable")
        rules_collection = getattr(self._db, "pos_happy_hour_rules", None)
        rules = []
        if rules_collection is not None:
            rules = await rules_collection.find(
                {"tenant_id": ctx.tenant_id, "active": True}, {"_id": 0}
            ).to_list(200)
        from domains.pms.pos_extensions.pos_happy_hour import _apply_discount, _rule_matches

        lines: list[dict] = []
        subtotal = 0.0
        tax_total = 0.0
        for requested in items:
            item_id = str(requested.get("item_id") or "").strip()
            if not item_id:
                raise HTTPException(status_code=422, detail="Her sipariş kalemi bir menü ürünü içermelidir")
            menu = await catalog.find_one(
                {"id": item_id, "tenant_id": ctx.tenant_id, "outlet_id": outlet_id}, {"_id": 0}
            )
            if not menu:
                raise HTTPException(status_code=422, detail="Menü ürünü bu satış noktasında bulunamadı")
            if menu.get("available", menu.get("status", "active") == "active") is False:
                raise HTTPException(status_code=422, detail="Menü ürünü satışta değil")
            try:
                quantity = int(requested.get("quantity", 1))
                price = float(menu.get("unit_price", menu.get("price")))
                tax_rate = float(menu.get("tax_rate", 0.10) or 0)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="Menü ürününün fiyat veya KDV tanımı geçersiz")
            if quantity < 1 or quantity > 100 or price < 0 or not 0 <= tax_rate <= 1:
                raise HTTPException(status_code=422, detail="Sipariş miktarı, fiyatı veya KDV oranı geçersiz")
            applied_rule_id = None
            final_price = price
            pricing_item = {"item_id": item_id, "category": menu.get("category")}
            for rule in rules:
                if _rule_matches(rule, now, outlet_id, pricing_item):
                    final_price = _apply_discount(price, rule)
                    applied_rule_id = rule["id"]
                    break
            line_total = round(quantity * final_price, 2)
            subtotal += line_total
            tax_total += round(line_total * tax_rate, 2)
            lines.append(
                {
                    "line_id": str(uuid.uuid4()),
                    "item_id": item_id,
                    "item_name": menu.get("item_name") or menu.get("name") or "Ürün",
                    "quantity": quantity,
                    "unit_price": final_price,
                    "original_unit_price": price,
                    "applied_happy_hour_rule_id": applied_rule_id,
                    "total": line_total,
                    "tax_rate": tax_rate,
                    "station": menu.get("station") or requested.get("station") or "main",
                    "special_instructions": str(requested.get("special_instructions") or "")[:500] or None,
                    "status": "pending",
                }
            )
        return lines, round(subtotal, 2), round(tax_total, 2)

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
                return ServiceResult.success({
                    "message": "Order already exists (idempotent)",
                    "order_id": existing.get("id"),
                    "order": existing,
                    "idempotent": True,
                })

        if not items or len(items) == 0:
            return ServiceResult.fail("Order must have at least one item", "VALIDATION_ERROR")

        table = None
        # Validate table availability for dine-in.  The later conditional write
        # is the authority: this read only preserves the useful fast failure
        # and legacy behaviour for outlets without a table-layout record.
        if order_type == "dine_in" and table_number:
            table = await self._db.table_layouts.find_one({"table_number": table_number, "outlet_id": outlet_id, "tenant_id": ctx.tenant_id})
            if table and (table.get("status") != "available" or table.get("current_order_id")):
                return ServiceResult.fail(f"Table {table_number} is unavailable", "TABLE_UNAVAILABLE")

        now = datetime.now(UTC)
        business_date = await self._business_date(ctx.tenant_id, now)
        order_id = str(uuid.uuid4())
        order_number = f"ORD-{now.strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:4].upper()}"

        try:
            order_items, total_amount, tax_amount = await self._catalog_lines(ctx, outlet_id, items, now)
        except HTTPException as exc:
            return ServiceResult.fail(str(exc.detail), "VALIDATION_ERROR")
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
            "business_date": business_date,
            "created_at": now.isoformat(),
        }
        # Create kitchen orders per station
        stations = {}
        for item in order_items:
            st = item.get("station", "main")
            if st not in stations:
                stations[st] = []
            stations[st].append(item)

        kitchen_docs = []
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
                    "line_id": si["line_id"],
                    "quantity": si["quantity"],
                    "special_instructions": si.get("special_instructions"),
                    "station": station,
                    "status": "pending",
                    "ordered_at": now.isoformat(),
                }
                kitchen_docs.append(ko_doc)

        if table is not None:
            try:
                await self._persist_order_and_claim_table(
                    tenant_id=ctx.tenant_id,
                    outlet_id=outlet_id,
                    table_number=table_number,
                    order_doc=order_doc,
                    kitchen_docs=kitchen_docs,
                )
            except PosTableUnavailable:
                return ServiceResult.fail(f"Table {table_number} is unavailable", "TABLE_UNAVAILABLE")
        else:
            # Outlets that have not configured a table layout retain the
            # existing counter-service flow.  A configured dine-in table always
            # takes the atomic claim path above.
            await self._db.pos_orders.insert_one(order_doc)
            for kitchen_doc in kitchen_docs:
                await self._db.kitchen_orders.insert_one(kitchen_doc)

        await self._enqueue_kot(ctx.tenant_id, order_doc, order_items, ctx.actor_id)
        await self._broadcast_kitchen_queue(ctx.tenant_id)

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

    async def _persist_order_and_claim_table(
        self,
        *,
        tenant_id: str,
        outlet_id: str,
        table_number: str,
        order_doc: dict,
        kitchen_docs: list[dict],
    ) -> None:
        """Create a dine-in order only if its table is still unclaimed.

        The availability read in ``create_order`` is intentionally not trusted:
        two waiter terminals can both observe an available table.  The
        conditional update is performed before the inserts inside the same
        transaction, so losing the race leaves neither an order nor kitchen
        rows behind.
        """

        async def _commit(session) -> None:
            claim = await self._db.table_layouts.update_one(
                {
                    "tenant_id": tenant_id,
                    "outlet_id": outlet_id,
                    "table_number": table_number,
                    "status": "available",
                    "current_order_id": None,
                },
                {
                    "$set": {
                        "status": "occupied",
                        "current_order_id": order_doc["id"],
                        "opened_at": order_doc["created_at"],
                    }
                },
                session=session,
            )
            if claim.matched_count != 1:
                raise PosTableUnavailable(table_number)
            await self._db.pos_orders.insert_one(order_doc, session=session)
            if kitchen_docs:
                await self._db.kitchen_orders.insert_many(kitchen_docs, session=session)

        try:
            await with_resource_locks(
                client=self._db.client,
                db=self._db,
                tenant_id=tenant_id,
                locks_collection="pos_table_locks",
                # The conditional claim itself is the synchronization point;
                # keeping this list empty also avoids redundant lock documents.
                resources=[],
                callback=_commit,
            )
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, PosTableUnavailable):
                raise
            if not is_replica_set_unavailable(exc):
                raise
            if not standalone_fallback_allowed():
                raise HTTPException(
                    status_code=503,
                    detail="POS masa açılışı atomik garanti sağlayamıyor (Mongo replica set gerekli).",
                )
            # Explicit local-development opt-in.  The table claim remains
            # conditional, and we compensate it if a following local write
            # fails so a development failure does not strand the table.
            try:
                await _commit(None)
            except Exception:
                await self._db.table_layouts.update_one(
                    {
                        "tenant_id": tenant_id,
                        "outlet_id": outlet_id,
                        "table_number": table_number,
                        "current_order_id": order_doc["id"],
                    },
                    {"$set": {"status": "available", "current_order_id": None, "opened_at": None}},
                )
                raise

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
        guest_signature: str | None = None,
        payments: list[dict] | None = None,
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
        business_date = await self._business_date(ctx.tenant_id, now)
        grand_total = order.get("grand_total", 0)
        total_with_tip = round(grand_total + tip_amount, 2)

        payment_breakdown = None
        if payments:
            allowed_methods = {"cash", "card"}
            payment_breakdown = []
            for part in payments:
                method = str(part.get("method") or "").strip().lower()
                amount = round(float(part.get("amount") or 0), 2)
                if method not in allowed_methods or amount <= 0:
                    return ServiceResult.fail("Karma ödeme yalnızca pozitif nakit veya kart satırları içerebilir", "VALIDATION_ERROR")
                payment_breakdown.append({"method": method, "amount": amount})
            if round(sum(part["amount"] for part in payment_breakdown), 2) != total_with_tip:
                return ServiceResult.fail("Ödeme dağılımı adisyon toplamına eşit olmalıdır", "PAYMENT_MISMATCH")
            payment_method = payment_breakdown[0]["method"] if len(payment_breakdown) == 1 else "mixed"
            post_to_folio = False

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
            "transaction_date": business_date,
            "transaction_time": now.time().isoformat(),
            "amount": grand_total,
            "discount_amount": round(float(order.get("discount_amount") or 0), 2),
            "service_charge_amount": round(float(order.get("service_charge_amount") or 0), 2),
            "tax_amount": round(float(order.get("effective_tax_amount", order.get("tax_amount", 0)) or 0), 2),
            "tip_amount": tip_amount,
            "total_amount": total_with_tip,
            "payment_method": payment_method,
            "status": "completed",
            "processed_by": ctx.actor_id,
            "idempotency_key": idempotency_key,
            "order_items": order.get("order_items", []),
            # Preserve the expected mutable state so the transactional update
            # below becomes a compare-and-set rather than overwriting a void
            # or another terminal's checkout.
            "order_status_before_payment": order.get("status"),
            "payment_status_before_payment": order.get("payment_status"),
            "created_at": now.isoformat(),
        }
        if payment_breakdown:
            txn_doc["payment_breakdown"] = payment_breakdown
        if guest_signature:
            txn_doc["guest_signature"] = guest_signature
        # Task #389 — Outbox/Compensation. Resolve the target folio (if any)
        # BEFORE the write so the IC folio-posting event is enqueued ATOMICALLY
        # with the transaction record (intent durable). The async, guaranteed,
        # idempotent consumer (core.pos_folio_consumer) applies the folio charge
        # + recalculates the balance from the ledger (single strategy, never
        # $inc) and guards a non-open folio at apply time.
        folio_charge_id = None
        outbox_payload = None
        if post_to_folio and not booking_id:
            return ServiceResult.fail("Room charge requires a booking", "BOOKING_REQUIRED")
        if post_to_folio and booking_id:
            booking = await self._db.bookings.find_one(
                {
                    "id": booking_id,
                    "tenant_id": ctx.tenant_id,
                    "status": {"$in": ["checked_in", "in_house"]},
                },
                {"_id": 0, "id": 1, "status": 1},
            )
            if not booking:
                return ServiceResult.fail(
                    "Oda hesabına yalnızca giriş yapmış misafirlerin adisyonu aktarılabilir",
                    "BOOKING_NOT_IN_HOUSE",
                )
            folio = await self._db.folios.find_one({"booking_id": booking_id, "folio_type": "guest", "status": "open", "tenant_id": ctx.tenant_id})
            if not folio:
                return ServiceResult.fail("Open guest folio not found", "FOLIO_NOT_OPEN")
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
                    "tax_amount": order.get("effective_tax_amount", order.get("tax_amount", 0)),
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

        # Atomic checkout: transaction, optional IC intent and terminal order
        # state must commit together.  Persisting the sale and closing the
        # order in separate writes could leave a paid transaction attached to
        # a still-open adisyon after a process/network failure.
        # The partial unique index (tenant_id, order_id) for completed sales is
        # the final concurrency guard when two terminals close the same check.
        try:
            await self._persist_txn_and_intent(
                ctx.tenant_id,
                txn_doc,
                order_id,
                outbox_payload,
            )
        except DuplicateKeyError:
            existing_sale = await self._db.pos_transactions.find_one(
                {"tenant_id": ctx.tenant_id, "order_id": order_id, "status": "completed"}, {"_id": 0, "id": 1}
            )
            if existing_sale:
                return ServiceResult.success({
                    "message": "Order was already closed by another terminal",
                    "transaction_id": existing_sale.get("id"),
                    "idempotent": True,
                })
            raise
        except PosOrderStateChanged:
            # A void or another terminal may win between our initial read and
            # the transaction.  Re-read to return a deterministic business
            # result rather than treating it as a server error.
            current = await self._db.pos_orders.find_one(
                {"id": order_id, "tenant_id": ctx.tenant_id}, {"_id": 0, "status": 1, "payment_status": 1}
            )
            if current and (current.get("status") == "closed" or current.get("payment_status") == "paid"):
                return ServiceResult.success({"message": "Order already closed (idempotent)", "idempotent": True})
            if current and current.get("status") == "voided":
                return ServiceResult.fail("Cannot close a voided order", "ORDER_VOIDED")
            return ServiceResult.fail("Order is no longer payable", "ORDER_NOT_OPEN")

        try:
            from core.integrations.operational_gl_bridge import post_direct_pos_to_gl

            await post_direct_pos_to_gl(
                self._db,
                ctx.tenant_id,
                transaction=txn_doc,
                order=order,
                posted_to_folio=post_to_folio and folio_charge_id is not None,
                actor=ctx.actor_id,
            )
        except Exception as exc:  # noqa: BLE001 — completed payment must remain completed
            logger.exception("POS GL bridge failed for order=%s tenant=%s: %s", order_id, ctx.tenant_id, exc)
            await self._db.pos_transactions.update_one(
                {"tenant_id": ctx.tenant_id, "id": txn_id},
                {"$set": {"gl_bridge_status": "failed", "gl_bridge_error": str(exc)[:500]}},
            )

        # Release table
        if order.get("table_number") and order.get("outlet_id"):
            await self._db.table_layouts.update_one(
                {
                    "table_number": order["table_number"],
                    "outlet_id": order["outlet_id"],
                    "tenant_id": ctx.tenant_id,
                },
                {"$set": {"status": "dirty", "current_order_id": None, "opened_at": None}},
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
                "payment_breakdown": payment_breakdown,
                "folio_charge_id": folio_charge_id,
                "posted_to_folio": post_to_folio and folio_charge_id is not None,
                "folio_posting_status": "queued" if outbox_payload else None,
            }
        )

    async def get_order(self, ctx: OperationContext, order_id: str) -> ServiceResult:
        order = await self._db.pos_orders.find_one(
            {"id": order_id, "tenant_id": ctx.tenant_id},
            {"_id": 0},
        )
        if not order:
            return ServiceResult.fail("Order not found", "NOT_FOUND")
        return ServiceResult.success({"order": order})

    @audited("pos.add_order_items", "pos_order", severity=SEVERITY_INFO, capture_before=True)
    async def add_order_items(
        self,
        ctx: OperationContext,
        order_id: str,
        items: list[dict],
        idempotency_key: str | None = None,
    ) -> ServiceResult:
        if not items:
            return ServiceResult.fail("Order must have at least one item", "VALIDATION_ERROR")
        if idempotency_key:
            existing = await self._db.pos_order_item_batches.find_one(
                {"tenant_id": ctx.tenant_id, "idempotency_key": idempotency_key},
                {"_id": 0},
            )
            if existing:
                return ServiceResult.success({**existing, "idempotent": True})

        order = await self._db.pos_orders.find_one(
            {"id": order_id, "tenant_id": ctx.tenant_id},
            {"_id": 0},
        )
        if not order:
            return ServiceResult.fail("Order not found", "NOT_FOUND")
        if order.get("status") not in {"pending", "preparing", "ready"} or order.get("payment_status") == "paid":
            return ServiceResult.fail("Order is not open", "ORDER_NOT_OPEN")

        now = datetime.now(UTC)
        try:
            normalized, subtotal_delta, tax_delta = await self._catalog_lines(
                ctx, str(order.get("outlet_id") or ""), items, now
            )
        except HTTPException as exc:
            return ServiceResult.fail(str(exc.detail), "VALIDATION_ERROR")
        grand_delta = round(subtotal_delta + tax_delta, 2)
        updated = await self._db.pos_orders.update_one(
            {"id": order_id, "tenant_id": ctx.tenant_id, "payment_status": {"$ne": "paid"}},
            {
                "$push": {"order_items": {"$each": normalized}},
                "$inc": {
                    "total_amount": round(subtotal_delta, 2),
                    "tax_amount": tax_delta,
                    "grand_total": grand_delta,
                },
                "$set": {"updated_at": now.isoformat()},
            },
        )
        if getattr(updated, "matched_count", 0) == 0:
            return ServiceResult.fail("Order is not open", "ORDER_NOT_OPEN")

        for item in normalized:
            await self._db.kitchen_orders.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": ctx.tenant_id,
                    "order_id": order_id,
                    "order_number": order.get("order_number"),
                    "outlet_id": order.get("outlet_id"),
                    "table_number": order.get("table_number"),
                    "items": [item],
                    "line_id": item["line_id"],
                    "station": item.get("station"),
                    "status": "pending",
                    "priority": "normal",
                    "ordered_at": now.isoformat(),
                }
            )

        batch = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            "order_id": order_id,
            "idempotency_key": idempotency_key,
            "items_count": len(normalized),
            "amount_added": grand_delta,
            "created_at": now.isoformat(),
        }
        if idempotency_key:
            await self._db.pos_order_item_batches.insert_one(dict(batch))
        await self._enqueue_kot(ctx.tenant_id, order, normalized, ctx.actor_id)
        await self._broadcast_kitchen_queue(ctx.tenant_id)
        return ServiceResult.success(batch)

    @audited("pos.void_order_item", "pos_order", severity=SEVERITY_WARNING, require_reason=True, capture_before=True)
    async def void_order_item(
        self,
        ctx: OperationContext,
        order_id: str,
        line_index: int,
        reason: str,
    ) -> ServiceResult:
        if not getattr(ctx, "actor_is_super_admin", False) and ctx.actor_role not in ("admin", "supervisor", "super_admin", "fnb_manager"):
            return ServiceResult.fail("Kalem iptali için yönetici yetkisi gerekir", "FORBIDDEN")
        if not reason.strip():
            return ServiceResult.fail("İptal nedeni gereklidir", "VALIDATION_ERROR")
        order = await self._db.pos_orders.find_one({"id": order_id, "tenant_id": ctx.tenant_id}, {"_id": 0})
        if not order:
            return ServiceResult.fail("Order not found", "NOT_FOUND")
        if order.get("status") not in {"pending", "preparing", "ready"} or order.get("payment_status") == "paid":
            return ServiceResult.fail("Order is not open", "ORDER_NOT_OPEN")
        items = list(order.get("order_items") or [])
        if line_index < 0 or line_index >= len(items):
            return ServiceResult.fail("Adisyon kalemi bulunamadı", "NOT_FOUND")
        removed = dict(items.pop(line_index))
        if not items:
            return ServiceResult.fail("Son kalem buradan silinemez; adisyonu iptal edin", "VALIDATION_ERROR")
        subtotal = round(sum(float(item.get("total") or 0) for item in items), 2)
        tax = round(sum(float(item.get("total") or 0) * float(item.get("tax_rate") or 0) for item in items), 2)
        grand_total = round(subtotal + tax, 2)
        now = datetime.now(UTC).isoformat()
        await self._db.pos_orders.update_one(
            {"id": order_id, "tenant_id": ctx.tenant_id, "payment_status": {"$ne": "paid"}},
            {"$set": {"order_items": items, "total_amount": subtotal, "tax_amount": tax, "grand_total": grand_total, "updated_at": now}},
        )
        kitchen_query = {"tenant_id": ctx.tenant_id, "order_id": order_id, "status": {"$nin": ["served", "cancelled"]}}
        if removed.get("line_id"):
            kitchen_query["$or"] = [{"line_id": removed["line_id"]}, {"items.line_id": removed["line_id"]}]
        else:
            kitchen_query["item_name"] = removed.get("item_name")
        await self._db.kitchen_orders.update_many(
            kitchen_query,
            {"$set": {"status": "cancelled", "cancelled_at": now, "cancelled_by": ctx.actor_id, "cancel_reason": reason.strip()}},
        )
        await self._db.pos_order_item_voids.insert_one({
            "id": str(uuid.uuid4()), "tenant_id": ctx.tenant_id, "order_id": order_id,
            "line": removed, "reason": reason.strip(), "voided_at": now, "voided_by": ctx.actor_id,
        })
        await self._broadcast_kitchen_queue(ctx.tenant_id)
        return ServiceResult.success({"order_id": order_id, "removed_item": removed, "grand_total": grand_total})

    @audited("pos.refund_order", "pos_order", severity=SEVERITY_CRITICAL, require_reason=True, capture_before=True)
    async def refund_order(
        self,
        ctx: OperationContext,
        order_id: str,
        amount: float | None,
        reason: str,
        idempotency_key: str | None = None,
    ) -> ServiceResult:
        if not getattr(ctx, "actor_is_super_admin", False) and ctx.actor_role not in ("admin", "supervisor", "super_admin", "fnb_manager"):
            return ServiceResult.fail("İade için yönetici yetkisi gerekir", "FORBIDDEN")
        if not reason.strip():
            return ServiceResult.fail("İade nedeni gereklidir", "VALIDATION_ERROR")
        if idempotency_key:
            prior = await self._db.pos_transactions.find_one({"tenant_id": ctx.tenant_id, "idempotency_key": idempotency_key}, {"_id": 0})
            if prior:
                return ServiceResult.success({"refund_id": prior.get("id"), "idempotent": True})
        order = await self._db.pos_orders.find_one({"id": order_id, "tenant_id": ctx.tenant_id}, {"_id": 0})
        if not order:
            return ServiceResult.fail("Order not found", "NOT_FOUND")
        if order.get("status") != "closed" or order.get("payment_status") not in {"paid", "partially_refunded"}:
            return ServiceResult.fail("Yalnızca kapatılmış bir adisyon iade edilebilir", "ORDER_NOT_CLOSED")
        sale = await self._db.pos_transactions.find_one({"tenant_id": ctx.tenant_id, "order_id": order_id, "status": "completed"}, {"_id": 0})
        if not sale:
            return ServiceResult.fail("Satış işlemi bulunamadı", "NOT_FOUND")
        paid = round(float(sale.get("total_amount") or sale.get("amount") or 0), 2)
        refunded = round(float(sale.get("refunded_amount") or 0), 2)
        refund_amount = round(float(amount if amount is not None else paid - refunded), 2)
        if refund_amount <= 0 or refund_amount > round(paid - refunded, 2):
            return ServiceResult.fail("İade tutarı kalan iade edilebilir tutarı aşamaz", "REFUND_LIMIT")
        if sale.get("payment_method") == "room_charge" and refund_amount != round(paid - refunded, 2):
            return ServiceResult.fail("Oda hesabı işlemleri yalnızca tamamen iade edilebilir", "REFUND_LIMIT")
        now = datetime.now(UTC)
        business_date = await self._business_date(ctx.tenant_id, now)
        refund_id = str(uuid.uuid4())
        refund_doc = {
            "id": refund_id, "tenant_id": ctx.tenant_id, "order_id": order_id,
            "original_transaction_id": sale.get("id"), "outlet_id": order.get("outlet_id"),
            "transaction_date": business_date, "transaction_time": now.time().isoformat(),
            "amount": -refund_amount, "total_amount": -refund_amount, "payment_method": sale.get("payment_method"),
            "payment_type": "refund", "status": "refunded", "reason": reason.strip(),
            "processed_by": ctx.actor_id, "idempotency_key": idempotency_key, "created_at": now.isoformat(),
        }
        updated_sale = await self._persist_refund_and_state(
            tenant_id=ctx.tenant_id,
            order_id=order_id,
            sale_id=sale["id"],
            paid=paid,
            refund_amount=refund_amount,
            refund_doc=refund_doc,
        )
        if updated_sale is None:
            # Another manager completed (or consumed) the remaining refundable
            # balance after our initial read.  No refund document is inserted.
            return ServiceResult.fail("İade tutarı kalan iade edilebilir tutarı aşıyor", "REFUND_LIMIT")
        new_refunded = round(float(updated_sale.get("refunded_amount") or 0), 2)
        full_refund = new_refunded >= paid
        if sale.get("payment_method") == "room_charge" and full_refund:
            folio = await self._db.folios.find_one({"booking_id": order.get("booking_id"), "folio_type": "guest", "tenant_id": ctx.tenant_id}, {"_id": 0, "id": 1})
            await self._publish_charge_reversal(ctx.tenant_id, order_id, folio.get("id") if folio else None, reason.strip())
        elif sale.get("payment_method") != "room_charge":
            try:
                from core.integrations.operational_gl_bridge import post_direct_pos_refund_to_gl

                await post_direct_pos_refund_to_gl(
                    self._db, ctx.tenant_id, refund=refund_doc,
                    original_transaction=sale, order=order, actor=ctx.actor_id,
                )
            except Exception as exc:  # noqa: BLE001 — refund record remains authoritative
                logger.exception("POS refund GL bridge failed for order=%s tenant=%s", order_id, ctx.tenant_id)
                await self._db.pos_transactions.update_one(
                    {"tenant_id": ctx.tenant_id, "id": refund_id},
                    {"$set": {"gl_bridge_status": "failed", "gl_bridge_error": str(exc)[:500]}},
                )
        if full_refund:
            try:
                await self._restore_recipe_stock(ctx, order_id)
            except Exception:
                logger.exception("Recipe stock restore failed for refunded order %s", order_id)
        return ServiceResult.success({"order_id": order_id, "refund_id": refund_id, "refund_amount": refund_amount, "full_refund": full_refund})

    @audited("pos.transfer_order_table", "pos_order", severity=SEVERITY_INFO, capture_before=True)
    async def transfer_order_table(
        self,
        ctx: OperationContext,
        order_id: str,
        to_table_number: str,
    ) -> ServiceResult:
        order = await self._db.pos_orders.find_one(
            {"id": order_id, "tenant_id": ctx.tenant_id},
            {"_id": 0},
        )
        if not order:
            return ServiceResult.fail("Order not found", "NOT_FOUND")
        if order.get("status") not in {"pending", "preparing", "ready"} or order.get("payment_status") == "paid":
            return ServiceResult.fail("Order is not open", "ORDER_NOT_OPEN")
        outlet_id = order.get("outlet_id")
        source_number = str(order.get("table_number") or "")
        target_number = str(to_table_number or "").strip()
        if not outlet_id or not target_number:
            return ServiceResult.fail("Target table is required", "VALIDATION_ERROR")
        target = await self._db.table_layouts.find_one(
            {"tenant_id": ctx.tenant_id, "outlet_id": outlet_id, "table_number": target_number},
            {"_id": 0},
        )
        if not target:
            return ServiceResult.fail("Target table not found", "NOT_FOUND")
        if (
            target.get("status") != "available"
            or target.get("current_order_id")
            or target.get("current_transaction_id")
        ):
            return ServiceResult.fail("Target table is unavailable", "TABLE_UNAVAILABLE")

        now = datetime.now(UTC).isoformat()
        claimed = await self._db.table_layouts.update_one(
            {
                "tenant_id": ctx.tenant_id,
                "outlet_id": outlet_id,
                "table_number": target_number,
                "status": "available",
                "current_order_id": {"$in": [None]},
                "current_transaction_id": {"$in": [None]},
            },
            {"$set": {"status": "occupied", "current_order_id": order_id, "opened_at": order.get("created_at") or now}},
        )
        if getattr(claimed, "matched_count", 0) == 0:
            return ServiceResult.fail("Target table is unavailable", "TABLE_UNAVAILABLE")
        await self._db.pos_orders.update_one(
            {"id": order_id, "tenant_id": ctx.tenant_id},
            {"$set": {"table_number": target_number, "updated_at": now}},
        )
        await self._db.kitchen_orders.update_many(
            {"order_id": order_id, "tenant_id": ctx.tenant_id, "status": {"$nin": ["served", "cancelled"]}},
            {"$set": {"table_number": target_number, "updated_at": now}},
        )
        if source_number:
            await self._db.table_layouts.update_one(
                {"tenant_id": ctx.tenant_id, "outlet_id": outlet_id, "table_number": source_number, "current_order_id": order_id},
                {"$set": {"status": "available", "current_order_id": None, "opened_at": None}},
            )
        await self._broadcast_kitchen_queue(ctx.tenant_id)
        return ServiceResult.success(
            {"order_id": order_id, "from_table": source_number, "to_table": target_number}
        )

    @audited("pos.adjust_order", "pos_order", severity=SEVERITY_WARNING, require_reason=True, capture_before=True)
    async def apply_order_adjustment(
        self,
        ctx: OperationContext,
        order_id: str,
        adjustment_type: str,
        calculation: str,
        value: float,
        reason: str,
    ) -> ServiceResult:
        if not getattr(ctx, "actor_is_super_admin", False) and ctx.actor_role not in ("admin", "supervisor", "super_admin", "fnb_manager"):
            return ServiceResult.fail("İndirim ve servis bedeli için yönetici yetkisi gerekir", "FORBIDDEN")
        order = await self._db.pos_orders.find_one({"tenant_id": ctx.tenant_id, "id": order_id}, {"_id": 0})
        if not order:
            return ServiceResult.fail("Order not found", "NOT_FOUND")
        if order.get("status") not in {"pending", "preparing", "ready"} or order.get("payment_status") == "paid":
            return ServiceResult.fail("Order is not open", "ORDER_NOT_OPEN")
        base_total = round(float(order.get("pre_adjustment_total") or 0), 2)
        if base_total <= 0:
            base_total = round(float(order.get("total_amount") or 0) + float(order.get("tax_amount") or 0), 2)
        amount = round(base_total * float(value) / 100, 2) if calculation == "percentage" else round(float(value), 2)
        if amount <= 0:
            return ServiceResult.fail("Adjustment must be positive", "VALIDATION_ERROR")
        discount = amount if adjustment_type == "discount" else round(float(order.get("discount_amount") or 0), 2)
        service_charge = amount if adjustment_type == "service_charge" else round(float(order.get("service_charge_amount") or 0), 2)
        if discount > base_total:
            return ServiceResult.fail("İndirim adisyon toplamını aşamaz", "VALIDATION_ERROR")
        grand_total = round(base_total - discount + service_charge, 2)
        original_tax = round(float(order.get("original_tax_amount", order.get("tax_amount", 0)) or 0), 2)
        effective_tax = round(original_tax * max(base_total - discount, 0) / base_total, 2) if base_total else 0
        now = datetime.now(UTC).isoformat()
        event = {
            "id": str(uuid.uuid4()), "type": adjustment_type, "calculation": calculation,
            "value": float(value), "amount": amount, "reason": reason.strip(),
            "created_at": now, "created_by": ctx.actor_id,
        }
        await self._db.pos_orders.update_one(
            {"tenant_id": ctx.tenant_id, "id": order_id, "payment_status": {"$ne": "paid"}},
            {"$set": {"pre_adjustment_total": base_total, "original_tax_amount": original_tax, "effective_tax_amount": effective_tax, "discount_amount": discount, "service_charge_amount": service_charge, "grand_total": grand_total, "updated_at": now}, "$push": {"adjustments": event}},
        )
        return ServiceResult.success({"order_id": order_id, "grand_total": grand_total, "discount_amount": discount, "service_charge_amount": service_charge, "adjustment": event})

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
        """Write the sale, optional IC intent and closed order in ONE Mongo txn.

        Either all records land or none do — a completed sale can never survive
        with its order still payable.  The order update is conditional so a
        concurrent void/checkout aborts the transaction instead of overwriting
        a terminal state.
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
            close_result = await self._db.pos_orders.update_one(
                {
                    "id": order_id,
                    "tenant_id": tenant_id,
                    # Compare-and-set keeps a concurrent void or checkout from
                    # being overwritten between the transaction read and write.
                    "status": txn_doc.get("order_status_before_payment"),
                    "payment_status": txn_doc.get("payment_status_before_payment"),
                },
                {
                    "$set": {
                        "status": "closed",
                        "payment_status": "paid",
                        "payment_method": txn_doc["payment_method"],
                        "closed_at": txn_doc["created_at"],
                        "closed_by": txn_doc["processed_by"],
                        "guest_signature": txn_doc.get("guest_signature"),
                        "payment_breakdown": txn_doc.get("payment_breakdown"),
                    }
                },
                session=session,
            )
            if close_result.matched_count != 1:
                raise PosOrderStateChanged(order_id)

        try:
            await with_resource_locks(
                client=self._db.client,
                db=self._db,
                tenant_id=tenant_id,
                locks_collection="folio_locks",
                # The conditional update of the POS order is the resource
                # serialization point. The transaction retry handles a write
                # conflict with a concurrent void or checkout.
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

    async def _persist_refund_and_state(
        self,
        *,
        tenant_id: str,
        order_id: str,
        sale_id: str,
        paid: float,
        refund_amount: float,
        refund_doc: dict,
    ) -> dict | None:
        """Atomically reserve refundable balance and persist its refund.

        The refund ceiling must be checked at write time, not against a stale
        ``refunded_amount`` read.  The transaction also ensures that the refund
        record, source sale and order state move together.
        """

        async def _commit(session):
            updated_sale = await self._db.pos_transactions.find_one_and_update(
                {
                    "tenant_id": tenant_id,
                    "id": sale_id,
                    "status": "completed",
                    "$expr": {
                        "$lte": [
                            {"$add": [{"$ifNull": ["$refunded_amount", 0]}, refund_amount]},
                            paid,
                        ]
                    },
                },
                [
                    {"$set": {"refunded_amount": {"$add": [{"$ifNull": ["$refunded_amount", 0]}, refund_amount]}}},
                    {
                        "$set": {
                            "refund_status": {
                                "$cond": [{"$gte": ["$refunded_amount", paid]}, "full", "partial"]
                            }
                        }
                    },
                ],
                return_document=True,
                session=session,
            )
            if not updated_sale:
                return None
            new_refunded = round(float(updated_sale.get("refunded_amount") or 0), 2)
            await self._db.pos_transactions.insert_one(refund_doc, session=session)
            await self._db.pos_orders.update_one(
                {"tenant_id": tenant_id, "id": order_id},
                {
                    "$set": {
                        "payment_status": "refunded" if new_refunded >= paid else "partially_refunded",
                        "refunded_amount": new_refunded,
                    }
                },
                session=session,
            )
            return updated_sale

        try:
            return await with_resource_locks(
                client=self._db.client,
                db=self._db,
                tenant_id=tenant_id,
                locks_collection="pos_refund_locks",
                resources=[("sale", sale_id)],
                callback=_commit,
            )
        except Exception as exc:  # noqa: BLE001
            if not is_replica_set_unavailable(exc):
                raise
            if not standalone_fallback_allowed():
                raise HTTPException(
                    status_code=503,
                    detail="POS iadesi atomik garanti sağlayamıyor (Mongo replica set gerekli).",
                )
            # Explicit local-development opt-in only.  The conditional source
            # update still protects the financial ceiling, but a standalone
            # Mongo cannot offer all-or-nothing writes across three documents.
            return await _commit(None)

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
                {"$set": {"status": "available", "current_order_id": None, "opened_at": None}},
            )

        await self._broadcast_kitchen_queue(ctx.tenant_id)

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
