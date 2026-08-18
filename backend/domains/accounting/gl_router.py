"""
Accounting / Genel Muhasebe (GL) — Hesap planı + çift-taraflı yevmiye + mizan
=============================================================================
Hesap planı (chart of accounts) yönetimi, dengeli yevmiye fişi gönderimi ve
mizan (trial balance) raporu. Posting çekirdeği shared_kernel.gl_posting'tedir.

Tüm uçlar tenant-scoped; mutasyonlar muhasebe seviyesi RBAC. PII/secret loglanmaz.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.database import db
from core.integrations.invoice_gl_bridge import (
    InvoiceGLBridgeError,
    get_incoming_invoice_gl_link,
    post_incoming_invoice_to_gl,
)
from core.security import get_current_user
from models.schemas import User
from shared_kernel.gl_posting import (
    ACCOUNT_TYPES,
    GLPostingError,
    compute_trial_balance,
    normal_balance,
    post_journal_entry,
)
from shared_kernel.pos_idem import ensure_compound_unique

logger = logging.getLogger("domains.accounting.gl")

router = APIRouter(prefix="/api/gl", tags=["Accounting / GL"])

_GL_ROLES = {"super_admin", "admin", "finance"}
_READ_ROLES = {"super_admin", "admin", "finance", "supervisor"}

_DEFAULT_CHART_OF_ACCOUNTS = (
    ("100", "Kasa", "asset"),
    ("102", "Bankalar", "asset"),
    ("108", "Diğer Hazır Değerler (Kredi Kartı)", "asset"),
    ("120", "Alıcılar", "asset"),
    ("150", "İlk Madde ve Malzeme", "asset"),
    ("153", "Ticari Mallar", "asset"),
    ("320", "Satıcılar", "liability"),
    ("335", "Personele Borçlar", "liability"),
    ("336", "Diğer Çeşitli Borçlar", "liability"),
    ("360", "Ödenecek Vergi ve Fonlar", "liability"),
    ("391", "Hesaplanan KDV", "liability"),
    ("600", "Yurtiçi Satışlar (Oda/F&B Geliri)", "revenue"),
    ("740", "Hizmet Üretim Maliyeti", "expense"),
    ("770", "Genel Yönetim Giderleri", "expense"),
)


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
# Hesap planı (Chart of Accounts)
# ─────────────────────────────────────────────────────────────────────
class AccountIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., max_length=20)
    parent_code: str | None = Field(None, max_length=40)
    active: bool = True


class AccountUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    parent_code: str | None = Field(None, max_length=40)
    active: bool | None = None


@router.get("/accounts")
async def list_accounts(
    include_inactive: bool = Query(True),
    type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
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
        "normal_balance": normal_balance(payload.type),
        "parent_code": (payload.parent_code or "").strip() or None,
        "active": payload.active,
        "created_at": now,
        "updated_at": now,
        "created_by": _actor_id(current_user),
    }
    await db.gl_accounts.insert_one(dict(doc))
    doc.pop("_id", None)
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
    for code, name, account_type in _DEFAULT_CHART_OF_ACCOUNTS:
        now = _now_iso()
        result = await db.gl_accounts.update_one(
            {"tenant_id": tenant_id, "code": code},
            {
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "code": code,
                    "name": name,
                    "type": account_type,
                    "normal_balance": normal_balance(account_type),
                    "parent_code": None,
                    "active": True,
                    "created_at": now,
                    "updated_at": now,
                    "created_by": _actor_id(current_user),
                }
            },
            upsert=True,
        )
        if getattr(result, "upserted_id", None) is not None:
            created += 1
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
    return {
        "created": created,
        "total": len(_DEFAULT_CHART_OF_ACCOUNTS),
        "payroll_mapping_created": mapping_created,
    }


@router.put("/accounts/{code}")
async def update_account(code: str, payload: AccountUpdate, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    updates = dict(payload.model_dump(exclude_unset=True))
    if "name" in updates and updates["name"]:
        updates["name"] = updates["name"].strip()
    if not updates:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")
    updates["updated_at"] = _now_iso()
    res = await db.gl_accounts.update_one({"tenant_id": tenant_id, "code": code}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Hesap bulunamadı")
    doc = await db.gl_accounts.find_one({"tenant_id": tenant_id, "code": code}, {"_id": 0})
    return {"account": doc}


# ─────────────────────────────────────────────────────────────────────
# Yevmiye fişleri
# ─────────────────────────────────────────────────────────────────────
class JournalLineIn(BaseModel):
    account_code: str = Field(..., min_length=1, max_length=40)
    debit: float = Field(0, ge=0)
    credit: float = Field(0, ge=0)
    memo: str | None = Field(None, max_length=300)


class JournalIn(BaseModel):
    date: str | None = Field(None, max_length=40)
    memo: str = Field(..., min_length=1, max_length=500)
    lines: list[JournalLineIn] = Field(..., min_length=2, max_length=500)
    source: str = Field("manual", max_length=40)
    source_ref: str | None = Field(None, max_length=120)
    idempotency_key: str | None = Field(None, max_length=120)


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
    tenant_id = _tenant_of(current_user)
    doc = await db.gl_journal_entries.find_one({"tenant_id": tenant_id, "id": entry_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Fiş bulunamadı")
    return {"entry": doc}


@router.post("/journal")
async def create_journal(payload: JournalIn, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _GL_ROLES)
    tenant_id = _tenant_of(current_user)
    try:
        entry = await post_journal_entry(
            db,
            tenant_id,
            date=payload.date,
            memo=payload.memo.strip(),
            lines=[ln.model_dump() for ln in payload.lines],
            source=payload.source,
            source_ref=payload.source_ref,
            actor=_actor_id(current_user),
            idempotency_key=(payload.idempotency_key or "").strip() or None,
        )
    except GLPostingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"entry": entry}


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

