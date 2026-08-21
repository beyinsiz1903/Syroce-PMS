"""
Accounting / Genel Muhasebe (GL) — Hesap planı + çift-taraflı yevmiye + mizan
=============================================================================
Hesap planı (chart of accounts) yönetimi, dengeli yevmiye fişi gönderimi ve
mizan (trial balance) raporu. Posting çekirdeği shared_kernel.gl_posting'tedir.

Tüm uçlar tenant-scoped; mutasyonlar muhasebe seviyesi RBAC. PII/secret loglanmaz.
"""

import asyncio
import io
import logging
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from core.audit import log_audit_event
from core.database import db
from core.integrations.invoice_gl_bridge import (
    InvoiceGLBridgeError,
    get_incoming_invoice_gl_link,
    post_incoming_invoice_to_gl,
)
from core.integrations.operational_gl_bridge import (
    DEFAULT_MAPPING,
    OperationalGLBridgeError,
    get_operational_mapping,
    post_night_audit_daily_to_gl,
)
from core.security import get_current_user
from core.tenant_db import get_system_db
from core.utils import create_excel_workbook, excel_response
from models.schemas import User
from shared_kernel.gl_periods import GLPeriodError, ensure_calendar_year_periods
from shared_kernel.gl_posting import (
    ACCOUNT_TYPES,
    GLPostingError,
    compute_balance_sheet,
    compute_income_statement,
    compute_trial_balance,
    normal_balance,
    post_journal_entry,
)
from shared_kernel.pos_idem import ensure_compound_unique

logger = logging.getLogger("domains.accounting.gl")

router = APIRouter(prefix="/api/gl", tags=["Accounting / GL"])
_system_db = get_system_db()

_GL_ROLES = {"super_admin", "admin", "finance"}
_READ_ROLES = {"super_admin", "admin", "finance", "supervisor"}
_REOPEN_ROLES = {"super_admin", "admin"}

_DEFAULT_CHART_OF_ACCOUNTS = (
    ("100", "Kasa", "asset"),
    ("102", "Bankalar", "asset"),
    ("108", "Diğer Hazır Değerler (Kredi Kartı)", "asset"),
    ("120", "Alıcılar", "asset"),
    ("150", "İlk Madde ve Malzeme", "asset"),
    ("153", "Ticari Mallar", "asset"),
    ("257", "Birikmiş Amortismanlar", "asset", "credit"),
    ("320", "Satıcılar", "liability"),
    ("335", "Personele Borçlar", "liability"),
    ("336", "Diğer Çeşitli Borçlar", "liability"),
    ("360", "Ödenecek Vergi ve Fonlar", "liability"),
    ("391", "Hesaplanan KDV", "liability"),
    ("570", "Geçmiş Yıllar Kârları", "equity"),
    ("580", "Geçmiş Yıllar Zararları", "equity", "debit"),
    ("590", "Dönem Net Kârı", "equity"),
    ("591", "Dönem Net Zararı", "equity", "debit"),
    ("600", "Yurtiçi Satışlar (Oda/F&B Geliri)", "revenue"),
    ("646", "Kambiyo Kârları", "revenue"),
    ("656", "Kambiyo Zararları", "expense"),
    ("690", "Dönem Kârı veya Zararı", "equity"),
    ("740", "Hizmet Üretim Maliyeti", "expense"),
    ("770", "Genel Yönetim Giderleri", "expense"),
)

_DEFAULT_MONETARY_ACCOUNTS = {"102", "108", "120", "320", "335", "336"}


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


# ─────────────────────────────────────────────────────────────────────
# Mali dönemler
# ─────────────────────────────────────────────────────────────────────
class FiscalYearIn(BaseModel):
    fiscal_year: int = Field(..., ge=2000, le=2100)


class PeriodActionIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class YearEndCloseIn(BaseModel):
    fiscal_year: int = Field(..., ge=2000, le=2099)
    reason: str = Field(..., min_length=3, max_length=500)


@router.get("/periods")
async def list_periods(
    fiscal_year: int | None = Query(None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    query: dict = {"tenant_id": tenant_id}
    if fiscal_year is not None:
        query["fiscal_year"] = fiscal_year
    rows = await db.gl_periods.find(query, {"_id": 0}).sort("start_date", -1).to_list(1200)
    return {"periods": rows}


@router.post("/periods/initialize")
async def initialize_periods(payload: FiscalYearIn, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    try:
        await ensure_calendar_year_periods(db, tenant_id, payload.fiscal_year, actor=_actor_id(current_user))
    except GLPeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rows = await db.gl_periods.find(
        {"tenant_id": tenant_id, "fiscal_year": payload.fiscal_year},
        {"_id": 0},
    ).sort("period_no", 1).to_list(12)
    return {"periods": rows, "created_or_existing": len(rows)}


@router.post("/periods/{period_id}/close")
async def close_period(
    period_id: str,
    payload: PeriodActionIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    period = await db.gl_periods.find_one({"tenant_id": tenant_id, "id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(status_code=404, detail="Mali dönem bulunamadı")
    if period.get("status") == "closed":
        return {"period": period, "already_closed": True}
    earlier_open = await db.gl_periods.find_one(
        {
            "tenant_id": tenant_id,
            "fiscal_year": period["fiscal_year"],
            "period_no": {"$lt": period["period_no"]},
            "status": "open",
        },
        {"_id": 0, "name": 1},
    )
    if earlier_open:
        raise HTTPException(status_code=409, detail=f"Önce {earlier_open.get('name')} dönemi kapatılmalıdır")
    trial = await compute_trial_balance(db, tenant_id, as_of=period["end_date"])
    if not trial.get("totals", {}).get("balanced", False):
        raise HTTPException(status_code=409, detail="Mizan dengeli olmadığı için dönem kapatılamaz")
    now = _now_iso()
    result = await db.gl_periods.update_one(
        {"tenant_id": tenant_id, "id": period_id, "status": "open"},
        {
            "$set": {
                "status": "closed",
                "closed_at": now,
                "closed_by": _actor_id(current_user),
                "close_reason": payload.reason.strip(),
                "closing_trial_balance": trial["totals"],
            }
        },
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=409, detail="Dönem durumu eşzamanlı olarak değişti")
    updated = await db.gl_periods.find_one({"tenant_id": tenant_id, "id": period_id}, {"_id": 0})
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gl_period_closed",
        entity_type="gl_period",
        entity_id=period_id,
        details=f"{period.get('name')} mali dönemi kapatıldı",
        before_value={"status": "open"},
        after_value={"status": "closed", "reason": payload.reason.strip()},
        db=db,
    )
    return {"period": updated, "already_closed": False}


@router.post("/periods/{period_id}/reopen")
async def reopen_period(
    period_id: str,
    payload: PeriodActionIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _REOPEN_ROLES)
    tenant_id = _tenant_of(current_user)
    period = await db.gl_periods.find_one({"tenant_id": tenant_id, "id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(status_code=404, detail="Mali dönem bulunamadı")
    if period.get("status") == "open":
        return {"period": period, "already_open": True}
    later_closed = await db.gl_periods.find_one(
        {
            "tenant_id": tenant_id,
            "fiscal_year": period["fiscal_year"],
            "period_no": {"$gt": period["period_no"]},
            "status": "closed",
        },
        {"_id": 0, "name": 1},
    )
    if later_closed:
        raise HTTPException(status_code=409, detail=f"Önce {later_closed.get('name')} dönemi yeniden açılmalıdır")
    now = _now_iso()
    result = await db.gl_periods.update_one(
        {"tenant_id": tenant_id, "id": period_id, "status": "closed"},
        {
            "$set": {
                "status": "open",
                "reopened_at": now,
                "reopened_by": _actor_id(current_user),
                "reopen_reason": payload.reason.strip(),
            },
            "$push": {
                "reopen_history": {
                    "at": now,
                    "by": _actor_id(current_user),
                    "reason": payload.reason.strip(),
                }
            },
        },
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=409, detail="Dönem durumu eşzamanlı olarak değişti")
    updated = await db.gl_periods.find_one({"tenant_id": tenant_id, "id": period_id}, {"_id": 0})
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gl_period_reopened",
        entity_type="gl_period",
        entity_id=period_id,
        details=f"{period.get('name')} mali dönemi yeniden açıldı",
        before_value={"status": "closed"},
        after_value={"status": "open", "reason": payload.reason.strip()},
        db=db,
        severity="warning",
    )
    return {"period": updated, "already_open": False}


@router.get("/year-end/{fiscal_year}")
async def get_year_end_status(
    fiscal_year: int,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    closure = await db.gl_year_end_closures.find_one(
        {"tenant_id": tenant_id, "fiscal_year": fiscal_year},
        {"_id": 0},
    )
    return {"fiscal_year": fiscal_year, "closed": closure is not None, "closure": closure}


@router.post("/year-end/close")
async def close_fiscal_year(
    payload: YearEndCloseIn,
    current_user: User = Depends(get_current_user),
):
    """Close P&L into 590/591 and record continuous-ledger opening carry-forward."""
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    existing = await db.gl_year_end_closures.find_one(
        {"tenant_id": tenant_id, "fiscal_year": payload.fiscal_year},
        {"_id": 0},
    )
    if existing:
        return {"closure": existing, "already_closed": True}

    await ensure_calendar_year_periods(db, tenant_id, payload.fiscal_year, actor=_actor_id(current_user))
    periods = await db.gl_periods.find(
        {"tenant_id": tenant_id, "fiscal_year": payload.fiscal_year},
        {"_id": 0},
    ).sort("period_no", 1).to_list(12)
    periods_by_no = {int(period["period_no"]): period for period in periods}
    if len(periods_by_no) != 12:
        raise HTTPException(status_code=409, detail="Mali yılın 12 dönemi eksiksiz oluşturulmalıdır")
    earlier_open = [period["name"] for no, period in periods_by_no.items() if no < 12 and period.get("status") != "closed"]
    if earlier_open:
        raise HTTPException(status_code=409, detail=f"Önce {earlier_open[0]} dönemi kapatılmalıdır")
    december = periods_by_no[12]
    if december.get("status") != "open":
        raise HTTPException(status_code=409, detail="Aralık dönemi kapanış fişi için açık olmalıdır")

    accounts = await db.gl_accounts.find({"tenant_id": tenant_id, "active": True}, {"_id": 0}).to_list(5000)
    account_codes = {account["code"] for account in accounts}
    required_codes = {"570", "580", "590", "591", "690"}
    missing_codes = sorted(required_codes - account_codes)
    if missing_codes:
        raise HTTPException(
            status_code=409,
            detail=f"Yıl sonu için eksik hesap kodları: {', '.join(missing_codes)}. Standart hesap planını hazırlayın.",
        )

    year_start = f"{payload.fiscal_year}-01-01"
    year_end = f"{payload.fiscal_year}-12-31"
    income = await compute_income_statement(db, tenant_id, start=year_start, end=year_end)
    pre_close_trial = await compute_trial_balance(db, tenant_id, as_of=year_end)
    pre_close_by_code = {row["account_code"]: row for row in pre_close_trial["rows"]}
    lines: list[dict] = []
    prior_profit = pre_close_by_code.get("590", {})
    if prior_profit.get("credit_balance_minor"):
        amount = prior_profit["credit_balance"]
        lines.extend(
            [
                {"account_code": "590", "debit": amount, "memo": "Önceki dönem kârı devri"},
                {"account_code": "570", "credit": amount, "memo": "Geçmiş yıllar kârları"},
            ]
        )
    prior_loss = pre_close_by_code.get("591", {})
    if prior_loss.get("debit_balance_minor"):
        amount = prior_loss["debit_balance"]
        lines.extend(
            [
                {"account_code": "591", "credit": amount, "memo": "Önceki dönem zararı devri"},
                {"account_code": "580", "debit": amount, "memo": "Geçmiş yıllar zararları"},
            ]
        )
    for row in income["revenue"]:
        amount = row["amount"]
        if amount > 0:
            lines.append({"account_code": row["account_code"], "debit": amount, "memo": "Gelir hesabı kapanışı"})
        elif amount < 0:
            lines.append({"account_code": row["account_code"], "credit": abs(amount), "memo": "Gelir hesabı kapanışı"})
    for row in income["expenses"]:
        amount = row["amount"]
        if amount > 0:
            lines.append({"account_code": row["account_code"], "credit": amount, "memo": "Gider hesabı kapanışı"})
        elif amount < 0:
            lines.append({"account_code": row["account_code"], "debit": abs(amount), "memo": "Gider hesabı kapanışı"})

    net_income = income["totals"]["net_income"]
    if net_income > 0:
        lines.extend(
            [
                {"account_code": "690", "credit": net_income, "memo": "Dönem kârı"},
                {"account_code": "690", "debit": net_income, "memo": "Net kâr devri"},
                {"account_code": "590", "credit": net_income, "memo": "Dönem net kârı"},
            ]
        )
    elif net_income < 0:
        loss = abs(net_income)
        lines.extend(
            [
                {"account_code": "690", "debit": loss, "memo": "Dönem zararı"},
                {"account_code": "690", "credit": loss, "memo": "Net zarar devri"},
                {"account_code": "591", "debit": loss, "memo": "Dönem net zararı"},
            ]
        )

    closing_entry = None
    if lines:
        try:
            closing_entry = await post_journal_entry(
                db,
                tenant_id,
                date=year_end,
                memo=f"{payload.fiscal_year} mali yıl kapanışı",
                lines=lines,
                source="year_end_close",
                source_ref=str(payload.fiscal_year),
                actor=_actor_id(current_user),
                idempotency_key=f"gl-year-end-close:{payload.fiscal_year}",
            )
        except GLPostingError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    await close_period(
        december["id"],
        PeriodActionIn(reason=payload.reason.strip()),
        current_user=current_user,
    )
    await ensure_calendar_year_periods(db, tenant_id, payload.fiscal_year + 1, actor=_actor_id(current_user))
    closing_trial = await compute_trial_balance(db, tenant_id, as_of=year_end)
    opening_balances = [
        {
            "account_code": row["account_code"],
            "account_name": row["account_name"],
            "account_type": row["account_type"],
            "debit_balance_minor": row["debit_balance_minor"],
            "credit_balance_minor": row["credit_balance_minor"],
        }
        for row in closing_trial["rows"]
        if row.get("account_type") in {"asset", "liability", "equity"}
        and (row["debit_balance_minor"] or row["credit_balance_minor"])
    ]
    now = _now_iso()
    closure = {
        "id": f"{tenant_id}:{payload.fiscal_year}",
        "tenant_id": tenant_id,
        "fiscal_year": payload.fiscal_year,
        "status": "closed",
        "closed_at": now,
        "closed_by": _actor_id(current_user),
        "reason": payload.reason.strip(),
        "closing_entry_id": closing_entry.get("id") if closing_entry else None,
        "closing_entry_no": closing_entry.get("entry_no") if closing_entry else None,
        "net_income_minor": income["totals"]["net_income_minor"],
        "opening_fiscal_year": payload.fiscal_year + 1,
        "opening_carry_forward_mode": "continuous_ledger",
        "opening_balances": opening_balances,
    }
    try:
        await db.gl_year_end_closures.insert_one(dict(closure))
    except DuplicateKeyError:
        closure = await db.gl_year_end_closures.find_one(
            {"tenant_id": tenant_id, "fiscal_year": payload.fiscal_year},
            {"_id": 0},
        )
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gl_fiscal_year_closed",
        entity_type="gl_year_end_closure",
        entity_id=closure["id"],
        details=f"{payload.fiscal_year} mali yılı kapatıldı ve açılış bakiyeleri devredildi",
        after_value={
            "closing_entry_no": closure.get("closing_entry_no"),
            "net_income_minor": closure["net_income_minor"],
            "opening_fiscal_year": closure["opening_fiscal_year"],
            "opening_balance_count": len(closure["opening_balances"]),
        },
        db=db,
    )
    return {"closure": closure, "already_closed": False}


# ─────────────────────────────────────────────────────────────────────
# Hesap planı (Chart of Accounts)
# ─────────────────────────────────────────────────────────────────────
class AccountIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., max_length=20)
    parent_code: str | None = Field(None, max_length=40)
    active: bool = True
    normal_balance: Literal["debit", "credit"] | None = None
    monetary: bool = False


class AccountUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    parent_code: str | None = Field(None, max_length=40)
    active: bool | None = None
    normal_balance: Literal["debit", "credit"] | None = None
    monetary: bool | None = None


@router.get("/accounts")
async def list_accounts(
    include_inactive: bool = Query(True),
    type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if not include_inactive:
        q["active"] = True
    if type:
        q["type"] = type
    rows = await db.gl_accounts.find(q, {"_id": 0}).sort("code", 1).to_list(5000)
    return {"accounts": rows}


@router.post("/accounts")
async def create_account(payload: AccountIn, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    if payload.type not in ACCOUNT_TYPES:
        raise HTTPException(status_code=400, detail="Geçersiz hesap tipi")
    code = payload.code.strip()
    existing = await db.gl_accounts.find_one({"tenant_id": tenant_id, "code": code}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Bu kod ile hesap zaten var")
    now = _now_iso()
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "code": code,
        "name": payload.name.strip(),
        "type": payload.type,
        "normal_balance": payload.normal_balance or normal_balance(payload.type),
        "parent_code": (payload.parent_code or "").strip() or None,
        "active": payload.active,
        "monetary": payload.monetary,
        "created_at": now,
        "updated_at": now,
        "created_by": _actor_id(current_user),
    }
    await db.gl_accounts.insert_one(dict(doc))
    doc.pop("_id", None)
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gl_account_created",
        entity_type="gl_account",
        entity_id=doc["id"],
        details=f"{code} hesap kodu oluşturuldu",
        after_value={key: doc.get(key) for key in ("code", "name", "type", "parent_code", "active", "normal_balance", "monetary")},
        db=db,
    )
    return {"account": doc}


@router.post("/accounts/initialize")
async def initialize_chart_of_accounts(current_user: User = Depends(get_current_user)):
    """Create the tenant's standard TDHP accounts without overwriting custom data."""
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    await ensure_compound_unique(
        db.gl_accounts,
        [("tenant_id", 1), ("code", 1)],
        name="ux_gl_accounts_tenant_code",
    )
    created = 0
    for account_definition in _DEFAULT_CHART_OF_ACCOUNTS:
        code, name, account_type, *balance_override = account_definition
        now = _now_iso()
        existing_account = await db.gl_accounts.find_one(
            {"tenant_id": tenant_id, "code": code},
            {"_id": 0, "monetary": 1},
        )
        result = await db.gl_accounts.update_one(
            {"tenant_id": tenant_id, "code": code},
            {
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "code": code,
                    "name": name,
                    "type": account_type,
                    "normal_balance": balance_override[0] if balance_override else normal_balance(account_type),
                    "parent_code": None,
                    "active": True,
                    "monetary": code in _DEFAULT_MONETARY_ACCOUNTS,
                    "created_at": now,
                    "updated_at": now,
                    "created_by": _actor_id(current_user),
                }
            },
            upsert=True,
        )
        if getattr(result, "upserted_id", None) is not None:
            created += 1
        elif existing_account is not None and "monetary" not in existing_account:
            await db.gl_accounts.update_one(
                {"tenant_id": tenant_id, "code": code},
                {"$set": {"monetary": code in _DEFAULT_MONETARY_ACCOUNTS, "updated_at": now}},
            )
    mapping_created = False
    existing_mapping = await db.payroll_gl_mapping.find_one(
        {"tenant_id": tenant_id},
        {"_id": 0, "tenant_id": 1},
    )
    if not existing_mapping:
        now = _now_iso()
        mapping_result = await db.payroll_gl_mapping.update_one(
            {"tenant_id": tenant_id},
            {
                "$setOnInsert": {
                    "tenant_id": tenant_id,
                    "wage_expense_code": "770",
                    "withholding_payable_code": "360",
                    "net_payable_code": "335",
                    "updated_at": now,
                    "updated_by": _actor_id(current_user),
                }
            },
            upsert=True,
        )
        mapping_created = getattr(mapping_result, "upserted_id", None) is not None
    response = {
        "created": created,
        "total": len(_DEFAULT_CHART_OF_ACCOUNTS),
        "payroll_mapping_created": mapping_created,
    }
    if created or mapping_created:
        await log_audit_event(
            tenant_id=tenant_id,
            user_id=_actor_id(current_user),
            action="gl_chart_initialized",
            entity_type="gl_chart_of_accounts",
            entity_id=tenant_id,
            details="Standart hesap planı ve varsayılan bordro eşlemesi hazırlandı",
            after_value=response,
            db=db,
        )
    return response


@router.put("/accounts/{code}")
async def update_account(code: str, payload: AccountUpdate, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    before = await db.gl_accounts.find_one({"tenant_id": tenant_id, "code": code}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Hesap bulunamadı")
    updates = dict(payload.model_dump(exclude_unset=True))
    if "name" in updates and updates["name"]:
        updates["name"] = updates["name"].strip()
    if "normal_balance" in updates and updates["normal_balance"] is None:
        updates["normal_balance"] = normal_balance(before["type"])
    if not updates:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")
    updates["updated_at"] = _now_iso()
    res = await db.gl_accounts.update_one({"tenant_id": tenant_id, "code": code}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=409, detail="Hesap eşzamanlı olarak değişti")
    doc = await db.gl_accounts.find_one({"tenant_id": tenant_id, "code": code}, {"_id": 0})
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gl_account_updated",
        entity_type="gl_account",
        entity_id=before.get("id") or code,
        details=f"{code} hesap kodu güncellendi",
        before_value={key: before.get(key) for key in ("name", "parent_code", "active", "normal_balance", "monetary")},
        after_value={key: doc.get(key) for key in ("name", "parent_code", "active", "normal_balance", "monetary")},
        db=db,
    )
    return {"account": doc}


# ─────────────────────────────────────────────────────────────────────
# Yevmiye fişleri
# ─────────────────────────────────────────────────────────────────────
class JournalLineIn(BaseModel):
    account_code: str = Field(..., min_length=1, max_length=40)
    debit: Decimal = Field(Decimal("0"), ge=0, max_digits=18)
    credit: Decimal = Field(Decimal("0"), ge=0, max_digits=18)
    memo: str | None = Field(None, max_length=300)
    currency: str | None = Field(None, min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    foreign_amount: Decimal | None = Field(None, gt=0, max_digits=18)
    exchange_rate: Decimal | None = Field(None, gt=0, max_digits=18)


class JournalIn(BaseModel):
    date: str | None = Field(None, max_length=40)
    memo: str = Field(..., min_length=1, max_length=500)
    lines: list[JournalLineIn] = Field(..., min_length=2, max_length=500)
    # This public endpoint is exclusively for operator-entered vouchers.
    # Domain bridges post with trusted sources by calling the shared kernel;
    # accepting an arbitrary source here would let a client bypass manual-post
    # controls and impersonate an integration.
    source: Literal["manual"] = "manual"
    source_ref: str | None = Field(None, max_length=120)
    idempotency_key: str | None = Field(None, max_length=120)


class JournalReversalIn(BaseModel):
    date: str | None = Field(None, max_length=40)
    reason: str = Field(..., min_length=3, max_length=500)
    idempotency_key: str = Field(..., min_length=8, max_length=120)


class FXRevaluationIn(BaseModel):
    date: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$")
    currency: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    closing_rate: Decimal = Field(..., gt=0, max_digits=18)
    gain_account_code: str = Field("646", min_length=1, max_length=40)
    loss_account_code: str = Field("656", min_length=1, max_length=40)


class OperationalMappingIn(BaseModel):
    enabled: bool = False
    auto_night_audit: bool = True
    auto_pos: bool = True
    receivable_account_code: str = Field("120", min_length=1, max_length=40)
    revenue_account_code: str = Field("600", min_length=1, max_length=40)
    tax_account_code: str = Field("391", min_length=1, max_length=40)
    cash_account_code: str = Field("100", min_length=1, max_length=40)
    card_account_code: str = Field("108", min_length=1, max_length=40)
    bank_account_code: str = Field("102", min_length=1, max_length=40)


class NilveraIncomingGLPostIn(BaseModel):
    purchase_account_code: str = Field(..., description="GL account for expense/asset")
    vat_account_code: str = Field(..., description="GL account for deductible VAT")
    payable_account_code: str = Field(..., description="GL account for vendor payable")


class NilveraOutgoingGLPostIn(BaseModel):
    revenue_account_code: str = Field(..., description="GL account for revenue/sales")
    receivable_account_code: str = Field(..., description="GL account for customer receivable")
    discount_account_code: str | None = Field(None, description="GL account for sales discounts")

    vat_account_code: str | None = Field(None, description="Fallback GL account for calculated VAT")
    accommodation_tax_account_code: str | None = Field(None, description="Fallback GL account for Accommodation Tax (0059)")

    vat_accounts_by_rate: dict[str, str] = Field(default_factory=dict, description="e.g. {'10': '391.10', '20': '391.20'}")
    accommodation_tax_accounts_by_rate: dict[str, str] = Field(default_factory=dict, description="e.g. {'1': '360.01', '2': '360.02'}")

@router.get("/journal")
async def list_journal(
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    q: dict = {"tenant_id": tenant_id}
    if start or end:
        date_q: dict = {}
        if start:
            date_q["$gte"] = start
        if end:
            date_q["$lte"] = end
        q["date"] = date_q
    rows = await db.gl_journal_entries.find(q, {"_id": 0}).sort("date", -1).to_list(limit)
    return {"entries": rows}


@router.get("/journal/{entry_id}")
async def get_journal(entry_id: str, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    doc = await db.gl_journal_entries.find_one({"tenant_id": tenant_id, "id": entry_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Fiş bulunamadı")
    return {"entry": doc}


@router.get("/sequence-audit")
async def sequence_audit(
    fiscal_year: int | None = Query(None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
):
    """Expose posted/void/reserved journal ordinals without mutating them."""
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    query: dict = {"tenant_id": tenant_id}
    if fiscal_year is not None:
        query["fiscal_year"] = fiscal_year
    rows = await db.gl_sequence_reservations.find(query, {"_id": 0}).sort(
        [("fiscal_year", -1), ("sequence", 1)]
    ).to_list(100000)
    counters = await db.gl_counters.find(query, {"_id": 0}).to_list(1000)
    counts = {"posted": 0, "void": 0, "reserved": 0}
    sequences_by_year: dict[int, set[int]] = {}
    for row in rows:
        status = row.get("status", "reserved")
        counts[status] = counts.get(status, 0) + 1
        sequences_by_year.setdefault(int(row["fiscal_year"]), set()).add(int(row["sequence"]))
    missing_by_year: dict[str, list[int]] = {}
    missing_count = 0
    for counter in counters:
        year = int(counter["fiscal_year"])
        allocated = int(counter.get("value") or 0)
        present = sequences_by_year.get(year, set())
        missing = [number for number in range(1, allocated + 1) if number not in present]
        if missing:
            missing_count += len(missing)
            missing_by_year[str(year)] = missing[:100]
    return {
        "fiscal_year": fiscal_year,
        "reservations": rows,
        "totals": {"count": len(rows), **counts, "missing": missing_count},
        "missing_sequences": missing_by_year,
        "healthy": counts.get("reserved", 0) == 0 and missing_count == 0,
    }


@router.post("/fx/revalue")
async def revalue_foreign_currency(
    payload: FXRevaluationIn,
    current_user: User = Depends(get_current_user),
):
    """Revalue foreign-currency monetary accounts using an operator-supplied closing rate."""
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    currency = payload.currency.upper()
    if currency in {"TRY", "TRL"}:
        raise HTTPException(status_code=400, detail="TRY için döviz değerlemesi yapılamaz")

    monetary_accounts = await db.gl_accounts.find(
        {"tenant_id": tenant_id, "active": True, "monetary": True},
        {"_id": 0},
    ).to_list(5000)
    account_by_code = {account["code"]: account for account in monetary_accounts}
    if not account_by_code:
        raise HTTPException(status_code=409, detail="Değerleme için parasal hesap tanımlanmamış")
    entries = await db.gl_journal_entries.find(
        {"tenant_id": tenant_id, "status": "posted", "date": {"$lte": payload.date}},
        {"_id": 0},
    ).to_list(100000)
    positions: dict[str, dict[str, int]] = {}
    for entry in entries:
        for line in entry.get("lines", []):
            code = line.get("account_code")
            if code not in account_by_code:
                continue
            if line.get("currency") != currency:
                if entry.get("revaluation_currency") == currency:
                    position = positions.setdefault(code, {"foreign_minor": 0, "carrying_minor": 0})
                    position["carrying_minor"] += int(line.get("debit_minor") or 0) - int(
                        line.get("credit_minor") or 0
                    )
                continue
            foreign_minor = int(line.get("foreign_amount_minor") or 0)
            if not foreign_minor:
                continue
            sign = 1 if int(line.get("debit_minor") or 0) > 0 else -1
            position = positions.setdefault(code, {"foreign_minor": 0, "carrying_minor": 0})
            position["foreign_minor"] += sign * foreign_minor
            position["carrying_minor"] += int(line.get("debit_minor") or 0) - int(line.get("credit_minor") or 0)

    rate = Decimal(str(payload.closing_rate))
    lines: list[dict] = []
    result_positions: list[dict] = []
    total_gain_minor = total_loss_minor = 0
    for code in sorted(positions):
        position = positions[code]
        target_minor = int(
            (Decimal(position["foreign_minor"]) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        difference_minor = target_minor - position["carrying_minor"]
        result_positions.append(
            {
                "account_code": code,
                "account_name": account_by_code[code].get("name"),
                "foreign_amount": float(Decimal(position["foreign_minor"]) / 100),
                "carrying_amount": float(Decimal(position["carrying_minor"]) / 100),
                "revalued_amount": float(Decimal(target_minor) / 100),
                "difference": float(Decimal(difference_minor) / 100),
            }
        )
        if difference_minor > 0:
            amount = float(Decimal(difference_minor) / 100)
            lines.append({"account_code": code, "debit": amount, "memo": f"{currency} kur değerlemesi"})
            total_gain_minor += difference_minor
        elif difference_minor < 0:
            amount = float(Decimal(abs(difference_minor)) / 100)
            lines.append({"account_code": code, "credit": amount, "memo": f"{currency} kur değerlemesi"})
            total_loss_minor += abs(difference_minor)
    if total_gain_minor:
        lines.append(
            {
                "account_code": payload.gain_account_code.strip(),
                "credit": float(Decimal(total_gain_minor) / 100),
                "memo": f"{currency} kambiyo kârı",
            }
        )
    if total_loss_minor:
        lines.append(
            {
                "account_code": payload.loss_account_code.strip(),
                "debit": float(Decimal(total_loss_minor) / 100),
                "memo": f"{currency} kambiyo zararı",
            }
        )
    if not lines:
        return {"entry": None, "positions": result_positions, "message": "Değerleme farkı oluşmadı"}
    try:
        entry = await post_journal_entry(
            db,
            tenant_id,
            date=payload.date,
            memo=f"{payload.date} {currency} dönem sonu kur değerlemesi",
            lines=lines,
            source="fx_revaluation",
            source_ref=f"{currency}:{payload.date}",
            actor=_actor_id(current_user),
            idempotency_key=f"gl-fx-revaluation:{currency}:{payload.date}",
        )
    except GLPostingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.gl_journal_entries.update_one(
        {"tenant_id": tenant_id, "id": entry["id"]},
        {"$set": {"revaluation_currency": currency, "closing_rate": str(rate), "revaluation_positions": result_positions}},
    )
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gl_fx_revaluation_posted",
        entity_type="gl_journal_entry",
        entity_id=entry["id"],
        details=f"{currency} {payload.date} kur değerlemesi kaydedildi",
        after_value={"entry_no": entry.get("entry_no"), "currency": currency, "closing_rate": str(rate)},
        db=db,
    )
    return {"entry": entry, "positions": result_positions}


@router.get("/integrations/operational/mapping")
async def get_operational_gl_mapping(current_user: User = Depends(get_current_user)):
    _require_role(current_user, _READ_ROLES)
    return {"mapping": await get_operational_mapping(db, _tenant_of(current_user))}


@router.put("/integrations/operational/mapping")
async def update_operational_gl_mapping(
    payload: OperationalMappingIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    account_codes = {
        value.strip()
        for key, value in payload.model_dump().items()
        if key.endswith("_account_code")
    }
    accounts = await db.gl_accounts.find(
        {"tenant_id": tenant_id, "active": True, "code": {"$in": sorted(account_codes)}},
        {"_id": 0, "code": 1},
    ).to_list(100)
    missing = sorted(account_codes - {account["code"] for account in accounts})
    if missing:
        raise HTTPException(status_code=409, detail=f"Operasyonel köprü için eksik hesap kodları: {', '.join(missing)}")
    now = _now_iso()
    mapping = {**payload.model_dump(), "tenant_id": tenant_id, "updated_at": now, "updated_by": _actor_id(current_user)}
    await db.gl_operational_mappings.update_one(
        {"tenant_id": tenant_id},
        {"$set": mapping, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gl_operational_mapping_updated",
        entity_type="gl_operational_mapping",
        entity_id=tenant_id,
        details="PMS/POS otomatik muhasebe eşlemesi güncellendi",
        after_value={key: mapping[key] for key in DEFAULT_MAPPING},
        db=db,
    )
    return {"mapping": mapping}


@router.get("/integrations/operational/status")
async def operational_gl_status(current_user: User = Depends(get_current_user)):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    mapping = await get_operational_mapping(db, tenant_id)
    failed_night_audits = await db.night_audit_runs.count_documents(
        {"tenant_id": tenant_id, "gl_bridge_status": "failed"}
    )
    failed_pos = await db.pos_transactions.count_documents(
        {"tenant_id": tenant_id, "gl_bridge_status": "failed"}
    )
    latest = await db.night_audit_runs.find_one(
        {"tenant_id": tenant_id, "status": "completed"},
        {"_id": 0, "id": 1, "business_date": 1, "gl_bridge_status": 1, "gl_entry_no": 1},
        sort=[("business_date", -1)],
    )
    return {
        "configured": bool(mapping["enabled"]),
        "mapping": mapping,
        "failed": {"night_audit": failed_night_audits, "pos": failed_pos},
        "latest_night_audit": latest,
        "healthy": bool(mapping["enabled"]) and failed_night_audits == 0 and failed_pos == 0,
    }


@router.post("/integrations/operational/night-audit/{run_id}/retry")
async def retry_night_audit_gl_bridge(run_id: str, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    run = await db.night_audit_runs.find_one(
        {"tenant_id": tenant_id, "id": run_id, "status": "completed"},
        {"_id": 0},
    )
    if not run:
        raise HTTPException(status_code=404, detail="Tamamlanmış gece denetimi bulunamadı")
    try:
        return await post_night_audit_daily_to_gl(
            db,
            tenant_id,
            run["business_date"],
            run_id=run_id,
            actor=_actor_id(current_user),
        )
    except OperationalGLBridgeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/journal")
async def create_journal(payload: JournalIn, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    idempotency_key = (payload.idempotency_key or "").strip() or None
    if not idempotency_key:
        raise HTTPException(status_code=422, detail="Manuel fiş için idempotency_key zorunludur")
    try:
        entry = await post_journal_entry(
            db,
            tenant_id,
            date=payload.date,
            memo=payload.memo.strip(),
            lines=[ln.model_dump() for ln in payload.lines],
            source="manual",
            source_ref=payload.source_ref,
            actor=_actor_id(current_user),
            idempotency_key=idempotency_key,
        )
    except GLPostingError as exc:
        status_code = 409 if "dönemi kapalı" in str(exc) or "Idempotency anahtarı" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gl_manual_journal_posted",
        entity_type="gl_journal_entry",
        entity_id=entry["id"],
        details=f"{entry.get('entry_no') or entry['id']} manuel yevmiye fişi kaydedildi",
        after_value={
            "entry_no": entry.get("entry_no"),
            "date": entry.get("date"),
            "total_debit_minor": entry.get("total_debit_minor"),
            "total_credit_minor": entry.get("total_credit_minor"),
            "idempotency_key": entry.get("idempotency_key"),
        },
        db=db,
    )
    return {"entry": entry}


@router.post("/journal/{entry_id}/reverse")
async def reverse_journal(
    entry_id: str,
    payload: JournalReversalIn,
    current_user: User = Depends(get_current_user),
):
    """Create an immutable, linked contra-entry; never edit/delete the source."""
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    original = await db.gl_journal_entries.find_one(
        {"tenant_id": tenant_id, "id": entry_id, "status": "posted"},
        {"_id": 0},
    )
    if not original:
        raise HTTPException(status_code=404, detail="Ters kayıt yapılacak fiş bulunamadı")
    if original.get("reverses_entry_id"):
        raise HTTPException(status_code=409, detail="Bir ters kayıt fişi yeniden ters kayda alınamaz")

    reversed_lines = [
        {
            "account_code": line.get("account_code"),
            "debit": line.get("credit", 0),
            "credit": line.get("debit", 0),
            "memo": f"Ters kayıt: {line.get('memo') or original.get('memo') or ''}".strip(),
        }
        for line in original.get("lines", [])
    ]
    if not reversed_lines:
        raise HTTPException(status_code=409, detail="Kaynak fişin ters çevrilecek satırı yok")

    idempotency_key = payload.idempotency_key.strip()
    existing_reversal = await db.gl_journal_entries.find_one(
        {"tenant_id": tenant_id, "reverses_entry_id": entry_id},
        {"_id": 0},
    )
    if existing_reversal and existing_reversal.get("idempotency_key") != idempotency_key:
        raise HTTPException(status_code=409, detail="Bu fiş için daha önce ters kayıt oluşturulmuş")

    await ensure_compound_unique(
        db.gl_journal_entries,
        [("tenant_id", 1), ("reverses_entry_id", 1)],
        partial_filter={"reverses_entry_id": {"$type": "string"}},
        name="ux_gl_single_reversal",
    )
    try:
        reversal = await post_journal_entry(
            db,
            tenant_id,
            date=payload.date,
            memo=f"{original.get('entry_no') or entry_id} ters kaydı — {payload.reason.strip()}",
            lines=reversed_lines,
            source="reversal",
            source_ref=entry_id,
            actor=_actor_id(current_user),
            idempotency_key=idempotency_key,
            reverses_entry_id=entry_id,
            reversal_reason=payload.reason.strip(),
        )
    except GLPostingError as exc:
        status_code = 409 if "dönemi kapalı" in str(exc) or "Idempotency anahtarı" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="Bu fiş için eşzamanlı olarak ters kayıt oluşturulmuş") from exc

    await db.gl_journal_entries.update_one(
        {"tenant_id": tenant_id, "id": entry_id},
        {
            "$set": {
                "reversal_status": "reversed",
                "reversed_by_entry_id": reversal["id"],
                "reversed_at": reversal["created_at"],
                "reversed_by": _actor_id(current_user),
            }
        },
    )
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gl_journal_reversed",
        entity_type="gl_journal_entry",
        entity_id=entry_id,
        details=f"{original.get('entry_no') or entry_id} için bağlı ters kayıt oluşturuldu",
        before_value={"reversal_status": original.get("reversal_status")},
        after_value={
            "reversal_status": "reversed",
            "reversal_entry_id": reversal["id"],
            "reason": payload.reason.strip(),
        },
        db=db,
        severity="warning",
    )
    return {"entry": reversal, "original_entry_id": entry_id}


# ─────────────────────────────────────────────────────────────────────
# Nilvera incoming invoice ↔ GL bridge
# ─────────────────────────────────────────────────────────────────────
@router.post("/integrations/nilvera/incoming/{invoice_id}/post")
async def post_nilvera_incoming_invoice_to_gl(
    invoice_id: str,
    payload: NilveraIncomingGLPostIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    try:
        entry = await post_incoming_invoice_to_gl(
            tenant_id,
            invoice_id,
            purchase_account_code=payload.purchase_account_code,
            vat_account_code=payload.vat_account_code,
            payable_account_code=payload.payable_account_code,
            actor=_actor_id(current_user),
        )
    except InvoiceGLBridgeError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "NILVERA_GL_POSTING_BLOCKED", "detail": str(exc)},
        ) from exc
    return {"entry": entry}


@router.get("/integrations/nilvera/incoming/{invoice_id}/link")
async def get_nilvera_incoming_invoice_gl_link(
    invoice_id: str,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    link = await get_incoming_invoice_gl_link(tenant_id, invoice_id)
    return {
        "source_entry": link.source_entry,
        "return_entries": list(link.return_entries),
    }


@router.get("/trial-balance")
async def trial_balance(
    as_of: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    return await compute_trial_balance(db, tenant_id, as_of=as_of)


@router.get("/statements/income-statement")
async def income_statement(
    start: str | None = Query(None),
    end: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    try:
        return await compute_income_statement(db, tenant_id, start=start, end=end)
    except GLPeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/statements/balance-sheet")
async def balance_sheet(
    as_of: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    try:
        return await compute_balance_sheet(db, tenant_id, as_of=as_of)
    except GLPeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _variance(current: int, comparison: int) -> dict:
    difference = current - comparison
    percent = None if comparison == 0 else round((difference / abs(comparison)) * 100, 2)
    return {"current_minor": current, "comparison_minor": comparison, "difference_minor": difference, "percent": percent}


@router.get("/statements/comparative-income-statement")
async def comparative_income_statement(
    start: str = Query(...),
    end: str = Query(...),
    comparison_start: str = Query(...),
    comparison_end: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    try:
        current = await compute_income_statement(db, tenant_id, start=start, end=end)
        comparison = await compute_income_statement(
            db,
            tenant_id,
            start=comparison_start,
            end=comparison_end,
        )
    except GLPeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "current": current,
        "comparison": comparison,
        "variance": {
            key: _variance(current["totals"][f"{key}_minor"], comparison["totals"][f"{key}_minor"])
            for key in ("revenue", "expenses", "net_income")
        },
    }


@router.get("/statements/comparative-balance-sheet")
async def comparative_balance_sheet(
    as_of: str = Query(...),
    comparison_as_of: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    try:
        current = await compute_balance_sheet(db, tenant_id, as_of=as_of)
        comparison = await compute_balance_sheet(db, tenant_id, as_of=comparison_as_of)
    except GLPeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "current": current,
        "comparison": comparison,
        "variance": {
            key: _variance(
                int(round(current["totals"][key] * 100)),
                int(round(comparison["totals"][key] * 100)),
            )
            for key in ("assets", "liabilities", "equity", "liabilities_and_equity")
        },
    }


async def _chain_properties(current_user: User) -> list[dict]:
    tenant_id = _tenant_of(current_user)
    own = await _system_db.tenants.find_one(
        {"$or": [{"tenant_id": tenant_id}, {"id": tenant_id}]},
        {"_id": 0, "chain_id": 1, "tenant_id": 1, "id": 1, "hotel_name": 1, "name": 1},
    )
    chain_id = (own or {}).get("chain_id")
    if not chain_id:
        return [
            {
                "tenant_id": tenant_id,
                "property_name": (own or {}).get("hotel_name") or (own or {}).get("name") or tenant_id,
            }
        ]
    tenants = await _system_db.tenants.find(
        {"chain_id": chain_id},
        {"_id": 0, "tenant_id": 1, "id": 1, "hotel_name": 1, "name": 1},
    ).to_list(500)
    return [
        {
            "tenant_id": tenant.get("tenant_id") or tenant.get("id"),
            "property_name": tenant.get("hotel_name") or tenant.get("name") or tenant.get("tenant_id") or tenant.get("id"),
        }
        for tenant in tenants
        if tenant.get("tenant_id") or tenant.get("id")
    ]


@router.get("/chain/consolidated")
async def chain_consolidated_finance(
    start: str = Query(...),
    end: str = Query(...),
    as_of: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    """Chain-scoped consolidated statements; never widens beyond the user's chain_id."""
    _require_role(current_user, _READ_ROLES)
    properties = await _chain_properties(current_user)

    async def _property_finance(property_doc: dict) -> dict:
        tenant_id = property_doc["tenant_id"]
        income, balance = await asyncio.gather(
            compute_income_statement(_system_db, tenant_id, start=start, end=end),
            compute_balance_sheet(_system_db, tenant_id, as_of=as_of),
        )
        return {**property_doc, "income": income["totals"], "balance": balance["totals"]}

    property_rows = await asyncio.gather(*(_property_finance(property_doc) for property_doc in properties))
    totals_minor = {
        "revenue": sum(row["income"]["revenue_minor"] for row in property_rows),
        "expenses": sum(row["income"]["expenses_minor"] for row in property_rows),
        "net_income": sum(row["income"]["net_income_minor"] for row in property_rows),
        "assets": int(round(sum(row["balance"]["assets"] for row in property_rows) * 100)),
        "liabilities": int(round(sum(row["balance"]["liabilities"] for row in property_rows) * 100)),
        "equity": int(round(sum(row["balance"]["equity"] for row in property_rows) * 100)),
        "liabilities_and_equity": int(
            round(sum(row["balance"]["liabilities_and_equity"] for row in property_rows) * 100)
        ),
    }
    return {
        "scope": "chain" if len(property_rows) > 1 else "single_property",
        "property_count": len(property_rows),
        "start": start,
        "end": end,
        "as_of": as_of,
        "properties": property_rows,
        "totals": {
            key: {"amount_minor": value, "amount": float(Decimal(value) / 100)}
            for key, value in totals_minor.items()
        },
        "consolidation": {
            "mode": "aggregation",
            "intercompany_eliminations_applied": False,
            "warning": "Grup içi cari hesap eliminasyonları tanımlanmadıysa toplamlar brüt görünür.",
        },
    }


async def _export_rows(tenant_id: str, report: str, start: str | None, end: str | None, as_of: str | None):
    if report == "trial_balance":
        data = await compute_trial_balance(db, tenant_id, as_of=as_of)
        return (
            "Mizan",
            ["Hesap Kodu", "Hesap Adı", "Borç Toplamı", "Alacak Toplamı", "Borç Bakiye", "Alacak Bakiye"],
            [
                [
                    row["account_code"],
                    row["account_name"],
                    row["total_debit"],
                    row["total_credit"],
                    row["debit_balance"],
                    row["credit_balance"],
                ]
                for row in data["rows"]
            ],
        )
    if report == "income_statement":
        data = await compute_income_statement(db, tenant_id, start=start, end=end)
        rows = [
            ["Gelir", row["account_code"], row["account_name"], row["amount"]] for row in data["revenue"]
        ] + [["Gider", row["account_code"], row["account_name"], row["amount"]] for row in data["expenses"]]
        return "Gelir Tablosu", ["Bölüm", "Hesap Kodu", "Hesap Adı", "Tutar"], rows
    if report == "balance_sheet":
        data = await compute_balance_sheet(db, tenant_id, as_of=as_of)
        section_names = {"assets": "Varlık", "liabilities": "Yükümlülük", "equity": "Özkaynak"}
        rows = [
            [section_names[section], row["account_code"], row["account_name"], row["amount"]]
            for section in ("assets", "liabilities", "equity")
            for row in data[section]
        ]
        return "Bilanço", ["Bölüm", "Hesap Kodu", "Hesap Adı", "Tutar"], rows
    query: dict = {"tenant_id": tenant_id, "status": "posted"}
    if start or end:
        query["date"] = {}
        if start:
            query["date"]["$gte"] = start
        if end:
            query["date"]["$lte"] = end
    entries = await db.gl_journal_entries.find(query, {"_id": 0}).sort(
        [("date", 1), ("posting_sequence", 1)]
    ).to_list(100000)
    rows = [
        [
            entry.get("entry_no"),
            entry.get("date"),
            entry.get("memo"),
            line.get("line_no", 0) + 1,
            line.get("account_code"),
            line.get("account_name"),
            line.get("debit", 0),
            line.get("credit", 0),
            entry.get("source"),
        ]
        for entry in entries
        for line in entry.get("lines", [])
    ]
    return (
        "Yevmiye Defteri",
        ["Fiş No", "Tarih", "Açıklama", "Satır", "Hesap Kodu", "Hesap Adı", "Borç", "Alacak", "Kaynak"],
        rows,
    )


@router.get("/reports/export")
async def export_gl_report(
    report: Literal["trial_balance", "income_statement", "balance_sheet", "journal"] = Query(...),
    format: Literal["xlsx", "pdf"] = Query("xlsx"),
    start: str | None = Query(None),
    end: str | None = Query(None),
    as_of: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    title, headers, rows = await _export_rows(tenant_id, report, start, end, as_of)
    if format == "pdf" and len(rows) > 10000:
        raise HTTPException(status_code=413, detail="PDF dışa aktarma 10.000 satırla sınırlıdır; Excel kullanın")
    filename = f"gl-{report}-{as_of or end or datetime.now(UTC).date().isoformat()}"
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gl_report_exported",
        entity_type="gl_report",
        entity_id=filename,
        details=f"{report} raporu {format} olarak dışa aktarıldı",
        after_value={"report": report, "format": format, "row_count": len(rows), "start": start, "end": end, "as_of": as_of},
        db=db,
    )
    if format == "xlsx":
        workbook = create_excel_workbook(title, headers, rows, sheet_name=title[:31])
        return excel_response(workbook, f"{filename}.xlsx")

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    table = Table([headers, *rows], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    document.build([Paragraph(title, styles["Title"]), table])
    return Response(
        content=output.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )


# ─────────────────────────────────────────────────────────────────────
# Nilvera outgoing invoice ↔ GL bridge
# ─────────────────────────────────────────────────────────────────────
@router.post("/integrations/nilvera/outgoing/{invoice_id}/post")
async def post_nilvera_outgoing_invoice_to_gl(
    invoice_id: str,
    payload: NilveraOutgoingGLPostIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    try:
        from core.integrations.invoice_gl_bridge import post_outgoing_invoice_to_gl
        entry = await post_outgoing_invoice_to_gl(
            tenant_id,
            invoice_id,
            revenue_account_code=payload.revenue_account_code,
            receivable_account_code=payload.receivable_account_code,
            discount_account_code=payload.discount_account_code,
            vat_account_code=payload.vat_account_code,
            accommodation_tax_account_code=payload.accommodation_tax_account_code,
            vat_accounts_by_rate=payload.vat_accounts_by_rate,
            accommodation_tax_accounts_by_rate=payload.accommodation_tax_accounts_by_rate,
            actor=_actor_id(current_user),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "NILVERA_GL_POSTING_BLOCKED", "detail": str(exc)},
        ) from exc
    return {"entry": entry}
