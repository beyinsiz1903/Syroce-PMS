"""Source-backed folio settlements, not a second cash payment selector.

Gift/wallet opening credit must already exist in a sealed GL liability entry.
Barter/write-off limits need an explicit document and account; loyalty consumes
the existing member's points. Pending cheques never reduce a folio. All writes,
including GL, points, folio and audit, use the caller's financial transaction.
"""
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.pms_core.enterprise_billing import fingerprint, minor, require_cent_currency
from modules.pms_core.folio_selection import select_booking_folio
from modules.pms_core.receivable_reporting import folio_snapshots
from shared_kernel.atomic_workflow import SessionDatabase
from shared_kernel.gl_posting import GLPostingError, post_journal_entry, verify_journal_entry_hash

KINDS = {"gift_card_redemption": "Hediye kartı", "wallet": "Misafir cüzdanı",
    "loyalty_redemption": "Sadakat puanı", "barter": "Barter", "write_off": "Alacaktan silme",
    "cheque_pending_clearance": "Çek — tahsil bekliyor"}
FUNDED = {"gift_card_redemption", "wallet"}


async def prepare(db, tenant):
    # The GL helper ensures indexes too. Precreate them BEFORE the data snapshot:
    # first-use DDL outside a running transaction can invalidate its namespace.
    from shared_kernel.gl_posting import ensure_gl_idem_index
    from shared_kernel.pos_idem import ensure_compound_unique

    await ensure_gl_idem_index(db)
    for collection, fields, name in [(db.billing_instruments, [("tenant_id", 1), ("id", 1)], "ux_billing_instrument_id"),
            (db.billing_instruments, [("tenant_id", 1), ("kind", 1), ("reference", 1)], "ux_billing_instrument_reference"),
            (db.billing_instrument_operations, [("tenant_id", 1), ("id", 1)], "ux_billing_instrument_operation")]:
        await ensure_compound_unique(collection, fields, name=name)
    await ensure_compound_unique(db.billing_instrument_operations, [("tenant_id", 1), ("original_operation_id", 1)],
        name="ux_billing_instrument_reversal", partial_filter={"original_operation_id": {"$type": "string"}})
    from pymongo.errors import DuplicateKeyError

    query = {"_id": "billing-instruments:" + tenant, "tenant_id": tenant}
    try:
        await db.billing_instrument_locks.update_one(query, {"$setOnInsert": {"revision": 0}}, upsert=True)
    except DuplicateKeyError:
        if not await db.billing_instrument_locks.find_one(query):
            raise


async def _serialize(db, tenant, session):
    # Stable primary key, not an assumed unique legacy lock index. Different
    # instruments sharing a funding entry must not allocate its credit twice.
    updated = await db.billing_instrument_locks.update_one({"_id": "billing-instruments:" + tenant, "tenant_id": tenant},
        {"$inc": {"revision": 1}}, session=session)
    if updated.matched_count != 1:
        raise HTTPException(503, "Mahsup kilidi hazır değil; transaction öncesi hazırlık gerekli")


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    reference: str = Field(min_length=3, max_length=160)
    reason: str = Field(min_length=3, max_length=500)


class Issue(Evidence):
    booking_id: str = Field(min_length=1, max_length=100)
    kind: Literal["gift_card_redemption", "wallet", "loyalty_redemption", "barter", "write_off", "cheque_pending_clearance"]
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount_minor: int = Field(strict=True, gt=0, le=100_000_000_000)
    account_code: str = Field(min_length=1, max_length=50)
    funding_entry_id: str | None = Field(default=None, min_length=1, max_length=100)
    point_value_minor: int | None = Field(default=None, strict=True, gt=0, le=100_000)
    expires_on: date | None = None
    due_on: date | None = None

    @model_validator(mode="after")
    def shape(self):
        require_cent_currency(self.currency)
        if (self.kind in FUNDED) != bool(self.funding_entry_id):
            raise ValueError("Hediye kartı/cüzdan için önceki fonlama fişi zorunlu; diğer türlerde kullanılamaz")
        if (self.kind == "loyalty_redemption") != (self.point_value_minor is not None):
            raise ValueError("Puan değeri yalnız sadakat için zorunludur")
        if (self.kind == "cheque_pending_clearance") != (self.due_on is not None):
            raise ValueError("Vade yalnız çek için zorunludur")
        if self.kind == "cheque_pending_clearance" and self.currency != "TRY":
            raise ValueError("Çek tahsil kabulü TRY ile sınırlıdır")
        if self.point_value_minor and self.amount_minor % self.point_value_minor:
            raise ValueError("Sadakat limiti puan değerinin tam katı olmalı")
        if self.due_on and self.expires_on and self.expires_on < self.due_on:
            raise ValueError("Çekin son kullanım günü vadesinden önce olamaz")
        return self


class Apply(Evidence):
    booking_id: str = Field(min_length=1, max_length=100)
    folio_id: str = Field(min_length=1, max_length=100)
    amount_minor: int = Field(strict=True, gt=0, le=100_000_000_000)
    rate_to_try: Decimal = Field(gt=0, le=1_000_000, max_digits=13, decimal_places=6, allow_inf_nan=False)
    rate_reference: str = Field(min_length=3, max_length=160)
    fx_gain_account: str | None = Field(default=None, min_length=1, max_length=50)
    fx_loss_account: str | None = Field(default=None, min_length=1, max_length=50)


class Reverse(Evidence):
    booking_id: str = Field(min_length=1, max_length=100)


def public(row):
    return {key: value for key, value in row.items() if key not in {"_id", "fingerprint", "request_payload"}}


async def _day(db, tenant, session):
    settings = await db.tenant_settings.find_one({"tenant_id": tenant}, session=session)
    try:
        return date.fromisoformat(str((settings or {}).get("business_date"))).isoformat()
    except (TypeError, ValueError):
        raise HTTPException(409, "Açık iş günü doğrulanamadı") from None


async def _replay(db, tenant, body, session, *, instrument_id=None, action):
    key = f"billing-instrument:{tenant}:{body.request_id}"
    payload = {"action": action, "instrument_id": instrument_id, **body.model_dump(mode="json")}
    digest = fingerprint(payload)
    old = await db.billing_instrument_operations.find_one({"_id": key, "tenant_id": tenant}, session=session)
    if old and old["fingerprint"] != digest:
        raise HTTPException(409, "İşlem anahtarı farklı bir içerik için kullanılmış")
    return key, digest, old


async def _account(db, tenant, code, types, session):
    row = await db.gl_accounts.find_one({"tenant_id": tenant, "code": code}, session=session)
    if not row or not row.get("active", True) or row.get("type") not in types:
        raise HTTPException(409, "Aktif ve uygun türde muhasebe hesabı seçin: " + code)
    return row


async def _booking(db, tenant, booking_id, session):
    row = await db.bookings.find_one({"tenant_id": tenant, "id": booking_id}, session=session)
    if not row:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    if row.get("status") in {"cancelled", "no_show", "checked_out", "archived_demo"}:
        raise HTTPException(409, "Tamamlanmış rezervasyon için ayrı finansal düzeltme akışı gerekli")
    return row


async def _assert_funding_not_reversed(db, tenant, entry, session):
    if (entry.get("reverses_entry_id") or entry.get("reversal_status") == "reversed"
        or await db.gl_journal_entries.find_one({"tenant_id": tenant, "reverses_entry_id": entry["id"], "status": "posted"}, session=session)):
        raise HTTPException(409, "Fonlama fişi ters kaydedilmiş; yeni hak veya mahsup üretilemez")


async def _funding(db, tenant, body, session):
    entry = await db.gl_journal_entries.find_one({"tenant_id": tenant, "id": body.funding_entry_id, "status": "posted"}, session=session)
    if not entry or not verify_journal_entry_hash(entry):
        raise HTTPException(409, "Mühürlü fonlama fişi doğrulanamadı")
    await _assert_funding_not_reversed(db, tenant, entry, session)
    lines = [line for line in entry["lines"] if line["account_code"] == body.account_code]
    if any(line.get("debit_minor") for line in lines):
        raise HTTPException(409, "Fonlama hesabında borç/alacak karışık; ayrı fonlama fişi gerekli")
    credit = sum(line.get("credit_minor", 0) for line in lines)
    if body.currency == "TRY":
        if any(line.get("currency") for line in lines):
            raise HTTPException(409, "Fonlama fişinin para birimi farklı")
        nominal = credit
    else:
        if any(line.get("currency") != body.currency or not line.get("foreign_amount_minor") for line in lines):
            raise HTTPException(409, "Fonlama fişinde aynı dövizin özgün tutarı/kur snapshot'ı gerekli")
        nominal = sum(line["foreign_amount_minor"] for line in lines)
    prior = await db.billing_instruments.find({"tenant_id": tenant, "funding_entry_id": entry["id"],
        "account_code": body.account_code}, session=session).to_list(None)
    allocated = sum(row["issued_minor"] for row in prior)
    base_allocated = sum(row["issued_base_minor"] for row in prior)
    if nominal <= 0 or body.amount_minor + allocated > nominal:
        raise HTTPException(409, "Fonlama fişinin kullanılmamış bakiyesi yetersiz")
    # Cumulative allocation preserves the final TRY cent on partial issuance.
    base = int((Decimal(allocated + body.amount_minor) * credit / nominal).quantize(Decimal(1), rounding=ROUND_HALF_UP)) - base_allocated
    if base <= 0:
        raise HTTPException(409, "Fonlama değerlemesi kuruş hassasiyetinde doğrulanamadı")
    return {"funding_entry_hash": entry["entry_hash"], "issued_base_minor": base, "remaining_base_minor": base}


async def _record(db, tenant, actor, body, key, digest, action, instrument, result, session, *, payment=None, journal=None):
    from core.audit_chain import append_audit_log
    from shared_kernel.audit_helper import build_audit_entry

    op = {"_id": key, "id": str(body.request_id), "tenant_id": tenant, "action": action,
        "instrument_id": instrument["id"], "kind": instrument["kind"], "business_date": await _day(db, tenant, session),
        "booking_id": getattr(body, "booking_id", instrument["origin_booking_id"]), "fingerprint": digest,
        "reference": body.reference, "reason": body.reason, "actor_id": actor.id,
        "created_at": datetime.now(UTC).isoformat(), "result": result,
        "payment_id": payment, "gl_journal_entry_id": journal}
    await db.billing_instrument_operations.insert_one(op, session=session)
    entry = build_audit_entry(actor.id, tenant, "reservation", op["booking_id"], "billing_instrument_" + action)
    entry.update(actor_name=getattr(actor, "name", actor.id), actor_role=getattr(actor, "role", None),
        override_reason=body.reason, details=f"{KINDS[instrument['kind']]} / {action}: {body.reason}",
        after_snapshot={key: value for key, value in op.items() if key not in {"_id", "fingerprint", "result"}})
    await append_audit_log(db, entry, session=session, require_chain=True)
    return result


async def issue(db, tenant, actor, body, *, session):
    if session is None:
        raise HTTPException(503, "Finansal işlem transaction desteği gerektirir")
    await _serialize(db, tenant, session)
    key, digest, prior = await _replay(db, tenant, body, session, action="issue")
    if prior:
        return prior["result"]
    booking = await _booking(db, tenant, body.booking_id, session)
    day = await _day(db, tenant, session)
    if body.expires_on and body.expires_on.isoformat() < day:
        raise HTTPException(422, "Geçmiş vadeli hak açılamaz")
    if await db.billing_instruments.find_one({"tenant_id": tenant, "kind": body.kind, "reference": body.reference}, session=session):
        raise HTTPException(409, "Bu belge referansı zaten kullanılmış")
    types = {"liability"} if body.kind in FUNDED else {"expense"} if body.kind in {"loyalty_redemption", "write_off"} else {"asset"}
    await _account(db, tenant, body.account_code, types, session)
    guest = booking.get("guest_id")
    if body.kind in {"wallet", "loyalty_redemption"} and not guest:
        raise HTTPException(409, "Cüzdan/sadakat için rezervasyon misafir profiline bağlı olmalı")
    if body.kind == "loyalty_redemption":
        members = await db.loyalty_members.find({"tenant_id": tenant, "guest_id": guest}, session=session).to_list(2)
        if len(members) != 1:
            raise HTTPException(409, "Tekil mevcut sadakat üyeliği doğrulanamadı; puan üretilmedi")
    document = {"_id": key, "id": str(body.request_id), "tenant_id": tenant,
        **body.model_dump(mode="json", exclude={"request_id", "booking_id"}), "origin_booking_id": body.booking_id,
        "owner_guest_id": guest, "issued_minor": body.amount_minor, "remaining_minor": body.amount_minor,
        "status": "pending" if body.kind == "cheque_pending_clearance" else "active",
        "created_at": datetime.now(UTC).isoformat(), "created_by": actor.id, "business_date": day}
    if body.kind in FUNDED:
        document.update(await _funding(db, tenant, body, session))
    await db.billing_instruments.insert_one(document, session=session)
    return await _record(db, tenant, actor, body, key, digest, "issue", document, public(document), session)


def _base(amount, rate):
    return int((Decimal(amount) * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))


async def apply(db, tenant, actor, instrument_id, body, *, session, record_cash):
    if session is None:
        raise HTTPException(503, "Finansal işlem transaction desteği gerektirir")
    await _serialize(db, tenant, session)
    key, digest, prior = await _replay(db, tenant, body, session, instrument_id=instrument_id, action="apply")
    if prior:
        return prior["result"]
    item = await db.billing_instruments.find_one({"tenant_id": tenant, "id": instrument_id}, session=session)
    if not item:
        raise HTTPException(404, "Ödeme aracı bulunamadı")
    booking = await _booking(db, tenant, body.booking_id, session)
    if item.get("owner_guest_id"):
        if item["owner_guest_id"] != booking.get("guest_id"):
            raise HTTPException(409, "Bu hak başka bir misafire ait")
    elif item["origin_booking_id"] != body.booking_id:
        raise HTTPException(409, "Bu hak başka bir rezervasyona ait")
    day = await _day(db, tenant, session)
    if item.get("expires_on") and item["expires_on"] < day:
        raise HTTPException(409, "Hakkın süresi dolmuş")
    is_cheque = item["kind"] == "cheque_pending_clearance"
    if item["status"] != ("pending" if is_cheque else "active") or body.amount_minor > item["remaining_minor"]:
        raise HTTPException(409, "Araç durumu veya kullanılabilir limit yetersiz")
    if is_cheque and (body.amount_minor != item["remaining_minor"] or item["due_on"] > day):
        raise HTTPException(409, "Çek vadesinde ve tam tutarla, harici banka tahsil belgesiyle kapatılmalı")
    folio = await select_booking_folio(db, tenant, body.booking_id, body.folio_id, session=session)
    code = require_cent_currency(folio.get("currency") or booking.get("currency"))
    if code != item["currency"] or require_cent_currency(booking.get("currency")) != code or (code == "TRY" and body.rate_to_try != 1):
        raise HTTPException(409, "Aynı para birimi gerekli; TRY kuru 1 olmalı")
    if folio.get("invoice_id") or await db.invoices.find_one({"tenant_id": tenant, "voided": {"$ne": True},
        "status": {"$nin": ["cancelled", "canceled", "void", "voided"]},
        "$or": [{"folio_id": folio["id"]}, {"folio_ids": folio["id"]}, {"booking_id": body.booking_id}]}, session=session):
        raise HTTPException(409, "Faturalı folyo için ayrı belge/mali düzeltme akışı gerekli")
    snap = (await folio_snapshots(db, tenant, [folio], fallback_currency=code, session=session))[folio["id"]]
    if any(cur != code and value for cur, value in snap["balance_by_currency"].items()) or minor(snap["balance_by_currency"].get(code, 0)) < body.amount_minor:
        raise HTTPException(409, "Mutabık folyo borcu bu tutar için yeterli değil")
    mapping = await db.gl_operational_mappings.find_one({"tenant_id": tenant}, session=session)
    if not mapping or not mapping.get("enabled") or not mapping.get("receivable_account_code"):
        raise HTTPException(409, "Aktif muhasebe köprüsü ve misafir alacak hesabı gerekli")
    ar = mapping["receivable_account_code"]
    await _account(db, tenant, ar, {"asset"}, session)
    if ar == item["account_code"]:
        raise HTTPException(409, "Kaynak ve misafir alacak hesabı aynı olamaz")
    if is_cheque and item["account_code"] != mapping.get("bank_account_code"):
        raise HTTPException(409, "Çek yalnız tanımlı banka hesabına tahsil kaydedilebilir")
    types = {"liability"} if item["kind"] in FUNDED else {"expense"} if item["kind"] in {"loyalty_redemption", "write_off"} else {"asset"}
    await _account(db, tenant, item["account_code"], types, session)
    paid_base = _base(body.amount_minor, body.rate_to_try)
    if paid_base <= 0:
        raise HTTPException(422, "Değerleme en az bir TRY kuruş olmalı")
    source_base = paid_base
    if item["kind"] in FUNDED:
        funding = await db.gl_journal_entries.find_one({"tenant_id": tenant, "id": item["funding_entry_id"]}, session=session)
        if not funding or funding.get("entry_hash") != item["funding_entry_hash"] or not verify_journal_entry_hash(funding):
            raise HTTPException(409, "Özgün fonlama fişi değişmiş")
        await _assert_funding_not_reversed(db, tenant, funding, session)
        source_base = item["remaining_base_minor"] if body.amount_minor == item["remaining_minor"] else _base(
            body.amount_minor, Decimal(item["remaining_base_minor"]) / item["remaining_minor"])
        if source_base <= 0:
            raise HTTPException(422, "Kısmi kullanımın defter değeri bir kuruştan az")
    points = None
    if item["kind"] == "loyalty_redemption":
        if body.amount_minor % item["point_value_minor"]:
            raise HTTPException(422, "Tutar tanımlı puan değerinin tam katı olmalı")
        points = body.amount_minor // item["point_value_minor"]
        members = await db.loyalty_members.find({"tenant_id": tenant, "guest_id": item["owner_guest_id"]}, session=session).to_list(2)
        if len(members) != 1:
            raise HTTPException(409, "Tekil sadakat üyesi doğrulanamadı")
        updated = await db.loyalty_members.update_one({"tenant_id": tenant, "guest_id": item["owner_guest_id"],
            "points_balance": {"$gte": points}}, {"$inc": {"points_balance": -points}}, session=session)
        if updated.matched_count != 1:
            raise HTTPException(409, "Sadakat puanı yetersiz; puan üretilmedi")
        await db.loyalty_transactions.insert_one({"id": str(body.request_id), "tenant_id": tenant,
            "guest_id": item["owner_guest_id"], "type": "redeem", "points": -points,
            "source": "folio_settlement", "reference_id": str(body.request_id), "created_at": datetime.now(UTC).isoformat()}, session=session)
    lines = [{"account_code": item["account_code"], "debit": source_base / 100}, {"account_code": ar, "credit": paid_base / 100}]
    if code != "TRY":
        # Preserve native monetary positions, not just the TRY journal value.
        source_rate = (Decimal(source_base) / body.amount_minor).quantize(Decimal(".000001"), rounding=ROUND_HALF_UP)
        if abs(_base(body.amount_minor, source_rate) - source_base) > 1:
            raise HTTPException(422, "Kısmi kullanımın kaynak kur hassasiyeti yetersiz; ayrı mali değerleme gerekli")
        lines[0].update(currency=code, foreign_amount=body.amount_minor / 100, exchange_rate=str(source_rate))
        lines[1].update(currency=code, foreign_amount=body.amount_minor / 100, exchange_rate=str(body.rate_to_try))
    delta = source_base - paid_base
    if delta:
        gain = delta > 0
        account = body.fx_gain_account if gain else body.fx_loss_account
        if not account or account in {ar, item["account_code"]}:
            raise HTTPException(409, "Gerçekleşen kur farkı için ayrı kazanç/zarar hesabı gerekli")
        await _account(db, tenant, account, {"revenue"} if gain else {"expense"}, session)
        lines.append({"account_code": account, "credit" if gain else "debit": abs(delta) / 100})
    manifest = {"version": 1, "operation_id": str(body.request_id), "instrument_id": instrument_id, "kind": item["kind"],
        "booking_id": body.booking_id, "folio_id": folio["id"], "currency": code, "amount_minor": body.amount_minor,
        "source_base_minor": source_base, "settlement_base_minor": paid_base, "rate_to_try": str(body.rate_to_try),
        "rate_reference": body.rate_reference, "reference": body.reference, "reason": body.reason, "points": points,
        "business_date": day, "payment_id": "instrument:" + str(body.request_id)}
    try:
        journal = await post_journal_entry(SessionDatabase(db, session), tenant, date=day,
            memo=f"{KINDS[item['kind']]}: {body.reason}", lines=lines, source="billing_settlement", source_ref=str(body.request_id),
            actor=actor.id, idempotency_key=key, source_manifest=manifest)
    except GLPostingError as exc:
        raise HTTPException(409, str(exc)) from exc
    payment = {"_id": key, "id": manifest["payment_id"], "tenant_id": tenant, "booking_id": body.booking_id,
        "folio_id": folio["id"], "amount": body.amount_minor / 100, "currency": code,
        "method": "bank_transfer" if is_cheque else item["kind"], "payment_type": "payment" if is_cheque else "non_cash_settlement",
        "status": "paid", "voided": False, "business_date": day, "processed_at": datetime.now(UTC).isoformat(),
        "processed_by": actor.id, "reference": body.reference, "notes": body.reason,
        "billing_settlement_id": str(body.request_id), "gl_journal_entry_id": journal["id"], "instrument_id": instrument_id,
        "reporting_currency": "TRY", "reporting_amount": paid_base / 100, "exchange_rate_date": day}
    if is_cheque:
        cash = await record_cash(tenant_id=tenant, amount=paid_base / 100, method="bank_transfer", direction="in",
            description="Harici bankada tahsil edilmiş çek: " + body.reference, txn_type="folio_payment", ref_type="payment",
            ref_id=payment["id"], created_by=actor.id, idempotency_key=key, require_open_shift=True, session=session)
        if not cash:
            raise HTTPException(503, "Çek tahsilatının kasa kaydı doğrulanamadı")
    await db.payments.insert_one(payment, session=session)
    changes = {"remaining_minor": item["remaining_minor"] - body.amount_minor}
    if item["kind"] in FUNDED:
        changes["remaining_base_minor"] = item["remaining_base_minor"] - source_base
    if not changes["remaining_minor"]:
        changes["status"] = "cleared" if is_cheque else "exhausted"
    updated = await db.billing_instruments.update_one({"tenant_id": tenant, "id": instrument_id, "remaining_minor": item["remaining_minor"], "status": item["status"]}, {"$set": changes}, session=session)
    if updated.matched_count != 1:
        raise HTTPException(409, "Araç başka bir işlem tarafından kullanıldı")
    fresh = (await folio_snapshots(db, tenant, [folio], fallback_currency=code, session=session))[folio["id"]]
    updated = await db.folios.update_one({"tenant_id": tenant, "id": folio["id"], "status": "open"},
        {"$set": {"balance": fresh["balance_by_currency"].get(code, 0)}}, session=session)
    if updated.matched_count != 1:
        raise HTTPException(409, "Açık folyo değişti")
    result = {"id": str(body.request_id), "status": "applied", **manifest, "gl_journal_entry_id": journal["id"],
        "remaining_minor": changes["remaining_minor"], "balance": fresh["balance_by_currency"].get(code, 0),
        "cash_collection": is_cheque, "execution": "external_bank_clearance_record" if is_cheque else "non_cash_ledger_settlement"}
    return await _record(db, tenant, actor, body, key, digest, "apply", item, result, session,
        payment=payment["id"], journal=journal["id"])


async def exclude_direct_cheques(db, tenant, payments):
    """Do not post a cleared cheque again at night audit; verify its GL proof."""
    result = []
    for payment in payments:
        if not payment.get("billing_settlement_id") or payment.get("method") != "bank_transfer":
            result.append(payment)
            continue
        entry = await db.gl_journal_entries.find_one({"tenant_id": tenant, "id": payment.get("gl_journal_entry_id"),
            "source": {"$in": ["billing_settlement", "billing_settlement_reversal"]}, "source_ref": payment["billing_settlement_id"]}, {"_id": 0})
        proof = (entry or {}).get("source_manifest") or {}
        if (not entry or not verify_journal_entry_hash(entry) or proof.get("kind") != "cheque_pending_clearance"
            or proof.get("payment_id") != payment.get("id") or abs(proof.get("amount_minor", 0)) != abs(minor(payment["amount"]))
            or proof.get("currency") != payment.get("currency") or proof.get("business_date") != payment.get("business_date")
            or proof.get("folio_id") != payment.get("folio_id") or proof.get("booking_id") != payment.get("booking_id")
            or (proof.get("amount_minor", 0) < 0) != (payment.get("payment_type") == "refund")):
            raise HTTPException(409, "Çek tahsilatının özgün muhasebe bağlantısı doğrulanamadı")
    return result


async def reverse(db, tenant, actor, operation_id, body, *, session, record_cash):
    if session is None:
        raise HTTPException(503, "Finansal işlem transaction desteği gerektirir")
    await _serialize(db, tenant, session)
    key, digest, replay = await _replay(db, tenant, body, session, instrument_id=operation_id, action="reverse")
    if replay:
        return replay["result"]
    original = await db.billing_instrument_operations.find_one({"tenant_id": tenant, "id": operation_id,
        "booking_id": body.booking_id, "action": "apply"}, session=session)
    if not original:
        raise HTTPException(404, "Özgün mahsup bulunamadı")
    if not (await reconcile(db, tenant, booking_id=body.booking_id))["healthy"]:
        raise HTTPException(409, "Özgün mahsup mutabakatı doğrulanmadan ters kayıt yapılamaz")
    if await db.billing_instrument_operations.find_one({"tenant_id": tenant, "original_operation_id": operation_id, "action": "reverse"}, session=session):
        raise HTTPException(409, "Mahsup zaten ters kayıtla iade edilmiş")
    await _booking(db, tenant, body.booking_id, session)
    item = await db.billing_instruments.find_one({"tenant_id": tenant, "id": original["instrument_id"]}, session=session)
    source = original["result"]
    folio = await select_booking_folio(db, tenant, body.booking_id, source["folio_id"], session=session)
    if folio.get("invoice_id") or await db.invoices.find_one({"tenant_id": tenant, "voided": {"$ne": True},
        "status": {"$nin": ["cancelled", "canceled", "void", "voided"]},
        "$or": [{"folio_id": folio["id"]}, {"folio_ids": folio["id"]}, {"booking_id": body.booking_id}]}, session=session):
        raise HTTPException(409, "Faturalı mahsup için önce belge düzeltme akışı gerekli")
    old_entry = await db.gl_journal_entries.find_one({"tenant_id": tenant, "id": original["gl_journal_entry_id"]}, session=session)
    payment = await db.payments.find_one({"tenant_id": tenant, "id": original["payment_id"]}, session=session)
    if not item or not old_entry or not verify_journal_entry_hash(old_entry) or not payment or payment.get("voided"):
        raise HTTPException(409, "Özgün kaynaklar doğrulanamadı")
    if old_entry.get("source_manifest", {}).get("payment_id") != payment["id"] or minor(payment["amount"]) != source["amount_minor"]:
        raise HTTPException(409, "Özgün mahsup/muhasebe bağlantısı değişmiş")
    remaining = item["remaining_minor"] + source["amount_minor"]
    if remaining > item["issued_minor"]:
        raise HTTPException(409, "İade hakkın ilk limitini aşamaz")
    day = await _day(db, tenant, session)
    lines = [{"account_code": row["account_code"], "debit": row["credit"], "credit": row["debit"], "memo": "Bağlı mahsup ters kaydı",
        **({"currency": row["currency"], "foreign_amount": row["foreign_amount"], "exchange_rate": row["exchange_rate"]} if row.get("currency") else {})} for row in old_entry["lines"]]
    pid = "instrument:" + str(body.request_id)
    manifest = {**old_entry["source_manifest"], "operation_id": str(body.request_id), "original_operation_id": operation_id,
        "amount_minor": -source["amount_minor"], "payment_id": pid, "business_date": day,
        "reference": body.reference, "reason": body.reason}
    try:
        journal = await post_journal_entry(SessionDatabase(db, session), tenant, date=day, memo="Mahsup ters kaydı: " + body.reason,
            lines=lines, source="billing_settlement_reversal", source_ref=str(body.request_id), actor=actor.id,
            idempotency_key=key, reverses_entry_id=old_entry["id"], reversal_reason=body.reason, source_manifest=manifest)
    except GLPostingError as exc:
        raise HTTPException(409, str(exc)) from exc
    refund = {**payment, "_id": key, "id": pid, "payment_type": "refund", "reference": body.reference, "notes": body.reason,
        "business_date": day, "exchange_rate_date": day, "processed_at": datetime.now(UTC).isoformat(), "processed_by": actor.id,
        "billing_settlement_id": str(body.request_id), "gl_journal_entry_id": journal["id"], "original_payment_id": payment["id"],
        "amount": -abs(payment["amount"]), "reporting_amount": -abs(payment["reporting_amount"])}
    await db.payments.insert_one(refund, session=session)
    if source.get("points"):
        update = await db.loyalty_members.update_one({"tenant_id": tenant, "guest_id": item["owner_guest_id"]},
            {"$inc": {"points_balance": source["points"]}}, session=session)
        if update.matched_count != 1:
            raise HTTPException(409, "Sadakat üyesi bulunamadı; iade tamamlanamadı")
        await db.loyalty_transactions.insert_one({"id": str(body.request_id), "tenant_id": tenant, "guest_id": item["owner_guest_id"],
            "type": "refund", "points": source["points"], "source": "folio_settlement_reversal", "reference_id": operation_id,
            "created_at": datetime.now(UTC).isoformat()}, session=session)
    cheque = item["kind"] == "cheque_pending_clearance"
    if cheque:
        transaction = await record_cash(tenant_id=tenant, amount=source["settlement_base_minor"] / 100, method="bank_transfer", direction="out",
            description="Harici banka çek iadesi: " + body.reference, txn_type="refund", ref_type="payment", ref_id=pid,
            created_by=actor.id, idempotency_key=key, require_open_shift=True, session=session)
        if not transaction:
            raise HTTPException(503, "Çek iadesinin kasa kaydı doğrulanamadı")
    changes = {"remaining_minor": remaining, "status": "returned" if cheque else "active"}
    if item["kind"] in FUNDED:
        changes["remaining_base_minor"] = item["remaining_base_minor"] + source["source_base_minor"]
    await db.billing_instruments.update_one({"tenant_id": tenant, "id": item["id"]}, {"$set": changes}, session=session)
    snapshot = (await folio_snapshots(db, tenant, [folio], fallback_currency=item["currency"], session=session))[folio["id"]]
    updated = await db.folios.update_one({"tenant_id": tenant, "id": folio["id"], "status": "open"},
        {"$set": {"balance": snapshot["balance_by_currency"].get(item["currency"], 0)}}, session=session)
    if updated.matched_count != 1:
        raise HTTPException(409, "Açık folyo değişti")
    result = {"id": str(body.request_id), "status": "reversed", "original_operation_id": operation_id,
        "payment_id": pid, "gl_journal_entry_id": journal["id"], "remaining_minor": remaining,
        "booking_id": body.booking_id, "currency": item["currency"], "amount_minor": source["amount_minor"]}
    await _record(db, tenant, actor, body, key, digest, "reverse", item, result, session, payment=pid, journal=journal["id"])
    await db.billing_instrument_operations.update_one({"tenant_id": tenant, "id": str(body.request_id)},
        {"$set": {"original_operation_id": operation_id}}, session=session)
    return result


async def reconcile(db, tenant, *, business_date=None, booking_id=None):
    query = {"tenant_id": tenant, "action": {"$in": ["apply", "reverse"]}}
    if business_date:
        query["business_date"] = business_date
    if booking_id:
        query["booking_id"] = booking_id
    operations = await db.billing_instrument_operations.find(query, {"_id": 0}).to_list(None)
    issues, totals = [], {}
    for op in operations:
        entry = await db.gl_journal_entries.find_one({"tenant_id": tenant, "id": op["gl_journal_entry_id"]}, {"_id": 0})
        payment = await db.payments.find_one({"tenant_id": tenant, "id": op["payment_id"]}, {"_id": 0})
        proof = (entry or {}).get("source_manifest") or {}
        sign = -1 if op["action"] == "reverse" else 1
        result = op["result"]
        if op["kind"] in FUNDED:
            item = await db.billing_instruments.find_one({"tenant_id": tenant, "id": op["instrument_id"]})
            funding = await db.gl_journal_entries.find_one({"tenant_id": tenant, "id": (item or {}).get("funding_entry_id")})
            invalid_funding = not funding or not verify_journal_entry_hash(funding) or funding.get("entry_hash") != (item or {}).get("funding_entry_hash")
            if not invalid_funding:
                try:
                    await _assert_funding_not_reversed(db, tenant, funding, None)
                except HTTPException:
                    invalid_funding = True
            if invalid_funding:
                issues.append({"operation_id": op["id"], "reason": "funding_source_invalid"})
                continue
        if (not entry or not verify_journal_entry_hash(entry) or not payment or payment.get("voided")
            or payment.get("status") != "paid" or entry.get("source") != ("billing_settlement" if sign > 0 else "billing_settlement_reversal")
            or entry.get("source_ref") != op["id"] or proof.get("payment_id") != payment.get("id")
            or proof.get("amount_minor") != sign * result["amount_minor"] or minor(payment.get("amount")) != sign * result["amount_minor"]
            or proof.get("currency") != payment.get("currency") or proof.get("booking_id") != op["booking_id"]
            or proof.get("folio_id") != payment.get("folio_id") or proof.get("business_date") != payment.get("business_date")
            or payment.get("billing_settlement_id") != op["id"] or payment.get("instrument_id") != op["instrument_id"]
            or payment.get("method") != ("bank_transfer" if op["kind"] == "cheque_pending_clearance" else op["kind"])
            or abs(minor(payment.get("reporting_amount"))) != proof.get("settlement_base_minor")
            or (payment.get("payment_type") == "refund") != (sign < 0)):
            issues.append({"operation_id": op["id"], "reason": "payment_or_gl_source_mismatch"})
            continue
        code = payment["currency"]
        group = totals.setdefault(code, {"non_cash_minor": 0, "cleared_cheque_minor": 0})
        group["cleared_cheque_minor" if op["kind"] == "cheque_pending_clearance" else "non_cash_minor"] += sign * result["amount_minor"]
    return {"healthy": not issues, "operation_count": len(operations), "totals_by_currency": totals, "issues": issues,
        "basis": "sealed_settlement_journal_to_payment", "business_date": business_date}
