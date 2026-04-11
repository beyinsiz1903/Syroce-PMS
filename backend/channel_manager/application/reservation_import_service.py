"""
Reservation Import Service - Production-grade engine for pulling and importing
reservations from external providers.

Features:
  - Idempotent import (connector_id + external_reservation_id + payload_fingerprint)
  - Delta detection: new, duplicate, modification, cancellation, out_of_order
  - Cancellation rules: checked-in → review, already_cancelled → duplicate_cancel,
    modification after cancel → conflict
  - Manual review queue with review_reason_code and suggested_action
  - Acknowledgement tracking: ack_pending → ack_sent / ack_failed
  - Batch-level summary
  - Full audit trail
"""
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from core.database import db

from ..connectors.hotelrunner_v2.auth import HotelRunnerAuth
from ..connectors.hotelrunner_v2.hr_client import HotelRunnerClient
from ..connectors.hotelrunner_v2.connector_errors import ConnectorError
from ..connectors.hotelrunner_v2.reservation_mapper import HotelRunnerMapper
from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..domain.models.canonical import CanonicalReservation, ReservationStatus
from ..domain.models.connector_account import ConnectorAccount, ConnectorProvider
from ..domain.models.reservation_import import (
    AckStatus,
    ImportedReservation,
    ImportStatus,
    ReservationImportBatch,
    ReviewReasonCode,
)
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.reservation_import_service")

IMPORTED_RESERVATIONS = "cm_imported_reservations"
IMPORT_BATCHES = "cm_import_batches"


class ReservationImportService:
    """Orchestrates reservation pull, dedup, import, and acknowledgement."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()
        self._mapper = HotelRunnerMapper()

    # ─── Main Entry Point ────────────────────────────────────────────

    async def pull_and_import(
        self,
        tenant_id: str,
        connector_id: str,
        date_start: str | None = None,
        date_end: str | None = None,
        triggered_by: str = "system",
    ) -> dict[str, Any]:
        """
        Pull reservations from provider, process each with full lifecycle,
        acknowledge successes, and return batch summary.
        """
        connector_doc = await self._repo.get_connector(tenant_id, connector_id)
        if not connector_doc:
            raise ValueError("Connector not found")
        if connector_doc.get("status") != "active":
            raise ValueError("Connector is not active")

        connector = ConnectorAccount.from_doc(connector_doc)
        property_id = connector.property_id

        # Create import batch
        batch = ReservationImportBatch(
            tenant_id=tenant_id,
            property_id=property_id,
            connector_id=connector_id,
            triggered_by=triggered_by,
            pull_from=date_start,
            pull_to=date_end,
        )
        await self._repo.create_import_batch(batch.to_doc())

        await self._audit(
            tenant_id, property_id, connector_id,
            AuditAction.RESERVATION_IMPORT_STARTED,
            metadata={"batch_id": batch.id, "triggered_by": triggered_by},
        )

        start_time = time.monotonic()

        try:
            raw_reservations = await self._pull_from_provider(connector, date_start, date_end)
            await self._repo.update_import_batch(batch.id, {"total_reservations": len(raw_reservations)})

            if not raw_reservations:
                duration = int((time.monotonic() - start_time) * 1000)
                await self._repo.update_import_batch(batch.id, {
                    "status": "completed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "duration_ms": duration,
                })
                await self._audit(
                    tenant_id, property_id, connector_id,
                    AuditAction.RESERVATION_IMPORT_COMPLETED,
                    metadata={"batch_id": batch.id, "total": 0},
                )
                return {"batch_id": batch.id, "status": "completed", "total": 0}

            # Get mapping lookups
            from ..application.mapping_service import MappingService
            mapping_svc = MappingService(self._repo)
            room_reverse = await mapping_svc.get_reverse_lookup(tenant_id, connector_id, "room_type")
            rate_reverse = await mapping_svc.get_reverse_lookup(tenant_id, connector_id, "rate_plan")

            # Process each reservation
            stats = {
                "new": 0, "modified": 0, "cancelled": 0, "duplicate": 0,
                "duplicate_cancel": 0, "conflict": 0, "review": 0,
                "failed": 0, "out_of_order": 0,
            }
            ack_results = {"sent": 0, "failed": 0}
            ack_pending_ids = []

            for raw in raw_reservations:
                canonical = self._mapper.reservation_to_canonical(raw)
                result = await self._process_single_reservation(
                    tenant_id, property_id, connector_id, batch.id,
                    canonical, room_reverse, rate_reverse,
                )
                action = result["action"]
                stats[action] = stats.get(action, 0) + 1
                if result.get("acknowledge"):
                    ack_pending_ids.append({
                        "external_id": canonical.external_id,
                        "message_uid": canonical.message_uid,
                        "hr_number": canonical.hr_number,
                        "pms_booking_id": result.get("pms_booking_id"),
                        "reservation_id": result.get("reservation_id"),
                    })

            # Acknowledge to provider (confirm delivery via message_uid)
            if ack_pending_ids:
                ack_items = [
                    {
                        "message_uid": a["message_uid"],
                        "pms_number": a.get("pms_booking_id"),
                    }
                    for a in ack_pending_ids if a.get("message_uid")
                ]
                res_ids = [a["reservation_id"] for a in ack_pending_ids]
                try:
                    ack_result = await self._acknowledge_to_provider(connector, ack_items)
                    ack_sent = ack_result.get("sent", 0)
                    ack_failed = ack_result.get("failed", 0)
                    # Update individual reservation ACK statuses
                    for i, rid in enumerate(res_ids):
                        if rid and i < len(ack_items):
                            await self._repo.update_imported_reservation(tenant_id, rid, {
                                "ack_status": AckStatus.ACK_SENT.value,
                                "ack_sent_at": datetime.now(UTC).isoformat(),
                            })
                    ack_results["sent"] = ack_sent
                    ack_results["failed"] = ack_failed
                    await self._audit(
                        tenant_id, property_id, connector_id,
                        AuditAction.RESERVATION_ACK_SENT,
                        metadata={
                            "batch_id": batch.id,
                            "sent": ack_sent,
                            "failed": ack_failed,
                            "errors": ack_result.get("errors", []),
                        },
                    )
                except ConnectorError as e:
                    logger.warning("Acknowledgement failed: %s", e.message)
                    for rid in res_ids:
                        if rid:
                            await self._repo.update_imported_reservation(tenant_id, rid, {
                                "ack_status": AckStatus.ACK_FAILED.value,
                                "ack_failed_reason": e.message,
                            })
                    ack_results["failed"] = len(ack_items)
                    await self._audit(
                        tenant_id, property_id, connector_id,
                        AuditAction.RESERVATION_ACK_FAILED,
                        metadata={"batch_id": batch.id, "error": e.message},
                    )

            # Finalize batch
            duration = int((time.monotonic() - start_time) * 1000)
            await self._repo.update_import_batch(batch.id, {
                "status": "completed",
                "new_count": stats["new"],
                "modified_count": stats["modified"],
                "cancelled_count": stats["cancelled"],
                "duplicate_count": stats["duplicate"],
                "duplicate_cancel_count": stats["duplicate_cancel"],
                "conflict_count": stats["conflict"],
                "review_count": stats["review"],
                "failed_count": stats["failed"],
                "out_of_order_count": stats["out_of_order"],
                "ack_sent_count": ack_results["sent"],
                "ack_failed_count": ack_results["failed"],
                "completed_at": datetime.now(UTC).isoformat(),
                "duration_ms": duration,
            })

            await self._audit(
                tenant_id, property_id, connector_id,
                AuditAction.RESERVATION_IMPORT_COMPLETED,
                metadata={"batch_id": batch.id, "total": len(raw_reservations), **stats},
            )

            return {
                "batch_id": batch.id,
                "status": "completed",
                "total": len(raw_reservations),
                "duration_ms": duration,
                **stats,
                "ack_sent": ack_results["sent"],
                "ack_failed": ack_results["failed"],
            }

        except Exception as e:
            duration = int((time.monotonic() - start_time) * 1000)
            await self._repo.update_import_batch(batch.id, {
                "status": "failed",
                "completed_at": datetime.now(UTC).isoformat(),
                "duration_ms": duration,
            })
            await self._audit(
                tenant_id, property_id, connector_id,
                AuditAction.RESERVATION_IMPORT_FAILED,
                metadata={"batch_id": batch.id, "error": str(e)},
            )
            logger.error("Import batch %s failed: %s", batch.id, str(e))
            raise

    # ─── Single Reservation Processing ───────────────────────────────

    async def _process_single_reservation(
        self, tenant_id: str, property_id: str, connector_id: str, batch_id: str,
        canonical: CanonicalReservation,
        room_reverse: dict[str, str],
        rate_reverse: dict[str, str],
    ) -> dict[str, Any]:
        """Process a single reservation with full lifecycle handling."""

        # Compute payload fingerprint
        fingerprint = ImportedReservation.compute_fingerprint(canonical.model_dump())

        # Check for existing import
        existing = await self._repo.get_imported_reservation_by_external_id(
            tenant_id, connector_id, canonical.external_id,
        )

        # Map external IDs to PMS IDs
        pms_room_type = room_reverse.get(canonical.room_type_id)
        pms_rate_plan = rate_reverse.get(canonical.rate_plan_id)

        # Build imported reservation record
        imported = ImportedReservation(
            tenant_id=tenant_id,
            property_id=property_id,
            connector_id=connector_id,
            batch_id=batch_id,
            external_reservation_id=canonical.external_id,
            external_confirmation_number=canonical.confirmation_number,
            hr_number=canonical.hr_number,
            message_uid=canonical.message_uid,
            payload_fingerprint=fingerprint,
            channel_name=canonical.channel_name,
            requires_ack=canonical.requires_ack,
            guest_name=f"{canonical.guest.first_name} {canonical.guest.last_name}".strip(),
            guest_email=canonical.guest.email,
            guest_phone=canonical.guest.phone,
            arrival_date=canonical.arrival_date,
            departure_date=canonical.departure_date,
            room_type_external_id=canonical.room_type_id,
            rate_plan_external_id=canonical.rate_plan_id,
            room_type_mapped_id=pms_room_type,
            rate_plan_mapped_id=pms_rate_plan,
            adult_count=canonical.adult_count,
            child_count=canonical.child_count,
            total_amount=canonical.total_amount,
            currency=canonical.currency,
            payment_type=canonical.payment_type,
            special_requests=canonical.special_requests,
            raw_payload=canonical.raw_provider_data,
        )

        # ── Cancellation path ──────────────────────────────────────
        if canonical.status == ReservationStatus.CANCELLED:
            return await self._handle_cancellation(
                tenant_id, property_id, connector_id, imported, existing, fingerprint,
                requires_ack=canonical.requires_ack,
            )

        # ── Existing reservation path ──────────────────────────────
        if existing:
            existing_status = existing.get("import_status", "")

            # Modification after cancellation -> conflict
            if existing_status in (ImportStatus.CANCELLED.value, ImportStatus.DUPLICATE_CANCEL.value):
                imported.import_status = ImportStatus.CONFLICT
                imported.conflict_reason = "Modification received after cancellation"
                imported.review_reason_code = ReviewReasonCode.MODIFICATION_AFTER_CANCEL.value
                imported.suggested_action = "Verify with provider if reservation was re-opened"
                imported.ack_status = AckStatus.NOT_REQUIRED
                await self._repo.upsert_imported_reservation(imported.to_doc())
                await self._audit(
                    tenant_id, property_id, connector_id,
                    AuditAction.RESERVATION_CONFLICT,
                    metadata={"external_id": canonical.external_id, "reason": "modification_after_cancel"},
                )
                return {"action": "conflict", "acknowledge": False, "reservation_id": imported.id}

            # Exact duplicate check (same fingerprint)
            if existing.get("payload_fingerprint") == fingerprint:
                imported.import_status = ImportStatus.DUPLICATE
                imported.ack_status = AckStatus.ACK_PENDING if canonical.requires_ack else AckStatus.ACK_PENDING
                await self._repo.upsert_imported_reservation(imported.to_doc())
                await self._audit(
                    tenant_id, property_id, connector_id,
                    AuditAction.RESERVATION_DUPLICATE,
                    metadata={"external_id": canonical.external_id},
                )
                return {"action": "duplicate", "acknowledge": True, "reservation_id": imported.id}

            # Payload differs -> modification
            if existing_status in (ImportStatus.CREATED.value, ImportStatus.MODIFIED.value, ImportStatus.ACKNOWLEDGED.value):
                imported.is_modification = True
                imported.previous_version_id = existing.get("id")
                imported.pms_booking_id = existing.get("pms_booking_id")
                if imported.pms_booking_id:
                    await self._modify_pms_booking(tenant_id, imported)
                imported.import_status = ImportStatus.MODIFIED
                imported.ack_status = AckStatus.ACK_PENDING
                await self._repo.upsert_imported_reservation(imported.to_doc())
                await self._audit(
                    tenant_id, property_id, connector_id,
                    AuditAction.RESERVATION_MODIFIED,
                    metadata={
                        "external_id": canonical.external_id,
                        "pms_booking_id": imported.pms_booking_id,
                        "old_fingerprint": existing.get("payload_fingerprint"),
                        "new_fingerprint": fingerprint,
                    },
                )
                return {"action": "modified", "acknowledge": True, "reservation_id": imported.id, "pms_booking_id": imported.pms_booking_id}

            # Payload differs but status is unexpected -> out_of_order
            imported.import_status = ImportStatus.OUT_OF_ORDER
            imported.review_reason = f"Unexpected existing status: {existing_status}"
            imported.review_reason_code = ReviewReasonCode.MANUAL_ESCALATION.value
            imported.suggested_action = "Check reservation timeline on provider side"
            imported.ack_status = AckStatus.NOT_REQUIRED
            await self._repo.upsert_imported_reservation(imported.to_doc())
            await self._audit(
                tenant_id, property_id, connector_id,
                AuditAction.RESERVATION_OUT_OF_ORDER,
                metadata={"external_id": canonical.external_id, "existing_status": existing_status},
            )
            return {"action": "out_of_order", "acknowledge": False, "reservation_id": imported.id}

        # ── New reservation path ────────────────────────────────────

        # Check room type mapping
        if not pms_room_type:
            imported.import_status = ImportStatus.REVIEW
            imported.review_reason = f"No mapping for room type: {canonical.room_type_id}"
            imported.review_reason_code = ReviewReasonCode.MISSING_ROOM_MAPPING.value
            imported.suggested_action = "Create room type mapping and reprocess"
            imported.ack_status = AckStatus.NOT_REQUIRED
            await self._repo.upsert_imported_reservation(imported.to_doc())
            await self._audit(
                tenant_id, property_id, connector_id,
                AuditAction.RESERVATION_REVIEW_QUEUED,
                metadata={
                    "external_id": canonical.external_id,
                    "reason_code": ReviewReasonCode.MISSING_ROOM_MAPPING.value,
                },
            )
            return {"action": "review", "acknowledge": False, "reservation_id": imported.id}

        # Create PMS booking
        try:
            pms_booking_id = await self._create_pms_booking(tenant_id, property_id, canonical, pms_room_type)
            imported.pms_booking_id = pms_booking_id
            imported.import_status = ImportStatus.CREATED
            # requires_ack=true → ACK mandatory; otherwise still pending
            imported.ack_status = AckStatus.ACK_PENDING
            await self._repo.upsert_imported_reservation(imported.to_doc())
            await self._audit(
                tenant_id, property_id, connector_id,
                AuditAction.RESERVATION_CREATED,
                metadata={
                    "external_id": canonical.external_id,
                    "pms_booking_id": pms_booking_id,
                    "channel": canonical.channel_name,
                    "requires_ack": canonical.requires_ack,
                },
            )
            return {"action": "new", "acknowledge": True, "reservation_id": imported.id, "pms_booking_id": pms_booking_id}
        except Exception as e:
            imported.import_status = ImportStatus.FAILED
            imported.error_message = str(e)
            imported.ack_status = AckStatus.NOT_REQUIRED
            await self._repo.upsert_imported_reservation(imported.to_doc())
            return {"action": "failed", "acknowledge": False, "reservation_id": imported.id}

    # ─── Cancellation Handler ────────────────────────────────────────

    async def _handle_cancellation(
        self, tenant_id: str, property_id: str, connector_id: str,
        imported: ImportedReservation, existing: dict | None,
        fingerprint: str, requires_ack: bool = False,
    ) -> dict[str, Any]:
        """Handle cancellation with checked-in protection and duplicate detection."""
        imported.is_cancellation = True

        if existing:
            existing_status = existing.get("import_status", "")

            # Already cancelled → duplicate cancel
            if existing_status in (ImportStatus.CANCELLED.value, ImportStatus.DUPLICATE_CANCEL.value):
                imported.import_status = ImportStatus.DUPLICATE_CANCEL
                imported.ack_status = AckStatus.ACK_PENDING
                await self._repo.upsert_imported_reservation(imported.to_doc())
                await self._audit(
                    tenant_id, property_id, connector_id,
                    AuditAction.RESERVATION_DUPLICATE_CANCEL,
                    metadata={"external_id": imported.external_reservation_id},
                )
                return {"action": "duplicate_cancel", "acknowledge": True, "reservation_id": imported.id}

            pms_booking_id = existing.get("pms_booking_id")
            if pms_booking_id:
                # Check if booking is checked-in
                pms_booking = await db.bookings.find_one(
                    {"id": pms_booking_id, "tenant_id": tenant_id}, {"_id": 0, "status": 1},
                )
                if pms_booking and pms_booking.get("status") == "checked_in":
                    imported.import_status = ImportStatus.REVIEW
                    imported.review_reason = "Cancellation received for checked-in guest"
                    imported.review_reason_code = ReviewReasonCode.CHECKED_IN_CANCELLATION.value
                    imported.suggested_action = "Contact guest and provider before cancelling"
                    imported.pms_booking_id = pms_booking_id
                    imported.ack_status = AckStatus.NOT_REQUIRED
                    await self._repo.upsert_imported_reservation(imported.to_doc())
                    await self._audit(
                        tenant_id, property_id, connector_id,
                        AuditAction.RESERVATION_REVIEW_QUEUED,
                        metadata={
                            "external_id": imported.external_reservation_id,
                            "reason_code": ReviewReasonCode.CHECKED_IN_CANCELLATION.value,
                            "pms_booking_id": pms_booking_id,
                        },
                    )
                    return {"action": "review", "acknowledge": False, "reservation_id": imported.id}

                # Normal cancel
                await self._cancel_pms_booking(tenant_id, pms_booking_id)
                imported.import_status = ImportStatus.CANCELLED
                imported.pms_booking_id = pms_booking_id
                imported.ack_status = AckStatus.ACK_PENDING
                await self._repo.upsert_imported_reservation(imported.to_doc())
                await self._audit(
                    tenant_id, property_id, connector_id,
                    AuditAction.RESERVATION_CANCELLED,
                    metadata={
                        "external_id": imported.external_reservation_id,
                        "pms_booking_id": pms_booking_id,
                    },
                )
                return {"action": "cancelled", "acknowledge": True, "reservation_id": imported.id}
            else:
                # No PMS booking linked yet, just mark as cancelled
                imported.import_status = ImportStatus.CANCELLED
                imported.ack_status = AckStatus.ACK_PENDING
                await self._repo.upsert_imported_reservation(imported.to_doc())
                await self._audit(
                    tenant_id, property_id, connector_id,
                    AuditAction.RESERVATION_CANCELLED,
                    metadata={"external_id": imported.external_reservation_id, "note": "no_pms_booking"},
                )
                return {"action": "cancelled", "acknowledge": True, "reservation_id": imported.id}
        else:
            # Cancellation for unknown reservation → still record it
            imported.import_status = ImportStatus.CANCELLED
            imported.ack_status = AckStatus.ACK_PENDING
            await self._repo.upsert_imported_reservation(imported.to_doc())
            await self._audit(
                tenant_id, property_id, connector_id,
                AuditAction.RESERVATION_CANCELLED,
                metadata={"external_id": imported.external_reservation_id, "note": "no_prior_import"},
            )
            return {"action": "cancelled", "acknowledge": True, "reservation_id": imported.id}

    # ─── PMS Booking Operations ──────────────────────────────────────

    async def _create_pms_booking(
        self, tenant_id: str, property_id: str,
        canonical: CanonicalReservation, pms_room_type: str,
    ) -> str:
        """Create a booking in the PMS from a canonical reservation."""
        booking_id = str(uuid.uuid4())
        guest_id = await self._find_or_create_guest(tenant_id, canonical)

        booking = {
            "id": booking_id,
            "tenant_id": tenant_id,
            "property_id": property_id,
            "guest_id": guest_id,
            "guest_name": f"{canonical.guest.first_name} {canonical.guest.last_name}".strip(),
            "room_type": pms_room_type,
            "check_in": canonical.arrival_date,
            "check_out": canonical.departure_date,
            "adults": canonical.adult_count,
            "children": canonical.child_count,
            "status": "confirmed",
            "source": "ota",
            "channel": canonical.channel_name,
            "total_amount": canonical.total_amount,
            "currency": canonical.currency,
            "payment_status": "pending",
            "special_requests": canonical.special_requests,
            "external_confirmation": canonical.confirmation_number,
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": "channel_manager",
        }
        from core.atomic_booking import BookingConflictError, create_booking_atomic
        try:
            await create_booking_atomic(booking)
        except BookingConflictError:
            logger.warning("OTA import conflict for %s, creating without room assignment", canonical.external_id)
            booking["room_id"] = None
            booking["allocation_source"] = "pending_assignment"
            await db.bookings.insert_one(booking)
            booking.pop("_id", None)
        logger.info("Created PMS booking %s from external %s", booking_id, canonical.external_id)
        return booking_id

    async def _modify_pms_booking(self, tenant_id: str, imported: ImportedReservation):
        if not imported.pms_booking_id:
            return
        updates = {
            "check_in": imported.arrival_date,
            "check_out": imported.departure_date,
            "adults": imported.adult_count,
            "children": imported.child_count,
            "total_amount": imported.total_amount,
            "special_requests": imported.special_requests,
            "updated_at": datetime.now(UTC).isoformat(),
            "updated_by": "channel_manager",
        }
        if imported.room_type_mapped_id:
            updates["room_type"] = imported.room_type_mapped_id
        await db.bookings.update_one(
            {"id": imported.pms_booking_id, "tenant_id": tenant_id},
            {"$set": updates},
        )
        logger.info("Modified PMS booking %s", imported.pms_booking_id)

    async def _cancel_pms_booking(self, tenant_id: str, pms_booking_id: str):
        now = datetime.now(UTC)
        booking = await db.bookings.find_one(
            {"id": pms_booking_id, "tenant_id": tenant_id},
            {"_id": 0, "guest_name": 1, "guest_id": 1, "room_id": 1, "room_number": 1, "check_in": 1, "check_out": 1},
        )
        await db.bookings.update_one(
            {"id": pms_booking_id, "tenant_id": tenant_id},
            {"$set": {
                "status": "cancelled",
                "cancelled_at": now.isoformat(),
                "cancelled_by": "channel_manager",
            }},
        )
        # Create notification for channel-manager-synced cancellation
        try:
            guest_name = booking.get("guest_name", "Misafir") if booking else "Misafir"
            room_id = booking.get("room_id") if booking else None
            room_label = ""
            if room_id:
                room_doc = await db.rooms.find_one({"id": room_id}, {"_id": 0, "room_number": 1})
                room_label = f" - Oda {room_doc.get('room_number', '')}" if room_doc else ""
            check_in = (booking.get("check_in", "") or "")[:10] if booking else ""
            check_out = (booking.get("check_out", "") or "")[:10] if booking else ""
            await db.notifications.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "type": "reservation_cancelled",
                "severity": "warning",
                "title": f"OTA İptali - {guest_name}{room_label}",
                "message": f"{guest_name} adlı misafirin {check_in} - {check_out} tarihli OTA rezervasyonu kanal tarafından iptal edildi.",
                "related_entity": "reservation",
                "related_id": pms_booking_id,
                "read": False,
                "created_at": now.isoformat(),
            })
        except Exception:
            pass
        logger.info("Cancelled PMS booking %s", pms_booking_id)

    async def _find_or_create_guest(self, tenant_id: str, canonical: CanonicalReservation) -> str:
        if canonical.guest.email:
            existing = await db.guests.find_one(
                {"tenant_id": tenant_id, "email": canonical.guest.email}, {"_id": 0, "id": 1},
            )
            if existing:
                return existing["id"]

        guest_id = str(uuid.uuid4())
        guest = {
            "id": guest_id,
            "tenant_id": tenant_id,
            "first_name": canonical.guest.first_name,
            "last_name": canonical.guest.last_name,
            "name": f"{canonical.guest.first_name} {canonical.guest.last_name}".strip(),
            "email": canonical.guest.email,
            "phone": canonical.guest.phone,
            "nationality": canonical.guest.nationality,
            "source": "ota",
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.guests.insert_one(guest)
        return guest_id

    # ─── Provider Communication ──────────────────────────────────────

    async def _pull_from_provider(
        self, connector: ConnectorAccount,
        date_start: str | None, date_end: str | None,
    ) -> list[dict[str, Any]]:
        if connector.provider == ConnectorProvider.HOTELRUNNER:
            auth = HotelRunnerAuth.from_credentials(connector.credentials)
            client = HotelRunnerClient(auth=auth, sandbox=True)
            try:
                reservations = await client.pull_reservations(
                    date_start=date_start,
                    date_end=date_end,
                )
                # Store audit entries from the pull session
                if client.audit_entries:
                    for entry in client.audit_entries:
                        await self._audit(
                            connector.tenant_id,
                            connector.property_id,
                            connector.id,
                            AuditAction.RESERVATION_PULL_AUDIT,
                            metadata={
                                "type": "raw_request_response",
                                "correlation_id": entry.get("correlation_id"),
                                "method": entry.get("method"),
                                "url": entry.get("url"),
                                "status_code": entry.get("status_code"),
                                "latency_ms": entry.get("latency_ms"),
                            },
                        )
                return reservations
            finally:
                await client.close()
        raise ValueError(f"Unsupported provider: {connector.provider}")

    async def _acknowledge_to_provider(
        self, connector: ConnectorAccount, ack_items: list[dict[str, str]],
    ) -> dict[str, Any]:
        """
        Confirm delivery of reservations to HotelRunner.
        Each item: {"message_uid": str, "pms_number": Optional[str]}
        """
        if connector.provider == ConnectorProvider.HOTELRUNNER:
            auth = HotelRunnerAuth.from_credentials(connector.credentials)
            client = HotelRunnerClient(auth=auth, sandbox=True)
            try:
                result = await client.acknowledge_reservations(ack_items)
                return result
            finally:
                await client.close()
        raise ValueError(f"Unsupported provider: {connector.provider}")

    # ─── Manual Review Queue ─────────────────────────────────────────

    async def get_review_queue(self, tenant_id: str, connector_id: str | None = None) -> list[dict]:
        return await self._repo.get_reservation_review_queue(tenant_id, connector_id)

    async def reprocess_review(
        self, tenant_id: str, reservation_id: str, actor_id: str,
        room_type_override: str | None = None,
    ) -> dict[str, Any]:
        """Reprocess a reservation from the review queue."""
        imported = await self._repo.get_imported_reservation_by_id(tenant_id, reservation_id)
        if not imported:
            raise ValueError("Imported reservation not found")
        if imported.get("import_status") not in ("review", "conflict", "out_of_order"):
            raise ValueError("Reservation is not in review status")

        pms_room_type = room_type_override or imported.get("room_type_mapped_id")
        if not pms_room_type:
            raise ValueError("Room type mapping required for reprocessing")

        # If it was a cancellation in review
        if imported.get("is_cancellation"):
            pms_booking_id = imported.get("pms_booking_id")
            if pms_booking_id:
                await self._cancel_pms_booking(tenant_id, pms_booking_id)
            await self._repo.update_imported_reservation(tenant_id, reservation_id, {
                "import_status": ImportStatus.CANCELLED.value,
                "reviewed_by": actor_id,
                "reviewed_at": datetime.now(UTC).isoformat(),
                "reprocessed_at": datetime.now(UTC).isoformat(),
                "ack_status": AckStatus.ACK_PENDING.value,
            })
            await self._audit(
                tenant_id, imported.get("property_id", ""), imported.get("connector_id", ""),
                AuditAction.RESERVATION_REVIEW_REPROCESSED,
                actor_id=actor_id,
                metadata={"reservation_id": reservation_id, "action": "cancel_approved"},
            )
            return {"reservation_id": reservation_id, "status": "cancelled", "action": "reprocessed"}

        # Create PMS booking for the reservation
        canonical = CanonicalReservation(
            external_id=imported.get("external_reservation_id", ""),
            confirmation_number=imported.get("external_confirmation_number", ""),
            channel_name=imported.get("channel_name", ""),
            arrival_date=imported.get("arrival_date", ""),
            departure_date=imported.get("departure_date", ""),
            adult_count=imported.get("adult_count", 1),
            child_count=imported.get("child_count", 0),
            total_amount=imported.get("total_amount", 0.0),
            currency=imported.get("currency", "TRY"),
            special_requests=imported.get("special_requests", ""),
        )
        canonical.guest.first_name = imported.get("guest_name", "").split(" ")[0]
        canonical.guest.last_name = " ".join(imported.get("guest_name", "").split(" ")[1:])
        canonical.guest.email = imported.get("guest_email", "")

        pms_booking_id = await self._create_pms_booking(
            tenant_id, imported.get("property_id", ""), canonical, pms_room_type,
        )

        await self._repo.update_imported_reservation(tenant_id, reservation_id, {
            "pms_booking_id": pms_booking_id,
            "import_status": ImportStatus.CREATED.value,
            "room_type_mapped_id": pms_room_type,
            "reviewed_by": actor_id,
            "reviewed_at": datetime.now(UTC).isoformat(),
            "reprocessed_at": datetime.now(UTC).isoformat(),
            "ack_status": AckStatus.ACK_PENDING.value,
        })

        await self._audit(
            tenant_id, imported.get("property_id", ""), imported.get("connector_id", ""),
            AuditAction.RESERVATION_REVIEW_REPROCESSED,
            actor_id=actor_id,
            metadata={"reservation_id": reservation_id, "pms_booking_id": pms_booking_id},
        )

        return {"reservation_id": reservation_id, "pms_booking_id": pms_booking_id, "status": "created"}

    async def dismiss_review(
        self, tenant_id: str, reservation_id: str, actor_id: str,
    ) -> dict[str, Any]:
        """Dismiss a reservation from the review queue."""
        imported = await self._repo.get_imported_reservation_by_id(tenant_id, reservation_id)
        if not imported:
            raise ValueError("Imported reservation not found")
        if imported.get("import_status") not in ("review", "conflict", "out_of_order"):
            raise ValueError("Reservation is not in review status")

        await self._repo.update_imported_reservation(tenant_id, reservation_id, {
            "import_status": ImportStatus.DISMISSED.value,
            "dismissed_by": actor_id,
            "dismissed_at": datetime.now(UTC).isoformat(),
        })

        await self._audit(
            tenant_id, imported.get("property_id", ""), imported.get("connector_id", ""),
            AuditAction.RESERVATION_REVIEW_DISMISSED,
            actor_id=actor_id,
            metadata={"reservation_id": reservation_id},
        )

        return {"reservation_id": reservation_id, "status": "dismissed"}

    # ─── Approve Review (legacy compat) ──────────────────────────────

    async def approve_review(
        self, tenant_id: str, reservation_id: str, actor_id: str,
        room_type_override: str | None = None,
    ) -> dict[str, Any]:
        """Alias for reprocess_review for backward compatibility."""
        return await self.reprocess_review(tenant_id, reservation_id, actor_id, room_type_override)

    # ─── Batch & Reservation Queries ─────────────────────────────────

    async def get_import_batches(self, tenant_id: str, connector_id: str | None = None) -> list[dict]:
        return await self._repo.get_import_batches(tenant_id, connector_id)

    async def get_import_batch_detail(self, tenant_id: str, batch_id: str) -> dict[str, Any]:
        batch = await self._repo.get_import_batch_by_id(tenant_id, batch_id)
        if not batch:
            raise ValueError("Batch not found")
        reservations = await self._repo.get_imported_reservations_by_batch(batch_id)
        return {"batch": batch, "reservations": reservations, "reservation_count": len(reservations)}

    async def get_imported_reservations(
        self, tenant_id: str, connector_id: str | None = None,
        status: str | None = None, limit: int = 100,
    ) -> list[dict]:
        return await self._repo.get_imported_reservations(tenant_id, connector_id, status, limit)

    async def get_imported_reservation_detail(self, tenant_id: str, reservation_id: str) -> dict | None:
        return await self._repo.get_imported_reservation_by_id(tenant_id, reservation_id)

    # ─── Reservation Stats & Summary ────────────────────────────────

    async def get_reservation_stats(self, tenant_id: str, connector_id: str | None = None) -> dict[str, Any]:
        """Get reservation import stats for dashboard display."""
        base_q: dict[str, Any] = {"tenant_id": tenant_id}
        if connector_id:
            base_q["connector_id"] = connector_id

        total = await db[IMPORTED_RESERVATIONS].count_documents(base_q)
        # Status breakdown
        status_pipeline = [
            {"$match": base_q},
            {"$group": {"_id": "$import_status", "count": {"$sum": 1}}},
        ]
        by_status: dict[str, int] = {}
        async for doc in db[IMPORTED_RESERVATIONS].aggregate(status_pipeline):
            by_status[doc["_id"]] = doc["count"]

        # ACK breakdown
        ack_pipeline = [
            {"$match": base_q},
            {"$group": {"_id": "$ack_status", "count": {"$sum": 1}}},
        ]
        by_ack: dict[str, int] = {}
        async for doc in db[IMPORTED_RESERVATIONS].aggregate(ack_pipeline):
            by_ack[doc["_id"]] = doc["count"]

        # Review queue count
        review_q = {**base_q, "import_status": {"$in": ["review", "conflict", "out_of_order"]}}
        review_count = await db[IMPORTED_RESERVATIONS].count_documents(review_q)

        # Failed ACK count
        ack_failed_count = by_ack.get("ack_failed", 0)

        # Recent batches (last 5)
        batch_q: dict[str, Any] = {"tenant_id": tenant_id}
        if connector_id:
            batch_q["connector_id"] = connector_id
        recent_batches = await db[IMPORT_BATCHES].find(batch_q, {"_id": 0}).sort("started_at", -1).to_list(5)

        return {
            "total_reservations": total,
            "by_status": by_status,
            "by_ack_status": by_ack,
            "review_queue_count": review_count,
            "ack_failed_count": ack_failed_count,
            "recent_batches": recent_batches,
            "success_rate": round(
                (by_status.get("created", 0) + by_status.get("modified", 0) + by_status.get("cancelled", 0))
                / max(total, 1) * 100, 1
            ),
        }

    # ─── Retry Failed ACKs ──────────────────────────────────────────

    async def retry_failed_acks(self, tenant_id: str, connector_id: str, actor_id: str | None = None) -> dict[str, Any]:
        """Retry all failed ACKs for a connector."""
        connector_doc = await self._repo.get_connector(tenant_id, connector_id)
        if not connector_doc:
            raise ValueError("Connector not found")

        connector = ConnectorAccount.from_doc(connector_doc)
        property_id = connector.property_id

        # Get all ack_failed reservations
        failed_q = {
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "ack_status": AckStatus.ACK_FAILED.value,
        }
        failed_docs = await db[IMPORTED_RESERVATIONS].find(failed_q, {"_id": 0}).to_list(200)

        if not failed_docs:
            return {"retried": 0, "message": "No failed ACKs to retry"}

        # Mark all as retrying
        for doc in failed_docs:
            await self._repo.update_imported_reservation(tenant_id, doc["id"], {
                "ack_status": AckStatus.ACK_RETRYING.value,
            })

        # Build ACK items
        ack_items = [
            {"message_uid": doc.get("message_uid", ""), "pms_number": doc.get("pms_booking_id")}
            for doc in failed_docs if doc.get("message_uid")
        ]

        sent = 0
        failed = 0
        try:
            result = await self._acknowledge_to_provider(connector, ack_items)
            sent = result.get("sent", 0)
            failed = result.get("failed", 0)
            for doc in failed_docs:
                await self._repo.update_imported_reservation(tenant_id, doc["id"], {
                    "ack_status": AckStatus.ACK_SENT.value,
                    "ack_sent_at": datetime.now(UTC).isoformat(),
                })
            await self._audit(
                tenant_id, property_id, connector_id,
                AuditAction.RESERVATION_ACK_SENT,
                actor_id=actor_id,
                metadata={"action": "retry_acks", "sent": sent, "failed": failed},
            )
        except ConnectorError as e:
            for doc in failed_docs:
                await self._repo.update_imported_reservation(tenant_id, doc["id"], {
                    "ack_status": AckStatus.ACK_FAILED.value,
                    "ack_failed_reason": f"Retry failed: {e.message}",
                })
            failed = len(ack_items)
            await self._audit(
                tenant_id, property_id, connector_id,
                AuditAction.RESERVATION_ACK_FAILED,
                actor_id=actor_id,
                metadata={"action": "retry_acks_failed", "error": e.message},
            )

        return {"retried": len(failed_docs), "ack_sent": sent, "ack_failed": failed}

    # ─── Audit Log Query ─────────────────────────────────────────────

    async def get_audit_trail(self, tenant_id: str, connector_id: str | None = None, limit: int = 100) -> list[dict]:
        return await self._repo.get_audit_logs(tenant_id, connector_id, limit)

    # ─── Audit ───────────────────────────────────────────────────────

    async def _audit(self, tenant_id, property_id, connector_id, action, actor_id=None, metadata=None):
        log = IntegrationAuditLog(
            tenant_id=tenant_id,
            property_id=property_id,
            connector_id=connector_id,
            action=action,
            actor_id=actor_id,
            metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())
