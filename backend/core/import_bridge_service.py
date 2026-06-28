"""
DATA-001: Import Bridge Service — OTA → PMS Automatic Booking Import
=====================================================================
Reliably converts eligible imported_reservations into PMS bookings
using the atomic booking core.

Key guarantees:
  - Atomic claim pattern prevents concurrent processing
  - Duplicate prevention via external_reservation_id uniqueness + booking source
  - Reuses create_booking_atomic (single booking creation path)
  - Classifies errors as retryable vs permanent
  - Links booking_id back to import record on success
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.atomic_booking import BookingConflictError, create_booking_atomic
from core.database import db
from core.import_decision import (
    COLL_IMPORTED,
    check_booking_source_exists,
)

logger = logging.getLogger("core.import_bridge_service")


def _timeline_append(**kwargs):
    """Fire-and-forget timeline write. Returns a coroutine."""
    try:
        from controlplane.timeline_writer import get_timeline_writer

        return get_timeline_writer().append(**kwargs)
    except Exception:

        async def _noop():
            return None

        return _noop()


def _failure_record(**kwargs):
    """Fire-and-forget failure recording. Returns a coroutine."""
    try:
        from controlplane.failure_tracker import get_failure_tracker

        return get_failure_tracker().record(**kwargs)
    except Exception:

        async def _noop():
            return None

        return _noop()


# ── Status constants ─────────────────────────────────────────────────
STATUS_PENDING = "pending_auto_import"
STATUS_PROCESSING = "processing"
STATUS_IMPORTED = "imported"
STATUS_REVIEW = "review_required"
STATUS_RETRY = "retry"
STATUS_FAILED = "failed"
STATUS_DUPLICATE = "duplicate"

# ── Retry backoff (seconds) ─────────────────────────────────────────
IMPORT_RETRY_BACKOFF = {
    1: 30,
    2: 120,
    3: 600,
    4: 1800,
    5: 7200,
}

DEFAULT_MAX_RETRIES = 5

# ── Retryable vs permanent errors ───────────────────────────────────
RETRYABLE_KEYWORDS = [
    "timeout",
    "timed out",
    "connection refused",
    "connection reset",
    "temporary",
    "unavailable",
    "network",
    "write conflict",
    "lock",
    "replica",
]

PERMANENT_KEYWORDS = [
    "mapping error",
    "invalid payload",
    "validation",
    "business rule",
    "duplicate",
    "not found",
]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _is_retryable(error_msg: str) -> bool:
    lower = error_msg.lower()
    for kw in PERMANENT_KEYWORDS:
        if kw in lower:
            return False
    for kw in RETRYABLE_KEYWORDS:
        if kw in lower:
            return True
    return True


def _compute_next_retry_at(retry_count: int) -> str:
    backoff = IMPORT_RETRY_BACKOFF.get(retry_count, 7200)
    return (datetime.now(UTC) + timedelta(seconds=backoff)).isoformat()


async def create_import_record(
    lineage: dict[str, Any],
    import_status: str,
    review_reason: str | None = None,
    connector_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Create an imported_reservations record from a lineage record.
    Returns the created document or None if duplicate.
    """
    now = _utc_now()
    record_id = str(uuid.uuid4())

    doc = {
        "id": record_id,
        "tenant_id": lineage["tenant_id"],
        "property_id": lineage.get("property_id", lineage["tenant_id"]),
        "provider": lineage.get("provider", ""),
        "connector_id": connector_id or lineage.get("connection_id", ""),
        "external_reservation_id": lineage["external_reservation_id"],
        "lineage_id": lineage.get("id", ""),
        "payload_hash": lineage.get("payload_hash", ""),
        "import_status": import_status,
        "review_reason": review_reason,
        "retry_count": 0,
        "max_retries": DEFAULT_MAX_RETRIES,
        "next_retry_at": None,
        "booking_id": None,
        "folio_id": None,
        "correlation_id": lineage.get("correlation_id", str(uuid.uuid4())),
        "last_error": None,
        "imported_at": None,
        # Reservation data snapshot
        "guest_name": lineage.get("guest_name", ""),
        "guest_email": lineage.get("guest_email", ""),
        "guest_phone": lineage.get("guest_phone", ""),
        "arrival_date": lineage.get("arrival_date", ""),
        "departure_date": lineage.get("departure_date", ""),
        "room_type_code": lineage.get("room_type_code", ""),
        "rate_plan_code": lineage.get("rate_plan_code", ""),
        "adults": lineage.get("adults", 1),
        "children": lineage.get("children", 0),
        "total_amount": lineage.get("total_amount", 0.0),
        "currency": lineage.get("currency", "TRY"),
        "source_system": lineage.get("source_system", ""),
        "provider_updated_at": lineage.get("provider_last_modified_at", "") or lineage.get("provider_updated_at", ""),
        "created_at": now,
        "updated_at": now,
    }

    try:
        await db[COLL_IMPORTED].insert_one(doc)
        doc.pop("_id", None)
        logger.info(
            "Import record created: id=%s ext=%s status=%s",
            record_id,
            doc["external_reservation_id"],
            import_status,
        )
        return doc
    except DuplicateKeyError:
        logger.info(
            "Import record already exists for ext=%s (duplicate key)",
            lineage["external_reservation_id"],
        )
        return None


async def auto_import_reservation_to_pms(
    imported_reservation_id: str,
    pre_claimed_record: dict | None = None,
) -> tuple[bool, str]:
    """
    Attempt to auto-import an imported reservation into PMS.

    Args:
        imported_reservation_id: The ID of the imported_reservation record.
        pre_claimed_record: If provided, skip atomic claim (already claimed by caller).

    Returns:
        (success, message) tuple
    """
    now_str = _utc_now()

    if pre_claimed_record:
        # Record already claimed by caller (e.g., import_retry_worker)
        record = pre_claimed_record
    else:
        # ── 1. Atomic claim ──────────────────────────────────────────
        record = await db[COLL_IMPORTED].find_one_and_update(
            {
                "id": imported_reservation_id,
                "import_status": {"$in": [STATUS_PENDING, STATUS_RETRY]},
                "$or": [
                    {"next_retry_at": None},
                    {"next_retry_at": {"$lte": now_str}},
                ],
            },
            {
                "$set": {
                    "import_status": STATUS_PROCESSING,
                    "updated_at": now_str,
                },
            },
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )

    if not record:
        return False, "Record not claimable (already processing, imported, or not due for retry)"

    tenant_id = record["tenant_id"]

    # Ensure tenant context is set for strict mode
    from core.tenant_db import set_tenant_context

    set_tenant_context(tenant_id)

    provider = record.get("provider", "")
    ext_res_id = record["external_reservation_id"]
    correlation_id = record.get("correlation_id", str(uuid.uuid4()))

    # Timeline: import processing started
    await _timeline_append(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        entity_type="reservation",
        external_id=ext_res_id,
        stage="import_decided",
        source="import_bridge",
        provider=provider,
        metadata={"import_id": imported_reservation_id, "decision": "auto_import"},
    )

    try:
        # ── 2. Duplicate check (booking source) ─────────────────
        existing_booking_id = await check_booking_source_exists(
            tenant_id,
            provider,
            ext_res_id,
        )
        if existing_booking_id:
            await db[COLL_IMPORTED].update_one(
                {"id": imported_reservation_id},
                {
                    "$set": {
                        "import_status": STATUS_DUPLICATE,
                        "booking_id": existing_booking_id,
                        "updated_at": _utc_now(),
                        "last_error": f"Booking already exists: {existing_booking_id}",
                    },
                },
            )
            # Link lineage to existing booking
            if record.get("lineage_id"):
                await db.reservation_lineage.update_one(
                    {"id": record["lineage_id"]},
                    {"$set": {"reservation_id": existing_booking_id, "updated_at": _utc_now()}},
                )
            return True, f"Duplicate resolved — linked to existing booking {existing_booking_id}"

        # ── 3. Resolve room mapping ──────────────────────────────
        room_id = None
        room_type = record.get("room_type_code", "")
        property_id = record.get("property_id", tenant_id)

        async def _park_as_unmatched_hold(reason: str, detail: str) -> None:
            """Eslestirilemeyen rezervasyonu review'a al + tutma + ACIL alarm.

            HARD-FAIL korunur (otomatik kabul YOK). Tutma idempotenttir.
            """
            await _mark_review(imported_reservation_id, reason, detail)
            from domains.channel_manager.providers.unmatched_hold import (
                create_unmatched_reservation_hold,
            )

            try:
                hold = await create_unmatched_reservation_hold(
                    provider=provider,
                    tenant_id=tenant_id,
                    external_id=ext_res_id,
                    check_in=record.get("arrival_date", ""),
                    check_out=record.get("departure_date", ""),
                    guest_name=record.get("guest_name", ""),
                    room_type_code=record.get("room_type_code", ""),
                    rate_plan_code=record.get("rate_plan_code", ""),
                    total_amount=float(record.get("total_amount", 0) or 0),
                    currency=record.get("currency", "TRY"),
                    adults=record.get("adults", 1) or 1,
                    children=record.get("children", 0) or 0,
                    channel=record.get("source_system", "") or provider,
                    property_id=property_id,
                )
                if hold.get("booking_id"):
                    await db[COLL_IMPORTED].update_one(
                        {"id": imported_reservation_id},
                        {
                            "$set": {
                                "hold_booking_id": hold["booking_id"],
                                "updated_at": _utc_now(),
                            }
                        },
                    )
            except Exception as e:  # noqa: BLE001
                logger.exception(f"[IMPORT-BRIDGE] unmatched hold olusturma hatasi {ext_res_id}: {e}")

        if room_type:
            room_mapping = await db.room_mappings.find_one(
                {
                    "tenant_id": tenant_id,
                    "property_id": property_id,
                    "provider": provider,
                    "provider_room_code": room_type,
                    "is_active": True,
                },
                {"_id": 0},
            )
            if room_mapping:
                room_id = room_mapping.get("pms_room_type_id")
            else:
                await _park_as_unmatched_hold(
                    "unmapped_room_type",
                    f"No room mapping for provider room code: {room_type}",
                )
                return False, f"Review required: unmapped room type {room_type}"

        # ── 4. Resolve rate plan mapping ─────────────────────────
        rate_plan_id = None
        rate_code = record.get("rate_plan_code", "")
        if rate_code:
            rate_mapping = await db.rate_plan_mappings.find_one(
                {
                    "tenant_id": tenant_id,
                    "property_id": property_id,
                    "provider": provider,
                    "provider_rate_code": rate_code,
                    "is_active": True,
                },
                {"_id": 0},
            )
            if rate_mapping:
                rate_plan_id = rate_mapping.get("pms_rate_plan_id")
            else:
                await _park_as_unmatched_hold(
                    "unmapped_rate_plan",
                    f"No rate plan mapping for provider rate code: {rate_code}",
                )
                return False, f"Review required: unmapped rate plan {rate_code}"

        # ── 5. Build booking document ────────────────────────────
        # Eslestirme cozuldu -> varsa onceki tutmayi rebind ile serbest birak
        # (sentinel kilitler + tutma kaydi silinir) ki cift sayim olmasin.
        from domains.channel_manager.providers.unmatched_hold import (
            release_unmatched_reservation_hold,
        )

        try:
            await release_unmatched_reservation_hold(
                tenant_id=tenant_id,
                external_id=ext_res_id,
                reason="mapping_resolved",
                delete_hold=True,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[IMPORT-BRIDGE] unmatched hold rebind hatasi {ext_res_id}: {e}")

        booking_id = str(uuid.uuid4())
        # Use PMS room type name from mapping, not provider code
        pms_room_type = room_id if room_id else room_type
        booking_doc = {
            "id": booking_id,
            "tenant_id": tenant_id,
            "property_id": property_id,
            "guest_name": record.get("guest_name", ""),
            "guest_email": record.get("guest_email", ""),
            "guest_phone": record.get("guest_phone", ""),
            "check_in": record["arrival_date"],
            "check_out": record["departure_date"],
            "room_type": pms_room_type,
            "room_type_id": room_id,
            "rate_plan_id": rate_plan_id,
            "rate_plan_code": rate_code,
            "adults": record.get("adults", 1),
            "children": record.get("children", 0),
            "total_amount": record.get("total_amount", 0.0),
            "currency": record.get("currency", "TRY"),
            "status": "confirmed",
            "booking_source": "ota_import",
            "channel": record.get("source_system", "") or provider,
            "external_reservation_id": ext_res_id,
            "source": {
                "provider": provider,
                "external_reservation_id": ext_res_id,
                "connector_id": record.get("connector_id", ""),
                "import_record_id": imported_reservation_id,
            },
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }

        # ── 5b. Create/find guest record ─────────────────────────
        guest_name = record.get("guest_name", "")
        guest_parts = guest_name.split(" ", 1) if guest_name else ["", ""]
        guest_first = guest_parts[0]
        guest_last = guest_parts[1] if len(guest_parts) > 1 else ""
        guest_email = record.get("guest_email", "")
        guest_phone = record.get("guest_phone", "")

        if guest_name:
            # Try to find existing guest by email or phone
            # Dual-read: the insert below encrypts PII, so a plaintext-equality
            # lookup would never match an encrypted row → a duplicate guest record
            # on every repeated OTA sync. Match _hash_<field> OR legacy plaintext.
            from security.encrypted_lookup import build_guest_pii_query

            guest_query = {"tenant_id": tenant_id}
            if guest_email:
                guest_query.update(build_guest_pii_query("email", guest_email))
            elif guest_phone:
                guest_query.update(build_guest_pii_query("phone", guest_phone))
            else:
                guest_query["first_name"] = guest_first
                guest_query["last_name"] = guest_last

            existing_guest = await db.guests.find_one(guest_query, {"_id": 0, "id": 1})
            if existing_guest:
                booking_doc["guest_id"] = existing_guest["id"]
            else:
                guest_id = str(uuid.uuid4())
                guest_doc = {
                    "id": guest_id,
                    "tenant_id": tenant_id,
                    "first_name": guest_first,
                    "last_name": guest_last,
                    "email": guest_email,
                    "phone": guest_phone,
                    "nationality": "",
                    "vip_status": False,
                    "tags": [],
                    "notes": "",
                    "source": f"ota_import:{provider}",
                    "created_at": _utc_now(),
                    "updated_at": _utc_now(),
                }
                # Encrypt PII fields before persistence
                try:
                    from security.field_encryption import get_field_encryption_service

                    guest_doc = get_field_encryption_service().encrypt_document(guest_doc, collection="guests")
                except Exception:
                    pass
                # Plaintext name companions for index-serviceable prefix search.
                from security.search_normalize import apply_collection_normalized_fields

                apply_collection_normalized_fields(guest_doc, collection="guests")
                await db.guests.insert_one(guest_doc)
                guest_doc.pop("_id", None)
                booking_doc["guest_id"] = guest_id

        # Assign room_id only if we have a specific room (not just type)
        # OTA imports should NOT auto-assign rooms — user wants manual placement
        # Reservations arrive as "unassigned" and user places them on the calendar

        # ── 6. Create booking via atomic core ────────────────────
        try:
            await create_booking_atomic(booking_doc)
        except BookingConflictError as e:
            await _mark_review(
                imported_reservation_id,
                "booking_conflict",
                f"Room conflict: {str(e)[:500]}",
            )
            return False, f"Review required: booking conflict — {str(e)[:200]}"

        # ── 7. Update import record → imported ───────────────────
        imported_at = _utc_now()
        await db[COLL_IMPORTED].update_one(
            {"id": imported_reservation_id},
            {
                "$set": {
                    "import_status": STATUS_IMPORTED,
                    "booking_id": booking_id,
                    "imported_at": imported_at,
                    "updated_at": imported_at,
                    "last_error": None,
                },
            },
        )

        # ── 8. Link lineage to booking ───────────────────────────
        if record.get("lineage_id"):
            await db.reservation_lineage.update_one(
                {"id": record["lineage_id"]},
                {"$set": {"reservation_id": booking_id, "updated_at": imported_at}},
            )

        # Timeline: booking stored
        await _timeline_append(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            entity_type="reservation",
            entity_id=booking_id,
            external_id=ext_res_id,
            stage="stored",
            source="import_bridge",
            provider=provider,
            metadata={
                "booking_id": booking_id,
                "room_id": booking_doc.get("room_id", ""),
                "import_id": imported_reservation_id,
            },
        )

        # ── 9. Audit log ─────────────────────────────────────────
        await db.pms_audit_trail.insert_one(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "entity_type": "booking",
                "entity_id": booking_id,
                "action": "ota_auto_import",
                "details": {
                    "provider": provider,
                    "external_reservation_id": ext_res_id,
                    "import_record_id": imported_reservation_id,
                },
                "timestamp": imported_at,
                "performed_by": "import_bridge_service",
            }
        )

        # ── 9b. In-app notification for new OTA reservation ──────
        try:
            guest_name = booking_doc.get("guest_name", "Misafir")
            check_in = booking_doc.get("check_in", "")
            check_out = booking_doc.get("check_out", "")
            room_type_label = booking_doc.get("room_type", "")
            channel = booking_doc.get("channel", provider)
            total = booking_doc.get("total_amount", 0)
            currency = booking_doc.get("currency", "TRY")

            notif_title = f"Yeni Rezervasyon: {guest_name}"
            notif_message = f"{channel} kanalından yeni rezervasyon geldi. Giriş: {check_in}, Çıkış: {check_out}, Oda Tipi: {room_type_label}, Tutar: {total} {currency}"

            await db.notifications.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "user_id": None,  # System-wide — visible to all users
                    "type": "reservation",
                    "title": notif_title,
                    "message": notif_message,
                    "priority": "high",
                    "read": False,
                    "action_url": f"/reservations?booking_id={booking_id}",
                    "metadata": {
                        "booking_id": booking_id,
                        "provider": provider,
                        "external_reservation_id": ext_res_id,
                        "guest_name": guest_name,
                        "channel": channel,
                    },
                    "created_at": imported_at,
                }
            )
            logger.info("Notification created for OTA import: booking=%s", booking_id)
        except Exception as e:
            logger.warning("Failed to create notification for import %s: %s", imported_reservation_id, e)

        # ── 10. Enqueue outbox event for confirmation ────────────
        try:
            from core.outbox_service import BOOKING_CREATED, enqueue_outbox_event

            await enqueue_outbox_event(
                db,
                tenant_id=tenant_id,
                event_type=BOOKING_CREATED,
                entity_type="booking",
                entity_id=booking_id,
                payload={
                    "booking_id": booking_id,
                    "source": "ota_import",
                    "provider": provider,
                    "external_reservation_id": ext_res_id,
                },
                provider=provider,
                connector_id=record.get("connector_id"),
                property_id=property_id,
                correlation_id=record.get("correlation_id"),
            )
            # Timeline: queued for outbox delivery
            await _timeline_append(
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                entity_type="reservation",
                entity_id=booking_id,
                external_id=ext_res_id,
                stage="queued",
                source="outbox_service",
                provider=provider,
                metadata={"booking_id": booking_id},
            )
        except Exception as e:
            logger.warning("Outbox enqueue for import failed (non-critical): %s", e)

        logger.info(
            "OTA reservation imported: import=%s booking=%s ext=%s provider=%s",
            imported_reservation_id,
            booking_id,
            ext_res_id,
            provider,
        )
        return True, f"Booking {booking_id} created successfully"

    except Exception as e:
        error_msg = str(e)[:1000]
        logger.exception(
            "Import bridge error for %s: %s",
            imported_reservation_id,
            error_msg,
        )
        await _handle_import_failure(record, error_msg)

        # Timeline: failure
        await _timeline_append(
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            entity_type="reservation",
            external_id=ext_res_id,
            stage="stored",
            status="failure",
            source="import_bridge",
            provider=provider,
            metadata={"error_message": error_msg[:500], "import_id": imported_reservation_id},
        )

        # FailureTracker: record structured failure
        await _failure_record(
            tenant_id=tenant_id,
            provider=provider,
            operation_type="reservation_import",
            error_code="IMPORT_ERROR",
            error_message=error_msg,
            correlation_id=correlation_id,
            context={"import_id": imported_reservation_id, "external_reservation_id": ext_res_id},
        )

        return False, f"Import error: {error_msg[:200]}"


async def _mark_review(
    import_id: str,
    reason: str,
    error_detail: str,
) -> None:
    """Move import record to review_required."""
    await db[COLL_IMPORTED].update_one(
        {"id": import_id},
        {
            "$set": {
                "import_status": STATUS_REVIEW,
                "review_reason": reason,
                "last_error": error_detail[:1000],
                "updated_at": _utc_now(),
            },
        },
    )


async def _handle_import_failure(
    record: dict[str, Any],
    error_msg: str,
) -> None:
    """Handle import failure — retry or mark as permanently failed."""
    now = _utc_now()
    retry_count = record.get("retry_count", 0) + 1
    max_retries = record.get("max_retries", DEFAULT_MAX_RETRIES)
    retryable = _is_retryable(error_msg)

    if not retryable or retry_count >= max_retries:
        await db[COLL_IMPORTED].update_one(
            {"id": record["id"]},
            {
                "$set": {
                    "import_status": STATUS_FAILED,
                    "last_error": error_msg,
                    "retry_count": retry_count,
                    "updated_at": now,
                },
            },
        )
        logger.error(
            "Import FAILED (permanent): %s retries=%d error=%s",
            record["id"],
            retry_count,
            error_msg[:200],
        )
    else:
        next_retry = _compute_next_retry_at(retry_count)
        await db[COLL_IMPORTED].update_one(
            {"id": record["id"]},
            {
                "$set": {
                    "import_status": STATUS_RETRY,
                    "last_error": error_msg,
                    "retry_count": retry_count,
                    "next_retry_at": next_retry,
                    "updated_at": now,
                },
            },
        )
        logger.warning(
            "Import scheduled for retry: %s count=%d/%d next=%s",
            record["id"],
            retry_count,
            max_retries,
            next_retry,
        )


async def ensure_import_indexes() -> None:
    """Create required indexes for imported_reservations."""
    indexes = [
        {
            "keys": [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
            "name": "idx_import_unique_ext_res",
            "kwargs": {"unique": True},
        },
        {
            "keys": [("tenant_id", 1), ("import_status", 1), ("next_retry_at", 1), ("created_at", 1)],
            "name": "idx_import_worker_claim",
        },
        {
            "keys": [("tenant_id", 1), ("provider", 1), ("import_status", 1), ("created_at", -1)],
            "name": "idx_import_provider_status",
        },
        {
            "keys": [("correlation_id", 1)],
            "name": "idx_import_correlation",
        },
        # Booking source lookup
        {
            "keys": [("tenant_id", 1), ("source.provider", 1), ("source.external_reservation_id", 1)],
            "name": "idx_booking_source_lookup",
            "collection": "bookings",
        },
    ]
    for idx in indexes:
        coll_name = idx.pop("collection", COLL_IMPORTED)
        try:
            await db[coll_name].create_index(
                idx["keys"],
                name=idx["name"],
                background=True,
                **idx.get("kwargs", {}),
            )
        except Exception as e:
            if "already exists" in str(e) or "IndexOptionsConflict" in str(e):
                pass
            else:
                logger.warning("Import index %s failed: %s", idx["name"], e)
    logger.info("Import bridge indexes ensured (DATA-001)")
