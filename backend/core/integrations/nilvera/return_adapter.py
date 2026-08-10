import uuid

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
    """Fail-closed adapter for the explicitly gated CreateReturn discovery."""

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
