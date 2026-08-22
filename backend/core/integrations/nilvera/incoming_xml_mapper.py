import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from core.integrations.nilvera.errors import NilveraValidationError
from models.schemas.incoming_invoice import IncomingTaxDetail


@dataclass(frozen=True)
class IncomingInvoiceXmlLine:
    provider_line_id: str | None
    line_number: int
    name: str
    quantity: Decimal
    unit_code: str
    unit_price: Decimal
    discount_amount: Decimal
    line_extension_amount: Decimal
    kdv_rate: Decimal
    kdv_amount: Decimal
    other_taxes: tuple[IncomingTaxDetail, ...]
    currency: str


@dataclass(frozen=True)
class IncomingInvoiceXml:
    provider_uuid: str
    invoice_number: str
    supplier_tax_number: str
    supplier_name: str
    lines: tuple[IncomingInvoiceXmlLine, ...]
    exchange_rate: Decimal | None = None
    exchange_rate_source_currency: str | None = None
    exchange_rate_target_currency: str | None = None


class NilveraIncomingXmlMapper:
    _NS = {
        "inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    }

    @staticmethod
    def _text(parent, path: str, field_name: str, *, required: bool = True) -> str | None:
        element = parent.find(path, NilveraIncomingXmlMapper._NS)
        value = element.text.strip() if element is not None and element.text else ""
        if not value:
            if required:
                raise NilveraValidationError(f"Incoming invoice XML is missing {field_name}")
            return None
        return value

    @classmethod
    def _decimal(cls, parent, path: str, field_name: str, *, allow_negative: bool = False) -> Decimal:
        value = cls._optional_decimal(parent, path, field_name, allow_negative=allow_negative)
        if value is None:
            raise NilveraValidationError(f"Incoming invoice XML is missing {field_name}")
        return value

    @classmethod
    def _optional_decimal(
        cls,
        parent,
        path: str,
        field_name: str,
        *,
        allow_negative: bool = False,
    ) -> Decimal | None:
        raw = cls._text(parent, path, field_name, required=False)
        if raw is None:
            return None
        try:
            value = Decimal(raw)
        except (InvalidOperation, TypeError):
            lexical_form = cls._decimal_lexical_form(raw)
            raise NilveraValidationError(f"Incoming invoice XML has invalid {field_name} (lexical_form={lexical_form})") from None
        if not value.is_finite():
            raise NilveraValidationError(f"Incoming invoice XML has invalid {field_name} (numeric_form=non_finite)")
        if value < 0 and not allow_negative:
            raise NilveraValidationError(f"Incoming invoice XML has invalid {field_name} (numeric_form=negative)")
        return value

    @staticmethod
    def _decimal_lexical_form(raw: str) -> str:
        if "," in raw and "." in raw:
            return "mixed_separators"
        if "," in raw:
            return "comma_separator"
        if any(character.isspace() for character in raw):
            return "embedded_whitespace"
        return "non_decimal"

    @classmethod
    def _currency(cls, parent, path: str, field_name: str) -> str:
        element = parent.find(path, cls._NS)
        currency = element.attrib.get("currencyID", "").strip() if element is not None else ""
        if not currency:
            raise NilveraValidationError(f"Incoming invoice XML is missing {field_name} currency")
        return currency

    @classmethod
    def map_document(cls, content: bytes) -> IncomingInvoiceXml:
        if not content:
            raise NilveraValidationError("Incoming invoice XML is empty")
        try:
            root = ET.fromstring(content)
        except (ET.ParseError, DefusedXmlException):
            raise NilveraValidationError("Incoming invoice XML cannot be parsed") from None

        expected_root = f"{{{cls._NS['inv']}}}Invoice"
        if root.tag != expected_root:
            raise NilveraValidationError("Incoming invoice XML has an unexpected root")

        raw_uuid = cls._text(root, "cbc:UUID", "UUID")
        try:
            provider_uuid = str(uuid.UUID(raw_uuid))
        except (TypeError, ValueError):
            raise NilveraValidationError("Incoming invoice XML has invalid UUID") from None

        invoice_number = cls._text(root, "cbc:ID", "invoice number")
        supplier_tax_number = cls._supplier_tax_identity(root)
        supplier_name = cls._text(
            root,
            "cac:AccountingSupplierParty/cac:Party/cac:PartyName/cbc:Name",
            "supplier name",
            required=False,
        )
        if supplier_name is None:
            supplier_name = cls._text(
                root,
                "cac:AccountingSupplierParty/cac:Party/cac:PartyLegalEntity/cbc:RegistrationName",
                "supplier name",
                required=False,
            )
        if supplier_name is None:
            first_name = cls._text(
                root,
                "cac:AccountingSupplierParty/cac:Party/cac:Person/cbc:FirstName",
                "supplier first name",
                required=False,
            )
            family_name = cls._text(
                root,
                "cac:AccountingSupplierParty/cac:Party/cac:Person/cbc:FamilyName",
                "supplier family name",
                required=False,
            )
            supplier_name = " ".join(part for part in (first_name, family_name) if part)
            if not supplier_name:
                raise NilveraValidationError("Incoming invoice XML is missing supplier name")

        line_elements = root.findall("cac:InvoiceLine", cls._NS)
        if not line_elements:
            raise NilveraValidationError("Incoming invoice XML has no invoice lines")

        lines = tuple(cls._map_line(element, index) for index, element in enumerate(line_elements, start=1))
        exchange_path = "cac:PricingExchangeRate"
        exchange_rate = cls._optional_decimal(root, f"{exchange_path}/cbc:CalculationRate", "pricing exchange rate")
        if exchange_rate is None:
            exchange_path = "cac:PaymentExchangeRate"
            exchange_rate = cls._optional_decimal(root, f"{exchange_path}/cbc:CalculationRate", "payment exchange rate")
        exchange_rate_source_currency = None
        exchange_rate_target_currency = None
        if exchange_rate is not None:
            exchange_rate_source_currency = cls._text(
                root,
                f"{exchange_path}/cbc:SourceCurrencyCode",
                "exchange-rate source currency",
            )
            exchange_rate_target_currency = cls._text(
                root,
                f"{exchange_path}/cbc:TargetCurrencyCode",
                "exchange-rate target currency",
            )
        return IncomingInvoiceXml(
            provider_uuid=provider_uuid,
            invoice_number=invoice_number,
            supplier_tax_number=supplier_tax_number,
            supplier_name=supplier_name,
            lines=lines,
            exchange_rate=exchange_rate,
            exchange_rate_source_currency=exchange_rate_source_currency,
            exchange_rate_target_currency=exchange_rate_target_currency,
        )

    @classmethod
    def _supplier_tax_identity(cls, root) -> str:
        identity_elements = root.findall(
            "cac:AccountingSupplierParty/cac:Party/cac:PartyIdentification/cbc:ID",
            cls._NS,
        )
        fallback = None
        for element in identity_elements:
            value = element.text.strip() if element.text else ""
            if not value:
                continue
            scheme = element.attrib.get("schemeID", "").strip().upper()
            if scheme in {"VKN", "TCKN"}:
                fallback = value
                break
            if fallback is None and value.isdigit() and len(value) in {10, 11}:
                fallback = value
        if fallback is None or not fallback.isdigit() or len(fallback) not in {10, 11}:
            raise NilveraValidationError("Incoming invoice XML has invalid supplier tax identity")
        return fallback

    @classmethod
    def _map_line(cls, element, line_number: int) -> IncomingInvoiceXmlLine:
        provider_line_id = cls._text(element, "cbc:ID", "line ID", required=False)
        quantity_element = element.find("cbc:InvoicedQuantity", cls._NS)
        quantity = cls._decimal(element, "cbc:InvoicedQuantity", "quantity")
        if quantity == 0:
            raise NilveraValidationError("Incoming invoice XML has invalid quantity")
        unit_code = quantity_element.attrib.get("unitCode", "").strip() if quantity_element is not None else ""
        if not unit_code:
            raise NilveraValidationError("Incoming invoice XML is missing unit code")

        line_extension_amount = cls._decimal(element, "cbc:LineExtensionAmount", "line extension amount")
        line_currency = cls._currency(element, "cbc:LineExtensionAmount", "line extension amount")
        unit_price = cls._decimal(element, "cac:Price/cbc:PriceAmount", "unit price")
        price_currency = cls._currency(element, "cac:Price/cbc:PriceAmount", "unit price")
        if price_currency != line_currency:
            raise NilveraValidationError("Incoming invoice XML line currencies do not match")

        name = cls._text(element, "cac:Item/cbc:Name", "line name", required=False)
        if name is None:
            name = cls._text(element, "cac:Item/cbc:Description", "line name")

        discount_amount = Decimal("0")
        for allowance in element.findall("cac:AllowanceCharge", cls._NS):
            charge_indicator = cls._text(allowance, "cbc:ChargeIndicator", "charge indicator")
            if charge_indicator.lower() == "false":
                allowance_currency = cls._currency(allowance, "cbc:Amount", "allowance")
                if allowance_currency != line_currency:
                    raise NilveraValidationError("Incoming invoice XML allowance currency does not match")
                discount_amount += cls._decimal(allowance, "cbc:Amount", "allowance amount")
            elif charge_indicator.lower() != "true":
                raise NilveraValidationError("Incoming invoice XML has invalid charge indicator")

        kdv_rate = Decimal("0")
        kdv_amount = Decimal("0")
        other_taxes: list[IncomingTaxDetail] = []
        vat_rates: set[Decimal] = set()
        for subtotal in element.findall("cac:TaxTotal/cac:TaxSubtotal", cls._NS):
            tax_code = cls._text(subtotal, "cac:TaxCategory/cac:TaxScheme/cbc:TaxTypeCode", "tax code")
            tax_kind = "VAT" if tax_code == "0015" else "other"
            tax_amount = cls._decimal(
                subtotal,
                "cbc:TaxAmount",
                f"{tax_kind} tax amount",
                allow_negative=True,
            )
            tax_currency = cls._currency(subtotal, "cbc:TaxAmount", "tax amount")
            if tax_currency != line_currency:
                raise NilveraValidationError("Incoming invoice XML tax currency does not match")
            taxable_amount = cls._optional_decimal(subtotal, "cbc:TaxableAmount", "taxable amount")
            rate = cls._optional_decimal(
                subtotal,
                "cac:TaxCategory/cbc:Percent",
                "tax rate",
            )
            if rate is None:
                if tax_amount == 0:
                    rate = Decimal("0")
                elif taxable_amount is not None and taxable_amount > 0:
                    rate = (abs(tax_amount) * Decimal("100") / taxable_amount).quantize(Decimal("0.01"))
                else:
                    raise NilveraValidationError("Incoming invoice XML is missing tax rate")

            if tax_code == "0015":
                vat_rates.add(rate)
                kdv_rate = rate
                kdv_amount += tax_amount
                continue

            if taxable_amount is None:
                raise NilveraValidationError("Incoming invoice XML is missing taxable amount")
            tax_name = (
                cls._text(
                    subtotal,
                    "cac:TaxCategory/cac:TaxScheme/cbc:Name",
                    "tax name",
                    required=False,
                )
                or tax_code
            )
            exemption_code = cls._text(
                subtotal,
                "cac:TaxCategory/cbc:TaxExemptionReasonCode",
                "tax exemption code",
                required=False,
            )
            exemption_reason = cls._text(
                subtotal,
                "cac:TaxCategory/cbc:TaxExemptionReason",
                "tax exemption reason",
                required=False,
            )
            if bool(exemption_code) != bool(exemption_reason):
                exemption_code = exemption_reason = None
            other_taxes.append(
                IncomingTaxDetail(
                    tax_code=tax_code,
                    tax_name=tax_name,
                    rate=rate,
                    taxable_amount=taxable_amount,
                    amount=abs(tax_amount),
                    is_deduction=tax_amount < 0,
                    exemption_code=exemption_code,
                    exemption_reason=exemption_reason,
                )
            )

        if len(vat_rates) > 1:
            raise NilveraValidationError("Incoming invoice XML line has multiple VAT rates")

        return IncomingInvoiceXmlLine(
            provider_line_id=provider_line_id,
            line_number=line_number,
            name=name,
            quantity=quantity,
            unit_code=unit_code,
            unit_price=unit_price,
            discount_amount=discount_amount,
            line_extension_amount=line_extension_amount,
            kdv_rate=kdv_rate,
            kdv_amount=kdv_amount,
            other_taxes=tuple(other_taxes),
            currency=line_currency,
        )
