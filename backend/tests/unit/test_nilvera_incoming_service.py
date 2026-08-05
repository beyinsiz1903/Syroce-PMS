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
        "Data": [],
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
            "Take": "50",
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
