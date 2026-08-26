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
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.accounting.eledger_source_package import (
    ELedgerSourceError,
    build_eledger_source_package,
    preflight_eledger_source,
)
from core.audit import log_audit_event
from core.database import db
from core.integrations.invoice_gl_bridge import (
    InvoiceGLBridgeError,
    get_incoming_invoice_gl_link,
    post_incoming_invoice_to_gl,
)
from core.integrations.nilvera_gl_automation import (
    get_nilvera_gl_settings,
    list_nilvera_gl_queue,
    process_nilvera_gl_queue_item,
    save_nilvera_gl_settings,
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
from shared_kernel.gl_periods import (
    GLPeriodError,
    assert_gl_period_open,
    ensure_calendar_year_periods,
    normalize_posting_date,
)
from shared_kernel.gl_posting import (
    ACCOUNT_TYPES,
    INTEGRITY_GENESIS,
    GLPostingError,
    compute_balance_sheet,
    compute_income_statement,
    compute_journal_entry_hash,
    compute_trial_balance,
    normal_balance,
    normalize_journal_lines,
    post_journal_entry,
    sequence_void_hash,
    verify_journal_entry_hash,
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
    ("191", "İndirilecek KDV", "asset"),
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
    ("611", "Satış İskontoları", "revenue", "debit"),
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
    rows = (
        await db.gl_periods.find(
            {"tenant_id": tenant_id, "fiscal_year": payload.fiscal_year},
            {"_id": 0},
        )
        .sort("period_no", 1)
        .to_list(12)
    )
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
    pending_voucher = await db.gl_vouchers.find_one(
        {
            "tenant_id": tenant_id,
            "date": {"$gte": period["start_date"], "$lte": period["end_date"]},
            "status": {"$in": ["draft", "submitted", "approved", "posting", "rejected"]},
        },
        {"_id": 0, "voucher_no": 1, "status": 1},
    )
    if pending_voucher:
        raise HTTPException(
            status_code=409,
            detail=(f"{pending_voucher.get('voucher_no') or 'Bekleyen fiş'} kesinleşmeden mali dönem kapatılamaz"),
        )
    integrity = await journal_integrity_audit(
        fiscal_year=int(period["fiscal_year"]),
        current_user=current_user,
    )
    if not integrity.get("healthy"):
        raise HTTPException(
            status_code=409,
            detail="Yevmiye sıra veya bütünlük denetimi başarısız olduğu için dönem kapatılamaz",
        )
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
    periods = (
        await db.gl_periods.find(
            {"tenant_id": tenant_id, "fiscal_year": payload.fiscal_year},
            {"_id": 0},
        )
        .sort("period_no", 1)
        .to_list(12)
    )
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
        if row.get("account_type") in {"asset", "liability", "equity"} and (row["debit_balance_minor"] or row["credit_balance_minor"])
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


class VoucherCreateIn(BaseModel):
    date: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$")
    voucher_type: Literal["mahsup", "tahsil", "tediye", "acilis", "kapanis"] = "mahsup"
    memo: str = Field(..., min_length=1, max_length=500)
    lines: list[JournalLineIn] = Field(..., min_length=2, max_length=500)


class VoucherUpdateIn(VoucherCreateIn):
    version: int = Field(..., ge=1)


class VoucherActionIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


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


class IntercompanyRuleIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    kind: Literal["balance", "income"]
    tenant_a_id: str = Field(..., min_length=1, max_length=80)
    account_a_code: str = Field(..., min_length=1, max_length=40)
    tenant_b_id: str = Field(..., min_length=1, max_length=80)
    account_b_code: str = Field(..., min_length=1, max_length=40)
    active: bool = True


class ELedgerSettingsIn(BaseModel):
    taxpayer_id: str = Field(..., min_length=10, max_length=11, pattern=r"^\d{10,11}$")
    legal_name: str = Field(..., min_length=2, max_length=240)
    source_application: str = Field("Syroce PMS", min_length=2, max_length=120)
    source_application_version: str = Field(..., min_length=1, max_length=40)
    software_approval_reference: str | None = Field(None, max_length=120)


class NilveraIncomingGLPostIn(BaseModel):
    purchase_account_code: str = Field(..., description="GL account for expense/asset")
    vat_account_code: str = Field(..., description="GL account for deductible VAT")
    payable_account_code: str = Field(..., description="GL account for vendor payable")
    other_tax_account_code: str | None = Field(None, description="Fallback GL account for additive purchase taxes")
    deduction_account_code: str | None = Field(None, description="Fallback GL account for deductions/withholding")
    other_tax_accounts_by_code: dict[str, str] = Field(default_factory=dict)
    deduction_accounts_by_code: dict[str, str] = Field(default_factory=dict)


class NilveraOutgoingGLPostIn(BaseModel):
    revenue_account_code: str = Field(..., description="GL account for revenue/sales")
    receivable_account_code: str = Field(..., description="GL account for customer receivable")
    discount_account_code: str | None = Field(None, description="GL account for sales discounts")

    vat_account_code: str | None = Field(None, description="Fallback GL account for calculated VAT")
    accommodation_tax_account_code: str | None = Field(None, description="Fallback GL account for Accommodation Tax (0059)")

    vat_accounts_by_rate: dict[str, str] = Field(default_factory=dict, description="e.g. {'10': '391.10', '20': '391.20'}")
    accommodation_tax_accounts_by_rate: dict[str, str] = Field(default_factory=dict, description="e.g. {'1': '360.01', '2': '360.02'}")


class NilveraGLSettingsIn(BaseModel):
    incoming_mode: Literal["disabled", "review", "automatic"] = "review"
    outgoing_mode: Literal["disabled", "review", "automatic"] = "review"
    incoming_purchase_account_code: str = Field("153", min_length=1, max_length=40)
    incoming_vat_account_code: str = Field("191", min_length=1, max_length=40)
    incoming_payable_account_code: str = Field("320", min_length=1, max_length=40)
    incoming_other_tax_account_code: str | None = Field(None, max_length=40)
    incoming_deduction_account_code: str | None = Field(None, max_length=40)
    incoming_other_tax_accounts_by_code: dict[str, str] = Field(default_factory=dict)
    incoming_deduction_accounts_by_code: dict[str, str] = Field(default_factory=dict)
    outgoing_revenue_account_code: str = Field("600", min_length=1, max_length=40)
    outgoing_receivable_account_code: str = Field("120", min_length=1, max_length=40)
    outgoing_discount_account_code: str | None = Field("611", max_length=40)
    outgoing_vat_account_code: str | None = Field("391", max_length=40)
    outgoing_accommodation_tax_account_code: str | None = Field("360", max_length=40)
    outgoing_vat_accounts_by_rate: dict[str, str] = Field(default_factory=dict)
    outgoing_accommodation_tax_accounts_by_rate: dict[str, str] = Field(default_factory=dict)


_VOUCHER_STATUSES = {"draft", "submitted", "approved", "rejected", "posting", "posted", "cancelled"}


def _normalized_voucher_payload(payload: VoucherCreateIn | VoucherUpdateIn) -> dict:
    try:
        lines, total_debit, total_credit = normalize_journal_lines([line.model_dump() for line in payload.lines])
    except GLPostingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "date": normalize_posting_date(payload.date),
        "voucher_type": payload.voucher_type,
        "memo": payload.memo.strip(),
        "lines": lines,
        "total_debit": total_debit,
        "total_credit": total_credit,
    }


async def _allocate_voucher_number(tenant_id: str, fiscal_year: int, now: str) -> tuple[int, str]:
    """Allocate a durable, monotonic document number that is never reused.

    Cancelled vouchers remain in the register, so an allocated number is
    always explainable instead of disappearing from the audit trail.
    """
    counter_id = f"gl-voucher-counter:{tenant_id}:{fiscal_year}"
    counter = await db.gl_counters.find_one_and_update(
        {"_id": counter_id, "tenant_id": tenant_id},
        {
            "$inc": {"value": 1},
            "$setOnInsert": {
                "tenant_id": tenant_id,
                "fiscal_year": fiscal_year,
                "counter_type": "voucher",
                "created_at": now,
            },
            "$set": {"updated_at": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    sequence = int(counter["value"])
    return sequence, f"MF-{fiscal_year}-{sequence:08d}"


async def _validate_voucher_context(tenant_id: str, voucher: dict, actor: str) -> None:
    try:
        await assert_gl_period_open(db, tenant_id, voucher["date"], actor=actor)
    except GLPeriodError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    codes = sorted({line["account_code"] for line in voucher.get("lines", [])})
    accounts = await db.gl_accounts.find(
        {"tenant_id": tenant_id, "code": {"$in": codes}},
        {"_id": 0, "code": 1, "active": 1},
    ).to_list(1000)
    active_codes = {account["code"] for account in accounts if account.get("active", True)}
    missing = sorted(set(codes) - active_codes)
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"Hesap planında olmayan veya pasif hesaplar: {', '.join(missing)}",
        )


async def _audit_voucher_transition(
    *,
    tenant_id: str,
    actor: str,
    voucher: dict,
    action: str,
    before_status: str | None,
    after_status: str,
    reason: str | None = None,
) -> None:
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=actor,
        action=action,
        entity_type="gl_voucher",
        entity_id=voucher["id"],
        details=f"{voucher.get('voucher_no')} fişi: {before_status or '-'} → {after_status}",
        before_value={"status": before_status},
        after_value={"status": after_status, "reason": reason},
        db=db,
    )


@router.get("/vouchers")
async def list_vouchers(
    status: str | None = Query(None),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    if status and status not in _VOUCHER_STATUSES:
        raise HTTPException(status_code=400, detail="Geçersiz fiş durumu")
    query: dict = {"tenant_id": _tenant_of(current_user)}
    if status:
        query["status"] = status
    if start or end:
        query["date"] = {
            **({"$gte": normalize_posting_date(start)} if start else {}),
            **({"$lte": normalize_posting_date(end)} if end else {}),
        }
    rows = await db.gl_vouchers.find(query, {"_id": 0}).sort("updated_at", -1).to_list(limit)
    return {"vouchers": rows}


@router.get("/vouchers/{voucher_id}")
async def get_voucher(voucher_id: str, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _READ_ROLES)
    voucher = await db.gl_vouchers.find_one(
        {"tenant_id": _tenant_of(current_user), "id": voucher_id},
        {"_id": 0},
    )
    if not voucher:
        raise HTTPException(status_code=404, detail="Muhasebe fişi bulunamadı")
    return {"voucher": voucher}


@router.post("/vouchers")
async def create_voucher(payload: VoucherCreateIn, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    actor = _actor_id(current_user)
    normalized = _normalized_voucher_payload(payload)
    now = _now_iso()
    voucher_id = str(uuid.uuid4())
    fiscal_year = int(normalized["date"][:4])
    voucher_sequence, voucher_no = await _allocate_voucher_number(tenant_id, fiscal_year, now)
    voucher = {
        "id": voucher_id,
        "tenant_id": tenant_id,
        "voucher_no": voucher_no,
        "voucher_sequence": voucher_sequence,
        "fiscal_year": fiscal_year,
        **normalized,
        "status": "draft",
        "version": 1,
        "created_at": now,
        "created_by": actor,
        "updated_at": now,
        "updated_by": actor,
        "history": [{"at": now, "by": actor, "action": "created", "status": "draft"}],
    }
    await db.gl_vouchers.insert_one(dict(voucher))
    voucher.pop("_id", None)
    await _audit_voucher_transition(
        tenant_id=tenant_id,
        actor=actor,
        voucher=voucher,
        action="gl_voucher_created",
        before_status=None,
        after_status="draft",
    )
    return {"voucher": voucher}


@router.put("/vouchers/{voucher_id}")
async def update_voucher(
    voucher_id: str,
    payload: VoucherUpdateIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    actor = _actor_id(current_user)
    before = await db.gl_vouchers.find_one(
        {"tenant_id": tenant_id, "id": voucher_id},
        {"_id": 0},
    )
    if not before:
        raise HTTPException(status_code=404, detail="Muhasebe fişi bulunamadı")
    if before.get("status") not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="Yalnız taslak veya reddedilmiş fiş düzenlenebilir")
    if int(before.get("version") or 1) != payload.version:
        raise HTTPException(status_code=409, detail="Fiş başka bir kullanıcı tarafından güncellendi")
    now = _now_iso()
    normalized = _normalized_voucher_payload(payload)
    revision = {
        "version": before.get("version", 1),
        "at": now,
        "by": actor,
        "date": before.get("date"),
        "voucher_type": before.get("voucher_type"),
        "memo": before.get("memo"),
        "lines": before.get("lines", []),
        "status": before.get("status"),
    }
    new_version = payload.version + 1
    result = await db.gl_vouchers.update_one(
        {
            "tenant_id": tenant_id,
            "id": voucher_id,
            "status": {"$in": ["draft", "rejected"]},
            "version": payload.version,
        },
        {
            "$set": {
                **normalized,
                "status": "draft",
                "version": new_version,
                "updated_at": now,
                "updated_by": actor,
                "rejection_reason": None,
                "rejected_at": None,
                "rejected_by": None,
            },
            "$push": {
                "revisions": revision,
                "history": {"at": now, "by": actor, "action": "updated", "status": "draft"},
            },
        },
    )
    if result.modified_count != 1:
        raise HTTPException(status_code=409, detail="Fiş eşzamanlı olarak değişti")
    voucher = await db.gl_vouchers.find_one({"tenant_id": tenant_id, "id": voucher_id}, {"_id": 0})
    await _audit_voucher_transition(
        tenant_id=tenant_id,
        actor=actor,
        voucher=voucher,
        action="gl_voucher_updated",
        before_status=before.get("status"),
        after_status="draft",
    )
    return {"voucher": voucher}


@router.post("/vouchers/{voucher_id}/submit")
async def submit_voucher(
    voucher_id: str,
    payload: VoucherActionIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    actor = _actor_id(current_user)
    voucher = await db.gl_vouchers.find_one(
        {"tenant_id": tenant_id, "id": voucher_id, "status": "draft"},
        {"_id": 0},
    )
    if not voucher:
        raise HTTPException(status_code=409, detail="Yalnız taslak fiş incelemeye gönderilebilir")
    await _validate_voucher_context(tenant_id, voucher, actor)
    now = _now_iso()
    result = await db.gl_vouchers.update_one(
        {"tenant_id": tenant_id, "id": voucher_id, "status": "draft", "version": voucher.get("version", 1)},
        {
            "$set": {
                "status": "submitted",
                "submitted_at": now,
                "submitted_by": actor,
                "submission_note": payload.reason.strip(),
                "updated_at": now,
                "updated_by": actor,
                "version": int(voucher.get("version") or 1) + 1,
            },
            "$push": {"history": {"at": now, "by": actor, "action": "submitted", "status": "submitted", "reason": payload.reason.strip()}},
        },
    )
    if result.modified_count != 1:
        raise HTTPException(status_code=409, detail="Fiş eşzamanlı olarak değişti")
    updated = await db.gl_vouchers.find_one({"tenant_id": tenant_id, "id": voucher_id}, {"_id": 0})
    await _audit_voucher_transition(
        tenant_id=tenant_id,
        actor=actor,
        voucher=updated,
        action="gl_voucher_submitted",
        before_status="draft",
        after_status="submitted",
        reason=payload.reason.strip(),
    )
    return {"voucher": updated}


@router.post("/vouchers/{voucher_id}/approve")
async def approve_voucher(
    voucher_id: str,
    payload: VoucherActionIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    actor = _actor_id(current_user)
    voucher = await db.gl_vouchers.find_one(
        {"tenant_id": tenant_id, "id": voucher_id, "status": "submitted"},
        {"_id": 0},
    )
    if not voucher:
        raise HTTPException(status_code=409, detail="Yalnız incelemedeki fiş onaylanabilir")
    if voucher.get("created_by") == actor:
        raise HTTPException(status_code=409, detail="Fişi hazırlayan kullanıcı aynı fişi onaylayamaz")
    await _validate_voucher_context(tenant_id, voucher, actor)
    now = _now_iso()
    result = await db.gl_vouchers.update_one(
        {"tenant_id": tenant_id, "id": voucher_id, "status": "submitted", "version": voucher.get("version", 1)},
        {
            "$set": {
                "status": "approved",
                "approved_at": now,
                "approved_by": actor,
                "approval_reason": payload.reason.strip(),
                "updated_at": now,
                "updated_by": actor,
                "version": int(voucher.get("version") or 1) + 1,
            },
            "$push": {"history": {"at": now, "by": actor, "action": "approved", "status": "approved", "reason": payload.reason.strip()}},
        },
    )
    if result.modified_count != 1:
        raise HTTPException(status_code=409, detail="Fiş eşzamanlı olarak değişti")
    updated = await db.gl_vouchers.find_one({"tenant_id": tenant_id, "id": voucher_id}, {"_id": 0})
    await _audit_voucher_transition(
        tenant_id=tenant_id,
        actor=actor,
        voucher=updated,
        action="gl_voucher_approved",
        before_status="submitted",
        after_status="approved",
        reason=payload.reason.strip(),
    )
    return {"voucher": updated}


@router.post("/vouchers/{voucher_id}/reject")
async def reject_voucher(
    voucher_id: str,
    payload: VoucherActionIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    actor = _actor_id(current_user)
    voucher = await db.gl_vouchers.find_one(
        {"tenant_id": tenant_id, "id": voucher_id, "status": "submitted"},
        {"_id": 0},
    )
    if not voucher:
        raise HTTPException(status_code=409, detail="Yalnız incelemedeki fiş reddedilebilir")
    now = _now_iso()
    result = await db.gl_vouchers.update_one(
        {"tenant_id": tenant_id, "id": voucher_id, "status": "submitted", "version": voucher.get("version", 1)},
        {
            "$set": {
                "status": "rejected",
                "rejected_at": now,
                "rejected_by": actor,
                "rejection_reason": payload.reason.strip(),
                "updated_at": now,
                "updated_by": actor,
                "version": int(voucher.get("version") or 1) + 1,
            },
            "$push": {"history": {"at": now, "by": actor, "action": "rejected", "status": "rejected", "reason": payload.reason.strip()}},
        },
    )
    if result.modified_count != 1:
        raise HTTPException(status_code=409, detail="Fiş eşzamanlı olarak değişti")
    updated = await db.gl_vouchers.find_one({"tenant_id": tenant_id, "id": voucher_id}, {"_id": 0})
    await _audit_voucher_transition(
        tenant_id=tenant_id,
        actor=actor,
        voucher=updated,
        action="gl_voucher_rejected",
        before_status="submitted",
        after_status="rejected",
        reason=payload.reason.strip(),
    )
    return {"voucher": updated}


@router.post("/vouchers/{voucher_id}/cancel")
async def cancel_voucher(
    voucher_id: str,
    payload: VoucherActionIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    actor = _actor_id(current_user)
    voucher = await db.gl_vouchers.find_one(
        {"tenant_id": tenant_id, "id": voucher_id, "status": {"$in": ["draft", "rejected"]}},
        {"_id": 0},
    )
    if not voucher:
        raise HTTPException(status_code=409, detail="Bu aşamadaki fiş iptal edilemez")
    now = _now_iso()
    result = await db.gl_vouchers.update_one(
        {"tenant_id": tenant_id, "id": voucher_id, "status": voucher["status"], "version": voucher.get("version", 1)},
        {
            "$set": {
                "status": "cancelled",
                "cancelled_at": now,
                "cancelled_by": actor,
                "cancellation_reason": payload.reason.strip(),
                "updated_at": now,
                "updated_by": actor,
                "version": int(voucher.get("version") or 1) + 1,
            },
            "$push": {"history": {"at": now, "by": actor, "action": "cancelled", "status": "cancelled", "reason": payload.reason.strip()}},
        },
    )
    if result.modified_count != 1:
        raise HTTPException(status_code=409, detail="Fiş eşzamanlı olarak değişti")
    updated = await db.gl_vouchers.find_one({"tenant_id": tenant_id, "id": voucher_id}, {"_id": 0})
    await _audit_voucher_transition(
        tenant_id=tenant_id,
        actor=actor,
        voucher=updated,
        action="gl_voucher_cancelled",
        before_status=voucher["status"],
        after_status="cancelled",
        reason=payload.reason.strip(),
    )
    return {"voucher": updated}


@router.post("/vouchers/{voucher_id}/post")
async def post_approved_voucher(voucher_id: str, current_user: User = Depends(get_current_user)):
    """Idempotently convert an approved voucher into an immutable journal entry."""
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    actor = _actor_id(current_user)
    voucher = await db.gl_vouchers.find_one(
        {"tenant_id": tenant_id, "id": voucher_id},
        {"_id": 0},
    )
    if not voucher:
        raise HTTPException(status_code=404, detail="Muhasebe fişi bulunamadı")
    if voucher.get("status") == "posted" and voucher.get("journal_entry_id"):
        entry = await db.gl_journal_entries.find_one(
            {"tenant_id": tenant_id, "id": voucher["journal_entry_id"]},
            {"_id": 0},
        )
        return {"voucher": voucher, "entry": entry, "already_posted": True}
    if voucher.get("status") not in {"approved", "posting"}:
        raise HTTPException(status_code=409, detail="Yalnız onaylanmış fiş yevmiyeye işlenebilir")
    await _validate_voucher_context(tenant_id, voucher, actor)
    now = _now_iso()
    claim_id = voucher.get("posting_claim_id") or str(uuid.uuid4())
    if voucher.get("status") == "approved":
        claim = await db.gl_vouchers.update_one(
            {"tenant_id": tenant_id, "id": voucher_id, "status": "approved", "version": voucher.get("version", 1)},
            {
                "$set": {
                    "status": "posting",
                    "posting_claim_id": claim_id,
                    "posting_started_at": now,
                    "updated_at": now,
                    "updated_by": actor,
                    "version": int(voucher.get("version") or 1) + 1,
                },
                "$push": {"history": {"at": now, "by": actor, "action": "posting", "status": "posting"}},
            },
        )
        if claim.modified_count != 1:
            raise HTTPException(status_code=409, detail="Fiş başka bir işlem tarafından alındı")
        voucher = await db.gl_vouchers.find_one({"tenant_id": tenant_id, "id": voucher_id}, {"_id": 0})
    try:
        entry = await post_journal_entry(
            db,
            tenant_id,
            date=voucher["date"],
            memo=voucher["memo"],
            lines=voucher["lines"],
            source="manual_voucher",
            source_ref=voucher["id"],
            actor=actor,
            idempotency_key=f"gl-voucher:{voucher['id']}",
        )
    except GLPostingError as exc:
        await db.gl_vouchers.update_one(
            {"tenant_id": tenant_id, "id": voucher_id, "status": "posting", "posting_claim_id": claim_id},
            {
                "$set": {
                    "status": "approved",
                    "last_post_error": str(exc)[:500],
                    "updated_at": _now_iso(),
                    "updated_by": actor,
                },
                "$unset": {"posting_claim_id": ""},
            },
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    completed_at = _now_iso()
    result = await db.gl_vouchers.update_one(
        {"tenant_id": tenant_id, "id": voucher_id, "status": "posting"},
        {
            "$set": {
                "status": "posted",
                "posted_at": completed_at,
                "posted_by": actor,
                "journal_entry_id": entry["id"],
                "journal_entry_no": entry["entry_no"],
                "updated_at": completed_at,
                "updated_by": actor,
            },
            "$unset": {"posting_claim_id": "", "last_post_error": ""},
            "$push": {"history": {"at": completed_at, "by": actor, "action": "posted", "status": "posted", "entry_no": entry["entry_no"]}},
        },
    )
    if result.modified_count != 1:
        raise HTTPException(
            status_code=409,
            detail="Yevmiye oluşturuldu ancak fiş durumu kesinleştirilemedi; güvenli tekrar deneyin",
        )
    updated = await db.gl_vouchers.find_one({"tenant_id": tenant_id, "id": voucher_id}, {"_id": 0})
    await _audit_voucher_transition(
        tenant_id=tenant_id,
        actor=actor,
        voucher=updated,
        action="gl_voucher_posted",
        before_status="approved",
        after_status="posted",
        reason=entry["entry_no"],
    )
    return {"voucher": updated, "entry": entry, "already_posted": False}


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
    rows = await db.gl_sequence_reservations.find(query, {"_id": 0}).sort([("fiscal_year", -1), ("sequence", 1)]).to_list(100000)
    counters = [
        counter
        for counter in await db.gl_counters.find(query, {"_id": 0}).to_list(1000)
        if counter.get("counter_type") != "voucher"
    ]
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


@router.get("/integrity-audit")
async def journal_integrity_audit(
    fiscal_year: int | None = Query(None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
):
    """Verify journal seals, predecessor links and allocated ordinals.

    Older records created before the integrity-chain rollout are reported as
    ``legacy_unsealed``. They are never silently labelled immutable.
    """
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    query: dict = {"tenant_id": tenant_id}
    if fiscal_year is not None:
        query["fiscal_year"] = fiscal_year
    entries = await db.gl_journal_entries.find(query, {"_id": 0}).to_list(100000)
    reservations = await db.gl_sequence_reservations.find(query, {"_id": 0}).to_list(100000)
    counters = [
        counter
        for counter in await db.gl_counters.find(query, {"_id": 0}).to_list(1000)
        if counter.get("counter_type") != "voucher"
    ]

    entries_by_key = {(int(entry.get("fiscal_year") or str(entry.get("date") or "0000")[:4]), int(entry.get("posting_sequence") or 0)): entry for entry in entries if entry.get("posting_sequence")}
    reservations_by_key = {(int(row.get("fiscal_year") or 0), int(row.get("sequence") or 0)): row for row in reservations if row.get("fiscal_year") and row.get("sequence")}
    counter_by_year = {int(row["fiscal_year"]): int(row.get("value") or 0) for row in counters}
    years = sorted(set(counter_by_year) | {key[0] for key in entries_by_key} | {key[0] for key in reservations_by_key})
    issues: list[dict] = []
    legacy_unsealed: list[str] = []
    sealed_count = 0
    posted_count = 0
    void_count = 0

    for year in years:
        last_hash = INTEGRITY_GENESIS
        max_sequence = max([counter_by_year.get(year, 0)] + [seq for item_year, seq in entries_by_key if item_year == year] + [seq for item_year, seq in reservations_by_key if item_year == year])
        for sequence in range(1, max_sequence + 1):
            key = (year, sequence)
            reservation = reservations_by_key.get(key)
            if not reservation:
                issues.append({"code": "sequence_reservation_missing", "fiscal_year": year, "sequence": sequence})
                continue
            status = reservation.get("status")
            if status == "void":
                void_count += 1
                last_hash = sequence_void_hash(reservation)
                continue
            if status != "posted":
                issues.append({"code": "sequence_not_final", "fiscal_year": year, "sequence": sequence, "status": status or "reserved"})
                continue
            posted_count += 1
            entry = entries_by_key.get(key)
            if not entry:
                issues.append({"code": "posted_entry_missing", "fiscal_year": year, "sequence": sequence})
                continue
            if not entry.get("entry_hash"):
                legacy_unsealed.append(str(entry.get("entry_no") or entry.get("id") or key))
                last_hash = compute_journal_entry_hash(entry)
                continue
            sealed_count += 1
            if entry.get("previous_entry_hash") != last_hash:
                issues.append({"code": "predecessor_hash_mismatch", "entry_no": entry.get("entry_no"), "fiscal_year": year, "sequence": sequence})
            if not verify_journal_entry_hash(entry):
                issues.append({"code": "entry_hash_mismatch", "entry_no": entry.get("entry_no"), "fiscal_year": year, "sequence": sequence})
            last_hash = str(entry.get("entry_hash"))

    duplicate_entry_numbers: list[str] = []
    seen_numbers: set[str] = set()
    for entry in entries:
        entry_no = str(entry.get("entry_no") or "")
        if entry_no and entry_no in seen_numbers:
            duplicate_entry_numbers.append(entry_no)
        seen_numbers.add(entry_no)
    if duplicate_entry_numbers:
        issues.append({"code": "duplicate_entry_number", "entry_numbers": sorted(set(duplicate_entry_numbers))[:100]})

    return {
        "fiscal_year": fiscal_year,
        "healthy": not issues,
        "fully_sealed": not issues and not legacy_unsealed,
        "source_ledger_ready": not issues and not legacy_unsealed,
        # A valid internal chain is necessary but never sufficient for an
        # official GIB e-Defter/berat.  Signing, approved software and GIB
        # acceptance are deliberately represented separately.
        "official_ledger_ready": False,
        "official_edefter": False,
        "counts": {
            "posted": posted_count,
            "sealed": sealed_count,
            "legacy_unsealed": len(legacy_unsealed),
            "void": void_count,
            "issues": len(issues),
        },
        "legacy_unsealed_entries": legacy_unsealed[:100],
        "issues": issues[:500],
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
                    position["carrying_minor"] += int(line.get("debit_minor") or 0) - int(line.get("credit_minor") or 0)
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
        target_minor = int((Decimal(position["foreign_minor"]) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
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
    account_codes = {value.strip() for key, value in payload.model_dump().items() if key.endswith("_account_code")}
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
    failed_night_audits = await db.night_audit_runs.count_documents({"tenant_id": tenant_id, "gl_bridge_status": "failed"})
    failed_pos = await db.pos_transactions.count_documents({"tenant_id": tenant_id, "gl_bridge_status": "failed"})
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


def _reconciliation_minor(value: object) -> int:
    return int(
        (
            Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            * 100
        ).to_integral_exact()
    )


def _reconciliation_amount(value: int) -> float:
    return float(Decimal(value) / 100)


def _settlement_account(mapping: dict, method: object) -> str:
    normalized = str(method or "").strip().lower()
    if normalized in {"cash", "nakit"}:
        return mapping["cash_account_code"]
    if normalized in {"card", "credit_card", "debit_card", "kredi_karti", "pos"}:
        return mapping["card_account_code"]
    return mapping["bank_account_code"]


@router.get("/integrations/operational/reconciliation")
async def operational_reconciliation(
    business_date: str | None = Query(None, min_length=10, max_length=10),
    current_user: User = Depends(get_current_user),
):
    """Cross-check PMS/POS/bank/cashier sources against durable GL links.

    This endpoint is deliberately read-only: it never imports bank data,
    changes operational records, or posts a journal. It exposes missing and
    mismatched source-to-ledger links before period close.
    """
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    selected = business_date or datetime.now(UTC).date().isoformat()
    try:
        parsed_date = date.fromisoformat(selected)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="İş günü YYYY-AA-GG biçiminde olmalıdır") from exc
    if parsed_date.isoformat() != selected:
        raise HTTPException(status_code=400, detail="İş günü YYYY-AA-GG biçiminde olmalıdır")
    next_day = (parsed_date + timedelta(days=1)).isoformat()
    mapping = await get_operational_mapping(db, tenant_id)

    payment_query = {
        "tenant_id": tenant_id,
        "voided": {"$ne": True},
        "$or": [
            {"payment_date": {"$gte": selected, "$lt": next_day}},
            {"processed_at": {"$gte": selected, "$lt": next_day}},
            {"date": {"$gte": selected, "$lt": next_day}},
        ],
    }
    pos_query = {
        "tenant_id": tenant_id,
        "status": {"$in": ["completed", "closed", "paid"]},
        "$or": [
            {"transaction_date": selected},
            {"closed_at": {"$gte": selected, "$lt": next_day}},
            {"created_at": {"$gte": selected, "$lt": next_day}},
        ],
    }
    (
        payments,
        pos_transactions,
        source_folio_charges,
        bank_transactions,
        night_audits,
        cashier_shifts,
        pos_closures,
        journal_entries,
    ) = await asyncio.gather(
        db.payments.find(payment_query, {"_id": 0}).to_list(100000),
        db.pos_transactions.find(pos_query, {"_id": 0}).to_list(100000),
        db.folio_charges.find(
            {
                "tenant_id": tenant_id,
                "voided": {"$ne": True},
                "source_pos_order_id": {"$exists": True},
                "date": {"$gte": selected, "$lt": next_day},
            },
            {"_id": 0, "source_pos_order_id": 1},
        ).to_list(100000),
        db.bank_transactions.find(
            {"tenant_id": tenant_id, "date": {"$gte": selected, "$lt": next_day}},
            {"_id": 0},
        ).to_list(100000),
        db.night_audit_runs.find(
            {"tenant_id": tenant_id, "business_date": selected},
            {"_id": 0},
        ).to_list(1000),
        db.cashier_shifts.find(
            {
                "tenant_id": tenant_id,
                "$or": [
                    {"business_date": selected},
                    {"closed_at": {"$gte": selected, "$lt": next_day}},
                    {"opened_at": {"$gte": selected, "$lt": next_day}},
                ],
            },
            {"_id": 0},
        ).to_list(10000),
        db.pos_closures.find(
            {"tenant_id": tenant_id, "closure_date": selected},
            {"_id": 0},
        ).to_list(1000),
        db.gl_journal_entries.find(
            {
                "tenant_id": tenant_id,
                "date": selected,
                "status": "posted",
                "source": {"$in": ["night_audit", "pos_direct", "bank_reconciliation"]},
            },
            {"_id": 0},
        ).to_list(100000),
    )

    entries_by_id = {str(entry.get("id")): entry for entry in journal_entries if entry.get("id")}
    entries_by_source = {
        (str(entry.get("source")), str(entry.get("source_ref"))): entry
        for entry in journal_entries
        if entry.get("source_ref")
    }
    settlement_accounts = {
        mapping["cash_account_code"],
        mapping["card_account_code"],
        mapping["bank_account_code"],
    }

    blockers: list[dict] = []
    warnings: list[dict] = []
    if not mapping.get("enabled"):
        blockers.append(
            {
                "code": "operational_bridge_disabled",
                "message": "PMS/POS muhasebe köprüsü kapalı; operasyon kayıtları yevmiyeye otomatik bağlanmıyor.",
            }
        )

    payment_by_account: dict[str, int] = {}
    for payment in payments:
        account = _settlement_account(mapping, payment.get("method") or payment.get("payment_method"))
        payment_by_account[account] = payment_by_account.get(account, 0) + _reconciliation_minor(payment.get("amount"))
    payment_total_minor = sum(payment_by_account.values())
    posted_night_runs = [run for run in night_audits if run.get("gl_bridge_status") == "posted"]
    linked_night_entries: list[dict] = []
    for run in posted_night_runs:
        entry = entries_by_id.get(str(run.get("gl_journal_entry_id"))) or entries_by_source.get(
            ("night_audit", str(run.get("id")))
        )
        if not entry:
            blockers.append(
                {
                    "code": "night_audit_journal_missing",
                    "message": f"{run.get('id') or selected} gün sonu kaydının yevmiye bağlantısı bulunamadı.",
                }
            )
            continue
        linked_night_entries.append(entry)

    if payment_total_minor and not posted_night_runs:
        blockers.append(
            {
                "code": "folio_payments_unposted",
                "message": "Günün folyo tahsilatları var ancak muhasebeleştirilmiş gün sonu kaydı yok.",
            }
        )
    night_gl_by_account: dict[str, int] = {}
    for entry in linked_night_entries:
        for line in entry.get("lines", []):
            account = str(line.get("account_code") or "")
            if account in settlement_accounts:
                night_gl_by_account[account] = night_gl_by_account.get(account, 0) + int(
                    line.get("debit_minor") or 0
                )
    payment_variance_minor = payment_total_minor - sum(night_gl_by_account.values())
    if payment_variance_minor:
        blockers.append(
            {
                "code": "folio_gl_variance",
                "message": f"Folyo tahsilatları ile yevmiye arasında {_reconciliation_amount(payment_variance_minor):.2f} fark var.",
            }
        )

    folio_pos_orders = {
        str(row.get("source_pos_order_id"))
        for row in source_folio_charges
        if row.get("source_pos_order_id")
    }
    direct_pos = [
        row
        for row in pos_transactions
        if str(row.get("order_id") or "") not in folio_pos_orders
        and row.get("gl_bridge_status") != "folio_path"
    ]
    pos_total_minor = 0
    pos_gl_total_minor = 0
    for transaction in direct_pos:
        amount_minor = _reconciliation_minor(
            transaction.get("total_amount", transaction.get("amount"))
        )
        pos_total_minor += amount_minor
        entry = entries_by_id.get(str(transaction.get("gl_journal_entry_id"))) or entries_by_source.get(
            ("pos_direct", str(transaction.get("order_id")))
        )
        if transaction.get("gl_bridge_status") != "posted" or not entry:
            blockers.append(
                {
                    "code": "pos_journal_missing",
                    "record_id": transaction.get("id"),
                    "message": f"POS işlemi {transaction.get('order_number') or transaction.get('order_id') or transaction.get('id')} yevmiyeye bağlı değil.",
                }
            )
            continue
        account = _settlement_account(mapping, transaction.get("payment_method"))
        linked_minor = sum(
            int(line.get("debit_minor") or 0)
            for line in entry.get("lines", [])
            if str(line.get("account_code") or "") == account
        )
        pos_gl_total_minor += linked_minor
        if linked_minor != amount_minor:
            blockers.append(
                {
                    "code": "pos_gl_variance",
                    "record_id": transaction.get("id"),
                    "message": f"POS işlemi {transaction.get('order_number') or transaction.get('order_id')} ile yevmiye tutarı farklı.",
                }
            )
    if direct_pos and not pos_closures:
        warnings.append(
            {
                "code": "pos_closure_missing",
                "message": "Günde kesinleşmiş POS işlemleri var ancak POS günlük kapanışı oluşturulmamış.",
            }
        )

    matched_bank = [row for row in bank_transactions if row.get("status") == "matched"]
    unmatched_bank = [row for row in bank_transactions if row.get("status") != "matched"]
    bank_total_minor = 0
    bank_gl_total_minor = 0
    for transaction in matched_bank:
        amount_minor = _reconciliation_minor(transaction.get("amount"))
        bank_total_minor += amount_minor
        entry = entries_by_id.get(str(transaction.get("journal_entry_id"))) or entries_by_source.get(
            ("bank_reconciliation", str(transaction.get("id")))
        )
        if not entry:
            blockers.append(
                {
                    "code": "bank_journal_missing",
                    "record_id": transaction.get("id"),
                    "message": f"Eşleşmiş banka işlemi {transaction.get('id')} için yevmiye bağlantısı yok.",
                }
            )
            continue
        linked_minor = sum(
            int(line.get("debit_minor") or 0)
            for line in entry.get("lines", [])
            if str(line.get("account_code") or "") == mapping["bank_account_code"]
        )
        bank_gl_total_minor += linked_minor
        if linked_minor != amount_minor:
            blockers.append(
                {
                    "code": "bank_gl_variance",
                    "record_id": transaction.get("id"),
                    "message": f"Banka işlemi {transaction.get('id')} ile yevmiye tutarı farklı.",
                }
            )
    if unmatched_bank:
        warnings.append(
            {
                "code": "bank_transactions_unmatched",
                "message": f"{len(unmatched_bank)} banka hareketi henüz fatura/yevmiye ile eşleştirilmemiş.",
            }
        )

    cashier_difference_minor = sum(
        _reconciliation_minor(shift.get("difference"))
        for shift in cashier_shifts
        if shift.get("status") == "closed"
    )
    open_cashier_count = sum(1 for shift in cashier_shifts if shift.get("status") == "open")
    if cashier_difference_minor:
        blockers.append(
            {
                "code": "cashier_count_variance",
                "message": f"Kasa sayımlarında toplam {_reconciliation_amount(cashier_difference_minor):.2f} fark var.",
            }
        )
    if open_cashier_count:
        warnings.append(
            {
                "code": "cashier_shift_open",
                "message": f"{open_cashier_count} kasa vardiyası hâlâ açık.",
            }
        )

    referenced_entries = linked_night_entries + [
        entry
        for entry in journal_entries
        if entry.get("source") in {"pos_direct", "bank_reconciliation"}
    ]
    invalid_entries = sorted(
        {
            str(entry.get("entry_no") or entry.get("id"))
            for entry in referenced_entries
            if not entry.get("entry_hash") or not verify_journal_entry_hash(entry)
        }
    )
    if invalid_entries:
        blockers.append(
            {
                "code": "linked_journal_integrity_failed",
                "message": f"Bağlı yevmiye kayıtlarının bütünlük doğrulaması başarısız: {', '.join(invalid_entries[:10])}",
            }
        )

    return {
        "business_date": selected,
        "healthy": not blockers,
        "mapping_enabled": bool(mapping.get("enabled")),
        "blockers": blockers,
        "warnings": warnings,
        "folios": {
            "payment_count": len(payments),
            "payment_total": _reconciliation_amount(payment_total_minor),
            "gl_total": _reconciliation_amount(sum(night_gl_by_account.values())),
            "variance": _reconciliation_amount(payment_variance_minor),
            "by_account": {
                code: _reconciliation_amount(amount)
                for code, amount in sorted(payment_by_account.items())
            },
        },
        "pos": {
            "direct_count": len(direct_pos),
            "folio_path_count": len(pos_transactions) - len(direct_pos),
            "total": _reconciliation_amount(pos_total_minor),
            "gl_total": _reconciliation_amount(pos_gl_total_minor),
            "closure_count": len(pos_closures),
        },
        "bank": {
            "matched_count": len(matched_bank),
            "unmatched_count": len(unmatched_bank),
            "matched_total": _reconciliation_amount(bank_total_minor),
            "gl_total": _reconciliation_amount(bank_gl_total_minor),
        },
        "cashier": {
            "shift_count": len(cashier_shifts),
            "open_count": open_cashier_count,
            "difference": _reconciliation_amount(cashier_difference_minor),
        },
        "journal": {
            "linked_entry_count": len({entry.get("id") for entry in referenced_entries}),
            "invalid_entry_count": len(invalid_entries),
        },
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


async def create_journal(payload: JournalIn, current_user: User = Depends(get_current_user)):
    """Trusted compatibility helper used by accounting-domain tests.

    Manual HTTP clients must use the voucher lifecycle.  Keeping the posting
    helper undecorated lets older internal callers be migrated without
    exposing a maker-checker bypass over the public API.
    """
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


@router.post("/journal", status_code=410)
async def reject_legacy_manual_journal(current_user: User = Depends(get_current_user)):
    """Reject the former direct manual-post route.

    Operational integrations post through the shared GL kernel; human-entered
    documents must follow draft -> submit -> approve -> post under /vouchers.
    """
    _require_role(current_user, _GL_ROLES)
    raise HTTPException(
        status_code=410,
        detail="Doğrudan yevmiye kaydı kapatıldı. Taslak fiş oluşturup onay akışını kullanın.",
    )


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
@router.get("/integrations/nilvera/settings")
async def get_nilvera_accounting_settings(
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    return {"settings": await get_nilvera_gl_settings(_tenant_of(current_user))}


@router.put("/integrations/nilvera/settings")
async def update_nilvera_accounting_settings(
    payload: NilveraGLSettingsIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    before = await get_nilvera_gl_settings(tenant_id)
    try:
        settings = await save_nilvera_gl_settings(
            tenant_id,
            payload.model_dump(),
            actor=_actor_id(current_user),
        )
    except InvoiceGLBridgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gl_nilvera_mapping_updated",
        entity_type="gl_nilvera_settings",
        entity_id=tenant_id,
        details="Nilvera muhasebe eşlemesi ve otomasyon modu güncellendi",
        before_value=before,
        after_value=settings,
        db=db,
    )
    return {"settings": settings}


@router.get("/integrations/nilvera/queue")
async def get_nilvera_accounting_queue(
    status: Literal["pending", "processing", "posted", "blocked", "reversed", "not_applicable"] | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    items = await list_nilvera_gl_queue(tenant_id, status=status, limit=limit)
    counts: dict[str, int] = {}
    for item in items:
        key = item.get("status") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return {"items": items, "counts": counts}


@router.post("/integrations/nilvera/queue/{item_id}/post")
async def post_nilvera_accounting_queue_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _GL_ROLES)
    try:
        item = await process_nilvera_gl_queue_item(
            _tenant_of(current_user),
            item_id,
            actor=_actor_id(current_user),
        )
    except InvoiceGLBridgeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"item": item}


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
            other_tax_account_code=payload.other_tax_account_code,
            deduction_account_code=payload.deduction_account_code,
            other_tax_accounts_by_code=payload.other_tax_accounts_by_code,
            deduction_accounts_by_code=payload.deduction_accounts_by_code,
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
        "variance": {key: _variance(current["totals"][f"{key}_minor"], comparison["totals"][f"{key}_minor"]) for key in ("revenue", "expenses", "net_income")},
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


@router.get("/e-ledger/settings")
async def get_eledger_settings(current_user: User = Depends(get_current_user)):
    _require_role(current_user, _READ_ROLES)
    settings = await db.gl_eledger_settings.find_one(
        {"tenant_id": _tenant_of(current_user)},
        {"_id": 0},
    )
    return {"settings": settings}


@router.put("/e-ledger/settings")
async def update_eledger_settings(
    payload: ELedgerSettingsIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _REOPEN_ROLES)
    tenant_id = _tenant_of(current_user)
    before = await db.gl_eledger_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    now = _now_iso()
    settings = {
        "tenant_id": tenant_id,
        **payload.model_dump(),
        "updated_at": now,
        "updated_by": _actor_id(current_user),
    }
    if before and before.get("created_at"):
        settings["created_at"] = before["created_at"]
        settings["created_by"] = before.get("created_by")
    else:
        settings["created_at"] = now
        settings["created_by"] = _actor_id(current_user)
    await db.gl_eledger_settings.update_one(
        {"tenant_id": tenant_id},
        {"$set": settings},
        upsert=True,
    )
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gl_eledger_settings_updated",
        entity_type="gl_eledger_settings",
        entity_id=tenant_id,
        details="e-Defter kaynak paket hazırlık bilgileri güncellendi",
        before_value=before,
        after_value=settings,
        db=db,
    )
    return {"settings": settings}


@router.get("/e-ledger/preflight")
async def eledger_preflight(
    period: str = Query(..., pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)
    try:
        return await preflight_eledger_source(db, tenant_id, period)
    except ELedgerSourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/e-ledger/source-package")
async def download_eledger_source_package(
    period: str = Query(..., pattern=r"^20\d{2}-(0[1-9]|1[0-2])$"),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    settings = await db.gl_eledger_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if not settings:
        raise HTTPException(status_code=400, detail="Önce e-Defter hazırlık bilgilerini kaydedin")
    try:
        package, manifest = await build_eledger_source_package(db, tenant_id, period, settings)
    except ELedgerSourceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=_actor_id(current_user),
        action="gl_eledger_source_package_downloaded",
        entity_type="gl_eledger_source_package",
        entity_id=f"{tenant_id}:{period}",
        details=f"{period} kaynak veri paketi indirildi; GİB gönderimi yapılmadı",
        after_value={
            "period": period,
            "entry_count": manifest["entry_count"],
            "line_count": manifest["line_count"],
            "official_edefter": False,
        },
        db=db,
    )
    filename = f"syroce-eledger-source-{period}.zip"
    return Response(
        content=package,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Syroce-Official-Edefter": "false",
        },
    )


async def _chain_properties(current_user: User) -> list[dict]:
    tenant_id = _tenant_of(current_user)
    own = await _system_db.tenants.find_one(
        {"$or": [{"tenant_id": tenant_id}, {"id": tenant_id}]},
        {
            "_id": 0,
            "chain_id": 1,
            "tenant_id": 1,
            "id": 1,
            "hotel_name": 1,
            "name": 1,
            "property_name": 1,
            "is_chain_headquarters": 1,
        },
    )
    chain_id = (own or {}).get("chain_id")
    if not chain_id:
        return [
            {
                "tenant_id": tenant_id,
                "property_name": (own or {}).get("property_name") or (own or {}).get("hotel_name") or (own or {}).get("name") or tenant_id,
            }
        ]
    tenants = await _system_db.tenants.find(
        {"chain_id": chain_id},
        {"_id": 0, "tenant_id": 1, "id": 1, "hotel_name": 1, "name": 1, "property_name": 1},
    ).to_list(500)
    return [
        {
            "tenant_id": tenant.get("tenant_id") or tenant.get("id"),
            "property_name": tenant.get("property_name") or tenant.get("hotel_name") or tenant.get("name") or tenant.get("tenant_id") or tenant.get("id"),
        }
        for tenant in tenants
        if tenant.get("tenant_id") or tenant.get("id")
    ]


async def _chain_scope(current_user: User) -> dict:
    tenant_id = _tenant_of(current_user)
    own = await _system_db.tenants.find_one(
        {"$or": [{"tenant_id": tenant_id}, {"id": tenant_id}]},
        {"_id": 0, "chain_id": 1, "is_chain_headquarters": 1},
    )
    chain_id = (own or {}).get("chain_id")
    properties = await _chain_properties(current_user)
    headquarters_tenant_id = None
    if chain_id:
        chain = await _system_db.hotel_chains.find_one(
            {"id": chain_id},
            {"_id": 0, "headquarters_tenant_id": 1},
        )
        headquarters_tenant_id = (chain or {}).get("headquarters_tenant_id")
        if not headquarters_tenant_id and (own or {}).get("is_chain_headquarters"):
            headquarters_tenant_id = tenant_id
    return {
        "tenant_id": tenant_id,
        "chain_id": chain_id,
        "properties": properties,
        "headquarters_tenant_id": headquarters_tenant_id,
    }


def _require_chain_rule_admin(current_user: User, scope: dict) -> None:
    _require_role(current_user, _REOPEN_ROLES)
    if not scope["chain_id"] or len(scope["properties"]) < 2:
        raise HTTPException(status_code=400, detail="Eliminasyon için en az iki otelli bir zincir gerekir")
    if getattr(current_user, "is_super_admin", False):
        return
    headquarters_tenant_id = scope.get("headquarters_tenant_id")
    if headquarters_tenant_id and headquarters_tenant_id != scope["tenant_id"]:
        raise HTTPException(status_code=403, detail="Eliminasyon kurallarını yalnız zincir merkezi yönetebilir")


@router.get("/chain/intercompany-rules")
async def list_intercompany_rules(current_user: User = Depends(get_current_user)):
    _require_role(current_user, _READ_ROLES)
    scope = await _chain_scope(current_user)
    if not scope["chain_id"]:
        return {"chain_id": None, "rules": [], "can_manage": False}
    rules = (
        await _system_db.gl_intercompany_rules.find(
            {"chain_id": scope["chain_id"]},
            {"_id": 0},
        )
        .sort("name", 1)
        .to_list(1000)
    )
    can_manage = bool(
        getattr(current_user, "is_super_admin", False)
        or (_role_of(current_user) in _REOPEN_ROLES and (not scope.get("headquarters_tenant_id") or scope["headquarters_tenant_id"] == scope["tenant_id"]))
    )
    return {
        "chain_id": scope["chain_id"],
        "headquarters_tenant_id": scope.get("headquarters_tenant_id"),
        "properties": scope["properties"],
        "rules": rules,
        "can_manage": can_manage,
    }


@router.post("/chain/intercompany-rules")
async def create_intercompany_rule(
    payload: IntercompanyRuleIn,
    current_user: User = Depends(get_current_user),
):
    scope = await _chain_scope(current_user)
    _require_chain_rule_admin(current_user, scope)
    if payload.tenant_a_id == payload.tenant_b_id:
        raise HTTPException(status_code=400, detail="Eliminasyonun iki tarafı farklı oteller olmalıdır")
    member_ids = {item["tenant_id"] for item in scope["properties"]}
    if payload.tenant_a_id not in member_ids or payload.tenant_b_id not in member_ids:
        raise HTTPException(status_code=400, detail="Eliminasyon tarafları aynı zincirin üyeleri olmalıdır")

    account_a, account_b = await asyncio.gather(
        _system_db.gl_accounts.find_one(
            {"tenant_id": payload.tenant_a_id, "code": payload.account_a_code},
            {"_id": 0},
        ),
        _system_db.gl_accounts.find_one(
            {"tenant_id": payload.tenant_b_id, "code": payload.account_b_code},
            {"_id": 0},
        ),
    )
    if not account_a or not account_b or account_a.get("active") is False or account_b.get("active") is False:
        raise HTTPException(status_code=400, detail="Eliminasyon hesaplarından biri aktif hesap planında bulunamadı")
    required_types = {"asset", "liability"} if payload.kind == "balance" else {"revenue", "expense"}
    actual_types = {account_a.get("type"), account_b.get("type")}
    if actual_types != required_types:
        expected = "varlık/borç" if payload.kind == "balance" else "gelir/gider"
        raise HTTPException(status_code=400, detail=f"Bu eliminasyon türü bir {expected} hesap çifti gerektirir")

    pair_key = "|".join(
        sorted(
            (
                f"{payload.tenant_a_id}:{payload.account_a_code}",
                f"{payload.tenant_b_id}:{payload.account_b_code}",
            )
        )
    )
    duplicate = await _system_db.gl_intercompany_rules.find_one(
        {"chain_id": scope["chain_id"], "pair_key": pair_key},
        {"_id": 0, "id": 1},
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Bu hesap çifti için eliminasyon kuralı zaten var")

    now = _now_iso()
    rule = {
        "id": str(uuid.uuid4()),
        "tenant_id": scope.get("headquarters_tenant_id") or scope["tenant_id"],
        "chain_id": scope["chain_id"],
        "pair_key": pair_key,
        **payload.model_dump(),
        "account_a_type": account_a["type"],
        "account_b_type": account_b["type"],
        "created_at": now,
        "created_by": _actor_id(current_user),
        "updated_at": now,
    }
    try:
        await _system_db.gl_intercompany_rules.insert_one(rule.copy())
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="Bu hesap çifti için eliminasyon kuralı zaten var") from exc
    await log_audit_event(
        tenant_id=scope["tenant_id"],
        user_id=_actor_id(current_user),
        action="gl_intercompany_rule_created",
        entity_type="gl_intercompany_rule",
        entity_id=rule["id"],
        details=f"{payload.name} eliminasyon kuralı oluşturuldu",
        after_value={key: rule[key] for key in ("chain_id", "kind", "tenant_a_id", "account_a_code", "tenant_b_id", "account_b_code")},
        db=db,
    )
    rule.pop("_id", None)
    return {"rule": rule}


@router.delete("/chain/intercompany-rules/{rule_id}")
async def delete_intercompany_rule(rule_id: str, current_user: User = Depends(get_current_user)):
    scope = await _chain_scope(current_user)
    _require_chain_rule_admin(current_user, scope)
    existing = await _system_db.gl_intercompany_rules.find_one(
        {"id": rule_id, "chain_id": scope["chain_id"]},
        {"_id": 0},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Eliminasyon kuralı bulunamadı")
    await _system_db.gl_intercompany_rules.delete_one({"id": rule_id, "chain_id": scope["chain_id"]})
    await log_audit_event(
        tenant_id=scope["tenant_id"],
        user_id=_actor_id(current_user),
        action="gl_intercompany_rule_deleted",
        entity_type="gl_intercompany_rule",
        entity_id=rule_id,
        details=f"{existing.get('name') or rule_id} eliminasyon kuralı kaldırıldı",
        before_value=existing,
        db=db,
    )
    return {"success": True, "id": rule_id}


def _report_account_amount(report: dict, account_type: str, account_code: str) -> int:
    if account_type == "asset":
        rows = report.get("assets", [])
    elif account_type == "liability":
        rows = report.get("liabilities", [])
    elif account_type == "revenue":
        rows = report.get("revenue", [])
    else:
        rows = report.get("expenses", [])
    row = next((item for item in rows if item.get("account_code") == account_code), None)
    return max(int((row or {}).get("amount_minor") or 0), 0)


@router.get("/chain/consolidated")
async def chain_consolidated_finance(
    start: str = Query(...),
    end: str = Query(...),
    as_of: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    """Chain-scoped consolidated statements; never widens beyond the user's chain_id."""
    _require_role(current_user, _READ_ROLES)
    scope = await _chain_scope(current_user)
    properties = scope["properties"]

    async def _property_finance(property_doc: dict) -> dict:
        tenant_id = property_doc["tenant_id"]
        income, balance = await asyncio.gather(
            compute_income_statement(_system_db, tenant_id, start=start, end=end),
            compute_balance_sheet(_system_db, tenant_id, as_of=as_of),
        )
        return {**property_doc, "income_report": income, "balance_report": balance}

    property_rows = await asyncio.gather(*(_property_finance(property_doc) for property_doc in properties))
    raw_totals_minor = {
        "revenue": sum(row["income_report"]["totals"]["revenue_minor"] for row in property_rows),
        "expenses": sum(row["income_report"]["totals"]["expenses_minor"] for row in property_rows),
        "net_income": sum(row["income_report"]["totals"]["net_income_minor"] for row in property_rows),
        "assets": int(round(sum(row["balance_report"]["totals"]["assets"] for row in property_rows) * 100)),
        "liabilities": int(round(sum(row["balance_report"]["totals"]["liabilities"] for row in property_rows) * 100)),
        "equity": int(round(sum(row["balance_report"]["totals"]["equity"] for row in property_rows) * 100)),
        "liabilities_and_equity": int(round(sum(row["balance_report"]["totals"]["liabilities_and_equity"] for row in property_rows) * 100)),
    }
    totals_minor = dict(raw_totals_minor)
    rules = []
    if scope["chain_id"]:
        rules = (
            await _system_db.gl_intercompany_rules.find(
                {"chain_id": scope["chain_id"], "active": True},
                {"_id": 0},
            )
            .sort("name", 1)
            .to_list(1000)
        )
    row_by_tenant = {row["tenant_id"]: row for row in property_rows}
    elimination_details = []
    remaining_amounts: dict[tuple[str, str, str], int] = {}
    for rule in rules:
        row_a = row_by_tenant.get(rule.get("tenant_a_id"))
        row_b = row_by_tenant.get(rule.get("tenant_b_id"))
        if not row_a or not row_b:
            continue
        if rule.get("kind") == "balance":
            report_a = row_a["balance_report"]
            report_b = row_b["balance_report"]
        else:
            report_a = row_a["income_report"]
            report_b = row_b["income_report"]
        key_a = (rule.get("tenant_a_id"), rule.get("account_a_type"), rule.get("account_a_code"))
        key_b = (rule.get("tenant_b_id"), rule.get("account_b_type"), rule.get("account_b_code"))
        if key_a not in remaining_amounts:
            remaining_amounts[key_a] = _report_account_amount(
                report_a,
                rule.get("account_a_type"),
                rule.get("account_a_code"),
            )
        if key_b not in remaining_amounts:
            remaining_amounts[key_b] = _report_account_amount(
                report_b,
                rule.get("account_b_type"),
                rule.get("account_b_code"),
            )
        amount_a = remaining_amounts[key_a]
        amount_b = remaining_amounts[key_b]
        matched_minor = min(amount_a, amount_b)
        remaining_amounts[key_a] -= matched_minor
        remaining_amounts[key_b] -= matched_minor
        if rule.get("kind") == "balance":
            totals_minor["assets"] -= matched_minor
            totals_minor["liabilities"] -= matched_minor
            totals_minor["liabilities_and_equity"] -= matched_minor
        else:
            totals_minor["revenue"] -= matched_minor
            totals_minor["expenses"] -= matched_minor
            totals_minor["net_income"] = totals_minor["revenue"] - totals_minor["expenses"]
        elimination_details.append(
            {
                "rule_id": rule.get("id"),
                "name": rule.get("name"),
                "kind": rule.get("kind"),
                "amount_a_minor": amount_a,
                "amount_b_minor": amount_b,
                "matched_minor": matched_minor,
                "matched_amount": float(Decimal(matched_minor) / 100),
                "status": "applied" if matched_minor > 0 else "no_matching_balance",
            }
        )
    response_properties = [
        {
            "tenant_id": row["tenant_id"],
            "property_name": row["property_name"],
            "income": row["income_report"]["totals"],
            "balance": row["balance_report"]["totals"],
        }
        for row in property_rows
    ]
    applied_count = sum(1 for item in elimination_details if item["matched_minor"] > 0)
    return {
        "scope": "chain" if len(response_properties) > 1 else "single_property",
        "chain_id": scope["chain_id"],
        "property_count": len(response_properties),
        "start": start,
        "end": end,
        "as_of": as_of,
        "properties": response_properties,
        "raw_totals": {key: {"amount_minor": value, "amount": float(Decimal(value) / 100)} for key, value in raw_totals_minor.items()},
        "totals": {key: {"amount_minor": value, "amount": float(Decimal(value) / 100)} for key, value in totals_minor.items()},
        "consolidation": {
            "mode": "eliminated" if applied_count else "aggregation",
            "rule_count": len(rules),
            "applied_rule_count": applied_count,
            "intercompany_eliminations_applied": applied_count > 0,
            "eliminations": elimination_details,
            "warning": (None if applied_count else "Aktif ve eşleşen grup içi hesap bakiyesi bulunmadığı için toplamlar brüt görünür."),
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
        rows = [["Gelir", row["account_code"], row["account_name"], row["amount"]] for row in data["revenue"]] + [
            ["Gider", row["account_code"], row["account_name"], row["amount"]] for row in data["expenses"]
        ]
        return "Gelir Tablosu", ["Bölüm", "Hesap Kodu", "Hesap Adı", "Tutar"], rows
    if report == "balance_sheet":
        data = await compute_balance_sheet(db, tenant_id, as_of=as_of)
        section_names = {"assets": "Varlık", "liabilities": "Yükümlülük", "equity": "Özkaynak"}
        rows = [[section_names[section], row["account_code"], row["account_name"], row["amount"]] for section in ("assets", "liabilities", "equity") for row in data[section]]
        return "Bilanço", ["Bölüm", "Hesap Kodu", "Hesap Adı", "Tutar"], rows
    query: dict = {"tenant_id": tenant_id, "status": "posted"}
    if start or end:
        query["date"] = {}
        if start:
            query["date"]["$gte"] = start
        if end:
            query["date"]["$lte"] = end
    entries = await db.gl_journal_entries.find(query, {"_id": 0}).sort([("date", 1), ("posting_sequence", 1)]).to_list(100000)
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
