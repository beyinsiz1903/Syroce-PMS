"""Enterprise billing controls. No provider calls and no invented collections.

Concessions cover selected POSTED charges only; future-night pricing remains
in the rate-plan workflow. Approval and the non-cash ledger offset are one
transaction, with a separate requester and an explicitly configured limit.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.pms_core.folio_selection import select_booking_folio
from modules.pms_core.receivable_reporting import folio_snapshots

CENT_CURRENCIES = frozenset({"TRY", "USD", "EUR", "GBP", "CHF"})


def minor(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise ValueError
        return int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (ValueError, ArithmeticError):
        raise HTTPException(409, "Finansal tutar doğrulanamadı") from None


def currency(value):
    code = str(value or "").strip().upper()
    code = "TRY" if code == "TL" else code
    if len(code) != 3 or not code.isascii() or not code.isalpha():
        raise HTTPException(409, "Finansal işlem için para birimi doğrulanmalı")
    return code


def manual_collection_method(value):
    method = str(getattr(value, "value", value) or "").strip().lower()
    if method not in {"cash", "card", "credit_card", "bank_transfer", "transfer", "online", "check"}:
        raise HTTPException(422, "Bu işlem tahsilat yöntemi değildir. İkram/indirim, cari, güvence ve provizyon için ilgili ayrı akışı kullanın")
    return method


def require_cent_currency(value):
    code = currency(value)
    if code not in CENT_CURRENCIES:
        raise HTTPException(422, "Bu yeni kurumsal akışta doğrulanmış para birimleri TRY/USD/EUR/GBP/CHF ile sınırlıdır; farklı hassasiyetler için ayrı kabul testi gerekli")
    return code


class BillingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Missing currency is deliberately NOT unlimited approval authority.
    approval_limits_minor: dict[str, Annotated[int, Field(strict=True, ge=0, le=100_000_000_000)]] = Field(default_factory=dict, max_length=30)

    @model_validator(mode="after")
    def limits(self):
        for code, amount in self.approval_limits_minor.items():
            if currency(code) != code or isinstance(amount, bool) or not 0 <= amount <= 100_000_000_000:
                raise ValueError("Limitler ISO para birimi ve negatif olmayan kuruş tutarı olmalı")
        return self


class ConcessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    booking_id: str = Field(min_length=1, max_length=100)
    folio_id: str = Field(min_length=1, max_length=100)
    charge_ids: list[str] = Field(min_length=1, max_length=200)
    kind: Literal["room_comp", "selected_services_comp", "service_recovery", "discount"]
    mode: Literal["full", "percentage", "amount"]
    percentage: Decimal | None = Field(default=None, gt=0, le=100, max_digits=5, decimal_places=2, allow_inf_nan=False)
    amount_minor: int | None = Field(default=None, strict=True, gt=0, le=100_000_000_000)
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def shape(self):
        if len(set(self.charge_ids)) != len(self.charge_ids) or any(not key for key in self.charge_ids):
            raise ValueError("Masraf kalemleri boş veya tekrarlı olamaz")
        if (self.mode == "percentage") != (self.percentage is not None):
            raise ValueError("Yüzde yalnız yüzdesel işlemde zorunludur")
        if (self.mode == "amount") != (self.amount_minor is not None):
            raise ValueError("Tutar yalnız tutarsal işlemde zorunludur")
        return self


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


async def policy(database, tenant_id, *, session=None):
    settings = await database.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0, "enterprise_billing": 1}, session=session)
    return BillingPolicy.model_validate((settings or {}).get("enterprise_billing") or {})


async def concession_basis(database, tenant_id, body, *, session):
    booking = await database.bookings.find_one({"tenant_id": tenant_id, "id": body.booking_id}, {"_id": 0}, session=session)
    if not booking:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    if booking.get("status") in {"cancelled", "checked_out", "no_show"}:
        raise HTTPException(409, "Tamamlanmış rezervasyon için ayrı finansal düzeltme akışı gerekli")
    folio = await select_booking_folio(database, tenant_id, body.booking_id, body.folio_id, session=session)
    code = currency(folio.get("currency") or booking.get("currency"))
    require_cent_currency(code)
    if folio.get("invoice_id") or await database.invoices.find_one({"tenant_id": tenant_id,
        "status": {"$nin": ["cancelled", "canceled", "void", "voided"]}, "voided": {"$ne": True},
        "$or": [{"booking_id": body.booking_id}, {"folio_id": body.folio_id}, {"folio_ids": {"$in": [body.folio_id]}}]}, session=session):
        raise HTTPException(409, "Faturaya bağlı hesapta önce fatura düzeltme akışı tamamlanmalı")
    snap = (await folio_snapshots(database, tenant_id, [folio], fallback_currency=code, session=session))[body.folio_id]
    if any(cur != code and value for cur, value in snap["balance_by_currency"].items()):
        raise HTTPException(409, "Çok para birimli folyo önce mutabık hale getirilmeli")
    selected = sorted([row for row in snap["charges"] if row.get("id") in body.charge_ids], key=lambda row: row["id"])
    if len(selected) != len(body.charge_ids):
        raise HTTPException(409, "Seçili masraflar değişti; yenileyin")
    for row in selected:
        category = str(row.get("charge_category") or row.get("category") or "")
        if minor(row["total"]) <= 0 or row.get("invoice_id") or category in {"split_adjustment", "opening_balance"}:
            raise HTTPException(409, "Yalnız pozitif, faturalanmamış asıl hizmetler seçilebilir")
        if body.kind == "room_comp" and category != "room":
            raise HTTPException(422, "Oda ikramında yalnız oda masrafları seçilebilir")
        if currency(row.get("currency") or code) != code:
            raise HTTPException(409, "Masraf para birimi folyo ile aynı olmalı")
    # Service identity survives folio moves. A previously comped charge must
    # never regain concession capacity simply because its payer window changed.
    applied = await database.billing_concessions.find({"tenant_id": tenant_id, "booking_id": body.booking_id,
        "status": "applied"}, session=session).to_list(None)
    remaining = {row["id"]: minor(row["total"]) for row in selected}
    for previous in applied:
        overlaps = set(previous.get("charge_ids") or []) & remaining.keys()
        if overlaps and not previous.get("allocated_charge_minor"):
            raise HTTPException(409, "Önceki ikramın hizmet dağılımı doğrulanamadı")
        for key in overlaps:
            remaining[key] -= previous["allocated_charge_minor"].get(key, 0)
    if any(value <= 0 for value in remaining.values()):
        raise HTTPException(409, "Seçilen hizmet için kullanılabilir ikram/indirim bakiyesi kalmamış")
    total = sum(remaining.values())
    amount = total if body.mode == "full" else body.amount_minor if body.mode == "amount" else int(
        (Decimal(total) * body.percentage / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if amount <= 0 or amount > total or amount > minor(snap["balance_by_currency"].get(code, 0)):
        raise HTTPException(409, "İkram/indirim seçili hizmetleri veya açık folyo borcunu aşamaz")
    # Other requests may share a charge. Any applied concession invalidates the
    # approval snapshot, even where the total balance was topped up meanwhile.
    basis = fingerprint({"charges": selected, "balance": snap["balance_by_currency"], "prior": sorted(
        [(str(row["_id"]), row["amount_minor"]) for row in applied])})
    allocation = {key: amount * value // total for key, value in remaining.items()}
    remainder = amount - sum(allocation.values())
    for key in sorted(allocation):
        if remainder and allocation[key] < remaining[key]:
            allocation[key] += 1
            remainder -= 1
    return {"currency": code, "amount_minor": amount, "selected_total_minor": total, "basis": basis,
            "allocated_charge_minor": allocation}


async def request_concession(database, tenant_id, actor, body, *, session):
    if session is None:
        raise HTTPException(503, "İkram talebi için transaction desteği gerekli")
    key = f"concession:{tenant_id}:{body.request_id}"
    payload = body.model_dump(mode="json")
    payload["charge_ids"] = sorted(payload["charge_ids"])
    digest = fingerprint(payload)
    old = await database.billing_concessions.find_one({"_id": key, "tenant_id": tenant_id}, session=session)
    if old:
        if old["fingerprint"] != digest:
            raise HTTPException(409, "İşlem anahtarı başka bir talebe ait")
        return public_concession(old)
    basis = await concession_basis(database, tenant_id, body, session=session)
    document = {"_id": key, "id": str(body.request_id), "tenant_id": tenant_id, **payload, **basis, "request_payload": payload,
        "fingerprint": digest, "requested_by": actor, "status": "requested", "created_at": datetime.now(UTC).isoformat()}
    await database.billing_concessions.insert_one(document, session=session)
    return public_concession(document)


def public_concession(row):
    return {key: value for key, value in row.items() if key not in {"_id", "basis", "fingerprint", "request_payload"}}


async def decide_concession(database, tenant_id, actor, request_id, approve, *, session):
    if session is None:
        raise HTTPException(503, "İkram onayı için transaction desteği gerekli")
    query = {"_id": f"concession:{tenant_id}:{request_id}", "tenant_id": tenant_id}
    row = await database.billing_concessions.find_one(query, session=session)
    if not row:
        raise HTTPException(404, "İkram talebi bulunamadı")
    if row["status"] != "requested":
        if (row["status"] == "applied") == approve:
            return public_concession(row)
        raise HTTPException(409, "Sonuçlanmış talebin kararı değiştirilemez")
    if row["requested_by"] == actor:
        raise HTTPException(403, "Talep sahibi kendi ikramını onaylayamaz veya reddedemez")
    now = datetime.now(UTC).isoformat()
    changes = {"status": "rejected", "decided_by": actor, "decided_at": now}
    if approve:
        body = ConcessionRequest.model_validate(row["request_payload"])
        basis = await concession_basis(database, tenant_id, body, session=session)
        if basis["basis"] != row["basis"] or basis["amount_minor"] != row["amount_minor"]:
            raise HTTPException(409, "Hesap değişti; eski talebi reddedip güncel tutarla yeni talep oluşturun")
        limit = (await policy(database, tenant_id, session=session)).approval_limits_minor.get(row["currency"])
        if limit is None or row["amount_minor"] > limit:
            raise HTTPException(403, "Bu para biriminde yeterli ikram onay limiti tanımlanmamış")
        settings = await database.tenant_settings.find_one({"tenant_id": tenant_id}, {"business_date": 1}, session=session)
        from datetime import date

        try:
            day = date.fromisoformat(str((settings or {}).get("business_date"))).isoformat()
        except ValueError:
            raise HTTPException(409, "Açık iş günü doğrulanamadı") from None
        amount = row["amount_minor"] / 100
        payment_id = f"concession:{request_id}"
        await database.payments.insert_one({"_id": f"{tenant_id}:{payment_id}", "id": payment_id, "tenant_id": tenant_id,
            "booking_id": row["booking_id"], "folio_id": row["folio_id"], "amount": amount, "currency": row["currency"],
            "method": "discount", "payment_type": "comp_adjustment" if row["kind"] != "discount" else "discount",
            "status": "paid", "voided": False, "reference": payment_id, "notes": row["reason"],
            "concession_id": str(request_id), "charge_ids": row["charge_ids"], "processed_by": actor,
            "processed_at": now, "business_date": day}, session=session)
        snapshots = await folio_snapshots(database, tenant_id, [await database.folios.find_one(
            {"tenant_id": tenant_id, "id": row["folio_id"]}, session=session)], fallback_currency=row["currency"], session=session)
        await database.folios.update_one({"tenant_id": tenant_id, "id": row["folio_id"], "status": "open"},
            {"$set": {"balance": snapshots[row["folio_id"]]["balance_by_currency"][row["currency"]]}}, session=session)
        changes.update(status="applied", payment_id=payment_id, business_date=day)
    await database.billing_concessions.update_one({**query, "status": "requested"}, {"$set": changes}, session=session)
    await database.pms_audit_trail.insert_one({"id": f"concession:{request_id}:{changes['status']}", "tenant_id": tenant_id,
        "entity_type": "folio", "entity_id": row["folio_id"], "action": f"concession_{changes['status']}",
        "performed_by": actor, "timestamp": now, "metadata": {"request_id": str(request_id), "requested_by": row["requested_by"],
            "amount_minor": row["amount_minor"], "currency": row["currency"], "reason": row["reason"]}}, session=session)
    return public_concession({**row, **changes})


async def payment_catalog(database, tenant_id):
    from core.payments.contracts import PaymentError
    from core.payments.registry import get_provider_for_tenant

    provider_name, capabilities, readiness = None, {}, "not_configured"
    try:
        provider = await get_provider_for_tenant(database, tenant_id)
        provider_name, capabilities, readiness = provider.name, asdict(provider.capabilities), "configured_not_live_verified"
    except PaymentError:
        pass
    return {"provider": provider_name, "provider_readiness": readiness, "provider_capabilities": capabilities,
        "enterprise_currency_scale": 2, "enterprise_currencies": sorted(CENT_CURRENCIES),
        "manual_collection_methods": [{"code": code, "label": label, "execution": "external_record_only"} for code, label in
            [("cash", "Nakit"), ("card", "Harici POS / kart"), ("bank_transfer", "Doğrulanmış banka transferi"), ("check", "Çek")]],
        "non_collection_operations": ["city_ledger", "concession", "folio_transfer", "deposit_application", "authorization"],
        "not_enabled": ["gift_card_redemption", "wallet", "loyalty_redemption", "barter", "write_off"],
        "notes": ["Yapılandırma canlı tahsilat doğrulaması değildir.", "Provizyon tahsilat değildir.", "Cari aktarımı tahsilat değildir."]}


def assert_direct_bill_capacity(account, booking_currency, amount, balance):
    """Legacy zero limit means unrestricted; a configured limit is enforced.

    No guessed FX. The caller holds the canonical AR account's transaction
    lock and rereads its balance immediately before this check.
    """
    if account.get("is_active") is False or str(account.get("status") or "").lower() in {"blocked", "restricted", "inactive", "closed"}:
        raise HTTPException(409, "Seçili cari hesap kredili işleme kapalı")
    code = currency(booking_currency)
    if account.get("currency") and currency(account["currency"]) != code:
        raise HTTPException(409, "Cari hesap para birimi farklı; kur tahminiyle aktarım yapılamaz")
    limit = minor(account.get("credit_limit") or 0)
    debt = minor(balance)
    if limit < 0:
        raise HTTPException(409, "Cari kredi limiti/bakiyesi doğrulanamadı")
    if limit and not account.get("currency"):
        raise HTTPException(409, "Kredi limiti olan cari hesapta para birimi tanımlanmalı")
    if limit and debt + minor(amount) > limit:
        raise HTTPException(409, "Cari kredi limiti bu aktarım için yetersiz")
