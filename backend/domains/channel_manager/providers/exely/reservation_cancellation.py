"""Operator-initiated, whole-booking Exely cancellations with durable delivery state.

Local cancellation and inventory publication do not prove OTA_CancelRQ delivery.
Only an explicit provider Success confirms it. An uncertain write is never replayed.
Inbound cancellations/no-shows do not create an intent and cannot echo back.
"""
import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta

from pymongo.errors import DuplicateKeyError

from core.outbox_service import EXELY_RESERVATION_CANCEL, enqueue_outbox_event

logger = logging.getLogger(__name__)


def _now():
    return datetime.now(UTC).isoformat()


def _identity(booking):
    source = booking.get("source") or {}
    if not isinstance(source, dict) or source.get("provider") != "exely":
        return None
    external = booking.get("provider_group_reservation_id") or source.get("group_external_reservation_id")
    property_id = booking.get("property_id")
    if not external or not property_id:
        return None
    return str(property_id), str(external)


def operator_intent(booking, actor, reason):
    """Persist this marker atomically with the operator's local status change."""
    if not _identity(booking):
        return {}
    return {"exely_cancel_intent": {
        "actor": actor, "reason": (str(reason or "").strip() or "Cancelled by hotel operator")[:500],
        "provider_version_key": booking.get("provider_version_key"),
        "requested_at": _now(), "state": "PENDING",
    }}


def _request_id(tenant_id, property_id, external):
    # One operation per provider booking, including after a timeout/version change.
    return hashlib.sha256(f"exely-cancel-v1\0{tenant_id}\0{property_id}\0{external}".encode()).hexdigest()


async def _source(database, tenant_id, booking_id):
    booking = await database.bookings.find_one({"tenant_id": tenant_id, "id": booking_id})
    identity = _identity(booking or {})
    if not identity:
        raise ValueError("EXELY_SOURCE_MISSING")
    property_id, external = identity
    source = await database.exely_reservations.find_one({
        "tenant_id": tenant_id, "property_id": property_id, "external_id": external,
    })
    if not source or booking_id not in (source.get("pms_booking_ids") or []):
        raise ValueError("EXELY_SOURCE_INCOMPLETE")
    return booking, source, property_id, external


async def _validate_group(database, tenant_id, source, property_id, external):
    ids = source.get("pms_booking_ids") or []
    version = source.get("provider_version_key")
    if (not version or source.get("durable_version_key") != version
            or source.get("pms_status") != "imported" or not ids or len(ids) != len(set(ids))):
        raise ValueError("EXELY_SOURCE_INCOMPLETE")
    rows = await database.bookings.find({"tenant_id": tenant_id, "id": {"$in": ids}}).to_list(len(ids) + 1)
    if len(rows) != len(ids) or any(_identity(row) != (property_id, external)
            or row.get("provider_version_key") != version for row in rows):
        raise ValueError("EXELY_SOURCE_INCOMPLETE")
    if any(row.get("status") != "cancelled" for row in rows):
        raise ValueError("EXELY_WHOLE_BOOKING_REQUIRED")
    return sorted(ids), version


def _public(request):
    return {key: request.get(key) for key in ("state", "requested_at", "updated_at", "confirmed_at", "code")}


async def status(database, tenant_id, booking_id):
    booking, source, property_id, external = await _source(database, tenant_id, booking_id)
    request = await database.exely_cancel_requests.find_one({
        "_id": _request_id(tenant_id, property_id, external), "tenant_id": tenant_id,
    })
    if request:
        return {**_public(request), "can_send": False}
    if source.get("pms_status") == "cancellation_done":
        return {"state": "REMOTE_CANCELLED", "can_send": False}
    try:
        await _validate_group(database, tenant_id, source, property_id, external)
    except ValueError as exc:
        return {"state": "BLOCKED", "code": str(exc), "can_send": False}
    return {"state": "NOT_REQUESTED", "can_send": booking.get("status") == "cancelled"}


async def enqueue(database, tenant_id, booking_id):
    booking, source, property_id, external = await _source(database, tenant_id, booking_id)
    intent = booking.get("exely_cancel_intent") or {}
    if not intent.get("actor") or not intent.get("reason"):
        raise ValueError("EXELY_OPERATOR_INTENT_REQUIRED")
    if source.get("pms_status") == "cancellation_done":
        return {"state": "REMOTE_CANCELLED", "can_send": False}
    ids, version = await _validate_group(database, tenant_id, source, property_id, external)
    if intent.get("provider_version_key") != version:
        raise ValueError("EXELY_SOURCE_CHANGED")
    request_id = _request_id(tenant_id, property_id, external)
    request = {
        "_id": request_id, "tenant_id": tenant_id, "property_id": property_id, "external_id": external,
        "booking_id": booking_id, "booking_ids": ids, "provider_version_key": version,
        "actor": intent["actor"], "reason": intent["reason"], "echo_token": str(uuid.uuid4()),
        "state": "PENDING", "requested_at": intent["requested_at"], "updated_at": _now(),
    }
    try:
        await database.exely_cancel_requests.insert_one(request)
    except DuplicateKeyError:
        request = await database.exely_cancel_requests.find_one({"_id": request_id, "tenant_id": tenant_id})
    if request["state"] == "PENDING":
        await enqueue_outbox_event(database, tenant_id=tenant_id, event_type=EXELY_RESERVATION_CANCEL,
            provider="exely", property_id=property_id, entity_type="exely_cancellation", entity_id=request_id,
            idempotency_key=f"exely-cancel-v1:{request_id}", payload={"request_id": request_id})
    await database.bookings.update_one({"tenant_id": tenant_id, "id": booking_id,
        "exely_cancel_intent.requested_at": intent["requested_at"]},
        {"$set": {"exely_cancel_intent.state": "QUEUED"}})
    return {**_public(request), "can_send": False}


async def queue_after_local_cancel(database, tenant_id, booking_id):
    """A durable marker survives enqueue failures; local cancellation stays valid."""
    try:
        return await enqueue(database, tenant_id, booking_id)
    except ValueError as exc:
        return {"state": "BLOCKED", "code": str(exc), "can_send": False}
    except Exception:
        logger.exception("Exely cancellation enqueue deferred")
        return {"state": "PENDING", "can_send": False}


async def recover_pending(database, tenant_id, property_id):
    """Recover only explicit new operator intents; never backfill historical cancels."""
    now = _now()
    rows = await database.bookings.find({"tenant_id": tenant_id, "property_id": property_id,
        "status": "cancelled", "exely_cancel_intent.state": "PENDING",
        "$or": [{"exely_cancel_intent.retry_at": {"$exists": False}},
                {"exely_cancel_intent.retry_at": {"$lte": now}}],
    }).sort("exely_cancel_intent.requested_at", 1).to_list(50)
    for row in rows:
        await database.bookings.update_one({"tenant_id": tenant_id, "id": row["id"]}, {"$set": {
            "exely_cancel_intent.retry_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}})
        await queue_after_local_cancel(database, tenant_id, row["id"])


async def _save_outcome(database, request, state, code=None):
    fields = {"state": state, "code": code, "updated_at": _now()}
    if state == "CONFIRMED":
        fields["confirmed_at"] = fields["updated_at"]
    await database.exely_cancel_requests.update_one({"_id": request["_id"],
        "tenant_id": request["tenant_id"], "state": "SENDING"}, {"$set": fields})


async def deliver(database, event):
    from .factory import get_exely_provider

    tenant_id = event.get("tenant_id")
    request_id = (event.get("payload") or {}).get("request_id")
    if (event.get("event_type") != EXELY_RESERVATION_CANCEL or event.get("provider") != "exely"
            or not tenant_id or not request_id or event.get("entity_id") != request_id):
        return False, "permanent: EXELY_CANCEL_SOURCE_INVALID"
    request = await database.exely_cancel_requests.find_one({"_id": request_id, "tenant_id": tenant_id})
    if not request or event.get("property_id") != request["property_id"]:
        return False, "permanent: EXELY_CANCEL_SOURCE_INVALID"
    if request["state"] == "CONFIRMED":
        return True, "Exely cancellation confirmed"
    if request["state"] != "PENDING":
        return False, "permanent: EXELY_CANCEL_REVIEW_REQUIRED"
    try:
        _, source, property_id, external = await _source(database, tenant_id, request["booking_id"])
        ids, version = await _validate_group(database, tenant_id, source, property_id, external)
        if (ids != request["booking_ids"] or version != request["provider_version_key"]
                or property_id != request["property_id"] or external != request["external_id"]):
            raise ValueError("EXELY_SOURCE_CHANGED")
    except ValueError:
        # Nothing was sent. Do not expose credentials/provider exception contents.
        await database.exely_cancel_requests.update_one({"_id": request_id, "tenant_id": tenant_id,
            "state": "PENDING"}, {"$set": {"state": "BLOCKED", "code": "EXELY_CANCEL_SOURCE_OR_CONNECTION_INVALID",
                                         "updated_at": _now()}})
        return False, "permanent: EXELY_CANCEL_SOURCE_OR_CONNECTION_INVALID"
    try:
        provider, connection = await get_exely_provider(tenant_id, property_id=property_id,
                                                       actor="exely_reservation_cancel")
        if connection.get("auto_sync_reservations") is not True:
            raise RuntimeError("EXELY_RESERVATION_SYNC_DISABLED")
    except Exception:
        # Provider I/O has not started; connection resolution can safely retry.
        exhausted = event.get("attempt_count", 0) >= event.get("max_attempts", 5)
        await database.exely_cancel_requests.update_one({"_id": request_id, "tenant_id": tenant_id,
            "state": "PENDING"}, {"$set": {"state": "BLOCKED" if exhausted else "PENDING",
                "code": "EXELY_CANCEL_CONNECTION_UNAVAILABLE", "updated_at": _now()}})
        return False, f"{'permanent' if exhausted else 'retryable'}: EXELY_CANCEL_CONNECTION_UNAVAILABLE"
    claimed = await database.exely_cancel_requests.update_one({"_id": request_id, "tenant_id": tenant_id,
        "state": "PENDING"}, {"$set": {"state": "SENDING", "updated_at": _now()}})
    if claimed.modified_count != 1:
        return False, "permanent: EXELY_CANCEL_ALREADY_CLAIMED"
    try:
        result = await provider.cancel_reservation(external, request["reason"], request["echo_token"])
    except Exception:
        await _save_outcome(database, request, "UNKNOWN", "EXELY_CANCEL_DELIVERY_UNKNOWN")
        return False, "permanent: EXELY_CANCEL_DELIVERY_UNKNOWN"
    if result.success:
        await _save_outcome(database, request, "CONFIRMED")
        return True, "Exely cancellation confirmed"
    metadata = result.metadata or {}
    classification = metadata.get("classification") or metadata.get("provider_status_class")
    writes = metadata.get("provider_write_count", 1)
    if (writes == 0 or classification == "RATE_LIMITED") and event.get("attempt_count", 0) < event.get("max_attempts", 5):
        await _save_outcome(database, request, "PENDING", "EXELY_CANCEL_NOT_ACCEPTED")
        return False, "retryable: EXELY_CANCEL_NOT_ACCEPTED"
    definitive = classification in {"AUTH_FAILED", "REJECTED", "RATE_LIMITED"} or writes == 0
    await _save_outcome(database, request, "REJECTED" if definitive else "UNKNOWN",
                        "EXELY_CANCEL_REJECTED" if definitive else "EXELY_CANCEL_DELIVERY_UNKNOWN")
    return False, "permanent: EXELY_CANCEL_REVIEW_REQUIRED"


async def dispatch(event):
    from core.database import db

    return await deliver(db, event)
