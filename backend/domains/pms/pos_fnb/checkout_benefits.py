"""Server-priced POS checkout benefits. All redemption writes share the sale session."""
import hashlib
import json
import math
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException

from domains.pms.pos_extensions.pos_coupons import _check_validity, _compute_discount


def money(value):
    try:
        result = Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        raise HTTPException(422, "Tutar geçersiz.") from None
    if not result.is_finite() or result < 0:
        raise HTTPException(422, "Tutar geçersiz.")
    return float(result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


async def quote_checkout(db, tenant_id, order, options, session=None):
    """No writes: quote the current order and tenant policies."""
    kw = {"session": session} if session is not None else {}
    settings = await db.hotel_settings.find_one({"tenant_id": tenant_id}, {"_id": 0}, **kw) or {}
    base = str(settings.get("currency") or "TRY").upper()
    gross = money(order.get("grand_total"))
    coupon_code = str(options.get("coupon_code") or "").strip().upper()
    guest_id = options.get("guest_id")
    points = int(options.get("loyalty_points") or 0)
    if points < 0:
        raise HTTPException(422, "Puan negatif olamaz.")
    coupon, coupon_discount = None, 0.0
    if coupon_code:
        coupon = await db.pos_coupons.find_one({"tenant_id": tenant_id, "code": coupon_code}, {"_id": 0}, **kw)
        if not coupon:
            raise HTTPException(409, "Kupon bulunamadı.")
        valid, reason = _check_validity(coupon, gross, datetime.now(UTC))
        if not valid:
            raise HTTPException(409, reason)
        coupon_discount = money(_compute_discount(coupon, gross))
    loyalty_discount, earned = 0.0, 0
    policy = {}
    if guest_id:
        guest = await db.guests.find_one({"tenant_id": tenant_id, "id": guest_id}, {"id": 1}, **kw)
        if not guest:
            raise HTTPException(404, "Misafir bu tesiste bulunamadı.")
        policy = await db.loyalty_pos_settings.find_one({"tenant_id": tenant_id}, {"_id": 0}, **kw) or {
            "active": True, "earn_points_per_unit": 1, "redeem_value_per_point": .1, "min_redeem_points": 10,
        }
        if not policy.get("active", True):
            raise HTTPException(409, "Sadakat programı etkin değil.")
        if points:
            if points < int(policy.get("min_redeem_points", 10)):
                raise HTTPException(409, "Asgari puan kullanımına ulaşılmadı.")
            account = await db.loyalty_pos_accounts.find_one({"tenant_id": tenant_id, "guest_id": guest_id}, {"_id": 0}, **kw) or {}
            if points > int(account.get("balance", 0)):
                raise HTTPException(409, "Puan bakiyesi yetersiz.")
            loyalty_discount = money(Decimal(points) * Decimal(str(policy.get("redeem_value_per_point", .1))))
    elif points:
        raise HTTPException(422, "Puan kullanımı için misafir seçin.")
    if loyalty_discount > money(gross - coupon_discount):
        raise HTTPException(409, "Puan indirimi kalan adisyon tutarını aşamaz.")
    net = money(gross - coupon_discount - loyalty_discount)
    tip = money(options.get("tip_amount"))
    if guest_id:
        rate = Decimal(str(policy.get("earn_points_per_unit", 1)))
        if not rate.is_finite() or rate < 0:
            raise HTTPException(409, "Sadakat kazanım oranı geçersiz.")
        earned = math.floor(Decimal(str(net)) * rate)
    code = str(options.get("currency_code") or base).upper()
    rate_doc, rate = None, 1.0
    if code != base:
        rate_doc = await db.pos_exchange_rates.find_one(
            {"tenant_id": tenant_id, "currency_code": code, "base_currency": base},
            {"_id": 0}, sort=[("valid_at", -1)], **kw,
        )
        if not rate_doc:
            raise HTTPException(409, "Bu döviz için geçerli kur tanımlanmamış.")
        rate = float(rate_doc["rate_to_base"])
        if not math.isfinite(rate) or rate <= 0:
            raise HTTPException(409, "Döviz kuru geçersiz.")
    payable = money(net + tip)
    quote = {
        "order_id": order["id"], "base_currency": base, "currency_code": code,
        "gross": gross, "coupon_code": coupon_code or None, "coupon_discount": coupon_discount,
        "guest_id": guest_id, "loyalty_points": points, "loyalty_discount": loyalty_discount,
        "points_earned": earned, "net": net, "tip_amount": tip, "payable": payable,
        "rate_used": rate, "rate_id": (rate_doc or {}).get("id"),
        "amount_foreign": money(Decimal(str(payable)) / Decimal(str(rate))),
        "tax_amount": money(Decimal(str(order.get("effective_tax_amount", order.get("tax_amount", 0)) or 0)) * Decimal(str(net)) / Decimal(str(gross))) if gross else 0,
    }
    # Explicit residual: never hide foreign minor-unit rounding in sales/tax.
    quote["fx_rounding_base"] = float(
        (Decimal(str(quote["amount_foreign"])) * Decimal(str(rate)) - Decimal(str(payable)))
        .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )
    quote["quote_id"] = fingerprint({
        "quote": quote, "lines": order.get("order_items"), "adjustments": order.get("adjustments"),
        "coupon": coupon, "policy": policy,
    })
    return quote


async def commit_benefits(db, tenant_id, order, txn, session):
    quote = txn.get("checkout_quote")
    if not quote:
        return
    fresh = await quote_checkout(db, tenant_id, order, quote, session=session)
    if fresh["quote_id"] != quote["quote_id"]:
        raise HTTPException(409, "Fiyat, kur veya avantajlar değişti. Ödeme özetini yeniden onaylayın.")
    if quote["coupon_code"]:
        changed = await db.pos_coupons.update_one(
            {"tenant_id": tenant_id, "code": quote["coupon_code"], "active": {"$ne": False},
             "$expr": {"$lt": [{"$ifNull": ["$used_count", 0]}, {"$ifNull": ["$max_uses", 1]}]}},
            {"$inc": {"used_count": 1}}, session=session,
        )
        if changed.modified_count != 1:
            raise HTTPException(409, "Kupon kullanım limiti doldu.")
        await db.pos_coupon_redemptions.insert_one({
            "id": str(uuid.uuid4()), "tenant_id": tenant_id, "order_id": order["id"],
            "transaction_id": txn["id"], "code": quote["coupon_code"],
            "discount_amount": quote["coupon_discount"], "created_at": txn["created_at"],
            "idempotency_key": "checkout:" + order["id"],
        }, session=session)
    guest_id = quote["guest_id"]
    if guest_id:
        used, earned = quote["loyalty_points"], quote["points_earned"]
        query = {"tenant_id": tenant_id, "guest_id": guest_id}
        if used:
            query["balance"] = {"$gte": used}
        changed = await db.loyalty_pos_accounts.update_one(query, {
            "$inc": {"balance": earned - used, "lifetime_earned": earned, "lifetime_redeemed": used},
            "$set": {"updated_at": txn["created_at"]},
        }, upsert=not used, session=session)
        if used and changed.matched_count != 1:
            raise HTTPException(409, "Puan bakiyesi başka işlemde değişti.")
        await db.loyalty_pos_ledger.insert_one({
            "id": str(uuid.uuid4()), "tenant_id": tenant_id, "guest_id": guest_id,
            "order_id": order["id"], "transaction_id": txn["id"], "kind": "checkout",
            "points": earned - used, "points_earned": earned, "points_redeemed": used,
            "discount_value": quote["loyalty_discount"], "created_at": txn["created_at"],
            "idempotency_key": "checkout:" + order["id"],
        }, session=session)


async def reverse_benefits(db, tenant_id, sale, refund, paid, cumulative, session):
    """Reverse points cumulatively, including rounding residue on full refund.

    A previously spent reward may leave a negative balance (debt); it must not
    block a monetary refund. Coupon usage remains consumed to prevent reuse.
    """
    quote = sale.get("checkout_quote") or {}
    guest_id = quote.get("guest_id")
    if not guest_id or not paid:
        return
    earned, redeemed = quote["points_earned"], quote["loyalty_points"]
    ratio = min(Decimal(1), Decimal(str(cumulative)) / Decimal(str(paid)))
    earn_target, redeem_target = int(Decimal(earned) * ratio), int(Decimal(redeemed) * ratio)
    earn_delta = earn_target - int(sale.get("loyalty_earned_reversed", 0))
    redeem_delta = redeem_target - int(sale.get("loyalty_redeemed_restored", 0))
    await db.loyalty_pos_accounts.update_one(
        {"tenant_id": tenant_id, "guest_id": guest_id},
        {"$inc": {"balance": redeem_delta - earn_delta, "lifetime_earned": -earn_delta,
                  "lifetime_redeemed": -redeem_delta}}, session=session,
    )
    await db.pos_transactions.update_one(
        {"tenant_id": tenant_id, "id": sale["id"]},
        {"$set": {"loyalty_earned_reversed": earn_target, "loyalty_redeemed_restored": redeem_target}},
        session=session,
    )
    await db.loyalty_pos_ledger.insert_one({
        "id": str(uuid.uuid4()), "tenant_id": tenant_id, "guest_id": guest_id,
        "order_id": sale["order_id"], "transaction_id": refund["id"], "kind": "refund",
        "points": redeem_delta - earn_delta, "created_at": refund["created_at"],
    }, session=session)
