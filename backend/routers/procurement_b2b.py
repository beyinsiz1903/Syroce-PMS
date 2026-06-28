"""B2B Supply Integration & Automated Replenishment.

Links local inventory critical stock levels (reorder_level) to the Supplies Marketplace.
Generates order proposals and submits approved orders directly to vendors via the Vendor Portal.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op
from modules.supplies_market.service import place_order
from modules.supplies_market.models import OrderCreate, OrderLineIn

router = APIRouter(prefix="/api/procurement/b2b", tags=["B2B Procurement Automation"])


class B2BReplenishLine(BaseModel):
    inventory_item_id: str = Field(..., min_length=1)
    mp_product_id: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=1)


class B2BApproveRequest(BaseModel):
    lines: list[B2BReplenishLine] = Field(..., min_length=1)
    shipping_address: str = Field(..., min_length=5, max_length=500)
    contact_name: str = Field(..., min_length=2, max_length=120)
    contact_phone: str = Field(..., min_length=7, max_length=30)
    payment_method: Literal["cash_on_delivery", "bank_transfer", "credit_card"] = "bank_transfer"
    notes: str | None = Field(None, max_length=1000)


@router.get("/proposals")
async def get_replenishment_proposals(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_hr")),  # or other procurement view perm
):
    """Scan local critical stock and match with approved marketplace vendors."""
    db = get_system_db()
    tenant_id = current_user.tenant_id

    # 1. Fetch local inventory items
    local_items = await db.inventory_items.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(1000)

    # 2. Filter for low stock (quantity <= reorder_level)
    low_stock_items = [
        item for item in local_items
        if float(item.get("quantity", 0)) <= float(item.get("reorder_level", 0))
    ]

    proposals_by_vendor: dict[str, dict[str, Any]] = {}

    for item in low_stock_items:
        # 3. Match with marketplace products in mp_products (raw db)
        sku = item.get("sku")
        name = item.get("name")
        product = None

        if sku:
            product = await db.mp_products.find_one({"sku": sku, "is_active": True})
        if not product and name:
            product = await db.mp_products.find_one({
                "name": {"$regex": f"^{name}$", "$options": "i"},
                "is_active": True
            })

        if not product:
            continue

        # Check if vendor is approved
        vendor_id = product["vendor_id"]
        vendor = await db.mp_vendors.find_one({"id": vendor_id, "status": "approved"})
        if not vendor:
            continue

        # Calculate proposed qty (to bring stock back to 2x reorder level)
        reorder_lvl = float(item.get("reorder_level", 0))
        curr_qty = float(item.get("quantity", 0))
        target_qty = int(max(product.get("moq", 1), reorder_lvl * 2 - curr_qty))

        proposal_line = {
            "inventory_item_id": item["id"],
            "name": item["name"],
            "sku": item.get("sku"),
            "current_stock": curr_qty,
            "reorder_level": reorder_lvl,
            "proposed_qty": target_qty,
            "mp_product_id": product["id"],
            "unit": product.get("unit", "adet"),
            "unit_price": product["price_try"],
            "total_price": round(product["price_try"] * target_qty, 2)
        }

        if vendor_id not in proposals_by_vendor:
            proposals_by_vendor[vendor_id] = {
                "vendor_id": vendor_id,
                "vendor_name": vendor.get("company_name", ""),
                "lines": []
            }
        proposals_by_vendor[vendor_id]["lines"].append(proposal_line)

    return {"proposals": list(proposals_by_vendor.values())}


@router.post("/orders/approve")
async def approve_replenishment_orders(
    payload: B2BApproveRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Group approved items by vendor and submit orders directly to marketplace."""
    db = get_system_db()
    tenant_id = current_user.tenant_id

    # 1. Fetch products to group by vendor_id
    product_ids = [line.mp_product_id for line in payload.lines]
    products = await db.mp_products.find({"id": {"$in": product_ids}, "is_active": True}).to_list(1000)
    products_by_id = {p["id"]: p for p in products}

    if len(products_by_id) != len(set(product_ids)):
        raise HTTPException(status_code=400, detail="Bir veya daha fazla pazaryeri ürünü bulunamadı")

    # Group lines by vendor
    lines_by_vendor: dict[str, list[B2BReplenishLine]] = {}
    for line in payload.lines:
        p = products_by_id[line.mp_product_id]
        vid = p["vendor_id"]
        if vid not in lines_by_vendor:
            lines_by_vendor[vid] = []
        lines_by_vendor[vid].append(line)

    placed_orders = []
    hotel_name = getattr(current_user, "tenant_name", None) or current_user.username

    # 2. Place orders per vendor
    for vid, group_lines in lines_by_vendor.items():
        order_lines = [
            OrderLineIn(product_id=line.mp_product_id, quantity=line.quantity)
            for line in group_lines
        ]

        order_create = OrderCreate(
            lines=order_lines,
            payment_method=payload.payment_method,
            shipping_address=payload.shipping_address,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            notes=payload.notes or "Otomatik kritik stok siparişi"
        )

        # place_order decreases stock and inserts order_doc
        order_doc = await place_order(
            payload=order_create,
            hotel_tenant_id=tenant_id,
            hotel_name=hotel_name
        )
        placed_orders.append(order_doc)

        # Write trace/audit mappings for local tracking
        for line in group_lines:
            replenishment_trace = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "inventory_item_id": line.inventory_item_id,
                "mp_product_id": line.mp_product_id,
                "order_id": order_doc["id"],
                "order_no": order_doc["order_no"],
                "quantity": line.quantity,
                "created_at": datetime.now(UTC).isoformat()
            }
            await db.procurement_b2b_replenishments.insert_one(replenishment_trace)

    return {
        "success": True,
        "message": f"{len(placed_orders)} adet tedarikçi siparişi başarıyla oluşturuldu.",
        "orders": [
            {"order_id": o["id"], "order_no": o["order_no"], "vendor_name": o["vendor_name"], "total": o["total"]}
            for o in placed_orders
        ]
    }
