from unittest.mock import AsyncMock

import pytest

from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.taxpayer import (
    NilveraTaxpayerService,
    TaxpayerInfo,
)


@pytest.fixture
def mock_client():
    client = AsyncMock(spec=NilveraHttpClient)
    return client


@pytest.fixture
def taxpayer_service(mock_client):
    return NilveraTaxpayerService(client=mock_client)


@pytest.mark.asyncio
async def test_check_taxpayer_valid_e_invoice_user(taxpayer_service, mock_client):
    mock_client.get.return_value = [
        {
            "TaxNumber": "1234567801",
            "Title": "TEST KURUM 1",
            "FirstCreatedTime": "2023-01-01T00:00:00Z",
            "CreationTime": "2023-01-01T00:00:00Z",
            "DocumentType": "EInvoice",
            "Name": "urn:mail:defaultpk@nilvera.com",
            "Type": "Public",
        }
    ]

    result = await taxpayer_service.check_taxpayer("1234567801")

    assert isinstance(result, TaxpayerInfo)
    assert result.tax_number == "1234567801"
    assert result.is_e_invoice_user is True
    assert result.document_type == "E_INVOICE"
    assert result.title == "TEST KURUM 1"


@pytest.mark.asyncio
async def test_check_taxpayer_invalid_not_e_invoice(taxpayer_service, mock_client):
    mock_client.get.return_value = []

    result = await taxpayer_service.check_taxpayer("1234567801")

    assert isinstance(result, TaxpayerInfo)
    assert result.tax_number == "1234567801"
    assert result.is_e_invoice_user is False
    assert result.document_type == "E_ARCHIVE"
    assert result.title is None


@pytest.mark.asyncio
async def test_check_taxpayer_invalid_vkn_length(taxpayer_service, mock_client):
    # Length 5 is invalid
    result = await taxpayer_service.check_taxpayer("12345")

    # API shouldn't be called
    mock_client.get.assert_not_called()

    assert result.is_e_invoice_user is False
    assert result.document_type == "E_ARCHIVE"


@pytest.mark.asyncio
async def test_get_taxpayer_aliases_valid(taxpayer_service, mock_client):
    mock_client.get.return_value = {
        "TaxNumber": "1234567801",
        "Title": "TEST KURUM 1",
        "Aliases": [
            {
                "Name": "urn:mail:defaultpk@nilvera.com",
                "CreationTime": "2023-01-01T00:00:00Z",
                "DeletionTime": None,
            },
            {
                "Name": "urn:mail:oldpk@nilvera.com",
                "CreationTime": "2022-01-01T00:00:00Z",
                "DeletionTime": "2023-01-01T00:00:00Z",
            },
        ],
    }

    result = await taxpayer_service.get_taxpayer_aliases("1234567801")

    assert result.is_e_invoice_user is True
    assert result.title == "TEST KURUM 1"
    # Should only return the active alias
    assert len(result.aliases) == 1
    assert result.aliases[0] == "urn:mail:defaultpk@nilvera.com"


@pytest.mark.asyncio
async def test_get_taxpayer_aliases_empty(taxpayer_service, mock_client):
    mock_client.get.return_value = {
        "TaxNumber": "1234567801",
        "Title": "TEST KURUM 1",
        "Aliases": [],
    }

    result = await taxpayer_service.get_taxpayer_aliases("1234567801")

    assert result.is_e_invoice_user is False
    assert result.document_type == "E_ARCHIVE"
    assert len(result.aliases) == 0
