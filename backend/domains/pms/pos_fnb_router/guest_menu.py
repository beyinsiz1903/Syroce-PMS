"""
guest_menu.py

Public endpoints for the QR Digital Menu and Ordering System.
"""
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.database import db
from domains.pms.pos_fnb_router.pos_core import _auto_kds_and_kot, _ensure_adisyon_counter_index, _get_pos_business_date, _next_adisyon_number

router = APIRouter(tags=["guest_menu"])

class GuestOrderRequest(BaseModel):
    table_id: str
    items: list[dict[str, Any]]  # [{"item_id": "...", "quantity": 1}]
    guest_name: str | None = None
    notes: str | None = None

@router.get("/public/fnb/{tenant_id}/{outlet_id}/menu")
async def get_guest_menu(tenant_id: str, outlet_id: str):
    """Get active menu categories and items for the guest."""

    items = await db.pos_menu_items.find({
        "tenant_id": tenant_id,
        "is_active": True
    }, {"_id": 0}).to_list(1000)

    if not items:
        return {"categories": []}

    categories = {}
    for item in items:
        cat_name = item.get("category", "Diğer")
        if cat_name not in categories:
            categories[cat_name] = []
        categories[cat_name].append(item)

    result = []
    for cat_name, cat_items in categories.items():
        result.append({
            "name": cat_name,
            "items": cat_items
        })

    return {"categories": result}


@router.post("/public/fnb/{tenant_id}/{outlet_id}/order")
async def place_guest_order(tenant_id: str, outlet_id: str, req: GuestOrderRequest):
    """
    Misafir tarafından QR menü üzerinden verilen sipariş doğrudan mutfağa (KDS) düşer.
    Ayrıca POS personeli ekranında da görünmesi için pending statüsünde bir sipariş oluşturulur.
    """

    # 1. Fetch items to calculate prices
    item_ids = [it["item_id"] for it in req.items]
    db_items = await db.pos_menu_items.find({
        "tenant_id": tenant_id,
        "id": {"$in": item_ids}
    }).to_list(1000)

    db_items_map = {str(it["id"]): it for it in db_items}

    order_items = []
    total_amount = 0.0

    for it in req.items:
        db_item = db_items_map.get(str(it["item_id"]))
        if not db_item:
            continue

        qty = float(it.get("quantity", 1))
        price = float(db_item.get("unit_price", 0))
        total_price = qty * price

        order_items.append({
            "item_id": db_item["id"],
            "item_name": db_item["item_name"],
            "category": db_item.get("category", "Diğer"),
            "quantity": qty,
            "unit_price": price,
            "total_price": total_price,
            "notes": it.get("notes", "")
        })
        total_amount += total_price

    if not order_items:
        raise HTTPException(status_code=400, detail="Sipariş kalemi bulunamadı veya geçersiz")

    business_date = await _get_pos_business_date(tenant_id)
    await _ensure_adisyon_counter_index()
    adisyon_no = await _next_adisyon_number(tenant_id, outlet_id, business_date)

    order_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "outlet_id": outlet_id,
        "source": "guest_qr",
        "table_id": req.table_id,
        "guest_name": req.guest_name,
        "status": "pending",  # Pending staff approval/closure
        "items": order_items,
        "total_amount": total_amount,
        "currency": "TRY",
        "business_date": business_date,
        "ordered_at": datetime.now(UTC).isoformat(),
        "adisyon_no": adisyon_no,
        "notes": req.notes
    }

    # Atomicity could be improved, but this is a guest facing non-financial draft order
    await db.pos_orders.insert_one(order_doc)

    # Send to KDS/Kitchen
    try:
        class DummyOrder:
            id = order_doc["id"]
            items = order_items
            outlet_id = outlet_id
            table_id = req.table_id
            notes = req.notes

        await _auto_kds_and_kot(DummyOrder(), tenant_id, "Guest QR")
    except Exception:
        pass  # non-critical for insertion

    # Cleanup _id just in case
    order_doc.pop("_id", None)

    return {
        "success": True,
        "message": "Siparişiniz mutfağa iletildi.",
        "order_id": order_doc["id"]
    }
