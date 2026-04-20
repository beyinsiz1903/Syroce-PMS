"""Vendor portal endpoints — separate auth scope.

Mounted under /api/supplies-market/vendor.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

from .models import (
    OrderOut,
    ProductIn,
    ProductOut,
    ShipmentInfo,
    VendorLogin,
    VendorPublic,
    VendorRegister,
    VendorTokenResponse,
    _utc_now_iso,
)
from .repository import orders_col, products_col, vendors_col
from .service import DEFAULT_COMMISSION_PCT, public_product, public_vendor
from .vendor_auth import (
    create_vendor_token,
    get_current_vendor_id,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/supplies-market/vendor", tags=["Supplies Marketplace — Vendor"])


# ── Auth ─────────────────────────────────────────────────────────────────────
@router.post("/register", response_model=VendorTokenResponse)
async def vendor_register(payload: VendorRegister):
    existing = await vendors_col.find_one({"email": payload.email.lower()})
    if existing:
        raise HTTPException(409, "Bu e-posta zaten kayıtlı")
    now = _utc_now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "email": payload.email.lower(),
        "password_hash": hash_password(payload.password),
        "company_name": payload.company_name,
        "contact_name": payload.contact_name,
        "phone": payload.phone,
        "tax_no": payload.tax_no,
        "tax_office": payload.tax_office,
        "iban": payload.iban,
        "address": payload.address,
        "city": payload.city,
        "status": "pending",  # awaits admin approval
        "commission_pct": DEFAULT_COMMISSION_PCT,
        "created_at": now,
        "updated_at": now,
    }
    await vendors_col.insert_one(doc)
    token = create_vendor_token(doc["id"], doc["email"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "vendor": public_vendor(doc),
    }


@router.post("/login", response_model=VendorTokenResponse)
async def vendor_login(payload: VendorLogin):
    doc = await vendors_col.find_one({"email": payload.email.lower()})
    if not doc or not verify_password(payload.password, doc.get("password_hash", "")):
        raise HTTPException(401, "E-posta veya şifre hatalı")
    if doc.get("status") == "suspended":
        raise HTTPException(403, "Hesabınız askıya alınmış")
    token = create_vendor_token(doc["id"], doc["email"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "vendor": public_vendor(doc),
    }


@router.get("/me", response_model=VendorPublic)
async def vendor_me(vendor_id: str = Depends(get_current_vendor_id)):
    doc = await vendors_col.find_one({"id": vendor_id})
    if not doc:
        raise HTTPException(404, "Vendor not found")
    return public_vendor(doc)


# ── Products ─────────────────────────────────────────────────────────────────
@router.get("/products", response_model=list[ProductOut])
async def vendor_list_products(vendor_id: str = Depends(get_current_vendor_id)):
    docs = await products_col.find({"vendor_id": vendor_id}).sort("created_at", -1).to_list(length=500)
    return [public_product(d) for d in docs]


@router.post("/products", response_model=ProductOut)
async def vendor_create_product(
    payload: ProductIn,
    vendor_id: str = Depends(get_current_vendor_id),
):
    vendor = await vendors_col.find_one({"id": vendor_id})
    if not vendor:
        raise HTTPException(404, "Vendor not found")
    if vendor.get("status") != "approved":
        raise HTTPException(403, "Hesabınız henüz onaylanmadı; ürün ekleyemezsiniz")
    now = _utc_now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "vendor_id": vendor_id,
        "vendor_name": vendor.get("company_name", ""),
        **payload.model_dump(),
        "created_at": now,
        "updated_at": now,
    }
    await products_col.insert_one(doc)
    return public_product(doc)


@router.put("/products/{product_id}", response_model=ProductOut)
async def vendor_update_product(
    product_id: str,
    payload: ProductIn,
    vendor_id: str = Depends(get_current_vendor_id),
):
    existing = await products_col.find_one({"id": product_id, "vendor_id": vendor_id})
    if not existing:
        raise HTTPException(404, "Ürün bulunamadı")
    now = _utc_now_iso()
    update = {**payload.model_dump(), "updated_at": now}
    await products_col.update_one({"id": product_id}, {"$set": update})
    merged = {**existing, **update}
    return public_product(merged)


@router.delete("/products/{product_id}")
async def vendor_delete_product(
    product_id: str,
    vendor_id: str = Depends(get_current_vendor_id),
):
    res = await products_col.delete_one({"id": product_id, "vendor_id": vendor_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Ürün bulunamadı")
    return {"deleted": True}


# ── Orders ───────────────────────────────────────────────────────────────────
def _order_to_out(doc: dict) -> dict:
    out = dict(doc)
    out.pop("_id", None)
    return out


@router.get("/orders", response_model=list[OrderOut])
async def vendor_list_orders(vendor_id: str = Depends(get_current_vendor_id)):
    docs = await orders_col.find({"vendor_id": vendor_id}).sort("created_at", -1).to_list(length=500)
    return [_order_to_out(d) for d in docs]


@router.post("/orders/{order_id}/confirm", response_model=OrderOut)
async def vendor_confirm_order(order_id: str, vendor_id: str = Depends(get_current_vendor_id)):
    doc = await orders_col.find_one({"id": order_id, "vendor_id": vendor_id})
    if not doc:
        raise HTTPException(404, "Sipariş bulunamadı")
    if doc["status"] != "pending":
        raise HTTPException(400, f"Sipariş şu durumda: {doc['status']}")
    now = _utc_now_iso()
    await orders_col.update_one({"id": order_id}, {"$set": {"status": "confirmed", "updated_at": now}})
    doc["status"] = "confirmed"
    doc["updated_at"] = now
    return _order_to_out(doc)


@router.post("/orders/{order_id}/ship", response_model=OrderOut)
async def vendor_ship_order(
    order_id: str,
    shipment: ShipmentInfo,
    vendor_id: str = Depends(get_current_vendor_id),
):
    doc = await orders_col.find_one({"id": order_id, "vendor_id": vendor_id})
    if not doc:
        raise HTTPException(404, "Sipariş bulunamadı")
    if doc["status"] not in {"pending", "confirmed"}:
        raise HTTPException(400, f"Sipariş kargoya verilemez: {doc['status']}")
    now = _utc_now_iso()
    shipment_doc = {**shipment.model_dump(), "shipped_at": now}
    await orders_col.update_one(
        {"id": order_id},
        {"$set": {"status": "shipped", "shipment": shipment_doc, "updated_at": now}},
    )
    doc.update({"status": "shipped", "shipment": shipment_doc, "updated_at": now})
    return _order_to_out(doc)


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def vendor_cancel_order(order_id: str, vendor_id: str = Depends(get_current_vendor_id)):
    doc = await orders_col.find_one({"id": order_id, "vendor_id": vendor_id})
    if not doc:
        raise HTTPException(404, "Sipariş bulunamadı")
    if doc["status"] in {"shipped", "delivered", "cancelled"}:
        raise HTTPException(400, f"Bu durumda iptal edilemez: {doc['status']}")
    now = _utc_now_iso()
    await orders_col.update_one({"id": order_id}, {"$set": {"status": "cancelled", "updated_at": now}})
    # Restore stock
    for line in doc.get("lines", []):
        try:
            await products_col.update_one(
                {"id": line["product_id"]},
                {"$inc": {"stock": int(line["quantity"])}, "$set": {"updated_at": now}},
            )
        except Exception:
            logger.warning("supplies_market: stock restore failed", exc_info=True)
    doc["status"] = "cancelled"
    doc["updated_at"] = now
    return _order_to_out(doc)
