"""
HotelRunner ARI Adapter.

Translates ARIDelta into HotelRunner REST API calls.
"""
import logging
import time

from domains.channel_manager.ari.events import ARIDelta, ProviderResult

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

        if not self._client:
            # Dry-run / sandbox mode
            duration = int((time.time() - start) * 1000)
            logger.info(f"[HotelRunner DRY-RUN] {scope} push: {delta.room_type_code} {delta.date_from}→{delta.date_to}")
            return ProviderResult(
                success=True,
                provider="hotelrunner",
                status_code=200,
                response_payload={"dry_run": True, "scope": scope},
                duration_ms=duration,
            )

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
                for key in ("min_stay", "cta", "ctd", "stop_sale"):
                    if key in payload:
                        params[key] = payload[key]

            result = await self._client.update_room(**params)
            duration = int((time.time() - start) * 1000)

            if result.get("success"):
                return ProviderResult(
                    success=True,
                    provider="hotelrunner",
                    status_code=200,
                    response_payload=result.get("data"),
                    duration_ms=duration,
                )
            else:
                status_code = 500
                error = result.get("error", "Unknown error")
                if "429" in str(error) or "rate" in str(error).lower():
                    status_code = 429
                return ProviderResult(
                    success=False,
                    provider="hotelrunner",
                    status_code=status_code,
                    error=error,
                    duration_ms=duration,
                    retryable=status_code >= 500 or status_code == 429,
                )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            return ProviderResult(
                success=False,
                provider="hotelrunner",
                error=str(e),
                duration_ms=duration,
                retryable=True,
            )
