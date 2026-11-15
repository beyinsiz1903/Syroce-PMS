"""Merge open windows of one booking without copying financial transactions.

The caller holds both folio locks and the booking lock in a Mongo transaction.
Original charge/payment IDs, business dates, taxes and references are preserved.
"""
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.pms_core.folio_selection import select_booking_folio
from modules.pms_core.receivable_reporting import folio_snapshots
from modules.pms_core.report_money import currency_code, money, rounded


class FolioMergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    booking_id: str = Field(min_length=1, max_length=100)
    source_folio_id: str = Field(min_length=1, max_length=100)
    target_folio_id: str = Field(min_length=1, max_length=100)
    expected_source_balance: Decimal = Field(max_digits=14, decimal_places=2, allow_inf_nan=False)
    expected_target_balance: Decimal = Field(max_digits=14, decimal_places=2, allow_inf_nan=False)
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def distinct_folios(self):
        if self.source_folio_id == self.target_folio_id:
            raise ValueError("Kaynak ve hedef farklı folyolar olmalı")
        return self


async def merge_folio_windows(database, tenant_id, actor_id, body, *, session):
    if session is None:
        raise HTTPException(503, "Folyo birleştirme için transaction desteği gerekli")
    operation_id = f"folio-merge:{tenant_id}:{body.request_id}"
    fingerprint = hashlib.sha256(json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    previous = await database.folio_operations.find_one({"_id": operation_id, "tenant_id": tenant_id}, session=session)
    if previous:
        if previous.get("fingerprint") != fingerprint:
            raise HTTPException(409, "İşlem anahtarı farklı bir birleştirme için kullanılmış")
        return {**previous["result"], "replayed": True}
    booking = await database.bookings.find_one({"tenant_id": tenant_id, "id": body.booking_id}, session=session)
    if not booking:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    if booking.get("status") in {"cancelled", "canceled", "no_show", "checked_out"}:
        raise HTTPException(409, "Tamamlanmış rezervasyonun folyoları birleştirilemez")
    source = await select_booking_folio(database, tenant_id, body.booking_id, body.source_folio_id, session=session)
    target = await select_booking_folio(database, tenant_id, body.booking_id, body.target_folio_id, session=session)
    if not (source.get("currency") or booking.get("currency")) or not (target.get("currency") or booking.get("currency")):
        raise HTTPException(409, "Folyo para birimi doğrulanamadı")
    code = currency_code(source.get("currency") or booking.get("currency"))
    if code != currency_code(target.get("currency") or booking.get("currency")):
        raise HTTPException(409, "Folyo para birimleri aynı olmalı")
    ids = [source["id"], target["id"]]
    invoice = await database.invoices.find_one({"tenant_id": tenant_id, "voided": {"$ne": True},
        "status": {"$nin": ["cancelled", "canceled", "void", "voided"]},
        "$or": [{"booking_id": body.booking_id}, {"folio_id": {"$in": ids}}, {"folio_ids": {"$in": ids}}]}, session=session)
    if invoice or source.get("invoice_id") or target.get("invoice_id"):
        raise HTTPException(409, "Faturaya bağlı hesapları birleştirmeden önce faturayı uzlaştırın")
    settings = await database.tenant_settings.find_one({"tenant_id": tenant_id}, session=session)
    try:
        business_date = date.fromisoformat(str((settings or {}).get("business_date"))[:10]).isoformat()
    except ValueError:
        raise HTTPException(409, "Açık iş günü doğrulanamadı") from None
    if await database.billing_concessions.find_one({"tenant_id": tenant_id, "folio_id": {"$in": ids}, "status": "requested"}, session=session):
        raise HTTPException(409, "Bekleyen ikram/indirim işlemini önce sonuçlandırın")
    # Sealed settlement journals contain the original folio ID. Moving their
    # payment would invalidate reconciliation and the instrument's reversal
    # path. Keep this window open; the operator can merge INTO it instead.
    source_payments = await database.payments.find(
        {"tenant_id": tenant_id, "folio_id": source["id"]}, session=session).to_list(None)
    if any(row.get("billing_settlement_id") or row.get("gl_journal_entry_id") for row in source_payments):
        raise HTTPException(409, "Kaynak hesapta muhasebeye bağlı mahsup var. Bu hesabı hedef seçerek diğer hesabı buna birleştirin.")
    before = await folio_snapshots(database, tenant_id, [source, target], fallback_currency=code, session=session, include_booking_extras=True)
    for snapshot in before.values():
        # Check gross movements, not only net balance: other-currency debits
        # and credits can cancel out without making a window single-currency.
        if any(row["currency"] != code for key in ("charges", "payments") for row in snapshot[key]):
            raise HTTPException(409, "Çok para birimli hesapları önce uzlaştırın")
        if any(c != code and amount for key in ("charges_by_currency", "payments_by_currency", "opening_by_currency")
               for c, amount in snapshot[key].items()):
            raise HTTPException(409, "Çok para birimli hesapları önce uzlaştırın")
    balances = {fid: money(snap["balance_by_currency"].get(code, 0)) for fid, snap in before.items()}
    if balances[source["id"]] != body.expected_source_balance or balances[target["id"]] != body.expected_target_balance:
        raise HTTPException(409, "Hesap bakiyesi değişti. Kartı yenileyip birleştirmeyi tekrar kontrol edin")
    now = datetime.now(UTC).isoformat()
    # Move rows rather than duplicating them. Voided and refund rows travel
    # with their originals so their history remains available in one window.
    counts = {}
    for name in ("folio_charges", "payments", "extra_charges", "folio_postings", "deposits"):
        moved = await database[name].update_many({"tenant_id": tenant_id, "folio_id": source["id"]},
            {"$set": {"folio_id": target["id"]}}, session=session)
        counts[name] = moved.modified_count
    # A rule referencing the now closed window must not keep targeting it.
    await database.folio_routing.update_many({"tenant_id": tenant_id, "active": True,
        "$or": [{"source_folio_id": source["id"]}, {"dest_folio_id": source["id"]}]},
        {"$set": {"active": False, "disabled_by_merge": str(body.request_id), "deleted_at": now}}, session=session)
    opening = money(source.get("opening_balance") or 0) + money(target.get("opening_balance") or 0)
    for folio, patch in [(source, {"status": "closed", "closed_at": now, "merged_into_folio_id": target["id"], "opening_balance": 0, "balance": 0}),
                         (target, {"opening_balance": rounded(opening), "balance": rounded(sum(balances.values()))})]:
        updated = await database.folios.update_one({"tenant_id": tenant_id, "id": folio["id"], "status": "open"}, {"$set": patch}, session=session)
        if updated.matched_count != 1:
            raise HTTPException(409, "Folyo durumu değişti; birleştirme iptal edildi")
        folio.update(patch)
    after = await folio_snapshots(database, tenant_id, [source, target], fallback_currency=code, session=session, include_booking_extras=True)
    if money(after[source["id"]]["balance_by_currency"].get(code, 0)) != 0 or money(after[target["id"]]["balance_by_currency"].get(code, 0)) != sum(balances.values()):
        raise HTTPException(409, "Birleştirme toplamları uzlaşmadı; işlem geri alındı")
    result = {"success": True, "source_folio_id": source["id"], "target_folio_id": target["id"],
              "target_balance": rounded(sum(balances.values())), "currency": code, "moved": counts, "replayed": False}
    await database.folio_operations.insert_one({"_id": operation_id, "id": str(body.request_id), "tenant_id": tenant_id,
        "booking_id": body.booking_id, "operation_type": "merge", "from_folio_id": source["id"], "to_folio_id": target["id"],
        "amount": rounded(balances[source["id"]]), "currency": code, "reason": body.reason, "performed_by": actor_id,
        "performed_at": now, "business_date": business_date, "fingerprint": fingerprint, "result": result}, session=session)
    await database.pms_audit_trail.insert_one({"id": str(body.request_id), "tenant_id": tenant_id, "entity_type": "folio",
        "entity_id": source["id"], "action": "folio_merge", "performed_by": actor_id, "timestamp": now,
        "metadata": {"target_folio_id": target["id"], "reason": body.reason, "currency": code,
                     "before": {fid: rounded(value) for fid, value in balances.items()}, "result": result}}, session=session)
    return result
