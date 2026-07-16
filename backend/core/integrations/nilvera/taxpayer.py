"""Nilvera taxpayer validation and routing service."""

import logging
from typing import Literal

from pydantic import BaseModel, Field

from .client import NilveraHttpClient
from .errors import NilveraApiError

logger = logging.getLogger("core.integrations.nilvera.taxpayer")


class TaxpayerInfo(BaseModel):
    """Normalized taxpayer information for Syroce."""

    tax_number: str
    is_e_invoice_user: bool
    document_type: Literal["E_INVOICE", "E_ARCHIVE"]
    title: str | None = None
    aliases: list[str] = []


class NilveraCheckResponseItem(BaseModel):
    """Schema for individual items returned by the Check VKN endpoint."""

    tax_number: str = Field(alias="TaxNumber")
    title: str | None = Field(None, alias="Title")
    first_created_time: str | None = Field(None, alias="FirstCreatedTime")
    creation_time: str | None = Field(None, alias="CreationTime")
    document_type: str | None = Field(None, alias="DocumentType")
    name: str | None = Field(None, alias="Name")
    type_field: str | None = Field(None, alias="Type")


class NilveraAliasItem(BaseModel):
    """Schema for alias items returned inside CustomerInfo."""

    name: str = Field(alias="Name")
    creation_time: str | None = Field(None, alias="CreationTime")
    deletion_time: str | None = Field(None, alias="DeletionTime")


class NilveraCustomerInfoResponse(BaseModel):
    """Schema for the CustomerInfo endpoint response."""

    tax_number: str = Field(alias="TaxNumber")
    title: str | None = Field(None, alias="Title")
    tax_department: str | None = Field(None, alias="TaxDepartment")
    address: str | None = Field(None, alias="Address")
    country: str | None = Field(None, alias="Country")
    city: str | None = Field(None, alias="City")
    district: str | None = Field(None, alias="District")
    postal_code: str | None = Field(None, alias="PostalCode")
    phone: str | None = Field(None, alias="Phone")
    fax: str | None = Field(None, alias="Fax")
    email: str | None = Field(None, alias="Email")
    type_field: str | None = Field(None, alias="Type")
    website: str | None = Field(None, alias="WebSite")
    module_type: str | None = Field(None, alias="ModuleType")
    first_creation_time: str | None = Field(None, alias="FirstCreationTime")
    aliases: list[NilveraAliasItem] = Field(default_factory=list, alias="Aliases")


class NilveraTaxpayerService:
    """Service to check e-Document taxpayer status in Nilvera."""

    def __init__(self, client: NilveraHttpClient):
        self._client = client

    async def check_taxpayer(self, tax_number: str, correlation_id: str | None = None) -> TaxpayerInfo:
        """
        Check if the given VKN/TCKN is an e-Invoice taxpayer.

        Returns TaxpayerInfo containing boolean status, default E_INVOICE/E_ARCHIVE
        document type, and potentially the company Title if available.
        """
        tax_number = (tax_number or "").strip()

        # 10 digits for VKN, 11 digits for TCKN
        if not tax_number.isdigit() or len(tax_number) not in (10, 11):
            logger.warning(
                "Invalid tax number length: %s. Defaulting to E_ARCHIVE",
                _mask_tax_number(tax_number),
                extra={"correlation_id": correlation_id},
            )
            return TaxpayerInfo(
                tax_number=tax_number,
                is_e_invoice_user=False,
                document_type="E_ARCHIVE",
            )

        try:
            path = f"/general/GlobalCompany/Check/TaxNumber/{tax_number}?globalUserType=Invoice"
            response_data = await self._client.get(path, correlation_id=correlation_id)

            if not isinstance(response_data, list):
                logger.warning(
                    "Unexpected response type from Check/TaxNumber: %s",
                    type(response_data).__name__,
                    extra={"correlation_id": correlation_id},
                )
                return TaxpayerInfo(tax_number=tax_number, is_e_invoice_user=False, document_type="E_ARCHIVE")

            if len(response_data) == 0:
                return TaxpayerInfo(tax_number=tax_number, is_e_invoice_user=False, document_type="E_ARCHIVE")

            # Parse the first item to safely extract Title if needed
            first_item = NilveraCheckResponseItem(**response_data[0])

            logger.info(
                "Taxpayer check for %s: is_e_invoice_user=True",
                _mask_tax_number(tax_number),
                extra={"correlation_id": correlation_id},
            )

            return TaxpayerInfo(
                tax_number=tax_number,
                is_e_invoice_user=True,
                document_type="E_INVOICE",
                title=first_item.title,
            )

        except NilveraApiError as e:
            logger.error(
                "Failed to check taxpayer status for %s: %s",
                _mask_tax_number(tax_number),
                e,
                extra={"correlation_id": correlation_id},
            )
            raise

    async def get_taxpayer_aliases(self, tax_number: str, correlation_id: str | None = None) -> TaxpayerInfo:
        """
        Get detailed customer info including Aliases for a given VKN/TCKN.
        """
        tax_number = (tax_number or "").strip()

        if not tax_number.isdigit() or len(tax_number) not in (10, 11):
            return TaxpayerInfo(tax_number=tax_number, is_e_invoice_user=False, document_type="E_ARCHIVE")

        try:
            path = f"/general/GlobalCompany/GetGlobalCustomerInfo/{tax_number}?globalUserType=Invoice"
            response_data = await self._client.get(path, correlation_id=correlation_id)

            if not isinstance(response_data, dict):
                logger.warning(
                    "Unexpected response type from GetGlobalCustomerInfo: %s",
                    type(response_data).__name__,
                    extra={"correlation_id": correlation_id},
                )
                return TaxpayerInfo(tax_number=tax_number, is_e_invoice_user=False, document_type="E_ARCHIVE")

            info = NilveraCustomerInfoResponse(**response_data)

            # Extract active aliases (those without a DeletionTime)
            active_aliases = [alias.name for alias in info.aliases if alias.deletion_time is None]

            is_taxpayer = len(active_aliases) > 0

            return TaxpayerInfo(
                tax_number=tax_number,
                is_e_invoice_user=is_taxpayer,
                document_type="E_INVOICE" if is_taxpayer else "E_ARCHIVE",
                title=info.title,
                aliases=active_aliases,
            )

        except NilveraApiError as e:
            logger.error(
                "Failed to get taxpayer aliases for %s: %s",
                _mask_tax_number(tax_number),
                e,
                extra={"correlation_id": correlation_id},
            )
            raise


def _mask_tax_number(tax_number: str) -> str:
    """Mask VKN/TCKN for safe logging (e.g., '***1234')."""
    if not tax_number or len(tax_number) < 4:
        return "****"
    return "***" + tax_number[-4:]
