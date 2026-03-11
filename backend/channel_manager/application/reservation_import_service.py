"""
Reservation Import Service - Pulls and imports reservations from external providers.

Features:
  - Idempotent import (duplicate protection via external_reservation_id)
  - Modification detection and handling
  - Cancellation processing
  - Manual review queue for edge cases
  - Acknowledgement to provider after successful import
  - Audit trail for every import action
"""
import logging
import uuid
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from ..domain.models.reservation_import import ReservationImportBatch, ImportedReservation, ImportStatus
from ..domain.models.connector_account import ConnectorAccount, ConnectorProvider
from ..domain.models.canonical import CanonicalReservation, ReservationStatus
from ..domain.models.audit import IntegrationAuditLog, AuditAction
from ..infrastructure.repository import ChannelManagerRepository
from ..connectors.hotelrunner.client import HotelRunnerClient
from ..connectors.hotelrunner.auth import HotelRunnerAuth
from ..connectors.hotelrunner.mapper import HotelRunnerMapper
from ..connectors.hotelrunner.errors import ConnectorError

from core.database import db

logger = logging.getLogger("channel_manager.application.reservation_import_service")


class ReservationImportService:
    """Orchestrates reservation pull, dedup, import, and acknowledgement."""

    def __init__(self, repo: Optional[ChannelManagerRepository] = None):
        self._repo = repo or ChannelManagerRepository()
        self._mapper = HotelRunnerMapper()

    async def pull_and_import(
        self,
        tenant_id: str,
        connector_id: str,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        triggered_by: str = "system",
    ) -> Dict[str, Any]:
        """
        Main entry point: pull reservations from provider and import into PMS.
        Returns batch summary with counts of new, modified, cancelled, duplicate, review, failed.
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

        start_time = time.monotonic()

        try:
            # Pull from provider
            raw_reservations = await self._pull_from_provider(connector, date_start, date_end)
            batch_updates = {"total_reservations": len(raw_reservations)}
            await self._repo.update_import_batch(batch.id, batch_updates)

            if not raw_reservations:
                await self._repo.update_import_batch(batch.id, {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": int((time.monotonic() - start_time) * 1000),
                })
                return {"batch_id": batch.id, "status": "completed", "total": 0}

            # Process each reservation
            stats = {"new": 0, "modified": 0, "cancelled": 0, "duplicate": 0, "review": 0, "failed": 0}
            acknowledged_ids = []

            # Get mapping lookups
            from ..application.mapping_service import MappingService
            mapping_svc = MappingService(self._repo)
            room_reverse = await mapping_svc.get_reverse_lookup(tenant_id, connector_id, "room_type")
            rate_reverse = await mapping_svc.get_reverse_lookup(tenant_id, connector_id, "rate_plan")

            for raw in raw_reservations:
                canonical = self._mapper.reservation_to_canonical(raw)
                result = await self._process_single_reservation(
                    tenant_id, property_id, connector_id, batch.id,
                    canonical, room_reverse, rate_reverse,
                )
                stats[result["action"]] = stats.get(result["action"], 0) + 1
                if result.get("acknowledge"):
                    acknowledged_ids.append(canonical.external_id)

            # Acknowledge to provider
            if acknowledged_ids:
                try:
                    await self._acknowledge_to_provider(connector, acknowledged_ids)
                except ConnectorError as e:
                    logger.warning("Acknowledgement failed: %s", e.message)

            # Finalize batch
            duration = int((time.monotonic() - start_time) * 1000)
            await self._repo.update_import_batch(batch.id, {
                "status": "completed",
                "new_count": stats["new"],
                "modified_count": stats["modified"],
                "cancelled_count": stats["cancelled"],
                "duplicate_count": stats["duplicate"],
                "review_count": stats["review"],
                "failed_count": stats["failed"],
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": duration,
            })

            await self._audit(
                tenant_id, property_id, connector_id,
                AuditAction.RESERVATIONS_PULLED,
                metadata={"batch_id": batch.id, "total": len(raw_reservations), **stats},
            )

            return {"batch_id": batch.id, "status": "completed", "total": len(raw_reservations), **stats}

        except Exception as e:
            await self._repo.update_import_batch(batch.id, {
                "status": "failed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "duration_ms": int((time.monotonic() - start_time) * 1000),
            })
            logger.error("Import batch %s failed: %s", batch.id, str(e))
            raise

    async def _process_single_reservation(
        self, tenant_id: str, property_id: str, connector_id: str, batch_id: str,
        canonical: CanonicalReservation,
        room_reverse: Dict[str, str],
        rate_reverse: Dict[str, str],
    ) -> Dict[str, Any]:
        """Process a single reservation: dedup, import/modify/cancel."""

        # Check for existing import (idempotency)
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
            channel_name=canonical.channel_name,
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

        # Determine action
        if canonical.status == ReservationStatus.CANCELLED:
            imported.is_cancellation = True
            if existing and existing.get("pms_booking_id"):
                # Cancel existing PMS booking
                await self._cancel_pms_booking(tenant_id, existing["pms_booking_id"])
                imported.import_status = ImportStatus.CANCELLED
                imported.pms_booking_id = existing["pms_booking_id"]
                await self._repo.upsert_imported_reservation(imported.to_doc())
                return {"action": "cancelled", "acknowledge": True}
            elif existing:
                imported.import_status = ImportStatus.CANCELLED
                await self._repo.upsert_imported_reservation(imported.to_doc())
                return {"action": "cancelled", "acknowledge": True}
            else:
                imported.import_status = ImportStatus.CANCELLED
                await self._repo.upsert_imported_reservation(imported.to_doc())
                return {"action": "cancelled", "acknowledge": True}

        if existing:
            if existing.get("import_status") in ("created", "modified", "acknowledged"):
                # Check if this is a modification
                if self._is_modification(existing, imported.to_doc()):
                    imported.is_modification = True
                    imported.previous_version_id = existing.get("id")
                    imported.pms_booking_id = existing.get("pms_booking_id")
                    if imported.pms_booking_id:
                        await self._modify_pms_booking(tenant_id, imported)
                    imported.import_status = ImportStatus.MODIFIED
                    await self._repo.upsert_imported_reservation(imported.to_doc())
                    return {"action": "modified", "acknowledge": True}
                else:
                    imported.import_status = ImportStatus.DUPLICATE
                    await self._repo.upsert_imported_reservation(imported.to_doc())
                    return {"action": "duplicate", "acknowledge": True}

        # New reservation - check mapping validity
        if not pms_room_type:
            imported.import_status = ImportStatus.REVIEW
            imported.review_reason = f"No mapping for room type: {canonical.room_type_id}"
            await self._repo.upsert_imported_reservation(imported.to_doc())
            return {"action": "review", "acknowledge": False}

        # Create PMS booking
        try:
            pms_booking_id = await self._create_pms_booking(tenant_id, property_id, canonical, pms_room_type)
            imported.pms_booking_id = pms_booking_id
            imported.import_status = ImportStatus.CREATED
            await self._repo.upsert_imported_reservation(imported.to_doc())
            return {"action": "new", "acknowledge": True}
        except Exception as e:
            imported.import_status = ImportStatus.FAILED
            imported.error_message = str(e)
            await self._repo.upsert_imported_reservation(imported.to_doc())
            return {"action": "failed", "acknowledge": False}

    async def _create_pms_booking(
        self, tenant_id: str, property_id: str,
        canonical: CanonicalReservation, pms_room_type: str,
    ) -> str:
        """Create a booking in the PMS from a canonical reservation."""
        booking_id = str(uuid.uuid4())

        # Find or create guest
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
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "channel_manager",
        }
        await db.bookings.insert_one(booking)
        logger.info("Created PMS booking %s from external %s", booking_id, canonical.external_id)
        return booking_id

    async def _modify_pms_booking(self, tenant_id: str, imported: ImportedReservation):
        """Modify an existing PMS booking based on imported changes."""
        if not imported.pms_booking_id:
            return
        updates = {
            "check_in": imported.arrival_date,
            "check_out": imported.departure_date,
            "adults": imported.adult_count,
            "children": imported.child_count,
            "total_amount": imported.total_amount,
            "special_requests": imported.special_requests,
            "updated_at": datetime.now(timezone.utc).isoformat(),
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
        """Cancel an existing PMS booking."""
        await db.bookings.update_one(
            {"id": pms_booking_id, "tenant_id": tenant_id},
            {"$set": {
                "status": "cancelled",
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
                "cancelled_by": "channel_manager",
            }},
        )
        logger.info("Cancelled PMS booking %s", pms_booking_id)

    async def _find_or_create_guest(self, tenant_id: str, canonical: CanonicalReservation) -> str:
        """Find existing guest by email or create new one."""
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
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.guests.insert_one(guest)
        return guest_id

    def _is_modification(self, existing: Dict, new: Dict) -> bool:
        """Detect if a re-received reservation is a modification."""
        compare_fields = ["arrival_date", "departure_date", "adult_count", "child_count", "total_amount", "room_type_external_id"]
        for f in compare_fields:
            if existing.get(f) != new.get(f):
                return True
        return False

    async def _pull_from_provider(
        self, connector: ConnectorAccount,
        date_start: Optional[str], date_end: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Pull reservations from the external provider."""
        if connector.provider == ConnectorProvider.HOTELRUNNER:
            auth = HotelRunnerAuth.from_credentials(connector.credentials)
            client = HotelRunnerClient(auth=auth, sandbox=True)
            try:
                return await client.pull_reservations(date_start, date_end)
            finally:
                await client.close()
        raise ValueError(f"Unsupported provider: {connector.provider}")

    async def _acknowledge_to_provider(self, connector: ConnectorAccount, reservation_ids: List[str]):
        """Send acknowledgement to provider for received reservations."""
        if connector.provider == ConnectorProvider.HOTELRUNNER:
            auth = HotelRunnerAuth.from_credentials(connector.credentials)
            client = HotelRunnerClient(auth=auth, sandbox=True)
            try:
                await client.acknowledge_reservations(reservation_ids)
            finally:
                await client.close()

    async def get_review_queue(self, tenant_id: str, connector_id: Optional[str] = None) -> List[Dict]:
        """Get reservations needing manual review."""
        return await self._repo.get_imported_reservations(tenant_id, connector_id, status="review")

    async def approve_review(
        self, tenant_id: str, reservation_id: str, actor_id: str,
        room_type_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Approve a reservation in the review queue and import it."""
        imported = await self._repo.get_imported_reservation_by_external_id(tenant_id, "", reservation_id)
        # Fetch by id if external lookup fails
        if not imported:
            results = await self._repo.get_imported_reservations(tenant_id, status="review")
            imported = next((r for r in results if r.get("id") == reservation_id), None)

        if not imported:
            raise ValueError("Imported reservation not found")

        pms_room_type = room_type_override or imported.get("room_type_mapped_id")
        if not pms_room_type:
            raise ValueError("Room type mapping required for approval")

        # Create canonical for PMS booking creation
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

        imported["pms_booking_id"] = pms_booking_id
        imported["import_status"] = ImportStatus.CREATED.value
        imported["reviewed_by"] = actor_id
        imported["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        await self._repo.upsert_imported_reservation(imported)

        return {"reservation_id": reservation_id, "pms_booking_id": pms_booking_id, "status": "created"}

    async def get_import_batches(self, tenant_id: str, connector_id: Optional[str] = None) -> List[Dict]:
        return await self._repo.get_import_batches(tenant_id, connector_id)

    async def get_imported_reservations(
        self, tenant_id: str, connector_id: Optional[str] = None,
        status: Optional[str] = None, limit: int = 100,
    ) -> List[Dict]:
        return await self._repo.get_imported_reservations(tenant_id, connector_id, status, limit)

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
