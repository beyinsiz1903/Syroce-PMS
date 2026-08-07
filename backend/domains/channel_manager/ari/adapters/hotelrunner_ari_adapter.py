"""
HotelRunner ARI Adapter.

Translates ARIDelta into HotelRunner REST API calls.
"""

import logging
import time

from domains.channel_manager.ari.events import ARIDelta, ProviderResult
from domains.channel_manager.providers.hotelrunner.ari_delivery import (
    deliver_hotelrunner_ari,
)

logger = logging.getLogger(__name__)


class HotelRunnerARIAdapter:
    """ARI push adapter for HotelRunner REST API."""

    def __init__(self, provider_client=None):
        """
        Args:
            provider_client: HotelRunnerProvider instance (optional, for live mode)
        """
        self._client = provider_client

    async def push_availability(self, delta: ARIDelta) -> ProviderResult:
        """Push availability update to HotelRunner."""
        return await self._push(delta, "availability")

    async def push_rate(self, delta: ARIDelta) -> ProviderResult:
        """Push rate update to HotelRunner."""
        return await self._push(delta, "rate")

    async def push_restrictions(self, delta: ARIDelta) -> ProviderResult:
        """Push restriction update to HotelRunner."""
        return await self._push(delta, "restriction")

    async def _push(self, delta: ARIDelta, scope: str) -> ProviderResult:
        start = time.time()

        try:
            params = {
                "inv_code": delta.room_type_code,
                "start_date": str(delta.date_from),
                "end_date": str(delta.date_to),
            }

            payload = delta.payload
            if scope == "availability":
                if "availability" in payload:
                    params["availability"] = payload["availability"]
                if "stop_sale" in payload:
                    params["stop_sale"] = payload["stop_sale"]
            elif scope == "rate":
                if "price" in payload:
                    params["price"] = payload["price"]
            elif scope == "restriction":
                for key in ("min_stay", "max_stay", "cta", "ctd", "stop_sale"):
                    if key in payload:
                        params[key] = payload[key]

            delivery = await deliver_hotelrunner_ari(
                delta.tenant_id,
                params,
                provider=self._client,
            )
            duration = int((time.time() - start) * 1000)

            status_codes = {
                "confirmed": 200,
                "blocked": 409,
                "rejected": 429 if delivery.retryable else 422,
                "ambiguous": 503,
                "reconciliation_pending": 202,
                "partial_failure": 502,
            }
            return ProviderResult(
                success=delivery.success,
                provider="hotelrunner",
                status_code=status_codes.get(delivery.state, 500),
                response_payload=delivery.safe_metadata(),
                error=delivery.error_code or None,
                duration_ms=duration,
                retryable=delivery.retryable,
                delivery_state=delivery.state,
                provider_write_count=delivery.provider_write_count,
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            return ProviderResult(
                success=False,
                provider="hotelrunner",
                error=f"ARI_ADAPTER_{type(e).__name__.upper()}",
                duration_ms=duration,
                retryable=False,
                delivery_state="ambiguous",
            )
