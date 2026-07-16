"""Nilvera taxpayer validation and routing service."""

import logging
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .client import NilveraHttpClient
from .errors import NilveraApiError, NilveraValidationError

logger = logging.getLogger("core.integrations.nilvera.taxpayer")


def _safe_validation_summary(error: ValidationError) -> dict:
    """Safely extract validation error locations without exposing sensitive inputs."""
    # include_input=False ensures input values are omitted from the dict representation
    errors = error.errors(include_input=False)
    return {
        "error_count": len(errors),
        "locations": [".".join(str(part) for part in item.get("loc", ())) for item in errors],
    }


def _mask_tax_number(tax_number: str) -> str:
    """Mask VKN/TCKN for safe logging (e.g., '***1234')."""
    if not tax_number or len(tax_number) < 4:
        return "****"
    return "***" + tax_number[-4:]


class TaxpayerCheckResult(BaseModel):
    """Result of checking if a taxpayer is an e-Invoice user."""

    tax_number: str
    is_e_invoice_user: bool
    document_type: Literal["E_INVOICE", "E_ARCHIVE"]
    title: str | None = None


class TaxpayerAliasResult(BaseModel):
    """Result of fetching aliases for a taxpayer."""

    tax_number: str
    aliases: list[str] = Field(default_factory=list)


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
    # In Nilvera's response, the Aliases array is strictly present even if empty,
    # so we enforce its presence without a default_factory to fail-closed if missing.
    aliases: list[NilveraAliasItem] = Field(alias="Aliases")


class NilveraTaxpayerService:
    """Service to check e-Document taxpayer status in Nilvera."""

    def __init__(self, client: NilveraHttpClient):
        self._client = client

    def _validate_tax_number(self, tax_number: str, correlation_id: str | None) -> str:
        """Validate format and length of tax number."""
        clean_number = (tax_number or "").strip()
        if not clean_number or not clean_number.isdigit() or len(clean_number) not in (10, 11):
            logger.warning(
                "Invalid tax number format for %s",
                _mask_tax_number(clean_number),
                extra={"correlation_id": correlation_id},
            )
            raise NilveraValidationError(
                message="Geçersiz Vergi Kimlik Numarası (VKN) veya TCKN",
                correlation_id=correlation_id,
            )
        return clean_number

    async def check_taxpayer(self, tax_number: str, correlation_id: str | None = None) -> TaxpayerCheckResult:
        """
        Check if the given VKN/TCKN is an e-Invoice taxpayer.
        """
        clean_number = self._validate_tax_number(tax_number, correlation_id)

        try:
            path = f"/general/GlobalCompany/Check/TaxNumber/{clean_number}?globalUserType=Invoice"
            response_data = await self._client.get(path, correlation_id=correlation_id)

            if not isinstance(response_data, list):
                logger.error(
                    "Unexpected response type from Check/TaxNumber: %s",
                    type(response_data).__name__,
                    extra={"correlation_id": correlation_id},
                )
                raise NilveraValidationError(
                    message="Nilvera Check servisi geçersiz yanıt döndürdü (Liste bekleniyordu).",
                    correlation_id=correlation_id,
                )

            if len(response_data) == 0:
                return TaxpayerCheckResult(
                    tax_number=clean_number,
                    is_e_invoice_user=False,
                    document_type="E_ARCHIVE",
                )

            try:
                first_item = NilveraCheckResponseItem(**response_data[0])
            except ValidationError as e:
                logger.error(
                    "Malformed response item in Check/TaxNumber for %s",
                    _mask_tax_number(clean_number),
                    extra={
                        "correlation_id": correlation_id,
                        "validation_errors": _safe_validation_summary(e),
                    },
                )
                raise NilveraValidationError(
                    message="Nilvera Check servisi geçersiz öğe döndürdü.",
                    correlation_id=correlation_id,
                ) from e

            return TaxpayerCheckResult(
                tax_number=clean_number,
                is_e_invoice_user=True,
                document_type="E_INVOICE",
                title=first_item.title,
            )

        except NilveraApiError as e:
            logger.error(
                "Failed to check taxpayer status for %s: %s",
                _mask_tax_number(clean_number),
                e.__class__.__name__,
                extra={"correlation_id": correlation_id},
            )
            raise

    async def get_taxpayer_aliases(self, tax_number: str, correlation_id: str | None = None) -> TaxpayerAliasResult:
        """
        Get detailed customer info including active Aliases for a given VKN/TCKN.
        """
        clean_number = self._validate_tax_number(tax_number, correlation_id)

        try:
            path = f"/general/GlobalCompany/GetGlobalCustomerInfo/{clean_number}?globalUserType=Invoice"
            response_data = await self._client.get(path, correlation_id=correlation_id)

            if not isinstance(response_data, dict):
                logger.error(
                    "Unexpected response type from GetGlobalCustomerInfo: %s",
                    type(response_data).__name__,
                    extra={"correlation_id": correlation_id},
                )
                raise NilveraValidationError(
                    message="Nilvera CustomerInfo servisi geçersiz yanıt döndürdü (Obje bekleniyordu).",
                    correlation_id=correlation_id,
                )

            try:
                info = NilveraCustomerInfoResponse(**response_data)
            except ValidationError as e:
                logger.error(
                    "Malformed response in GetGlobalCustomerInfo for %s",
                    _mask_tax_number(clean_number),
                    extra={
                        "correlation_id": correlation_id,
                        "validation_errors": _safe_validation_summary(e),
                    },
                )
                raise NilveraValidationError(
                    message="Nilvera CustomerInfo servisi geçersiz öğe döndürdü.",
                    correlation_id=correlation_id,
                ) from e

            # Extract active aliases (those without a DeletionTime)
            active_aliases = [alias.name for alias in info.aliases if alias.deletion_time is None]

            return TaxpayerAliasResult(
                tax_number=clean_number,
                aliases=active_aliases,
            )

        except NilveraApiError as e:
            logger.error(
                "Failed to get taxpayer aliases for %s: %s",
                _mask_tax_number(clean_number),
                e.__class__.__name__,
                extra={"correlation_id": correlation_id},
            )
            raise
