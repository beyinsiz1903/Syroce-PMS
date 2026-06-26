"""
OTA-002: Outbox Dispatcher — Provider Routing & Error Classification
=====================================================================
Routes outbox events to the correct provider adapter (Exely / HotelRunner)
or fans out to all active connectors via EventSyncService.

Error classification determines retry vs. permanent failure.
"""
import logging
from typing import Any

logger = logging.getLogger("core.outbox_dispatcher")


# Event type → channel manager event mapping for EventSyncService
EVENT_TYPE_TO_CM_EVENT = {
    "booking.created.v1": "booking_created",
    "booking.cancelled.v1": "booking_cancelled",
    # CM-Hardening Turu #3a + #3b (May 2026): canonical CM event name for no-show.
    # As of Turu #3b, EventSyncService supports `booking_no_show` and routes it
    # to the same InventorySyncService.trigger_inventory_sync path as
    # `booking_cancelled` (Strategy A — inventory recompute, no provider-level
    # booking/no-show endpoint). HotelRunner side: room is republished as
    # sellable via PUT /api/v2/apps/rooms/daily. Exely parity is Turu #3c.
    "booking.no_show.v1": "booking_no_show",
    "booking.modified.v1": "booking_modified",
    "inventory.blocked.v1": "room_blocked",
    "inventory.released.v1": "room_unblocked",
    "inventory.availability.updated.v1": "booking_modified",
    "restriction.updated.v1": "restriction_changed",
    "rate.updated.v1": "rate_changed",
    # Legacy mappings
    "reservation.created.v1": "booking_created",
    "reservation.cancelled.v1": "booking_cancelled",
    "reservation.modified.v1": "booking_modified",
}


async def dispatch_outbox_event(event: dict[str, Any]) -> tuple[bool, str]:
    """
    Dispatch an outbox event to the appropriate provider(s).

    Returns:
        (success: bool, message: str)
        - (True, "...") on successful delivery
        - (False, "retryable: ...") for transient failures
        - (False, "permanent: ...") for non-retryable failures
    """
    event_type = event.get("event_type", "")
    tenant_id = event.get("tenant_id", "")

    if not tenant_id:
        return False, "permanent: missing tenant_id"

    # Internal-Consistency (IC) events — Task #389. These drive the async
    # POS -> folio posting (Outbox/Compensation) ENTIRELY inside this system and
    # MUST be routed here BEFORE any channel-manager mapping so they never reach
    # EventSyncService / OTA (external_calls stays []).
    from core.outbox_service import IC_OUTBOX_EVENT_TYPES

    if event_type in IC_OUTBOX_EVENT_TYPES:
        from core.pos_folio_consumer import handle_ic_pos_event

        return await handle_ic_pos_event(event)

    # Agency v1 outbound webhooks (Adim 4, ADR Karar 6). These deliver a signed
    # webhook to a partner agency ENTIRELY at the SXI edge and MUST be routed
    # here BEFORE any channel-manager mapping so they never reach
    # EventSyncService / OTA (external_calls stays []; agency<->tenant mapping
    # stays out of the PMS core per Karar 7).
    from core.agency_webhook import AGENCY_OUTBOX_EVENT_TYPES

    if event_type in AGENCY_OUTBOX_EVENT_TYPES:
        from core.agency_webhook import dispatch_agency_webhook

        return await dispatch_agency_webhook(event)

    # Agency v1 fan-out (Karar 7). For internal inventory/rate/restriction/booking
    # source events, fan out an ANONYMIZED (zero-PII) agency webhook event to every
    # active partner agency of this tenant. This runs at the SXI edge, is idempotent
    # (deduped per source+agency), NEVER raises, and is INDEPENDENT of this source
    # event's own OTA dispatch outcome below. agency.*/IC events are already returned
    # above, so fan-out never recurses. agency<->tenant mapping stays out of the PMS
    # core (resolved in the b2b boundary helper).
    from core.agency_fanout import fan_out_agency_events

    await fan_out_agency_events(event)

    # Map outbox event_type to channel manager event name
    cm_event_name = EVENT_TYPE_TO_CM_EVENT.get(event_type)
    if not cm_event_name:
        return False, f"permanent: unsupported event_type '{event_type}'"

    # Build CM event payload
    cm_payload = _build_cm_payload(event, cm_event_name)

    try:
        from channel_manager.application.event_sync_service import EventSyncService

        sync_service = EventSyncService()
        result = await sync_service.handle_event(
            tenant_id=tenant_id,
            event_type=cm_event_name,
            event_payload=cm_payload,
        )

        if not result.get("handled"):
            reason = result.get("reason", "unknown")
            if "no active connectors" in reason.lower():
                # No connectors → nothing to do, mark as processed
                return True, f"No active connectors for tenant {tenant_id}"
            if "unsupported" in reason.lower():
                return False, f"permanent: {reason}"
            return True, f"Event handled: {reason}"

        jobs_created = result.get("sync_jobs_created", 0)
        jobs = result.get("jobs", [])

        # Check if any jobs had errors
        errors = [j for j in jobs if "error" in j]
        if errors and not any("job_id" in j for j in jobs):
            # All jobs failed
            error_msgs = "; ".join(j.get("error", "unknown") for j in errors)
            return False, f"retryable: all sync jobs failed: {error_msgs}"

        if errors:
            # Partial success
            error_msgs = "; ".join(j.get("error", "unknown") for j in errors)
            logger.warning(
                "Partial outbox dispatch: %d/%d jobs succeeded, errors: %s",
                jobs_created, len(jobs), error_msgs,
            )

        return True, f"Dispatched: {jobs_created} sync jobs created"

    except ImportError:
        logger.warning("EventSyncService not available, using fallback dispatch")
        return await _fallback_dispatch(event, cm_event_name)
    except Exception as e:
        error_msg = str(e)
        from core.outbox_service import is_retryable_error
        if is_retryable_error(error_msg):
            return False, f"retryable: {error_msg[:500]}"
        return False, f"permanent: {error_msg[:500]}"


async def _fallback_dispatch(event: dict[str, Any], cm_event_name: str) -> tuple[bool, str]:
    """
    Fallback dispatch when EventSyncService is unavailable.
    Attempts direct webhook push similar to old cm_push_event.
    """
    try:
        import httpx
        tenant_id = event.get("tenant_id", "")
        payload = event.get("payload", {})

        # Build a simple webhook payload
        webhook_payload = {
            "type": cm_event_name,
            "tenant_id": tenant_id,
            "event_id": event.get("id"),
            "payload": payload,
        }

        # Try the channel manager webhook
        from domains.channel_manager.router import CM_PARTNER_WEBHOOK_URL
        if CM_PARTNER_WEBHOOK_URL:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(CM_PARTNER_WEBHOOK_URL, json=webhook_payload)
                if resp.status_code >= 500:
                    return False, f"retryable: webhook returned {resp.status_code}"
                if resp.status_code >= 400:
                    return False, f"permanent: webhook returned {resp.status_code}"
                return True, f"Webhook delivered: {resp.status_code}"
        else:
            return True, "No webhook URL configured, event acknowledged"

    except Exception as e:
        from core.outbox_service import is_retryable_error
        error_msg = str(e)
        if is_retryable_error(error_msg):
            return False, f"retryable: fallback dispatch failed: {error_msg[:300]}"
        return False, f"permanent: fallback dispatch failed: {error_msg[:300]}"


def _build_cm_payload(event: dict[str, Any], cm_event_name: str) -> dict[str, Any]:
    """Build the payload expected by EventSyncService from an outbox event."""
    payload = dict(event.get("payload", {}))

    # Ensure property_id is present
    if "property_id" not in payload:
        payload["property_id"] = event.get("property_id", event.get("tenant_id", ""))

    # Booking events need check_in/check_out for date range extraction
    if cm_event_name in ("booking_created", "booking_cancelled", "booking_modified", "booking_no_show"):
        if "check_in" not in payload:
            payload.setdefault("date_start", payload.get("check_in", ""))
        if "check_out" not in payload:
            payload.setdefault("date_end", payload.get("check_out", ""))

    # Room block events need date_start/date_end
    if cm_event_name in ("room_blocked", "room_unblocked"):
        if "date_start" not in payload:
            payload.setdefault("date_start", payload.get("start_date", payload.get("block_start", "")))
        if "date_end" not in payload:
            payload.setdefault("date_end", payload.get("end_date", payload.get("block_end", "")))

    return payload
