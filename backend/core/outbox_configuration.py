"""Read-only configuration preflight for failed booking availability events."""

from datetime import date

from core.database import db
from core.tenant_db import tenant_context

CONFIGURATION_ERRORS = {
    "exely_room_mapping_missing", "exely_property_mapping_missing",
    "exely_room_mapping_incomplete", "exely_multiple_availability_mappings",
    "hotelrunner_room_mapping_missing", "hotelrunner_room_mapping_incomplete",
    "room_not_found", "room_type_missing", "invalid_date_range",
}
CONFIGURATION_ERROR_PATTERN = "|".join(sorted(CONFIGURATION_ERRORS))
BOOKING_AVAILABILITY_EVENTS = (
    "booking.created.v1", "booking.cancelled.v1", "booking.modified.v1", "booking.no_show.v1",
    "reservation.created.v1", "reservation.cancelled.v1", "reservation.modified.v1",
    "inventory.availability.updated.v1",
)


def is_configuration_failure(event: dict) -> bool:
    return event.get("event_type") in BOOKING_AVAILABILITY_EVENTS and any(
        code in (event.get("last_error") or "") for code in CONFIGURATION_ERRORS
    )


async def booking_configuration_readiness(event: dict) -> dict:
    """No inventory reconciliation, queue writes or provider calls are allowed here.

    This verifies configuration only, not actual external delivery. A corrected
    configuration still requires an explicit operator requeue and worker result.
    """
    from core.outbox_dispatcher import _build_cm_payload
    from domains.channel_manager.availability_auto_sync import _exely_wire_pair

    tenant_id = event.get("tenant_id")
    previous_error = event.get("last_error") or ""
    payload = _build_cm_payload(event, "booking_modified")
    room_id = payload.get("room_id")
    issues = []
    providers = []
    if not tenant_id or not room_id:
        return {"ready": False, "issues": ["booking_availability_payload_incomplete"], "providers": []}
    try:
        check_in = date.fromisoformat((payload.get("check_in") or payload.get("date_start") or "")[:10])
        check_out = date.fromisoformat((payload.get("check_out") or payload.get("date_end") or "")[:10])
        if check_out <= check_in:
            raise ValueError("empty date range")
    except (TypeError, ValueError):
        return {"ready": False, "issues": ["invalid_date_range"], "providers": []}
    with tenant_context(tenant_id):
        room = await db.rooms.find_one({"tenant_id": tenant_id, "id": room_id}, {"_id": 0, "room_type": 1})
        if not room:
            return {"ready": False, "issues": ["room_not_found"], "providers": []}
        room_type = room.get("room_type")
        if not room_type:
            return {"ready": False, "issues": ["room_type_missing"], "providers": []}
        conn = await db.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0, "hotel_code": 1})
        if conn is not None:
            providers.append("exely")
            if not conn.get("hotel_code"):
                issues.append("exely_property_mapping_missing")
            mappings = await db.exely_room_mappings.find({
                "tenant_id": tenant_id, "pms_room_type": room_type, "sync_availability": {"$ne": False},
            }, {"_id": 0, "pms_api_room_code": 1, "pms_api_rate_plan_code": 1,
                "exely_room_code": 1, "exely_rate_plan_code": 1}).to_list(10)
            pairs = {_exely_wire_pair(row) for row in mappings if all(_exely_wire_pair(row))}
            if not mappings:
                issues.append("exely_room_mapping_missing")
            elif not pairs:
                issues.append("exely_room_mapping_incomplete")
            elif len(pairs) > 1:
                issues.append("exely_multiple_availability_mappings")
        elif "exely_" in previous_error:
            issues.append("exely_connection_inactive")
        conn = await db.hotelrunner_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0, "id": 1})
        if conn is not None:
            providers.append("hotelrunner")
            mappings = await db.hotelrunner_room_mappings.find({
                "tenant_id": tenant_id, "pms_room_type": room_type,
            }, {"_id": 0, "hr_inv_code": 1}).to_list(10)
            if not mappings:
                issues.append("hotelrunner_room_mapping_missing")
            elif not any(row.get("hr_inv_code") for row in mappings):
                issues.append("hotelrunner_room_mapping_incomplete")
        elif "hotelrunner_" in previous_error:
            issues.append("hotelrunner_connection_inactive")
    # A removed/inactive connection is not proof the originally failed target
    # received this update. Keep the old event visible for operator review.
    if not providers:
        issues.append("no_active_provider_connection")
    return {"ready": not issues, "issues": issues, "providers": providers}
