"""Tests for NilveraSeriesService — GET /einvoice/Series."""

import logging
import traceback
from unittest.mock import AsyncMock

import pytest

from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.errors import NilveraApiError, NilveraValidationError
from core.integrations.nilvera.series import (
    NilveraSeriesPage,
    NilveraSeriesService,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_SERIES_RESPONSE = {
    "Page": 1,
    "PageSize": 50,
    "TotalCount": 2,
    "TotalPages": 1,
    "Content": [
        {
            "ID": 1,
            "Name": "AEF",
            "IsDefault": True,
            "IsActive": True,
            "CreatedDate": "2026-01-01T00:00:00.000Z",
            "Details": [
                {
                    "ID": 10,
                    "Year": "2026",
                    "OrdinalNumber": 42,
                    "LastIssueDate": "2026-07-15T00:00:00.000Z",
                }
            ],
        },
        {
            "ID": 2,
            "Name": "BEF",
            "IsDefault": False,
            "IsActive": False,
            "CreatedDate": "2025-01-01T00:00:00.000Z",
            "Details": [],
        },
    ],
}


@pytest.fixture
def mock_client():
    return AsyncMock(spec=NilveraHttpClient)


@pytest.fixture
def series_service(mock_client):
    return NilveraSeriesService(client=mock_client)


# ---------------------------------------------------------------------------
# 1. Happy path — active series list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_einvoice_series_valid(series_service, mock_client):
    mock_client.get.return_value = VALID_SERIES_RESPONSE

    result = await series_service.list_einvoice_series()

    assert isinstance(result, NilveraSeriesPage)
    assert result.page == 1
    assert result.page_size == 50
    assert result.total_count == 2
    assert result.total_pages == 1
    assert len(result.content) == 2

    first = result.content[0]
    assert first.id == 1
    assert first.name == "AEF"
    assert first.is_default is True
    assert first.is_active is True
    assert len(first.details) == 1
    assert first.details[0].year == "2026"
    assert first.details[0].ordinal_number == 42


# ---------------------------------------------------------------------------
# 2. Edge case — empty Content list (valid, not an error)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_einvoice_series_empty_content(series_service, mock_client):
    mock_client.get.return_value = {
        "Page": 1,
        "PageSize": 50,
        "TotalCount": 0,
        "TotalPages": 0,
        "Content": [],
    }

    result = await series_service.list_einvoice_series()
    assert result.total_count == 0
    assert result.content == []


# ---------------------------------------------------------------------------
# 3. Filter — IsActive query parameter is forwarded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_active_filter_forwarded(series_service, mock_client):
    mock_client.get.return_value = {
        "Page": 1,
        "PageSize": 50,
        "TotalCount": 0,
        "TotalPages": 0,
        "Content": [],
    }

    await series_service.list_einvoice_series(is_active=True)

    call_args = mock_client.get.call_args
    path = call_args[0][0]
    assert "IsActive=True" in path


# ---------------------------------------------------------------------------
# 4. Filter — IsDefault query parameter is forwarded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_default_filter_forwarded(series_service, mock_client):
    mock_client.get.return_value = {
        "Page": 1,
        "PageSize": 50,
        "TotalCount": 0,
        "TotalPages": 0,
        "Content": [],
    }

    await series_service.list_einvoice_series(is_default=True)

    call_args = mock_client.get.call_args
    path = call_args[0][0]
    assert "IsDefault=True" in path


# ---------------------------------------------------------------------------
# 5. Fail-closed — response is not a dict (e.g. list returned)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_dict_response_raises_validation_error(series_service, mock_client):
    mock_client.get.return_value = [{"ID": 1}]

    with pytest.raises(NilveraValidationError) as exc:
        await series_service.list_einvoice_series()
    assert "Obje bekleniyordu" in str(exc.value)


# ---------------------------------------------------------------------------
# 6. Fail-closed — Content field missing (schema violation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_content_field_raises_validation_error(series_service, mock_client):
    mock_client.get.return_value = {
        "Page": 1,
        "PageSize": 50,
        "TotalCount": 0,
        "TotalPages": 0,
        # "Content" intentionally omitted
    }

    with pytest.raises(NilveraValidationError) as exc:
        await series_service.list_einvoice_series()
    assert "geçersiz yapı döndürdü" in str(exc.value)


# ---------------------------------------------------------------------------
# 7. Fail-closed — Details field missing on an item (schema violation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_details_on_item_raises_validation_error(series_service, mock_client):
    mock_client.get.return_value = {
        "Page": 1,
        "PageSize": 50,
        "TotalCount": 1,
        "TotalPages": 1,
        "Content": [
            {
                "ID": 1,
                "Name": "AEF",
                "IsDefault": True,
                "IsActive": True,
                "CreatedDate": "2026-01-01T00:00:00.000Z",
                # "Details" intentionally omitted
            }
        ],
    }

    with pytest.raises(NilveraValidationError) as exc:
        await series_service.list_einvoice_series()
    assert "geçersiz yapı döndürdü" in str(exc.value)


# ---------------------------------------------------------------------------
# 8. Security — malformed response: caplog PII redaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_response_caplog_redaction(series_service, mock_client, caplog):
    caplog.set_level(logging.ERROR)

    sensitive_name = "GIZLI_SERI_2026"
    sensitive_detail_year = "2099-INTERNAL"

    mock_client.get.return_value = {
        "Page": 1,
        "PageSize": 50,
        "TotalCount": 1,
        "TotalPages": 1,
        "Content": [
            {
                # Missing required ID — triggers ValidationError
                "Name": sensitive_name,
                "IsDefault": True,
                "IsActive": True,
                "Details": [
                    {
                        "ID": 1,
                        "Year": sensitive_detail_year,
                        "OrdinalNumber": 1,
                    }
                ],
            }
        ],
    }

    with pytest.raises(NilveraValidationError):
        await series_service.list_einvoice_series()

    assert "Malformed response from /einvoice/Series" in caplog.text
    # Sensitive values must NOT appear in logs
    assert sensitive_name not in caplog.text
    assert sensitive_detail_year not in caplog.text


# ---------------------------------------------------------------------------
# 9. Security — malformed response: __cause__ is None (chain suppressed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_response_cause_is_none(series_service, mock_client):
    mock_client.get.return_value = {
        # Missing all required top-level fields
        "unexpected_key": "unexpected_value",
    }

    with pytest.raises(NilveraValidationError) as exc:
        await series_service.list_einvoice_series()

    assert exc.value.__cause__ is None


# ---------------------------------------------------------------------------
# 10. Security — malformed response: traceback PII redaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_response_traceback_redaction(series_service, mock_client):
    sensitive_series_name = "TOP_SECRET_SERIES"
    sensitive_year = "2099-CLASSIFIED"

    mock_client.get.return_value = {
        "Page": 1,
        "PageSize": 50,
        "TotalCount": 1,
        "TotalPages": 1,
        "Content": [
            {
                # Missing required ID
                "Name": sensitive_series_name,
                "IsDefault": True,
                "IsActive": True,
                "Details": [
                    {
                        "ID": 1,
                        "Year": sensitive_year,
                        "OrdinalNumber": 1,
                    }
                ],
            }
        ],
    }

    with pytest.raises(NilveraValidationError) as exc:
        await series_service.list_einvoice_series()

    tb_text = "".join(traceback.format_exception(type(exc.value), exc.value, exc.value.__traceback__))
    assert sensitive_series_name not in tb_text
    assert sensitive_year not in tb_text


# ---------------------------------------------------------------------------
# 11. Error handling — NilveraApiError propagates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_error_propagates(series_service, mock_client):
    mock_client.get.side_effect = NilveraApiError(message="Connection refused", http_status=503)

    with pytest.raises(NilveraApiError):
        await series_service.list_einvoice_series()


# ---------------------------------------------------------------------------
# 12. Model — pagination fields correctly mapped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pagination_fields_mapped(series_service, mock_client):
    mock_client.get.return_value = {
        "Page": 3,
        "PageSize": 10,
        "TotalCount": 25,
        "TotalPages": 3,
        "Content": [],
    }

    result = await series_service.list_einvoice_series(page=3, page_size=10)

    assert result.page == 3
    assert result.page_size == 10
    assert result.total_count == 25
    assert result.total_pages == 3


# ---------------------------------------------------------------------------
# 13–17. Input validation — invalid pagination values must not reach the API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_page_zero_raises_validation_error(series_service, mock_client):
    with pytest.raises(NilveraValidationError) as exc:
        await series_service.list_einvoice_series(page=0)
    assert "page" in str(exc.value).lower()
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_page_negative_raises_validation_error(series_service, mock_client):
    with pytest.raises(NilveraValidationError) as exc:
        await series_service.list_einvoice_series(page=-1)
    assert "page" in str(exc.value).lower()
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_page_size_zero_raises_validation_error(series_service, mock_client):
    with pytest.raises(NilveraValidationError) as exc:
        await series_service.list_einvoice_series(page_size=0)
    assert "page_size" in str(exc.value).lower()
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_page_size_negative_raises_validation_error(series_service, mock_client):
    with pytest.raises(NilveraValidationError) as exc:
        await series_service.list_einvoice_series(page_size=-1)
    assert "page_size" in str(exc.value).lower()
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_pagination_never_calls_api(series_service, mock_client):
    """Guard test: any invalid pagination input must abort before the HTTP call."""
    for kwargs in [{"page": 0}, {"page": -5}, {"page_size": 0}, {"page_size": -99}]:
        mock_client.reset_mock()
        with pytest.raises(NilveraValidationError):
            await series_service.list_einvoice_series(**kwargs)
        mock_client.get.assert_not_called()
