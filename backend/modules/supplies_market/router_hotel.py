"""Hotel-facing endpoints — uses the existing staff JWT (get_current_user)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import get_current_user
from modules.pms_core.role_permission_service import require_op  # v99 DW

from .models import CompareResponse, OrderCreate, OrderOut, ProductOut
from .repository import orders_col, products_col, vendors_col
from .service import place_order, public_product, resolve_effective_price

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


async def _approved_vendor_ids() -> set[str]:
    """Yalnızca onaylı tedarikçilerin id'lerini döner."""
    cur = vendors_col.find({"status": "approved"}, {"id": 1})
    return {v["id"] async for v in cur}


@router.get("/products", response_model=list[ProductOut])
async def list_products(
    category: str | None = None,
    q: str | None = Query(default=None, description="search text"),
    limit: int = Query(default=60, ge=1, le=200),
    _user=Depends(get_current_user),
):
    approved = await _approved_vendor_ids()
    if not approved:
        return []
    query: dict = {
        "is_active": True,
        "stock": {"$gt": 0},
        "vendor_id": {"$in": list(approved)},
    }
    if category:
        query["category"] = category
    if q:
        from security.query_safety import safe_search_term
        if (_s := safe_search_term(q)):
            query["name"] = {"$regex": _s, "$options": "i"}
    docs = await products_col.find(query).sort("created_at", -1).to_list(length=limit)
    return [public_product(d) for d in docs]


@router.get("/products/compare", response_model=CompareResponse)
async def compare_products(
    category: str | None = Query(default=None, description="Ürün kategorisi"),
    q: str | None = Query(default=None, description="İsim araması"),
    qty: int = Query(default=1, ge=1, le=100000, description="Karşılaştırma için adet"),
    limit: int = Query(default=20, ge=3, le=50, description="Maks. tedarikçi seçeneği"),
    _user=Depends(get_current_user),
):
    """3+ tedarikçinin aynı kategorideki en iyi tekliflerini yan yana getirir.

    Her ürün için verilen miktara göre kademeli fiyat (price_tiers) ve
    aktif promosyonları uygular; en uygun fiyat + en kısa teslim + en
    iyi vade kombinasyonunu skorlayıp `best_pick_id` olarak işaretler.
    """
    query: dict = {"is_active": True, "stock": {"$gt": 0}}
    if category:
        query["category"] = category
    if q:
        from security.query_safety import safe_search_term
        if (_s := safe_search_term(q)):
            query["name"] = {"$regex": _s, "$options": "i"}

    docs = await products_col.find(query).to_list(length=limit * 4)
    if not docs:
        return {"category": category, "q": q, "qty": qty, "options": [], "best_pick_id": None}

    # Vendor adı ve onay kontrolü için bir kerelik fetch
    vendor_ids = list({d["vendor_id"] for d in docs})
    vendors = await vendors_col.find({"id": {"$in": vendor_ids}}).to_list(length=len(vendor_ids))
    approved_vendors = {
        v["id"]: v.get("company_name", "")
        for v in vendors
        if v.get("status") == "approved"
    }

    options: list[dict] = []
    for d in docs:
        vid = d["vendor_id"]
        if vid not in approved_vendors:
            continue
        if int(d.get("stock", 0)) < qty:
            # qty kadar stok yoksa karşılaştırmaya alma
            continue
        priced = resolve_effective_price(d, qty)
        options.append({
            "product_id": d["id"],
            "product_name": d["name"],
            "vendor_id": vid,
            "vendor_name": approved_vendors[vid] or d.get("vendor_name", ""),
            "base_price_try": priced["base_price"],
            "effective_price_try": priced["unit_price"],
            "line_total_try": round(priced["unit_price"] * qty, 2),
            "qty": qty,
            "moq": int(d.get("moq", 1)),
            "unit": d.get("unit", "adet"),
            "stock": int(d.get("stock", 0)),
            "lead_time_days": int(d.get("lead_time_days", 0) or 0),
            "payment_terms_days": int(d.get("payment_terms_days", 0) or 0),
            "applied_tier": priced["applied_tier"],
            "applied_promotion": priced["applied_promotion"],
            "savings_pct": priced["savings_pct"],
        })

    # Ucuz → pahalı sırala
    options.sort(key=lambda o: o["effective_price_try"])
    options = options[:limit]

    # Akıllı seçim skoru: fiyat (60%) + teslim süresi (25%) + vade (15%)
    best_pick_id: str | None = None
    if options:
        prices = [o["effective_price_try"] for o in options]
        leads = [o["lead_time_days"] for o in options]
        terms = [o["payment_terms_days"] for o in options]
        p_min, p_max = min(prices), max(prices)
        l_min, l_max = min(leads), max(leads)
        t_min, t_max = min(terms), max(terms)

        def score(o: dict) -> float:
            # 0..1 arası, küçük iyi (price/lead için), büyük iyi (term için)
            p_n = (o["effective_price_try"] - p_min) / (p_max - p_min) if p_max > p_min else 0
            l_n = (o["lead_time_days"] - l_min) / (l_max - l_min) if l_max > l_min else 0
            t_n = 1 - ((o["payment_terms_days"] - t_min) / (t_max - t_min)) if t_max > t_min else 0
            return 0.60 * p_n + 0.25 * l_n + 0.15 * t_n

        best_pick_id = min(options, key=score)["product_id"]

    return {
        "category": category,
        "q": q,
        "qty": qty,
        "options": options,
        "best_pick_id": best_pick_id,
    }


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: str, _user=Depends(get_current_user)):
    doc = await products_col.find_one({"id": product_id, "is_active": True})
    if not doc:
        raise HTTPException(404, "Ürün bulunamadı")
    vendor = await vendors_col.find_one({"id": doc.get("vendor_id")}, {"status": 1})
    if not vendor or vendor.get("status") != "approved":
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
