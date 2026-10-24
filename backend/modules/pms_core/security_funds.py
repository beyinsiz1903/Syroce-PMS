"""Refundable security money is a liability, not a room payment or a hold.

External receipt/refund evidence is recorded here; no card charge/refund is
initiated. Application moves existing money into a folio without collecting it
again. Cashier movement and liability movement share the caller's transaction.
"""
from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from modules.pms_core.enterprise_billing import currency, fingerprint, minor, require_cent_currency
from modules.pms_core.folio_selection import select_booking_folio
from modules.pms_core.receivable_reporting import folio_snapshots


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    booking_id: str = Field(min_length=1, max_length=100)
    amount_minor: int = Field(strict=True, gt=0, le=100_000_000_000)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    method: Literal["cash", "card", "bank_transfer"]
    reference: str = Field(min_length=3, max_length=200)
    reason: str = Field(min_length=3, max_length=500)


class Movement(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    action: Literal["refund", "apply"]
    amount_minor: int = Field(strict=True, gt=0, le=100_000_000_000)
    folio_id: str | None = Field(default=None, min_length=1, max_length=100)
    reference: str = Field(min_length=3, max_length=200)
    reason: str = Field(min_length=3, max_length=500)


def public(row):
    return {key: value for key, value in row.items() if key not in {"_id", "fingerprint"}}


async def _day(database, tenant_id, session):
    settings = await database.tenant_settings.find_one({"tenant_id": tenant_id}, {"business_date": 1}, session=session)
    try:
        return date.fromisoformat(str((settings or {}).get("business_date"))).isoformat()
    except ValueError:
        raise HTTPException(409, "Açık iş günü doğrulanamadı") from None


async def _replay(database, tenant_id, key, digest, session):
    prior = await database.security_fund_operations.find_one({"_id": key, "tenant_id": tenant_id}, session=session)
    if prior:
        if prior["fingerprint"] != digest:
            raise HTTPException(409, "İşlem anahtarı farklı güvence hareketi için kullanılmış")
        return prior["result"]
    return None


async def _cash(record_cash, tenant_id, fund, amount_minor, direction, actor, operation, session):
    # Foreign cash needs an immutable conversion snapshot before it can enter
    # the existing TRY cashier drawer; never substitute today's/default FX.
    if fund["method"] == "cash" and fund["currency"] != "TRY":
        raise HTTPException(422, "Bu akışta yabancı para nakit güvence desteklenmiyor; kur izli kasa akışı gerekli")
    if fund["method"] != "cash":
        return
    transaction = await record_cash(tenant_id=tenant_id, amount=amount_minor / 100, method="cash", direction=direction,
        description=f"İade edilebilir güvence: {fund['id']}", txn_type="security_deposit" if direction == "in" else "security_deposit_refund",
        ref_type="security_fund", ref_id=fund["id"], created_by=actor, idempotency_key=operation,
        require_open_shift=True, session=session)
    if not transaction:
        raise HTTPException(503, "Güvence kasa hareketi doğrulanamadı; işlem kaydedilmedi")


async def receive(database, tenant_id, actor, body, *, session, record_cash):
    if session is None:
        raise HTTPException(503, "Güvence için transaction desteği gerekli")
    key = f"security-fund:{tenant_id}:{body.request_id}"
    digest = fingerprint(body.model_dump(mode="json"))
    prior = await _replay(database, tenant_id, key, digest, session)
    if prior:
        return prior
    duplicate = await database.security_funds.find_one({"tenant_id": tenant_id, "booking_id": body.booking_id,
        "method": body.method, "currency": body.currency, "reference": body.reference}, session=session)
    if duplicate:
        if duplicate["received_minor"] != body.amount_minor or duplicate["reason"] != body.reason:
            raise HTTPException(409, "Aynı güvence fişi farklı tutar veya gerekçe ile kullanılmış")
        return public(duplicate)
    booking = await database.bookings.find_one({"tenant_id": tenant_id, "id": body.booking_id}, session=session)
    if not booking:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    if booking.get("status") in {"checked_out", "cancelled", "no_show"}:
        raise HTTPException(409, "Tamamlanmış rezervasyon için yeni güvence alınamaz")
    if currency(booking.get("currency")) != currency(body.currency):
        raise HTTPException(409, "Güvence para birimi rezervasyon ile aynı olmalı")
    require_cent_currency(body.currency)
    day = await _day(database, tenant_id, session)
    fund = {"_id": key, "id": str(body.request_id), "tenant_id": tenant_id, "booking_id": body.booking_id,
        "currency": body.currency, "method": body.method, "received_minor": body.amount_minor, "remaining_minor": body.amount_minor,
        "refunded_minor": 0, "applied_minor": 0, "reference": body.reference, "reason": body.reason, "status": "held",
        "recorded_by": actor, "business_date": day, "created_at": datetime.now(UTC).isoformat(), "execution": "external_record_only"}
    await _cash(record_cash, tenant_id, fund, body.amount_minor, "in", actor, key, session)
    await database.security_funds.insert_one(fund, session=session)
    result = public(fund)
    await _evidence(database, tenant_id, actor, key, digest, fund, result, "received", body.amount_minor, day, session, body.reference, body.reason)
    return result


async def move(database, tenant_id, actor, fund_id, body, *, session, record_cash):
    if session is None:
        raise HTTPException(503, "Güvence için transaction desteği gerekli")
    key = f"security-move:{tenant_id}:{body.request_id}"
    digest = fingerprint({"fund_id": str(fund_id), **body.model_dump(mode="json")})
    prior = await _replay(database, tenant_id, key, digest, session)
    if prior:
        return prior
    fund = await database.security_funds.find_one({"_id": f"security-fund:{tenant_id}:{fund_id}", "tenant_id": tenant_id}, session=session)
    if not fund:
        raise HTTPException(404, "Güvence kaydı bulunamadı")
    previous = await database.security_fund_operations.find_one({"tenant_id": tenant_id, "fund_id": str(fund_id),
        "action": body.action, "reference": body.reference}, session=session)
    if previous:
        if (previous["amount_minor"] != body.amount_minor or previous.get("reason") != body.reason
                or previous.get("folio_id") != body.folio_id):
            raise HTTPException(409, "Aynı güvence hareketi referansı farklı içerikle kullanılmış")
        return previous["result"]
    if body.amount_minor > fund["remaining_minor"]:
        raise HTTPException(409, "İşlem tutarı kalan güvenceyi aşamaz")
    day = await _day(database, tenant_id, session)
    if body.action == "apply":
        if not body.folio_id:
            raise HTTPException(422, "Güvence mahsubu için hedef folyo gerekli")
        folio = await select_booking_folio(database, tenant_id, fund["booking_id"], body.folio_id, session=session)
        if currency(folio.get("currency") or fund["currency"]) != fund["currency"]:
            raise HTTPException(409, "Güvence ve folyo para birimleri aynı olmalı")
        snapshots = await folio_snapshots(database, tenant_id, [folio], fallback_currency=fund["currency"], session=session)
        balances = snapshots[folio["id"]]["balance_by_currency"]
        if any(code != fund["currency"] and value for code, value in balances.items()):
            raise HTTPException(409, "Çok para birimli folyo önce mutabık hale getirilmeli")
        if body.amount_minor > minor(balances.get(fund["currency"], 0)):
            raise HTTPException(409, "Güvence mahsubu açık folyo borcunu aşamaz")
        amount = body.amount_minor / 100
        await database.payments.insert_one({"_id": key, "id": str(body.request_id), "tenant_id": tenant_id,
            "booking_id": fund["booking_id"], "folio_id": folio["id"], "currency": fund["currency"], "amount": amount,
            "method": "security_deposit_application", "payment_type": "interim", "status": "paid", "voided": False,
            "security_fund_id": fund["id"], "reference": key, "notes": body.reason, "processed_by": actor,
            "processed_at": datetime.now(UTC).isoformat(), "business_date": day}, session=session)
        await database.folios.update_one({"tenant_id": tenant_id, "id": folio["id"], "status": "open"},
            {"$set": {"balance": balances[fund["currency"]] - amount}}, session=session)
    else:
        if body.folio_id:
            raise HTTPException(422, "Güvence iadesi folyoya ödeme/iade yazmaz")
        await _cash(record_cash, tenant_id, fund, body.amount_minor, "out", actor, key, session)
    remaining = fund["remaining_minor"] - body.amount_minor
    changes = {"remaining_minor": remaining, "status": "held" if remaining else "closed",
        "refunded_minor": fund["refunded_minor"] + (body.amount_minor if body.action == "refund" else 0),
        "applied_minor": fund["applied_minor"] + (body.amount_minor if body.action == "apply" else 0)}
    await database.security_funds.update_one({"_id": fund["_id"], "tenant_id": tenant_id}, {"$set": changes}, session=session)
    result = public({**fund, **changes})
    await _evidence(database, tenant_id, actor, key, digest, fund, result, body.action, body.amount_minor, day, session, body.reference, body.reason, body.folio_id)
    return result


async def _evidence(database, tenant_id, actor, key, digest, fund, result, action, amount, day, session, reference, reason, folio_id=None):
    await database.security_fund_operations.insert_one({"_id": key, "tenant_id": tenant_id, "fund_id": fund["id"],
        "booking_id": fund["booking_id"], "action": action, "amount_minor": amount, "currency": fund["currency"],
        "business_date": day, "fingerprint": digest, "reference": reference, "reason": reason,
        "folio_id": folio_id, "result": result}, session=session)
    await database.pms_audit_trail.insert_one({"id": key, "tenant_id": tenant_id, "entity_type": "security_fund",
        "entity_id": fund["id"], "action": f"security_fund_{action}", "performed_by": actor,
        "timestamp": datetime.now(UTC).isoformat(), "metadata": {"amount_minor": amount, "currency": fund["currency"],
            "booking_id": fund["booking_id"], "folio_id": folio_id, "remaining_minor": result["remaining_minor"],
            "reference": reference, "reason": reason}}, session=session)
