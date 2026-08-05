from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.integrations.nilvera.errors import NilveraValidationError
from core.integrations.nilvera.incoming_mapper import NilveraIncomingMapper


def test_map_page_success():
    payload = {
        "TotalCount": 1,
        "TotalPages": 1,
        "Content": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": 100.50,
                "CurrencyCode": "TRY",
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
        "Content": [
            {
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": 100.50,
                "CurrencyCode": "TRY",
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="missing UUID"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_fails_on_missing_invoice_number():
    payload = {
        "Content": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": 100.50,
                "CurrencyCode": "TRY",
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="missing InvoiceNumber"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_fails_on_invalid_amount():
    payload = {
        "Content": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": "invalid-amount",
                "CurrencyCode": "TRY",
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="invalid PayableAmount format"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_fails_on_missing_currency():
    payload = {
        "Content": [
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
        "Content": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "INVALID-DATE",
                "PayableAmount": 1000000.50,
                "CurrencyCode": "TRY",
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
        "Content": [
            {
                "UUID": "invalid-uuid",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": 100.50,
                "CurrencyCode": "TRY",
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="invalid UUID format"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_fails_on_negative_amount():
    payload = {
        "Content": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": -100.50,
                "CurrencyCode": "TRY",
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="invalid PayableAmount"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_fails_on_infinite_amount():
    payload = {
        "Content": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00.000Z",
                "PayableAmount": "Infinity",
                "CurrencyCode": "TRY",
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="invalid PayableAmount format"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_handles_invalid_pagination_metadata():
    payload = {"TotalCount": "invalid", "TotalPages": -5, "Content": []}
    with pytest.raises(NilveraValidationError, match="invalid TotalCount"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_fails_on_negative_total_pages():
    payload = {"TotalCount": 10, "TotalPages": -5, "Content": []}
    with pytest.raises(NilveraValidationError, match="invalid TotalPages"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_fails_on_non_string_issue_date():
    payload = {
        "Content": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": 1234567890,
                "PayableAmount": 100.50,
                "CurrencyCode": "TRY",
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="invalid IssueDate format"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_naive_issue_date_is_assumed_europe_istanbul():
    payload = {
        "TotalCount": 1,
        "TotalPages": 1,
        "Content": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00",
                "PayableAmount": 100.50,
                "CurrencyCode": "TRY",
            }
        ],
    }
    page = NilveraIncomingMapper.map_page(payload, page=1, page_size=100)
    assert len(page.items) == 1
    item = page.items[0]
    assert item.issue_date.tzinfo is not None
    assert str(item.issue_date.tzinfo) == "Europe/Istanbul"
    assert item.timezone_assumed is True
    assert item.provider_issue_date_raw == "2023-10-01T12:00:00"


def test_offset_issue_date_preserves_provider_offset():
    payload = {
        "TotalCount": 1,
        "TotalPages": 1,
        "Content": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00+02:00",
                "PayableAmount": 100.50,
                "CurrencyCode": "TRY",
            }
        ],
    }
    page = NilveraIncomingMapper.map_page(payload, page=1, page_size=100)
    item = page.items[0]
    assert item.issue_date.tzinfo is not None
    assert item.timezone_assumed is False
    assert item.provider_issue_date_raw == "2023-10-01T12:00:00+02:00"


def test_utc_issue_date_preserves_utc():
    payload = {
        "TotalCount": 1,
        "TotalPages": 1,
        "Content": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "2023-10-01T12:00:00Z",
                "PayableAmount": 100.50,
                "CurrencyCode": "TRY",
            }
        ],
    }
    page = NilveraIncomingMapper.map_page(payload, page=1, page_size=100)
    item = page.items[0]
    assert item.issue_date.tzinfo is not None
    assert item.timezone_assumed is False
    assert item.provider_issue_date_raw == "2023-10-01T12:00:00Z"


def test_invalid_issue_date_still_fails():
    payload = {
        "Content": [
            {
                "UUID": "123e4567-e89b-12d3-a456-426614174000",
                "InvoiceNumber": "ABC2023000000001",
                "IssueDate": "invalid-date",
                "PayableAmount": 100.50,
                "CurrencyCode": "TRY",
            }
        ]
    }
    with pytest.raises(NilveraValidationError, match="invalid IssueDate format"):
        NilveraIncomingMapper.map_page(payload, page=1, page_size=100)


def test_map_page_fails_when_data_is_missing():
    with pytest.raises(NilveraValidationError, match="missing Content"):
        NilveraIncomingMapper.map_page(
            {"TotalCount": 0, "TotalPages": 0},
            page=1,
            page_size=100,
        )


def _incoming_detail_payload() -> dict:
    return {
        "UUID": "123e4567-e89b-12d3-a456-426614174000",
        "InvoiceType": "SATIS",
        "InvoiceProfile": "TICARIFATURA",
        "InvoiceNumber": "TEST-INVOICE",
        "SendDate": "2023-10-01T12:05:00Z",
        "IssueDate": "2023-10-01T12:00:00Z",
        "CurrencyCode": "TRY",
        "NumberOfItems": 2,
        "InvoiceAmount": "120.00",
        "TaxAmount": "20.00",
        "AnswerCode": "unknown",
    }


def _incoming_status_payload() -> dict:
    return {
        "InvoiceProfile": "TICARIFATURA",
        "IssueDate": "2023-10-01T12:00:00Z",
        "Answer": {"AnswerCode": "unknown"},
        "InvoiceStatus": {"Code": "Success"},
        "EnvelopeInfo": {
            "GIBCode": 1200,
            "CreatedDate": "2023-10-01T12:06:00Z",
        },
    }


def test_map_incoming_detail_contract():
    detail = NilveraIncomingMapper.map_detail(_incoming_detail_payload())

    assert detail.provider_uuid == "123e4567-e89b-12d3-a456-426614174000"
    assert detail.invoice_profile == "TICARIFATURA"
    assert detail.issue_date == datetime(2023, 10, 1, 12, tzinfo=UTC)
    assert detail.issue_date_timezone_assumed is False
    assert detail.send_date == datetime(2023, 10, 1, 12, 5, tzinfo=UTC)
    assert detail.invoice_amount == Decimal("120.00")
    assert detail.tax_amount == Decimal("20.00")


def test_map_incoming_status_contract():
    status = NilveraIncomingMapper.map_status(_incoming_status_payload())

    assert status.invoice_profile == "TICARIFATURA"
    assert status.issue_date == datetime(2023, 10, 1, 12, tzinfo=UTC)
    assert status.answer_code == "unknown"
    assert status.status_code == "Success"
    assert status.gib_code == "1200"
    assert status.envelope_created_date == datetime(
        2023,
        10,
        1,
        12,
        6,
        tzinfo=UTC,
    )


@pytest.mark.parametrize("mapper_name", ["map_detail", "map_status"])
def test_only_issue_date_may_assume_europe_istanbul(mapper_name):
    payload = _incoming_detail_payload() if mapper_name == "map_detail" else _incoming_status_payload()
    payload["IssueDate"] = "2023-10-01T12:00:00"

    mapped = getattr(NilveraIncomingMapper, mapper_name)(payload)

    assert mapped.issue_date_timezone_assumed is True
    assert str(mapped.issue_date.tzinfo) == "Europe/Istanbul"


def test_detail_rejects_naive_send_date_without_timezone_fallback():
    payload = _incoming_detail_payload()
    payload["SendDate"] = "2023-10-01T12:05:00"

    with pytest.raises(NilveraValidationError, match="timezone-naive SendDate"):
        NilveraIncomingMapper.map_detail(payload)


def test_status_rejects_naive_envelope_date_without_timezone_fallback():
    payload = _incoming_status_payload()
    payload["EnvelopeInfo"]["CreatedDate"] = "2023-10-01T12:06:00"

    with pytest.raises(
        NilveraValidationError,
        match="timezone-naive CreatedDate",
    ):
        NilveraIncomingMapper.map_status(payload)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("UUID", "not-a-uuid"),
        ("NumberOfItems", -1),
        ("InvoiceAmount", "Infinity"),
        ("TaxAmount", -1),
    ],
)
def test_detail_rejects_invalid_contract_fields_without_echoing_values(
    field_name,
    invalid_value,
):
    payload = _incoming_detail_payload()
    payload[field_name] = invalid_value

    with pytest.raises(NilveraValidationError) as exc_info:
        NilveraIncomingMapper.map_detail(payload)

    assert str(invalid_value) not in str(exc_info.value)
    assert field_name in str(exc_info.value)


@pytest.mark.parametrize("missing_object", ["Answer", "InvoiceStatus", "EnvelopeInfo"])
def test_status_requires_documented_nested_objects(missing_object):
    payload = _incoming_status_payload()
    payload.pop(missing_object)

    with pytest.raises(NilveraValidationError, match=f"invalid {missing_object}"):
        NilveraIncomingMapper.map_status(payload)
