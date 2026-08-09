"""Persistent non-production reservation import bridge for the Exely pilot."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from pymongo.errors import DuplicateKeyError

from bootstrap.migrations.versions.v010_exely_reservation_lifecycle import (
    ExelyReservationLifecycleMigration,
)
from bootstrap.migrations.versions.v011_exely_reservation_fencing import (
    ExelyReservationFencingMigration,
)
from core.database import db
from core.tenant_db import tenant_context
from domains.channel_manager.providers.common_ingest import ingest_reservation
from domains.channel_manager.providers.exely.lifecycle import ACK_PENDING, PMS_DURABLE
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.pms_lifecycle import process_reservation_version


class PilotImportError(RuntimeError):
    """Payload-free, fail-closed pilot import failure."""


@dataclass(frozen=True)
class DurableImportVerification:
    durable_pms_state: bool
    lineage_match: bool
    version_match: bool
    ack_state_pending: bool
    ack_reservation_id_present: bool
    ack_confirmation_id_present: bool
    ack_create_datetime_present: bool
    ack_last_modify_datetime_present: bool
    booking_count: int

    @property
    def success(self) -> bool:
        return all(
            (
                self.durable_pms_state,
                self.lineage_match,
                self.version_match,
                self.ack_state_pending,
                self.ack_reservation_id_present,
                self.ack_confirmation_id_present,
                self.ack_create_datetime_present,
                self.ack_last_modify_datetime_present,
                self.booking_count > 0,
            )
        )


@dataclass(frozen=True)
class DurableImportResult:
    verification: DurableImportVerification
    local_pms_write_count: int
    already_durable: bool


def _event_type(raw_reservation: dict[str, Any]) -> str:
    status = str(raw_reservation.get("status") or "").lower()
    if status in {"cancel", "cancelled"}:
        return "cancellation"
    if status in {"modify", "modified"}:
        return "modification"
    return "reservation"


def validate_exact_mapping(
    raw_reservation: dict[str, Any],
    *,
    room_type_code: str,
    rate_plan_code: str,
) -> None:
    rooms = raw_reservation.get("rooms")
    if not isinstance(rooms, list) or not rooms:
        raise PilotImportError("BLOCKED_PILOT_MAPPING_NOT_DISCOVERED")
    for room in rooms:
        if not isinstance(room, dict):
            raise PilotImportError("BLOCKED_PILOT_MAPPING_NOT_DISCOVERED")
        if not hmac.compare_digest(str(room.get("room_type_code") or ""), room_type_code):
            raise PilotImportError("BLOCKED_PILOT_MAPPING_NOT_DISCOVERED")
        if not hmac.compare_digest(str(room.get("rate_plan_code") or ""), rate_plan_code):
            raise PilotImportError("BLOCKED_PILOT_MAPPING_NOT_DISCOVERED")


async def ensure_pilot_schema() -> None:
    """Install only the canonical Exely lifecycle indexes in the pilot DB."""
    await ExelyReservationLifecycleMigration().up(db)
    await ExelyReservationFencingMigration().up(db)


async def ensure_pilot_mapping(
    tenant_id: str,
    *,
    room_type_code: str,
    rate_plan_code: str,
    pms_room_type: str,
) -> int:
    query = {
        "tenant_id": tenant_id,
        "exely_room_code": room_type_code,
        "exely_rate_plan_code": rate_plan_code,
    }
    existing = await db.exely_room_mappings.find_one(query, {"_id": 0, "pms_room_type": 1})
    if existing:
        if not hmac.compare_digest(str(existing.get("pms_room_type") or ""), pms_room_type):
            raise PilotImportError("BLOCKED_PILOT_MAPPING_CONFLICT")
        return 0

    mapping_id = hashlib.sha256("\x1f".join((tenant_id, room_type_code, rate_plan_code)).encode("utf-8")).hexdigest()
    try:
        await db.exely_room_mappings.insert_one(
            {
                "id": mapping_id,
                "tenant_id": tenant_id,
                "exely_room_code": room_type_code,
                "exely_rate_plan_code": rate_plan_code,
                "pms_room_type": pms_room_type,
                "source": "exely_pilot",
            }
        )
        return 1
    except DuplicateKeyError:
        concurrent = await db.exely_room_mappings.find_one(query, {"_id": 0, "pms_room_type": 1})
        if not concurrent or not hmac.compare_digest(str(concurrent.get("pms_room_type") or ""), pms_room_type):
            raise PilotImportError("BLOCKED_PILOT_MAPPING_CONFLICT") from None
        return 0


async def prepare_pilot_persistence(
    tenant_id: str,
    *,
    room_type_code: str,
    rate_plan_code: str,
    pms_room_type: str,
) -> None:
    """Prove pilot DB access before consuming an undelivered reservation."""
    try:
        await ensure_pilot_schema()
        await ensure_pilot_mapping(
            tenant_id,
            room_type_code=room_type_code,
            rate_plan_code=rate_plan_code,
            pms_room_type=pms_room_type,
        )
    except PilotImportError:
        raise
    except Exception as exc:
        raise PilotImportError("BLOCKED_PERSISTENT_TEST_DB_PREFLIGHT_FAILED") from exc


async def verify_durable_import(
    tenant_id: str,
    property_id: str,
    raw_reservation: dict[str, Any],
    *,
    room_type_code: str,
    rate_plan_code: str,
) -> DurableImportVerification:
    external_id = str(raw_reservation.get("reservation_id") or "")
    expected_version = str(raw_reservation.get("last_modify") or "")
    current = await db.exely_reservations.find_one(
        {"tenant_id": tenant_id, "property_id": property_id, "external_id": external_id},
        {
            "_id": 0,
            "provider_version_identity": 1,
            "provider_version_key": 1,
            "delivery_state": 1,
            "room_stay_lineage": 1,
        },
    )
    identity = str((current or {}).get("provider_version_identity") or "")
    version = (
        await db.exely_reservation_versions.find_one(
            {"tenant_id": tenant_id, "version_identity": identity},
            {
                "_id": 0,
                "provider_reservation_id": 1,
                "provider_version_key": 1,
                "processing_state": 1,
                "ack_state": 1,
                "room_stays": 1,
                "ack_confirmations": 1,
                "durable_expectations": 1,
            },
        )
        if identity
        else None
    )
    confirmations = list((version or {}).get("ack_confirmations") or [])
    expectations = list((version or {}).get("durable_expectations") or [])
    confirmation_ids = {str(row.get("pms_booking_id") or "") for row in confirmations}
    expectation_ids = {str(row.get("pms_booking_id") or "") for row in expectations}
    lineage_ids = {str(row.get("pms_booking_id") or "") for row in (current or {}).get("room_stay_lineage") or [] if row.get("active", True)}
    ids_valid = bool(confirmation_ids) and "" not in confirmation_ids
    lineage_match = ids_valid and confirmation_ids == expectation_ids == lineage_ids

    booking_match = lineage_match
    for expected in expectations:
        booking = await db.bookings.find_one(
            {"tenant_id": tenant_id, "id": expected.get("pms_booking_id")},
            {
                "_id": 0,
                "status": 1,
                "provider_version_key": 1,
                "inventory_release_pending": 1,
            },
        )
        if not booking or booking.get("status") != expected.get("status") or booking.get("provider_version_key") != expected_version or booking.get("inventory_release_pending"):
            booking_match = False
            break

    room_stays = list((version or {}).get("room_stays") or [])
    mapping_match = bool(room_stays) and all(
        isinstance(room, dict) and hmac.compare_digest(str(room.get("room_type_code") or ""), room_type_code) and hmac.compare_digest(str(room.get("rate_plan_code") or ""), rate_plan_code)
        for room in room_stays
    )
    version_match = bool(version) and all(
        (
            hmac.compare_digest(str(version.get("provider_reservation_id") or ""), external_id),
            hmac.compare_digest(str(version.get("provider_version_key") or ""), expected_version),
            hmac.compare_digest(str((current or {}).get("provider_version_key") or ""), expected_version),
            mapping_match,
        )
    )
    durable_pms_state = bool(version) and version.get("processing_state") == PMS_DURABLE and booking_match
    ack_state_pending = bool(version) and version.get("ack_state") == ACK_PENDING and (current or {}).get("delivery_state") == ACK_PENDING

    return DurableImportVerification(
        durable_pms_state=durable_pms_state,
        lineage_match=lineage_match,
        version_match=version_match,
        ack_state_pending=ack_state_pending,
        ack_reservation_id_present=bool((version or {}).get("provider_reservation_id")),
        ack_confirmation_id_present=ids_valid,
        ack_create_datetime_present=bool(confirmations) and all(bool(row.get("pms_created_at")) for row in confirmations),
        ack_last_modify_datetime_present=bool((version or {}).get("provider_version_key")),
        booking_count=len(confirmation_ids) if ids_valid else 0,
    )


async def import_reservation_durably(
    tenant_id: str,
    property_id: str,
    raw_reservation: dict[str, Any],
    *,
    room_type_code: str,
    rate_plan_code: str,
    pms_room_type: str,
) -> DurableImportResult:
    """Run one reservation through the canonical ingest and PMS lifecycle."""
    validate_exact_mapping(
        raw_reservation,
        room_type_code=room_type_code,
        rate_plan_code=rate_plan_code,
    )
    await prepare_pilot_persistence(
        tenant_id,
        room_type_code=room_type_code,
        rate_plan_code=rate_plan_code,
        pms_room_type=pms_room_type,
    )

    provider_payload = {**raw_reservation, "property_id": property_id}
    with tenant_context(tenant_id):
        ingest = await ingest_reservation(
            provider="exely",
            tenant_id=tenant_id,
            raw_payload=provider_payload,
            normalizer=normalize_reservation,
            event_type=_event_type(provider_payload),
            source="pilot_import",
        )
        if not ingest.get("success") or ingest.get("action") in {"error", "hold"}:
            raise PilotImportError("BLOCKED_CANONICAL_PERSISTENCE_FAILED")

        current = await db.exely_reservations.find_one(
            {
                "tenant_id": tenant_id,
                "property_id": property_id,
                "external_id": str(raw_reservation.get("reservation_id") or ""),
            },
            {"_id": 0},
        )
        if not current:
            raise PilotImportError("BLOCKED_CANONICAL_PERSISTENCE_FAILED")

        processed = await process_reservation_version(tenant_id, current)
        if not processed.get("success"):
            raise PilotImportError("BLOCKED_CANONICAL_LIFECYCLE_FAILED")

        verification = await verify_durable_import(
            tenant_id,
            property_id,
            raw_reservation,
            room_type_code=room_type_code,
            rate_plan_code=rate_plan_code,
        )
    if not verification.success:
        raise PilotImportError("BLOCKED_DURABLE_PMS_READBACK_FAILED")

    already_durable = processed.get("reason") == "ALREADY_DURABLE"
    local_writes = sum(int(processed.get(key) or 0) for key in ("created", "updated", "cancelled"))
    if not already_durable and local_writes < 1:
        raise PilotImportError("BLOCKED_LOCAL_PMS_WRITE_NOT_DURABLE")
    return DurableImportResult(
        verification=verification,
        local_pms_write_count=local_writes,
        already_durable=already_durable,
    )


async def load_ack_ready_reservation(
    tenant_id: str,
    property_id: str,
    raw_reservation: dict[str, Any],
    *,
    room_type_code: str,
    rate_plan_code: str,
) -> dict[str, Any]:
    verification = await verify_durable_import(
        tenant_id,
        property_id,
        raw_reservation,
        room_type_code=room_type_code,
        rate_plan_code=rate_plan_code,
    )
    if not verification.success:
        raise PilotImportError("BLOCKED_ACK_DURABLE_STATE_NOT_VERIFIED")
    current = await db.exely_reservations.find_one(
        {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "external_id": str(raw_reservation.get("reservation_id") or ""),
        },
        {"_id": 0},
    )
    if not current:
        raise PilotImportError("BLOCKED_ACK_DURABLE_STATE_NOT_VERIFIED")
    return current
