"""Business logic for the supplies marketplace."""

from __future__ import annotations

import logging
import secrets
import uuid

from fastapi import HTTPException

from .models import OrderCreate, OrderLineOut, _utc_now_iso
from .repository import orders_col, products_col, vendors_col

logger = logging.getLogger(__name__)

DEFAULT_COMMISSION_PCT = 8.0  # Syroce komisyon %


def public_vendor(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "email": doc["email"],
        "company_name": doc["company_name"],
        "contact_name": doc.get("contact_name", ""),
        "phone": doc.get("phone", ""),
        "tax_no": doc.get("tax_no", ""),
        "tax_office": doc.get("tax_office"),
        "iban": doc.get("iban"),
        "address": doc.get("address"),
        "city": doc.get("city"),
        "status": doc.get("status", "pending"),
        "commission_pct": float(doc.get("commission_pct", DEFAULT_COMMISSION_PCT)),
        "created_at": doc.get("created_at", ""),
    }


def public_product(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "vendor_id": doc["vendor_id"],
        "vendor_name": doc.get("vendor_name", ""),
        "name": doc["name"],
        "description": doc.get("description"),
        "category": doc["category"],
        "images": doc.get("images", []),
        "price_try": float(doc.get("price_try", 0)),
        "unit": doc.get("unit", "adet"),
        "pack_size": int(doc.get("pack_size", 1)),
        "moq": int(doc.get("moq", 1)),
        "stock": int(doc.get("stock", 0)),
        "is_active": bool(doc.get("is_active", True)),
        "price_tiers": list(doc.get("price_tiers", []) or []),
        "promotions": list(doc.get("promotions", []) or []),
        "lead_time_days": int(doc.get("lead_time_days", 0) or 0),
        "payment_terms_days": int(doc.get("payment_terms_days", 0) or 0),
        "created_at": doc.get("created_at", ""),
        "updated_at": doc.get("updated_at", ""),
    }


def _promotion_active(promo: dict) -> bool:
    """Promo süre kontrolü.

    - `valid_until` yoksa daima aktif.
    - YYYY-MM-DD formatı verilirse o günün sonu (23:59:59 UTC) bitiş kabul edilir.
    - Tam ISO datetime de kabul edilir.
    - Geçersiz/parse edilemeyen değer → promosyon DEVRE DIŞI (güvenli taraf).
    """
    valid_until = promo.get("valid_until")
    if not valid_until:
        return True
    from datetime import UTC, datetime, time

    raw = str(valid_until).strip()
    try:
        if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
            d = datetime.strptime(raw, "%Y-%m-%d").date()
            dt = datetime.combine(d, time(23, 59, 59), tzinfo=UTC)
        else:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        # Geçersiz tarih → promosyonu uygulama (yanlış indirimi önle)
        logger.warning("supplies_market: invalid promotion valid_until=%r — discarded", raw)
        return False
    return dt >= datetime.now(UTC)


def resolve_effective_price(product: dict, qty: int) -> dict:
    """Verilen miktar için en avantajlı tier + promosyon kombinasyonunu döner.

    Returns:
        dict with keys: unit_price, base_price, applied_tier, applied_promotion,
        savings_pct.
    """
    base_price = float(product.get("price_try", 0))
    qty = max(1, int(qty or 1))

    # En yüksek min_qty <= qty olan tier (en derin indirim)
    tiers = sorted(
        [t for t in (product.get("price_tiers") or []) if int(t.get("min_qty", 0)) <= qty],
        key=lambda t: int(t.get("min_qty", 0)),
        reverse=True,
    )
    applied_tier = tiers[0] if tiers else None
    tier_price = float(applied_tier["price_try"]) if applied_tier else base_price

    # En iyi promosyon: aktif + min_qty karşılanır + en yüksek discount_pct
    candidate_promos = [p for p in (product.get("promotions") or []) if (p.get("min_qty") is None or qty >= int(p.get("min_qty") or 0)) and _promotion_active(p)]
    applied_promo = None
    if candidate_promos:
        applied_promo = max(candidate_promos, key=lambda p: float(p.get("discount_pct", 0)))

    final = tier_price
    if applied_promo:
        final = round(final * (1 - float(applied_promo["discount_pct"]) / 100.0), 2)

    savings_pct = 0.0
    if base_price > 0 and final < base_price:
        savings_pct = round((1 - final / base_price) * 100.0, 2)

    return {
        "unit_price": round(final, 2),
        "base_price": base_price,
        "applied_tier": applied_tier,
        "applied_promotion": applied_promo,
        "savings_pct": savings_pct,
    }


def _new_order_no() -> str:
    return f"SM-{secrets.token_hex(4).upper()}"


async def place_order(
    *,
    payload: OrderCreate,
    hotel_tenant_id: str,
    hotel_name: str,
) -> dict:
    """Create an order. All lines must belong to a single approved vendor.

    For MVP we keep one vendor per order — if the cart has multiple vendors
    the frontend is expected to split them client-side.
    """
    if not payload.lines:
        raise HTTPException(400, "Order has no lines")

    # Fetch products
    product_ids = [line.product_id for line in payload.lines]
    products = await products_col.find({"id": {"$in": product_ids}}).to_list(length=len(product_ids))
    products_by_id = {p["id"]: p for p in products}

    if len(products_by_id) != len(set(product_ids)):
        raise HTTPException(400, "One or more products not found")

    vendor_ids = {p["vendor_id"] for p in products}
    if len(vendor_ids) > 1:
        raise HTTPException(400, "Order spans multiple vendors; split into separate orders")

    vendor_id = next(iter(vendor_ids))
    vendor = await vendors_col.find_one({"id": vendor_id})
    if not vendor or vendor.get("status") != "approved":
        raise HTTPException(400, "Vendor is not approved")

    # Build lines + totals (kademeli fiyat + promosyon uygulanır)
    lines_out: list[OrderLineOut] = []
    subtotal = 0.0
    for line in payload.lines:
        p = products_by_id[line.product_id]
        if not p.get("is_active", True):
            raise HTTPException(400, f"Product '{p['name']}' is not available")
        if line.quantity < int(p.get("moq", 1)):
            raise HTTPException(400, f"Product '{p['name']}' min order is {p.get('moq')}")
        if int(p.get("stock", 0)) < line.quantity:
            raise HTTPException(400, f"Product '{p['name']}' has insufficient stock")
        priced = resolve_effective_price(p, line.quantity)
        unit_price = priced["unit_price"]
        line_total = round(unit_price * line.quantity, 2)
        subtotal += line_total
        lines_out.append(
            OrderLineOut(
                product_id=p["id"],
                product_name=p["name"],
                quantity=line.quantity,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

    commission_pct = float(vendor.get("commission_pct", DEFAULT_COMMISSION_PCT))
    commission_amount = round(subtotal * commission_pct / 100.0, 2)
    vendor_payout = round(subtotal - commission_amount, 2)

    now = _utc_now_iso()
    order_doc = {
        "id": str(uuid.uuid4()),
        "order_no": _new_order_no(),
        "hotel_tenant_id": hotel_tenant_id,
        "hotel_name": hotel_name,
        "vendor_id": vendor["id"],
        "vendor_name": vendor.get("company_name", ""),
        "lines": [line.model_dump() for line in lines_out],
        "subtotal": round(subtotal, 2),
        "commission_pct": commission_pct,
        "commission_amount": commission_amount,
        "vendor_payout": vendor_payout,
        "total": round(subtotal, 2),  # cargo is vendor-paid in MVP
        "payment_method": payload.payment_method,
        "status": "pending",
        "shipping_address": payload.shipping_address,
        "contact_name": payload.contact_name,
        "contact_phone": payload.contact_phone,
        "notes": payload.notes,
        "shipment": None,
        "created_at": now,
        "updated_at": now,
    }
    # Atomic stock decrement BEFORE insert: only succeeds if stock >= qty.
    # Roll back any successful decrements if a later line fails.
    decremented: list[tuple[str, int]] = []
    try:
        for line in payload.lines:
            res = await products_col.update_one(
                {"id": line.product_id, "stock": {"$gte": line.quantity}},
                {"$inc": {"stock": -line.quantity}, "$set": {"updated_at": now}},
            )
            if res.modified_count != 1:
                # Roll back previously decremented lines
                for pid, qty in decremented:
                    await products_col.update_one(
                        {"id": pid},
                        {"$inc": {"stock": qty}},
                    )
                p = products_by_id.get(line.product_id, {})
                raise HTTPException(
                    409,
                    f"Stock unavailable for '{p.get('name', line.product_id)}' (concurrent order)",
                )
            decremented.append((line.product_id, line.quantity))
    except HTTPException:
        raise
    except Exception:
        logger.exception("supplies_market: atomic stock decrement failed")
        for pid, qty in decremented:
            try:
                await products_col.update_one({"id": pid}, {"$inc": {"stock": qty}})
            except Exception:
                logger.exception("supplies_market: rollback failed for %s", pid)
        raise HTTPException(500, "Order could not be placed; stock not changed")

    await orders_col.insert_one(order_doc)
    order_doc.pop("_id", None)
    return order_doc
