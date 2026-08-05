from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from core.integrations.nilvera.errors import NilveraValidationError
from core.integrations.nilvera.incoming import NilveraIncomingService


@pytest.fixture
def mock_http_client():
    client = AsyncMock()
    # Provide a simple valid mock response for happy paths
    client.get.return_value = {
        "TotalCount": 0,
        "TotalPages": 0,
        "Content": [],
    }
    return client


@pytest.fixture
def incoming_service(mock_http_client):
    return NilveraIncomingService(client=mock_http_client)


@pytest.mark.asyncio
async def test_fetch_incoming_invoices_success(incoming_service, mock_http_client):
    start = datetime(2023, 10, 1, tzinfo=UTC)
    end = datetime(2023, 10, 31, tzinfo=UTC)

    page = await incoming_service.fetch_incoming_invoices(start, end, page=2, page_size=50)

    assert page.total_count == 0
    assert page.page == 2
    assert page.page_size == 50

    mock_http_client.get.assert_called_once_with(
        "/einvoice/Purchase",
        params={
            "StartDate": "2023-10-01T00:00:00+00:00",
            "EndDate": "2023-10-31T00:00:00+00:00",
            "Page": "2",
            "PageSize": "50",
        },
    )


@pytest.mark.asyncio
async def test_fetch_incoming_invoices_fails_if_start_date_naive(incoming_service):
    start = datetime(2023, 10, 1)  # naive
    end = datetime(2023, 10, 31, tzinfo=UTC)
    with pytest.raises(NilveraValidationError, match="timezone-aware"):
        await incoming_service.fetch_incoming_invoices(start, end)


@pytest.mark.asyncio
async def test_fetch_incoming_invoices_fails_if_start_after_end(incoming_service):
    start = datetime(2023, 10, 10, tzinfo=UTC)
    end = datetime(2023, 10, 1, tzinfo=UTC)
    with pytest.raises(NilveraValidationError, match="start_date cannot be after end_date"):
        await incoming_service.fetch_incoming_invoices(start, end)


@pytest.mark.asyncio
async def test_fetch_incoming_invoices_fails_if_range_exceeds_31_days(incoming_service):
    start = datetime(2023, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=32)
    with pytest.raises(NilveraValidationError, match="cannot exceed 31 days"):
        await incoming_service.fetch_incoming_invoices(start, end)


@pytest.mark.asyncio
async def test_fetch_incoming_invoices_fails_if_invalid_page(incoming_service):
    start = datetime(2023, 10, 1, tzinfo=UTC)
    end = datetime(2023, 10, 2, tzinfo=UTC)
    with pytest.raises(NilveraValidationError, match="page must be at least 1"):
        await incoming_service.fetch_incoming_invoices(start, end, page=0)


@pytest.mark.asyncio
async def test_fetch_incoming_invoices_fails_if_invalid_page_size(incoming_service):
    start = datetime(2023, 10, 1, tzinfo=UTC)
    end = datetime(2023, 10, 2, tzinfo=UTC)
    with pytest.raises(NilveraValidationError, match="page_size must be between 1 and 100"):
        await incoming_service.fetch_incoming_invoices(start, end, page=1, page_size=101)


@pytest.mark.asyncio
async def test_fetch_incoming_invoice_detail_uses_canonical_uuid(
    incoming_service,
    mock_http_client,
):
    provider_uuid = "123E4567-E89B-12D3-A456-426614174000"
    mock_http_client.get.return_value = {
        "UUID": provider_uuid,
        "InvoiceType": "SATIS",
        "InvoiceProfile": "TICARIFATURA",
        "InvoiceNumber": "TEST-INVOICE",
        "SendDate": "2023-10-01T12:05:00Z",
        "IssueDate": "2023-10-01T12:00:00Z",
        "CurrencyCode": "TRY",
        "NumberOfItems": 1,
        "InvoiceAmount": 100,
        "TaxAmount": 20,
        "AnswerCode": "unknown",
    }

    detail = await incoming_service.fetch_incoming_invoice_detail(provider_uuid)

    assert detail.provider_uuid == provider_uuid.lower()
    mock_http_client.get.assert_awaited_once_with(f"/einvoice/Purchase/{provider_uuid.lower()}/Details")


@pytest.mark.asyncio
async def test_fetch_incoming_invoice_detail_rejects_uuid_mismatch(
    incoming_service,
    mock_http_client,
):
    requested_uuid = "123e4567-e89b-12d3-a456-426614174000"
    mock_http_client.get.return_value = {
        "UUID": "123e4567-e89b-12d3-a456-426614174001",
        "InvoiceType": "SATIS",
        "InvoiceProfile": "TICARIFATURA",
        "InvoiceNumber": "TEST-INVOICE",
        "SendDate": "2023-10-01T12:05:00Z",
        "IssueDate": "2023-10-01T12:00:00Z",
        "CurrencyCode": "TRY",
        "NumberOfItems": 1,
        "InvoiceAmount": 100,
        "TaxAmount": 20,
        "AnswerCode": "unknown",
    }

    with pytest.raises(NilveraValidationError, match="UUID mismatch"):
        await incoming_service.fetch_incoming_invoice_detail(requested_uuid)


@pytest.mark.asyncio
async def test_fetch_incoming_invoice_status_uses_documented_endpoint(
    incoming_service,
    mock_http_client,
):
    provider_uuid = "123e4567-e89b-12d3-a456-426614174000"
    mock_http_client.get.return_value = {
        "InvoiceProfile": "TICARIFATURA",
        "IssueDate": "2023-10-01T12:00:00Z",
        "Answer": {"AnswerCode": "unknown"},
        "InvoiceStatus": {"Code": "Success"},
        "EnvelopeInfo": {"GIBCode": 1200, "CreatedDate": "2023-10-01T12:06:00Z"},
    }

    status = await incoming_service.fetch_incoming_invoice_status(provider_uuid)

    assert status.status_code == "Success"
    mock_http_client.get.assert_awaited_once_with(f"/einvoice/Purchase/{provider_uuid}/Status")


@pytest.mark.asyncio
async def test_incoming_read_methods_reject_invalid_uuid_without_http_call(
    incoming_service,
    mock_http_client,
):
    with pytest.raises(NilveraValidationError, match="UUID is invalid"):
        await incoming_service.fetch_incoming_invoice_detail("not-a-uuid")
    with pytest.raises(NilveraValidationError, match="UUID is invalid"):
        await incoming_service.fetch_incoming_invoice_status("not-a-uuid")

    mock_http_client.get.assert_not_awaited()
