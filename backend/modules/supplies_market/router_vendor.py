"""Vendor portal endpoints — separate auth scope.

Mounted under /api/supplies-market/vendor.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

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
async def vendor_login(request: Request, payload: VendorLogin):
    # Task-135 (P0 drain fix) — Verify-first, record-on-fail,
    # drain-on-success ordering. See the parallel comment on
    # agency_portal.agency_login for the full rationale: enforcing
    # the throttle BEFORE verify_password makes the (cap+1)th attempt
    # 429 even when credentials are correct, blocking legitimate
    # users with mistyped-prior-attempts and making the `.reset()`
    # drain branch unreachable. Failed attempts still record a hit,
    # so the 21st wrong-credential attempt against a given IP (or
    # 11th against a given account) returns 429 — matches stress
    # spec 98D Phase 3 boundary.
    from security.auth_throttle import (
        VENDOR_LOGIN_ACCOUNT,
        VENDOR_LOGIN_IP,
        client_ip,
        normalize_identity,
    )
    from security.auth_throttle import enforce as _throttle

    _ip = client_ip(request)
    _email_key = normalize_identity(payload.email)
    _ip_key = f"vendor_login_ip:{_ip}"
    _acct_key = f"vendor_login_acct:{_email_key}" if _email_key else None

    async def _record_failure_and_raise(status_code: int, detail: str):
        await _throttle(VENDOR_LOGIN_IP, _ip_key, "giris denemesi")
        if _acct_key:
            await _throttle(VENDOR_LOGIN_ACCOUNT, _acct_key, "giris denemesi")
        raise HTTPException(status_code, detail)

    doc = await vendors_col.find_one({"email": payload.email.lower()})
    if not doc or not verify_password(payload.password, doc.get("password_hash", "")):
        await _record_failure_and_raise(401, "E-posta veya şifre hatalı")
    if doc.get("status") == "suspended":
        # Account-status 403 is an authorization decision (credentials
        # were already verified above), NOT a credential probe. Do not
        # consume the throttle budget — see the parallel comment in
        # agency_portal.agency_login.
        raise HTTPException(403, "Hesabınız askıya alınmış")

    # Successful credential verify — drain throttle counters so a
    # legitimate vendor isn't penalised for prior typos.
    try:
        await VENDOR_LOGIN_IP.reset(_ip_key)
        if _acct_key:
            await VENDOR_LOGIN_ACCOUNT.reset(_acct_key)
    except Exception:
        pass

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


_UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "backend/uploads"))
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/products/upload-image")
async def vendor_upload_product_image(
    file: UploadFile = File(...),
    vendor_id: str = Depends(get_current_vendor_id),
):
    from security.upload_validator import MAX_IMAGE_BYTES, validate_image_bytes

    # Magic-bytes verify (rejects SVG, PDF, spoofed-MIME polyglots and
    # canonicalizes ext/content-type from the real decoded format).
    content = await file.read(MAX_IMAGE_BYTES + 1)
    _, ext = validate_image_bytes(content, max_bytes=MAX_IMAGE_BYTES, field_label="Gorsel")

    folder = _UPLOAD_DIR / "vendors" / vendor_id / "products"
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    relative_path = f"vendors/{vendor_id}/products/{filename}"
    (folder / filename).write_bytes(content)
    
    upload_id = str(uuid.uuid4())
    upload_record = {
        "_id": upload_id,
        "owner_type": "vendor",
        "vendor_id": vendor_id,
        "file_scope": "product_image",
        "visibility": "marketplace_public",
        "filename": filename,
        "relative_path": relative_path,
        "content_type": getattr(file, "content_type", "application/octet-stream"),
        "size_bytes": len(content),
        "created_at": datetime.now(UTC).isoformat(),
    }
    
    from core.database import db
    await db.uploads.insert_one(upload_record)
    
    url = f"/api/uploads/{upload_id}"
    return {"url": url}


# ── Orders ───────────────────────────────────────────────────────────────────
def _order_to_out(doc: dict) -> dict:
    out = dict(doc)
    out.pop("_id", None)
    return out


@router.get("/orders", response_model=list[OrderOut])
async def vendor_list_orders(vendor_id: str = Depends(get_current_vendor_id)):
    docs = await orders_col.find({"vendor_id": vendor_id}).sort("created_at", -1).to_list(length=500)
    return [_order_to_out(d) for d in docs]


@router.get("/earnings")
async def vendor_earnings(vendor_id: str = Depends(get_current_vendor_id)):
    """Kazanç ve komisyon özeti — tüm zamanlar, son 30 gün, aylık trend, durum kırılımı."""
    from collections import defaultdict
    from datetime import UTC, datetime, timedelta

    docs = await orders_col.find({"vendor_id": vendor_id}).to_list(length=5000)

    # Earned (gelir sayılan) durumlar: confirmed, shipped, delivered, completed
    EARNED_STATES = {"confirmed", "shipped", "delivered", "completed"}
    PENDING_STATES = {"pending"}
    CANCELLED_STATES = {"cancelled", "refunded"}

    now = datetime.now(UTC)
    last30 = now - timedelta(days=30)

    def bucket():
        return {"orders": 0, "gross": 0.0, "commission": 0.0, "net": 0.0}

    all_time = bucket()
    last_30d = bucket()
    pending_b = bucket()
    cancelled_b = bucket()
    monthly = defaultdict(bucket)

    for d in docs:
        gross = float(d.get("subtotal", 0))
        commission = float(d.get("commission_amount", 0))
        net = float(d.get("vendor_payout", gross - commission))
        status = d.get("status", "pending")
        created = d.get("created_at", "")

        if status in EARNED_STATES:
            for b in (all_time,):
                b["orders"] += 1
                b["gross"] += gross
                b["commission"] += commission
                b["net"] += net
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                if dt >= last30:
                    last_30d["orders"] += 1
                    last_30d["gross"] += gross
                    last_30d["commission"] += commission
                    last_30d["net"] += net
                key = dt.strftime("%Y-%m")
                m = monthly[key]
                m["orders"] += 1
                m["gross"] += gross
                m["commission"] += commission
                m["net"] += net
            except Exception:
                pass
        elif status in PENDING_STATES:
            pending_b["orders"] += 1
            pending_b["gross"] += gross
            pending_b["commission"] += commission
            pending_b["net"] += net
        elif status in CANCELLED_STATES:
            cancelled_b["orders"] += 1
            cancelled_b["gross"] += gross
            cancelled_b["commission"] += commission
            cancelled_b["net"] += net

    def round_b(b):
        return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in b.items()}

    monthly_list = sorted(
        [{"month": k, **round_b(v)} for k, v in monthly.items()],
        key=lambda x: x["month"],
    )[-12:]

    return {
        "all_time": round_b(all_time),
        "last_30_days": round_b(last_30d),
        "pending": round_b(pending_b),
        "cancelled": round_b(cancelled_b),
        "monthly": monthly_list,
        "currency": "TRY",
    }


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
