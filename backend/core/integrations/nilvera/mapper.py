from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from core.integrations.nilvera.errors import NilveraBusinessRuleError
from models.schemas.invoicing import Invoice, validate_invoice_tax_snapshot


class NilveraConfiguredModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        strict=True,
    )


class NilveraInvoiceInfo(NilveraConfiguredModel):
    UUID: str
    IssueDate: datetime
    InvoiceType: str
    InvoiceProfile: str
    InvoiceSerieOrNumber: str
    CurrencyCode: str
    ExchangeRate: Decimal | None = None
    PayableAmount: Decimal


class NilveraCompanyInfo(NilveraConfiguredModel):
    TaxNumber: str
    Name: str
    TaxOffice: str
    Country: str
    City: str
    Address: str


class NilveraCustomerInfo(NilveraConfiguredModel):
    TaxNumber: str
    Name: str
    Country: str
    City: str
    Address: str
    TaxOffice: str | None = None


class NilveraInvoiceLine(NilveraConfiguredModel):
    Name: str
    Quantity: Decimal
    UnitType: str
    Price: Decimal
    AllowanceTotal: Decimal
    KDVPercent: Decimal
    KDVTotal: Decimal


class NilveraEInvoiceModel(NilveraConfiguredModel):
    InvoiceInfo: NilveraInvoiceInfo
    CompanyInfo: NilveraCompanyInfo
    CustomerInfo: NilveraCustomerInfo
    InvoiceLines: list[NilveraInvoiceLine]


class NilveraEInvoicePayload(NilveraConfiguredModel):
    EInvoice: NilveraEInvoiceModel
    CustomerAlias: str


class SellerSnapshot(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )
    tax_number: str | None = None
    name: str | None = None
    tax_office: str | None = None
    country: str | None = None
    city: str | None = None
    address: str | None = None


def _validate_text(value: str | None, err_msg: str, provider_code: str) -> str:
    if value is None or not value.strip():
        raise NilveraBusinessRuleError(err_msg, provider_code=provider_code)
    return value.strip()


class NilveraInvoiceMapper:
    """Pure transformation layer for mapping Syroce Invoice domain to Nilvera EInvoice Model."""

    @staticmethod
    def map_to_nilvera(
        invoice: Invoice,
        seller: SellerSnapshot,
        customer_alias: str | None,
        request_uuid: UUID,
    ) -> NilveraEInvoicePayload:
        """
        Map a validated Syroce Invoice snapshot to a Nilvera e-Invoice payload.
        Fail-closed: raises NilveraBusinessRuleError if any required field is missing or invalid.
        """
        # 1. Document Kind
        if invoice.document_kind != "E_INVOICE":
            raise NilveraBusinessRuleError("Unsupported document kind", provider_code="E_INVOICE_DOCUMENT_KIND_INVALID")

        # 2. UUID Type
        if not isinstance(request_uuid, UUID):
            raise NilveraBusinessRuleError("Invalid request UUID type", provider_code="E_INVOICE_UUID_INVALID")

        # 3. Empty Items
        if not invoice.items:
            raise NilveraBusinessRuleError("Invoice has no items", provider_code="E_INVOICE_ITEMS_EMPTY")

        # 4. Domain Validation
        try:
            validate_invoice_tax_snapshot(invoice)
        except ValueError:
            raise NilveraBusinessRuleError(
                "E-invoice domain snapshot validation failed.",
                provider_code="E_INVOICE_DOMAIN_VALIDATION_FAILED",
            ) from None

        # 5. Seller Identity and Address
        seller_tax_clean = _validate_text(seller.tax_number, "Seller tax number is missing", "E_INVOICE_SELLER_TAX_NUMBER_REQUIRED")
        if not seller_tax_clean.isdigit() or len(seller_tax_clean) not in (10, 11):
            raise NilveraBusinessRuleError("Seller tax number is invalid", provider_code="E_INVOICE_SELLER_TAX_NUMBER_INVALID")

        seller_name_clean = _validate_text(seller.name, "Seller name is missing", "E_INVOICE_SELLER_NAME_REQUIRED")
        seller_tax_office_clean = _validate_text(seller.tax_office, "Seller tax office is missing", "E_INVOICE_SELLER_TAX_OFFICE_REQUIRED")
        seller_country_clean = _validate_text(seller.country, "Seller country is missing", "E_INVOICE_SELLER_COUNTRY_REQUIRED")
        seller_city_clean = _validate_text(seller.city, "Seller city is missing", "E_INVOICE_SELLER_CITY_REQUIRED")
        seller_address_clean = _validate_text(seller.address, "Seller address is missing", "E_INVOICE_SELLER_ADDRESS_REQUIRED")

        # 6. Buyer Identity and Address
        buyer_tax_clean = _validate_text(invoice.buyer_tax_number, "Buyer tax number is missing", "E_INVOICE_BUYER_TAX_NUMBER_REQUIRED")
        if not buyer_tax_clean.isdigit() or len(buyer_tax_clean) not in (10, 11):
            raise NilveraBusinessRuleError("Buyer tax number is invalid", provider_code="E_INVOICE_BUYER_TAX_NUMBER_INVALID")

        buyer_name_clean = _validate_text(invoice.buyer_legal_name, "Buyer legal name is missing", "E_INVOICE_BUYER_NAME_REQUIRED")
        buyer_country_clean = _validate_text(invoice.buyer_country_name, "Buyer country is missing", "E_INVOICE_BUYER_COUNTRY_REQUIRED")
        buyer_city_clean = _validate_text(invoice.buyer_city, "Buyer city is missing", "E_INVOICE_BUYER_CITY_REQUIRED")
        buyer_address_clean = _validate_text(invoice.buyer_address, "Buyer address is missing", "E_INVOICE_BUYER_ADDRESS_REQUIRED")

        buyer_tax_office_clean = invoice.buyer_tax_office.strip() if invoice.buyer_tax_office and invoice.buyer_tax_office.strip() else None

        # 7. Alias
        alias_clean = _validate_text(customer_alias, "Customer alias is required", "E_INVOICE_CUSTOMER_ALIAS_REQUIRED")

        # 8. Type, Profile, Series
        invoice_type_clean = _validate_text(invoice.invoice_type, "Invoice type is missing", "E_INVOICE_TYPE_REQUIRED")
        if invoice_type_clean != "SATIS":
            raise NilveraBusinessRuleError("Unsupported invoice type", provider_code="E_INVOICE_TYPE_UNSUPPORTED")

        profile_clean = _validate_text(invoice.profile, "Invoice profile is missing", "E_INVOICE_PROFILE_REQUIRED")

        if invoice.series is None or not invoice.series.strip():
            raise NilveraBusinessRuleError("Invoice series is missing", provider_code="E_INVOICE_SERIES_REQUIRED")
        if invoice.series != invoice.series.strip() or not invoice.series.isprintable():
            raise NilveraBusinessRuleError("Invalid series format", provider_code="E_INVOICE_SERIES_FORMAT_INVALID")
        if len(invoice.series) not in (3, 16):
            raise NilveraBusinessRuleError("Invalid series length", provider_code="E_INVOICE_SERIES_FORMAT_INVALID")
        series_clean = invoice.series

        # 9. Currency & Exchange Rate
        if invoice.currency is None or not invoice.currency.strip():
            raise NilveraBusinessRuleError("Currency is missing", provider_code="E_INVOICE_CURRENCY_REQUIRED")
        if len(invoice.currency) != 3 or not invoice.currency.isupper() or not invoice.currency.isalpha() or not invoice.currency.isascii():
            raise NilveraBusinessRuleError("Invalid currency format", provider_code="E_INVOICE_CURRENCY_INVALID")
        currency_clean = invoice.currency

        exchange_rate = None
        if currency_clean != "TRY":
            if invoice.exchange_rate is None or not invoice.exchange_rate.is_finite() or invoice.exchange_rate <= Decimal("0"):
                raise NilveraBusinessRuleError("Valid exchange rate is required for non-TRY currencies", provider_code="E_INVOICE_EXCHANGE_RATE_REQUIRED")
            exchange_rate = invoice.exchange_rate

        # 10. Issue Date Timezone validation
        if invoice.issue_date is None or invoice.issue_date.tzinfo is None or invoice.issue_date.utcoffset() is None:
            raise NilveraBusinessRuleError("Issue date must be timezone-aware", provider_code="E_INVOICE_NAIVE_DATETIME")

        # 11. KDV & Other Taxes Mapping
        nilvera_lines = []
        for item in invoice.items:
            if item.other_taxes:
                raise NilveraBusinessRuleError("Other taxes are currently unsupported", provider_code="E_INVOICE_OTHER_TAX_UNSUPPORTED")

            if item.kdv_rate == Decimal('0'):
                raise NilveraBusinessRuleError("KDV exemption is currently unsupported", provider_code="E_INVOICE_KDV_EXEMPTION_UNSUPPORTED")

            line = NilveraInvoiceLine(
                Name=item.description,
                Quantity=item.tax_quantity,
                UnitType=item.unit_code,
                Price=item.tax_unit_price,
                AllowanceTotal=item.discount_amount,
                KDVPercent=item.kdv_rate,
                KDVTotal=item.kdv_amount,
            )
            nilvera_lines.append(line)

        # Assemble Final Payload
        info = NilveraInvoiceInfo(
            UUID=str(request_uuid),
            IssueDate=invoice.issue_date,
            InvoiceType=invoice_type_clean,
            InvoiceProfile=profile_clean,
            InvoiceSerieOrNumber=series_clean,
            CurrencyCode=currency_clean,
            ExchangeRate=exchange_rate,
            PayableAmount=invoice.payable_total,
        )

        comp = NilveraCompanyInfo(
            TaxNumber=seller_tax_clean,
            Name=seller_name_clean,
            TaxOffice=seller_tax_office_clean,
            Country=seller_country_clean,
            City=seller_city_clean,
            Address=seller_address_clean,
        )

        cust = NilveraCustomerInfo(
            TaxNumber=buyer_tax_clean,
            Name=buyer_name_clean,
            Country=buyer_country_clean,
            City=buyer_city_clean,
            Address=buyer_address_clean,
            TaxOffice=buyer_tax_office_clean,
        )

        einvoice = NilveraEInvoiceModel(
            InvoiceInfo=info,
            CompanyInfo=comp,
            CustomerInfo=cust,
            InvoiceLines=nilvera_lines,
        )

        return NilveraEInvoicePayload(
            EInvoice=einvoice,
            CustomerAlias=alias_clean,
        )
