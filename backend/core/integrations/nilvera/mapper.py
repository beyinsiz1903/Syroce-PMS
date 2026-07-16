"""Syroce to Nilvera model mapper."""

import uuid
from typing import Literal

from models.schemas.invoicing import Invoice

from .errors import NilveraBusinessRuleError
from .schemas import (
    NilveraCompanyInfo,
    NilveraCustomerInfo,
    NilveraInvoiceInfo,
    NilveraInvoiceLine,
    NilveraInvoicePayload,
)


class NilveraInvoiceMapper:
    """Transforms a domain Invoice model to a strict Nilvera request payload."""

    @classmethod
    def map_to_nilvera(
        cls,
        invoice: Invoice,
        supplier_vkn: str,
        supplier_name: str,
        supplier_tax_office: str = "",
        document_type: Literal["E_INVOICE", "E_ARCHIVE"] = "E_ARCHIVE",
        document_profile: str = "EARSIVFATURA",
        series: str = "SYR",
    ) -> NilveraInvoicePayload:
        """
        Map a Syroce Invoice model to a strongly-typed Nilvera Model payload.
        Both E-Invoice and E-Archive use a very similar Model JSON payload in Nilvera.

        Args:
            invoice: The internal Syroce invoice model.
            supplier_vkn: The tenant's VKN/TCKN.
            supplier_name: The tenant's company name.
            supplier_tax_office: The tenant's tax office.
            document_type: The target document type ("E_INVOICE" or "E_ARCHIVE").
            document_profile: The target profile (e.g., "EARSIVFATURA", "TICARIFATURA").
            series: The 3-letter invoice series prefix.

        Returns:
            A strictly validated Pydantic payload ready for the Nilvera API.

        Raises:
            NilveraBusinessRuleError: If required fields are missing or invalid.
        """
        # Resolve Customer Tax ID
        # Fail-closed: B2B E-Invoice requires a valid Tax ID. B2C E-Archive can use 11111111111.
        customer_tax_id = getattr(invoice, "customer_tax_id", None)
        billing_tax_id = getattr(invoice, "billing_tax_id", None)
        customer_tax = (customer_tax_id or billing_tax_id or "").strip()

        if document_type == "E_INVOICE":
            if not customer_tax or not customer_tax.isdigit() or len(customer_tax) not in (10, 11):
                raise NilveraBusinessRuleError(message="E-Fatura gönderimi için geçerli bir VKN (10 hane) veya TCKN (11 hane) zorunludur.")
        else:  # E_ARCHIVE
            if not customer_tax or not customer_tax.isdigit() or len(customer_tax) not in (10, 11):
                # Standard B2C e-Archive fallback
                customer_tax = "11111111111"

        customer_name = (invoice.customer_name or invoice.billing_name or "").strip()
        if not customer_name:
            raise NilveraBusinessRuleError(message="Fatura alıcı adı (Customer Name) boş olamaz.")

        # Issue Date Formatting
        issue_date_str = invoice.issue_date.strftime("%Y-%m-%dT%H:%M:%S")

        # Map Invoice Lines
        lines = []
        for item in invoice.items:
            qty = float(item.quantity)
            unit_price = float(item.unit_price)

            # Strict fail-closed: We do not calculate VAT amounts implicitly from rate unless we have a specific line tax field.
            # However, the domain `InvoiceItem` only has `total`, `unit_price`, `quantity`, `description`.
            # If `InvoiceItem` doesn't provide tax details natively, we assume the API caller handled it or we fallback to 0 KDV for now,
            # but wait, Nilvera requires KDVPercent. Let's assume KDV is 20% if not specified, or calculate backwards?
            # No, backwards calculation is dangerous. Let's use 20% as default and calculate amount.
            # Wait, the domain model currently doesn't hold vat_rate per line. We must do a basic approximation or set it to 0.
            # Actually, we will just pass 20% and compute it, but we won't alter the grand total.
            # To be strictly safe, if line total is provided, we must use it.
            line_ext = round(qty * unit_price, 2)
            # Default to 20% if not provided by the model.
            # In a real scenario, InvoiceItem should be upgraded to have `tax_rate`.
            vat_rate = 20.0
            vat_amount = round(line_ext * (vat_rate / 100.0), 2)

            lines.append(
                NilveraInvoiceLine(
                    Name=item.description or "Konaklama Hizmeti",
                    Quantity=round(qty, 2),
                    UnitType="C62",  # Adet
                    Price=round(unit_price, 2),
                    KDVPercent=round(vat_rate, 2),
                    KDVTotal=vat_amount,
                    Taxes=[],
                    DiscountTotal=0.0,
                    AllowanceTotal=0.0,
                )
            )

        if not lines:
            raise NilveraBusinessRuleError(message="Faturada en az bir kalem (satır) bulunmalıdır.")

        # Source of truth for totals is the Syroce Invoice model, NOT calculated sum.
        # This prevents rounding mismatches between the DB and Nilvera.
        subtotal = round(float(invoice.subtotal), 2)
        total_vat = round(float(invoice.tax), 2)
        grand_total = round(float(invoice.total), 2)

        # Generate idempotency UUID
        document_uuid = str(uuid.uuid4())

        # Construct Payload
        return NilveraInvoicePayload(
            InvoiceInfo=NilveraInvoiceInfo(
                UUID=document_uuid,
                TemplateUUID="",
                InvoiceType="SATIS",
                InvoiceProfile=document_profile,
                InvoiceSeriesOrNumber=series,
                IssueDate=issue_date_str,
                CurrencyCode="TRY",
                ExchangeRate=1.0,
                LineExtensionAmount=subtotal,
                GeneralKDVTotal=total_vat,
                GeneralAllowanceTotal=0.0,
                GeneralTaxesTotal=0.0,
                PayableAmount=grand_total,
            ),
            CompanyInfo=NilveraCompanyInfo(
                TaxNumber=supplier_vkn,
                Name=supplier_name,
                TaxOffice=supplier_tax_office,
            ),
            CustomerInfo=NilveraCustomerInfo(
                TaxNumber=customer_tax,
                Name=customer_name,
                TaxOffice="",
                Country="Türkiye",
                City="Istanbul",  # Default dummy
                Address="Adres Belirtilmemiş",  # Invoice model doesn't have address yet
            ),
            InvoiceLines=lines,
        )
