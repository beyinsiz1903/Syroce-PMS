from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.integrations.nilvera.errors import NilveraValidationError
from core.integrations.nilvera.incoming_mapper import NilveraIncomingMapper


def test_map_page_success():
    payload = {
        "TotalCount": 1,
        "TotalPages": 1,
        "Data": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": 100.50,
                "Currency": "TRY",
                "StatusCode": "PENDING",
                "AnswerCode": "NONE",
                "SenderTaxNumber": "1234567890",
                "SenderName": "Test Supplier",
                "UnknownExtraField": "Should be ignored",
            }
        ],
    }

    page = NilveraIncomingMapper.map_page(payload, page=1, page_size=100)

    assert page.total_count == 1
    assert page.total_pages == 1
    assert page.page == 1
    assert page.page_size == 100
    assert len(page.items) == 1

    item = page.items[0]
    assert item.provider_uuid == "123e4567-e89b-12d3-a456-426614174000"
    assert item.invoice_number == "ABC2023000000001"
    assert item.issue_date == datetime(2023, 10, 1, 12, 0, 0, tzinfo=UTC)
    assert item.payable_amount == Decimal("100.5")
    assert item.currency == "TRY"
    assert item.status_code == "PENDING"
    assert item.answer_code == "NONE"
    assert item.supplier_tax_number == "1234567890"
    assert item.supplier_name == "Test Supplier"


def test_map_page_fails_on_missing_uuid():
    payload = {
        "Data": [
            {
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": 100.50,
                "Currency": "TRY",
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="missing UUID"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_fails_on_missing_invoice_number():
    payload = {
        "Data": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": 100.50,
                "Currency": "TRY",
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="missing InvoiceNumber"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_fails_on_invalid_amount():
    payload = {
        "Data": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": "invalid-amount",
                "Currency": "TRY",
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="invalid PayableAmount format"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_fails_on_missing_currency():
    payload = {
        "Data": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": 100.50,
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="missing Currency"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_strips_pii_from_errors():
    """Ensure error messages do not leak PII like names or exact amounts."""
    payload = {
        "Data": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "INVALID-DATE",
                "PayableAmount": 1000000.50,
                "Currency": "TRY",
                "SenderName": "SECRET PII NAME",
                "SenderTaxNumber": "9999999999",
            }
        ]
    }
    with pytest.raises(NilveraValidationError) as exc:
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)

    err_str = str(exc.value)
    assert "SECRET PII NAME" not in err_str
    assert "9999999999" not in err_str
    assert "1000000.50" not in err_str
    assert "invalid IssueDate" in err_str


def test_map_page_fails_on_invalid_uuid_format():
    payload = {
        "Data": [
            {
                "UUID": "invalid-uuid",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": 100.50,
                "Currency": "TRY",
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="invalid UUID format"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_fails_on_negative_amount():
    payload = {
        "Data": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": -100.50,
                "Currency": "TRY",
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="invalid PayableAmount"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_fails_on_infinite_amount():
    payload = {
        "Data": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": "Infinity",
                "Currency": "TRY",
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="invalid PayableAmount format"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_handles_invalid_pagination_metadata():
    payload = {"TotalCount": "invalid", "TotalPages": -5, "Data": []}
    page = NilveraIncomingMapper.map_page(payload, page=1, page_size=100)
    assert page.total_count == 0
    assert page.total_pages == 0
