"""Marketplace period statements: hotel issues, agency agrees or disputes, payments settle.

Hotel (PMS JWT):   /api/marketplace/hotel/statements
Agency (portal):   /api/marketplace/v1/statements
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.agency_statements import build_statement, outstanding
from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User
from routers.marketplace_b2b import _require_hotel_admin, get_marketplace_agency

hotel_router = APIRouter(prefix="/api/marketplace/hotel/statements", tags=["Marketplace / Statements (hotel)"])
agency_router = APIRouter(prefix="/api/marketplace/v1/statements", tags=["Marketplace / Statements (agency)"])

OPEN_STATUSES = ("issued", "agreed", "disputed", "resolved")
LOCK_TTL_SECONDS = 120


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
    # Storage paths of payment proofs never leave the server.
    statement["payment_notices"] = [
        {**{k: v for k, v in notice.items() if k != "proof_path"}, "has_proof": bool(notice.get("proof_path"))}
        for notice in statement.get("payment_notices") or []
    ]
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
    async with _issue_lock(sysdb, tenant_id, data.agency_id, data.currency):
        return await _issue_statement_locked(sysdb, tenant_id, data, contract, current_user)


@asynccontextmanager
async def _issue_lock(sysdb, tenant_id: str, agency_id: str, currency: str):
    """Serialize issuing per hotel/agency/currency so two concurrent issues
    cannot both pass the overlap check. A crashed holder expires."""
    key = f"{tenant_id}:{agency_id}:{currency}"
    for _ in range(2):
        try:
            await sysdb.agency_statement_locks.insert_one({"_id": key, "created_at": _now()})
            break
        except DuplicateKeyError:
            stale_before = datetime.fromtimestamp(datetime.now(UTC).timestamp() - LOCK_TTL_SECONDS, UTC).isoformat()
            removed = await sysdb.agency_statement_locks.delete_one({"_id": key, "created_at": {"$lt": stale_before}})
            if not removed.deleted_count:
                raise HTTPException(409, "Bu acente için başka bir ekstre şu an düzenleniyor; birazdan tekrar deneyin") from None
    else:
        raise HTTPException(409, "Bu acente için başka bir ekstre şu an düzenleniyor; birazdan tekrar deneyin")
    try:
        yield
    finally:
        await sysdb.agency_statement_locks.delete_one({"_id": key})


async def _issue_statement_locked(sysdb, tenant_id: str, data, contract: dict, current_user: User) -> dict:
    # Any overlap would bill the same stays twice (e.g. 1-31 Oct and 15-31 Oct).
    duplicate = await sysdb.agency_statements.find_one({
        "tenant_id": tenant_id, "agency_id": data.agency_id, "currency": data.currency,
        "period_start": {"$lte": data.period_end}, "period_end": {"$gte": data.period_start},
        "status": {"$in": list(OPEN_STATUSES) + ["settled"]},
    }, {"_id": 0, "number": 1, "period_start": 1, "period_end": 1})
    if duplicate:
        raise HTTPException(
            409, f"Bu dönem {duplicate['number']} ekstresiyle ({duplicate['period_start']} – {duplicate['period_end']}) çakışıyor; önce onu iptal edin"
        )
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
    return await _record_payment(statement_id, data, current_user)


def _ref_key(reference) -> str:
    """One comparison for bank references on every path ("EFT-1 " == "eft-1")."""
    return " ".join(str(reference or "").split()).casefold()


async def _record_payment(statement_id: str, data: PaymentCreate, current_user: User, *, notify: bool = True,
                          notice_id: str | None = None, note: str = "") -> dict:
    """Record a statement payment. With ``notice_id`` (or a pending agency
    notice carrying the same reference and amount) the payment and the
    notice decision are one atomic write: both happen or neither does, and a
    concurrent decision on the notice makes this write lose."""
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    statement = await _hotel_statement(statement_id, tenant_id)
    if statement["status"] == "settled":
        raise HTTPException(409, "Ekstre kapanmış; fazla ödeme veya iade ayrı bir işlem olarak kaydedilmelidir")
    if statement["status"] in ("void", "issued", "disputed"):
        raise HTTPException(409, "Ödeme yalnız acentenin onayladığı veya itirazı çözülmüş ekstreye kaydedilir")
    previous = statement.get("payments") or []
    reference = data.reference.strip()
    key = _ref_key(reference)
    if notice_id:
        notice = _find_notice(statement, notice_id)
        if notice["status"] != "pending":
            raise HTTPException(409, "Bu bildirim zaten sonuçlandırılmış")
    else:
        notice = next((n for n in statement.get("payment_notices") or [] if key and data.direction == "agency_to_hotel"
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
               "recorded_by": current_user.email, "recorded_at": _now()}
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
    query = {"id": statement_id, "tenant_id": tenant_id, "status": statement["status"], **guard}
    updates: dict = {"$push": {"payments": payment, "history": _event("payment", current_user.email, amount=data.amount, direction=data.direction)},
                     "$set": {"status": status}}
    options: dict = {}
    if notice:
        query["payment_notices"] = {"$elemMatch": {"id": notice["id"], "status": "pending"}}
        updates["$set"].update({
            "payment_notices.$[n].status": "verified", "payment_notices.$[n].decided_at": _now(),
            "payment_notices.$[n].decided_by": current_user.email,
            "payment_notices.$[n].note": note or ("" if notice_id else "Aynı referansla ödeme kaydedildi"),
        })
        options["array_filters"] = [{"n.id": notice["id"]}]
    updated = await sysdb.agency_statements.find_one_and_update(
        query, updates, projection={"_id": 0}, return_document=ReturnDocument.AFTER, **options,
    )
    if not updated:
        raise HTTPException(409, "Ekstre veya ödeme bildirimi eş zamanlı değişti; yenileyin")
    if notify:
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
    current = await _hotel_statement(statement_id, tenant_id)
    if any(n.get("status") == "pending" for n in current.get("payment_notices") or []):
        raise HTTPException(409, "Ekstrede yanıt bekleyen ödeme bildirimi var; önce doğrulayın veya reddedin")
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


# ── Payment notices: the agency reports a transfer, the hotel verifies ──

PROOF_TYPES = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
NOTICE_PAYABLE = ("agreed", "resolved")


def _pending_notice_total(statement: dict) -> float:
    return round(sum(float(n.get("amount") or 0) for n in statement.get("payment_notices") or [] if n.get("status") == "pending"), 2)


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


def _find_notice(statement: dict, notice_id: str) -> dict:
    notice = next((n for n in statement.get("payment_notices") or [] if n.get("id") == notice_id), None)
    if not notice:
        raise HTTPException(404, "Ödeme bildirimi bulunamadı")
    return notice


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
    """The agency reports a payment on an agreed statement. Nothing is
    credited until the hotel verifies it."""
    try:
        paid_on = _iso_date(paid_at)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if paid_on > date.today().isoformat():
        raise HTTPException(422, "Ödeme tarihi ileri bir tarih olamaz")
    sysdb = get_system_db()
    statement = await _agency_statement(statement_id, agency["agency_id"])
    if statement["status"] not in NOTICE_PAYABLE:
        raise HTTPException(409, "Ödeme bildirimi yalnız mutabık kalınan ekstreye yapılır")
    owed = outstanding(statement)
    if owed <= 0.01:
        raise HTTPException(409, "Bu ekstrede acentenin otele ödemesi gereken bakiye yok")
    open_amount = round(owed - _pending_notice_total(statement), 2)
    if amount - open_amount >= 0.01:
        raise HTTPException(409, f"Bildirilen tutar, onay bekleyen bildirimler düşüldükten sonra kalan bakiyeyi aşıyor (kalan {max(open_amount, 0):.2f} {statement['currency']})")
    reference = reference.strip()
    if _reference_taken(statement, reference):
        raise HTTPException(409, f"{reference} referansıyla bir ödeme zaten bildirilmiş veya kayıtlı")
    notice_id = str(uuid.uuid4())
    proof_path = await _store_proof(statement, notice_id, proof) if proof is not None and proof.filename else None
    actor = (agency.get("user") or {}).get("email") or agency.get("contact_email") or agency["agency_id"]
    notice = {"id": notice_id, "amount": round(amount, 2), "paid_at": paid_on, "reference": reference, "method": method,
              "proof_path": proof_path, "status": "pending", "reported_at": _now(), "reported_by": actor}
    previous = statement.get("payment_notices") or []
    guard = {f"payment_notices.{len(previous)}": {"$exists": False}}
    updated = await sysdb.agency_statements.find_one_and_update(
        {"id": statement_id, "agency_id": agency["agency_id"], "status": statement["status"], **guard},
        {"$push": {"payment_notices": notice, "history": _event("payment_reported", actor, amount=notice["amount"], reference=reference)}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Ekstre eş zamanlı değişti; yenileyip tekrar deneyin")
    await _notify_hotel(updated, "acente ödeme bildirdi",
                        f"{notice['amount']:.2f} {updated['currency']} · {paid_on} · ref {reference}. Doğrulayın veya reddedin.")
    return _public(updated)


@agency_router.get("/{statement_id}/payment-notices/{notice_id}/proof")
async def agency_payment_proof(statement_id: str, notice_id: str, agency: dict = Depends(get_marketplace_agency)):
    return _proof_response(_find_notice(await _agency_statement(statement_id, agency["agency_id"]), notice_id))


@hotel_router.get("/{statement_id}/payment-notices/{notice_id}/proof")
async def hotel_payment_proof(statement_id: str, notice_id: str, current_user: User = Depends(get_current_user)):
    return _proof_response(_find_notice(await _hotel_statement(statement_id, _require_hotel_admin(current_user)), notice_id))


class NoticeDecision(BaseModel):
    note: str = Field("", max_length=500)


@hotel_router.post("/{statement_id}/payment-notices/{notice_id}/verify")
async def verify_payment_notice(statement_id: str, notice_id: str, data: NoticeDecision, current_user: User = Depends(get_current_user)):
    """Verified notice = a statement payment with the same bank reference,
    written together with the decision; only now do the statement balance
    and the agency credit change."""
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    notice = _find_notice(await _hotel_statement(statement_id, tenant_id), notice_id)
    if notice["status"] != "pending":
        raise HTTPException(409, "Bu bildirim zaten sonuçlandırılmış")
    payment = PaymentCreate(amount=notice["amount"], direction="agency_to_hotel", paid_at=notice["paid_at"],
                            method=notice.get("method") or "bank_transfer", reference=notice["reference"])
    updated = await _record_payment(statement_id, payment, current_user, notify=False,
                                    notice_id=notice_id, note=data.note.strip())
    await _notify_agency(sysdb, updated, "ödeme bildiriminiz doğrulandı",
                         f"{notice['amount']:.2f} {updated['currency']} (ref {notice['reference']}) ekstreye işlendi. Kalan: {outstanding(updated):.2f}")
    return updated


class NoticeRejection(BaseModel):
    note: str = Field(..., min_length=5, max_length=500)


@hotel_router.post("/{statement_id}/payment-notices/{notice_id}/reject")
async def reject_payment_notice(statement_id: str, notice_id: str, data: NoticeRejection, current_user: User = Depends(get_current_user)):
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    updated = await sysdb.agency_statements.find_one_and_update(
        {"id": statement_id, "tenant_id": tenant_id, "payment_notices": {"$elemMatch": {"id": notice_id, "status": "pending"}}},
        {"$set": {"payment_notices.$.status": "rejected", "payment_notices.$.decided_at": _now(),
                  "payment_notices.$.decided_by": current_user.email, "payment_notices.$.note": data.note.strip()},
         "$push": {"history": _event("payment_notice_rejected", current_user.email, notice_id=notice_id, note=data.note.strip())}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(409, "Yanıt bekleyen ödeme bildirimi bulunamadı")
    notice = _find_notice(updated, notice_id)
    await _notify_agency(sysdb, updated, "ödeme bildiriminiz reddedildi", f"Ref {notice['reference']}: {data.note.strip()}")
    return _public(updated)
