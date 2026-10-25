"""Durable identity and transaction-bound evidence for legacy prepayments.

These deposits settle the reservation folio; they are not refundable security
liabilities. No gateway operation or historical payment is manufactured.
"""
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException

from core.audit_chain import append_audit_log
from modules.pms_core.enterprise_billing import fingerprint
from shared_kernel.audit_helper import build_audit_entry


async def refresh_reports(tenant_id):
    from core.report_cache import cache, invalidate_financial_report_caches, invalidate_receivable_report_caches
    from domains.pms.night_audit.router import invalidate_finance_cache

    invalidate_financial_report_caches(tenant_id)
    invalidate_receivable_report_caches(tenant_id)
    invalidate_finance_cache(tenant_id)
    if cache is not None:
        for prefix in ("report_daily_summary_v2", "flash_report_v2", "report_daily_flash_v3"):
            cache.invalidate_tenant_cache(tenant_id, prefix, include_role_variants=True)


def intent(data, tenant_id, booking_id, action):
    if data.request_id is None:
        raise HTTPException(422, "Depozito için kalıcı işlem anahtarı gerekli; ekranı yenileyin")
    try:
        request_id = str(UUID(str(data.request_id)))
    except ValueError:
        raise HTTPException(422, "Geçersiz depozito işlem anahtarı") from None
    amount = Decimal(str(data.amount if action == "receive" else data.refund_amount))
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.01")):
        raise HTTPException(422, "Depozito tutarı pozitif ve en fazla iki ondalık olmalı")
    method = data.method if action == "receive" else data.refund_method
    if method not in {"cash", "card", "bank_transfer"}:
        raise HTTPException(422, "Depozito yalnız nakit, harici kart veya banka transferi olarak kaydedilebilir")
    key = str(uuid5(NAMESPACE_URL, f"deposit:{tenant_id}:{request_id}"))
    return key, fingerprint({"booking_id": booking_id, "action": action, **data.model_dump(mode="json")})


def remaining(deposit):
    """An invalid legacy source is not a zero/refundable money balance."""
    try:
        amount = Decimal(str(deposit.get("amount")))
        refunded = Decimal(str(deposit.get("refunded_amount", 0) or 0))
        if not amount.is_finite() or not refunded.is_finite() or amount <= 0 or not 0 <= refunded <= amount:
            raise ValueError
        if any(value != value.quantize(Decimal("0.01")) for value in (amount, refunded)):
            raise ValueError
        return float(amount), float(refunded), float(amount - refunded)
    except (ValueError, ArithmeticError):
        raise HTTPException(409, "Eski depozito tutarı/iade toplamı doğrulanamadı; kaynak kaydı incelenmeli") from None


async def replay(database, tenant_id, key, digest, *, session=None):
    prior = await database.deposit_operations.find_one({"_id": key, "tenant_id": tenant_id}, session=session)
    if not prior:
        return None
    if prior["fingerprint"] != digest:
        raise HTTPException(409, "İşlem anahtarı farklı depozito içeriğiyle kullanılmış")
    return {**prior["result"], "replayed": True}


async def remember(database, user, key, digest, booking_id, action, result, *, session):
    if session is None:
        raise HTTPException(503, "Depozito için transaction desteği gerekli")
    payment = result["payment"]
    entry = build_audit_entry(actor_id=user.id, tenant_id=user.tenant_id, property_id=user.tenant_id,
        entity_type="reservation", entity_id=booking_id, action=f"deposit_{action}",
        metadata={"actor_name": user.name, "request_id": key, "deposit_id": payment["deposit_id"]})
    entry["after_snapshot"] = {"request_id": key, "deposit_id": payment["deposit_id"], "payment_id": payment["id"],
        "folio_id": payment["folio_id"], "amount": payment["amount"], "currency": payment["currency"],
        "method": payment["method"], "business_date": payment.get("business_date"),
        "reference": payment.get("reference"), "reason": payment.get("notes"), "actor_name": user.name}
    await append_audit_log(database, entry, session=session, require_chain=True)
    await database.deposit_operations.insert_one({"_id": key, "tenant_id": user.tenant_id,
        "booking_id": booking_id, "fingerprint": digest, "result": result}, session=session)
