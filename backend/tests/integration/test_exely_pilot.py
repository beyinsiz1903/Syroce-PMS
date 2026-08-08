"""Gated Exely test-account pilot selected only by the manual workflow."""

from __future__ import annotations

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

from core.database import db
from domains.channel_manager.providers.exely.ari_delivery import (
    COLL_EXELY_ARI_DELIVERIES,
    STATE_CONFIRMED,
    STATE_WARNING_SUCCESS,
    deliver_exely_ari,
    reconcile_pending_exely_ari,
)
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.security import (
    EXELY_TEST_ENDPOINT_URL,
    validate_exely_endpoint,
)
from domains.channel_manager.providers.exely.soap_builder import get_soap_action_uri

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.external,
    pytest.mark.exely_pilot,
]

logger = logging.getLogger("exely.pilot")

_READ_OPERATIONS = frozenset({"discovery", "reservation_read"})
_ARI_OPERATIONS = frozenset({"availability", "rate", "stop_sell", "min_los", "min_los_arrival"})
_WRITE_OPERATIONS = frozenset({*_ARI_OPERATIONS, "reservation_ack"})
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


class PilotSafetyError(RuntimeError):
    """Payload-free pilot guard failure."""


@dataclass(frozen=True)
class PilotSettings:
    operation: str
    endpoint_url: str
    approved_head: str
    run_id: str
    correlation_label: str
    test_date: date | None = None
    availability: int | None = None
    rate: Decimal | None = None
    currency: str = "USD"
    stop_sell: bool | None = None
    min_los: int | None = None
    min_los_arrival: int | None = None
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    hotel_code: str = field(default="", repr=False)
    room_type_code: str = field(default="", repr=False)
    rate_plan_code: str = field(default="", repr=False)
    hmac_key: str = field(default="", repr=False)
    ack_reservation_id: str = field(default="", repr=False)
    ack_confirmation_id: str = field(default="", repr=False)
    ack_create_datetime: str = field(default="", repr=False)
    ack_last_modify_datetime: str = field(default="", repr=False)


class PilotTransportGuard:
    """Allow expected SOAP reads and at most one selected mutation."""

    def __init__(self, provider: ExelyProvider, settings: PilotSettings):
        self._transport = provider._transport
        self._original_send = self._transport.send_soap
        self._write_approved = settings.operation in _WRITE_OPERATIONS
        self._allowed_read_action = get_soap_action_uri("OTA_ReadRQ" if settings.operation in {"reservation_read", "reservation_ack"} else "OTA_HotelAvailRQ")
        self._allowed_write_action = self._write_action(settings.operation)
        self.read_count = 0
        self.write_count = 0
        self.last_exception_class = ""
        self._transport.send_soap = self._guarded_send

    @staticmethod
    def _write_action(operation: str) -> str | None:
        if operation == "rate":
            return get_soap_action_uri("OTA_HotelRateAmountNotifRQ")
        if operation in _ARI_OPERATIONS:
            return get_soap_action_uri("OTA_HotelAvailNotifRQ")
        if operation == "reservation_ack":
            return get_soap_action_uri("OTA_NotifReportRQ")
        return None

    async def _guarded_send(
        self,
        xml_body: str,
        soap_action: str = "",
        *,
        correlation_id: str = "",
    ) -> bytes:
        if soap_action == self._allowed_read_action:
            self.read_count += 1
        elif soap_action == self._allowed_write_action:
            if not self._write_approved:
                raise PilotSafetyError("BLOCKED_PROVIDER_WRITE_IN_READONLY_MODE")
            if self.write_count >= 1:
                raise PilotSafetyError("BLOCKED_SECOND_PROVIDER_WRITE_ATTEMPT")
            self.write_count += 1
        else:
            raise PilotSafetyError("BLOCKED_UNEXPECTED_SOAP_ACTION")

        try:
            return await self._original_send(
                xml_body,
                soap_action,
                correlation_id=correlation_id,
            )
        except Exception as exc:
            self.last_exception_class = type(exc).__name__
            raise

    def restore(self) -> None:
        self._transport.send_soap = self._original_send


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


def _parse_bool(name: str) -> bool:
    raw = _required_env(name).lower()
    if raw not in {"true", "false"}:
        raise PilotSafetyError(f"BLOCKED_INVALID_CONFIGURATION:{name}")
    return raw == "true"


def _load_settings() -> PilotSettings:
    _require_local_test_database()
    operation = _required_env("EXELY_PILOT_OPERATION")
    if operation not in {*_READ_OPERATIONS, *_WRITE_OPERATIONS}:
        raise PilotSafetyError("BLOCKED_UNSUPPORTED_PILOT_OPERATION")

    write_approved = os.environ.get("EXELY_PILOT_WRITE_APPROVED") == "true"
    if operation in _READ_OPERATIONS and write_approved:
        raise PilotSafetyError("BLOCKED_READONLY_WRITE_CONFLICT")
    if operation in _WRITE_OPERATIONS and not write_approved:
        raise PilotSafetyError("BLOCKED_PROVIDER_WRITE_NOT_APPROVED")
    if os.environ.get("EXELY_PILOT_ACCOUNT_CONFIRMED") != "true":
        raise PilotSafetyError("BLOCKED_TEST_ACCOUNT_NOT_CONFIRMED")
    if os.environ.get("EXELY_PILOT_CREDENTIAL_SCOPE") != "test":
        raise PilotSafetyError("BLOCKED_NON_TEST_CREDENTIAL_SCOPE")

    endpoint_url = _required_env("EXELY_PILOT_ENDPOINT_URL").rstrip("/")
    if endpoint_url != EXELY_TEST_ENDPOINT_URL or validate_exely_endpoint(endpoint_url) != endpoint_url:
        raise PilotSafetyError("BLOCKED_UNAPPROVED_PROVIDER_HOST")

    approved_head = _required_env("EXELY_PILOT_APPROVED_HEAD").lower()
    actual_head = _required_env("GITHUB_SHA").lower()
    if not _SHA_PATTERN.fullmatch(approved_head) or not hmac.compare_digest(approved_head, actual_head):
        raise PilotSafetyError("BLOCKED_EXACT_HEAD_MISMATCH")

    hmac_key = _required_env("EXELY_PILOT_HMAC_KEY")
    if len(hmac_key) < 32:
        raise PilotSafetyError("BLOCKED_WEAK_PILOT_HMAC_KEY")
    run_id = _required_env("EXELY_PILOT_RUN_ID")
    correlation_label = hmac.new(
        hmac_key.encode(),
        f"{run_id}:{approved_head}:{operation}".encode(),
        hashlib.sha256,
    ).hexdigest()[:12]

    values: dict[str, Any] = {}
    if operation in _ARI_OPERATIONS:
        raw_date = _required_env("EXELY_PILOT_TEST_DATE")
        try:
            test_date = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise PilotSafetyError("BLOCKED_INVALID_PILOT_TEST_DATE") from exc
        days_ahead = (test_date - datetime.now(UTC).date()).days
        if days_ahead < 30 or days_ahead > 365:
            raise PilotSafetyError("BLOCKED_UNSAFE_PILOT_TEST_DATE")
        values["test_date"] = test_date

    if operation == "availability":
        values["availability"] = _parse_int("EXELY_PILOT_AVAILABILITY", minimum=0, maximum=20)
    elif operation == "rate":
        try:
            rate = Decimal(_required_env("EXELY_PILOT_RATE"))
        except InvalidOperation as exc:
            raise PilotSafetyError("BLOCKED_INVALID_CONFIGURATION:EXELY_PILOT_RATE") from exc
        if not rate.is_finite() or rate < Decimal("1") or rate > Decimal("100000"):
            raise PilotSafetyError("BLOCKED_INVALID_CONFIGURATION:EXELY_PILOT_RATE")
        currency = _required_env("EXELY_PILOT_CURRENCY").upper()
        if not _CURRENCY_PATTERN.fullmatch(currency):
            raise PilotSafetyError("BLOCKED_INVALID_CONFIGURATION:EXELY_PILOT_CURRENCY")
        values.update({"rate": rate, "currency": currency})
    elif operation == "stop_sell":
        values["stop_sell"] = _parse_bool("EXELY_PILOT_STOP_SELL")
    elif operation == "min_los":
        values["min_los"] = _parse_int("EXELY_PILOT_MIN_LOS", minimum=1, maximum=30)
    elif operation == "min_los_arrival":
        values["min_los_arrival"] = _parse_int("EXELY_PILOT_MIN_LOS_ARRIVAL", minimum=1, maximum=30)
    elif operation == "reservation_ack":
        if os.environ.get("EXELY_PILOT_ACK_DURABLE_PMS_ATTESTED") != "true":
            raise PilotSafetyError("BLOCKED_DURABLE_PMS_RESULT_NOT_ATTESTED")
        values.update(
            {
                "ack_reservation_id": _required_env("EXELY_PILOT_ACK_RESERVATION_ID"),
                "ack_confirmation_id": _required_env("EXELY_PILOT_ACK_CONFIRMATION_ID"),
                "ack_create_datetime": _required_env("EXELY_PILOT_ACK_CREATE_DATETIME"),
                "ack_last_modify_datetime": _required_env("EXELY_PILOT_ACK_LAST_MODIFY_DATETIME"),
            }
        )

    if operation in _ARI_OPERATIONS:
        room_type_code = _required_env("EXELY_PILOT_ROOM_TYPE_CODE")
        rate_plan_code = _required_env("EXELY_PILOT_RATE_PLAN_CODE")
    elif operation == "discovery":
        room_type_code = os.environ.get("EXELY_PILOT_ROOM_TYPE_CODE", "").strip()
        rate_plan_code = os.environ.get("EXELY_PILOT_RATE_PLAN_CODE", "").strip()
    else:
        room_type_code = ""
        rate_plan_code = ""
    return PilotSettings(
        operation=operation,
        endpoint_url=endpoint_url,
        approved_head=approved_head,
        run_id=run_id,
        correlation_label=correlation_label,
        username=_required_env("EXELY_PILOT_USERNAME"),
        password=_required_env("EXELY_PILOT_PASSWORD"),
        hotel_code=_required_env("EXELY_PILOT_HOTEL_CODE"),
        room_type_code=room_type_code,
        rate_plan_code=rate_plan_code,
        hmac_key=hmac_key,
        **values,
    )


def _build_provider(settings: PilotSettings) -> ExelyProvider:
    tenant_id = f"exely-pilot-{settings.correlation_label}"
    return ExelyProvider(
        username=settings.username,
        password=settings.password,
        hotel_code=settings.hotel_code,
        endpoint_url=settings.endpoint_url,
        tenant_id=tenant_id,
        property_id=settings.hotel_code,
        connection_id=tenant_id,
        max_retries=0,
    )


def _record_safe_metadata(record_property, metadata: dict[str, Any]) -> None:
    allowed = {
        "account_match",
        "capability_match",
        "correlation_label",
        "delivery_state",
        "exact_head_match",
        "exception_class",
        "match_count_class",
        "operation",
        "pilot_account_attested",
        "provider_status_class",
        "provider_write_count",
        "read_count",
        "result",
        "room_match",
        "rate_plan_match",
        "version_match",
    }
    safe = {key: value for key, value in metadata.items() if key in allowed}
    for key, value in sorted(safe.items()):
        record_property(key, value)
    logger.info("EXELY_PILOT_SAFE_METADATA %s", json.dumps(safe, sort_keys=True))


def _fail_safe(record_property, code: str, metadata: dict[str, Any]) -> None:
    _record_safe_metadata(record_property, {**metadata, "result": code})
    pytest.fail(code, pytrace=False)


async def _discover_mapping(
    provider: ExelyProvider,
    settings: PilotSettings,
    record_property,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "correlation_label": settings.correlation_label,
        "operation": settings.operation,
        "exact_head_match": True,
        "pilot_account_attested": True,
        "account_match": False,
        "room_match": False,
        "rate_plan_match": False,
        "capability_match": False,
        "provider_write_count": 0,
    }
    result = await provider.discover_rooms()
    if not result.success or not isinstance(result.data, dict):
        metadata["provider_status_class"] = result.error_type or "MALFORMED"
        _fail_safe(record_property, "BLOCKED_READONLY_DISCOVERY_FAILED", metadata)
    metadata["account_match"] = True

    rooms = result.data.get("room_types")
    rates = result.data.get("rate_plans")
    if not isinstance(rooms, list) or not isinstance(rates, list):
        _fail_safe(record_property, "BLOCKED_READONLY_DISCOVERY_RESPONSE_INVALID", metadata)
    room_candidates = [item for item in rooms if isinstance(item, dict) and item.get("code")]
    rate_candidates = [item for item in rates if isinstance(item, dict) and item.get("code")]
    room_matches = [item for item in room_candidates if hmac.compare_digest(str(item["code"]), settings.room_type_code)] if settings.room_type_code else room_candidates
    rate_matches = [item for item in rate_candidates if hmac.compare_digest(str(item["code"]), settings.rate_plan_code)] if settings.rate_plan_code else rate_candidates
    metadata["room_match"] = len(room_matches) == 1 if settings.room_type_code else bool(room_matches)
    metadata["rate_plan_match"] = len(rate_matches) == 1 if settings.rate_plan_code else bool(rate_matches)
    metadata["capability_match"] = metadata["room_match"] and metadata["rate_plan_match"]
    metadata["match_count_class"] = "ZERO" if not room_matches or not rate_matches else "ONE" if len(room_matches) == 1 and len(rate_matches) == 1 else "MULTIPLE"
    if not metadata["capability_match"]:
        _fail_safe(record_property, "BLOCKED_PILOT_MAPPING_NOT_DISCOVERED", metadata)
    metadata["provider_status_class"] = str(result.metadata.get("provider_status_class") or "SUCCESS")
    return metadata


async def _read_reservations(
    provider: ExelyProvider,
    settings: PilotSettings,
    record_property,
    *,
    require_ack_match: bool,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "correlation_label": settings.correlation_label,
        "operation": settings.operation,
        "exact_head_match": True,
        "pilot_account_attested": True,
        "account_match": False,
        "match_count_class": "NOT_APPLICABLE",
        "version_match": False,
        "provider_write_count": 0,
    }
    result = await provider.pull_reservations()
    if not result.success or not isinstance(result.data, dict):
        metadata["provider_status_class"] = result.error_type or "MALFORMED"
        _fail_safe(record_property, "BLOCKED_RESERVATION_READ_FAILED", metadata)
    metadata["account_match"] = True
    metadata["provider_status_class"] = str(result.metadata.get("provider_status_class") or "SUCCESS")
    reservations = result.data.get("reservations")
    if not isinstance(reservations, list):
        _fail_safe(record_property, "BLOCKED_RESERVATION_READ_RESPONSE_INVALID", metadata)

    if not require_ack_match:
        metadata["match_count_class"] = "ZERO" if not reservations else "ONE" if len(reservations) == 1 else "MULTIPLE"
        metadata["version_match"] = True
        return metadata

    matches = [item for item in reservations if isinstance(item, dict) and hmac.compare_digest(str(item.get("reservation_id") or ""), settings.ack_reservation_id)]
    metadata["match_count_class"] = "ZERO" if not matches else "ONE" if len(matches) == 1 else "MULTIPLE"
    if len(matches) != 1:
        code = "BLOCKED_ACK_RESERVATION_NOT_UNDELIVERED" if not matches else "CONFLICT_MULTIPLE_ACK_RESERVATIONS"
        _fail_safe(record_property, code, metadata)
    metadata["version_match"] = hmac.compare_digest(str(matches[0].get("last_modify") or ""), settings.ack_last_modify_datetime)
    if not metadata["version_match"]:
        _fail_safe(record_property, "BLOCKED_ACK_VERSION_MISMATCH", metadata)
    return metadata


def _ari_value(settings: PilotSettings) -> Any:
    values = {
        "availability": settings.availability,
        "rate": settings.rate,
        "stop_sell": settings.stop_sell,
        "min_los": settings.min_los,
        "min_los_arrival": settings.min_los_arrival,
    }
    return values[settings.operation]


async def test_exely_pilot_readonly(record_property):
    try:
        settings = _load_settings()
    except PilotSafetyError as exc:
        pytest.fail(str(exc), pytrace=False)
    if settings.operation not in _READ_OPERATIONS:
        pytest.fail("BLOCKED_READONLY_TARGET_OPERATION_MISMATCH", pytrace=False)

    provider = _build_provider(settings)
    guard = PilotTransportGuard(provider, settings)
    metadata: dict[str, Any] = {}
    try:
        if settings.operation == "discovery":
            metadata = await _discover_mapping(provider, settings, record_property)
        else:
            metadata = await _read_reservations(provider, settings, record_property, require_ack_match=False)
        metadata.update({"read_count": guard.read_count, "provider_write_count": guard.write_count})
        if guard.write_count != 0:
            _fail_safe(record_property, "FAIL_READONLY_PROVIDER_WRITE_DETECTED", metadata)
        if guard.read_count != 1:
            _fail_safe(record_property, "FAIL_READ_COUNT_INVALID", metadata)
        metadata["result"] = "PASS"
        _record_safe_metadata(record_property, metadata)
    except PilotSafetyError as exc:
        metadata.update(
            {
                "exception_class": type(exc).__name__,
                "read_count": guard.read_count,
                "provider_write_count": guard.write_count,
            }
        )
        _fail_safe(record_property, str(exc), metadata)
    finally:
        guard.restore()


@pytest.mark.side_effect
async def test_exely_pilot_single_write(record_property):
    try:
        settings = _load_settings()
    except PilotSafetyError as exc:
        pytest.fail(str(exc), pytrace=False)
    if settings.operation not in _WRITE_OPERATIONS:
        pytest.fail("BLOCKED_WRITE_TARGET_OPERATION_MISMATCH", pytrace=False)

    provider = _build_provider(settings)
    guard = PilotTransportGuard(provider, settings)
    tenant_id = f"exely-pilot-{settings.correlation_label}"
    metadata: dict[str, Any] = {
        "correlation_label": settings.correlation_label,
        "operation": settings.operation,
        "exact_head_match": True,
        "pilot_account_attested": True,
        "provider_write_count": 0,
    }
    try:
        if settings.operation in _ARI_OPERATIONS:
            metadata.update(await _discover_mapping(provider, settings, record_property))
            await db[COLL_EXELY_ARI_DELIVERIES].delete_many({"tenant_id": tenant_id})
            update = {
                "property_id": settings.hotel_code,
                "room_type_code": settings.room_type_code,
                "rate_plan_code": settings.rate_plan_code,
                "start_date": settings.test_date.isoformat(),
                "end_date": settings.test_date.isoformat(),
                "value": _ari_value(settings),
                "currency": settings.currency,
                "operation_identity": f"pilot:{settings.correlation_label}",
            }
            result = await deliver_exely_ari(
                tenant_id,
                settings.operation,
                update,
                provider=provider,
                write_enabled=True,
            )
            reconciliation = await reconcile_pending_exely_ari(tenant_id, limit=1)
            metadata.update(
                {
                    "delivery_state": result.state,
                    "provider_status_class": result.provider_status_class,
                    "provider_write_count": guard.write_count,
                    "read_count": guard.read_count,
                }
            )
            if guard.write_count != 1 or result.provider_write_count != 1:
                _fail_safe(record_property, "FAIL_PROVIDER_WRITE_COUNT_INVALID", metadata)
            if not result.success or result.state not in {STATE_CONFIRMED, STATE_WARNING_SUCCESS}:
                _fail_safe(record_property, f"BLOCKED_ARI_{result.state.upper()}", metadata)
            if reconciliation.get("pending") != 0 or reconciliation.get("provider_write_count") != 0:
                _fail_safe(record_property, "BLOCKED_ARI_RECONCILIATION_PENDING", metadata)
        else:
            metadata.update(await _read_reservations(provider, settings, record_property, require_ack_match=True))
            result = await provider.confirm_delivery(
                settings.ack_reservation_id,
                settings.ack_confirmation_id,
                create_datetime=settings.ack_create_datetime,
                last_modify_datetime=settings.ack_last_modify_datetime,
            )
            status_class = str(result.metadata.get("provider_status_class") or result.error_type or "MALFORMED")
            metadata.update(
                {
                    "delivery_state": "ACKED" if result.success else "ACK_FAILED",
                    "provider_status_class": status_class,
                    "provider_write_count": guard.write_count,
                    "read_count": guard.read_count,
                }
            )
            if guard.write_count != 1 or result.metadata.get("provider_write_count") != 1:
                _fail_safe(record_property, "FAIL_PROVIDER_WRITE_COUNT_INVALID", metadata)
            if not result.success or status_class not in {"SUCCESS", "WARNING_SUCCESS"}:
                _fail_safe(record_property, "BLOCKED_RESERVATION_ACK_NOT_CONFIRMED", metadata)

        metadata["result"] = "PASS"
        _record_safe_metadata(record_property, metadata)
    except PilotSafetyError as exc:
        metadata.update(
            {
                "exception_class": type(exc).__name__,
                "read_count": guard.read_count,
                "provider_write_count": guard.write_count,
            }
        )
        _fail_safe(record_property, str(exc), metadata)
    except Exception as exc:
        metadata.update(
            {
                "exception_class": type(exc).__name__,
                "read_count": guard.read_count,
                "provider_write_count": guard.write_count,
            }
        )
        _fail_safe(record_property, "BLOCKED_PROVIDER_OPERATION_EXCEPTION", metadata)
    finally:
        guard.restore()
        if settings.operation in _ARI_OPERATIONS:
            await db[COLL_EXELY_ARI_DELIVERIES].delete_many({"tenant_id": tenant_id})
