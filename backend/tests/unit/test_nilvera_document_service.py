import uuid
from unittest.mock import AsyncMock

import pytest

from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.document_service import NilveraDocumentService
from core.integrations.nilvera.errors import NilveraValidationError


@pytest.fixture
def mock_http_client():
    client = AsyncMock(spec=NilveraHttpClient)
    return client


@pytest.fixture
def doc_service(mock_http_client):
    return NilveraDocumentService(client=mock_http_client)


def test_uuid_validation(doc_service):
    with pytest.raises(ValueError, match="UUID cannot be empty"):
        doc_service._validate_uuid("")

    with pytest.raises(ValueError, match="Invalid UUID format"):
        doc_service._validate_uuid("invalid-uuid")

    valid_uuid = str(uuid.uuid4())
    assert doc_service._validate_uuid(valid_uuid) == valid_uuid


def test_pdf_content_validation(doc_service):
    with pytest.raises(NilveraValidationError, match="Empty binary response"):
        doc_service._validate_pdf_content(b"")

    with pytest.raises(NilveraValidationError, match="missing magic bytes"):
        doc_service._validate_pdf_content(b"<html></html>")

    # Should pass
    doc_service._validate_pdf_content(b"%PDF-1.4\ncontent")


def test_xml_content_validation(doc_service):
    with pytest.raises(NilveraValidationError, match="Empty binary response"):
        doc_service._validate_xml_content(b"")

    with pytest.raises(NilveraValidationError, match="parsing failed"):
        doc_service._validate_xml_content(b"not xml")

    with pytest.raises(NilveraValidationError, match="Expected Invoice root"):
        doc_service._validate_xml_content(b"<NotInvoice></NotInvoice>")

    # Should pass
    doc_service._validate_xml_content(b"<Invoice></Invoice>")
    doc_service._validate_xml_content(b"<?xml version=\"1.0\"?><Invoice xmlns=\"urn:oasis:names:specification:ubl:schema:xsd:Invoice-2\"></Invoice>")


@pytest.mark.asyncio
async def test_download_sale_pdf(doc_service, mock_http_client):
    mock_http_client.get_binary.return_value = b"%PDF-content"
    invoice_uuid = str(uuid.uuid4())
    
    res = await doc_service.download_sale_pdf(invoice_uuid)
    
    assert res == b"%PDF-content"
    mock_http_client.get_binary.assert_called_once_with(
        path=f"/einvoice/Sale/{invoice_uuid}/pdf",
        expected_content_types=["application/pdf", "application/octet-stream"]
    )


@pytest.mark.asyncio
async def test_download_purchase_xml(doc_service, mock_http_client):
    mock_http_client.get_binary.return_value = b"<Invoice></Invoice>"
    invoice_uuid = str(uuid.uuid4())
    
    res = await doc_service.download_purchase_xml(invoice_uuid)
    
    assert res == b"<Invoice></Invoice>"
    mock_http_client.get_binary.assert_called_once_with(
        path=f"/einvoice/Purchase/{invoice_uuid}/xml",
        expected_content_types=["application/xml", "text/xml", "application/octet-stream"]
    )
