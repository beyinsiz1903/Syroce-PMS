import uuid
import xml.etree.ElementTree as ET
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
        
        # Check magic bytes
        if not content.startswith(b"%PDF-"):
            raise NilveraValidationError("Invalid PDF document: missing magic bytes")

    @staticmethod
    def _validate_xml_content(content: bytes) -> None:
        if not content:
            raise NilveraValidationError("Empty binary response for XML")
        
        try:
            # We don't use full schema validation here, just check if it's parsable XML
            # and loosely verify if it looks like an invoice structure.
            root = ET.fromstring(content)
            
            # Simple heuristic to ensure it is somewhat related to UBL / Invoice
            tag_name = root.tag.lower()
            # Handle namespace, e.g. {urn:oasis:names:...}Invoice -> invoice
            if "}" in tag_name:
                tag_name = tag_name.split("}", 1)[1]
            if tag_name not in ("invoice", "despatchadvice"):
                raise NilveraValidationError(f"Invalid XML document: Expected Invoice root, got {root.tag}")
        except ET.ParseError as e:
            raise NilveraValidationError("Invalid XML document: parsing failed") from e

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
