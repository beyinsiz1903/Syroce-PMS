"""
Accounting / Sabit Kıymet (Demirbaş) + Amortisman
=================================================
Sabit kıymet register'ı (edinim tarihi/maliyet/hurda değer/faydalı ömür/yöntem),
düz (straight-line) ve azalan bakiye (declining-balance) amortisman hesabı,
dönemsel amortisman çalıştırma.

Değişmezler:
  * Tenant-scoped; mutasyonlar muhasebe seviyesi RBAC.
  * accumulated_depreciation HER ZAMAN depreciation_entries toplamından
    hesaplanır (ledger recalc), asla $inc.
  * Dönemsel çalıştırma idempotent: (tenant, asset_id, period) tekil; aynı dönem
    iki kez çalışsa ikinci kez yeni gider yazmaz.
  * Amortisman defter değerini hurda değerin altına indirmez (fail-safe clamp).
"""
import logging
import uuid
from calendar import monthrange
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger("domains.accounting.fixed_asset")

router = APIRouter(prefix="/api/fixed-assets", tags=["Accounting / Fixed Assets"])

_ASSET_ROLES = {"super_admin", "admin", "accountant"}
_READ_ROLES = {"super_admin", "admin", "accountant", "supervisor"}
_METHODS = {"straight_line", "declining_balance"}
_EPS = 0.005


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _tenant_of(user: User) -> str:
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=400, detail="Tenant bulunamadı")
    return tid


def _role_of(user: User) -> str:
    role = getattr(user, "role", None)
    return getattr(role, "value", role) or ""


def _require_role(user: User, allowed: set[str]) -> None:
    if getattr(user, "is_super_admin", False):
        return
    if _role_of(user) not in allowed:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")


def _actor_id(user: User) -> str:
    return getattr(user, "id", None) or getattr(user, "user_id", None) or "system"


def _period_of(date_iso: str) -> str:
    return date_iso[:7]


def _add_months(period: str, n: int) -> str:
    y, m = (int(x) for x in period.split("-")[:2])
    total = (y * 12 + (m - 1)) + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _monthly_depreciation(asset: dict, book_value: float) -> float:
    """Verilen defter değerine göre o ay düşülecek amortismanı döner."""
    cost = float(asset.get("acquisition_cost", 0) or 0)
    salvage = float(asset.get("salvage_value", 0) or 0)
    life = max(int(asset.get("useful_life_months", 1) or 1), 1)
    method = asset.get("method", "straight_line")
    depreciable_floor = salvage

    if book_value - depreciable_floor <= _EPS:
        return 0.0

    if method == "declining_balance":
        annual_rate = float(asset.get("declining_rate", 0) or 0) / 100.0
        raw = book_value * annual_rate / 12.0
    else:  # straight_line
        raw = (cost - salvage) / life

    # Hurda değerin altına inme.
    raw = min(raw, book_value - depreciable_floor)
    return round(max(raw, 0.0), 2)


def _build_schedule(asset: dict, max_periods: int = 600) -> list[dict]:
    """Edinimden itibaren tam amortisman tablosunu (persist edilmeden) üretir."""
    cost = float(asset.get("acquisition_cost", 0) or 0)
    period = _period_of(asset.get("acquisition_date", _now_iso()))
    book = cost
    accumulated = 0.0
    sched = []
    for _ in range(max_periods):
        dep = _monthly_depreciation(asset, book)
        if dep <= _EPS:
            break
        book = round(book - dep, 2)
        accumulated = round(accumulated + dep, 2)
        sched.append({
            "period": period,
            "depreciation": dep,
            "accumulated_depreciation": accumulated,
            "book_value": book,
        })
        period = _add_months(period, 1)
    return sched


async def _accumulated(tenant_id: str, asset_id: str) -> float:
    entries = await db.depreciation_entries.find(
        {"tenant_id": tenant_id, "asset_id": asset_id}, {"_id": 0}
    ).to_list(10000)
    return round(sum(float(e.get("depreciation", 0) or 0) for e in entries), 2)


def _enrich(asset: dict, accumulated: float) -> dict:
    cost = float(asset.get("acquisition_cost", 0) or 0)
    asset = dict(asset)
    asset["accumulated_depreciation"] = round(accumulated, 2)
    asset["book_value"] = round(cost - accumulated, 2)
    return asset


# ─────────────────────────────────────────────────────────────────────
# Şemalar
# ─────────────────────────────────────────────────────────────────────
class AssetIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: str | None = Field(None, max_length=80)
    acquisition_date: str = Field(..., max_length=40)
    acquisition_cost: float = Field(..., gt=0)
    salvage_value: float = Field(0, ge=0)
    useful_life_months: int = Field(..., ge=1, le=1200)
    method: str = Field("straight_line", max_length=30)
    declining_rate: float = Field(0, ge=0, le=100)


# ─────────────────────────────────────────────────────────────────────
# Kıymet register
# ─────────────────────────────────────────────────────────────────────
@router.get("/assets")
async def list_assets(
    status: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if status:
        q["status"] = status
    rows = await db.fixed_assets.find(q, {"_id": 0}).sort("name", 1).to_list(5000)
    enriched = []
    for a in rows:
        enriched.append(_enrich(a, await _accumulated(tenant_id, a["id"])))
    return {"assets": enriched}


@router.post("/assets")
async def create_asset(payload: AssetIn, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _ASSET_ROLES)
    tenant_id = _tenant_of(current_user)
    if payload.method not in _METHODS:
        raise HTTPException(status_code=400, detail="Geçersiz amortisman yöntemi")
    if payload.method == "declining_balance" and payload.declining_rate <= 0:
        raise HTTPException(
            status_code=400, detail="Azalan bakiye için declining_rate > 0 olmalı"
        )
    if payload.salvage_value >= payload.acquisition_cost:
        raise HTTPException(
            status_code=400, detail="Hurda değer maliyetten küçük olmalı"
        )
    now = _now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "name": payload.name.strip(),
        "category": (payload.category or "").strip() or None,
        "acquisition_date": payload.acquisition_date,
        "acquisition_cost": round(float(payload.acquisition_cost), 2),
        "salvage_value": round(float(payload.salvage_value), 2),
        "useful_life_months": payload.useful_life_months,
        "method": payload.method,
        "declining_rate": round(float(payload.declining_rate), 4),
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "created_by": _actor_id(current_user),
    }
    await db.fixed_assets.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"asset": _enrich(doc, 0.0)}


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str, current_user: User = Depends(get_current_user)):
    tenant_id = _tenant_of(current_user)
    a = await db.fixed_assets.find_one(
        {"tenant_id": tenant_id, "id": asset_id}, {"_id": 0}
    )
    if not a:
        raise HTTPException(status_code=404, detail="Kıymet bulunamadı")
    return {"asset": _enrich(a, await _accumulated(tenant_id, asset_id))}


@router.get("/assets/{asset_id}/schedule")
async def asset_schedule(asset_id: str, current_user: User = Depends(get_current_user)):
    tenant_id = _tenant_of(current_user)
    a = await db.fixed_assets.find_one(
        {"tenant_id": tenant_id, "id": asset_id}, {"_id": 0}
    )
    if not a:
        raise HTTPException(status_code=404, detail="Kıymet bulunamadı")
    return {"asset_id": asset_id, "schedule": _build_schedule(a)}


@router.post("/assets/{asset_id}/dispose")
async def dispose_asset(asset_id: str, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _ASSET_ROLES)
    tenant_id = _tenant_of(current_user)
    a = await db.fixed_assets.find_one(
        {"tenant_id": tenant_id, "id": asset_id}, {"_id": 0}
    )
    if not a:
        raise HTTPException(status_code=404, detail="Kıymet bulunamadı")
    if a.get("status") == "disposed":
        return {"asset": _enrich(a, await _accumulated(tenant_id, asset_id))}
    await db.fixed_assets.update_one(
        {"tenant_id": tenant_id, "id": asset_id},
        {"$set": {"status": "disposed", "disposed_at": _now_iso(),
                  "disposed_by": _actor_id(current_user), "updated_at": _now_iso()}},
    )
    a = await db.fixed_assets.find_one(
        {"tenant_id": tenant_id, "id": asset_id}, {"_id": 0}
    )
    return {"asset": _enrich(a, await _accumulated(tenant_id, asset_id))}


# ─────────────────────────────────────────────────────────────────────
# Dönemsel amortisman çalıştırma (idempotent)
# ─────────────────────────────────────────────────────────────────────
@router.get("/entries")
async def list_entries(
    period: str | None = Query(None),
    asset_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if period:
        q["period"] = period
    if asset_id:
        q["asset_id"] = asset_id
    rows = (
        await db.depreciation_entries.find(q, {"_id": 0})
        .sort("period", -1)
        .to_list(10000)
    )
    return {"entries": rows}


@router.post("/run-depreciation")
async def run_depreciation(
    period: str = Query(..., min_length=7, max_length=7),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _ASSET_ROLES)
    tenant_id = _tenant_of(current_user)
    try:
        monthrange(*(int(x) for x in period.split("-")[:2]))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Geçersiz dönem (YYYY-MM)") from exc

    assets = await db.fixed_assets.find(
        {"tenant_id": tenant_id, "status": "active"}, {"_id": 0}
    ).to_list(50000)

    created = 0
    skipped = 0
    total_depreciation = 0.0
    for a in assets:
        if _period_of(a.get("acquisition_date", "9999")) > period:
            skipped += 1
            continue
        existing = await db.depreciation_entries.find_one(
            {"tenant_id": tenant_id, "asset_id": a["id"], "period": period},
            {"_id": 0},
        )
        if existing:
            skipped += 1
            continue
        accumulated = await _accumulated(tenant_id, a["id"])
        book = round(float(a.get("acquisition_cost", 0) or 0) - accumulated, 2)
        dep = _monthly_depreciation(a, book)
        if dep <= _EPS:
            skipped += 1
            continue
        now = _now_iso()
        entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "asset_id": a["id"],
            "asset_name": a.get("name"),
            "period": period,
            "depreciation": dep,
            "book_value_after": round(book - dep, 2),
            "method": a.get("method"),
            "created_at": now,
            "created_by": _actor_id(current_user),
        }
        await db.depreciation_entries.insert_one(dict(entry))
        created += 1
        total_depreciation += dep

    return {
        "period": period,
        "created": created,
        "skipped": skipped,
        "total_depreciation": round(total_depreciation, 2),
    }
