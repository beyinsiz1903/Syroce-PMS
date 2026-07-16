"""Nilvera e-Invoice series discovery service."""

import logging
from datetime import datetime

from pydantic import BaseModel, Field, ValidationError

from .client import NilveraHttpClient
from .errors import NilveraApiError, NilveraValidationError

logger = logging.getLogger("core.integrations.nilvera.series")


def _safe_validation_summary(error: ValidationError) -> dict:
    """Safely extract validation error locations without exposing sensitive inputs."""
    errors = error.errors(include_input=False)
    return {
        "error_count": len(errors),
        "locations": [".".join(str(part) for part in item.get("loc", ())) for item in errors],
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class NilveraSeriesDetail(BaseModel):
    """Year-level detail for a single e-Invoice series."""

    id: int = Field(alias="ID")
    year: str = Field(alias="Year")
    ordinal_number: int = Field(alias="OrdinalNumber")
    last_issue_date: datetime | None = Field(None, alias="LastIssueDate")


class NilveraSeriesItem(BaseModel):
    """A single e-Invoice series as returned by GET /einvoice/Series."""

    id: int = Field(alias="ID")
    name: str = Field(alias="Name")
    is_default: bool = Field(alias="IsDefault")
    is_active: bool = Field(alias="IsActive")
    created_date: datetime | None = Field(None, alias="CreatedDate")
    # Details is required by the observed API contract; enforced without default_factory
    # so that a missing field causes a schema error (fail-closed).
    details: list[NilveraSeriesDetail] = Field(alias="Details")


class NilveraSeriesPage(BaseModel):
    """Paginated response from GET /einvoice/Series."""

    page: int = Field(alias="Page")
    page_size: int = Field(alias="PageSize")
    total_count: int = Field(alias="TotalCount")
    total_pages: int = Field(alias="TotalPages")
    # Content is required; fail-closed if absent.
    content: list[NilveraSeriesItem] = Field(alias="Content")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NilveraSeriesService:
    """Read-only service for listing e-Invoice series from Nilvera.

    Covers GET /einvoice/Series per the official Nilvera API v1 contract.
    The endpoint also supports Search, SortColumn and SortType query parameters;
    these are intentionally out of scope for this phase and not implemented here.
    Sending, mapping, routing and e-Archive series are also out of scope.
    """

    def __init__(self, client: NilveraHttpClient) -> None:
        self._client = client

    async def list_einvoice_series(
        self,
        *,
        is_active: bool | None = None,
        is_default: bool | None = None,
        page: int = 1,
        page_size: int = 50,
        correlation_id: str | None = None,
    ) -> NilveraSeriesPage:
        """Fetch a page of e-Invoice series from Nilvera.

        The official Nilvera API contract additionally accepts Search, SortColumn
        and SortType parameters; those are not exposed here (out of scope).

        Args:
            is_active: When provided, filters to active (True) or passive (False) series.
            is_default: When provided, filters to default (True) or non-default (False) series.
            page: 1-indexed page number. Must be >= 1 (default: 1).
            page_size: Records per page. Must be >= 1 (default: 50).
            correlation_id: Optional correlation ID for log tracing.

        Returns:
            NilveraSeriesPage with pagination metadata and series list.
            An empty ``content`` list is valid and means no series match the filter;
            alias/default selection is intentionally deferred to the caller.

        Raises:
            NilveraValidationError: If pagination inputs are invalid, or if the
                provider returns an unexpected response structure.
            NilveraApiError: On network or HTTP-level failures.
        """
        if page < 1:
            raise NilveraValidationError(
                message="Geçersiz sayfalama: page en az 1 olmalıdır.",
                correlation_id=correlation_id,
            )
        if page_size < 1:
            raise NilveraValidationError(
                message="Geçersiz sayfalama: page_size en az 1 olmalıdır.",
                correlation_id=correlation_id,
            )

        params: dict[str, str | int | bool] = {"Page": page, "PageSize": page_size}
        if is_active is not None:
            params["IsActive"] = is_active
        if is_default is not None:
            params["IsDefault"] = is_default

        # Build query string manually so NilveraHttpClient.get() can accept it.
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"/einvoice/Series?{qs}"

        try:
            response_data = await self._client.get(path, correlation_id=correlation_id)
        except NilveraApiError:
            logger.error(
                "Failed to fetch e-Invoice series",
                extra={"correlation_id": correlation_id},
            )
            raise

        if not isinstance(response_data, dict):
            logger.error(
                "Unexpected response type from /einvoice/Series: %s",
                type(response_data).__name__,
                extra={"correlation_id": correlation_id},
            )
            raise NilveraValidationError(
                message="Nilvera Series servisi geçersiz yanıt döndürdü (Obje bekleniyordu).",
                correlation_id=correlation_id,
            )

        try:
            page_result = NilveraSeriesPage(**response_data)
        except ValidationError as exc:
            logger.error(
                "Malformed response from /einvoice/Series",
                extra={
                    "correlation_id": correlation_id,
                    "validation_errors": _safe_validation_summary(exc),
                },
            )
            raise NilveraValidationError(
                message="Nilvera Series servisi geçersiz yapı döndürdü.",
                correlation_id=correlation_id,
            ) from None

        return page_result
