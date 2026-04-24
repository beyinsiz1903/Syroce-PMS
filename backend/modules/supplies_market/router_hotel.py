"""Hotel-facing endpoints — uses the existing staff JWT (get_current_user)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import get_current_user
from modules.pms_core.role_permission_service import require_op  # v99 DW

from .models import OrderCreate, OrderOut, ProductOut
from .repository import orders_col, products_col
from .service import place_order, public_product

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/supplies-market", tags=["Supplies Marketplace — Hotel"])


@router.get("/categories")
async def list_categories():
    return [
        {"key": "banyo", "label": "Banyo (Havlu, Şampuan, Terlik)"},
        {"key": "yatak_tekstil", "label": "Yatak & Tekstil"},
        {"key": "temizlik", "label": "Temizlik & Kimyasal"},
        {"key": "mutfak_fb", "label": "Mutfak & F&B"},
        {"key": "kirtasiye", "label": "Kırtasiye & Ofis"},
        {"key": "diger", "label": "Diğer"},
    ]


@router.get("/products", response_model=list[ProductOut])
async def list_products(
    category: str | None = None,
    q: str | None = Query(default=None, description="search text"),
    limit: int = Query(default=60, ge=1, le=200),
    _user=Depends(get_current_user),
):
    query: dict = {"is_active": True, "stock": {"$gt": 0}}
    if category:
        query["category"] = category
    if q:
        from security.query_safety import safe_search_term
        if (_s := safe_search_term(q)):
            query["name"] = {"$regex": _s, "$options": "i"}
    docs = await products_col.find(query).sort("created_at", -1).to_list(length=limit)
    return [public_product(d) for d in docs]


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: str, _user=Depends(get_current_user)):
    doc = await products_col.find_one({"id": product_id, "is_active": True})
    if not doc:
        raise HTTPException(404, "Ürün bulunamadı")
    return public_product(doc)


@router.post("/orders", response_model=OrderOut)
async def create_order(payload: OrderCreate, current_user=Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    hotel_tenant_id = getattr(current_user, "tenant_id", None)
    hotel_name = getattr(current_user, "tenant_name", None) or getattr(current_user, "username", "Hotel")
    if not hotel_tenant_id:
        raise HTTPException(400, "Tenant context missing")
    doc = await place_order(
        payload=payload, hotel_tenant_id=hotel_tenant_id, hotel_name=hotel_name
    )
    return doc


@router.get("/orders/mine", response_model=list[OrderOut])
async def my_orders(current_user=Depends(get_current_user), limit: int = Query(default=100, ge=1, le=500)):
    hotel_tenant_id = getattr(current_user, "tenant_id", None)
    if not hotel_tenant_id:
        raise HTTPException(400, "Tenant context missing")
    docs = await orders_col.find({"hotel_tenant_id": hotel_tenant_id}).sort("created_at", -1).to_list(length=limit)
    out = []
    for d in docs:
        d.pop("_id", None)
        out.append(d)
    return out


@router.post("/orders/{order_id}/confirm-delivery", response_model=OrderOut)
async def confirm_delivery(order_id: str, current_user=Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v99 DW
):
    hotel_tenant_id = getattr(current_user, "tenant_id", None)
    doc = await orders_col.find_one({"id": order_id, "hotel_tenant_id": hotel_tenant_id})
    if not doc:
        raise HTTPException(404, "Sipariş bulunamadı")
    if doc["status"] != "shipped":
        raise HTTPException(400, "Sipariş henüz kargoya verilmemiş")
    from .models import _utc_now_iso

    now = _utc_now_iso()
    await orders_col.update_one({"id": order_id}, {"$set": {"status": "delivered", "updated_at": now}})
    doc["status"] = "delivered"
    doc["updated_at"] = now
    doc.pop("_id", None)
    return doc
