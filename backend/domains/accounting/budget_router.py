"""
Accounting / Bütçe & Sapma Analizi
==================================
Dönem (YYYY-MM) ve kategori bazlı bütçe girişi; gerçekleşen (cash_flow tek
kaynak: expense/income) ile bütçe-gerçekleşen sapma motoru.

Değişmezler:
  * Tenant-scoped; mutasyonlar muhasebe seviyesi RBAC.
  * Bütçe upsert (tenant+period+category+kind) tekil; çift kayıt yok.
  * Gerçekleşen cash_flow'dan SUNUCUDA hesaplanır (kind→transaction_type:
    expense→expense, revenue→income). Uydurma sabit veri YOK.
  * Sapma yorumu kind'e göre: expense'te actual>budget = olumsuz (aşım),
    revenue'da actual>budget = olumlu.
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

logger = logging.getLogger("domains.accounting.budget")

router = APIRouter(prefix="/api/budget", tags=["Accounting / Budget"])

_BUDGET_ROLES = {"super_admin", "admin", "accountant"}
_READ_ROLES = {"super_admin", "admin", "accountant", "supervisor"}

_KIND_TO_TXN = {"expense": "expense", "revenue": "income"}


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


def _period_range(period: str) -> tuple[str, str]:
    """YYYY-MM → (gte ISO ay başı, lt ISO sonraki ay başı)."""
    try:
        year, month = (int(x) for x in period.split("-")[:2])
        last = monthrange(year, month)[1]
        start = f"{year:04d}-{month:02d}-01T00:00:00"
        end = f"{year:04d}-{month:02d}-{last:02d}T23:59:59.999999"
        return start, end
    except (ValueError, IndexError) as exc:
        raise HTTPException(status_code=400, detail="Geçersiz dönem (YYYY-MM)") from exc


# ─────────────────────────────────────────────────────────────────────
# Şemalar
# ─────────────────────────────────────────────────────────────────────
class BudgetIn(BaseModel):
    period: str = Field(..., min_length=7, max_length=7)  # YYYY-MM
    category: str = Field(..., min_length=1, max_length=80)
    kind: str = Field("expense", max_length=20)
    budget_amount: float = Field(..., ge=0)
    notes: str | None = Field(None, max_length=500)


# ─────────────────────────────────────────────────────────────────────
# Bütçe CRUD
# ─────────────────────────────────────────────────────────────────────
@router.get("/budgets")
async def list_budgets(
    period: str | None = Query(None),
    kind: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if period:
        q["period"] = period
    if kind:
        q["kind"] = kind
    rows = (
        await db.finance_budgets.find(q, {"_id": 0})
        .sort("category", 1)
        .to_list(5000)
    )
    return {"budgets": rows}


@router.post("/budgets")
async def upsert_budget(
    payload: BudgetIn, current_user: User = Depends(get_current_user)
):
    _require_role(current_user, _BUDGET_ROLES)
    tenant_id = _tenant_of(current_user)
    if payload.kind not in _KIND_TO_TXN:
        raise HTTPException(status_code=400, detail="Geçersiz kind (expense|revenue)")
    _period_range(payload.period)  # validate format

    category = payload.category.strip()
    now = _now_iso()
    key = {
        "tenant_id": tenant_id,
        "period": payload.period,
        "category": category,
        "kind": payload.kind,
    }
    await db.finance_budgets.update_one(
        key,
        {
            "$set": {
                **key,
                "budget_amount": round(float(payload.budget_amount), 2),
                "notes": (payload.notes or "").strip() or None,
                "updated_at": now,
                "updated_by": _actor_id(current_user),
            },
            "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
        },
        upsert=True,
    )
    doc = await db.finance_budgets.find_one(key, {"_id": 0})
    return {"budget": doc}


@router.delete("/budgets/{budget_id}")
async def delete_budget(budget_id: str, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _BUDGET_ROLES)
    tenant_id = _tenant_of(current_user)
    res = await db.finance_budgets.delete_one(
        {"tenant_id": tenant_id, "id": budget_id}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bütçe kaydı bulunamadı")
    return {"ok": True, "id": budget_id}


# ─────────────────────────────────────────────────────────────────────
# Bütçe vs gerçekleşen
# ─────────────────────────────────────────────────────────────────────
@router.get("/vs-actual")
async def budget_vs_actual(
    period: str = Query(..., min_length=7, max_length=7),
    kind: str = Query("expense"),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    if kind not in _KIND_TO_TXN:
        raise HTTPException(status_code=400, detail="Geçersiz kind (expense|revenue)")
    start, end = _period_range(period)

    budgets = await db.finance_budgets.find(
        {"tenant_id": tenant_id, "period": period, "kind": kind}, {"_id": 0}
    ).to_list(5000)
    budget_by_cat = {b["category"]: float(b.get("budget_amount", 0) or 0) for b in budgets}

    txn_type = _KIND_TO_TXN[kind]
    flows = await db.cash_flow.find(
        {
            "tenant_id": tenant_id,
            "transaction_type": txn_type,
            "date": {"$gte": start, "$lte": end},
        },
        {"_id": 0},
    ).to_list(100000)
    actual_by_cat: dict[str, float] = {}
    for f in flows:
        cat = f.get("category") or "uncategorized"
        actual_by_cat[cat] = actual_by_cat.get(cat, 0.0) + float(f.get("amount", 0) or 0)

    rows = []
    tot_budget = tot_actual = 0.0
    for cat in sorted(set(budget_by_cat) | set(actual_by_cat)):
        bud = round(budget_by_cat.get(cat, 0.0), 2)
        act = round(actual_by_cat.get(cat, 0.0), 2)
        tot_budget += bud
        tot_actual += act
        # variance: expense'te (bütçe-fiili) tasarruf pozitif; revenue'da (fiili-bütçe).
        if kind == "expense":
            variance = round(bud - act, 2)
            base = bud
        else:
            variance = round(act - bud, 2)
            base = bud
        variance_pct = round(variance / base * 100, 2) if base > 0 else None
        rows.append({
            "category": cat,
            "budget": bud,
            "actual": act,
            "variance": variance,
            "variance_pct": variance_pct,
            "favorable": variance >= 0,
        })

    rows.sort(key=lambda r: abs(r["variance"]), reverse=True)
    if kind == "expense":
        tot_var = round(tot_budget - tot_actual, 2)
    else:
        tot_var = round(tot_actual - tot_budget, 2)
    return {
        "period": period,
        "kind": kind,
        "data_available": bool(rows),
        "rows": rows,
        "totals": {
            "budget": round(tot_budget, 2),
            "actual": round(tot_actual, 2),
            "variance": tot_var,
            "variance_pct": (
                round(tot_var / tot_budget * 100, 2) if tot_budget > 0 else None
            ),
            "favorable": tot_var >= 0,
        },
    }
