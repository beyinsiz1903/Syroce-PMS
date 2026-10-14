"""Marketplace period statements: hotel issues, agency agrees or disputes, payments settle.

Hotel (PMS JWT):   /api/marketplace/hotel/statements
Agency (portal):   /api/marketplace/v1/statements
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from pymongo import ReturnDocument

from core.agency_statements import build_statement, outstanding
from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from routers.marketplace_b2b import _require_hotel_admin, get_marketplace_agency

hotel_router = APIRouter(prefix="/api/marketplace/hotel/statements", tags=["Marketplace / Statements (hotel)"])
agency_router = APIRouter(prefix="/api/marketplace/v1/statements", tags=["Marketplace / Statements (agency)"])

OPEN_STATUSES = ("issued", "agreed", "disputed", "resolved")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("Tarih YYYY-AA-GG biçiminde olmalıdır") from exc


class StatementCreate(BaseModel):
    agency_id: str = Field(..., min_length=1)
    period_start: str
    period_end: str
    currency: str = Field("TRY", pattern="^[A-Z]{3}$")

    @field_validator("period_start", "period_end")
    @classmethod
    def _dates(cls, value: str) -> str:
        return _iso_date(value)


class PaymentCreate(BaseModel):
    amount: float = Field(..., gt=0)
    direction: str = Field(..., pattern="^(agency_to_hotel|hotel_to_agency)$")
    paid_at: str
    method: str = Field("bank_transfer", max_length=40)
    reference: str = Field("", max_length=120)

    @field_validator("paid_at")
    @classmethod
    def _date(cls, value: str) -> str:
        return _iso_date(value)


class DisputeCreate(BaseModel):
    reason: str = Field(..., min_length=5, max_length=1000)
    booking_ids: list[str] = Field(default_factory=list, max_length=500)


class ResolveRequest(BaseModel):
    note: str = Field(..., min_length=5, max_length=1000)


async def _next_number(sysdb) -> str:
    year = datetime.now(UTC).year
    counter = await sysdb.counters.find_one_and_update(
        {"_id": f"agency_statement_{year}"}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return f"EKS-{year}-{counter['seq']:04d}"


def _event(kind: str, actor: str | None, **details) -> dict:
    return {"event": kind, "actor": actor, "at": _now(), **details}


def _public(statement: dict) -> dict:
    statement.pop("_id", None)
    statement["outstanding"] = outstanding(statement)
    return statement


async def _notify_agency(sysdb, statement: dict, title: str, message: str) -> None:
    from core.agency_notify import notify_agency

    await notify_agency(
        sysdb, agency_id=statement["agency_id"], tenant_id=statement["tenant_id"], kind="statement",
        title=f"{statement['number']} · {statement.get('hotel_name') or ''}: {title}", message=message,
        preference="payment_reconciliation", reference_id=statement["id"],
    )


async def _notify_hotel(statement: dict, title: str, message: str) -> None:
    from core.agency_notify import notify_hotel

    await notify_hotel(
        statement["tenant_id"], kind="agency_statement", title=f"{statement['number']} · {statement.get('agency_name') or ''}: {title}",
        message=message, action_url="/app/agency-statements", metadata={"statement_id": statement["id"]},
    )


# ── Hotel ──────────────────────────────────────────────────────────


@hotel_router.post("")
async def issue_statement(data: StatementCreate, current_user: User = Depends(get_current_user)):
    tenant_id = _require_hotel_admin(current_user)
    if data.period_end < data.period_start:
        raise HTTPException(400, "Dönem bitişi başlangıçtan önce olamaz")
    sysdb = get_system_db()
    # The contract may have ended since; its bookings are still billable.
    contract = await sysdb.agency_contracts.find_one(
        {"tenant_id": tenant_id, "agency_id": data.agency_id, "contract_code": {"$type": "string"}},
        {"_id": 0, "agency_name": 1, "hotel_name": 1},
        sort=[("created_at", -1)],
    )
    if not contract:
        raise HTTPException(404, "Bu acenteyle marketplace sözleşmesi bulunamadı")
    duplicate = await sysdb.agency_statements.find_one({
        "tenant_id": tenant_id, "agency_id": data.agency_id, "currency": data.currency,
        "period_start": data.period_start, "period_end": data.period_end, "status": {"$in": list(OPEN_STATUSES) + ["settled"]},
    }, {"_id": 0, "number": 1})
    if duplicate:
        raise HTTPException(409, f"Bu dönem için {duplicate['number']} ekstresi zaten var; önce iptal edin")
    built = await build_statement(
        sysdb, tenant_id=tenant_id, agency_id=data.agency_id, period_start=data.period_start,
        period_end=data.period_end, currency=data.currency,
    )
    if not built["lines"]:
        raise HTTPException(400, "Bu dönemde bu para biriminde rezervasyon yok")
    statement = {
        "id": str(uuid.uuid4()),
        "number": await _next_number(sysdb),
        "tenant_id": tenant_id,
        "hotel_name": contract.get("hotel_name"),
        "agency_id": data.agency_id,
        "agency_name": contract.get("agency_name"),
        "period_start": data.period_start,
        "period_end": data.period_end,
        "currency": data.currency,
        **built,
        "status": "issued",
        "payments": [],
        "dispute": None,
        "history": [_event("issued", current_user.email)],
        "issued_at": _now(),
        "issued_by": current_user.email,
    }
    await sysdb.agency_statements.insert_one(statement)
    totals = statement["totals"]
    await _notify_agency(
        sysdb, statement, "dönem ekstresi düzenlendi",
        f"{data.period_start} – {data.period_end}: {totals['bookings']} konaklama, bakiye {totals['net_balance']:.2f} {data.currency}. Lütfen onaylayın veya itiraz edin.",
    )
    return _public(statement)


@hotel_router.get("")
async def list_hotel_statements(
    agency_id: str | None = Query(None), status: str | None = Query(None), current_user: User = Depends(get_current_user)
):
    tenant_id = _require_hotel_admin(current_user)
    query: dict = {"tenant_id": tenant_id}
    if agency_id:
        query["agency_id"] = agency_id
    if status:
        query["status"] = status
    rows = await get_system_db().agency_statements.find(query, {"_id": 0, "lines": 0}).sort("issued_at", -1).to_list(200)
    return {"items": [_public(row) for row in rows]}


@hotel_router.get("/agencies")
async def statement_agencies(current_user: User = Depends(get_current_user)):
    """Marketplace agencies this hotel has (or had) a contract with."""
    tenant_id = _require_hotel_admin(current_user)
    rows = await get_system_db().agency_contracts.find(
        {"tenant_id": tenant_id, "contract_code": {"$type": "string"}, "status": {"$in": ["approved", "terminated", "expired"]}},
        {"_id": 0, "agency_id": 1, "agency_name": 1},
    ).to_list(500)
    unique = {row["agency_id"]: row.get("agency_name") for row in rows if row.get("agency_id")}
    return {"agencies": [{"id": key, "name": name} for key, name in sorted(unique.items(), key=lambda item: str(item[1]))]}


async def _hotel_statement(statement_id: str, tenant_id: str) -> dict:
    statement = await get_system_db().agency_statements.find_one({"id": statement_id, "tenant_id": tenant_id}, {"_id": 0})
    if not statement:
        raise HTTPException(404, "Ekstre bulunamadı")
    return statement


@hotel_router.get("/{statement_id}")
async def get_hotel_statement(statement_id: str, current_user: User = Depends(get_current_user)):
    return _public(await _hotel_statement(statement_id, _require_hotel_admin(current_user)))


@hotel_router.post("/{statement_id}/payments")
async def record_payment(statement_id: str, data: PaymentCreate, current_user: User = Depends(get_current_user)):
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    statement = await _hotel_statement(statement_id, tenant_id)
    if statement["status"] in ("void", "issued", "disputed"):
        raise HTTPException(409, "Ödeme yalnız acentenin onayladığı veya itirazı çözülmüş ekstreye kaydedilir")
    payment = {"id": str(uuid.uuid4()), **data.model_dump(), "recorded_by": current_user.email, "recorded_at": _now()}
    remaining = outstanding({**statement, "payments": [*statement.get("payments", []), payment]})
    status = "settled" if abs(remaining) < 0.01 else statement["status"]
    updated = await sysdb.agency_statements.find_one_and_update(
        {"id": statement_id, "tenant_id": tenant_id, "status": statement["status"]},
        {"$push": {"payments": payment, "history": _event("payment", current_user.email, amount=data.amount, direction=data.direction)},
         "$set": {"status": status}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Ekstre eş zamanlı değişti; yenileyin")
    await _notify_agency(sysdb, updated, "ödeme kaydedildi",
                         f"{data.amount:.2f} {updated['currency']} ({data.paid_at}). Kalan: {outstanding(updated):.2f}")
    return _public(updated)


@hotel_router.post("/{statement_id}/resolve")
async def resolve_dispute(statement_id: str, data: ResolveRequest, current_user: User = Depends(get_current_user)):
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    updated = await sysdb.agency_statements.find_one_and_update(
        {"id": statement_id, "tenant_id": tenant_id, "status": "disputed"},
        {"$set": {"status": "resolved", "resolution": {"note": data.note, "by": current_user.email, "at": _now()}},
         "$push": {"history": _event("resolved", current_user.email, note=data.note)}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Yalnız itiraz edilmiş ekstre çözülebilir")
    await _notify_agency(sysdb, updated, "itiraz yanıtlandı", data.note)
    return _public(updated)


@hotel_router.post("/{statement_id}/void")
async def void_statement(statement_id: str, data: ResolveRequest, current_user: User = Depends(get_current_user)):
    """Cancel a statement (e.g. to reissue after a dispute). Paid statements cannot be voided."""
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    updated = await sysdb.agency_statements.find_one_and_update(
        {"id": statement_id, "tenant_id": tenant_id, "status": {"$in": list(OPEN_STATUSES)}, "payments.0": {"$exists": False}},
        {"$set": {"status": "void", "voided": {"note": data.note, "by": current_user.email, "at": _now()}},
         "$push": {"history": _event("void", current_user.email, note=data.note)}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Ödeme kaydı olan veya kapanmış ekstre iptal edilemez")
    await _notify_agency(sysdb, updated, "ekstre iptal edildi", data.note)
    return _public(updated)


# ── Agency ─────────────────────────────────────────────────────────


@agency_router.get("")
async def list_agency_statements(agency: dict = Depends(get_marketplace_agency)):
    rows = await get_system_db().agency_statements.find(
        {"agency_id": agency["agency_id"], "status": {"$ne": "void"}}, {"_id": 0, "lines": 0}
    ).sort("issued_at", -1).to_list(200)
    return {"items": [_public(row) for row in rows]}


async def _agency_statement(statement_id: str, agency_id: str) -> dict:
    statement = await get_system_db().agency_statements.find_one({"id": statement_id, "agency_id": agency_id}, {"_id": 0})
    if not statement:
        raise HTTPException(404, "Ekstre bulunamadı")
    return statement


@agency_router.get("/{statement_id}")
async def get_agency_statement(statement_id: str, agency: dict = Depends(get_marketplace_agency)):
    return _public(await _agency_statement(statement_id, agency["agency_id"]))


@agency_router.post("/{statement_id}/agree")
async def agree_statement(statement_id: str, agency: dict = Depends(get_marketplace_agency)):
    sysdb = get_system_db()
    actor = agency.get("contact_email") or agency["agency_id"]
    updated = await sysdb.agency_statements.find_one_and_update(
        {"id": statement_id, "agency_id": agency["agency_id"], "status": {"$in": ["issued", "resolved"]}},
        {"$set": {"status": "agreed", "agreed_at": _now(), "agreed_by": actor},
         "$push": {"history": _event("agreed", actor)}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Bu ekstre şu anda onaylanamaz")
    await _notify_hotel(updated, "acente mutabakatı onayladı", f"Bakiye {outstanding(updated):.2f} {updated['currency']}")
    return _public(updated)


@agency_router.post("/{statement_id}/dispute")
async def dispute_statement(statement_id: str, data: DisputeCreate, agency: dict = Depends(get_marketplace_agency)):
    sysdb = get_system_db()
    statement = await _agency_statement(statement_id, agency["agency_id"])
    known = {line["booking_id"] for line in statement.get("lines", [])}
    if set(data.booking_ids) - known:
        raise HTTPException(400, "İtiraz edilen rezervasyonlar ekstrede yer almalıdır")
    actor = agency.get("contact_email") or agency["agency_id"]
    updated = await sysdb.agency_statements.find_one_and_update(
        {"id": statement_id, "agency_id": agency["agency_id"], "status": {"$in": ["issued", "resolved"]}},
        {"$set": {"status": "disputed", "dispute": {"reason": data.reason, "booking_ids": data.booking_ids, "by": actor, "at": _now()}},
         "$push": {"history": _event("disputed", actor, reason=data.reason)}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Bu ekstreye şu anda itiraz edilemez")
    await _notify_hotel(updated, "acente itiraz etti", data.reason)
    return _public(updated)
