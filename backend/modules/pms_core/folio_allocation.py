"""Atomic allocation between existing windows of one reservation.

This is neither a collection nor a discount. Item moves retain the original
tax/category/date; amount allocation uses balanced, non-revenue adjustments.
The caller MUST run the callback in the reservation financial transaction.
"""
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.pms_core.folio_selection import select_booking_folio
from modules.pms_core.receivable_reporting import folio_snapshots
from modules.pms_core.report_money import currency_code, money, rounded


class FolioAllocationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    request_id: UUID
    booking_id: str = Field(min_length=1, max_length=100)
    source_folio_id: str = Field(min_length=1, max_length=100)
    target_folio_id: str = Field(min_length=1, max_length=100)
    mode: Literal["items", "amount"]
    charge_ids: list[str] = Field(default_factory=list, max_length=200)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    expected_amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_allocation(self):
        if self.source_folio_id == self.target_folio_id:
            raise ValueError("Kaynak ve hedef farklı folyolar olmalı")
        if self.mode == "items":
            if not self.charge_ids or self.amount is not None or self.expected_amount is None or any(not cid.strip() for cid in self.charge_ids):
                raise ValueError("Kalem aktarımı için yalnız masraf kalemlerini seçin")
            if len(set(self.charge_ids)) != len(self.charge_ids):
                raise ValueError("Aynı kalem birden fazla seçilemez")
        elif self.amount is None or self.charge_ids or self.expected_amount is not None:
            raise ValueError("Tutar aktarımı için yalnız pozitif tutar girin")
        return self


def _fingerprint(body):
    payload = body.model_dump(mode="json", exclude={"request_id"})
    payload["charge_ids"] = sorted(payload["charge_ids"])
    for field in ("amount", "expected_amount"):
        if getattr(body, field) is not None:
            payload[field] = f"{getattr(body, field):.2f}"
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


async def allocate_posted_debt(database, tenant_id, actor_id, body, *, session):
    """All writes (including replay evidence) commit or roll back together."""
    if session is None:
        raise HTTPException(503, "Folyo paylaştırma için transaction desteği gerekli")
    operation_id = f"folio-allocation:{tenant_id}:{body.request_id}"
    fingerprint = _fingerprint(body)
    previous = await database.folio_operations.find_one({"_id": operation_id, "tenant_id": tenant_id}, session=session)
    if previous:
        if previous.get("fingerprint") != fingerprint:
            raise HTTPException(409, "İşlem anahtarı farklı bir paylaştırma için kullanılmış")
        return {**previous["result"], "replayed": True}

    booking = await database.bookings.find_one({"id": body.booking_id, "tenant_id": tenant_id}, {"_id": 0}, session=session)
    if not booking:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    source = await select_booking_folio(database, tenant_id, body.booking_id, body.source_folio_id, session=session)
    target = await select_booking_folio(database, tenant_id, body.booking_id, body.target_folio_id, session=session)
    if not booking.get("currency") and (not source.get("currency") or not target.get("currency")):
        raise HTTPException(409, "Folyo para birimi doğrulanamadı")
    currency = currency_code(source.get("currency") or booking.get("currency"))
    if currency != currency_code(target.get("currency") or booking.get("currency")):
        raise HTTPException(409, "Farklı para birimlerindeki folyolar arasında paylaştırma yapılamaz")
    if source.get("invoice_id") or target.get("invoice_id"):
        raise HTTPException(409, "Faturaya bağlı folyolar önce fatura düzeltme akışında uzlaştırılmalı")
    # Include booking-level and folio-level invoices; even drafts need explicit
    # invalidation/recreation before changing their debt/payer basis.
    invoice = await database.invoices.find_one({"tenant_id": tenant_id, "voided": {"$ne": True},
        "status": {"$nin": ["cancelled", "canceled", "void", "voided"]},
        "$or": [{"booking_id": body.booking_id}, {"folio_id": {"$in": [source["id"], target["id"]]}},
                {"folio_ids": {"$in": [source["id"], target["id"]]}}]}, session=session)
    if invoice:
        raise HTTPException(409, "Rezervasyona/folyoya bağlı fatura var; önce fatura düzeltme akışını tamamlayın")
    settings = await database.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0, "business_date": 1}, session=session)
    try:
        business_date = date.fromisoformat(str((settings or {}).get("business_date"))[:10]).isoformat()
    except ValueError:
        raise HTTPException(409, "Açık PMS iş günü doğrulanamadı; önce iş gününü kontrol edin") from None

    snapshots = await folio_snapshots(database, tenant_id, [source, target], fallback_currency=currency, session=session)
    for snap in snapshots.values():
        if any(code != currency and value for code, value in snap["balance_by_currency"].items()):
            raise HTTPException(409, "Çok para birimli folyo önce mutabık hale getirilmeli")
    before = {fid: money(snap["balance_by_currency"].get(currency, 0)) for fid, snap in snapshots.items()}
    rows = snapshots[source["id"]]["charges"]
    selected = [row for row in rows if row["id"] in body.charge_ids] if body.mode == "items" else []
    if body.mode == "items" and {row["id"] for row in selected} != set(body.charge_ids):
        raise HTTPException(409, "Seçilen kalemler kaynak folyoda yok veya iptal edilmiş; yenileyin")
    if any(row.get("invoice_id") or row.get("charge_category") == "split_adjustment" or
           money(row["total"]) <= 0 or money(row["total"]) != money(rounded(row["total"])) or
           currency_code(row.get("currency"), currency) != currency for row in selected):
        raise HTTPException(409, "Yalnız aynı para birimindeki pozitif, faturasız asıl masraflar taşınabilir")
    amount = money(rounded(sum((money(row["total"]) for row in selected), Decimal(0)))) if selected else body.amount
    if selected and amount != body.expected_amount:
        raise HTTPException(409, "Seçilen kalemlerin tutarı değişti; yenileyip önizlemeyi tekrar onaylayın")
    if amount is None or amount <= 0 or amount > before[source["id"]]:
        raise HTTPException(409, "Aktarım tutarı kaynak folyonun açık tahakkuk borcunu aşamaz")
    now = datetime.now(UTC).isoformat()
    if body.mode == "items":
        for row in selected:
            moved = await database.folio_charges.update_one({"tenant_id": tenant_id, "id": row["id"],
                "folio_id": source["id"], "voided": {"$ne": True}}, {"$set": {"folio_id": target["id"]}}, session=session)
            if moved.modified_count != 1:
                raise HTTPException(409, "Masraf değişti; aktarım iptal edildi. Yenileyin")
    else:
        # Never move payments or repost taxable revenue to allocate a debt.
        for folio, sign in [(source, -1), (target, 1)]:
            value = float(amount * sign)
            await database.folio_charges.insert_one({"id": f"{body.request_id}:{sign}", "tenant_id": tenant_id,
                "booking_id": body.booking_id, "folio_id": folio["id"], "currency": currency,
                "charge_category": "split_adjustment", "description": f"Folyo paylaştırma: {body.reason}",
                "amount": value, "total": value, "unit_price": value, "quantity": 1,
                "tax_amount": 0, "tax_rate": 0, "department": "folio_ops", "voided": False,
                "allocation_id": str(body.request_id), "posted_by": actor_id, "date": now, "business_date": business_date}, session=session)
    after = {source["id"]: before[source["id"]] - amount, target["id"]: before[target["id"]] + amount}
    for folio in [source, target]:
        updated = await database.folios.update_one({"tenant_id": tenant_id, "id": folio["id"], "status": "open"},
            {"$set": {"balance": rounded(after[folio["id"]])}}, session=session)
        if updated.matched_count != 1:
            raise HTTPException(409, "Folyo durumu değişti; aktarım iptal edildi")
    result = {"success": True, "allocation_id": str(body.request_id), "currency": currency,
        "transferred_amount": float(amount), "source_folio_id": source["id"], "target_folio_id": target["id"],
        "source_balance": rounded(after[source["id"]]), "target_balance": rounded(after[target["id"]]), "replayed": False}
    await database.folio_operations.insert_one({"_id": operation_id, "id": str(body.request_id), "tenant_id": tenant_id,
        "booking_id": body.booking_id, "operation_type": "transfer", "from_folio_id": source["id"], "to_folio_id": target["id"],
        "charge_ids": body.charge_ids, "amount": float(amount), "currency": currency, "reason": body.reason,
        "performed_by": actor_id, "performed_at": now, "business_date": business_date, "fingerprint": fingerprint, "result": result}, session=session)
    await database.pms_audit_trail.insert_one({"id": str(body.request_id), "tenant_id": tenant_id, "entity_type": "folio",
        "entity_id": source["id"], "action": "folio_allocation", "performed_by": actor_id, "timestamp": now,
        "metadata": {"folio_id": target["id"], "source_folio_id": source["id"], "reason": body.reason, "amount": float(amount), "currency": currency,
                    "before": {key: rounded(value) for key, value in before.items()},
                    "after": {key: rounded(value) for key, value in after.items()}}}, session=session)
    return result
