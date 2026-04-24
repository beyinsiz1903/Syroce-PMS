"""Admin endpoints — vendor approval & oversight (super_admin only)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from core.security import get_current_user

from .models import VendorPublic, _utc_now_iso
from .repository import orders_col, vendors_col
from .service import public_vendor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/supplies-market/admin", tags=["Supplies Marketplace — Admin"])


def _require_super_admin(current_user=Depends(get_current_user)):
    from core.security import _is_super_admin
    if _is_super_admin(current_user):
        return current_user
    raise HTTPException(403, "Super admin only")


@router.get("/vendors", response_model=list[VendorPublic])
async def admin_list_vendors(_=Depends(_require_super_admin)):
    docs = await vendors_col.find({}).sort("created_at", -1).to_list(length=500)
    return [public_vendor(d) for d in docs]


@router.post("/vendors/{vendor_id}/approve", response_model=VendorPublic)
async def admin_approve_vendor(
    vendor_id: str,
    commission_pct: float | None = None,
    _=Depends(_require_super_admin),
):
    update: dict = {"status": "approved", "updated_at": _utc_now_iso()}
    if commission_pct is not None:
        if not 0 <= commission_pct <= 50:
            raise HTTPException(400, "commission_pct out of range")
        update["commission_pct"] = float(commission_pct)
    res = await vendors_col.find_one_and_update(
        {"id": vendor_id},
        {"$set": update},
        return_document=True,
    )
    if not res:
        raise HTTPException(404, "Vendor not found")
    return public_vendor(res)


@router.post("/vendors/{vendor_id}/suspend", response_model=VendorPublic)
async def admin_suspend_vendor(vendor_id: str, _=Depends(_require_super_admin)):
    res = await vendors_col.find_one_and_update(
        {"id": vendor_id},
        {"$set": {"status": "suspended", "updated_at": _utc_now_iso()}},
        return_document=True,
    )
    if not res:
        raise HTTPException(404, "Vendor not found")
    return public_vendor(res)


@router.get("/orders")
async def admin_list_orders(_=Depends(_require_super_admin), limit: int = 200):
    docs = await orders_col.find({}).sort("created_at", -1).to_list(length=limit)
    out = []
    total_commission = 0.0
    for d in docs:
        d.pop("_id", None)
        total_commission += float(d.get("commission_amount", 0))
        out.append(d)
    return {"orders": out, "total_commission_try": round(total_commission, 2)}
