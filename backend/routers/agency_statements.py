"""Marketplace period statements between a hotel and an agency, symmetric.

Either party issues a statement (or the monthly job does, as "system"); the
issuer has agreed to what it issued, the other party agrees or disputes, and
a statement is "agreed" once both parties agreed to the same revision. Every
amount change (a line correction, by either party, with a reason) bumps the
revision and asks the other party again.

Money moves the same way in both directions: the party that owes reports a
payment (with a proof), the party that is owed verifies or rejects it, and
only the party that is owed may record a payment it received directly.

Hotel (PMS JWT):   /api/marketplace/hotel/statements
Agency (portal):   /api/marketplace/v1/statements
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.agency_statements import apply_adjustment, build_statement, outstanding, statement_totals
from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from routers.marketplace_b2b import _require_hotel_admin, get_marketplace_agency

hotel_router = APIRouter(prefix="/api/marketplace/hotel/statements", tags=["Marketplace / Statements (hotel)"])
agency_router = APIRouter(prefix="/api/marketplace/v1/statements", tags=["Marketplace / Statements (agency)"])

OPEN_STATUSES = ("issued", "agreed", "disputed", "resolved")
ADJUSTABLE = ("issued", "disputed", "resolved")
NOTICE_PAYABLE = ("agreed", "resolved")
SIDES = ("hotel", "agency")
SIDE_LABEL = {"hotel": "otel", "agency": "acente", "system": "sistem"}
LOCK_TTL_SECONDS = 120


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("Tarih YYYY-AA-GG biçiminde olmalıdır") from exc


# ── Requests ───────────────────────────────────────────────────────


class LineAdjustment(BaseModel):
    """Signed correction of one line: + the agency owes more, - less."""

    booking_id: str = Field(..., min_length=1)
    amount: float = Field(..., ge=-10_000_000, le=10_000_000)
    reason: str = Field("", max_length=300)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return value.strip()


class _Period(BaseModel):
    period_start: str
    period_end: str
    currency: str = Field("TRY", pattern="^[A-Z]{3}$")
    adjustments: list[LineAdjustment] = Field(default_factory=list, max_length=500)
    # What the issuer saw in the preview: issue refuses anything else.
    # The signature covers every line (booking, status, amounts, correction).
    expected_signature: str | None = Field(None, max_length=128)
    expected_net_balance: float | None = None

    @field_validator("period_start", "period_end")
    @classmethod
    def _dates(cls, value: str) -> str:
        return _iso_date(value)


class StatementCreate(_Period):
    """Hotel issues for one agency."""

    agency_id: str = Field(..., min_length=1)


class AgencyStatementCreate(_Period):
    """Agency issues for one hotel."""

    tenant_id: str = Field(..., min_length=1)


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


class AgreeRequest(BaseModel):
    # The statement version the party looked at; a correction since is refused.
    revision: int = Field(..., ge=1)


class NoticeDecision(BaseModel):
    note: str = Field("", max_length=500)


class NoticeRejection(BaseModel):
    note: str = Field(..., min_length=5, max_length=500)


# ── Parties and statement state ────────────────────────────────────


@dataclass(frozen=True)
class Party:
    side: str  # "hotel" | "agency"
    actor: str
    tenant_id: str | None = None
    agency_id: str | None = None

    @property
    def owner(self) -> dict:
        return {"tenant_id": self.tenant_id} if self.side == "hotel" else {"agency_id": self.agency_id}


def _hotel_party(current_user: User) -> Party:
    return Party("hotel", current_user.email, tenant_id=_require_hotel_admin(current_user))


def _agency_party(agency: dict) -> Party:
    actor = (agency.get("user") or {}).get("email") or agency.get("contact_email") or agency["agency_id"]
    return Party("agency", actor, agency_id=agency["agency_id"])


def _other(side: str) -> str:
    return "agency" if side == "hotel" else "hotel"


def _issuer(statement: dict) -> str:
    return statement.get("issuer") or "hotel"  # statements before both sides could issue


def _agreements(statement: dict) -> dict:
    """Revision each party agreed to (None: not agreed)."""
    if isinstance(statement.get("agreements"), dict):
        return {side: statement["agreements"].get(side) for side in SIDES}
    revision = statement.get("revision") or 1
    agreed = statement.get("status") in ("agreed", "settled")
    return {"hotel": revision, "agency": revision if agreed else None}


def _revision(statement: dict) -> dict:
    """Filter for exactly the version that was read: every amount change
    (line correction) bumps ``revision``; legacy statements have none."""
    return {"revision": statement.get("revision")}


def _version(statement: dict) -> dict:
    """Revision, status and agreements as read: any party's action since
    makes a conditional write miss."""
    return {**_revision(statement), "status": statement["status"], "agreements": statement.get("agreements")}


def _debtor(statement: dict) -> str | None:
    balance = outstanding(statement)
    if abs(balance) < 0.01:
        return None
    return "agency" if balance > 0 else "hotel"


def _public(statement: dict) -> dict:
    statement.pop("_id", None)
    statement["outstanding"] = outstanding(statement)
    statement["revision"] = statement.get("revision") or 1
    statement["issuer"] = _issuer(statement)
    statement["agreements"] = _agreements(statement)
    # Storage paths of payment proofs never leave the server.
    statement["payment_notices"] = [
        {**{k: v for k, v in notice.items() if k != "proof_path"}, "has_proof": bool(notice.get("proof_path")),
         "direction": notice.get("direction") or "agency_to_hotel"}
        for notice in statement.get("payment_notices") or []
    ]
    return statement


async def _load(statement_id: str, party: Party, sysdb=None) -> dict:
    statement = await (sysdb or get_system_db()).agency_statements.find_one({"id": statement_id, **party.owner}, {"_id": 0})
    if not statement:
        raise HTTPException(404, "Ekstre bulunamadı")
    return statement


async def _hotel_statement(statement_id: str, tenant_id: str) -> dict:
    return await _load(statement_id, Party("hotel", "", tenant_id=tenant_id))


async def _agency_statement(statement_id: str, agency_id: str) -> dict:
    return await _load(statement_id, Party("agency", "", agency_id=agency_id))


async def _notify_agency(sysdb, statement: dict, title: str, message: str) -> None:
    from core.agency_notify import notify_agency

    await notify_agency(
        sysdb, agency_id=statement["agency_id"], tenant_id=statement["tenant_id"], kind="statement",
        title=f"{statement['number']} · {statement.get('hotel_name') or ''}: {title}", message=message,
        preference="payment_reconciliation", reference_id=statement["id"],
    )


async def _notify_hotel(statement: dict, title: str, message: str, database=None) -> None:
    from core.agency_notify import notify_hotel

    await notify_hotel(
        statement["tenant_id"], kind="agency_statement", title=f"{statement['number']} · {statement.get('agency_name') or ''}: {title}",
        message=message, action_url="/app/agency-statements", metadata={"statement_id": statement["id"]}, database=database,
    )


async def _notify(sysdb, statement: dict, to_side: str, title: str, message: str, *, direct_db: bool = False) -> None:
    if to_side == "agency":
        await _notify_agency(sysdb, statement, title, message)
    else:
        await _notify_hotel(statement, title, message, database=sysdb if direct_db else None)


def _event(kind: str, actor: str | None, **details) -> dict:
    return {"event": kind, "actor": actor, "at": _now(), **details}


# ── Issue (either party, or the monthly job) ───────────────────────


async def _next_number(sysdb) -> str:
    year = datetime.now(UTC).year
    counter = await sysdb.counters.find_one_and_update(
        {"_id": f"agency_statement_{year}"}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return f"EKS-{year}-{counter['seq']:04d}"


async def _statement_contract(sysdb, tenant_id: str, agency_id: str) -> dict:
    # The contract may have ended since; its bookings are still billable.
    contract = await sysdb.agency_contracts.find_one(
        {"tenant_id": tenant_id, "agency_id": agency_id, "contract_code": {"$type": "string"}},
        {"_id": 0, "agency_name": 1, "hotel_name": 1},
        sort=[("created_at", -1)],
    )
    if not contract:
        raise HTTPException(404, "Bu otel ile acente arasında marketplace sözleşmesi bulunamadı")
    return contract


async def _overlapping_statement(sysdb, tenant_id: str, data) -> dict | None:
    # Any overlap would bill the same stays twice (e.g. 1-31 Oct and 15-31 Oct).
    return await sysdb.agency_statements.find_one({
        "tenant_id": tenant_id, "agency_id": data.agency_id, "currency": data.currency,
        "period_start": {"$lte": data.period_end}, "period_end": {"$gte": data.period_start},
        "status": {"$in": list(OPEN_STATUSES) + ["settled"]},
    }, {"_id": 0, "number": 1, "period_start": 1, "period_end": 1})


def _overlap_error(duplicate: dict) -> HTTPException:
    return HTTPException(
        409, f"Bu dönem {duplicate['number']} ekstresiyle ({duplicate['period_start']} – {duplicate['period_end']}) çakışıyor; önce onu iptal edin"
    )


@asynccontextmanager
async def _issue_lock(sysdb, tenant_id: str, agency_id: str, currency: str):
    """Serialize issuing per hotel/agency/currency so two concurrent issues
    (hotel, agency, monthly job) cannot both pass the overlap check. A
    crashed holder expires."""
    key = f"{tenant_id}:{agency_id}:{currency}"
    for _ in range(2):
        try:
            await sysdb.agency_statement_locks.insert_one({"_id": key, "created_at": _now()})
            break
        except DuplicateKeyError:
            stale_before = datetime.fromtimestamp(datetime.now(UTC).timestamp() - LOCK_TTL_SECONDS, UTC).isoformat()
            removed = await sysdb.agency_statement_locks.delete_one({"_id": key, "created_at": {"$lt": stale_before}})
            if not removed.deleted_count:
                raise HTTPException(409, "Bu otel–acente için başka bir ekstre şu an düzenleniyor; birazdan tekrar deneyin") from None
    else:
        raise HTTPException(409, "Bu otel–acente için başka bir ekstre şu an düzenleniyor; birazdan tekrar deneyin")
    try:
        yield
    finally:
        await sysdb.agency_statement_locks.delete_one({"_id": key})


def statement_signature(built: dict) -> str:
    """Fingerprint of the bookings and amounts a statement would contain."""
    import hashlib
    import json

    keys = ("booking_id", "status", "payment_terms", "gross", "penalty", "commission", "agency_owes_hotel", "hotel_owes_agency")
    lines = [[*(line.get(k) for k in keys), (line.get("adjustment") or {}).get("amount"), (line.get("adjustment") or {}).get("reason")]
             for line in built["lines"]]
    payload = json.dumps([lines, built["totals"].get("net_balance")], sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _with_adjustments(lines: list[dict], adjustments: list[LineAdjustment], actor: str, side: str) -> list[dict]:
    by_id = {line.get("booking_id"): index for index, line in enumerate(lines)}
    lines = list(lines)
    for item in adjustments:
        if item.booking_id not in by_id:
            raise HTTPException(400, "Düzeltilen rezervasyon bu ekstrede yok")
        if abs(item.amount) >= 0.01 and len(item.reason) < 5:
            raise HTTPException(422, "Her düzeltme için en az 5 karakterlik gerekçe yazın")
        index = by_id[item.booking_id]
        line = apply_adjustment(lines[index], item.amount, item.reason, actor=actor, at=_now())
        if line.get("adjustment"):
            line["adjustment"]["side"] = side
        lines[index] = line
    return lines


async def _build_checked(sysdb, tenant_id: str, data, actor: str, side: str) -> dict:
    """The statement exactly as it would be issued (shared by preview)."""
    if data.period_end < data.period_start:
        raise HTTPException(400, "Dönem bitişi başlangıçtan önce olamaz")
    built = await build_statement(
        sysdb, tenant_id=tenant_id, agency_id=data.agency_id, period_start=data.period_start,
        period_end=data.period_end, currency=data.currency,
    )
    if not built["lines"]:
        raise HTTPException(400, "Bu dönemde bu para biriminde rezervasyon yok")
    # A stay moved to another period after billing must not be billed again.
    ids = [line["booking_id"] for line in built["lines"] if line.get("booking_id")]
    billed = await sysdb.agency_statements.find_one(
        {"tenant_id": tenant_id, "agency_id": data.agency_id, "status": {"$ne": "void"}, "lines.booking_id": {"$in": ids}},
        {"_id": 0, "number": 1, "lines.booking_id": 1, "lines.confirmation_code": 1},
    )
    if billed:
        codes = sorted({line.get("confirmation_code") or line["booking_id"] for line in billed.get("lines", []) if line.get("booking_id") in ids})
        raise HTTPException(409, f"{', '.join(codes)} zaten {billed['number']} ekstresinde; önce o ekstreyi iptal edin")
    lines = _with_adjustments(built["lines"], data.adjustments, actor, side)
    return {"lines": lines, "totals": statement_totals(lines)}


async def _preview(sysdb, tenant_id: str, data, actor: str, side: str) -> dict:
    contract = await _statement_contract(sysdb, tenant_id, data.agency_id)
    duplicate = await _overlapping_statement(sysdb, tenant_id, data)
    if duplicate:
        raise _overlap_error(duplicate)
    built = await _build_checked(sysdb, tenant_id, data, actor, side)
    return {"tenant_id": tenant_id, "agency_id": data.agency_id, "agency_name": contract.get("agency_name"),
            "hotel_name": contract.get("hotel_name"), "period_start": data.period_start, "period_end": data.period_end,
            "currency": data.currency, **built, "outstanding": built["totals"]["net_balance"],
            "signature": statement_signature(built)}


async def _issue(sysdb, tenant_id: str, data, *, issuer: str, actor: str, direct_notify: bool = False,
                 skip_empty: bool = False) -> dict:
    """Create a statement. The issuing party has agreed to what it issued;
    a "system" (monthly job) statement waits for both parties."""
    if data.period_end < data.period_start:
        raise HTTPException(400, "Dönem bitişi başlangıçtan önce olamaz")
    contract = await _statement_contract(sysdb, tenant_id, data.agency_id)
    async with _issue_lock(sysdb, tenant_id, data.agency_id, data.currency):
        duplicate = await _overlapping_statement(sysdb, tenant_id, data)
        if duplicate:
            raise _overlap_error(duplicate)
        built = await _build_checked(sysdb, tenant_id, data, actor, issuer)
        if skip_empty and not built["totals"].get("bookings") and abs(built["totals"].get("net_balance") or 0) < 0.01:
            raise HTTPException(400, "Bu dönemde hesaba katılacak tutar yok")
        changed = (data.expected_signature is not None and data.expected_signature != statement_signature(built)) or (
            data.expected_net_balance is not None and abs(built["totals"]["net_balance"] - data.expected_net_balance) >= 0.01)
        if changed:
            raise HTTPException(409, "Ekstre önizlemede gösterilenden farklı hesaplandı (rezervasyonlar veya düzeltmeler değişti); yeniden önizleyin")
        agreements = {side: (1 if side == issuer else None) for side in SIDES}
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
            "issuer": issuer,
            "revision": 1,
            "agreements": agreements,
            "payments": [],
            "dispute": None,
            "history": [_event("issued", actor, issuer=issuer,
                               adjustments=len([a for a in data.adjustments if abs(a.amount) >= 0.01]))],
            "issued_at": _now(),
            "issued_by": actor,
        }
        await sysdb.agency_statements.insert_one(statement)
    totals = statement["totals"]
    summary = (f"{data.period_start} – {data.period_end}: {totals['bookings']} konaklama, bakiye "
               f"{totals['net_balance']:.2f} {data.currency}. Lütfen kontrol edip onaylayın veya itiraz edin.")
    title = "dönem ekstresi düzenlendi" if issuer != "system" else "aylık ekstre otomatik düzenlendi"
    for side in SIDES:
        if side != issuer:
            await _notify(sysdb, statement, side, title, summary, direct_db=direct_notify)
    return _public(statement)


# ── Agreement, dispute, correction, void (either party) ────────────


async def _agree(statement_id: str, revision: int, party: Party) -> dict:
    sysdb = get_system_db()
    statement = await _load(statement_id, party)
    if statement["status"] not in ("issued", "resolved"):
        raise HTTPException(409, "Bu ekstre şu anda onaylanamaz")
    current = statement.get("revision") or 1
    if current != revision:
        raise HTTPException(409, f"{SIDE_LABEL[_other(party.side)].capitalize()} bu ekstrede değişiklik yaptı; güncel satırları kontrol edip yeniden onaylayın")
    agreements = _agreements(statement)
    if agreements.get(party.side) == current:
        raise HTTPException(409, f"Bu sürümü zaten onayladınız; {SIDE_LABEL[_other(party.side)]} onayı bekleniyor")
    agreements[party.side] = current
    both = all(agreements.get(side) == current for side in SIDES)
    updates: dict = {"agreements": agreements, "updated_at": _now()}
    if both:
        updates.update(status="agreed", agreed_at=_now(), agreed_by=party.actor)
    updated = await sysdb.agency_statements.find_one_and_update(
        {"id": statement_id, **party.owner, **_version(statement)},
        {"$set": updates, "$push": {"history": _event("agreed", party.actor, side=party.side, revision=revision)}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Ekstre eş zamanlı değişti; yenileyip tekrar deneyin")
    other = _other(party.side)
    message = (f"Mutabakat tamamlandı. Bakiye {outstanding(updated):.2f} {updated['currency']}" if both
               else f"{SIDE_LABEL[party.side].capitalize()} onayladı; sizin onayınız bekleniyor. Bakiye {outstanding(updated):.2f} {updated['currency']}")
    await _notify(sysdb, updated, other, f"{SIDE_LABEL[party.side]} mutabakatı onayladı", message)
    return _public(updated)


async def _dispute(statement_id: str, data: DisputeCreate, party: Party) -> dict:
    sysdb = get_system_db()
    statement = await _load(statement_id, party)
    if _issuer(statement) == party.side:
        raise HTTPException(409, "Kendi düzenlediğiniz ekstreye itiraz edemezsiniz; satırı düzeltin veya ekstreyi iptal edin")
    if statement["status"] not in ("issued", "resolved"):
        raise HTTPException(409, "Bu ekstreye şu anda itiraz edilemez")
    known = {line["booking_id"] for line in statement.get("lines", [])}
    if set(data.booking_ids) - known:
        raise HTTPException(400, "İtiraz edilen rezervasyonlar ekstrede yer almalıdır")
    agreements = {**_agreements(statement), party.side: None}
    updated = await sysdb.agency_statements.find_one_and_update(
        {"id": statement_id, **party.owner, **_version(statement)},
        {"$set": {"status": "disputed", "agreements": agreements,
                  "dispute": {"reason": data.reason, "booking_ids": data.booking_ids, "by": party.actor, "by_side": party.side, "at": _now()}},
         "$push": {"history": _event("disputed", party.actor, side=party.side, reason=data.reason)}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Ekstre eş zamanlı değişti; yenileyip tekrar deneyin")
    await _notify(sysdb, updated, _other(party.side), f"{SIDE_LABEL[party.side]} itiraz etti", data.reason)
    return _public(updated)


async def _resolve(statement_id: str, data: ResolveRequest, party: Party) -> dict:
    sysdb = get_system_db()
    statement = await _load(statement_id, party)
    disputer = (statement.get("dispute") or {}).get("by_side") or "agency"
    if statement["status"] != "disputed" or disputer == party.side:
        raise HTTPException(409, "Yalnız karşı tarafın itiraz ettiği ekstre yanıtlanabilir")
    agreements = {**_agreements(statement), party.side: statement.get("revision") or 1}
    updated = await sysdb.agency_statements.find_one_and_update(
        {"id": statement_id, **party.owner, **_version(statement)},
        {"$set": {"status": "resolved", "agreements": agreements,
                  "resolution": {"note": data.note, "by": party.actor, "side": party.side, "at": _now()}},
         "$push": {"history": _event("resolved", party.actor, side=party.side, note=data.note)}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Ekstre eş zamanlı değişti; yenileyip tekrar deneyin")
    await _notify(sysdb, updated, disputer, "itiraz yanıtlandı", data.note)
    return _public(updated)


async def _adjust(statement_id: str, data: LineAdjustment, party: Party) -> dict:
    """Correct one line of a statement not yet agreed by both parties (no
    payment recorded). 0 removes the correction. The corrector has agreed to
    the new revision; the other party is asked again."""
    sysdb = get_system_db()
    statement = await _load(statement_id, party)
    if statement["status"] not in ADJUSTABLE or statement.get("payments"):
        raise HTTPException(409, "Yalnız henüz iki tarafça onaylanmamış ve ödeme kaydı olmayan ekstre düzeltilebilir")
    lines = _with_adjustments(statement.get("lines") or [], [data], party.actor, party.side)
    totals = statement_totals(lines)
    revision = (statement.get("revision") or 1) + 1
    status = "resolved" if statement["status"] == "disputed" else statement["status"]
    agreements = {party.side: revision, _other(party.side): None}
    updated = await sysdb.agency_statements.find_one_and_update(
        # Written over exactly the version we read: a concurrent agreement,
        # dispute, payment or correction makes this write miss.
        {"id": statement_id, **party.owner, "payments.0": {"$exists": False}, **_version(statement)},
        {"$set": {"lines": lines, "totals": totals, "status": status, "updated_at": _now(), "revision": revision,
                  "agreements": agreements},
         "$push": {"history": _event("line_adjusted", party.actor, side=party.side, booking_id=data.booking_id,
                                     amount=round(data.amount, 2), reason=data.reason)}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Ekstre eş zamanlı değişti; yenileyip tekrar deneyin")
    line = next(line for line in lines if line.get("booking_id") == data.booking_id)
    what = (f"{line.get('confirmation_code')}: {data.amount:+.2f} {updated['currency']} ({data.reason})"
            if abs(data.amount) >= 0.01 else f"{line.get('confirmation_code')}: düzeltme kaldırıldı")
    await _notify(sysdb, updated, _other(party.side), "ekstrede düzeltme yapıldı",
                  f"{what}. Yeni bakiye {outstanding(updated):.2f} {updated['currency']}. Lütfen yeniden kontrol edin.")
    return _public(updated)


async def _void(statement_id: str, data: ResolveRequest, party: Party) -> dict:
    """Cancel a statement (e.g. to reissue). Only its issuer (either party
    for a monthly statement); never once a payment is recorded."""
    sysdb = get_system_db()
    current = await _load(statement_id, party)
    if _issuer(current) not in (party.side, "system"):
        raise HTTPException(403, f"Bu ekstreyi {SIDE_LABEL[_issuer(current)]} düzenledi; yalnız o iptal edebilir. İtiraz edebilirsiniz.")
    if any(n.get("status") == "pending" for n in current.get("payment_notices") or []):
        raise HTTPException(409, "Ekstrede yanıt bekleyen ödeme bildirimi var; önce doğrulayın veya reddedin")
    updated = await sysdb.agency_statements.find_one_and_update(
        {"id": statement_id, **party.owner, "status": {"$in": list(OPEN_STATUSES)}, "payments.0": {"$exists": False}},
        {"$set": {"status": "void", "voided": {"note": data.note, "by": party.actor, "side": party.side, "at": _now()}},
         "$push": {"history": _event("void", party.actor, side=party.side, note=data.note)}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Ödeme kaydı olan veya kapanmış ekstre iptal edilemez")
    await _notify(sysdb, updated, _other(party.side), "ekstre iptal edildi", data.note)
    return _public(updated)


# ── Payments: the party owed records or verifies, the payer reports ──


def _ref_key(reference) -> str:
    """One comparison for bank references on every path ("EFT-1 " == "eft-1")."""
    return " ".join(str(reference or "").split()).casefold()


def _receiver(direction: str) -> str:
    return "hotel" if direction == "agency_to_hotel" else "agency"


def _find_notice(statement: dict, notice_id: str) -> dict:
    notice = next((n for n in statement.get("payment_notices") or [] if n.get("id") == notice_id), None)
    if not notice:
        raise HTTPException(404, "Ödeme bildirimi bulunamadı")
    return notice


async def _record_payment_as(statement_id: str, data: PaymentCreate, party: Party, *, notify: bool = True,
                             notice_id: str | None = None, note: str = "") -> dict:
    """Record a payment received by ``party``. With ``notice_id`` (or a
    pending notice carrying the same reference and amount) the payment and
    the notice decision are one atomic write: both happen or neither does,
    and a concurrent decision on the notice makes this write lose."""
    if _receiver(data.direction) != party.side:
        raise HTTPException(409, "Ödemeyi yalnız parayı alan taraf kaydeder; ödeyen taraf \"Ödeme bildir\" ile bildirmeli")
    sysdb = get_system_db()
    statement = await _load(statement_id, party)
    if statement["status"] == "settled":
        raise HTTPException(409, "Ekstre kapanmış; fazla ödeme veya iade ayrı bir işlem olarak kaydedilmelidir")
    if statement["status"] not in NOTICE_PAYABLE:
        raise HTTPException(409, "Ödeme yalnız iki tarafın mutabık kaldığı veya itirazı yanıtlanmış ekstreye kaydedilir")
    previous = statement.get("payments") or []
    reference = data.reference.strip()
    key = _ref_key(reference)
    if notice_id:
        notice = _find_notice(statement, notice_id)
        if notice["status"] != "pending":
            raise HTTPException(409, "Bu bildirim zaten sonuçlandırılmış")
    else:
        notice = next((n for n in statement.get("payment_notices") or [] if key
                       and (n.get("direction") or "agency_to_hotel") == data.direction
                       and n.get("status") == "pending" and _ref_key(n.get("reference")) == key
                       and abs(float(n.get("amount") or 0) - data.amount) < 0.01), None)
    if key:
        # A resent request (integration retry, double click, other letter
        # case) must not pay twice.
        repeat = next((p for p in previous if _ref_key(p.get("reference")) == key and p.get("direction") == data.direction), None)
        if repeat:
            if abs(float(repeat.get("amount") or 0) - data.amount) >= 0.01:
                raise HTTPException(409, f"{reference} referansıyla farklı tutarda bir ödeme zaten kayıtlı")
            if notice_id:
                raise HTTPException(409, f"{reference} referansıyla ödeme zaten kayıtlı; bildirimi reddedip gerekçe yazın")
            return _public(statement)
    current = outstanding(statement)
    expected = "agency_to_hotel" if current > 0 else "hotel_to_agency"
    if data.direction != expected:
        raise HTTPException(409, "Ödeme yönü ekstre bakiyesiyle uyuşmuyor: " + (
            "acente otele borçlu" if current > 0 else "otel acenteye borçlu"))
    if data.amount - abs(current) >= 0.01:
        raise HTTPException(409, f"Ödeme kalan bakiyeyi aşıyor (kalan {abs(current):.2f} {statement.get('currency', '')})")
    payment = {"id": str(uuid.uuid4()), **data.model_dump(), "reference": reference,
               "recorded_by": party.actor, "recorded_by_side": party.side, "recorded_at": _now()}
    if notice:
        payment["notice_id"] = notice["id"]
    remaining = outstanding({**statement, "payments": [*previous, payment]})
    status = "settled" if abs(remaining) < 0.01 else statement["status"]
    # The status is derived from the payments we read: refuse the write if
    # another payment landed meanwhile, otherwise two concurrent payments that
    # together settle the balance would leave the statement open.
    guard = {f"payments.{len(previous)}": {"$exists": False}}
    if previous:
        guard[f"payments.{len(previous) - 1}.id"] = previous[-1]["id"]
    # Written over the version read: a line correction landing meanwhile
    # changes the balance this payment was checked against.
    query = {"id": statement_id, **party.owner, "status": statement["status"], **guard, **_revision(statement)}
    updates: dict = {"$push": {"payments": payment, "history": _event("payment", party.actor, side=party.side,
                                                                      amount=data.amount, direction=data.direction)},
                     "$set": {"status": status}}
    options: dict = {}
    if notice:
        query["payment_notices"] = {"$elemMatch": {"id": notice["id"], "status": "pending"}}
        updates["$set"].update({
            "payment_notices.$[n].status": "verified", "payment_notices.$[n].decided_at": _now(),
            "payment_notices.$[n].decided_by": party.actor,
            "payment_notices.$[n].note": note or ("" if notice_id else "Aynı referansla ödeme kaydedildi"),
        })
        options["array_filters"] = [{"n.id": notice["id"]}]
    updated = await sysdb.agency_statements.find_one_and_update(
        query, updates, projection={"_id": 0}, return_document=ReturnDocument.AFTER, **options,
    )
    if not updated:
        raise HTTPException(409, "Ekstre veya ödeme bildirimi eş zamanlı değişti; yenileyin")
    if notify:
        await _notify(sysdb, updated, _other(party.side), "ödeme kaydedildi",
                      f"{data.amount:.2f} {updated['currency']} ({data.paid_at}). Kalan: {outstanding(updated):.2f}")
    return _public(updated)


PROOF_TYPES = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _pending_notice_total(statement: dict, direction: str) -> float:
    return round(sum(float(n.get("amount") or 0) for n in statement.get("payment_notices") or []
                     if n.get("status") == "pending" and (n.get("direction") or "agency_to_hotel") == direction), 2)


def _reference_taken(statement: dict, reference: str) -> bool:
    key = _ref_key(reference)
    return any(_ref_key(n.get("reference")) == key and n.get("status") in ("pending", "verified")
               for n in statement.get("payment_notices") or []) or any(
        _ref_key(p.get("reference")) == key for p in statement.get("payments") or [])


async def _store_proof(statement: dict, notice_id: str, proof: UploadFile) -> str:
    from routers.uploads import PRIVATE_UPLOAD_DIR
    from security.upload_validator import MAX_DOC_BYTES, validate_document_bytes

    payload = await proof.read(MAX_DOC_BYTES + 1)
    content_type = validate_document_bytes(payload, field_label="Dekont")
    extension = PROOF_TYPES.get(content_type)
    if not extension:
        raise HTTPException(400, "Dekont yalnız PDF, JPG, PNG veya WEBP olabilir")
    # Private folder: the generic /api/uploads route refuses it, so a proof is
    # readable only through the two authorised endpoints below.
    relative = f"agency-payment-proofs/{statement['tenant_id']}/{statement['id']}/{notice_id}{extension}"
    target = PRIVATE_UPLOAD_DIR / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return relative


def _proof_response(notice: dict) -> FileResponse:
    from routers.uploads import PRIVATE_UPLOAD_DIR

    relative = notice.get("proof_path")
    if not relative:
        raise HTTPException(404, "Bu bildirimde dekont yok")
    root = PRIVATE_UPLOAD_DIR.resolve()
    target = (root / relative).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(404, "Dekont bulunamadı")
    safe_ref = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(notice.get("reference") or ""))[:60]
    return FileResponse(target, filename=f"dekont-{safe_ref or notice['id']}{target.suffix}")


async def _report_payment_as(statement_id: str, party: Party, *, amount: float, paid_at: str, reference: str,
                             method: str, proof: UploadFile | None) -> dict:
    """The party that owes reports a payment on an agreed statement. Nothing
    is credited until the party owed verifies it."""
    try:
        paid_on = _iso_date(paid_at)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if paid_on > date.today().isoformat():
        raise HTTPException(422, "Ödeme tarihi ileri bir tarih olamaz")
    sysdb = get_system_db()
    statement = await _load(statement_id, party)
    if statement["status"] not in NOTICE_PAYABLE:
        raise HTTPException(409, "Ödeme bildirimi yalnız mutabık kalınan ekstreye yapılır")
    debtor = _debtor(statement)
    if debtor != party.side:
        raise HTTPException(409, f"Bu ekstrede {SIDE_LABEL[party.side]} tarafının ödemesi gereken bakiye yok")
    direction = "agency_to_hotel" if debtor == "agency" else "hotel_to_agency"
    open_amount = round(abs(outstanding(statement)) - _pending_notice_total(statement, direction), 2)
    if amount - open_amount >= 0.01:
        raise HTTPException(409, f"Bildirilen tutar, onay bekleyen bildirimler düşüldükten sonra kalan bakiyeyi aşıyor (kalan {max(open_amount, 0):.2f} {statement['currency']})")
    reference = reference.strip()
    if _reference_taken(statement, reference):
        raise HTTPException(409, f"{reference} referansıyla bir ödeme zaten bildirilmiş veya kayıtlı")
    notice_id = str(uuid.uuid4())
    proof_path = await _store_proof(statement, notice_id, proof) if proof is not None and proof.filename else None
    notice = {"id": notice_id, "amount": round(amount, 2), "paid_at": paid_on, "reference": reference, "method": method,
              "direction": direction, "proof_path": proof_path, "status": "pending", "reported_at": _now(),
              "reported_by": party.actor, "reported_by_side": party.side}
    previous = statement.get("payment_notices") or []
    guard = {f"payment_notices.{len(previous)}": {"$exists": False}}
    updated = await sysdb.agency_statements.find_one_and_update(
        {"id": statement_id, **party.owner, "status": statement["status"], **guard},
        {"$push": {"payment_notices": notice, "history": _event("payment_reported", party.actor, side=party.side,
                                                                amount=notice["amount"], reference=reference)}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Ekstre eş zamanlı değişti; yenileyip tekrar deneyin")
    await _notify(sysdb, updated, _other(party.side), f"{SIDE_LABEL[party.side]} ödeme bildirdi",
                  f"{notice['amount']:.2f} {updated['currency']} · {paid_on} · ref {reference}. Doğrulayın veya reddedin.")
    return _public(updated)


async def _verify_notice_as(statement_id: str, notice_id: str, data: NoticeDecision, party: Party) -> dict:
    """Verified notice = a statement payment with the same bank reference,
    written together with the decision; only now do the balance and the
    agency credit change."""
    sysdb = get_system_db()
    notice = _find_notice(await _load(statement_id, party), notice_id)
    if notice["status"] != "pending":
        raise HTTPException(409, "Bu bildirim zaten sonuçlandırılmış")
    direction = notice.get("direction") or "agency_to_hotel"
    if _receiver(direction) != party.side:
        raise HTTPException(403, "Bildirimi yalnız ödemeyi alan taraf doğrulayabilir")
    payment = PaymentCreate(amount=notice["amount"], direction=direction, paid_at=notice["paid_at"],
                            method=notice.get("method") or "bank_transfer", reference=notice["reference"])
    updated = await _record_payment_as(statement_id, payment, party, notify=False, notice_id=notice_id, note=data.note.strip())
    await _notify(sysdb, updated, _other(party.side), "ödeme bildiriminiz doğrulandı",
                  f"{notice['amount']:.2f} {updated['currency']} (ref {notice['reference']}) ekstreye işlendi. Kalan: {outstanding(updated):.2f}")
    return updated


async def _reject_notice_as(statement_id: str, notice_id: str, data: NoticeRejection, party: Party) -> dict:
    sysdb = get_system_db()
    notice = _find_notice(await _load(statement_id, party), notice_id)
    if _receiver(notice.get("direction") or "agency_to_hotel") != party.side:
        raise HTTPException(403, "Bildirimi yalnız ödemeyi alan taraf reddedebilir")
    updated = await sysdb.agency_statements.find_one_and_update(
        {"id": statement_id, **party.owner, "payment_notices": {"$elemMatch": {"id": notice_id, "status": "pending"}}},
        {"$set": {"payment_notices.$.status": "rejected", "payment_notices.$.decided_at": _now(),
                  "payment_notices.$.decided_by": party.actor, "payment_notices.$.note": data.note.strip()},
         "$push": {"history": _event("payment_notice_rejected", party.actor, side=party.side, notice_id=notice_id, note=data.note.strip())}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Yanıt bekleyen ödeme bildirimi bulunamadı")
    await _notify(sysdb, updated, _other(party.side), "ödeme bildiriminiz reddedildi", f"Ref {notice['reference']}: {data.note.strip()}")
    return _public(updated)


# ── Monthly statements (system) ─────────────────────────────────────


def previous_month(today: date) -> tuple[str, str]:
    end = today.replace(day=1) - timedelta(days=1)
    return end.replace(day=1).isoformat(), end.isoformat()


async def auto_issue_previous_month(sysdb, today: date | None = None) -> dict:
    """Issue last month's statement for every hotel–agency–currency with
    marketplace stays in it, unless one already covers the period (either
    party may have issued it). Idempotent: a rerun skips what exists."""
    start, end = previous_month(today or datetime.now(UTC).date())
    pairs: set[tuple[str, str, str]] = set()
    for collection, query in (
        (sysdb.marketplace_bookings, {"check_in": {"$gte": start, "$lte": end + "T23:59:59.999999"}}),
        (sysdb.bookings, {"agency_completion.kind": "marketplace", "check_in": {"$gte": start, "$lte": end + "T23:59:59.999999"}}),
    ):
        async for row in collection.find({**query, "agency_id": {"$nin": [None, ""]}}, {"_id": 0, "tenant_id": 1, "agency_id": 1, "currency": 1}):
            if row.get("tenant_id"):
                pairs.add((row["tenant_id"], row["agency_id"], str(row.get("currency") or "TRY").upper()))
    issued, skipped, failed = [], 0, []
    for tenant_id, agency_id, currency in sorted(pairs):
        data = StatementCreate(agency_id=agency_id, period_start=start, period_end=end, currency=currency)
        try:
            statement = await _issue(sysdb, tenant_id, data, issuer="system", actor="system", direct_notify=True, skip_empty=True)
            issued.append(statement["number"])
        except HTTPException as exc:
            # Already covered, nothing billable, no contract, or being issued now.
            if exc.status_code in (400, 404, 409):
                skipped += 1
            else:
                failed.append(f"{tenant_id}/{agency_id}: {exc.detail}")
    return {"period_start": start, "period_end": end, "issued": issued, "skipped": skipped, "failed": failed}


# ── Hotel endpoints ────────────────────────────────────────────────


@hotel_router.post("/preview")
async def preview_statement(data: StatementCreate, current_user: User = Depends(get_current_user)):
    """What "issue" would create, with the given corrections; nothing is saved
    and the agency is not notified."""
    party = _hotel_party(current_user)
    return await _preview(get_system_db(), party.tenant_id, data, party.actor, "hotel")


@hotel_router.post("")
async def issue_statement(data: StatementCreate, current_user: User = Depends(get_current_user)):
    party = _hotel_party(current_user)
    return await _issue(get_system_db(), party.tenant_id, data, issuer="hotel", actor=party.actor)


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


@hotel_router.get("/{statement_id}")
async def get_hotel_statement(statement_id: str, current_user: User = Depends(get_current_user)):
    return _public(await _load(statement_id, _hotel_party(current_user)))


@hotel_router.post("/{statement_id}/payments")
async def record_payment(statement_id: str, data: PaymentCreate, current_user: User = Depends(get_current_user)):
    """The hotel records money it received from the agency."""
    return await _record_payment_as(statement_id, data, _hotel_party(current_user))


@hotel_router.post("/{statement_id}/agree")
async def hotel_agree_statement(statement_id: str, data: AgreeRequest, current_user: User = Depends(get_current_user)):
    return await _agree(statement_id, data.revision, _hotel_party(current_user))


@hotel_router.post("/{statement_id}/dispute")
async def hotel_dispute_statement(statement_id: str, data: DisputeCreate, current_user: User = Depends(get_current_user)):
    return await _dispute(statement_id, data, _hotel_party(current_user))


@hotel_router.post("/{statement_id}/adjust")
async def adjust_statement_line(statement_id: str, data: LineAdjustment, current_user: User = Depends(get_current_user)):
    return await _adjust(statement_id, data, _hotel_party(current_user))


@hotel_router.post("/{statement_id}/resolve")
async def resolve_dispute(statement_id: str, data: ResolveRequest, current_user: User = Depends(get_current_user)):
    return await _resolve(statement_id, data, _hotel_party(current_user))


@hotel_router.post("/{statement_id}/void")
async def void_statement(statement_id: str, data: ResolveRequest, current_user: User = Depends(get_current_user)):
    return await _void(statement_id, data, _hotel_party(current_user))


@hotel_router.post("/{statement_id}/payment-notices")
async def hotel_report_payment(
    statement_id: str,
    amount: float = Form(..., gt=0),
    paid_at: str = Form(...),
    reference: str = Form(..., min_length=3, max_length=120),
    method: str = Form("bank_transfer", max_length=40),
    proof: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
):
    """The hotel reports the commission it paid the agency; the agency verifies."""
    return await _report_payment_as(statement_id, _hotel_party(current_user), amount=amount, paid_at=paid_at,
                                    reference=reference, method=method, proof=proof)


@hotel_router.get("/{statement_id}/payment-notices/{notice_id}/proof")
async def hotel_payment_proof(statement_id: str, notice_id: str, current_user: User = Depends(get_current_user)):
    return _proof_response(_find_notice(await _load(statement_id, _hotel_party(current_user)), notice_id))


@hotel_router.post("/{statement_id}/payment-notices/{notice_id}/verify")
async def verify_payment_notice(statement_id: str, notice_id: str, data: NoticeDecision, current_user: User = Depends(get_current_user)):
    return await _verify_notice_as(statement_id, notice_id, data, _hotel_party(current_user))


@hotel_router.post("/{statement_id}/payment-notices/{notice_id}/reject")
async def reject_payment_notice(statement_id: str, notice_id: str, data: NoticeRejection, current_user: User = Depends(get_current_user)):
    return await _reject_notice_as(statement_id, notice_id, data, _hotel_party(current_user))


# ── Agency endpoints ───────────────────────────────────────────────


@agency_router.get("")
async def list_agency_statements(agency: dict = Depends(get_marketplace_agency)):
    rows = await get_system_db().agency_statements.find(
        {"agency_id": agency["agency_id"], "status": {"$ne": "void"}}, {"_id": 0, "lines": 0}
    ).sort("issued_at", -1).to_list(200)
    return {"items": [_public(row) for row in rows]}


@agency_router.get("/hotels")
async def statement_hotels(agency: dict = Depends(get_marketplace_agency)):
    """Hotels this agency has (or had) a contract with: it can issue for them."""
    rows = await get_system_db().agency_contracts.find(
        {"agency_id": agency["agency_id"], "contract_code": {"$type": "string"}, "status": {"$in": ["approved", "terminated", "expired"]}},
        {"_id": 0, "tenant_id": 1, "hotel_name": 1, "currency": 1},
    ).to_list(500)
    unique = {row["tenant_id"]: row for row in rows if row.get("tenant_id")}
    return {"hotels": [{"tenant_id": key, "name": row.get("hotel_name"), "currency": row.get("currency") or "TRY"}
                       for key, row in sorted(unique.items(), key=lambda item: str(item[1].get("hotel_name")))]}


@agency_router.post("/preview")
async def agency_preview_statement(data: AgencyStatementCreate, agency: dict = Depends(get_marketplace_agency)):
    party = _agency_party(agency)
    request = StatementCreate(**data.model_dump(exclude={"tenant_id"}), agency_id=party.agency_id)
    return await _preview(get_system_db(), data.tenant_id, request, party.actor, "agency")


@agency_router.post("")
async def agency_issue_statement(data: AgencyStatementCreate, agency: dict = Depends(get_marketplace_agency)):
    """The agency issues the statement itself (e.g. its commission on
    pay-at-hotel stays) instead of waiting for the hotel."""
    party = _agency_party(agency)
    request = StatementCreate(**data.model_dump(exclude={"tenant_id"}), agency_id=party.agency_id)
    return await _issue(get_system_db(), data.tenant_id, request, issuer="agency", actor=party.actor)


@agency_router.get("/{statement_id}")
async def get_agency_statement(statement_id: str, agency: dict = Depends(get_marketplace_agency)):
    return _public(await _load(statement_id, _agency_party(agency)))


@agency_router.post("/{statement_id}/agree")
async def agree_statement(statement_id: str, data: AgreeRequest, agency: dict = Depends(get_marketplace_agency)):
    return await _agree(statement_id, data.revision, _agency_party(agency))


@agency_router.post("/{statement_id}/dispute")
async def dispute_statement(statement_id: str, data: DisputeCreate, agency: dict = Depends(get_marketplace_agency)):
    return await _dispute(statement_id, data, _agency_party(agency))


@agency_router.post("/{statement_id}/adjust")
async def agency_adjust_statement_line(statement_id: str, data: LineAdjustment, agency: dict = Depends(get_marketplace_agency)):
    return await _adjust(statement_id, data, _agency_party(agency))


@agency_router.post("/{statement_id}/resolve")
async def agency_resolve_dispute(statement_id: str, data: ResolveRequest, agency: dict = Depends(get_marketplace_agency)):
    return await _resolve(statement_id, data, _agency_party(agency))


@agency_router.post("/{statement_id}/void")
async def agency_void_statement(statement_id: str, data: ResolveRequest, agency: dict = Depends(get_marketplace_agency)):
    return await _void(statement_id, data, _agency_party(agency))


@agency_router.post("/{statement_id}/payments")
async def agency_record_payment(statement_id: str, data: PaymentCreate, agency: dict = Depends(get_marketplace_agency)):
    """The agency records commission it received from the hotel."""
    return await _record_payment_as(statement_id, data, _agency_party(agency))


@agency_router.post("/{statement_id}/payment-notices")
async def report_payment(
    statement_id: str,
    amount: float = Form(..., gt=0),
    paid_at: str = Form(...),
    reference: str = Form(..., min_length=3, max_length=120),
    method: str = Form("bank_transfer", max_length=40),
    proof: UploadFile | None = File(None),
    agency: dict = Depends(get_marketplace_agency),
):
    """The agency reports a payment it made to the hotel; the hotel verifies."""
    return await _report_payment_as(statement_id, _agency_party(agency), amount=amount, paid_at=paid_at,
                                    reference=reference, method=method, proof=proof)


@agency_router.get("/{statement_id}/payment-notices/{notice_id}/proof")
async def agency_payment_proof(statement_id: str, notice_id: str, agency: dict = Depends(get_marketplace_agency)):
    return _proof_response(_find_notice(await _load(statement_id, _agency_party(agency)), notice_id))


@agency_router.post("/{statement_id}/payment-notices/{notice_id}/verify")
async def agency_verify_payment_notice(statement_id: str, notice_id: str, data: NoticeDecision, agency: dict = Depends(get_marketplace_agency)):
    return await _verify_notice_as(statement_id, notice_id, data, _agency_party(agency))


@agency_router.post("/{statement_id}/payment-notices/{notice_id}/reject")
async def agency_reject_payment_notice(statement_id: str, notice_id: str, data: NoticeRejection, agency: dict = Depends(get_marketplace_agency)):
    return await _reject_notice_as(statement_id, notice_id, data, _agency_party(agency))
