"""Real Turkish e-Fatura / e-Arsiv provider integration.

Replaces the previous mock that wrote a fake ``EFATURA-{no}`` UUID at check-out.
The PMS is the authoritative data source: this module turns a closed-folio sales
invoice into a UBL-TR (TR-customised UBL 2.1) document and transmits it to the
operator-configured provider (Uyumsoft / Fit Solutions / GIB-compatible REST
gateway).

Fail-closed principle: if provider credentials are not configured we refuse to
"generate" anything. NO fake success is ever written. Transmission failures are
surfaced as :class:`EFaturaSubmissionError` so the caller can retry and alert.

Outbound HTTP always goes through the SSRF-safe, DNS-rebinding-protected
``safe_post_async`` helper so an operator-supplied provider URL cannot be abused
to reach internal infrastructure.
"""
from __future__ import annotations

import base64
import os
from datetime import UTC, datetime
from typing import Any
from xml.sax.saxutils import escape as _xe
from xml.sax.saxutils import quoteattr as _qa


class EFaturaConfigError(RuntimeError):
    """Raised (fail-closed) when provider credentials are not configured."""


class EFaturaSubmissionError(RuntimeError):
    """Raised when a provider call fails (transport or business error).

    Retryable: the caller keeps the invoice ``pending`` and retries on the next
    sweep until a max-attempts cap is reached, then alerts ops.
    """


# Minimum env vars required before we will attempt a real cut. Without any of
# these the integration stays fail-closed (no mock fallback).
_REQUIRED_ENV = (
    "EFATURA_PROVIDER_URL",
    "EFATURA_PROVIDER_API_KEY",
    "EFATURA_SUPPLIER_VKN",
)


def is_configured() -> bool:
    """True only when every required provider credential is present."""
    return all(os.environ.get(k) for k in _REQUIRED_ENV)


def provider_config() -> dict[str, Any]:
    """Resolve provider config from env; raise EFaturaConfigError if incomplete."""
    missing = [k for k in _REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        raise EFaturaConfigError(
            "e-Fatura provider not configured; missing env: " + ", ".join(missing)
        )
    try:
        timeout = float(os.environ.get("EFATURA_PROVIDER_TIMEOUT_SECONDS", "20") or "20")
    except (TypeError, ValueError):
        timeout = 20.0
    return {
        "provider": os.environ.get("EFATURA_PROVIDER", "generic"),
        "url": os.environ["EFATURA_PROVIDER_URL"],
        "api_key": os.environ["EFATURA_PROVIDER_API_KEY"],
        "supplier_vkn": os.environ["EFATURA_SUPPLIER_VKN"],
        "supplier_name": os.environ.get("EFATURA_SUPPLIER_NAME", "") or "",
        "test_mode": (os.environ.get("EFATURA_PROVIDER_TEST_MODE", "").strip().lower()
                      in {"1", "true", "yes", "on"}),
        "timeout": timeout,
    }


def max_attempts() -> int:
    """Retry cap before a pending invoice is marked ``error`` + alerted."""
    try:
        v = int(os.environ.get("EFATURA_MAX_ATTEMPTS", "5"))
    except (TypeError, ValueError):
        return 5
    return v if v > 0 else 5


def document_profile(invoice: dict[str, Any]) -> str:
    """Pick the UBL-TR profile.

    A registered taxpayer recipient (10-digit VKN) gets a commercial e-Fatura
    (``TICARIFATURA``); everyone else (no tax number, or an 11-digit individual
    TCKN) gets an e-Arsiv document (``EARSIVFATURA``).
    """
    tax = (invoice.get("customer_tax_number") or "").strip()
    return "TICARIFATURA" if (tax.isdigit() and len(tax) == 10) else "EARSIVFATURA"


def _money(value: Any) -> str:
    try:
        return f"{float(value or 0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_ubl_tr_document(
    invoice: dict[str, Any],
    *,
    supplier_vkn: str,
    supplier_name: str,
    ettn: str,
    profile: str | None = None,
    now: datetime | None = None,
) -> str:
    """Build a UBL-TR (TR-customised UBL 2.1) invoice document.

    Pure function: no network, no DB. All caller-supplied text is XML-escaped to
    prevent injection from guest/customer names or charge descriptions.
    """
    now = now or datetime.now(UTC)
    profile = profile or document_profile(invoice)
    currency = (invoice.get("currency") or "TRY").upper()
    inv_no = str(invoice.get("invoice_number") or "")
    items = invoice.get("items") or []

    customer_name = str(invoice.get("customer_name") or "").strip() or "Musteri"
    customer_tax = str(invoice.get("customer_tax_number") or "").strip()
    customer_address = str(invoice.get("customer_address") or "").strip()
    tax_scheme_id = "VKN" if (customer_tax.isdigit() and len(customer_tax) == 10) else "TCKN"

    lines: list[str] = []
    subtotal = 0.0
    total_vat = 0.0
    for idx, item in enumerate(items, start=1):
        qty = _num(item.get("quantity")) or 1.0
        unit_price = _num(item.get("unit_price"))
        line_ext = unit_price * qty
        vat_rate = _num(item.get("vat_rate"))
        vat_amount = item.get("vat_amount")
        vat_amount = _num(vat_amount) if vat_amount is not None else line_ext * (vat_rate / 100.0)
        subtotal += line_ext
        total_vat += vat_amount
        desc = _xe(str(item.get("description") or "Hizmet"))
        lines.append(
            "  <cac:InvoiceLine>\n"
            f"    <cbc:ID>{idx}</cbc:ID>\n"
            f"    <cbc:InvoicedQuantity unitCode=\"C62\">{_money(qty)}</cbc:InvoicedQuantity>\n"
            f"    <cbc:LineExtensionAmount currencyID={_qa(currency)}>{_money(line_ext)}</cbc:LineExtensionAmount>\n"
            "    <cac:TaxTotal>\n"
            f"      <cbc:TaxAmount currencyID={_qa(currency)}>{_money(vat_amount)}</cbc:TaxAmount>\n"
            "      <cac:TaxSubtotal>\n"
            f"        <cbc:TaxableAmount currencyID={_qa(currency)}>{_money(line_ext)}</cbc:TaxableAmount>\n"
            f"        <cbc:TaxAmount currencyID={_qa(currency)}>{_money(vat_amount)}</cbc:TaxAmount>\n"
            f"        <cbc:Percent>{_money(vat_rate)}</cbc:Percent>\n"
            "        <cac:TaxCategory><cac:TaxScheme><cbc:Name>KDV</cbc:Name>"
            "<cbc:TaxTypeCode>0015</cbc:TaxTypeCode></cac:TaxScheme></cac:TaxCategory>\n"
            "      </cac:TaxSubtotal>\n"
            "    </cac:TaxTotal>\n"
            "    <cac:Item>\n"
            f"      <cbc:Name>{desc}</cbc:Name>\n"
            "    </cac:Item>\n"
            f"    <cac:Price><cbc:PriceAmount currencyID={_qa(currency)}>{_money(unit_price)}</cbc:PriceAmount></cac:Price>\n"
            "  </cac:InvoiceLine>"
        )

    # Prefer stored aggregate totals when present (folio-sourced invoices carry
    # them), else fall back to the per-line sums computed above.
    if invoice.get("subtotal") is not None:
        subtotal = _num(invoice.get("subtotal"))
    if invoice.get("total_vat") is not None:
        total_vat = _num(invoice.get("total_vat"))
    grand_total = _num(invoice.get("total")) or (subtotal + total_vat)

    customer_party_id = ""
    if customer_tax:
        customer_party_id = (
            "      <cac:PartyIdentification>"
            f"<cbc:ID schemeID={_qa(tax_scheme_id)}>{_xe(customer_tax)}</cbc:ID>"
            "</cac:PartyIdentification>\n"
        )
    customer_address_xml = ""
    if customer_address:
        customer_address_xml = (
            "      <cac:PostalAddress>"
            f"<cbc:StreetName>{_xe(customer_address)}</cbc:StreetName>"
            "</cac:PostalAddress>\n"
        )

    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<Invoice xmlns=\"urn:oasis:names:specification:ubl:schema:xsd:Invoice-2\""
        " xmlns:cac=\"urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2\""
        " xmlns:cbc=\"urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2\">\n"
        "  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>\n"
        "  <cbc:CustomizationID>TR1.2</cbc:CustomizationID>\n"
        f"  <cbc:ProfileID>{_xe(profile)}</cbc:ProfileID>\n"
        f"  <cbc:ID>{_xe(inv_no)}</cbc:ID>\n"
        f"  <cbc:UUID>{_xe(ettn)}</cbc:UUID>\n"
        f"  <cbc:IssueDate>{now.strftime('%Y-%m-%d')}</cbc:IssueDate>\n"
        f"  <cbc:IssueTime>{now.strftime('%H:%M:%S')}</cbc:IssueTime>\n"
        "  <cbc:InvoiceTypeCode>SATIS</cbc:InvoiceTypeCode>\n"
        f"  <cbc:DocumentCurrencyCode>{_xe(currency)}</cbc:DocumentCurrencyCode>\n"
        f"  <cbc:LineCountNumeric>{len(items)}</cbc:LineCountNumeric>\n"
        "  <cac:AccountingSupplierParty>\n"
        "    <cac:Party>\n"
        f"      <cac:PartyIdentification><cbc:ID schemeID=\"VKN\">{_xe(str(supplier_vkn))}</cbc:ID></cac:PartyIdentification>\n"
        f"      <cac:PartyName><cbc:Name>{_xe(str(supplier_name) or 'Tedarikci')}</cbc:Name></cac:PartyName>\n"
        "    </cac:Party>\n"
        "  </cac:AccountingSupplierParty>\n"
        "  <cac:AccountingCustomerParty>\n"
        "    <cac:Party>\n"
        f"{customer_party_id}"
        f"      <cac:PartyName><cbc:Name>{_xe(customer_name)}</cbc:Name></cac:PartyName>\n"
        f"{customer_address_xml}"
        "    </cac:Party>\n"
        "  </cac:AccountingCustomerParty>\n"
        "  <cac:TaxTotal>\n"
        f"    <cbc:TaxAmount currencyID={_qa(currency)}>{_money(total_vat)}</cbc:TaxAmount>\n"
        "    <cac:TaxSubtotal>\n"
        f"      <cbc:TaxableAmount currencyID={_qa(currency)}>{_money(subtotal)}</cbc:TaxableAmount>\n"
        f"      <cbc:TaxAmount currencyID={_qa(currency)}>{_money(total_vat)}</cbc:TaxAmount>\n"
        "      <cac:TaxCategory><cac:TaxScheme><cbc:Name>KDV</cbc:Name>"
        "<cbc:TaxTypeCode>0015</cbc:TaxTypeCode></cac:TaxScheme></cac:TaxCategory>\n"
        "    </cac:TaxSubtotal>\n"
        "  </cac:TaxTotal>\n"
        "  <cac:LegalMonetaryTotal>\n"
        f"    <cbc:LineExtensionAmount currencyID={_qa(currency)}>{_money(subtotal)}</cbc:LineExtensionAmount>\n"
        f"    <cbc:TaxExclusiveAmount currencyID={_qa(currency)}>{_money(subtotal)}</cbc:TaxExclusiveAmount>\n"
        f"    <cbc:TaxInclusiveAmount currencyID={_qa(currency)}>{_money(grand_total)}</cbc:TaxInclusiveAmount>\n"
        f"    <cbc:PayableAmount currencyID={_qa(currency)}>{_money(grand_total)}</cbc:PayableAmount>\n"
        "  </cac:LegalMonetaryTotal>\n"
        + ("\n".join(lines) + ("\n" if lines else ""))
        + "</Invoice>\n"
    )


async def submit_document(
    *,
    ubl_xml: str,
    ettn: str,
    invoice_number: str,
    document_profile: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Transmit a UBL-TR document to the configured provider.

    Returns ``{official_id, status, provider, raw}`` on success. Raises
    :class:`EFaturaSubmissionError` on any transport or non-2xx provider
    response (retryable by the caller).
    """
    cfg = config or provider_config()
    from integrations.xchange.safety import EgressDenied, safe_post_async

    payload = {
        "documentType": "EARSIV" if document_profile == "EARSIVFATURA" else "EFATURA",
        "profile": document_profile,
        "ettn": ettn,
        "invoiceNumber": invoice_number,
        "supplierVkn": cfg["supplier_vkn"],
        "testMode": cfg["test_mode"],
        "ublXmlBase64": base64.b64encode(ubl_xml.encode("utf-8")).decode("ascii"),
    }
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        resp = await safe_post_async(
            cfg["url"], json=payload, headers=headers, timeout=cfg["timeout"]
        )
    except EgressDenied as e:
        raise EFaturaSubmissionError(f"provider egress blocked: {e}") from e
    except Exception as e:  # noqa: BLE001 - httpx/network errors are retryable
        raise EFaturaSubmissionError(f"provider transport error: {e}") from e

    if resp.status_code >= 400:
        raise EFaturaSubmissionError(
            f"provider returned HTTP {resp.status_code}: {str(resp.text)[:300]}"
        )

    try:
        data = resp.json()
    except Exception:  # noqa: BLE001 - tolerate non-JSON bodies
        data = {}
    if not isinstance(data, dict):
        data = {}

    official = (
        data.get("ettn")
        or data.get("uuid")
        or data.get("invoiceUuid")
        or data.get("documentId")
        or data.get("id")
        or ettn
    )
    status = str(data.get("status") or "generated")
    return {
        "official_id": str(official),
        "status": status,
        "provider": cfg["provider"],
        "raw": data,
    }
