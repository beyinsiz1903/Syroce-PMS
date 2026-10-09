"""Operational PMS/POS sources to the durable General Ledger.

Mappings are tenant-owned and disabled until explicitly enabled. Night audit
posts daily folio charges and collections; direct POS payments post at order
close. Room-charge POS orders are skipped because they are already represented
by the folio/night-audit path.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from shared_kernel.gl_posting import GLPostingError, post_journal_entry


class OperationalGLBridgeError(ValueError):
    pass


DEFAULT_MAPPING = {
    "enabled": False,
    "auto_night_audit": True,
    "auto_pos": True,
    "receivable_account_code": "120",
    "revenue_account_code": "600",
    "tax_account_code": "391",
    "cash_account_code": "100",
    "card_account_code": "108",
    "bank_account_code": "102",
}


def _minor(value: object) -> int:
    return int((Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100).to_integral_exact())


def _amount(value: int) -> float:
    return float(Decimal(value) / 100)


async def get_operational_mapping(db, tenant_id: str) -> dict:
    stored = await db.gl_operational_mappings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    return {**DEFAULT_MAPPING, **(stored or {}), "tenant_id": tenant_id}


def _payment_account(mapping: dict, method: str) -> str:
    normalized = (method or "").lower()
    if normalized in {"cash", "nakit"}:
        return mapping["cash_account_code"]
    if normalized in {"card", "credit_card", "debit_card", "kredi_karti", "pos"}:
        return mapping["card_account_code"]
    return mapping["bank_account_code"]


async def post_night_audit_daily_to_gl(
    db,
    tenant_id: str,
    business_date: str,
    *,
    run_id: str,
    actor: str = "night_audit",
) -> dict:
    mapping = await get_operational_mapping(db, tenant_id)
    if not mapping["enabled"] or not mapping["auto_night_audit"]:
        await db.night_audit_runs.update_one(
            {"tenant_id": tenant_id, "id": run_id},
            {"$set": {"gl_bridge_status": "not_configured"}},
        )
        return {"status": "skipped", "reason": "not_configured"}

    next_day = (date.fromisoformat(business_date) + timedelta(days=1)).isoformat()
    charges = await db.folio_charges.find(
        {
            "tenant_id": tenant_id,
            "voided": {"$ne": True},
            "$or": [
                {"run_id": run_id},
                {"business_date": business_date},
                {"date": {"$gte": business_date, "$lt": next_day}},
            ],
        },
        {"_id": 0},
    ).to_list(100000)
    payments = await db.payments.find(
        {
            "tenant_id": tenant_id,
            "voided": {"$ne": True},
            "$or": [
                {"payment_date": {"$gte": business_date, "$lt": next_day}},
                {"processed_at": {"$gte": business_date, "$lt": next_day}},
                {"date": {"$gte": business_date, "$lt": next_day}},
            ],
        },
        {"_id": 0},
    ).to_list(100000)

    charge_total = sum((_minor(row.get("total", row.get("amount"))) for row in charges), 0)
    tax_total = sum((_minor(row.get("tax_amount")) for row in charges), 0)
    if tax_total < 0 or tax_total > charge_total:
        raise OperationalGLBridgeError("Night-audit tax total is outside the charge total")
    lines: list[dict] = []
    if charge_total:
        lines.append({"account_code": mapping["receivable_account_code"], "debit": _amount(charge_total), "memo": "Günlük folio tahakkukları"})
        net_revenue = charge_total - tax_total
        if net_revenue:
            lines.append({"account_code": mapping["revenue_account_code"], "credit": _amount(net_revenue), "memo": "Günlük oda/PMS geliri"})
        if tax_total:
            lines.append({"account_code": mapping["tax_account_code"], "credit": _amount(tax_total), "memo": "Günlük hesaplanan vergi"})

    payment_totals: dict[str, int] = {}
    for payment in payments:
        account_code = _payment_account(mapping, str(payment.get("method") or payment.get("payment_method") or "bank"))
        payment_totals[account_code] = payment_totals.get(account_code, 0) + _minor(payment.get("amount"))
    payment_total = sum(payment_totals.values())
    for account_code, amount_minor in sorted(payment_totals.items()):
        if amount_minor:
            lines.append({"account_code": account_code, "debit": _amount(amount_minor), "memo": "Günlük tahsilatlar"})
    if payment_total:
        lines.append({"account_code": mapping["receivable_account_code"], "credit": _amount(payment_total), "memo": "Günlük folio tahsilat kapaması"})
    if not lines:
        await db.night_audit_runs.update_one(
            {"tenant_id": tenant_id, "id": run_id},
            {"$set": {"gl_bridge_status": "no_activity"}},
        )
        return {"status": "skipped", "reason": "no_activity"}

    try:
        entry = await post_journal_entry(
            db,
            tenant_id,
            date=business_date,
            memo=f"{business_date} PMS/POS günlük muhasebe aktarımı",
            lines=lines,
            source="night_audit",
            source_ref=run_id,
            actor=actor,
            idempotency_key=f"operational-daily:{business_date}",
        )
    except GLPostingError as exc:
        raise OperationalGLBridgeError(str(exc)) from exc
    await db.night_audit_runs.update_one(
        {"tenant_id": tenant_id, "id": run_id},
        {"$set": {"gl_bridge_status": "posted", "gl_journal_entry_id": entry["id"], "gl_entry_no": entry.get("entry_no")}},
    )
    return {"status": "posted", "entry": entry, "charge_total": _amount(charge_total), "payment_total": _amount(payment_total)}


async def post_direct_pos_to_gl(
    db,
    tenant_id: str,
    *,
    transaction: dict,
    order: dict,
    posted_to_folio: bool,
    actor: str,
) -> dict:
    mapping = await get_operational_mapping(db, tenant_id)
    if posted_to_folio:
        if transaction.get("id") and hasattr(db, "pos_transactions"):
            await db.pos_transactions.update_one(
                {"tenant_id": tenant_id, "id": transaction["id"]},
                {"$set": {"gl_bridge_status": "folio_path"}},
            )
        return {"status": "skipped", "reason": "folio_path"}
    if not mapping["enabled"] or not mapping["auto_pos"]:
        await db.pos_transactions.update_one(
            {"tenant_id": tenant_id, "id": transaction["id"]},
            {"$set": {"gl_bridge_status": "not_configured"}},
        )
        return {"status": "skipped", "reason": "not_configured"}
    total = _minor(transaction.get("total_amount"))
    tax = _minor(transaction.get("tax_amount", order.get("tax_amount")))
    # A fully complimentary order is a valid terminal POS transaction, but it
    # has no financial value to post.  Treat it as a successful no-op instead
    # of marking the already completed sale as a GL bridge failure.  The POS
    # transaction remains the auditable operational record of the comp.
    if total == 0 and tax == 0:
        await db.pos_transactions.update_one(
            {"tenant_id": tenant_id, "id": transaction["id"]},
            {"$set": {"gl_bridge_status": "no_activity"}},
        )
        return {"status": "skipped", "reason": "no_activity"}
    if total <= 0 or tax < 0 or tax > total:
        raise OperationalGLBridgeError("POS total/tax values are not postable")
    breakdown = transaction.get("payment_breakdown") or []
    if breakdown:
        settlement_lines = [
            {
                "account_code": _payment_account(mapping, str(part.get("method") or "cash")),
                "debit": float(part.get("amount") or 0),
                "memo": f"POS {str(part.get('method') or 'tahsilat').lower()} tahsilatı",
            }
            for part in breakdown
            if float(part.get("amount") or 0) > 0
        ]
        breakdown_total = sum(_minor(line["debit"]) for line in settlement_lines)
        if breakdown_total != total:
            raise OperationalGLBridgeError("POS payment breakdown does not match transaction total")
    else:
        settlement_lines = [{
            "account_code": _payment_account(mapping, str(transaction.get("payment_method") or "cash")),
            "debit": _amount(total),
            "memo": "POS tahsilatı",
        }]
    lines = [
        *settlement_lines,
        {"account_code": mapping["revenue_account_code"], "credit": _amount(total - tax), "memo": "POS geliri"},
    ]
    if tax:
        lines.append({"account_code": mapping["tax_account_code"], "credit": _amount(tax), "memo": "POS hesaplanan vergi"})
    try:
        entry = await post_journal_entry(
            db,
            tenant_id,
            date=transaction["transaction_date"],
            memo=f"POS sipariş {transaction.get('order_number') or transaction['order_id']}",
            lines=lines,
            source="pos_direct",
            source_ref=transaction["order_id"],
            actor=actor,
            idempotency_key=f"pos-direct:{transaction['order_id']}",
        )
    except GLPostingError as exc:
        raise OperationalGLBridgeError(str(exc)) from exc
    await db.pos_transactions.update_one(
        {"tenant_id": tenant_id, "id": transaction["id"]},
        {"$set": {"gl_bridge_status": "posted", "gl_journal_entry_id": entry["id"], "gl_entry_no": entry.get("entry_no")}},
    )
    return {"status": "posted", "entry": entry}


async def post_direct_pos_refund_to_gl(
    db,
    tenant_id: str,
    *,
    refund: dict,
    original_transaction: dict,
    order: dict,
    actor: str,
) -> dict:
    """Reverse the proportional settlement, revenue and tax for a POS refund."""
    mapping = await get_operational_mapping(db, tenant_id)
    if not mapping["enabled"] or not mapping["auto_pos"]:
        await db.pos_transactions.update_one(
            {"tenant_id": tenant_id, "id": refund["id"]},
            {"$set": {"gl_bridge_status": "not_configured"}},
        )
        return {"status": "skipped", "reason": "not_configured"}
    paid = _minor(original_transaction.get("total_amount"))
    refunded = abs(_minor(refund.get("total_amount")))
    if paid <= 0 or refunded <= 0 or refunded > paid:
        raise OperationalGLBridgeError("POS refund values are not postable")
    original_tax = _minor(order.get("tax_amount"))
    refund_tax = int((Decimal(original_tax) * Decimal(refunded) / Decimal(paid)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    breakdown = original_transaction.get("payment_breakdown") or []
    settlement_lines = []
    allocated = 0
    if breakdown:
        for index, part in enumerate(breakdown):
            if index == len(breakdown) - 1:
                part_refund = refunded - allocated
            else:
                part_paid = _minor(part.get("amount"))
                part_refund = int((Decimal(refunded) * Decimal(part_paid) / Decimal(paid)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                allocated += part_refund
            if part_refund > 0:
                settlement_lines.append({
                    "account_code": _payment_account(mapping, str(part.get("method") or "cash")),
                    "credit": _amount(part_refund),
                    "memo": "POS iade tahsilat ters kaydı",
                })
    else:
        settlement_lines.append({
            "account_code": _payment_account(mapping, str(original_transaction.get("payment_method") or "cash")),
            "credit": _amount(refunded),
            "memo": "POS iade tahsilat ters kaydı",
        })
    lines = [
        {"account_code": mapping["revenue_account_code"], "debit": _amount(refunded - refund_tax), "memo": "POS satış iadesi"},
    ]
    if refund_tax:
        lines.append({"account_code": mapping["tax_account_code"], "debit": _amount(refund_tax), "memo": "POS iade vergi ters kaydı"})
    lines.extend(settlement_lines)
    try:
        entry = await post_journal_entry(
            db, tenant_id, date=refund["transaction_date"], memo=f"POS iade {refund['order_id']}",
            lines=lines, source="pos_refund", source_ref=refund["id"], actor=actor,
            idempotency_key=f"pos-refund:{refund['id']}",
        )
    except GLPostingError as exc:
        raise OperationalGLBridgeError(str(exc)) from exc
    await db.pos_transactions.update_one(
        {"tenant_id": tenant_id, "id": refund["id"]},
        {"$set": {"gl_bridge_status": "posted", "gl_journal_entry_id": entry["id"], "gl_entry_no": entry.get("entry_no")}},
    )
    return {"status": "posted", "entry": entry}
