"""
Exely ARI Adapter.

Translates ARIDelta into Exely SOAP API calls (OTA_HotelAvailNotifRQ, OTA_HotelRateAmountNotifRQ).
"""
import logging
import time

from domains.channel_manager.ari.events import ARIDelta, ProviderResult

logger = logging.getLogger(__name__)


class ExelyARIAdapter:
    """ARI push adapter for Exely SOAP API."""

    def __init__(self, exely_client=None):
        """
        Args:
            exely_client: ExelyClient instance (optional, for live mode)
        """
        self._client = exely_client

    async def push_availability(self, delta: ARIDelta) -> ProviderResult:
        """Push availability via OTA_HotelAvailNotifRQ."""
        return await self._push(delta, "availability")

    async def push_rate(self, delta: ARIDelta) -> ProviderResult:
        """Push rate via OTA_HotelRateAmountNotifRQ."""
        return await self._push(delta, "rate")

    async def push_restrictions(self, delta: ARIDelta) -> ProviderResult:
        """Push restrictions via OTA_HotelAvailNotifRQ."""
        return await self._push(delta, "restriction")

    async def _push(self, delta: ARIDelta, scope: str) -> ProviderResult:
        start = time.time()

        if not self._client:
            # Dry-run / sandbox mode
            duration = int((time.time() - start) * 1000)
            logger.info(f"[Exely DRY-RUN] {scope} push: {delta.room_type_code} {delta.date_from}→{delta.date_to}")
            return ProviderResult(
                success=True,
                provider="exely",
                status_code=200,
                response_payload={"dry_run": True, "scope": scope},
                duration_ms=duration,
            )

        try:
            payload = delta.payload

            if scope == "availability":
                soap_action = "OTA_HotelAvailNotifRQ"
                request_body = {
                    "AvailStatusMessages": [{
                        "StatusApplicationControl": {
                            "Start": str(delta.date_from),
                            "End": str(delta.date_to),
                            "InvTypeCode": delta.room_type_code,
                            "RatePlanCode": delta.rate_plan_code or "",
                        },
                        "BookingLimit": payload.get("BookingLimit", 0),
                        "RestrictionStatus": payload.get("RestrictionStatus", "Open"),
                    }],
                }
            elif scope == "rate":
                soap_action = "OTA_HotelRateAmountNotifRQ"
                request_body = {
                    "RateAmountMessages": [{
                        "StatusApplicationControl": {
                            "Start": str(delta.date_from),
                            "End": str(delta.date_to),
                            "InvTypeCode": delta.room_type_code,
                            "RatePlanCode": delta.rate_plan_code or "",
                        },
                        "Rates": [{
                            "AmountAfterTax": payload.get("AmountAfterTax", "0"),
                            "CurrencyCode": payload.get("CurrencyCode", "TRY"),
                        }],
                    }],
                }
            elif scope == "restriction":
                soap_action = "OTA_HotelAvailNotifRQ"
                restriction_msg = {
                    "StatusApplicationControl": {
                        "Start": str(delta.date_from),
                        "End": str(delta.date_to),
                        "InvTypeCode": delta.room_type_code,
                        "RatePlanCode": delta.rate_plan_code or "",
                    },
                    "LengthsOfStay": {},
                }
                if "MinLOS" in payload:
                    restriction_msg["LengthsOfStay"]["MinLOS"] = payload["MinLOS"]
                if "MaxLOS" in payload:
                    restriction_msg["LengthsOfStay"]["MaxLOS"] = payload["MaxLOS"]
                if "RestrictionStatus" in payload:
                    restriction_msg["RestrictionStatus"] = payload["RestrictionStatus"]
                request_body = {"AvailStatusMessages": [restriction_msg]}
            else:
                return ProviderResult(
                    success=False, provider="exely",
                    error=f"Unknown scope: {scope}",
                )

            # In live mode, use SOAP client to send
            result = await self._client.send_request(soap_action, request_body)
            duration = int((time.time() - start) * 1000)

            if result.get("success"):
                return ProviderResult(
                    success=True,
                    provider="exely",
                    status_code=200,
                    response_payload=result.get("data"),
                    duration_ms=duration,
                )
            else:
                return ProviderResult(
                    success=False,
                    provider="exely",
                    status_code=result.get("status_code", 500),
                    error=result.get("error", "SOAP error"),
                    duration_ms=duration,
                    retryable=True,
                )

        except Exception as e:
            duration = int((time.time() - start) * 1000)
            return ProviderResult(
                success=False,
                provider="exely",
                error=str(e),
                duration_ms=duration,
                retryable=True,
            )
