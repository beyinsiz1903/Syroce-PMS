from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.integrations.incoming_invoice_sync_service import IncomingInvoiceSyncService
from core.integrations.nilvera.errors import NilveraValidationError
from core.integrations.nilvera.incoming_mapper import (
    IncomingInvoiceDetail,
    IncomingInvoiceStatus,
    IncomingInvoiceSummary,
)
from core.integrations.nilvera.incoming_xml_mapper import (
    IncomingInvoiceXml,
    IncomingInvoiceXmlLine,
)
from models.schemas.incoming_invoice import (
    IncomingInvoiceAnswerStatus,
    IncomingInvoiceProviderStatus,
)

PROVIDER_UUID = "123e4567-e89b-12d3-a456-426614174000"
ISSUE_DATE = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def _sources(*, status_code: str = "succeed", answer_code: str | None = "approved"):
    summary = IncomingInvoiceSummary(
        provider_uuid=PROVIDER_UUID,
        invoice_number="TEST2026000000001",
        issue_date=ISSUE_DATE,
        provider_issue_date_raw="2026-08-01T12:00:00Z",
        timezone_assumed=False,
        payable_amount=Decimal("120.00"),
        currency="TRY",
        status_code=status_code,
        answer_code=answer_code,
        supplier_tax_number=None,
        supplier_name=None,
    )
    detail = IncomingInvoiceDetail(
        provider_uuid=PROVIDER_UUID,
        invoice_type="SATIS",
        invoice_profile="TICARIFATURA",
        invoice_number="TEST2026000000001",
        issue_date=ISSUE_DATE,
        issue_date_timezone_assumed=False,
        currency="TRY",
        number_of_items=1,
        invoice_amount=Decimal("120.00"),
        tax_amount=Decimal("20.00"),
        answer_code=answer_code,
    )
    status = IncomingInvoiceStatus(
        invoice_profile="TICARIFATURA",
        issue_date=ISSUE_DATE,
        issue_date_timezone_assumed=False,
        answer_code=answer_code,
        status_code=status_code,
        gib_code="1200",
    )
    xml_invoice = IncomingInvoiceXml(
        provider_uuid=PROVIDER_UUID,
        invoice_number="TEST2026000000001",
        supplier_tax_number="1234567890",
        supplier_name="Test Supplier",
        lines=(
            IncomingInvoiceXmlLine(
                provider_line_id="1",
                line_number=1,
                name="Service",
                quantity=Decimal("1"),
                unit_code="C62",
                unit_price=Decimal("100.00"),
                discount_amount=Decimal("0"),
                line_extension_amount=Decimal("100.00"),
                kdv_rate=Decimal("20"),
                kdv_amount=Decimal("20.00"),
                other_taxes=(),
                currency="TRY",
            ),
        ),
    )
    return summary, detail, status, xml_invoice


def test_builds_deterministic_snapshot_and_maps_provider_state():
    invoice, lines = IncomingInvoiceSyncService._build_snapshot("tenant-1", *_sources())
    duplicate, duplicate_lines = IncomingInvoiceSyncService._build_snapshot("tenant-1", *_sources())

    assert invoice.id == duplicate.id
    assert lines[0].id == duplicate_lines[0].id
    assert invoice.answer_status == IncomingInvoiceAnswerStatus.APPROVED
    assert invoice.provider_status == IncomingInvoiceProviderStatus.SUCCEED
    assert invoice.payable_amount == Decimal("120.00")
    assert invoice.issue_date == ISSUE_DATE
    assert invoice.issue_date_timezone_assumed is False
    assert lines[0].incoming_invoice_id == invoice.id


def test_pending_status_is_preserved_as_waiting_not_success():
    invoice, _ = IncomingInvoiceSyncService._build_snapshot(
        "tenant-1",
        *_sources(status_code="waiting", answer_code="waitingForApproval"),
    )
    assert invoice.provider_status == IncomingInvoiceProviderStatus.WAITING
    assert invoice.provider_status != IncomingInvoiceProviderStatus.SUCCEED
    assert invoice.answer_status == IncomingInvoiceAnswerStatus.PENDING


def test_provider_error_is_preserved_as_error_not_success():
    invoice, _ = IncomingInvoiceSyncService._build_snapshot(
        "tenant-1",
        *_sources(status_code="error", answer_code="unknown"),
    )
    assert invoice.provider_status == IncomingInvoiceProviderStatus.ERROR
    assert invoice.provider_status != IncomingInvoiceProviderStatus.SUCCEED


def test_rejects_unknown_provider_status_without_exposing_value():
    sensitive_status = "private-provider-state"
    with pytest.raises(NilveraValidationError) as exc_info:
        IncomingInvoiceSyncService._build_snapshot(
            "tenant-1",
            *_sources(status_code=sensitive_status),
        )
    assert sensitive_status not in str(exc_info.value)


def test_rejects_line_count_mismatch():
    summary, detail, status, xml_invoice = _sources()
    mismatched_detail = IncomingInvoiceDetail(**{**detail.__dict__, "number_of_items": 2})
    with pytest.raises(NilveraValidationError, match="line count"):
        IncomingInvoiceSyncService._build_snapshot("tenant-1", summary, mismatched_detail, status, xml_invoice)
