"""Gated HotelRunner test-account ARI pilot.

This module is only selected by the manual ``hotelrunner-ari-pilot`` workflow.
It never runs as part of the normal CI test collection.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pytest

from channel_manager.connectors.hotelrunner_v2.feature_flags import (
    COLL_FEATURE_FLAGS,
    set_flags,
)
from core.database import db
from domains.channel_manager.providers.hotelrunner import endpoints as ep
from domains.channel_manager.providers.hotelrunner.ari_delivery import (
    COLL_ARI_DELIVERIES,
    STATE_AMBIGUOUS,
    STATE_CONFIRMED,
    STATE_RECONCILIATION_PENDING,
    deliver_hotelrunner_ari,
    reconcile_pending_hotelrunner_ari,
)
from domains.channel_manager.providers.hotelrunner.provider import HotelRunnerProvider

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.external,
    pytest.mark.hotelrunner_pilot,
]

logger = logging.getLogger("hotelrunner.ari_pilot")

_OFFICIAL_PILOT_BASE_URL = "https://app.hotelrunner.com"
_WRITE_OPERATIONS = frozenset({"availability", "rate", "stop_sell", "restriction"})
_ALLOWED_GET_PATHS = frozenset({ep.CHANNELS, ep.ROOMS, ep.RESERVATIONS, ep.TRANSACTION_DETAILS})
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_TERMINAL_STATES = frozenset({STATE_CONFIRMED, "partial_failure", "rejected", "blocked"})


class PilotSafetyError(RuntimeError):
    """Safe, payload-free pilot guard failure."""


@dataclass(frozen=True)
class PilotSettings:
    operation: str
    base_url: str
    test_date: date
    approved_head: str
    run_id: str
    correlation_label: str
    token: str = field(repr=False)
    hr_id: str = field(repr=False)
    inv_code: str = field(repr=False)
    channel_code: str = field(repr=False)
    hmac_key: str = field(repr=False)
    availability: int | None = None
    rate: Decimal | None = None
    stop_sell: int | None = None
    min_stay: int | None = None


class PilotHttpGuard:
    """Allow expected GETs and at most one date-range PUT."""

    def __init__(self, provider: HotelRunnerProvider, *, allow_write: bool):
        self._client = provider._client
        self._original_request = self._client._request
        self._allow_write = allow_write
        self.write_count = 0
        self.get_count = 0
        self.write_http_status: int | None = None
        self.read_http_status: int | None = None
        self.last_exception_class = ""
        self._client._request = self._guarded_request

    async def _guarded_request(self, method: str, path: str, **kwargs):
        normalized_method = str(method).upper()
        if normalized_method == "GET":
            if path not in _ALLOWED_GET_PATHS:
                raise PilotSafetyError("BLOCKED_UNEXPECTED_PROVIDER_GET")
            self.get_count += 1
        elif normalized_method == "PUT":
            if not self._allow_write:
                raise PilotSafetyError("BLOCKED_PROVIDER_WRITE_IN_READONLY_MODE")
            if path != ep.ROOMS_DATERANGE:
                raise PilotSafetyError("BLOCKED_UNEXPECTED_PROVIDER_WRITE_PATH")
            if self.write_count >= 1:
                raise PilotSafetyError("BLOCKED_SECOND_PROVIDER_WRITE_ATTEMPT")
            self.write_count += 1
        else:
            raise PilotSafetyError("BLOCKED_UNEXPECTED_PROVIDER_HTTP_METHOD")

        try:
            result = await self._original_request(normalized_method, path, **kwargs)
        except Exception as exc:
            self.last_exception_class = type(exc).__name__
            raise

        status_code = getattr(result, "status_code", None)
        if isinstance(status_code, int):
            if normalized_method == "PUT":
                self.write_http_status = status_code
            else:
                self.read_http_status = status_code
        return result

    def restore(self) -> None:
        self._client._request = self._original_request


def _required_env(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise PilotSafetyError(f"BLOCKED_MISSING_CONFIGURATION:{name}")
    return value


def _require_local_test_database() -> None:
    mongo_url = str(os.environ.get("MONGO_URL") or "")
    db_name = str(os.environ.get("DB_NAME") or "")
    if not mongo_url.startswith(("mongodb://localhost:", "mongodb://127.0.0.1:")):
        raise PilotSafetyError("BLOCKED_NON_LOCAL_TEST_DATABASE")
    if db_name != "hotel_pms_test":
        raise PilotSafetyError("BLOCKED_NON_TEST_DATABASE_NAME")
    if os.environ.get("APP_ENV") != "test" or os.environ.get("TESTING") != "1":
        raise PilotSafetyError("BLOCKED_NON_TEST_APPLICATION_ENVIRONMENT")


def _parse_int(name: str, *, minimum: int, maximum: int) -> int:
    raw = _required_env(name)
    try:
        value = int(raw)
    except ValueError as exc:
        raise PilotSafetyError(f"BLOCKED_INVALID_CONFIGURATION:{name}") from exc
    if value < minimum or value > maximum:
        raise PilotSafetyError(f"BLOCKED_INVALID_CONFIGURATION:{name}")
    return value


def _load_settings() -> PilotSettings:
    _require_local_test_database()
    operation = _required_env("HOTELRUNNER_PILOT_OPERATION")
    if operation not in {"discovery", "reservation_read", *_WRITE_OPERATIONS}:
        raise PilotSafetyError("BLOCKED_UNSUPPORTED_PILOT_OPERATION")

    write_approved = os.environ.get("HOTELRUNNER_PILOT_WRITE_APPROVED") == "true"
    if operation in {"discovery", "reservation_read"} and write_approved:
        raise PilotSafetyError("BLOCKED_READONLY_WRITE_CONFLICT")
    if operation in _WRITE_OPERATIONS and not write_approved:
        raise PilotSafetyError("BLOCKED_PROVIDER_WRITE_NOT_APPROVED")
    if os.environ.get("HOTELRUNNER_PILOT_ACCOUNT_CONFIRMED") != "true":
        raise PilotSafetyError("BLOCKED_TEST_ACCOUNT_NOT_CONFIRMED")

    base_url = _required_env("HOTELRUNNER_PILOT_BASE_URL").rstrip("/")
    if base_url != _OFFICIAL_PILOT_BASE_URL:
        raise PilotSafetyError("BLOCKED_UNAPPROVED_PROVIDER_HOST")

    approved_head = _required_env("HOTELRUNNER_PILOT_APPROVED_HEAD").lower()
    actual_head = _required_env("GITHUB_SHA").lower()
    if not _SHA_PATTERN.fullmatch(approved_head) or not hmac.compare_digest(approved_head, actual_head):
        raise PilotSafetyError("BLOCKED_EXACT_HEAD_MISMATCH")

    raw_date = _required_env("HOTELRUNNER_PILOT_TEST_DATE")
    try:
        test_date = date.fromisoformat(raw_date)
    except ValueError as exc:
        raise PilotSafetyError("BLOCKED_INVALID_PILOT_TEST_DATE") from exc
    days_ahead = (test_date - datetime.now(UTC).date()).days
    if days_ahead < 30 or days_ahead > 365:
        raise PilotSafetyError("BLOCKED_UNSAFE_PILOT_TEST_DATE")

    hmac_key = _required_env("HOTELRUNNER_PILOT_HMAC_KEY")
    if len(hmac_key) < 32:
        raise PilotSafetyError("BLOCKED_WEAK_PILOT_HMAC_KEY")
    run_id = _required_env("HOTELRUNNER_PILOT_RUN_ID")
    correlation_label = hmac.new(
        hmac_key.encode(),
        f"{run_id}:{approved_head}:{operation}".encode(),
        hashlib.sha256,
    ).hexdigest()[:12]

    availability = None
    rate = None
    stop_sell = None
    min_stay = None
    if operation == "availability":
        availability = _parse_int("HOTELRUNNER_PILOT_AVAILABILITY", minimum=0, maximum=20)
    elif operation == "rate":
        try:
            rate = Decimal(_required_env("HOTELRUNNER_PILOT_RATE"))
        except InvalidOperation as exc:
            raise PilotSafetyError("BLOCKED_INVALID_CONFIGURATION:HOTELRUNNER_PILOT_RATE") from exc
        if not rate.is_finite() or rate < Decimal("1") or rate > Decimal("100000"):
            raise PilotSafetyError("BLOCKED_INVALID_CONFIGURATION:HOTELRUNNER_PILOT_RATE")
    elif operation == "stop_sell":
        stop_sell = _parse_int("HOTELRUNNER_PILOT_STOP_SELL", minimum=0, maximum=1)
    elif operation == "restriction":
        min_stay = _parse_int("HOTELRUNNER_PILOT_MIN_STAY", minimum=1, maximum=30)

    return PilotSettings(
        operation=operation,
        base_url=base_url,
        test_date=test_date,
        approved_head=approved_head,
        run_id=run_id,
        correlation_label=correlation_label,
        token=_required_env("HOTELRUNNER_PILOT_TOKEN"),
        hr_id=_required_env("HOTELRUNNER_PILOT_HR_ID"),
        inv_code=_required_env("HOTELRUNNER_PILOT_INV_CODE"),
        channel_code=_required_env("HOTELRUNNER_PILOT_CHANNEL_CODE"),
        hmac_key=hmac_key,
        availability=availability,
        rate=rate,
        stop_sell=stop_sell,
        min_stay=min_stay,
    )


def _build_provider(settings: PilotSettings) -> HotelRunnerProvider:
    return HotelRunnerProvider(
        token=settings.token,
        hr_id=settings.hr_id,
        connection_id=f"pilot:{settings.correlation_label}",
        base_url=settings.base_url,
        max_retries=0,
    )


def _record_safe_metadata(record_property, metadata: dict[str, Any]) -> None:
    allowed = {
        "capability_match",
        "correlation_label",
        "credential_read_ok",
        "delivery_state",
        "exact_head_match",
        "get_count",
        "match_count_class",
        "operation",
        "pilot_account_attested",
        "provider_status_class",
        "provider_write_count",
        "read_http_status",
        "reservation_correlation_label",
        "reservation_identity_valid",
        "reservation_payload_shape_valid",
        "result",
        "room_match",
        "write_http_status",
    }
    safe = {key: value for key, value in metadata.items() if key in allowed}
    for key, value in sorted(safe.items()):
        record_property(key, value)
    logger.info("HOTELRUNNER_PILOT_SAFE_METADATA %s", json.dumps(safe, sort_keys=True))


def _fail_safe(record_property, code: str, metadata: dict[str, Any]) -> None:
    _record_safe_metadata(record_property, {**metadata, "result": code})
    pytest.fail(code, pytrace=False)


async def _read_only_preflight(
    provider: HotelRunnerProvider,
    settings: PilotSettings,
    record_property,
) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata: dict[str, Any] = {
        "correlation_label": settings.correlation_label,
        "operation": settings.operation,
        "exact_head_match": True,
        "pilot_account_attested": True,
        "credential_read_ok": False,
        "room_match": False,
        "capability_match": False,
        "match_count_class": "ZERO",
        "provider_write_count": 0,
    }

    connection = await provider.test_connection()
    if not connection.success:
        _fail_safe(record_property, "BLOCKED_READONLY_CREDENTIAL_CHECK_FAILED", metadata)
    metadata["credential_read_ok"] = True

    room_result = await provider.fetch_rooms()
    if not room_result.success or not isinstance(room_result.data, dict):
        _fail_safe(record_property, "BLOCKED_READONLY_ROOM_DISCOVERY_FAILED", metadata)
    rooms = room_result.data.get("rooms")
    if not isinstance(rooms, list):
        _fail_safe(record_property, "BLOCKED_READONLY_ROOM_RESPONSE_INVALID", metadata)

    matches = [room for room in rooms if isinstance(room, dict) and hmac.compare_digest(str(room.get("inv_code") or ""), settings.inv_code)]
    metadata["match_count_class"] = "ZERO" if not matches else "ONE" if len(matches) == 1 else "MULTIPLE"
    if len(matches) != 1:
        code = "BLOCKED_PILOT_ROOM_NOT_FOUND" if not matches else "CONFLICT_MULTIPLE_PILOT_ROOMS"
        _fail_safe(record_property, code, metadata)

    room = matches[0]
    metadata["room_match"] = True
    raw = room.get("raw")
    if not isinstance(raw, dict):
        _fail_safe(record_property, "BLOCKED_PILOT_ROOM_CAPABILITIES_MISSING", metadata)

    channel_codes = room.get("channel_codes")
    channel_match = isinstance(channel_codes, list) and any(isinstance(code, str) and hmac.compare_digest(code, settings.channel_code) for code in channel_codes)
    capability_key = {
        "availability": "availability_update",
        "rate": "price_update",
        "stop_sell": "restrictions_update",
        "restriction": "restrictions_update",
    }.get(settings.operation)
    if settings.operation == "discovery":
        capability_match = all(raw.get(key) is True for key in ("availability_update", "price_update", "restrictions_update"))
    else:
        capability_match = raw.get(capability_key) is True
    metadata["capability_match"] = bool(channel_match and capability_match)
    if not metadata["capability_match"]:
        _fail_safe(record_property, "BLOCKED_PILOT_CAPABILITY_MISMATCH", metadata)
    return room, metadata


def _build_single_mutation(settings: PilotSettings) -> dict[str, Any]:
    mutation: dict[str, Any] = {
        "inv_code": settings.inv_code,
        "start_date": settings.test_date.isoformat(),
        "end_date": settings.test_date.isoformat(),
        "channel_codes": [settings.channel_code],
    }
    if settings.operation == "availability":
        mutation["availability"] = settings.availability
    elif settings.operation == "rate":
        mutation["price"] = str(settings.rate)
    elif settings.operation == "stop_sell":
        mutation["stop_sale"] = settings.stop_sell
    elif settings.operation == "restriction":
        mutation["min_stay"] = settings.min_stay
    else:
        raise PilotSafetyError("BLOCKED_UNSUPPORTED_PILOT_WRITE_OPERATION")
    return mutation


async def _latest_delivery_record(tenant_id: str) -> dict[str, Any] | None:
    records = await db[COLL_ARI_DELIVERIES].find({"tenant_id": tenant_id}, {"_id": 0}).sort("created_at", -1).limit(1).to_list(1)
    return records[0] if records else None


async def test_hotelrunner_pilot_readonly_discovery(record_property):
    """Verify test credentials, one room, one channel and all ARI capabilities."""
    try:
        settings = _load_settings()
    except PilotSafetyError as exc:
        pytest.fail(str(exc), pytrace=False)
    if settings.operation != "discovery":
        pytest.fail("BLOCKED_DISCOVERY_TARGET_OPERATION_MISMATCH", pytrace=False)

    provider = _build_provider(settings)
    guard = PilotHttpGuard(provider, allow_write=False)
    try:
        _, metadata = await _read_only_preflight(provider, settings, record_property)
        metadata.update(
            {
                "get_count": guard.get_count,
                "provider_write_count": guard.write_count,
                "read_http_status": guard.read_http_status or "NOT_RECORDED",
                "result": "PASS",
            }
        )
        if guard.write_count != 0:
            _fail_safe(record_property, "FAIL_READONLY_PROVIDER_WRITE_DETECTED", metadata)
        _record_safe_metadata(record_property, metadata)
    finally:
        guard.restore()
        await provider._client.close()


async def test_hotelrunner_pilot_readonly_reservation(record_property):
    """Read exactly one undelivered test reservation without delivery ACK."""
    try:
        settings = _load_settings()
    except PilotSafetyError as exc:
        pytest.fail(str(exc), pytrace=False)
    if settings.operation != "reservation_read":
        pytest.fail("BLOCKED_RESERVATION_READ_TARGET_OPERATION_MISMATCH", pytrace=False)

    provider = _build_provider(settings)
    guard = PilotHttpGuard(provider, allow_write=False)
    metadata: dict[str, Any] = {
        "correlation_label": settings.correlation_label,
        "operation": settings.operation,
        "exact_head_match": True,
        "pilot_account_attested": True,
        "credential_read_ok": False,
        "match_count_class": "ZERO",
        "reservation_identity_valid": False,
        "reservation_payload_shape_valid": False,
        "provider_write_count": 0,
    }
    try:
        connection = await provider.test_connection()
        if not connection.success:
            _fail_safe(
                record_property,
                "BLOCKED_READONLY_CREDENTIAL_CHECK_FAILED",
                metadata,
            )
        metadata["credential_read_ok"] = True

        result = await provider.fetch_reservations(
            undelivered=True,
            per_page=2,
            page=1,
        )
        if not result.success or not isinstance(result.data, dict):
            _fail_safe(
                record_property,
                "BLOCKED_RESERVATION_READ_FAILED",
                metadata,
            )

        reservations = result.data.get("raw_reservations")
        if not isinstance(reservations, list):
            _fail_safe(
                record_property,
                "BLOCKED_RESERVATION_RESPONSE_INVALID",
                metadata,
            )
        metadata["reservation_payload_shape_valid"] = True
        metadata["match_count_class"] = "ZERO" if not reservations else "ONE" if len(reservations) == 1 else "MULTIPLE"
        if len(reservations) != 1:
            code = "BLOCKED_NO_UNDELIVERED_RESERVATION" if not reservations else "BLOCKED_MULTIPLE_UNDELIVERED_RESERVATIONS"
            _fail_safe(record_property, code, metadata)

        reservation = reservations[0]
        identity_fields = ("hr_number", "message_uid", "rooms")
        identity_valid = isinstance(reservation, dict) and all(reservation.get(field) for field in identity_fields)
        metadata["reservation_identity_valid"] = bool(identity_valid)
        if not identity_valid:
            _fail_safe(
                record_property,
                "BLOCKED_RESERVATION_IDENTITY_INVALID",
                metadata,
            )

        reservation_correlation_label = hmac.new(
            settings.hmac_key.encode(),
            str(reservation["message_uid"]).strip().encode(),
            hashlib.sha256,
        ).hexdigest()[:12]

        metadata.update(
            {
                "get_count": guard.get_count,
                "provider_write_count": guard.write_count,
                "read_http_status": guard.read_http_status or "NOT_RECORDED",
                "provider_status_class": "SUCCESS",
                "reservation_correlation_label": reservation_correlation_label,
                "result": "PASS",
            }
        )
        if guard.write_count != 0:
            _fail_safe(
                record_property,
                "FAIL_READONLY_PROVIDER_WRITE_DETECTED",
                metadata,
            )
        _record_safe_metadata(record_property, metadata)
    finally:
        guard.restore()
        await provider._client.close()


@pytest.mark.side_effect
async def test_hotelrunner_pilot_single_ari_write(record_property):
    """Send one approved ARI mutation and verify its transaction using GET only."""
    try:
        settings = _load_settings()
    except PilotSafetyError as exc:
        pytest.fail(str(exc), pytrace=False)
    if settings.operation not in _WRITE_OPERATIONS:
        pytest.fail("BLOCKED_WRITE_TARGET_OPERATION_MISMATCH", pytrace=False)

    provider = _build_provider(settings)
    guard = PilotHttpGuard(provider, allow_write=True)
    tenant_id = f"hotelrunner-pilot-{settings.correlation_label}"
    metadata: dict[str, Any] = {
        "correlation_label": settings.correlation_label,
        "operation": settings.operation,
        "provider_write_count": 0,
        "exact_head_match": True,
        "pilot_account_attested": True,
    }
    try:
        _, preflight_metadata = await _read_only_preflight(
            provider,
            settings,
            record_property,
        )
        metadata.update(preflight_metadata)

        await db[COLL_FEATURE_FLAGS].delete_many({"tenant_id": tenant_id, "provider": "hotelrunner_v2"})
        await db[COLL_ARI_DELIVERIES].delete_many({"tenant_id": tenant_id})
        await set_flags(
            tenant_id,
            {
                "connector_enabled": True,
                "write_enabled": True,
                "shadow_mode": False,
                "dry_run_mode": False,
            },
        )

        mutation = _build_single_mutation(settings)
        result = await deliver_hotelrunner_ari(tenant_id, mutation, provider=provider)

        if result.transaction_id and result.state in {
            STATE_RECONCILIATION_PENDING,
            STATE_AMBIGUOUS,
        }:
            for _ in range(6):
                await asyncio.sleep(5)
                await reconcile_pending_hotelrunner_ari(
                    tenant_id,
                    provider=provider,
                    limit=1,
                )
                record = await _latest_delivery_record(tenant_id)
                if record and record.get("state") in _TERMINAL_STATES:
                    break

        record = await _latest_delivery_record(tenant_id)
        final_state = str((record or {}).get("state") or result.state)
        provider_status_class = str((record or {}).get("provider_status_class") or result.provider_status_class or "NOT_RECORDED")
        metadata.update(
            {
                "delivery_state": final_state,
                "provider_status_class": provider_status_class,
                "provider_write_count": guard.write_count,
                "get_count": guard.get_count,
                "write_http_status": guard.write_http_status or "NOT_RECORDED",
                "read_http_status": guard.read_http_status or "NOT_RECORDED",
            }
        )

        if guard.write_count != 1:
            _fail_safe(record_property, "FAIL_PROVIDER_WRITE_COUNT_INVALID", metadata)
        if final_state != STATE_CONFIRMED:
            _fail_safe(record_property, f"BLOCKED_ARI_{final_state.upper()}", metadata)
        metadata["result"] = "PASS"
        _record_safe_metadata(record_property, metadata)
    except PilotSafetyError as exc:
        metadata.update(
            {
                "provider_write_count": guard.write_count,
                "get_count": guard.get_count,
                "write_http_status": guard.write_http_status or "NOT_RECORDED",
                "read_http_status": guard.read_http_status or "NOT_RECORDED",
            }
        )
        _fail_safe(record_property, str(exc), metadata)
    finally:
        guard.restore()
        await provider._client.close()
