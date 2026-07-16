import logging
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
async def test_invalid_vkn_raises_validation_error(taxpayer_service, mock_client, invalid_vkn, caplog):
    caplog.set_level(logging.WARNING)

    with pytest.raises(NilveraValidationError) as exc:
        await taxpayer_service.check_taxpayer(invalid_vkn)
    assert "Geçersiz Vergi Kimlik Numarası" in str(exc.value)

    # A. invalid tax number redaction test
    if invalid_vkn.strip():
        # Assert full invalid_vkn is NOT in the logs
        assert invalid_vkn not in caplog.text
        # Assert masked is in logs
        if len(invalid_vkn) >= 4:
            assert f"***{invalid_vkn[-4:]}" in caplog.text

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
async def test_check_taxpayer_malformed_item_error(taxpayer_service, mock_client, caplog):
    caplog.set_level(logging.ERROR)

    # B. malformed Check item log redaction test
    sensitive_vkn = "5555555555"
    sensitive_title = "COK GIZLI SIRKET A.S."
    sensitive_name = "urn:mail:gizli@sirket.com.tr"

    mock_client.get.return_value = [
        {
            "MissingTaxNumber": "123",
            "Title": sensitive_title,
            "Name": sensitive_name,
            # We purposely make the model fail by omitting TaxNumber.
            # We pass Title and Name which shouldn't be logged.
        }
    ]

    with pytest.raises(NilveraValidationError) as exc:
        await taxpayer_service.check_taxpayer("1234567801")
    assert "geçersiz öğe döndürdü" in str(exc.value)

    # Check that safe message is logged
    assert "Malformed response item in Check/TaxNumber for ***7801" in caplog.text
    # Verify PII/sensitive data is NOT in the logs
    assert sensitive_vkn not in caplog.text
    assert sensitive_title not in caplog.text
    assert sensitive_name not in caplog.text
    assert "MissingTaxNumber" not in caplog.text  # Keys/inputs shouldn't be exposed either


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
async def test_get_taxpayer_aliases_missing_aliases_fails_schema(taxpayer_service, mock_client):
    # Tests that Aliases key is strictly required
    mock_client.get.return_value = {
        "TaxNumber": "1234567801",
        "Title": "TEST KURUM 1",
        # Missing 'Aliases' entirely
    }

    with pytest.raises(NilveraValidationError) as exc:
        await taxpayer_service.get_taxpayer_aliases("1234567801")
    assert "geçersiz öğe döndürdü" in str(exc.value)


@pytest.mark.asyncio
async def test_get_taxpayer_aliases_malformed_item(taxpayer_service, mock_client, caplog):
    caplog.set_level(logging.ERROR)

    # C. malformed CustomerInfo/Alias log redaction test
    sensitive_vkn = "1112223334"
    sensitive_email = "very.secret@company.com"
    sensitive_address = "Gizli Mah. Gormez Sok. No: 1 Istanbul"
    sensitive_alias = "urn:mail:private_pk@company.com"

    mock_client.get.return_value = {
        "TaxNumber": sensitive_vkn,
        "Email": sensitive_email,
        "Address": sensitive_address,
        "Aliases": [{"MissingName": "invalid", "Name_but_wrong_key": sensitive_alias}],
    }

    with pytest.raises(NilveraValidationError) as exc:
        await taxpayer_service.get_taxpayer_aliases("1234567801")
    assert "geçersiz öğe döndürdü" in str(exc.value)

    assert "Malformed response in GetGlobalCustomerInfo for ***7801" in caplog.text
    # Verify PII/sensitive data is NOT in the logs
    assert sensitive_vkn not in caplog.text
    assert sensitive_email not in caplog.text
    assert sensitive_address not in caplog.text
    assert sensitive_alias not in caplog.text
    assert "MissingName" not in caplog.text  # Keys/inputs shouldn't be exposed either


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
