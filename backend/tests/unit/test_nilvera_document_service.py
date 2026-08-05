import base64
import json
import uuid
from unittest.mock import AsyncMock

import pytest

from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.document_service import NilveraDocumentService
from core.integrations.nilvera.errors import NilveraApiError, NilveraAuthError, NilveraNotFoundError, NilveraValidationError


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
    # Should maintain canonical format (lowercase, with dashes)
    upper_uuid = valid_uuid.upper()
    assert doc_service._validate_uuid(upper_uuid) == valid_uuid


def test_pdf_content_validation(doc_service):
    with pytest.raises(NilveraValidationError, match="Empty binary response"):
        doc_service._validate_pdf_content(b"")

    with pytest.raises(NilveraValidationError, match="missing magic bytes"):
        doc_service._validate_pdf_content(b"<html></html>")

    # Should pass normal
    doc_service._validate_pdf_content(b"%PDF-1.4\ncontent")

    # Should pass with BOM or whitespaces
    doc_service._validate_pdf_content(b"\xef\xbb\xbf%PDF-1.4\ncontent")
    doc_service._validate_pdf_content(b" \t\r\n%PDF-1.4\ncontent")


def test_xml_content_validation(doc_service):
    with pytest.raises(NilveraValidationError, match="Empty binary response"):
        doc_service._validate_xml_content(b"")

    with pytest.raises(NilveraValidationError, match="parsing failed"):
        doc_service._validate_xml_content(b"not xml")

    with pytest.raises(NilveraValidationError, match="Unexpected UBL document root"):
        doc_service._validate_xml_content(b"<DespatchAdvice></DespatchAdvice>")

    with pytest.raises(NilveraValidationError, match="Unexpected UBL Invoice namespace"):
        doc_service._validate_xml_content(b"<Invoice></Invoice>")

    with pytest.raises(NilveraValidationError, match="Unexpected UBL Invoice namespace"):
        doc_service._validate_xml_content(b'<?xml version="1.0"?><Invoice xmlns="wrong:namespace"></Invoice>')

    # Should pass
    doc_service._validate_xml_content(b'<?xml version="1.0"?><Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"></Invoice>')


@pytest.mark.asyncio
async def test_download_sale_pdf(doc_service, mock_http_client):
    mock_http_client.get_binary.return_value = (b"%PDF-content", "application/pdf")
    invoice_uuid = str(uuid.uuid4())

    res = await doc_service.download_sale_pdf(invoice_uuid)
    assert res == b"%PDF-content"
    mock_http_client.get_binary.assert_called_once_with(path=f"/einvoice/Sale/{invoice_uuid}/pdf", expected_content_types=["application/pdf", "application/octet-stream", "application/json"])


@pytest.mark.asyncio
async def test_download_sale_xml(doc_service, mock_http_client):
    mock_http_client.get_binary.return_value = (b'<?xml version="1.0"?><Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"></Invoice>', "application/xml")
    invoice_uuid = str(uuid.uuid4())

    res = await doc_service.download_sale_xml(invoice_uuid)
    assert res.startswith(b"<?xml")
    mock_http_client.get_binary.assert_called_once_with(
        path=f"/einvoice/Sale/{invoice_uuid}/xml", expected_content_types=["application/xml", "text/xml", "application/octet-stream", "application/json"]
    )


@pytest.mark.asyncio
async def test_download_purchase_pdf(doc_service, mock_http_client):
    mock_http_client.get_binary.return_value = (b"%PDF-content", "application/pdf")
    invoice_uuid = str(uuid.uuid4())

    res = await doc_service.download_purchase_pdf(invoice_uuid)
    assert res == b"%PDF-content"
    mock_http_client.get_binary.assert_called_once_with(path=f"/einvoice/Purchase/{invoice_uuid}/pdf", expected_content_types=["application/pdf", "application/octet-stream", "application/json"])


@pytest.mark.asyncio
async def test_download_purchase_xml(doc_service, mock_http_client):
    mock_http_client.get_binary.return_value = (b'<?xml version="1.0"?><Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"></Invoice>', "application/xml")
    invoice_uuid = str(uuid.uuid4())

    res = await doc_service.download_purchase_xml(invoice_uuid)
    assert b"Invoice" in res
    mock_http_client.get_binary.assert_called_once_with(
        path=f"/einvoice/Purchase/{invoice_uuid}/xml", expected_content_types=["application/xml", "text/xml", "application/octet-stream", "application/json"]
    )


@pytest.mark.asyncio
async def test_download_fails_closed_on_http_errors(doc_service, mock_http_client):
    mock_http_client.get_binary.side_effect = NilveraAuthError("401 Unauthorized")
    with pytest.raises(NilveraAuthError):
        await doc_service.download_sale_pdf(str(uuid.uuid4()))

    mock_http_client.get_binary.side_effect = NilveraNotFoundError("404 Not Found")
    with pytest.raises(NilveraNotFoundError):
        await doc_service.download_sale_pdf(str(uuid.uuid4()))

    mock_http_client.get_binary.side_effect = NilveraApiError("500 Server Error")
    with pytest.raises(NilveraApiError):
        await doc_service.download_sale_pdf(str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_download_pdf_validates_octet_stream_magic_bytes(doc_service, mock_http_client):
    # Simulate client returning octet-stream but content is invalid HTML instead of PDF
    mock_http_client.get_binary.return_value = (b"<html>Not a PDF</html>", "application/octet-stream")

    with pytest.raises(NilveraValidationError, match="missing magic bytes"):
        await doc_service.download_sale_pdf(str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_download_pdf_decodes_base64_json_string(doc_service, mock_http_client):
    mock_http_client._config = type("obj", (object,), {"max_response_size_bytes": 1048576})()
    valid_pdf_b64 = base64.b64encode(b"%PDF-1.4\nsome content").decode("utf-8")
    mock_http_client.get_binary.return_value = (json.dumps(valid_pdf_b64).encode("utf-8"), "application/json")

    invoice_uuid = str(uuid.uuid4())
    res = await doc_service.download_sale_pdf(invoice_uuid)

    assert res == b"%PDF-1.4\nsome content"


@pytest.mark.asyncio
async def test_download_pdf_handles_raw_string_wrapped_in_json(doc_service, mock_http_client):
    mock_http_client._config = type("obj", (object,), {"max_response_size_bytes": 1048576})()
    raw_content = "%PDF-1.4\nsome content İ"  # Turkish character prevents valid base64 decode
    mock_http_client.get_binary.return_value = (json.dumps(raw_content).encode("utf-8"), "application/json")

    invoice_uuid = str(uuid.uuid4())
    res = await doc_service.download_sale_pdf(invoice_uuid)

    assert res == raw_content.encode("utf-8")
