"""Controlled HotelRunner test-account reservation import/replay pilot.

Provider access is GET-only. The test writes only to the ephemeral local CI MongoDB,
runs the same unified ingest/import bridge used by production reservation polling,
and never sends HotelRunner delivery ACKs.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from core.database import db
from core.import_bridge_service import auto_import_reservation_to_pms
from domains.channel_manager.ingest.normalizer import normalize_hotelrunner
from domains.channel_manager.providers.hotelrunner.provider import HotelRunnerProvider
from domains.channel_manager.providers.hotelrunner_shared import (
    _persist_and_process,
    _resolve_property_id,
)
from tests.integration.test_hotelrunner_ari_pilot import PilotHttpGuard

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.external,
    pytest.mark.hotelrunner_pilot,
]

_OFFICIAL_BASE_URL = "https://app.hotelrunner.com"
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_ALLOWED_OPERATIONS = frozenset({"reservation_import", "reservation_replay"})


class ReservationPilotError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReservationPilotSettings:
    operation: str
    base_url: str
    approved_head: str
    correlation_label: str
    tenant_id: str
    token: str = field(repr=False)
    hr_id: str = field(repr=False)


def _required(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise ReservationPilotError(f"BLOCKED_MISSING_CONFIGURATION:{name}")
    return value


def _load_settings() -> ReservationPilotSettings:
    mongo_url = str(os.environ.get("MONGO_URL") or "")
    if not mongo_url.startswith(("mongodb://localhost:", "mongodb://127.0.0.1:")):
        raise ReservationPilotError("BLOCKED_NON_LOCAL_TEST_DATABASE")
    if str(os.environ.get("DB_NAME") or "") != "hotel_pms_test":
        raise ReservationPilotError("BLOCKED_NON_TEST_DATABASE_NAME")
    if os.environ.get("APP_ENV") != "test" or os.environ.get("TESTING") != "1":
        raise ReservationPilotError("BLOCKED_NON_TEST_APPLICATION_ENVIRONMENT")

    operation = _required("HOTELRUNNER_PILOT_OPERATION")
    if operation not in _ALLOWED_OPERATIONS:
        raise ReservationPilotError("BLOCKED_RESERVATION_IMPORT_OPERATION_MISMATCH")
    if os.environ.get("HOTELRUNNER_PILOT_WRITE_APPROVED") == "true":
        raise ReservationPilotError("BLOCKED_READONLY_WRITE_CONFLICT")
    if os.environ.get("HOTELRUNNER_PILOT_ACCOUNT_CONFIRMED") != "true":
        raise ReservationPilotError("BLOCKED_TEST_ACCOUNT_NOT_CONFIRMED")

    base_url = _required("HOTELRUNNER_PILOT_BASE_URL").rstrip("/")
    if base_url != _OFFICIAL_BASE_URL:
        raise ReservationPilotError("BLOCKED_UNAPPROVED_PROVIDER_HOST")

    approved_head = _required("HOTELRUNNER_PILOT_APPROVED_HEAD").lower()
    actual_head = _required("GITHUB_SHA").lower()
    if not _SHA_PATTERN.fullmatch(approved_head) or not hmac.compare_digest(approved_head, actual_head):
        raise ReservationPilotError("BLOCKED_EXACT_HEAD_MISMATCH")

    hmac_key = _required("HOTELRUNNER_PILOT_HMAC_KEY")
    if len(hmac_key) < 32:
        raise ReservationPilotError("BLOCKED_WEAK_PILOT_HMAC_KEY")
    run_id = _required("HOTELRUNNER_PILOT_RUN_ID")
    correlation_label = hmac.new(
        hmac_key.encode(),
        f"{run_id}:{approved_head}:{operation}".encode(),
        hashlib.sha256,
    ).hexdigest()[:12]

    return ReservationPilotSettings(
        operation=operation,
        base_url=base_url,
        approved_head=approved_head,
        correlation_label=correlation_label,
        tenant_id=f"hotelrunner-pilot-{correlation_label}",
        token=_required("HOTELRUNNER_PILOT_TOKEN"),
        hr_id=_required("HOTELRUNNER_PILOT_HR_ID"),
    )


def _record(record_property, **values: Any) -> None:
    for key, value in sorted(values.items()):
        record_property(key, value)


async def _fetch_one_undelivered(settings: ReservationPilotSettings):
    provider = HotelRunnerProvider(
        token=settings.token,
        hr_id=settings.hr_id,
        connection_id=f"pilot:{settings.correlation_label}",
        base_url=settings.base_url,
        max_retries=0,
    )
    guard = PilotHttpGuard(provider, allow_write=False)
    try:
        connection = await provider.test_connection()
        if not connection.success:
            raise ReservationPilotError("BLOCKED_READONLY_CREDENTIAL_CHECK_FAILED")
        result = await provider.fetch_reservations(undelivered=True, per_page=2, page=1)
        if not result.success or not isinstance(result.data, dict):
            raise ReservationPilotError("BLOCKED_RESERVATION_READ_FAILED")
        reservations = result.data.get("raw_reservations")
        if not isinstance(reservations, list):
            raise ReservationPilotError("BLOCKED_RESERVATION_RESPONSE_INVALID")
        if len(reservations) != 1:
            if not reservations:
                raise ReservationPilotError("BLOCKED_NO_UNDELIVERED_RESERVATION")
            raise ReservationPilotError("BLOCKED_MULTIPLE_UNDELIVERED_RESERVATIONS")
        if guard.write_count != 0:
            raise ReservationPilotError("FAIL_READONLY_PROVIDER_WRITE_DETECTED")
        return reservations[0], guard.get_count, guard.write_count
    finally:
        guard.restore()
        await provider._client.close()


async def _seed_local_mappings(settings: ReservationPilotSettings, raw: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    canonical = normalize_hotelrunner(raw)
    required = (
        "external_reservation_id",
        "guest_name",
        "check_in",
        "check_out",
        "room_type_code",
    )
    if not all(canonical.get(key) for key in required):
        raise ReservationPilotError("BLOCKED_RESERVATION_CANONICAL_SHAPE_INVALID")

    property_id = _resolve_property_id(raw)
    tenant_id = settings.tenant_id
    room_code = str(canonical["room_type_code"])
    rate_code = str(canonical.get("rate_plan_code") or "")

    await db.room_mappings.update_one(
        {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "provider": "hotelrunner",
            "provider_room_code": room_code,
        },
        {
            "$set": {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "property_id": property_id,
                "provider": "hotelrunner",
                "provider_room_code": room_code,
                "pms_room_type_id": "pilot-room-type",
                "pms_room_type_name": "Pilot Room Type",
                "is_active": True,
            }
        },
        upsert=True,
    )
    if rate_code:
        await db.rate_plan_mappings.update_one(
            {
                "tenant_id": tenant_id,
                "property_id": property_id,
                "provider": "hotelrunner",
                "provider_rate_code": rate_code,
            },
            {
                "$set": {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "property_id": property_id,
                    "provider": "hotelrunner",
                    "provider_rate_code": rate_code,
                    "pms_rate_plan_id": "pilot-rate-plan",
                    "pms_rate_plan_name": "Pilot Rate Plan",
                    "is_active": True,
                }
            },
            upsert=True,
        )

    await db.imported_reservations.create_index(
        [("tenant_id", 1), ("connector_id", 1), ("external_reservation_id", 1)],
        name="idx_import_unique_ext_res",
        unique=True,
    )
    return property_id, canonical


async def _import_durably(settings: ReservationPilotSettings, raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    property_id, canonical = await _seed_local_mappings(settings, raw)
    tenant_id = settings.tenant_id
    ext_id = str(canonical["external_reservation_id"])

    result = await _persist_and_process(
        tenant_id,
        property_id,
        raw,
        "reservation_pull",
        source_ip="hotelrunner-pilot",
    )
    if result.status != "processed":
        raise ReservationPilotError("BLOCKED_CANONICAL_PERSISTENCE_FAILED")

    import_record = await db.imported_reservations.find_one(
        {
            "tenant_id": tenant_id,
            "provider": "hotelrunner",
            "external_reservation_id": ext_id,
        },
        {"_id": 0},
    )
    if not import_record or import_record.get("import_status") != "pending_auto_import":
        raise ReservationPilotError("BLOCKED_IMPORT_BRIDGE_NOT_DURABLE")

    success, _ = await auto_import_reservation_to_pms(import_record["id"])
    if not success:
        raise ReservationPilotError("BLOCKED_PMS_BOOKING_IMPORT_FAILED")

    bookings = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "external_reservation_id": ext_id,
            "booking_source": "ota_import",
        },
        {"_id": 0},
    ).to_list(3)
    if len(bookings) != 1:
        raise ReservationPilotError("BLOCKED_DURABLE_PMS_READBACK_FAILED")

    imported = await db.imported_reservations.find_one(
        {"id": import_record["id"], "tenant_id": tenant_id},
        {"_id": 0},
    )
    if not imported or imported.get("import_status") != "imported" or imported.get("booking_id") != bookings[0].get("id"):
        raise ReservationPilotError("BLOCKED_IMPORT_BOOKING_LINK_NOT_DURABLE")
    return canonical, bookings[0]


async def test_hotelrunner_pilot_reservation_import(record_property):
    settings = _load_settings()
    if settings.operation != "reservation_import":
        pytest.fail("BLOCKED_RESERVATION_IMPORT_TARGET_OPERATION_MISMATCH", pytrace=False)
    try:
        raw, get_count, write_count = await _fetch_one_undelivered(settings)
        _, booking = await _import_durably(settings, raw)
        _record(
            record_property,
            credential_read_ok=True,
            durable_pms_booking=True,
            exact_head_match=True,
            get_count=get_count,
            match_count_class="ONE",
            operation=settings.operation,
            pms_booking_count=1,
            provider_write_count=write_count,
            result="PASS",
        )
        assert booking.get("id")
        assert write_count == 0
    except ReservationPilotError as exc:
        pytest.fail(str(exc), pytrace=False)


async def test_hotelrunner_pilot_reservation_replay(record_property):
    settings = _load_settings()
    if settings.operation != "reservation_replay":
        pytest.fail("BLOCKED_RESERVATION_REPLAY_TARGET_OPERATION_MISMATCH", pytrace=False)
    try:
        raw, get_count, write_count = await _fetch_one_undelivered(settings)
        canonical, _ = await _import_durably(settings, raw)
        ext_id = str(canonical["external_reservation_id"])

        replay = await _persist_and_process(
            settings.tenant_id,
            _resolve_property_id(raw),
            raw,
            "reservation_pull",
            source_ip="hotelrunner-pilot-replay",
        )
        if replay.status not in {"duplicate", "processed"}:
            raise ReservationPilotError("BLOCKED_REPLAY_NOT_IDEMPOTENT")

        booking_count = await db.bookings.count_documents(
            {
                "tenant_id": settings.tenant_id,
                "external_reservation_id": ext_id,
                "booking_source": "ota_import",
            }
        )
        import_count = await db.imported_reservations.count_documents(
            {
                "tenant_id": settings.tenant_id,
                "provider": "hotelrunner",
                "external_reservation_id": ext_id,
            }
        )
        if booking_count != 1 or import_count != 1:
            raise ReservationPilotError("BLOCKED_REPLAY_DUPLICATE_CREATED")

        _record(
            record_property,
            durable_pms_booking=True,
            exact_head_match=True,
            get_count=get_count,
            import_record_count=import_count,
            match_count_class="ONE",
            operation=settings.operation,
            pms_booking_count=booking_count,
            provider_write_count=write_count,
            replay_duplicate_safe=True,
            result="PASS",
        )
        assert write_count == 0
    except ReservationPilotError as exc:
        pytest.fail(str(exc), pytrace=False)
