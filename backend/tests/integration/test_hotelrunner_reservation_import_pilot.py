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
from datetime import UTC, datetime, timedelta
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
_ALLOWED_OPERATIONS = frozenset(
    {
        "reservation_import",
        "reservation_replay",
        "reservation_reconciliation",
        "reservation_history_import",
    }
)
_SOURCE_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_RECONCILIATION_WINDOW = timedelta(minutes=30)


class ReservationPilotError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReservationPilotSettings:
    operation: str
    base_url: str
    approved_head: str
    correlation_label: str
    tenant_id: str
    source_timestamp: datetime | None
    token: str = field(repr=False)
    hr_id: str = field(repr=False)
    hmac_key: str = field(repr=False)
    target_guest_name: str | None = field(default=None, repr=False)


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

    source_timestamp = None
    target_guest_name = None
    if operation in {"reservation_reconciliation", "reservation_history_import"}:
        raw_timestamp = _required("HOTELRUNNER_PILOT_SOURCE_TIMESTAMP")
        if not _SOURCE_TIMESTAMP_PATTERN.fullmatch(raw_timestamp):
            raise ReservationPilotError("BLOCKED_INVALID_RECONCILIATION_SOURCE_TIMESTAMP")
        try:
            source_timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ReservationPilotError("BLOCKED_INVALID_RECONCILIATION_SOURCE_TIMESTAMP") from exc
        age = datetime.now(UTC) - source_timestamp
        if age < timedelta(0) or age > timedelta(hours=48):
            raise ReservationPilotError("BLOCKED_UNSAFE_RECONCILIATION_SOURCE_TIMESTAMP")
        target_guest_name = _required("HOTELRUNNER_PILOT_TARGET_GUEST_NAME")

    return ReservationPilotSettings(
        operation=operation,
        base_url=base_url,
        approved_head=approved_head,
        correlation_label=correlation_label,
        tenant_id=f"hotelrunner-pilot-{correlation_label}",
        source_timestamp=source_timestamp,
        token=_required("HOTELRUNNER_PILOT_TOKEN"),
        hr_id=_required("HOTELRUNNER_PILOT_HR_ID"),
        hmac_key=hmac_key,
        target_guest_name=target_guest_name,
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


def _parse_provider_timestamp(raw: Any) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise ReservationPilotError("BLOCKED_HISTORY_TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReservationPilotError("BLOCKED_HISTORY_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None:
        raise ReservationPilotError("BLOCKED_HISTORY_TIMESTAMP_INVALID")
    return parsed.astimezone(UTC)


def _safe_reservation_correlation(settings: ReservationPilotSettings, message_uid: Any) -> str:
    if not isinstance(message_uid, str) or not message_uid.strip():
        raise ReservationPilotError("BLOCKED_HISTORY_IDENTITY_INVALID")
    return hmac.new(
        settings.hmac_key.encode(),
        message_uid.strip().encode(),
        hashlib.sha256,
    ).hexdigest()[:12]


def _guest_identity_digest(settings: ReservationPilotSettings, raw: Any) -> bytes | None:
    if not isinstance(raw, str):
        return None
    normalized = " ".join(raw.split()).casefold()
    if not normalized:
        return None
    return hmac.new(
        settings.hmac_key.encode(),
        normalized.encode(),
        hashlib.sha256,
    ).digest()


async def _fetch_target_history_reservation(
    settings: ReservationPilotSettings,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if settings.source_timestamp is None:
        raise ReservationPilotError("BLOCKED_MISSING_RECONCILIATION_SOURCE_TIMESTAMP")
    if settings.target_guest_name is None:
        raise ReservationPilotError("BLOCKED_MISSING_RECONCILIATION_TARGET")

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

        history = await provider.fetch_reservations(
            undelivered=False,
            from_date=(settings.source_timestamp - timedelta(days=1)).date().isoformat(),
            per_page=100,
            page=None,
        )
        if not history.success or not isinstance(history.data, dict):
            raise ReservationPilotError("BLOCKED_HISTORY_READ_FAILED")
        reservations = history.data.get("reservations")
        if not isinstance(reservations, list):
            raise ReservationPilotError("BLOCKED_HISTORY_RESPONSE_INVALID")

        window_start = settings.source_timestamp - _RECONCILIATION_WINDOW
        window_end = settings.source_timestamp + _RECONCILIATION_WINDOW
        candidates = []
        for reservation in reservations:
            if not isinstance(reservation, dict):
                raise ReservationPilotError("BLOCKED_HISTORY_RESPONSE_INVALID")
            completed_at = _parse_provider_timestamp(reservation.get("completed_at"))
            if window_start <= completed_at <= window_end:
                candidates.append(reservation)

        target_digest = _guest_identity_digest(settings, settings.target_guest_name)
        if target_digest is None:
            raise ReservationPilotError("BLOCKED_INVALID_RECONCILIATION_TARGET")
        target_candidates = [
            reservation
            for reservation in candidates
            if (candidate_digest := _guest_identity_digest(settings, reservation.get("guest"))) is not None and hmac.compare_digest(candidate_digest, target_digest)
        ]
        if len(target_candidates) != 1:
            if not target_candidates:
                raise ReservationPilotError("BLOCKED_TARGET_HISTORY_RESERVATION_NOT_FOUND")
            raise ReservationPilotError("CONFLICT_MULTIPLE_TARGET_HISTORY_RESERVATIONS")

        candidate = target_candidates[0]
        candidate_uid = candidate.get("message_uid")
        candidate_label = _safe_reservation_correlation(settings, candidate_uid)

        undelivered = await provider.fetch_reservations(
            undelivered=True,
            per_page=100,
            page=1,
        )
        if not undelivered.success or not isinstance(undelivered.data, dict):
            raise ReservationPilotError("BLOCKED_UNDELIVERED_READ_FAILED")
        queued = undelivered.data.get("raw_reservations")
        if not isinstance(queued, list):
            raise ReservationPilotError("BLOCKED_UNDELIVERED_RESPONSE_INVALID")
        queued_matches = [item for item in queued if isinstance(item, dict) and isinstance(item.get("message_uid"), str) and hmac.compare_digest(item["message_uid"], candidate_uid)]
        if len(queued_matches) > 1:
            raise ReservationPilotError("CONFLICT_MULTIPLE_UNDELIVERED_MATCHES")
        if guard.write_count != 0:
            raise ReservationPilotError("FAIL_READONLY_PROVIDER_WRITE_DETECTED")

        state = str(candidate.get("state") or "").strip().upper()
        metadata = {
            "credential_read_ok": True,
            "delivery_state": "UNDELIVERED" if queued_matches else "DELIVERED_OR_NOT_QUEUED",
            "exact_head_match": True,
            "get_count": guard.get_count,
            "history_window_match_count_class": "ONE" if len(candidates) == 1 else "MULTIPLE",
            "history_match_count_class": "ONE",
            "operation": settings.operation,
            "pms_number_present": bool(candidate.get("pms_number")),
            "provider_state_class": state if state in {"RESERVED", "CONFIRMED", "CANCELED"} else "UNKNOWN",
            "provider_write_count": guard.write_count,
            "reservation_correlation_label": candidate_label,
            "result": "PASS",
            "undelivered_match_count_class": "ONE" if queued_matches else "ZERO",
        }
        return candidate, metadata
    finally:
        guard.restore()
        await provider._client.close()


async def _reconcile_reservation_history(
    settings: ReservationPilotSettings,
) -> dict[str, Any]:
    _, metadata = await _fetch_target_history_reservation(settings)
    return metadata


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


async def test_hotelrunner_pilot_reservation_reconciliation(record_property):
    settings = _load_settings()
    if settings.operation != "reservation_reconciliation":
        pytest.fail(
            "BLOCKED_RESERVATION_RECONCILIATION_TARGET_OPERATION_MISMATCH",
            pytrace=False,
        )
    try:
        metadata = await _reconcile_reservation_history(settings)
        _record(record_property, **metadata)
        assert metadata["provider_write_count"] == 0
    except ReservationPilotError as exc:
        pytest.fail(str(exc), pytrace=False)


async def test_hotelrunner_pilot_reservation_history_import(record_property):
    settings = _load_settings()
    if settings.operation != "reservation_history_import":
        pytest.fail(
            "BLOCKED_RESERVATION_HISTORY_IMPORT_TARGET_OPERATION_MISMATCH",
            pytrace=False,
        )
    try:
        raw, provider_metadata = await _fetch_target_history_reservation(settings)
        if provider_metadata["undelivered_match_count_class"] != "ZERO":
            raise ReservationPilotError("BLOCKED_HISTORY_TARGET_STILL_UNDELIVERED")

        canonical, _ = await _import_durably(settings, raw)
        ext_id = str(canonical["external_reservation_id"])
        replay = await _persist_and_process(
            settings.tenant_id,
            _resolve_property_id(raw),
            raw,
            "reservation_pull",
            source_ip="hotelrunner-pilot-history-replay",
        )
        if replay.status not in {"duplicate", "processed"}:
            raise ReservationPilotError("BLOCKED_HISTORY_IMPORT_REPLAY_NOT_IDEMPOTENT")

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
            raise ReservationPilotError("BLOCKED_HISTORY_IMPORT_DUPLICATE_CREATED")

        _record(
            record_property,
            credential_read_ok=True,
            durable_pms_booking=True,
            exact_head_match=True,
            get_count=provider_metadata["get_count"],
            history_match_count_class=provider_metadata["history_match_count_class"],
            import_record_count=import_count,
            match_count_class="ONE",
            operation=settings.operation,
            pms_booking_count=booking_count,
            provider_state_class=provider_metadata["provider_state_class"],
            provider_write_count=provider_metadata["provider_write_count"],
            replay_duplicate_safe=True,
            reservation_correlation_label=provider_metadata["reservation_correlation_label"],
            result="PASS",
        )
        assert provider_metadata["provider_write_count"] == 0
    except ReservationPilotError as exc:
        pytest.fail(str(exc), pytrace=False)
