"""
Cross-Provider Reconciliation — Snapshot Collectors
=====================================================

Collect reservation snapshots from HotelRunner and Exely.
Normalize into canonical structure for comparison.

Uses real provider API clients with graceful error handling.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from domains.channel_manager.ingest.normalizer import (
    normalize_hotelrunner,
)

logger = logging.getLogger("reconciliation.snapshot_collectors")


async def collect_hotelrunner_snapshot(
    connection: dict[str, Any],
    since_hours: int = 24,
) -> list[dict[str, Any]]:
    """
    Fetch HotelRunner reservations updated in the last N hours.
    Returns list of canonical reservation dicts.
    Uses HotelRunnerProvider for real API calls with pagination.
    """
    from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider

    property_id = connection.get("property_id", "")
    credentials = connection.get("credentials", {})
    token = credentials.get("token") or credentials.get("api_key", "")
    hr_id = credentials.get("hr_id") or credentials.get("hotel_id", "")

    if not token or not hr_id:
        logger.warning(f"HotelRunner snapshot: missing credentials for property={property_id}")
        return []

    environment = connection.get("environment", "production")
    provider = HotelRunnerProvider(token=token, hr_id=hr_id, environment=environment)
    since = (datetime.now(UTC) - timedelta(hours=since_hours)).strftime("%Y-%m-%d")

    logger.info(f"HotelRunner snapshot: property={property_id}, window={since_hours}h, since={since}")

    all_reservations: list[dict[str, Any]] = []
    page = 1
    max_pages = 20

    while page <= max_pages:
        try:
            result = await provider.get_reservations(
                undelivered=False,
                from_last_update_date=since,
                per_page=50,
                page=page,
            )
        except Exception as e:
            logger.error(f"HotelRunner API error (page {page}): {e}")
            break

        if not result.get("success"):
            logger.error(f"HotelRunner snapshot failed: {result.get('error', 'unknown')}")
            break

        data = result.get("data", {})
        reservations = data.get("reservations", [])

        for raw in reservations:
            try:
                canonical = normalize_hotelrunner(raw)
                all_reservations.append(canonical)
            except Exception as e:
                ext_id = raw.get("hr_number", "?")
                logger.warning(f"Normalize error for HR reservation {ext_id}: {e}")

        total_pages = data.get("pages", 1)
        if page >= total_pages:
            break
        page += 1

    logger.info(f"HotelRunner snapshot complete: property={property_id}, reservations={len(all_reservations)}")
    return all_reservations


async def collect_exely_snapshot(
    connection: dict[str, Any],
    since_hours: int = 24,
) -> list[dict[str, Any]]:
    """Fail closed because PMSConnect has no historical reservation snapshot read."""
    del connection, since_hours
    raise RuntimeError("EXELY_RESERVATION_SNAPSHOT_UNSUPPORTED_BY_CONTRACT")


SNAPSHOT_COLLECTORS = {
    "hotelrunner": collect_hotelrunner_snapshot,
    "exely": collect_exely_snapshot,
}


async def collect_provider_snapshot(
    provider: str,
    connection: dict[str, Any],
    since_hours: int = 24,
) -> list[dict[str, Any]]:
    """Dispatch to the appropriate provider snapshot collector."""
    collector = SNAPSHOT_COLLECTORS.get(provider)
    if not collector:
        logger.warning(f"No snapshot collector for provider: {provider}")
        return []
    return await collector(connection, since_hours)
