"""
Cross-Provider Reconciliation — Snapshot Collectors
=====================================================

Collect reservation snapshots from HotelRunner and Exely.
Normalize into canonical structure for comparison.

NOTE: Real API calls are MOCKED. When provider credentials are available,
replace the stub methods with actual REST/SOAP calls.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from domains.channel_manager.ingest.normalizer import (
    normalize_hotelrunner, normalize_exely,
)

logger = logging.getLogger("reconciliation.snapshot_collectors")


async def collect_hotelrunner_snapshot(
    connection: Dict[str, Any],
    since_hours: int = 24,
) -> List[Dict[str, Any]]:
    """
    Fetch HotelRunner reservations updated in the last N hours.
    Returns list of canonical reservation dicts.

    In production: calls HotelRunner REST API /reservations endpoint.
    Currently: returns empty list (stub).
    """
    property_id = connection.get("property_id", "")
    logger.info(
        f"HotelRunner snapshot collection: property={property_id}, "
        f"window={since_hours}h [STUB — no real API call]"
    )

    # TODO: Replace with real HotelRunner API call:
    # credentials = connection.get("credentials", {})
    # api_key = credentials.get("api_key", "")
    # base_url = credentials.get("base_url", "https://app.hotelrunner.com/api/v2")
    # since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
    # response = await httpx.get(f"{base_url}/reservations?updated_since={since}", ...)
    # raw_reservations = response.json().get("reservations", [])
    # return [normalize_hotelrunner(r) for r in raw_reservations]

    return []


async def collect_exely_snapshot(
    connection: Dict[str, Any],
    since_hours: int = 24,
) -> List[Dict[str, Any]]:
    """
    Fetch Exely reservations via OTA_ReadRQ updated in the last N hours.
    Returns list of canonical reservation dicts.

    In production: makes SOAP OTA_ReadRQ call to Exely PMSConnect.
    Currently: returns empty list (stub).
    """
    property_id = connection.get("property_id", "")
    logger.info(
        f"Exely snapshot collection: property={property_id}, "
        f"window={since_hours}h [STUB — no real API call]"
    )

    # TODO: Replace with real Exely SOAP call:
    # credentials = connection.get("credentials", {})
    # hotel_id = credentials.get("hotel_id", "")
    # soap_url = credentials.get("soap_url", "")
    # since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
    # xml_response = await soap_client.ota_read_rq(hotel_id, since)
    # raw_reservations = parse_ota_read_response(xml_response)
    # return [normalize_exely(r) for r in raw_reservations]

    return []


SNAPSHOT_COLLECTORS = {
    "hotelrunner": collect_hotelrunner_snapshot,
    "exely": collect_exely_snapshot,
}


async def collect_provider_snapshot(
    provider: str,
    connection: Dict[str, Any],
    since_hours: int = 24,
) -> List[Dict[str, Any]]:
    """Dispatch to the appropriate provider snapshot collector."""
    collector = SNAPSHOT_COLLECTORS.get(provider)
    if not collector:
        logger.warning(f"No snapshot collector for provider: {provider}")
        return []
    return await collector(connection, since_hours)
