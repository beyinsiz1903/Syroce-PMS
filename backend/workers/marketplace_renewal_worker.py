"""Idempotent marketplace renewal worker with retry/dunning state."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)
DEFAULT_INTERVAL_SECONDS = int(os.environ.get("MARKETPLACE_RENEWAL_INTERVAL_SECONDS", "3600"))
_started = False


async def process_due_renewals(db, *, now: datetime | None = None, limit: int = 100) -> dict:
    from core.iyzico import charge_saved_card
    from core.marketplace_contracts import calculate_price
    from routers.marketplace import _activate_subscription

    now = now or datetime.now(UTC)
    cursor = db.tenant_subscriptions.find({
        "status": {"$in": ["active", "past_due"]}, "auto_renew": True,
        "end_date": {"$lte": (now + timedelta(hours=12)).isoformat()},
        "trial": {"$ne": True},
    }, {"_id": 0}).limit(limit)
    rows = [row async for row in cursor]
    result = {"processed": 0, "renewed": 0, "failed": 0}
    for sub in rows:
        result["processed"] += 1
        attempt_key = f"{sub['id']}:{sub.get('end_date')}"
        existing = await db.marketplace_renewal_attempts.find_one({"attempt_key": attempt_key, "status": "succeeded"})
        if existing:
            continue
        product = await db.marketplace_products.find_one({"key": sub["product_key"], "active": True}, {"_id": 0})
        mandate = await db.marketplace_payment_methods.find_one({"tenant_id": sub["tenant_id"], "is_default": True, "status": "active"}, {"_id": 0})
        attempt = {"id": str(uuid.uuid4()), "attempt_key": attempt_key, "tenant_id": sub["tenant_id"], "subscription_id": sub["id"], "product_key": sub["product_key"], "created_at": now.isoformat()}
        if not product or not mandate or not mandate.get("card_token") or not mandate.get("card_user_key"):
            reason = "payment_method_required" if product else "product_unavailable"
            await db.marketplace_renewal_attempts.update_one({"attempt_key": attempt_key}, {"$set": {**attempt, "status": "failed", "reason": reason}}, upsert=True)
            await db.tenant_subscriptions.update_one({"id": sub["id"]}, {"$set": {"status": "past_due", "renewal_status": "payment_action_required", "grace_until": (now + timedelta(days=7)).isoformat(), "updated_at": now.isoformat()}})
            result["failed"] += 1
            continue
        quote = calculate_price(product, sub.get("quantity", 1))
        order_id = str(uuid.uuid4())
        payload = {
            "locale": "tr", "conversationId": order_id, "price": str(quote["total_try"]), "paidPrice": str(quote["total_try"]),
            "currency": "TRY", "installment": "1", "basketId": order_id, "paymentChannel": "WEB", "paymentGroup": "SUBSCRIPTION",
            "paymentCard": {"cardUserKey": mandate["card_user_key"], "cardToken": mandate["card_token"]},
            "buyer": mandate["buyer"], "shippingAddress": mandate["address"], "billingAddress": mandate["address"],
            "basketItems": [{"id": product["key"], "name": product["name"][:80], "category1": "Dijital", "itemType": "VIRTUAL", "price": str(quote["total_try"])}],
        }
        response = charge_saved_card(payload)
        if response.get("status") == "success" and response.get("paymentStatus") == "SUCCESS":
            order = {"order_id": order_id, "tenant_id": sub["tenant_id"], "product_key": product["key"], "duration_days": product.get("duration_days", 30), "billing_type": "subscription", "quantity": sub.get("quantity", 1), **quote}
            await db.marketplace_orders.insert_one({**order, "status": "completed", "kind": "renewal", "iyzico_payment_id": response.get("paymentId"), "created_at": now.isoformat(), "completed_at": now.isoformat()})
            await _activate_subscription(order)
            await db.marketplace_renewal_attempts.update_one({"attempt_key": attempt_key}, {"$set": {**attempt, "status": "succeeded", "order_id": order_id}}, upsert=True)
            result["renewed"] += 1
        else:
            await db.marketplace_renewal_attempts.update_one({"attempt_key": attempt_key}, {"$set": {**attempt, "status": "failed", "reason": response.get("errorMessage") or "payment_failed"}}, upsert=True)
            await db.tenant_subscriptions.update_one({"id": sub["id"]}, {"$set": {"status": "past_due", "renewal_status": "retrying", "next_retry_at": (now + timedelta(days=1)).isoformat(), "grace_until": (now + timedelta(days=7)).isoformat(), "updated_at": now.isoformat()}})
            result["failed"] += 1
    return result


async def _loop(interval_seconds: int) -> None:
    from core.database import _raw_db
    await asyncio.sleep(30)
    while True:
        try:
            outcome = await process_due_renewals(_raw_db)
            if outcome["processed"]:
                logger.info("marketplace renewals processed=%s renewed=%s failed=%s", outcome["processed"], outcome["renewed"], outcome["failed"])
        except Exception as exc:
            logger.exception("marketplace renewal tick failed: %s", exc)
        await asyncio.sleep(interval_seconds)


def start() -> bool:
    global _started
    if _started:
        return True
    if DEFAULT_INTERVAL_SECONDS <= 0:
        return False
    asyncio.create_task(_loop(DEFAULT_INTERVAL_SECONDS), name="marketplace-renewal-worker")
    _started = True
    return True
