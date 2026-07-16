"""Pydantic schemas for Nilvera Invoice payloads."""

from pydantic import BaseModel, ConfigDict, Field


class NilveraTax(BaseModel):
    """Represents an additional tax line (e.g., Accommodation Tax)."""

    model_config = ConfigDict(populate_by_name=True)
    tax_code: str = Field(alias="TaxCode")
    total: float = Field(alias="Total")
    percent: float = Field(alias="Percent")


class NilveraInvoiceLine(BaseModel):
    """Represents a single line item in a Nilvera invoice."""

    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(alias="Name")
    quantity: float = Field(alias="Quantity")
    unit_type: str = Field(alias="UnitType")
    price: float = Field(alias="Price")
    kdv_percent: float = Field(alias="KDVPercent")
    kdv_total: float = Field(alias="KDVTotal")
    taxes: list[NilveraTax] = Field(default_factory=list, alias="Taxes")
    discount_total: float = Field(default=0.0, alias="DiscountTotal")
    allowance_total: float = Field(default=0.0, alias="AllowanceTotal")


class NilveraCompanyInfo(BaseModel):
    """Represents the sender (Supplier) company info."""

    model_config = ConfigDict(populate_by_name=True)
    tax_number: str = Field(alias="TaxNumber")
    name: str = Field(alias="Name")
    tax_office: str = Field(default="", alias="TaxOffice")


class NilveraCustomerInfo(BaseModel):
    """Represents the receiver (Customer) info."""

    model_config = ConfigDict(populate_by_name=True)
    tax_number: str = Field(alias="TaxNumber")
    name: str = Field(alias="Name")
    tax_office: str = Field(default="", alias="TaxOffice")
    country: str = Field(default="Türkiye", alias="Country")
    city: str = Field(default="Istanbul", alias="City")  # Often mandatory in e-Invoice schemas
    address: str = Field(alias="Address")


class NilveraInvoiceInfo(BaseModel):
    """Represents the metadata and totals of the invoice."""

    model_config = ConfigDict(populate_by_name=True)
    uuid: str = Field(alias="UUID")
    template_uuid: str = Field(default="", alias="TemplateUUID")
    invoice_type: str = Field(default="SATIS", alias="InvoiceType")
    invoice_profile: str = Field(alias="InvoiceProfile")  # EARSIVFATURA, TICARIFATURA, TEMELFATURA
    invoice_series_or_number: str = Field(alias="InvoiceSeriesOrNumber")  # e.g., 'SYR'
    issue_date: str = Field(alias="IssueDate")  # Format: "YYYY-MM-DDTHH:MM:SS"
    currency_code: str = Field(default="TRY", alias="CurrencyCode")
    exchange_rate: float = Field(default=1.0, alias="ExchangeRate")
    line_extension_amount: float = Field(alias="LineExtensionAmount")
    general_kdv_total: float = Field(alias="GeneralKDVTotal")
    general_allowance_total: float = Field(default=0.0, alias="GeneralAllowanceTotal")
    general_taxes_total: float = Field(default=0.0, alias="GeneralTaxesTotal")
    payable_amount: float = Field(alias="PayableAmount")


class NilveraInvoicePayload(BaseModel):
    """Root payload for sending Draft E-Invoices and E-Archives to Nilvera."""

    model_config = ConfigDict(populate_by_name=True)
    invoice_info: NilveraInvoiceInfo = Field(alias="InvoiceInfo")
    company_info: NilveraCompanyInfo = Field(alias="CompanyInfo")
    customer_info: NilveraCustomerInfo = Field(alias="CustomerInfo")
    invoice_lines: list[NilveraInvoiceLine] = Field(alias="InvoiceLines")
