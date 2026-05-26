"""POS Multi-Currency — yabancı dövizle tahsilat + kur snapshot.

Mevcut akış bozulmaz: bu router pos_transactions'a YAZMAZ, sadece
yan tablo (`pos_payments_multi`) tutar ve kur snapshot'larını
(`pos_exchange_rates`) saklar. Mevcut close_order/post_to_folio
akışı tenant currency'sinde çalışmaya devam eder.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User

from ._idem import idempotent_insert

router = APIRouter(prefix="/api/pos/ext/currency", tags=["pos-ext-currency"])


# ── Schemas ─────────────────────────────────────────────────────────
class ExchangeRateUpsert(BaseModel):
    model_config = ConfigDict(extra="ignore")
    currency_code: str = Field(min_length=3, max_length=3)
    rate_to_base: float = Field(gt=0)
    base_currency: str = Field(default="TRY", min_length=3, max_length=3)
    note: str | None = None


class ForeignPayment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    order_id: str
    currency_code: str = Field(min_length=3, max_length=3)
    amount_foreign: float = Field(gt=0)
    rate_used: float | None = Field(default=None, gt=0)
    payment_method: str = Field(default="cash")
    idempotency_key: str | None = None


# ── Helpers ─────────────────────────────────────────────────────────
async def _latest_rate(tenant_id: str, code: str) -> dict | None:
    return await db.pos_exchange_rates.find_one(
        {"tenant_id": tenant_id, "currency_code": code.upper()},
        sort=[("valid_at", -1)],
        projection={"_id": 0},
    )


# ── Endpoints ───────────────────────────────────────────────────────
@router.post("/rates")
async def upsert_rate(body: ExchangeRateUpsert, current_user: User = Depends(get_current_user)):
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "currency_code": body.currency_code.upper(),
        "base_currency": body.base_currency.upper(),
        "rate_to_base": float(body.rate_to_base),
        "note": body.note,
        "valid_at": datetime.now(UTC),
        "created_by": current_user.id,
    }
    await db.pos_exchange_rates.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "rate": doc}


@router.get("/rates")
async def list_rates(
    code: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    q: dict = {"tenant_id": current_user.tenant_id}
    if code:
        q["currency_code"] = code.upper()
    rows = await db.pos_exchange_rates.find(q, {"_id": 0}).sort("valid_at", -1).to_list(limit)
    return {"rates": rows, "count": len(rows)}


@router.get("/rates/latest/{code}")
async def latest(code: str, current_user: User = Depends(get_current_user)):
    rate = await _latest_rate(current_user.tenant_id, code)
    if not rate:
        raise HTTPException(status_code=404, detail="No rate found")
    return rate


@router.post("/payments")
async def record_foreign_payment(body: ForeignPayment, current_user: User = Depends(get_current_user)):
    code = body.currency_code.upper()
    rate_used = body.rate_used
    if rate_used is None:
        rate_doc = await _latest_rate(current_user.tenant_id, code)
        if not rate_doc:
            raise HTTPException(status_code=400, detail=f"No exchange rate for {code}; submit rate_used or upsert rate first")
        rate_used = float(rate_doc["rate_to_base"])

    # Verify the order belongs to this tenant (do not mutate it).
    order = await db.pos_orders.find_one(
        {"id": body.order_id, "tenant_id": current_user.tenant_id}, {"_id": 0, "id": 1}
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found in this tenant")

    amount_base = round(body.amount_foreign * rate_used, 2)
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "order_id": body.order_id,
        "currency_code": code,
        "amount_foreign": float(body.amount_foreign),
        "rate_used": rate_used,
        "amount_base": amount_base,
        "payment_method": body.payment_method,
        "idempotency_key": body.idempotency_key,
        "created_at": datetime.now(UTC),
        "created_by": current_user.id,
    }
    saved, replayed = await idempotent_insert(
        db.pos_payments_multi, current_user.tenant_id, body.idempotency_key, doc
    )
    return {"success": True, "payment": saved, "idempotent": replayed}


@router.get("/payments")
async def list_payments(
    order_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    q: dict = {"tenant_id": current_user.tenant_id}
    if order_id:
        q["order_id"] = order_id
    rows = await db.pos_payments_multi.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    total_base = round(sum(float(r.get("amount_base", 0)) for r in rows), 2)
    return {"payments": rows, "count": len(rows), "total_base": total_base}


@router.delete("/payments/{payment_id}")
async def void_payment(payment_id: str, current_user: User = Depends(get_current_user)):
    res = await db.pos_payments_multi.delete_one(
        {"id": payment_id, "tenant_id": current_user.tenant_id}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"success": True, "deleted": payment_id}


@router.delete("/rates/{rate_id}")
async def delete_rate(rate_id: str, current_user: User = Depends(get_current_user)):
    res = await db.pos_exchange_rates.delete_one(
        {"id": rate_id, "tenant_id": current_user.tenant_id}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rate not found")
    return {"success": True, "deleted": rate_id}
