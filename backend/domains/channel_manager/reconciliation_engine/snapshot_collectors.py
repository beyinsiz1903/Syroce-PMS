"""
Cross-Provider Reconciliation — Snapshot Collectors
=====================================================

Collect reservation snapshots from HotelRunner and Exely.
Normalize into canonical structure for comparison.

Uses real provider API clients with graceful error handling.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from domains.channel_manager.ingest.normalizer import (
    normalize_hotelrunner,
)

logger = logging.getLogger("reconciliation.snapshot_collectors")


async def collect_hotelrunner_snapshot(
    connection: Dict[str, Any],
    since_hours: int = 24,
) -> List[Dict[str, Any]]:
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
        logger.warning(
            f"HotelRunner snapshot: missing credentials for property={property_id}"
        )
        return []

    provider = HotelRunnerProvider(token=token, hr_id=hr_id)
    since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime("%Y-%m-%d")

    logger.info(
        f"HotelRunner snapshot: property={property_id}, "
        f"window={since_hours}h, since={since}"
    )

    all_reservations: List[Dict[str, Any]] = []
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
            logger.error(
                f"HotelRunner snapshot failed: {result.get('error', 'unknown')}"
            )
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

    logger.info(
        f"HotelRunner snapshot complete: property={property_id}, "
        f"reservations={len(all_reservations)}"
    )
    return all_reservations


async def collect_exely_snapshot(
    connection: Dict[str, Any],
    since_hours: int = 24,
) -> List[Dict[str, Any]]:
    """
    Fetch Exely reservations via OTA_ReadRQ updated in the last N hours.
    Returns list of canonical reservation dicts.
    Uses ExelyProvider for real SOAP API calls.
    """
    from domains.channel_manager.providers.exely import ExelyProvider

    property_id = connection.get("property_id", "")
    credentials = connection.get("credentials", {})
    username = credentials.get("username", "")
    password = credentials.get("password", "")
    hotel_code = credentials.get("hotel_code") or credentials.get("hotel_id", "")
    endpoint_url = credentials.get("endpoint_url") or credentials.get("soap_url", "")

    if not username or not password or not hotel_code:
        logger.warning(
            f"Exely snapshot: missing credentials for property={property_id}"
        )
        return []

    provider_kwargs = {"username": username, "password": password, "hotel_code": hotel_code}
    if endpoint_url:
        provider_kwargs["endpoint_url"] = endpoint_url
    provider = ExelyProvider(**provider_kwargs)

    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    from_date = since.strftime("%Y-%m-%d")
    to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info(
        f"Exely snapshot: property={property_id}, "
        f"window={since_hours}h, range={from_date} -> {to_date}"
    )

    try:
        result = await provider.legacy_pull_reservations(from_date=from_date, to_date=to_date)
    except Exception as e:
        logger.error(f"Exely SOAP error: {e}")
        return []

    if not result.get("success"):
        logger.error(f"Exely snapshot failed: {result.get('error', 'unknown')}")
        return []

    raw_reservations = result.get("reservations", [])
    canonical_list: List[Dict[str, Any]] = []

    for raw in raw_reservations:
        try:
            canonical = _exely_parsed_to_canonical(raw)
            canonical_list.append(canonical)
        except Exception as e:
            ext_id = raw.get("reservation_id", "?")
            logger.warning(f"Normalize error for Exely reservation {ext_id}: {e}")

    logger.info(
        f"Exely snapshot complete: property={property_id}, "
        f"reservations={len(canonical_list)}"
    )
    return canonical_list


def _exely_parsed_to_canonical(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert Exely response_parser output to the canonical format
    expected by the comparison engine.

    The response_parser returns dicts with keys like:
        reservation_id, status, guest_name, checkin_date, checkout_date,
        total, currency, rooms, channel, etc.

    The comparison engine expects:
        external_reservation_id, status, guest_name, check_in, check_out,
        total_amount, currency, room_type_code, rate_plan_code, adults, children
    """
    status_raw = (parsed.get("status") or "Commit").lower()
    status_map = {
        "commit": "confirmed",
        "confirmed": "confirmed",
        "modify": "modified",
        "modified": "modified",
        "cancel": "cancelled",
        "cancelled": "cancelled",
        "book": "confirmed",
    }

    rooms = parsed.get("rooms", [])
    first_room = rooms[0] if rooms else {}

    return {
        "external_reservation_id": parsed.get("reservation_id", ""),
        "provider": "exely",
        "guest_name": parsed.get("guest_name", ""),
        "guest_email": parsed.get("guest_email", ""),
        "guest_phone": parsed.get("guest_phone", ""),
        "check_in": parsed.get("checkin_date", ""),
        "check_out": parsed.get("checkout_date", ""),
        "adults": first_room.get("adults", 1),
        "children": first_room.get("children", 0),
        "room_type_code": first_room.get("room_type_code", ""),
        "rate_plan_code": first_room.get("rate_plan_code", ""),
        "currency": parsed.get("currency", "TRY"),
        "total_amount": float(parsed.get("total", 0.0)),
        "status": status_map.get(status_raw, "confirmed"),
        "provider_last_modified_at": parsed.get("last_modify", ""),
        "source_system": parsed.get("channel", "exely"),
        "source_payload_ref": parsed.get("reservation_id", ""),
    }


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
