"""
Accounting / Bordro → GL Köprüsü
================================
Kilitlenmiş (locked) bordro çalışmasından (payroll_runs) otomatik, dengeli
yevmiye fişi üretir ve GL'ye gönderir. Çift-post engellenir (dönem/run başına
tek fiş).

Muhasebe mantığı (TR bordro):
  Borç  Ücret Gideri (wage_expense)        = toplam brüt
  Alacak Stopaj/SGK Yükümlülüğü (withholding) = brüt - net  (kesintiler)
  Alacak Personele Borç / Net Ödenecek (net) = toplam net
  → Borç toplam = brüt = Alacak toplam. Dengeli.

Değişmezler:
  * Tenant-scoped; muhasebe seviyesi RBAC.
  * Yalnızca status='locked' bordro post edilebilir (draft fail-closed).
  * Hesap eşlemesi (mapping) tanımlı değilse fail-closed (409).
  * post_journal_entry idempotency_key=payroll:{run_id} → ikinci post yeni fiş
    yaratmaz, mevcut fişi döner.
  * GL posting çekirdeği shared_kernel.gl_posting'ten — cross-domain import yok.
"""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User
from shared_kernel.gl_posting import GLPostingError, post_journal_entry

logger = logging.getLogger("domains.accounting.payroll_gl")

router = APIRouter(prefix="/api/payroll-gl", tags=["Accounting / Payroll GL"])

_GL_ROLES = {"super_admin", "admin", "accountant", "finance"}
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


def _idem_key(run_id: str) -> str:
    return f"payroll:{run_id}"


class MappingIn(BaseModel):
    wage_expense_code: str = Field(..., min_length=1, max_length=40)
    withholding_payable_code: str = Field(..., min_length=1, max_length=40)
    net_payable_code: str = Field(..., min_length=1, max_length=40)


@router.get("/mapping")
async def get_mapping(current_user: User = Depends(get_current_user)):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    doc = await db.payroll_gl_mapping.find_one({"tenant_id": tenant_id}, {"_id": 0})
    return {"mapping": doc}


@router.put("/mapping")
async def set_mapping(payload: MappingIn, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)

    codes = [
        payload.wage_expense_code.strip(),
        payload.withholding_payable_code.strip(),
        payload.net_payable_code.strip(),
    ]
    found = await db.gl_accounts.find(
        {"tenant_id": tenant_id, "code": {"$in": codes}}, {"_id": 0, "code": 1}
    ).to_list(100)
    found_codes = {a["code"] for a in found}
    missing = [c for c in codes if c not in found_codes]
    if missing:
        raise HTTPException(
            status_code=400, detail=f"Hesap planında olmayan kod(lar): {missing}"
        )

    now = _now_iso()
    await db.payroll_gl_mapping.update_one(
        {"tenant_id": tenant_id},
        {"$set": {
            "tenant_id": tenant_id,
            "wage_expense_code": codes[0],
            "withholding_payable_code": codes[1],
            "net_payable_code": codes[2],
            "updated_at": now,
            "updated_by": _actor_id(current_user),
        }},
        upsert=True,
    )
    doc = await db.payroll_gl_mapping.find_one({"tenant_id": tenant_id}, {"_id": 0})
    return {"mapping": doc}


async def _find_posted_entry(tenant_id: str, run_id: str) -> dict | None:
    return await db.gl_journal_entries.find_one(
        {"tenant_id": tenant_id, "idempotency_key": _idem_key(run_id)}, {"_id": 0}
    )


@router.get("/{run_id}")
async def posting_status(run_id: str, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    entry = await _find_posted_entry(tenant_id, run_id)
    return {"run_id": run_id, "posted": bool(entry), "entry": entry}


@router.post("/{run_id}/post")
async def post_payroll(run_id: str, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)

    run = await db.payroll_runs.find_one(
        {"tenant_id": tenant_id, "id": run_id}, {"_id": 0}
    )
    if not run:
        raise HTTPException(status_code=404, detail="Bordro çalışması bulunamadı")
    if run.get("status") != "locked":
        raise HTTPException(
            status_code=409,
            detail="Yalnızca kilitli (locked) bordro GL'ye gönderilebilir",
        )

    mapping = await db.payroll_gl_mapping.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if not mapping:
        raise HTTPException(
            status_code=409,
            detail="Bordro hesap eşlemesi tanımlı değil (PUT /api/payroll-gl/mapping)",
        )

    summary = run.get("summary") or {}
    gross = round(float(summary.get("total_gross", 0) or 0), 2)
    net = round(float(summary.get("total_net", 0) or 0), 2)
    if gross <= _EPS:
        raise HTTPException(status_code=400, detail="Brüt tutar sıfır; post edilemez")
    if net > gross + _EPS:
        raise HTTPException(status_code=400, detail="Net brütten büyük olamaz")
    withholding = round(gross - net, 2)

    lines = [
        {"account_code": mapping["wage_expense_code"], "debit": gross,
         "memo": "Ücret gideri"},
        {"account_code": mapping["net_payable_code"], "credit": net,
         "memo": "Personele net ödenecek"},
    ]
    if withholding > _EPS:
        lines.append({
            "account_code": mapping["withholding_payable_code"],
            "credit": withholding, "memo": "Stopaj/SGK yükümlülüğü",
        })

    period = run.get("period_month")
    try:
        entry = await post_journal_entry(
            db,
            tenant_id,
            date=f"{period}-01" if period else None,
            memo=f"Bordro tahakkuk ({period})",
            lines=lines,
            source="payroll",
            source_ref=run_id,
            actor=_actor_id(current_user),
            idempotency_key=_idem_key(run_id),
        )
    except GLPostingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"run_id": run_id, "period_month": period, "entry": entry}
