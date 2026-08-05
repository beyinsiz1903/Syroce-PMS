import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
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


@dataclass(frozen=True)
class IncomingInvoiceDetail:
    provider_uuid: str
    invoice_type: str
    invoice_profile: str
    invoice_number: str
    issue_date: datetime
    issue_date_timezone_assumed: bool
    send_date: datetime | None
    currency: str
    number_of_items: int
    invoice_amount: Decimal
    tax_amount: Decimal
    answer_code: str | None


@dataclass(frozen=True)
class IncomingInvoiceStatus:
    invoice_profile: str
    issue_date: datetime
    issue_date_timezone_assumed: bool
    answer_code: str
    status_code: str
    gib_code: str | None
    envelope_created_date: datetime | None


class NilveraIncomingMapper:
    _ISTANBUL = ZoneInfo("Europe/Istanbul")

    @staticmethod
    def _require_object(payload: dict, field_name: str) -> dict:
        value = payload.get(field_name)
        if not isinstance(value, dict):
            raise NilveraValidationError(f"Incoming invoice response has invalid {field_name}")
        return value

    @staticmethod
    def _require_string(payload: dict, field_name: str) -> str:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise NilveraValidationError(f"Incoming invoice response has invalid {field_name}")
        return value

    @classmethod
    def _parse_uuid(cls, payload: dict, field_name: str) -> str:
        raw_value = cls._require_string(payload, field_name)
        try:
            return str(uuid.UUID(raw_value))
        except ValueError:
            raise NilveraValidationError(f"Incoming invoice response has invalid {field_name}") from None

    @staticmethod
    def _parse_decimal(payload: dict, field_name: str) -> Decimal:
        raw_value = payload.get(field_name)
        try:
            value = Decimal(str(raw_value))
        except Exception:
            raise NilveraValidationError(f"Incoming invoice response has invalid {field_name}") from None

        if raw_value is None or not value.is_finite() or value < 0:
            raise NilveraValidationError(f"Incoming invoice response has invalid {field_name}")
        return value

    @classmethod
    def _parse_datetime(
        cls,
        payload: dict,
        field_name: str,
        *,
        required: bool = True,
        assume_istanbul_for_naive_issue_date: bool = False,
    ) -> tuple[datetime | None, bool]:
        raw_value: Any = payload.get(field_name)
        if raw_value is None and not required:
            return None, False
        if not required and isinstance(raw_value, str) and not raw_value.strip():
            return None, False
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise NilveraValidationError(f"Incoming invoice response has invalid {field_name}")

        normalized = f"{raw_value[:-1]}+00:00" if raw_value.endswith("Z") else raw_value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            raise NilveraValidationError(f"Incoming invoice response has invalid {field_name}") from None

        if parsed.tzinfo is None:
            if assume_istanbul_for_naive_issue_date and field_name == "IssueDate":
                return parsed.replace(tzinfo=cls._ISTANBUL), True
            raise NilveraValidationError(f"Incoming invoice response has timezone-naive {field_name}")

        return parsed, False

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

    @classmethod
    def map_detail(cls, payload: dict) -> IncomingInvoiceDetail:
        """Map the documented GET /Purchase/{UUID}/Details response."""
        if not isinstance(payload, dict):
            raise NilveraValidationError("Incoming invoice detail is not a JSON object")

        issue_date, issue_date_assumed = cls._parse_datetime(
            payload,
            "IssueDate",
            assume_istanbul_for_naive_issue_date=True,
        )
        send_date, _ = cls._parse_datetime(payload, "SendDate", required=False)

        return IncomingInvoiceDetail(
            provider_uuid=cls._parse_uuid(payload, "UUID"),
            invoice_type=cls._require_string(payload, "InvoiceType"),
            invoice_profile=cls._require_string(payload, "InvoiceProfile"),
            invoice_number=cls._require_string(payload, "InvoiceNumber"),
            issue_date=issue_date,
            issue_date_timezone_assumed=issue_date_assumed,
            send_date=send_date,
            currency=cls._require_string(payload, "CurrencyCode"),
            number_of_items=cls._parse_non_negative_int(payload, "NumberOfItems"),
            invoice_amount=cls._parse_decimal(payload, "InvoiceAmount"),
            tax_amount=cls._parse_decimal(payload, "TaxAmount"),
            answer_code=(str(payload["AnswerCode"]) if payload.get("AnswerCode") is not None else None),
        )

    @classmethod
    def map_status(cls, payload: dict) -> IncomingInvoiceStatus:
        """Map the documented GET /Purchase/{UUID}/Status response."""
        if not isinstance(payload, dict):
            raise NilveraValidationError("Incoming invoice status is not a JSON object")

        answer = cls._require_object(payload, "Answer")
        invoice_status = cls._require_object(payload, "InvoiceStatus")
        envelope_info = cls._require_object(payload, "EnvelopeInfo")
        issue_date, issue_date_assumed = cls._parse_datetime(
            payload,
            "IssueDate",
            assume_istanbul_for_naive_issue_date=True,
        )
        envelope_created_date, _ = cls._parse_datetime(
            envelope_info,
            "CreatedDate",
            required=False,
        )

        gib_code = envelope_info.get("GIBCode")
        return IncomingInvoiceStatus(
            invoice_profile=cls._require_string(payload, "InvoiceProfile"),
            issue_date=issue_date,
            issue_date_timezone_assumed=issue_date_assumed,
            answer_code=cls._require_string(answer, "AnswerCode"),
            status_code=cls._require_string(invoice_status, "Code"),
            gib_code=str(gib_code) if gib_code is not None else None,
            envelope_created_date=envelope_created_date,
        )
