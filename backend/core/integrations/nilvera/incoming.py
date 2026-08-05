from datetime import datetime, timedelta

from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.errors import NilveraValidationError
from core.integrations.nilvera.incoming_mapper import IncomingInvoicePage, NilveraIncomingMapper


class NilveraIncomingService:
    def __init__(self, client: NilveraHttpClient):
        self._client = client

    async def fetch_incoming_invoices(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> IncomingInvoicePage:
        """
        Fetches incoming invoices from the Nilvera Sandbox `/einvoice/Purchase` endpoint.
        """
        # Timezone validation
        if start_date.tzinfo is None or end_date.tzinfo is None:
            raise NilveraValidationError("start_date and end_date must be timezone-aware")

        # Date range logic
        if start_date > end_date:
            raise NilveraValidationError("start_date cannot be after end_date")

        if (end_date - start_date) > timedelta(days=31):
            raise NilveraValidationError("Date range cannot exceed 31 days")

        # Pagination validation
        if page < 1:
            raise NilveraValidationError("page must be at least 1")
        if not (1 <= page_size <= 100):
            raise NilveraValidationError("page_size must be between 1 and 100")

        # ISO8601 formatting for URL (e.g. 2026-08-01T00:00:00.000Z)
        start_date_str = start_date.isoformat()
        end_date_str = end_date.isoformat()

        query_params = {
            "StartDate": start_date_str,
            "EndDate": end_date_str,
            "Page": str(page),
            "Take": str(page_size),
        }

        # Do not log the raw response or its JSON payload to avoid PII leaks
        response_json = await self._client.get("/einvoice/Purchase", params=query_params)

        # Delegate parsing and fail-closed security to the offline mapper
        return NilveraIncomingMapper.map_page(response_json, page=page, page_size=page_size)
