from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.integrations.nilvera.errors import NilveraValidationError


@dataclass(frozen=True)
class IncomingInvoiceSummary:
    provider_uuid: str
    invoice_number: str
    issue_date: datetime
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
    @classmethod
    def map_page(cls, payload: dict, page: int, page_size: int) -> IncomingInvoicePage:
        """
        Parses a JSON response from GET /einvoice/Purchase into IncomingInvoicePage.
        Fails closed on missing mandatory fields, and strips PII from error messages.
        """
        if not isinstance(payload, dict):
            raise NilveraValidationError("Payload is not a JSON object")

        # Fallback to standard pagination metadata if strictly typed
        total_count = payload.get("TotalCount") or payload.get("Total") or 0
        total_pages = payload.get("TotalPages") or 0

        data_list = payload.get("Data", [])
        if not isinstance(data_list, list):
            raise NilveraValidationError("'Data' field is not a list in incoming invoices response")

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
        uuid = item.get("UUID") or item.get("Id")
        if not uuid:
            raise NilveraValidationError("Incoming invoice is missing UUID")

        invoice_number = item.get("InvoiceNumber")
        if not invoice_number:
            raise NilveraValidationError("Incoming invoice is missing InvoiceNumber")

        raw_issue_date = item.get("IssueDate")
        if not raw_issue_date:
            raise NilveraValidationError("Incoming invoice is missing IssueDate")

        try:
            # Nilvera typically uses ISO8601 with or without microseconds/Z
            # Example: 2026-08-01T12:00:00.000Z or similar.
            if raw_issue_date.endswith("Z"):
                raw_issue_date = raw_issue_date.replace("Z", "+00:00")
            issue_date = datetime.fromisoformat(raw_issue_date)
        except ValueError as e:
            raise NilveraValidationError("Incoming invoice has invalid IssueDate format") from e

        raw_amount = item.get("PayableAmount")
        if raw_amount is None:
            raise NilveraValidationError("Incoming invoice is missing PayableAmount")

        try:
            payable_amount = Decimal(str(raw_amount))
        except Exception as e:
            raise NilveraValidationError("Incoming invoice has invalid PayableAmount format") from e

        currency = item.get("Currency")
        if not currency:
            raise NilveraValidationError("Incoming invoice is missing Currency")

        return IncomingInvoiceSummary(
            provider_uuid=str(uuid),
            invoice_number=str(invoice_number),
            issue_date=issue_date,
            payable_amount=payable_amount,
            currency=str(currency),
            status_code=str(item.get("StatusCode")) if item.get("StatusCode") else None,
            answer_code=str(item.get("AnswerCode")) if item.get("AnswerCode") else None,
            supplier_tax_number=str(item.get("SenderTaxNumber")) if item.get("SenderTaxNumber") else None,
            supplier_name=str(item.get("SenderName")) if item.get("SenderName") else None,
        )
