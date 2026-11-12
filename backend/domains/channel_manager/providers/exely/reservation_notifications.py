"""Local, replay-safe bell notifications for durable Exely imports.

The delivery intent is committed with PMS_DURABLE. Notification failures must
not repeat a reservation mutation, provider ACK or inventory publication.
Historical versions without this intent are deliberately not backfilled.
"""

import logging
import uuid
from datetime import UTC, datetime

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

TITLES = {
    "reservation": "Yeni Exely rezervasyonu",
    "reservation_modified": "Exely rezervasyonu güncellendi",
    "reservation_cancelled": "Exely rezervasyonu iptal edildi",
}


def build_notification(current, version, confirmations, expectations, created_at):
    kind = version.get("reservation_notification_kind")
    # A reviewed local archive cancellation is not a new operational alert.
    if kind not in TITLES or all(row.get("status") == "archived_demo" for row in expectations):
        return None
    booking_ids = list(dict.fromkeys(row["pms_booking_id"] for row in confirmations))
    if not booking_ids:
        return None
    identity = version["version_identity"]
    notice_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"exely-notification-v1:{identity}"))
    guest = " ".join(str(current.get("guest_name") or "Misafir").split())[:160]
    start = str(current.get("checkin_date") or "")[:10]
    end = str(current.get("checkout_date") or "")[:10]
    return {
        "_id": notice_id,
        "id": notice_id,
        "tenant_id": version["tenant_id"],
        "user_id": None,
        "type": kind,
        "category": "reservation",
        "priority": "high" if kind == "reservation_cancelled" else "normal",
        "title": TITLES[kind],
        "message": f"{guest} · {start} – {end} · {len(booking_ids)} oda · {current.get('external_id', '')}",
        "read": False,
        "created_at": created_at,
        "related_entity": "booking",
        "related_id": booking_ids[0],
        "metadata": {
            "booking_id": booking_ids[0],
            "booking_ids": booking_ids,
            "provider": "exely",
            "property_id": version["property_id"],
            "external_reservation_id": version["provider_reservation_id"],
            "version_identity": identity,
        },
    }


async def deliver_notification(database, tenant_id, identity):
    """One local upsert, recoverable after either insert/marker response loss."""
    query = {"tenant_id": tenant_id, "version_identity": identity, "processing_state": "PMS_DURABLE"}
    try:
        version = await database.exely_reservation_versions.find_one(query, {"_id": 0})
        if not version or version.get("reservation_notification_state") != "PENDING":
            return
        notice = version.get("reservation_notification_v1") or {}
        metadata = notice.get("metadata") or {}
        expected_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"exely-notification-v1:{identity}"))
        booking_ids = [row["pms_booking_id"] for row in version.get("ack_confirmations") or []]
        if (notice.get("tenant_id") != tenant_id or metadata.get("version_identity") != identity
                or metadata.get("property_id") != version.get("property_id")
                or metadata.get("external_reservation_id") != version.get("provider_reservation_id")
                or notice.get("type") not in TITLES or notice.get("id") != expected_id
                or notice.get("_id") != expected_id or not booking_ids
                or metadata.get("booking_ids") != list(dict.fromkeys(booking_ids))
                or notice.get("related_id") != booking_ids[0]):
            raise ValueError("EXELY_NOTIFICATION_INTENT_INVALID")
        notification_query = {"tenant_id": tenant_id, "_id": notice["_id"]}
        try:
            await database.notifications.update_one(notification_query, {"$setOnInsert": notice}, upsert=True)
        except DuplicateKeyError:
            # Concurrent upserts may lose the unique _id race. Only accept our
            # own exact tenant/version notification as the winner.
            existing = await database.notifications.find_one(notification_query, {"_id": 0, "id": 1, "metadata": 1})
            if not existing or existing.get("id") != notice["id"] or existing.get("metadata") != metadata:
                raise
        await database.exely_reservation_versions.update_one(
            {**query, "reservation_notification_state": "PENDING"},
            {"$set": {"reservation_notification_state": "SENT", "reservation_notification_sent_at": datetime.now(UTC).isoformat()}},
        )
    except Exception as exc:
        # The intent remains PENDING for a normal pull, including after ACK.
        logger.warning("[EXELY-LIFECYCLE] notification=pending exception_class=%s", type(exc).__name__)


async def deliver_pending_notifications(database, tenant_id, limit=100):
    try:
        versions = await database.exely_reservation_versions.find(
            {"tenant_id": tenant_id, "processing_state": "PMS_DURABLE", "reservation_notification_state": "PENDING"},
            {"_id": 0, "version_identity": 1},
        ).to_list(limit)
    except Exception as exc:
        logger.warning("[EXELY-LIFECYCLE] notification_scan=pending exception_class=%s", type(exc).__name__)
        return
    for version in versions:
        await deliver_notification(database, tenant_id, version["version_identity"])
