import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from core.integrations.nilvera.errors import NilveraValidationError


@dataclass(frozen=True)
class IncomingInvoiceSummary:
    provider_uuid: str
    invoice_number: str
    issue_date: datetime
    provider_issue_date_raw: str
    timezone_assumed: bool
    payable_amount: Decimal
    currency: str
    status_code: str | None
    answer_code: str | None
    supplier_tax_number: str | None
    supplier_name: str | None


@dataclass(frozen=True)
class IncomingInvoicePage:
    items: tuple[IncomingInvoiceSummary, ...]
    page: int
    page_size: int
    total_count: int
    total_pages: int


class NilveraIncomingMapper:
    @staticmethod
    def _parse_non_negative_int(
        payload: dict,
        field_name: str,
        *,
        default: int | None = None,
    ) -> int:
        raw_value = payload.get(field_name)

        if raw_value is None:
            if default is not None:
                return default
            raise NilveraValidationError(f"Incoming invoice response is missing {field_name}")

        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            raise NilveraValidationError(f"Incoming invoice response has invalid {field_name}") from None

        if value < 0:
            raise NilveraValidationError(f"Incoming invoice response has invalid {field_name}")

        return value

    @classmethod
    def map_page(cls, payload: dict, page: int, page_size: int) -> IncomingInvoicePage:
        """
        Parses a JSON response from GET /einvoice/Purchase into IncomingInvoicePage.
        Fails closed on missing mandatory fields, and strips PII from error messages.
        """
        if not isinstance(payload, dict):
            raise NilveraValidationError("Payload is not a JSON object")

        # Fail closed on invalid pagination metadata
        # Sandbox might use TotalCount or Total
        total_count = None
        if "TotalCount" in payload:
            total_count = cls._parse_non_negative_int(payload, "TotalCount")
        elif "Total" in payload:
            total_count = cls._parse_non_negative_int(payload, "Total")
        else:
            total_count = 0

        total_pages = cls._parse_non_negative_int(payload, "TotalPages", default=0)

        if "Content" not in payload:
            raise NilveraValidationError("Incoming invoice response is missing Content")

        data_list = payload["Content"]
        if not isinstance(data_list, list):
            raise NilveraValidationError("'Content' field is not a list in incoming invoices response")

        items = []
        for index, item in enumerate(data_list):
            if not isinstance(item, dict):
                raise NilveraValidationError(f"Incoming invoice item at index {index} is not an object")
            items.append(cls._map_item(item))

        return IncomingInvoicePage(
            items=tuple(items),
            page=page,
            page_size=page_size,
            total_count=total_count,
            total_pages=total_pages,
        )

    @classmethod
    def _map_item(cls, item: dict) -> IncomingInvoiceSummary:
        uuid_str = item.get("UUID") or item.get("Id")
        if not uuid_str:
            raise NilveraValidationError("Incoming invoice is missing UUID")

        try:
            parsed_uuid = uuid.UUID(str(uuid_str))
            provider_uuid = str(parsed_uuid)
        except (ValueError, TypeError, AttributeError):
            raise NilveraValidationError("Incoming invoice has invalid UUID format") from None

        invoice_number = item.get("InvoiceNumber")
        if not invoice_number:
            raise NilveraValidationError("Incoming invoice is missing InvoiceNumber")

        raw_issue_date = item.get("IssueDate")
        if not raw_issue_date:
            raise NilveraValidationError("Incoming invoice is missing IssueDate")

        if not isinstance(raw_issue_date, str):
            raise NilveraValidationError("Incoming invoice has invalid IssueDate format")

        try:
            # Nilvera typically uses ISO8601 with or without microseconds/Z
            # Example: 2026-08-01T12:00:00.000Z or similar.
            if raw_issue_date.endswith("Z"):
                issue_date_str = raw_issue_date.replace("Z", "+00:00")
            else:
                issue_date_str = raw_issue_date

            issue_date = datetime.fromisoformat(issue_date_str)
            timezone_assumed = False

            if issue_date.tzinfo is None:
                issue_date = issue_date.replace(tzinfo=ZoneInfo("Europe/Istanbul"))
                timezone_assumed = True
        except ValueError as e:
            raise NilveraValidationError("Incoming invoice has invalid IssueDate format") from e

        raw_amount = item.get("PayableAmount")
        if raw_amount is None:
            raise NilveraValidationError("Incoming invoice is missing PayableAmount")

        try:
            payable_amount = Decimal(str(raw_amount))
            if not payable_amount.is_finite():
                raise NilveraValidationError("Incoming invoice has invalid PayableAmount format")
            if payable_amount < 0:
                raise NilveraValidationError("Incoming invoice has invalid PayableAmount")
        except Exception as e:
            if isinstance(e, NilveraValidationError):
                raise
            raise NilveraValidationError("Incoming invoice has invalid PayableAmount format") from e

        currency = item.get("CurrencyCode") or item.get("Currency")
        if not currency:
            raise NilveraValidationError("Incoming invoice is missing Currency")

        return IncomingInvoiceSummary(
            provider_uuid=provider_uuid,
            invoice_number=str(invoice_number),
            issue_date=issue_date,
            provider_issue_date_raw=raw_issue_date,
            timezone_assumed=timezone_assumed,
            payable_amount=payable_amount,
            currency=str(currency),
            status_code=str(item.get("StatusCode")) if item.get("StatusCode") else None,
            answer_code=str(item.get("AnswerCode")) if item.get("AnswerCode") else None,
            supplier_tax_number=str(item.get("SenderTaxNumber")) if item.get("SenderTaxNumber") else None,
            supplier_name=str(item.get("SenderName")) if item.get("SenderName") else None,
        )
