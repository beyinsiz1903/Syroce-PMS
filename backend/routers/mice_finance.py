"""Banquet collections: recoverable GL posting followed by atomic cash/folio writes.

This records money already received/returned by the cashier. It never instructs
a bank or card processor to move money. An uncertain posting remains visibly
pending, freezes the sale, and is recovered with exactly the same request.
"""
import hashlib
import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from cache_manager import cache
from core.booking_atomicity import is_replica_set_unavailable, with_resource_locks
from core.business_date_service import ensure_business_date_initialized
from core.entitlements.enforcement import require_feature
from core.mice_integrity import money, rounded
from core.security import get_current_user
from core.spa_mice_authz import require_finance
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.reporting_financials import stamp_reporting_values
from modules.pms_core.role_permission_service import RolePermissionService, require_op
from shared_kernel.gl_posting import GLPostingError, post_journal_entry

router = APIRouter(dependencies=[Depends(require_feature("mice", "banquet_operations"))])


class SettlementIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, str_strip_whitespace=True, extra="forbid")
    request_id: str = Field(min_length=8, max_length=100)
    kind: str = Field("collection", pattern="^(collection|refund)$")
    amount: float = Field(gt=0, le=1_000_000_000)
    method: str = Field(pattern="^(cash|card|bank_transfer)$")
    bank_account_id: str | None = None
    original_payment_id: str | None = None
    reference: str = Field(min_length=3, max_length=200)
    reason: str = Field(min_length=10, max_length=1000)
    exchange_rate: float | None = Field(None, gt=0, le=1_000_000)


def settlement_totals(event, rows):
    posted = [r for r in rows if r.get("status") in {"paid", "refunded"} and not r.get("voided")]
    collected = sum((money(r["amount"]) for r in posted if r.get("payment_type") != "refund"), money(0))
    refunded = sum((money(abs(r["amount"])) for r in posted if r.get("payment_type") == "refund"), money(0))
    net = collected - refunded
    quoted = money((event.get("totals") or {}).get("grand_total"))
    sale = money(0) if event.get("status") == "cancelled" else quoted
    return {"collected": float(collected), "refunded": float(refunded), "net_collected": float(net),
            "quoted_total": float(quoted), "outstanding": float(max(money(0), sale - net)),
            "customer_credit": float(max(money(0), net - sale))}


@router.get("/events/{event_id}/settlements")
async def list_settlements(event_id: str, current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_finance_reports"))):
    require_finance(current_user)
    db, tid = get_system_db(), current_user.tenant_id
    event = await db.mice_events.find_one({"tenant_id": tid, "id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(404, "Etkinlik bulunamadı")
    rows = await db.payments.find({"tenant_id": tid, "mice_event_id": event_id}, {"_id": 0}).sort("processed_at", 1).to_list(None)
    accounts = await db.bank_accounts.find({"tenant_id": tid, "is_active": {"$ne": False}, "currency": event.get("currency", "TRY")}, {"_id": 0, "id": 1, "name": 1, "currency": 1}).to_list(None)
    return {"currency": event.get("currency", "TRY"), "payments": rows, "totals": settlement_totals(event, rows),
            "bank_accounts": accounts, "pending": {k: v for k, v in event["finance_pending"].items() if k in {"request", "payment_id", "started_at"}} if event.get("finance_pending") else None,
            "notice": "Gerçekte alınmış/iade edilmiş parayı kaydeder; bankaya veya karta ödeme emri göndermez. Ödeme planındaki eski beyanlar tahsilat sayılmaz."}


@router.post("/events/{event_id}/settlements")
async def record_settlement(event_id: str, body: SettlementIn, current_user: User = Depends(get_current_user), _perm=Depends(require_op("post_payment"))):
    require_finance(current_user)
    if body.kind == "refund":
        RolePermissionService().enforce_user_permission(current_user, "void_payment")
    db, tid = get_system_db(), current_user.tenant_id
    payload = body.model_dump()
    if body.kind == "collection" and body.original_payment_id:
        raise HTTPException(422, "Asıl tahsilat yalnız iade işleminde seçilebilir")
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    payment_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"mice-settlement:{tid}:{event_id}:{body.request_id}"))
    scope = {"tenant_id": tid, "id": event_id}
    day = (await ensure_business_date_initialized(db, tid))["business_date"]

    async def claim(session):
        event = await db.mice_events.find_one(scope, session=session)
        if not event:
            raise HTTPException(404, "Etkinlik bulunamadı")
        existing = await db.payments.find_one({"tenant_id": tid, "id": payment_id}, {"_id": 0}, session=session)
        if existing:
            if existing.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "İstek anahtarı farklı tahsilat/iade için kullanılamaz")
            return {"existing": existing}
        pending = event.get("finance_pending")
        if pending:
            if pending["payment_id"] != payment_id or pending["fingerprint"] != fingerprint:
                raise HTTPException(409, "Önce bekleyen tahsilat/iade isteğini aynı bilgilerle tamamlayın")
            return pending
        if event.get("gl_posting_state") == "pending":
            raise HTTPException(409, "Önce bekleyen satış muhasebe aktarımını tamamlayın")
        if body.kind == "collection" and event.get("status") not in {"definite", "confirmed", "completed"}:
            raise HTTPException(409, "Tahsilat için etkinlik kesinleşmiş olmalıdır")
        amount = money(rounded(body.amount))
        if not amount:
            raise HTTPException(422, "Tutar en az bir kuruş olmalıdır")
        currency = event.get("currency") or "TRY"
        rows = await db.payments.find({"tenant_id": tid, "mice_event_id": event_id}, session=session).to_list(None)
        total = settlement_totals(event, rows)
        if body.kind == "collection" and amount > money(total["outstanding"]):
            raise HTTPException(409, "Tahsilat etkinliğin açık tutarını aşamaz")
        rate = body.exchange_rate or (1 if currency == "TRY" else None)
        base = rounded(amount * money(rate)) if rate else None
        if currency == "TRY" and body.exchange_rate not in {None, 1}:
            raise HTTPException(422, "TRY için kur 1 olmalıdır")
        if body.kind == "refund":
            original = next((r for r in rows if r["id"] == body.original_payment_id and r.get("status") == "paid" and not r.get("voided") and r.get("payment_type") != "refund"), None)
            if not original:
                raise HTTPException(422, "İade için bu etkinliğin geçerli asıl tahsilatını seçin")
            previous = [r for r in rows if r.get("original_payment_id") == original["id"] and r.get("status") == "refunded"]
            remaining = money(original["amount"]) - sum((money(abs(r["amount"])) for r in previous), money(0))
            if amount > remaining:
                raise HTTPException(409, "İade kalan asıl tahsilat tutarını aşamaz")
            if body.method != original["method"] or body.bank_account_id != original.get("bank_account_id"):
                raise HTTPException(422, "İade asıl tahsilatın yöntemi ve hesabına yapılmalıdır")
            rate = original["gl_exchange_rate"]
            if body.exchange_rate not in {None, rate}:
                raise HTTPException(422, "İade asıl tahsilatın kayıtlı kurunu kullanır")
            # Keep the final rounding remainder refundable. A sub-cent TRY
            # allocation cannot be represented in the GL; require a larger or
            # full refund instead of consuming the last cent prematurely.
            remaining_base = money(original["gl_base_amount"]) - sum((money(r["gl_base_amount"]) for r in previous), money(0))
            base = rounded(remaining_base) if amount == remaining else rounded(amount * money(rate))
            if amount < remaining and money(base) >= remaining_base:
                raise HTTPException(422, "Kur yuvarlaması kalan iadeyi kuruş altına indiriyor; kalan tahsilatı tek işlemde iade edin")
        if rate is None or not base:
            raise HTTPException(422, "Döviz tahsilatı için TRY muhasebe kuru gereklidir; TRY karşılığı en az bir kuruş olmalıdır")
        if body.method != "cash":
            bank = await db.bank_accounts.find_one({"tenant_id": tid, "id": body.bank_account_id, "is_active": {"$ne": False}}, session=session)
            if not bank or bank.get("currency") != currency:
                raise HTTPException(422, "Aynı para biriminde aktif banka/kart hesabı seçin")
        elif body.bank_account_id:
            raise HTTPException(422, "Nakit işleminde banka hesabı seçilemez")
        shift = await db.cashier_shifts.find_one({"tenant_id": tid, "status": "open"}, sort=[("opened_at", -1)], session=session)
        if body.method == "cash" and not shift:
            raise HTTPException(409, "Nakit işleminden önce kasa vardiyasını açın")
        if shift:
            await db.cashier_shifts.update_one({"_id": shift["_id"], "tenant_id": tid, "status": "open"}, {"$addToSet": {"mice_pending_ids": payment_id}}, session=session)
        folio_id = None
        if event.get("reservation_id"):
            booking = await db.bookings.find_one({"tenant_id": tid, "id": event["reservation_id"]}, session=session)
            if not booking or booking.get("currency") != currency or booking.get("folio_merged_to"):
                raise HTTPException(409, "Bağlı rezervasyon para birimi veya ana folyo değişmiş; önce bağlantıyı düzeltin")
            folio = await db.folios.find_one({"tenant_id": tid, "booking_id": booking["id"], "status": "open", "currency": currency}, session=session)
            if not folio:
                raise HTTPException(409, "Bağlı rezervasyon için aynı para biriminde açık folyo gereklidir")
            folio_id = folio["id"]
        if event.get("group_block_id"):
            group = await db.group_blocks.find_one({"tenant_id": tid, "id": event["group_block_id"]}, session=session)
            folio = await db.folios.find_one({"tenant_id": tid, "id": (group or {}).get("master_folio_id"), "status": "open", "currency": currency}, session=session)
            if not folio:
                raise HTTPException(409, "Grup için aynı para biriminde açık ana folyo gereklidir")
            folio_id = folio["id"]
        pending = {"payment_id": payment_id, "fingerprint": fingerprint, "request": payload,
                   "currency": currency, "amount": float(amount), "rate": rate, "base": base,
                   "business_date": day, "folio_id": folio_id, "booking_id": event.get("reservation_id"),
                   "cashier_shift_id": shift["_id"] if shift else None,
                   "started_at": datetime.now(UTC).isoformat(), "actor": current_user.username}
        await db.mice_events.update_one(scope, {"$set": {"finance_pending": pending, "updated_at": pending["started_at"]}}, session=session)
        return pending

    try:
        pending = await with_resource_locks(client=db.client, db=db, tenant_id=tid, locks_collection="mice_locks", resources=[("finance", event_id)], callback=claim)
    except Exception as exc:
        if is_replica_set_unavailable(exc):
            raise HTTPException(503, "Tahsilat/iade için işlem destekleyen veritabanı gereklidir") from exc
        raise
    if "existing" in pending:
        return {"payment": pending["existing"], "replayed": True}
    refund = body.kind == "refund"
    code = {"cash": "100", "card": "108", "bank_transfer": "102"}[body.method]
    amount = pending["amount"]
    foreign = {"currency": pending["currency"], "foreign_amount": amount, "exchange_rate": pending["rate"]} if pending["currency"] != "TRY" else {}
    lines = [{"account_code": code, "credit" if refund else "debit": pending["base"], **foreign},
             {"account_code": "120", "debit" if refund else "credit": pending["base"], **foreign}]
    try:
        journal = await post_journal_entry(db, tid, date=pending["business_date"], memo=f"MICE {'iade' if refund else 'tahsilat'}: {event_id} / {body.reference}", lines=lines,
                                           source="mice_settlement", source_ref=event_id, actor=pending["actor"], idempotency_key=f"mice-settlement:{payment_id}")
    except GLPostingError as exc:
        # Keep the claim: the user can fix COA/period and retry, never silently
        # reallocate this amount to another request after an uncertain result.
        raise HTTPException(409, f"Muhasebe kaydı tamamlanamadı; aynı isteği tekrar deneyin: {exc}") from exc
    now = datetime.now(UTC).isoformat()
    payment = {"_id": f"mice-settlement:{payment_id}", "id": payment_id, "tenant_id": tid, "mice_event_id": event_id,
               "amount": -amount if refund else amount, "currency": pending["currency"], "method": body.method,
               "payment_type": "refund" if refund else "deposit", "status": "refunded" if refund else "paid",
               "reference": body.reference, "notes": body.reason, "bank_account_id": body.bank_account_id,
               "original_payment_id": body.original_payment_id, "request_fingerprint": fingerprint,
               "idempotency_key": f"mice-settlement:{payment_id}", "processed_at": now, "processed_by": pending["actor"],
               "business_date": pending["business_date"], "gl_journal_entry_id": journal["id"],
               "gl_exchange_rate": pending["rate"], "gl_base_amount": pending["base"], "voided": False,
               "reporting_amount": -pending["base"] if refund else pending["base"], "reporting_currency": "TRY",
               **({"folio_id": pending["folio_id"], "booking_id": pending["booking_id"]} if pending["folio_id"] else {})}
    stamp_reporting_values(payment)

    async def finish(session):
        existing = await db.payments.find_one({"tenant_id": tid, "id": payment_id}, {"_id": 0}, session=session)
        if existing:
            return existing
        event = await db.mice_events.find_one(scope, session=session)
        if (event.get("finance_pending") or {}).get("payment_id") != payment_id:
            raise HTTPException(409, "Bekleyen finans işlemi değişti; yetkili mutabakatı gerekiyor")
        await db.payments.insert_one(dict(payment), session=session)
        await db.cash_flow.insert_one({"_id": f"mice-settlement:{payment_id}", "id": payment_id, "tenant_id": tid,
                                      "transaction_type": "expense" if refund else "income", "category": "mice_refund" if refund else "mice_collection",
                                      "amount": amount, "currency": pending["currency"], "description": body.reason,
                                      "reference_id": payment_id, "reference_type": "payment", "date": pending["business_date"], "created_at": now, "created_by": pending["actor"]}, session=session)
        if body.bank_account_id:
            bank_result = await db.bank_accounts.update_one({"tenant_id": tid, "id": body.bank_account_id}, {"$inc": {"balance": -amount if refund else amount}}, session=session)
            if bank_result.matched_count != 1:
                raise HTTPException(409, "Banka hesabı bulunamadı; finans işlemi mutabakat bekliyor")
        if pending.get("cashier_shift_id"):
            transaction = {"id": payment_id, "amount": pending["base"], "original_amount": amount, "currency": pending["currency"], "fx_rate": pending["rate"],
                           "method": body.method, "direction": "out" if refund else "in", "type": "refund" if refund else "folio_payment",
                           "description": body.reason, "ref_type": "payment", "ref_id": payment_id, "created_at": now, "timestamp": now,
                           "created_by": pending["actor"], "idempotency_key": f"payment:{payment_id}", "business_date": pending["business_date"]}
            update = {"$push": {"transactions": transaction}, "$pull": {"mice_pending_ids": payment_id}}
            if body.method == "cash":
                update["$inc"] = {"cash_out" if refund else "cash_in": pending["base"]}
            shift_result = await db.cashier_shifts.update_one({"_id": pending["cashier_shift_id"], "tenant_id": tid, "status": "open"}, update, session=session)
            if shift_result.matched_count != 1:
                raise HTTPException(409, "Bekleyen finans işleminin kasa vardiyası kapanmış; yetkili mutabakatı gerekiyor")
        if pending["folio_id"]:
            # Header is a cache; canonical read services recompute from rows.
            folio_result = await db.folios.update_one({"tenant_id": tid, "id": pending["folio_id"], "status": "open"}, {"$inc": {"balance": amount if refund else -amount}}, session=session)
            if folio_result.matched_count != 1:
                raise HTTPException(409, "Ana folyo kapanmış; finans işlemi mutabakat bekliyor")
        await db.mice_events.update_one(scope, {"$unset": {"finance_pending": ""}, "$inc": {"settlement_count": 1}, "$set": {"updated_at": now}}, session=session)
        await db.audit_logs.insert_one({"tenant_id": tid, "id": str(uuid.uuid4()), "timestamp": now, "user_id": pending["actor"], "action": f"mice.{body.kind}", "entity_type": "mice_event", "entity_id": event_id, "details": {"payment_id": payment_id, "journal_entry_id": journal["id"], "amount": amount, "currency": pending["currency"]}}, session=session)
        return {k: v for k, v in payment.items() if k != "_id"}
    result = await with_resource_locks(client=db.client, db=db, tenant_id=tid, locks_collection="mice_locks", resources=[("finance", event_id)], callback=finish)
    for prefix in ("mice_events", "accounting_dashboard", "report_balance_sheet", "reports_basic_dashboard_v2"):
        cache.safe_invalidate(tid, prefix)
    return {"payment": result, "replayed": False}
