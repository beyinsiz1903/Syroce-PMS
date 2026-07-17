from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from models.schemas.incoming_invoice import IncomingInvoice, IncomingInvoiceAnswerStatus, IncomingInvoiceProfile
from models.schemas.invoice_sync import InvoiceProvider


def test_incoming_invoice_basic_profile():
    invoice = IncomingInvoice(
        id="test_inv_1",
        tenant_id="tenant_1",
        provider=InvoiceProvider.NILVERA,
        provider_uuid="11112222-3333-4444-5555-666677778888",
        invoice_number="ABC2023000000001",
        sender_vkn_tckn="11111111111",
        sender_title="Test Sender A.S.",
        profile=IncomingInvoiceProfile.BASIC,
        answer_status=IncomingInvoiceAnswerStatus.PENDING,
        issue_date=datetime.now(UTC),
        received_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC)
    )
    
    assert invoice.profile == IncomingInvoiceProfile.BASIC
    assert invoice.answer_status == IncomingInvoiceAnswerStatus.PENDING


def test_incoming_invoice_commercial_profile():
    invoice = IncomingInvoice(
        id="test_inv_2",
        tenant_id="tenant_1",
        provider=InvoiceProvider.NILVERA,
        provider_uuid="11112222-3333-4444-5555-666677778888",
        invoice_number="ABC2023000000002",
        sender_vkn_tckn="11111111111",
        sender_title="Test Sender A.S.",
        profile=IncomingInvoiceProfile.COMMERCIAL,
        answer_status=IncomingInvoiceAnswerStatus.PENDING,
        issue_date=datetime.now(UTC),
        received_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC)
    )
    
    assert invoice.profile == IncomingInvoiceProfile.COMMERCIAL
    assert invoice.answer_status == IncomingInvoiceAnswerStatus.PENDING
