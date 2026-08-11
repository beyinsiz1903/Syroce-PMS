import uuid
from typing import Never

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.config import (
    NilveraEndpoints,
    is_nilvera_create_return_enabled,
)
from core.integrations.nilvera.errors import NilveraMalformedResponseError


class NilveraCreateReturnResponse(BaseModel):
    """Validated subset of Nilvera's documented CreateReturn response."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    provider_uuid: uuid.UUID = Field(alias="UUID")
    invoice_number: str | None = Field(default=None, alias="InvoiceNumber", max_length=64)


class NilveraReturnAdapter:
    """Fail-closed adapter for creating and verifying a return draft."""

    def __init__(self, client: NilveraHttpClient):
        self._client = client

    async def create_return(
        self,
        source_provider_uuid: str,
        *,
        correlation_id: str | None = None,
    ) -> NilveraCreateReturnResponse:
        if not is_nilvera_create_return_enabled():
            raise RuntimeError("NILVERA_CREATE_RETURN_DISABLED")

        try:
            normalized_uuid = str(uuid.UUID(source_provider_uuid))
        except (AttributeError, TypeError, ValueError):
            raise ValueError("INVALID_SOURCE_PROVIDER_UUID") from None

        raw_response = await self._client.post(
            NilveraEndpoints.CREATE_PURCHASE_RETURN.format(uuid=normalized_uuid),
            correlation_id=correlation_id,
            retryable=False,
            stage="CREATE_RETURN",
        )
        try:
            return NilveraCreateReturnResponse.model_validate(raw_response)
        except ValidationError as exc:
            raise NilveraMalformedResponseError(
                "CreateReturn response contract is invalid",
                correlation_id=correlation_id,
                http_status=self._client.last_http_status,
                stage="CREATE_RETURN_RESPONSE",
            ) from exc

    async def verify_return_draft(
        self,
        generated_provider_uuid: str,
        *,
        correlation_id: str | None = None,
    ) -> None:
        """Verify the exact created draft exists and has the provider return type."""
        try:
            normalized_uuid = str(uuid.UUID(generated_provider_uuid))
        except (AttributeError, TypeError, ValueError):
            raise ValueError("INVALID_GENERATED_PROVIDER_UUID") from None

        raw_response = await self._client.get(
            NilveraEndpoints.GET_DRAFT_INVOICE_MODEL.format(uuid=normalized_uuid),
            correlation_id=correlation_id,
            retryable=False,
            stage="CREATE_RETURN_DRAFT_VERIFY",
        )
        if not isinstance(raw_response, dict):
            self._raise_invalid_draft(correlation_id)

        invoice_type = self._nested_string(
            raw_response,
            ("InvoiceType",),
            ("InvoiceInfo", "InvoiceType"),
            ("EInvoice", "InvoiceInfo", "InvoiceType"),
        )
        if invoice_type is None or invoice_type.casefold() not in {"iade", "return"}:
            self._raise_invalid_draft(correlation_id)

    @staticmethod
    def _nested_string(payload: dict, *paths: tuple[str, ...]) -> str | None:
        for path in paths:
            value: object = payload
            for key in path:
                if not isinstance(value, dict):
                    value = None
                    break
                value = value.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _raise_invalid_draft(self, correlation_id: str | None) -> Never:
        raise NilveraMalformedResponseError(
            "CreateReturn draft contract is invalid",
            correlation_id=correlation_id,
            http_status=self._client.last_http_status,
            stage="CREATE_RETURN_DRAFT_VERIFY",
        )
