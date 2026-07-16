from unittest.mock import AsyncMock

import pytest

from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.errors import NilveraApiError, NilveraValidationError
from core.integrations.nilvera.taxpayer import (
    NilveraTaxpayerService,
    TaxpayerAliasResult,
    TaxpayerCheckResult,
)


@pytest.fixture
def mock_client():
    client = AsyncMock(spec=NilveraHttpClient)
    return client


@pytest.fixture
def taxpayer_service(mock_client):
    return NilveraTaxpayerService(client=mock_client)


# 1. Invalid input validation error (empty, alphabetic, short, spaces)
@pytest.mark.parametrize("invalid_vkn", ["", "   ", "ABCDEFGHIJ", "12345", "123456789012"])
@pytest.mark.asyncio
async def test_invalid_vkn_raises_validation_error(taxpayer_service, mock_client, invalid_vkn):
    with pytest.raises(NilveraValidationError) as exc:
        await taxpayer_service.check_taxpayer(invalid_vkn)
    assert "Geçersiz Vergi Kimlik Numarası" in str(exc.value)

    with pytest.raises(NilveraValidationError) as exc:
        await taxpayer_service.get_taxpayer_aliases(invalid_vkn)
    assert "Geçersiz Vergi Kimlik Numarası" in str(exc.value)

    mock_client.get.assert_not_called()


# 2. Check Taxpayer valid scenarios
@pytest.mark.asyncio
async def test_check_taxpayer_valid_10_digit(taxpayer_service, mock_client):
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

    assert isinstance(result, TaxpayerCheckResult)
    assert result.tax_number == "1234567801"
    assert result.is_e_invoice_user is True
    assert result.document_type == "E_INVOICE"
    assert result.title == "TEST KURUM 1"


@pytest.mark.asyncio
async def test_check_taxpayer_valid_11_digit(taxpayer_service, mock_client):
    mock_client.get.return_value = [
        {
            "TaxNumber": "12345678901",
            "Title": "TEST SAHIS 1",
            "CreationTime": "2023-01-01T00:00:00Z",
        }
    ]

    result = await taxpayer_service.check_taxpayer("12345678901")

    assert result.tax_number == "12345678901"
    assert result.is_e_invoice_user is True
    assert result.title == "TEST SAHIS 1"


@pytest.mark.asyncio
async def test_check_taxpayer_empty_response_returns_earchive(taxpayer_service, mock_client):
    mock_client.get.return_value = []

    result = await taxpayer_service.check_taxpayer("1234567801")

    assert result.tax_number == "1234567801"
    assert result.is_e_invoice_user is False
    assert result.document_type == "E_ARCHIVE"
    assert result.title is None


# 3. Check Taxpayer fail-closed scenarios
@pytest.mark.asyncio
async def test_check_taxpayer_malformed_type_error(taxpayer_service, mock_client):
    mock_client.get.return_value = {"error": "not a list"}

    with pytest.raises(NilveraValidationError) as exc:
        await taxpayer_service.check_taxpayer("1234567801")
    assert "Liste bekleniyordu" in str(exc.value)


@pytest.mark.asyncio
async def test_check_taxpayer_malformed_item_error(taxpayer_service, mock_client):
    mock_client.get.return_value = [{"MissingTaxNumber": "123"}]

    with pytest.raises(NilveraValidationError) as exc:
        await taxpayer_service.check_taxpayer("1234567801")
    assert "geçersiz öğe döndürdü" in str(exc.value)


# 4. Aliases valid scenarios
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

    assert isinstance(result, TaxpayerAliasResult)
    assert result.tax_number == "1234567801"
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
    assert len(result.aliases) == 0


@pytest.mark.asyncio
async def test_get_taxpayer_aliases_only_deleted(taxpayer_service, mock_client):
    mock_client.get.return_value = {
        "TaxNumber": "1234567801",
        "Title": "TEST KURUM 1",
        "Aliases": [
            {
                "Name": "urn:mail:oldpk@nilvera.com",
                "CreationTime": "2022-01-01T00:00:00Z",
                "DeletionTime": "2023-01-01T00:00:00Z",
            },
        ],
    }

    result = await taxpayer_service.get_taxpayer_aliases("1234567801")
    assert len(result.aliases) == 0


# 5. Aliases fail-closed scenarios
@pytest.mark.asyncio
async def test_get_taxpayer_aliases_malformed_response_type(taxpayer_service, mock_client):
    mock_client.get.return_value = []

    with pytest.raises(NilveraValidationError) as exc:
        await taxpayer_service.get_taxpayer_aliases("1234567801")
    assert "Obje bekleniyordu" in str(exc.value)


@pytest.mark.asyncio
async def test_get_taxpayer_aliases_malformed_item(taxpayer_service, mock_client):
    mock_client.get.return_value = {
        "TaxNumber": "1234567801",
        "Aliases": [{"MissingName": "invalid"}],
    }

    with pytest.raises(NilveraValidationError) as exc:
        await taxpayer_service.get_taxpayer_aliases("1234567801")
    assert "geçersiz öğe döndürdü" in str(exc.value)


# 6. Api error propagation
@pytest.mark.asyncio
async def test_api_error_propagates(taxpayer_service, mock_client):
    mock_client.get.side_effect = NilveraApiError(message="Network fail", http_status=500)

    with pytest.raises(NilveraApiError):
        await taxpayer_service.check_taxpayer("1234567801")

    with pytest.raises(NilveraApiError):
        await taxpayer_service.get_taxpayer_aliases("1234567801")


# 7. Model mutability check
def test_alias_result_default_factory_isolation():
    r1 = TaxpayerAliasResult(tax_number="1234567801")
    r2 = TaxpayerAliasResult(tax_number="1234567802")
    r1.aliases.append("alias1")
    assert "alias1" not in r2.aliases
