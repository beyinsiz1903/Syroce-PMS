"""Best-effort, tenant-scoped realtime signals for durable booking changes.

The payload deliberately contains only identifiers and operational state. UI
clients use the signal as an invalidation hint and fetch the authoritative
booking data through the normal authenticated REST endpoint.
"""

import logging

logger = logging.getLogger(__name__)


async def publish_booking_change(
    *,
    tenant_id: str,
    booking_id: str,
    event_type: str,
    status: str | None = None,
    source: str | None = None,
    external_reservation_id: str | None = None,
) -> bool:
    """Publish a booking invalidation after its database mutation is durable.

    Realtime delivery must never turn a successful provider import/cancellation
    into a failed one, so transport errors are logged and reported as ``False``.
    """
    if not tenant_id or not booking_id:
        return False

    payload = {"id": booking_id}
    if status:
        payload["status"] = status
    if source:
        payload["source"] = source
    if external_reservation_id:
        payload["external_reservation_id"] = external_reservation_id

    try:
        from websocket_server import broadcast_booking_update

        await broadcast_booking_update(
            payload,
            event_type=event_type,
            tenant_id=tenant_id,
        )
        return True
    except Exception as exc:  # realtime is a non-critical delivery channel
        logger.warning(
            "Booking realtime publish failed event=%s exception_class=%s",
            event_type,
            type(exc).__name__,
        )
        return False
