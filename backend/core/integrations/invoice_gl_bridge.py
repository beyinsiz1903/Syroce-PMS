"""Nilvera incoming invoice ↔ General Ledger bridge.

The bridge deliberately avoids hard-coded Turkish account codes. The caller
provides the tenant's purchase/expense, input VAT and vendor payable accounts
when posting the source purchase invoice. A later successful CreateReturn then
reverses that exact posted journal entry byte-for-byte (debit/credit swapped),
so the return follows the tenant's own chart of accounts.

Safety invariants:
- source posting is idempotent per incoming invoice,
- return posting is idempotent per lifecycle action,
- only simple TRY purchase invoices are auto-postable here (no deductions or
  other taxes); unsupported tax shapes fail closed rather than guessing,
- return reversal never guesses accounts or amounts; it mirrors the source
  journal exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from core.integrations.incoming_invoice_repository import IncomingInvoiceRepository
from core.tenant_db import get_db_for_tenant
from shared_kernel.gl_posting import GLPostingError, post_journal_entry


class InvoiceGLBridgeError(ValueError):
    """Fail-closed accounting bridge validation error."""


@dataclass(frozen=True)
class InvoiceGLLink:
    source_entry: dict | None
    return_entries: tuple[dict, ...]


_ALLOWED_TRY_CODES = {"TRY", "TRL"}
_ROUNDING_TOLERANCE = Decimal("0.02")


def _money(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _clean_account(code: str, label: str) -> str:
    normalized = (code or "").strip()
    if not normalized:
        raise InvoiceGLBridgeError(f"{label} account code is required")
    if len(normalized) > 40:
        raise InvoiceGLBridgeError(f"{label} account code is too long")
    return normalized


async def post_incoming_invoice_to_gl(
    tenant_id: str,
    incoming_invoice_id: str,
    *,
    purchase_account_code: str,
    vat_account_code: str,
    payable_account_code: str,
    other_tax_account_code: str | None = None,
    deduction_account_code: str | None = None,
    other_tax_accounts_by_code: dict[str, str] | None = None,
    deduction_accounts_by_code: dict[str, str] | None = None,
    actor: str,
) -> dict:
    """Post a simple Nilvera purchase invoice to GL using explicit accounts.

    The posting is intentionally conservative. Complex tax/deduction invoices
    are rejected until a richer tax-to-account mapping is configured.
    """
    invoice = await IncomingInvoiceRepository.get_by_id(tenant_id, incoming_invoice_id)
    if invoice is None:
        raise InvoiceGLBridgeError("Incoming invoice not found")

    currency = (invoice.currency or "").strip().upper()
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise InvoiceGLBridgeError("Incoming invoice currency is invalid")
    exchange_rate: Decimal | None = None
    if currency not in _ALLOWED_TRY_CODES:
        raw_rate = getattr(invoice, "exchange_rate", None)
        if raw_rate is None:
            raise InvoiceGLBridgeError("Foreign-currency incoming invoice requires a TRY exchange rate")
        exchange_rate = Decimal(str(raw_rate))
        if not exchange_rate.is_finite() or exchange_rate <= 0:
            raise InvoiceGLBridgeError("Incoming invoice exchange rate must be positive")

    payable = _money(invoice.payable_amount)
    if payable <= 0:
        raise InvoiceGLBridgeError("Incoming invoice payable amount must be positive")

    lines = await IncomingInvoiceRepository.list_lines(tenant_id, incoming_invoice_id)
    active_lines = [line for line in lines if getattr(line, "active", True)]
    if not active_lines:
        raise InvoiceGLBridgeError("Incoming invoice has no active lines")

    base_total = sum((_money(line.line_extension_amount) for line in active_lines), Decimal("0"))
    vat_total = sum((_money(line.kdv_amount) for line in active_lines), Decimal("0"))
    other_taxes: dict[str, Decimal] = {}
    deductions: dict[str, Decimal] = {}
    for line in active_lines:
        for tax in getattr(line, "other_taxes", None) or []:
            if isinstance(tax, dict):
                code = str(tax.get("tax_code") or "").strip()
                amount = _money(tax.get("amount"))
                is_deduction = bool(tax.get("is_deduction"))
            else:
                code = str(getattr(tax, "tax_code", "") or "").strip()
                amount = _money(getattr(tax, "amount", None))
                is_deduction = bool(getattr(tax, "is_deduction", False))
            if not code or amount <= 0:
                raise InvoiceGLBridgeError("Incoming invoice contains unsupported other taxes or deductions")
            target = deductions if is_deduction else other_taxes
            target[code] = target.get(code, Decimal("0")) + amount

    other_tax_total = sum(other_taxes.values(), Decimal("0"))
    deduction_total = sum(deductions.values(), Decimal("0"))
    calculated_total = (base_total + vat_total + other_tax_total - deduction_total).quantize(Decimal("0.01"))
    if abs(calculated_total - payable) > _ROUNDING_TOLERANCE:
        raise InvoiceGLBridgeError("Incoming invoice totals do not reconcile to payable amount; accounting mapping is required")

    purchase_account = _clean_account(purchase_account_code, "Purchase")
    vat_account = _clean_account(vat_account_code, "VAT")
    payable_account = _clean_account(payable_account_code, "Payable")

    journal_lines: list[dict] = [
        {
            "account_code": purchase_account,
            "debit": float(base_total),
            "credit": 0,
            "memo": "Nilvera alış faturası matrahı",
        }
    ]
    if vat_total > 0:
        journal_lines.append(
            {
                "account_code": vat_account,
                "debit": float(vat_total),
                "credit": 0,
                "memo": "Nilvera indirilecek KDV",
            }
        )
    other_tax_map = other_tax_accounts_by_code or {}
    for code, amount in sorted(other_taxes.items()):
        account = other_tax_map.get(code) or other_tax_account_code
        if not account:
            raise InvoiceGLBridgeError(f"No incoming other-tax account provided for code {code}")
        journal_lines.append(
            {
                "account_code": _clean_account(account, f"Other tax {code}"),
                "debit": float(amount),
                "credit": 0,
                "memo": f"Nilvera alış faturası vergi {code}",
            }
        )
    deduction_map = deduction_accounts_by_code or {}
    for code, amount in sorted(deductions.items()):
        account = deduction_map.get(code) or deduction_account_code
        if not account:
            raise InvoiceGLBridgeError(f"No incoming deduction account provided for code {code}")
        journal_lines.append(
            {
                "account_code": _clean_account(account, f"Deduction {code}"),
                "debit": 0,
                "credit": float(amount),
                "memo": f"Nilvera alış faturası kesinti/tevkifat {code}",
            }
        )
    journal_lines.append(
        {
            "account_code": payable_account,
            "debit": 0,
            "credit": float(payable),
            "memo": "Nilvera satıcı borcu",
        }
    )

    if exchange_rate is not None:
        # GL is kept in TRY while preserving the provider currency snapshot on
        # every line.  The payable line absorbs at most one kuruş of component
        # rounding; larger drift fails closed instead of inventing an FX gain.
        for line in journal_lines:
            foreign_debit = _money(line.get("debit"))
            foreign_credit = _money(line.get("credit"))
            foreign_amount = foreign_debit or foreign_credit
            base_amount = (foreign_amount * exchange_rate).quantize(Decimal("0.01"))
            line["debit"] = float(base_amount) if foreign_debit > 0 else 0
            line["credit"] = float(base_amount) if foreign_credit > 0 else 0
            line["currency"] = currency
            line["foreign_amount"] = float(foreign_amount)
            line["exchange_rate"] = str(exchange_rate)

        total_debit_base = sum((_money(line["debit"]) for line in journal_lines), Decimal("0"))
        total_credit_base = sum((_money(line["credit"]) for line in journal_lines), Decimal("0"))
        rounding_delta = total_debit_base - total_credit_base
        payable_line = journal_lines[-1]
        adjusted_payable = _money(payable_line["credit"]) + rounding_delta
        expected_payable = (payable * exchange_rate).quantize(Decimal("0.01"))
        if adjusted_payable <= 0 or abs(adjusted_payable - expected_payable) > Decimal("0.01"):
            raise InvoiceGLBridgeError("Foreign-currency invoice has an unsupported TRY rounding difference")
        payable_line["credit"] = float(adjusted_payable)

    db = get_db_for_tenant(tenant_id)
    try:
        entry = await post_journal_entry(
            db,
            tenant_id,
            date=invoice.issue_date.date().isoformat(),
            memo=f"Nilvera alış faturası {invoice.invoice_number}",
            lines=journal_lines,
            source="nilvera_incoming",
            source_ref=incoming_invoice_id,
            actor=actor,
            idempotency_key=f"nilvera-incoming:{incoming_invoice_id}",
        )
    except GLPostingError as exc:
        raise InvoiceGLBridgeError(str(exc)) from exc

    await db.gl_journal_entries.update_one(
        {"tenant_id": tenant_id, "id": entry["id"]},
        {
            "$set": {
                "nilvera_source_invoice_id": incoming_invoice_id,
                "nilvera_source_provider_uuid": invoice.provider_uuid,
                "nilvera_invoice_number": invoice.invoice_number,
                "integration_kind": "nilvera_incoming",
            }
        },
    )
    return (
        await db.gl_journal_entries.find_one(
            {"tenant_id": tenant_id, "id": entry["id"]},
            {"_id": 0},
        )
        or entry
    )


async def reverse_incoming_invoice_gl_for_return(
    tenant_id: str,
    source_invoice_id: str,
    *,
    action_id: str,
    generated_provider_uuid: str,
    actor: str = "system",
) -> dict | None:
    """Reverse the exact source GL journal after successful CreateReturn.

    Returns ``None`` when the source invoice has not been posted to GL. This is
    not treated as a provider failure: CreateReturn can succeed independently,
    while accounting surfaces the missing source journal for an operator.
    """
    db = get_db_for_tenant(tenant_id)
    original = await db.gl_journal_entries.find_one(
        {
            "tenant_id": tenant_id,
            "idempotency_key": f"nilvera-incoming:{source_invoice_id}",
            "source": "nilvera_incoming",
            "status": "posted",
        },
        {"_id": 0},
    )
    if original is None:
        return None

    original_lines = original.get("lines") or []
    if not original_lines:
        raise InvoiceGLBridgeError("Source GL journal has no lines")

    reversal_lines: list[dict] = []
    for line in original_lines:
        debit = round(float(line.get("debit", 0) or 0), 2)
        credit = round(float(line.get("credit", 0) or 0), 2)
        if (debit > 0) == (credit > 0):
            raise InvoiceGLBridgeError("Source GL journal line is not reversible")
        reversal_lines.append(
            {
                "account_code": line.get("account_code"),
                "debit": credit,
                "credit": debit,
                "memo": f"İade ters kaydı: {line.get('memo') or original.get('memo') or ''}"[:300],
            }
        )

    try:
        reversal = await post_journal_entry(
            db,
            tenant_id,
            date=datetime.now(UTC).date().isoformat(),
            memo=f"Nilvera iade faturası ters kaydı: {original.get('entry_no') or source_invoice_id}",
            lines=reversal_lines,
            source="nilvera_return",
            source_ref=generated_provider_uuid,
            actor=actor,
            idempotency_key=f"nilvera-return:{action_id}",
            reverses_entry_id=original.get("id"),
            reversal_reason=f"Nilvera iade faturası {generated_provider_uuid}",
        )
    except GLPostingError as exc:
        raise InvoiceGLBridgeError(str(exc)) from exc

    await db.gl_journal_entries.update_one(
        {"tenant_id": tenant_id, "id": reversal["id"]},
        {
            "$set": {
                "nilvera_source_invoice_id": source_invoice_id,
                "nilvera_return_action_id": action_id,
                "nilvera_generated_provider_uuid": generated_provider_uuid,
                "integration_kind": "nilvera_return",
            }
        },
    )
    return (
        await db.gl_journal_entries.find_one(
            {"tenant_id": tenant_id, "id": reversal["id"]},
            {"_id": 0},
        )
        or reversal
    )


async def get_incoming_invoice_gl_link(tenant_id: str, incoming_invoice_id: str) -> InvoiceGLLink:
    db = get_db_for_tenant(tenant_id)
    source_entry = await db.gl_journal_entries.find_one(
        {
            "tenant_id": tenant_id,
            "idempotency_key": f"nilvera-incoming:{incoming_invoice_id}",
        },
        {"_id": 0},
    )
    cursor = db.gl_journal_entries.find(
        {
            "tenant_id": tenant_id,
            "nilvera_source_invoice_id": incoming_invoice_id,
            "integration_kind": "nilvera_return",
        },
        {"_id": 0},
    ).sort("created_at", -1)
    return_entries = tuple(await cursor.to_list(length=100))
    return InvoiceGLLink(source_entry=source_entry, return_entries=return_entries)


async def post_outgoing_invoice_to_gl(
    tenant_id: str,
    invoice_id: str,
    *,
    revenue_account_code: str,
    receivable_account_code: str,
    discount_account_code: str | None = None,
    vat_account_code: str | None = None,
    accommodation_tax_account_code: str | None = None,
    vat_accounts_by_rate: dict[str, str] | None = None,
    accommodation_tax_accounts_by_rate: dict[str, str] | None = None,
    actor: str,
) -> dict:
    """Post an outgoing invoice to GL with line-level tax and discount support."""
    db = get_db_for_tenant(tenant_id)
    invoice = await db.invoices.find_one({"tenant_id": tenant_id, "id": invoice_id})
    if not invoice:
        raise InvoiceGLBridgeError("Outgoing invoice not found")

    currency = str(invoice.get("currency") or "TRY").strip().upper()
    if currency not in _ALLOWED_TRY_CODES:
        raise InvoiceGLBridgeError("Only TRY outgoing invoices can be posted to GL automatically")

    total = _money(invoice.get("total", 0))
    if total <= 0:
        raise InvoiceGLBridgeError("Outgoing invoice total must be positive")

    revenue_account = _clean_account(revenue_account_code, "Revenue")
    receivable_account = _clean_account(receivable_account_code, "Receivable")
    discount_account = _clean_account(discount_account_code, "Discount") if discount_account_code else None

    vat_by_rate: dict[str, Decimal] = {}
    acc_tax_by_rate: dict[str, Decimal] = {}

    base_revenue = Decimal("0")
    total_discount = Decimal("0")

    items = invoice.get("items", [])
    if items:
        for item in items:
            qty = _money(item.get("quantity", 1))
            price = _money(item.get("unit_price", 0))
            gross = qty * price

            disc = _money(item.get("discount_amount", 0))
            total_discount += disc

            if discount_account:
                base_revenue += gross
            else:
                base_revenue += gross - disc

            vat_amt = _money(item.get("kdv_amount", 0))
            if vat_amt > 0:
                kdv_rate_str = str(int(item.get("kdv_rate", 0)))
                vat_by_rate[kdv_rate_str] = vat_by_rate.get(kdv_rate_str, Decimal("0")) + vat_amt

            other_taxes = item.get("other_taxes", [])
            for t in other_taxes:
                if t.get("tax_code") == "0059":
                    acc_tax_amt = _money(t.get("amount", 0))
                    acc_tax_rate_str = str(int(t.get("rate", 0)))
                    acc_tax_by_rate[acc_tax_rate_str] = acc_tax_by_rate.get(acc_tax_rate_str, Decimal("0")) + acc_tax_amt
                else:
                    raise InvoiceGLBridgeError(f"Unsupported other tax code: {t.get('tax_code')}")
    else:
        base_revenue = _money(invoice.get("subtotal", 0))
        tax = _money(invoice.get("tax", 0))
        if tax > 0:
            vat_by_rate["0"] = tax

    journal_lines: list[dict] = []

    # 1. Receivable (Debit)
    journal_lines.append({"account_code": receivable_account, "debit": float(total), "credit": 0, "memo": "Satış faturası alacağı"})

    # 2. Revenue (Credit)
    journal_lines.append({"account_code": revenue_account, "debit": 0, "credit": float(base_revenue), "memo": "Satış faturası geliri"})

    # 3. Discount (Debit)
    if discount_account and total_discount > 0:
        journal_lines.append({"account_code": discount_account, "debit": float(total_discount), "credit": 0, "memo": "Satış faturası iskontosu"})

    # 4. VAT (Credit) - Per Rate
    vat_map = vat_accounts_by_rate or {}
    for rate, amt in vat_by_rate.items():
        if amt > 0:
            acc = vat_map.get(rate) or vat_account_code
            if not acc:
                raise InvoiceGLBridgeError(f"No VAT account provided for rate {rate}%")
            journal_lines.append({"account_code": _clean_account(acc, f"VAT {rate}%"), "debit": 0, "credit": float(amt), "memo": f"Satış faturası {rate}% KDV"})

    # 5. Accommodation Tax (Credit) - Per Rate
    acc_tax_map = accommodation_tax_accounts_by_rate or {}
    for rate, amt in acc_tax_by_rate.items():
        if amt > 0:
            acc = acc_tax_map.get(rate) or accommodation_tax_account_code
            if not acc:
                raise InvoiceGLBridgeError(f"No Accommodation Tax account provided for rate {rate}%")
            journal_lines.append({"account_code": _clean_account(acc, f"Acc Tax {rate}%"), "debit": 0, "credit": float(amt), "memo": f"Satış faturası konaklama vergisi {rate}%"})

    tot_debit = float(total) + (float(total_discount) if discount_account else 0)
    tot_credit = float(base_revenue) + float(sum(vat_by_rate.values())) + float(sum(acc_tax_by_rate.values()))

    if abs(tot_debit - tot_credit) > 0.02:
        raise InvoiceGLBridgeError(f"Journal unbalanced: Debit {tot_debit} != Credit {tot_credit}")

    issue_date = invoice.get("issue_date")
    if isinstance(issue_date, datetime):
        posting_date = issue_date.date().isoformat()
    elif isinstance(issue_date, str) and len(issue_date) >= 10:
        posting_date = issue_date[:10]
    else:
        posting_date = datetime.now(UTC).date().isoformat()

    try:
        entry = await post_journal_entry(
            db,
            tenant_id,
            date=posting_date,
            memo=f"Satış faturası {invoice.get('invoice_number', invoice_id)}",
            lines=journal_lines,
            source="nilvera_outgoing",
            source_ref=invoice_id,
            actor=actor,
            idempotency_key=f"nilvera-outgoing:{invoice_id}",
        )
    except GLPostingError as exc:
        raise InvoiceGLBridgeError(str(exc)) from exc

    await db.gl_journal_entries.update_one(
        {"tenant_id": tenant_id, "id": entry["id"]},
        {
            "$set": {
                "nilvera_source_invoice_id": invoice_id,
                "nilvera_invoice_number": invoice.get("invoice_number"),
                "integration_kind": "nilvera_outgoing",
            }
        },
    )
    return (
        await db.gl_journal_entries.find_one(
            {"tenant_id": tenant_id, "id": entry["id"]},
            {"_id": 0},
        )
        or entry
    )


async def reverse_outgoing_invoice_gl(
    tenant_id: str,
    invoice_id: str,
    *,
    event_ref: str,
    reason: str,
    actor: str = "system",
) -> dict | None:
    """Reverse an accepted Nilvera sales invoice journal exactly once.

    Cancellation/rejection can arrive more than once through status polling or
    a local invoice update.  The event reference makes the reversal replay-safe
    while ``reversal_status`` on the source prevents a second event from
    reversing the same sale twice.
    """
    db = get_db_for_tenant(tenant_id)
    original = await db.gl_journal_entries.find_one(
        {
            "tenant_id": tenant_id,
            "idempotency_key": f"nilvera-outgoing:{invoice_id}",
            "source": "nilvera_outgoing",
            "status": "posted",
        },
        {"_id": 0},
    )
    if original is None:
        return None
    if original.get("reversal_status") == "reversed" and original.get("reversal_entry_id"):
        return await db.gl_journal_entries.find_one(
            {"tenant_id": tenant_id, "id": original["reversal_entry_id"]},
            {"_id": 0},
        )

    original_lines = original.get("lines") or []
    if not original_lines:
        raise InvoiceGLBridgeError("Source outgoing GL journal has no lines")
    reversal_lines: list[dict] = []
    for line in original_lines:
        debit = round(float(line.get("debit", 0) or 0), 2)
        credit = round(float(line.get("credit", 0) or 0), 2)
        if (debit > 0) == (credit > 0):
            raise InvoiceGLBridgeError("Source outgoing GL journal line is not reversible")
        reversal_line = {
            "account_code": line.get("account_code"),
            "debit": credit,
            "credit": debit,
            "memo": f"Satış iptal/iade ters kaydı: {line.get('memo') or ''}"[:300],
        }
        if line.get("currency"):
            reversal_line.update(
                {
                    "currency": line.get("currency"),
                    "foreign_amount": line.get("foreign_amount"),
                    "exchange_rate": line.get("exchange_rate"),
                }
            )
        reversal_lines.append(reversal_line)

    try:
        reversal = await post_journal_entry(
            db,
            tenant_id,
            date=datetime.now(UTC).date().isoformat(),
            memo=f"Nilvera satış iptal/iade ters kaydı: {original.get('entry_no') or invoice_id}",
            lines=reversal_lines,
            source="nilvera_outgoing_reversal",
            source_ref=event_ref,
            actor=actor,
            idempotency_key=f"nilvera-outgoing-reversal:{invoice_id}",
            reverses_entry_id=original.get("id"),
            reversal_reason=reason,
        )
    except GLPostingError as exc:
        raise InvoiceGLBridgeError(str(exc)) from exc

    now = datetime.now(UTC).isoformat()
    await db.gl_journal_entries.update_one(
        {"tenant_id": tenant_id, "id": reversal["id"]},
        {
            "$set": {
                "nilvera_source_invoice_id": invoice_id,
                "nilvera_cancellation_event_ref": event_ref,
                "integration_kind": "nilvera_outgoing_reversal",
            }
        },
    )
    await db.gl_journal_entries.update_one(
        {"tenant_id": tenant_id, "id": original["id"]},
        {
            "$set": {
                "reversal_status": "reversed",
                "reversal_entry_id": reversal["id"],
                "reversed_at": now,
                "reversed_by": actor,
            }
        },
    )
    return (
        await db.gl_journal_entries.find_one(
            {"tenant_id": tenant_id, "id": reversal["id"]},
            {"_id": 0},
        )
        or reversal
    )
