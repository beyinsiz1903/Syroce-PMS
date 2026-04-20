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
        "created_at": doc.get("created_at", ""),
        "updated_at": doc.get("updated_at", ""),
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

    # Build lines + totals
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
        unit_price = float(p["price_try"])
        line_total = unit_price * line.quantity
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
    await orders_col.insert_one(order_doc)

    # Decrement stock (best-effort; tolerated to fail without rolling order back
    # because admins can adjust stock from the vendor panel)
    for line in payload.lines:
        try:
            await products_col.update_one(
                {"id": line.product_id},
                {"$inc": {"stock": -line.quantity}, "$set": {"updated_at": now}},
            )
        except Exception:
            logger.warning("supplies_market: stock decrement failed for %s", line.product_id, exc_info=True)

    order_doc.pop("_id", None)
    return order_doc
