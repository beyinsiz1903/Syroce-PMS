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
    if currency not in _ALLOWED_TRY_CODES:
        raise InvoiceGLBridgeError("Only TRY incoming invoices can be posted to GL automatically")

    payable = _money(invoice.payable_amount)
    if payable <= 0:
        raise InvoiceGLBridgeError("Incoming invoice payable amount must be positive")

    lines = await IncomingInvoiceRepository.list_lines(tenant_id, incoming_invoice_id)
    active_lines = [line for line in lines if getattr(line, "active", True)]
    if not active_lines:
        raise InvoiceGLBridgeError("Incoming invoice has no active lines")

    if any(getattr(line, "other_taxes", None) for line in active_lines):
        raise InvoiceGLBridgeError("Incoming invoice contains unsupported other taxes or deductions")

    base_total = sum((_money(line.line_extension_amount) for line in active_lines), Decimal("0"))
    vat_total = sum((_money(line.kdv_amount) for line in active_lines), Decimal("0"))
    calculated_total = (base_total + vat_total).quantize(Decimal("0.01"))
    if abs(calculated_total - payable) > _ROUNDING_TOLERANCE:
        raise InvoiceGLBridgeError(
            "Incoming invoice totals do not reconcile to payable amount; accounting mapping is required"
        )

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
    journal_lines.append(
        {
            "account_code": payable_account,
            "debit": 0,
            "credit": float(payable),
            "memo": "Nilvera satıcı borcu",
        }
    )

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
    return await db.gl_journal_entries.find_one(
        {"tenant_id": tenant_id, "id": entry["id"]},
        {"_id": 0},
    ) or entry


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
                "reverses_entry_id": original.get("id"),
                "integration_kind": "nilvera_return",
            }
        },
    )
    return await db.gl_journal_entries.find_one(
        {"tenant_id": tenant_id, "id": reversal["id"]},
        {"_id": 0},
    ) or reversal


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
