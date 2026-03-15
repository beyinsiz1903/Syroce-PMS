"""
Reservation Ingest — Background Workers
========================================

Worker 1: HotelRunner Pull   (5-15 min interval)
Worker 2: Exely Pull          (5-10 min interval)
Worker 3: Ingest Processor    (processes pending raw events)
Worker 4: Replay Worker       (retries failed events)
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from core.database import db

from domains.channel_manager import unified_repository as repo
from domains.channel_manager.data_model import (
    ConnectorProvider, RawChannelEvent, RawEventSource, ProcessingStatus,
    COLL_RAW_CHANNEL_EVENTS,
)
from domains.channel_manager.ingest.normalizer import (
    extract_hotelrunner_identity, extract_exely_identity,
)
from domains.channel_manager.ingest.pipeline import process_event

logger = logging.getLogger("ingest.workers")

# ── Worker State ──────────────────────────────────────────────────────

_worker_state = {
    "hotelrunner_pull": {
        "running": False,
        "last_run": None,
        "last_cursor": None,
        "interval_seconds": 600,  # 10 min default
        "events_fetched": 0,
        "errors": 0,
    },
    "exely_pull": {
        "running": False,
        "last_run": None,
        "last_cursor": None,
        "interval_seconds": 300,  # 5 min default
        "events_fetched": 0,
        "errors": 0,
    },
    "ingest_processor": {
        "running": False,
        "last_run": None,
        "interval_seconds": 10,  # 10 sec
        "events_processed": 0,
        "errors": 0,
    },
    "replay_worker": {
        "running": False,
        "last_run": None,
        "interval_seconds": 300,  # 5 min
        "events_replayed": 0,
        "errors": 0,
    },
}

SAFETY_WINDOW_MINUTES = 5


def get_worker_states() -> Dict[str, Any]:
    return {k: {**v} for k, v in _worker_state.items()}


# ══════════════════════════════════════════════════════════════════════
# Worker 1: HotelRunner Pull
# ══════════════════════════════════════════════════════════════════════

async def hotelrunner_pull_once() -> Dict[str, Any]:
    """
    Pull reservations from HotelRunner REST API for all active connections.
    Fetches updated reservations since last cursor, persists into raw_channel_events.
    """
    from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider
    from domains.channel_manager.data_model import COLL_PROVIDER_CONNECTIONS

    state = _worker_state["hotelrunner_pull"]
    if state["running"]:
        return {"fetched": 0, "errors": 0, "provider": "hotelrunner", "status": "already_running"}
    state["running"] = True
    now = datetime.now(timezone.utc)
    result = {"fetched": 0, "errors": 0, "provider": "hotelrunner"}

    try:
        last_cursor = state["last_cursor"]
        if last_cursor:
            updated_since = last_cursor - timedelta(minutes=SAFETY_WINDOW_MINUTES)
        else:
            updated_since = now - timedelta(hours=24)

        since_str = updated_since.strftime("%Y-%m-%d")

        connections = await db[COLL_PROVIDER_CONNECTIONS].find(
            {"provider": "hotelrunner", "status": "active", "sync_reservations": True},
            {"_id": 0},
        ).to_list(50)

        if not connections:
            connections = await db[COLL_PROVIDER_CONNECTIONS].find(
                {"provider": "hotelrunner"}, {"_id": 0},
            ).to_list(50)

        for conn in connections:
            credentials = conn.get("credentials", {})
            token = credentials.get("token") or credentials.get("api_key", "")
            hr_id = credentials.get("hr_id") or credentials.get("hotel_id", "")
            tenant_id = conn.get("tenant_id", "")
            property_id = conn.get("property_id", "")
            connection_id = conn.get("id", "")

            if not token or not hr_id:
                logger.warning(f"HotelRunner pull: missing credentials for {property_id}")
                continue

            try:
                provider = HotelRunnerProvider(token=token, hr_id=hr_id)
                page = 1
                fetched_events = []

                while page <= 20:
                    api_result = await provider.get_reservations(
                        undelivered=True,
                        from_last_update_date=since_str,
                        per_page=50,
                        page=page,
                    )
                    if not api_result.get("success"):
                        logger.error(f"HotelRunner API error: {api_result.get('error')}")
                        result["errors"] += 1
                        break

                    data = api_result.get("data", {})
                    reservations = data.get("reservations", [])
                    fetched_events.extend(reservations)

                    if page >= data.get("pages", 1):
                        break
                    page += 1

                if fetched_events:
                    count = await _persist_pull_events(
                        "hotelrunner", fetched_events,
                        tenant_id, property_id, connection_id,
                    )
                    result["fetched"] += count
                    state["events_fetched"] += count

                logger.info(
                    f"HotelRunner pull [{property_id}]: "
                    f"fetched {len(fetched_events)} reservations"
                )
            except Exception as e:
                result["errors"] += 1
                logger.error(f"HotelRunner pull error for {property_id}: {e}")

        state["last_cursor"] = now
        state["last_run"] = now.isoformat()

    except Exception as e:
        state["errors"] += 1
        result["errors"] += 1
        result["error_message"] = str(e)
        logger.error(f"HotelRunner pull error: {e}")
    finally:
        state["running"] = False

    return result


async def _persist_pull_events(
    provider: str,
    events: List[Dict[str, Any]],
    tenant_id: str,
    property_id: str,
    connection_id: str = "",
) -> int:
    """Persist pulled events into raw_channel_events."""
    count = 0
    for payload in events:
        if provider == "hotelrunner":
            identity = extract_hotelrunner_identity(payload)
            event_type = "reservation_pull"
        else:
            identity = extract_exely_identity(payload)
            event_type = "reservation_pull"

        payload_hash = RawChannelEvent.compute_payload_hash(payload)

        event = RawChannelEvent(
            tenant_id=tenant_id,
            property_id=property_id,
            provider=ConnectorProvider(provider),
            connection_id=connection_id,
            event_type=event_type,
            provider_event_id=identity["provider_event_id"],
            external_reservation_id=identity["external_reservation_id"],
            provider_version=identity["provider_version"],
            provider_last_modified_at=identity["provider_last_modified_at"],
            raw_payload=payload,
            payload_hash=payload_hash,
            received_via=RawEventSource.PULL,
            processing_status=ProcessingStatus.PENDING,
        )
        await repo.insert_raw_event(event.to_doc())
        count += 1

    return count


# ══════════════════════════════════════════════════════════════════════
# Worker 2: Exely Pull
# ══════════════════════════════════════════════════════════════════════

async def exely_pull_once() -> Dict[str, Any]:
    """
    Pull reservations from Exely via OTA_ReadRQ SOAP for all active connections.
    Fetches updated reservations since last cursor, persists into raw_channel_events.
    """
    from domains.channel_manager.providers.exely.exely_client import ExelyClient
    from domains.channel_manager.data_model import COLL_PROVIDER_CONNECTIONS

    state = _worker_state["exely_pull"]
    if state["running"]:
        return {"fetched": 0, "errors": 0, "provider": "exely", "status": "already_running"}
    state["running"] = True
    now = datetime.now(timezone.utc)
    result = {"fetched": 0, "errors": 0, "provider": "exely"}

    try:
        last_cursor = state["last_cursor"]
        if last_cursor:
            updated_since = last_cursor - timedelta(minutes=SAFETY_WINDOW_MINUTES)
        else:
            updated_since = now - timedelta(hours=24)

        from_date = updated_since.strftime("%Y-%m-%d")
        to_date = now.strftime("%Y-%m-%d")

        connections = await db[COLL_PROVIDER_CONNECTIONS].find(
            {"provider": "exely", "status": "active", "sync_reservations": True},
            {"_id": 0},
        ).to_list(50)

        if not connections:
            connections = await db[COLL_PROVIDER_CONNECTIONS].find(
                {"provider": "exely"}, {"_id": 0},
            ).to_list(50)

        for conn in connections:
            credentials = conn.get("credentials", {})
            username = credentials.get("username", "")
            password = credentials.get("password", "")
            hotel_code = credentials.get("hotel_code") or credentials.get("hotel_id", "")
            endpoint_url = credentials.get("endpoint_url") or credentials.get("soap_url", "")
            tenant_id = conn.get("tenant_id", "")
            property_id = conn.get("property_id", "")
            connection_id = conn.get("id", "")

            if not username or not password or not hotel_code:
                logger.warning(f"Exely pull: missing credentials for {property_id}")
                continue

            try:
                client_kwargs = {"username": username, "password": password, "hotel_code": hotel_code}
                if endpoint_url:
                    client_kwargs["endpoint_url"] = endpoint_url
                client = ExelyClient(**client_kwargs)

                api_result = await client.pull_reservations(
                    from_date=from_date, to_date=to_date,
                )

                if not api_result.get("success"):
                    logger.error(f"Exely API error: {api_result.get('error')}")
                    result["errors"] += 1
                    continue

                raw_reservations = api_result.get("reservations", [])

                if raw_reservations:
                    exely_events = _convert_exely_parsed_to_raw(raw_reservations)
                    count = await _persist_pull_events(
                        "exely", exely_events,
                        tenant_id, property_id, connection_id,
                    )
                    result["fetched"] += count
                    state["events_fetched"] += count

                logger.info(
                    f"Exely pull [{property_id}]: "
                    f"fetched {len(raw_reservations)} reservations"
                )
            except Exception as e:
                result["errors"] += 1
                logger.error(f"Exely pull error for {property_id}: {e}")

        state["last_cursor"] = now
        state["last_run"] = now.isoformat()

    except Exception as e:
        state["errors"] += 1
        result["errors"] += 1
        result["error_message"] = str(e)
        logger.error(f"Exely pull error: {e}")
    finally:
        state["running"] = False

    return result


def _convert_exely_parsed_to_raw(parsed_reservations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert Exely response_parser output to the raw format expected
    by extract_exely_identity (OTA-style dict with UniqueID, ResStatus, etc.).
    """
    events = []
    for parsed in parsed_reservations:
        rooms = parsed.get("rooms", [])
        first_room = rooms[0] if rooms else {}
        status_raw = (parsed.get("status") or "Commit")
        status_map = {"confirmed": "Commit", "modified": "Modify", "cancelled": "Cancel"}
        ota_status = status_map.get(status_raw.lower(), status_raw)

        events.append({
            "UniqueID": parsed.get("reservation_id", ""),
            "ResStatus": ota_status,
            "LastModifyDateTime": parsed.get("last_modify", ""),
            "RoomStay": {
                "RoomTypeCode": first_room.get("room_type_code", ""),
                "RatePlanCode": first_room.get("rate_plan_code", ""),
                "StartDate": parsed.get("checkin_date", ""),
                "EndDate": parsed.get("checkout_date", ""),
            },
            "GuestCount": {
                "adults": first_room.get("adults", 1),
                "children": first_room.get("children", 0),
            },
            "ResGuest": {
                "GivenName": parsed.get("guest_firstname", ""),
                "Surname": parsed.get("guest_lastname", ""),
                "Email": parsed.get("guest_email", ""),
                "Phone": parsed.get("guest_phone", ""),
            },
            "Total": {
                "Amount": float(parsed.get("total", 0)),
                "CurrencyCode": parsed.get("currency", "TRY"),
            },
            "Source": parsed.get("channel", "exely"),
        })
    return events


# ══════════════════════════════════════════════════════════════════════
# Worker 3: Ingest Processor
# ══════════════════════════════════════════════════════════════════════

async def ingest_processor_once(batch_size: int = 50) -> Dict[str, Any]:
    """
    Process pending raw events through the ingest pipeline.
    """
    state = _worker_state["ingest_processor"]
    state["running"] = True
    now = datetime.now(timezone.utc)
    result = {
        "processed": 0,
        "created": 0,
        "updated": 0,
        "cancelled": 0,
        "skipped": 0,
        "failed": 0,
        "pending_mapping": 0,
        "manual_review": 0,
    }

    try:
        pending = await repo.get_pending_raw_events(limit=batch_size)
        for event in pending:
            pipeline_result = await process_event(event)
            result["processed"] += 1
            decision = pipeline_result.decision
            if decision == "create":
                result["created"] += 1
            elif decision == "update":
                result["updated"] += 1
            elif decision == "cancel":
                result["cancelled"] += 1
            elif decision == "skip":
                result["skipped"] += 1
            elif decision == "pending_mapping":
                result["pending_mapping"] += 1
                result["failed"] += 1
            elif decision == "manual_review":
                result["manual_review"] += 1
                result["failed"] += 1

        state["events_processed"] += result["processed"]
        state["last_run"] = now.isoformat()
        logger.info(f"Ingest processor: {result}")

    except Exception as e:
        state["errors"] += 1
        result["error"] = str(e)
        logger.error(f"Ingest processor error: {e}")
    finally:
        state["running"] = False

    return result


# ══════════════════════════════════════════════════════════════════════
# Worker 4: Replay Worker
# ══════════════════════════════════════════════════════════════════════

async def replay_worker_once(batch_size: int = 20) -> Dict[str, Any]:
    """
    Retry failed events by resetting their status to pending.
    """
    state = _worker_state["replay_worker"]
    state["running"] = True
    now = datetime.now(timezone.utc)
    result = {"replayed": 0, "errors": 0}

    try:
        failed = await repo.get_failed_events(limit=batch_size)
        for event in failed:
            # Reset to pending for reprocessing
            await repo.update_raw_event_status(event["id"], "pending")
            result["replayed"] += 1

        state["events_replayed"] += result["replayed"]
        state["last_run"] = now.isoformat()
        logger.info(f"Replay worker: replayed {result['replayed']} events")

    except Exception as e:
        state["errors"] += 1
        result["errors"] = 1
        logger.error(f"Replay worker error: {e}")
    finally:
        state["running"] = False

    return result


# ══════════════════════════════════════════════════════════════════════
# Manual Trigger API helpers
# ══════════════════════════════════════════════════════════════════════

async def trigger_ingest_now() -> Dict[str, Any]:
    """Manually trigger the ingest processor."""
    return await ingest_processor_once()


async def trigger_replay_now() -> Dict[str, Any]:
    """Manually trigger the replay worker."""
    return await replay_worker_once()


async def trigger_pull(provider: str) -> Dict[str, Any]:
    """Manually trigger a pull worker."""
    if provider == "hotelrunner":
        return await hotelrunner_pull_once()
    elif provider == "exely":
        return await exely_pull_once()
    else:
        return {"error": f"Unknown provider: {provider}"}
