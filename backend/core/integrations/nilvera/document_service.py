import uuid
from defusedxml import ElementTree as ET
from typing import Literal

from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.errors import NilveraValidationError


class NilveraDocumentService:
    """Service for securely downloading PDF and XML documents from Nilvera E-Invoice APIs."""

    def __init__(self, client: NilveraHttpClient):
        self._client = client

    @staticmethod
    def _validate_uuid(val: str) -> str:
        if not val:
            raise ValueError("UUID cannot be empty")
        try:
            return str(uuid.UUID(val))
        except ValueError as e:
            raise ValueError(f"Invalid UUID format: {val}") from e

    @staticmethod
    def _validate_pdf_content(content: bytes) -> None:
        if not content:
            raise NilveraValidationError("Empty binary response for PDF")

        # Check magic bytes (ignoring potential BOM or whitespace)
        if not content.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"%PDF-"):
            raise NilveraValidationError("Invalid PDF document: missing magic bytes")

    @staticmethod
    def _validate_xml_content(content: bytes) -> None:
        if not content:
            raise NilveraValidationError("Empty binary response for XML")

        try:
            root = ET.fromstring(content)

            tag = root.tag
            if "}" in tag:
                namespace, local_name = tag.split("}", 1)
                namespace = namespace.strip("{")
            else:
                namespace, local_name = None, tag

            if local_name != "Invoice":
                raise NilveraValidationError(f"Unexpected UBL document root: {local_name}")

            if namespace != "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2":
                raise NilveraValidationError(f"Unexpected UBL Invoice namespace: {namespace}")

        except ET.ParseError:
            raise NilveraValidationError("Invalid XML document: parsing failed") from None

    async def _download_document(
        self,
        invoice_uuid: str,
        doc_type: Literal["pdf", "xml"],
        direction: Literal["Sale", "Purchase"],
    ) -> bytes:
        clean_uuid = self._validate_uuid(invoice_uuid)

        # Endpoint construction based on official Nilvera structure
        path = f"/einvoice/{direction}/{clean_uuid}/{doc_type}"

        expected_types = []
        if doc_type == "pdf":
            expected_types = ["application/pdf", "application/octet-stream"]
        elif doc_type == "xml":
            expected_types = ["application/xml", "text/xml", "application/octet-stream"]

        content = await self._client.get_binary(
            path=path,
            expected_content_types=expected_types,
        )

        if doc_type == "pdf":
            self._validate_pdf_content(content)
        elif doc_type == "xml":
            self._validate_xml_content(content)

        return content

    async def download_sale_pdf(self, invoice_uuid: str) -> bytes:
        """Downloads the PDF representation of an outgoing (Sale) e-invoice."""
        return await self._download_document(invoice_uuid, "pdf", "Sale")

    async def download_sale_xml(self, invoice_uuid: str) -> bytes:
        """Downloads the UBL XML representation of an outgoing (Sale) e-invoice."""
        return await self._download_document(invoice_uuid, "xml", "Sale")

    async def download_purchase_pdf(self, invoice_uuid: str) -> bytes:
        """Downloads the PDF representation of an incoming (Purchase) e-invoice."""
        return await self._download_document(invoice_uuid, "pdf", "Purchase")

    async def download_purchase_xml(self, invoice_uuid: str) -> bytes:
        """Downloads the UBL XML representation of an incoming (Purchase) e-invoice."""
        return await self._download_document(invoice_uuid, "xml", "Purchase")
