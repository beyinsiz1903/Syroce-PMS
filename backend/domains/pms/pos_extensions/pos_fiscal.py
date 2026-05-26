"""POS Fiscal — Türkiye yasal mali yazıcı (ÖKC) adapter + kuyruk.

Türkiye'de fiscal printer entegrasyonu donanım + sertifikalı entegratör
gerektirir (Hugin/Beko/Profilo gibi markaların kapalı SDK'ları). Bu modül
adapter pattern ile **pluggable** bir iskelet sağlar:

  POS_FISCAL_DRIVER env değişkeni:
    - "simulator" (default) : mock fiscal_no/z_no üretir, prod-dışı
    - "hugin_stub"          : ileride entegratör tarafından doldurulacak
                              (şu an açıkça "manual mode required" döner)

Mevcut close_order/folio akışı bozulmaz; bu kuyruk POS bilgisini fiscal'a
asenkron forward eder. Production'da gerçek sürücü olmadan job 'failed'
döner ve operatör manuel mali fiş kesimi için uyarı alır.
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User

from ._idem import idempotent_insert

router = APIRouter(prefix="/api/pos/ext/fiscal", tags=["pos-ext-fiscal"])


# ── Fail-closed driver resolution ────────────────────────────────────
# Production'da simülatör default'u **deploy-blocker** olarak engellenir:
# sertifikalı ÖKC sürücüsü ya da explicit `ALLOW_POS_FISCAL_SIMULATOR=true`
# (sadece dev/test) olmadan submit/eod yolları 503 döner. Bu, mock fiscal
# yanıtının canlıda "başarılı" görünmesini imkânsız kılar.
def _resolve_driver() -> str:
    env = (os.environ.get("ENVIRONMENT") or os.environ.get("SENTRY_ENVIRONMENT") or "").lower()
    is_prod = env in ("production", "prod", "live")
    allow_sim = (os.environ.get("ALLOW_POS_FISCAL_SIMULATOR", "").lower() in ("1", "true", "yes"))
    driver = (os.environ.get("POS_FISCAL_DRIVER") or "").strip().lower()
    if not driver:
        driver = "simulator"
    if driver == "simulator" and is_prod and not allow_sim:
        raise HTTPException(
            status_code=503,
            detail=(
                "Fiscal simulator driver disabled in production. "
                "Configure certified ÖKC driver (POS_FISCAL_DRIVER) or set "
                "ALLOW_POS_FISCAL_SIMULATOR=true (dev/test only)."
            ),
        )
    return driver


class FiscalLineItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1, max_length=120)
    quantity: float = Field(gt=0)
    unit_price: float = Field(ge=0)
    tax_rate: float = Field(default=10.0, ge=0, le=100)  # KDV %
    department: str | None = None


class FiscalJobCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    order_id: str = Field(min_length=1)
    payment_method: str = Field(default="cash", pattern="^(cash|card|ticket|mixed)$")
    total: float = Field(ge=0)
    items: list[FiscalLineItem]
    customer_tax_id: str | None = None  # VKN/TCKN (e-fatura için)
    idempotency_key: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


async def _simulator_submit(job: dict) -> dict:
    """Mock fiscal device — production-dışı; deterministic mock fiscal_no."""
    fiscal_no = f"SIM-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{job['id'][:8].upper()}"
    z_no = datetime.now(UTC).strftime("%Y%m%d")
    return {
        "driver": "simulator",
        "ok": True,
        "fiscal_no": fiscal_no,
        "z_no": z_no,
        "submitted_at": _now().isoformat(),
        "warning": "SIMULATOR — production fiscal certification required",
    }


async def _hugin_stub_submit(job: dict) -> dict:
    """Hugin/Beko/Profilo ÖKC entegrasyonu için iskelet."""
    return {
        "driver": "hugin_stub",
        "ok": False,
        "reason": "manual mode required — certified integrator not configured",
        "manual_instruction": "Kasiyer fiziksel ÖKC üzerinden mali fiş kesimi yapmalı.",
    }


async def _submit(job: dict) -> dict:
    driver = _resolve_driver()  # may raise 503 in production
    if driver == "simulator":
        return await _simulator_submit(job)
    if driver == "hugin_stub":
        return await _hugin_stub_submit(job)
    return {"driver": driver, "ok": False, "reason": "unknown fiscal driver"}


@router.post("/jobs")
async def enqueue(body: FiscalJobCreate, current_user: User = Depends(get_current_user)):
    # Verify referenced order belongs to this tenant (no mutation).
    order = await db.pos_orders.find_one(
        {"id": body.order_id, "tenant_id": current_user.tenant_id}, {"_id": 0, "id": 1}
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found in this tenant")

    job = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "order_id": body.order_id,
        "payment_method": body.payment_method,
        "total": float(body.total),
        "items": [i.model_dump() for i in body.items],
        "customer_tax_id": body.customer_tax_id,
        "status": "pending",
        "idempotency_key": body.idempotency_key,
        "created_at": _now(),
        "created_by": current_user.id,
    }
    saved, replayed = await idempotent_insert(
        db.fiscal_jobs, current_user.tenant_id, body.idempotency_key, job
    )
    return {"success": True, "job": saved, "idempotent": replayed}


@router.get("/jobs")
async def list_jobs(
    status: str | None = Query(default=None, pattern="^(pending|submitted|failed|cancelled)$"),
    order_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    q: dict = {"tenant_id": current_user.tenant_id}
    if status:
        q["status"] = status
    if order_id:
        q["order_id"] = order_id
    rows = await db.fiscal_jobs.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"jobs": rows, "count": len(rows)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, current_user: User = Depends(get_current_user)):
    job = await db.fiscal_jobs.find_one(
        {"id": job_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/submit")
async def submit_job(job_id: str, current_user: User = Depends(get_current_user)):
    job = await db.fiscal_jobs.find_one(
        {"id": job_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] in ("submitted", "cancelled"):
        return {"success": True, "status": job["status"], "idempotent": True}

    result = await _submit(job)
    new_status = "submitted" if result.get("ok") else "failed"
    update = {
        "status": new_status,
        "submitted_at": _now() if result.get("ok") else None,
        "last_attempt_at": _now(),
        "fiscal_result": result,
    }
    if result.get("fiscal_no"):
        update["fiscal_no"] = result["fiscal_no"]
    if result.get("z_no"):
        update["z_no"] = result["z_no"]
    await db.fiscal_jobs.update_one(
        {"id": job_id, "tenant_id": current_user.tenant_id}, {"$set": update}
    )
    return {"success": result.get("ok", False), "status": new_status, "result": result}


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str, current_user: User = Depends(get_current_user)):
    res = await db.fiscal_jobs.update_one(
        {"id": job_id, "tenant_id": current_user.tenant_id, "status": "pending"},
        {"$set": {"status": "cancelled", "cancelled_at": _now(), "cancelled_by": current_user.id}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pending job not found")
    return {"success": True, "cancelled": job_id}


@router.post("/eod")
async def end_of_day(current_user: User = Depends(get_current_user)):
    """Trigger a Z-report on the fiscal device (simulator only for now)."""
    driver = _resolve_driver()  # may raise 503 in production w/o sim allowance
    if driver != "simulator":
        return {
            "success": False,
            "driver": driver,
            "reason": "EOD Z-report requires certified driver; perform on physical device.",
        }
    z_no = datetime.now(UTC).strftime("%Y%m%d")
    record = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "z_no": z_no,
        "driver": "simulator",
        "executed_at": _now(),
        "executed_by": current_user.id,
    }
    await db.fiscal_eod.insert_one(record)
    record.pop("_id", None)
    return {"success": True, "z_no": z_no, "record": record}
