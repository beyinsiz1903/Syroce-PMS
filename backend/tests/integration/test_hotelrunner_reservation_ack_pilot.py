"""Controlled single-write HotelRunner reservation ACK pilot.

The pilot selects exactly one approved undelivered reservation, creates and verifies
a durable local PMS booking first, then performs exactly one HotelRunner ACK mutation.
Any ambiguous/failing ACK is never retried automatically.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import re
from typing import Any

import pytest

from domains.channel_manager.providers.hotelrunner import endpoints as ep
from domains.channel_manager.providers.hotelrunner.provider import HotelRunnerProvider
from tests.integration.test_hotelrunner_reservation_import_pilot import (
    ReservationPilotError,
    ReservationPilotSettings,
    _import_durably,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.external,
    pytest.mark.hotelrunner_pilot,
]

_OFFICIAL_BASE_URL = "https://app.hotelrunner.com"
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_TARGET_POLL_INTERVAL_SECONDS = 10
_sleep = asyncio.sleep


class AckPilotHttpGuard:
    """Allow expected GETs plus exactly one reservation ACK PUT."""

    def __init__(self, provider: HotelRunnerProvider):
        self._client = provider._client
        self._original_request = self._client._request
        self.get_count = 0
        self.write_count = 0
        self.write_http_status: int | None = None
        self.read_http_status: int | None = None
        self._client._request = self._guarded_request

    async def _guarded_request(self, method: str, path: str, **kwargs):
        normalized_method = str(method).upper()
        if normalized_method == "GET":
            if path not in {ep.CHANNELS, ep.RESERVATIONS}:
                raise ReservationPilotError("BLOCKED_UNEXPECTED_PROVIDER_GET")
            self.get_count += 1
        elif normalized_method == "PUT":
            if path != ep.RESERVATIONS_ACK:
                raise ReservationPilotError("BLOCKED_UNEXPECTED_PROVIDER_WRITE_PATH")
            if self.write_count >= 1:
                raise ReservationPilotError("BLOCKED_SECOND_PROVIDER_WRITE_ATTEMPT")
            self.write_count += 1
        else:
            raise ReservationPilotError("BLOCKED_UNEXPECTED_PROVIDER_HTTP_METHOD")

        result = await self._original_request(normalized_method, path, **kwargs)
        status_code = getattr(result, "status_code", None)
        if isinstance(status_code, int):
            if normalized_method == "PUT":
                self.write_http_status = status_code
            else:
                self.read_http_status = status_code
        return result

    def restore(self) -> None:
        self._client._request = self._original_request


def _required(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise ReservationPilotError(f"BLOCKED_MISSING_CONFIGURATION:{name}")
    return value


def _load_ack_settings() -> ReservationPilotSettings:
    mongo_url = str(os.environ.get("MONGO_URL") or "")
    if not mongo_url.startswith(("mongodb://localhost:", "mongodb://127.0.0.1:")):
        raise ReservationPilotError("BLOCKED_NON_LOCAL_TEST_DATABASE")
    if str(os.environ.get("DB_NAME") or "") != "hotel_pms_test":
        raise ReservationPilotError("BLOCKED_NON_TEST_DATABASE_NAME")
    if os.environ.get("APP_ENV") != "test" or os.environ.get("TESTING") != "1":
        raise ReservationPilotError("BLOCKED_NON_TEST_APPLICATION_ENVIRONMENT")
    if _required("HOTELRUNNER_PILOT_OPERATION") != "reservation_ack":
        raise ReservationPilotError("BLOCKED_RESERVATION_ACK_OPERATION_MISMATCH")
    if os.environ.get("HOTELRUNNER_PILOT_WRITE_APPROVED") != "true":
        raise ReservationPilotError("BLOCKED_PROVIDER_WRITE_NOT_APPROVED")
    if os.environ.get("HOTELRUNNER_PILOT_ACCOUNT_CONFIRMED") != "true":
        raise ReservationPilotError("BLOCKED_TEST_ACCOUNT_NOT_CONFIRMED")
    if _required("HOTELRUNNER_PILOT_RUN_ATTEMPT") != "1":
        raise ReservationPilotError("BLOCKED_MUTATION_RERUN")

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
    source_run_id = _required("HOTELRUNNER_PILOT_SOURCE_RUN_ID")
    if not source_run_id.isdecimal():
        raise ReservationPilotError("BLOCKED_INVALID_SOURCE_RUN_ID")
    correlation_label = hmac.new(
        hmac_key.encode(),
        f"{run_id}:{source_run_id}:{approved_head}:reservation_ack".encode(),
        hashlib.sha256,
    ).hexdigest()[:12]

    return ReservationPilotSettings(
        operation="reservation_ack",
        base_url=base_url,
        approved_head=approved_head,
        correlation_label=correlation_label,
        tenant_id=f"hotelrunner-ack-pilot-{correlation_label}",
        source_timestamp=None,
        token=_required("HOTELRUNNER_PILOT_TOKEN"),
        hr_id=_required("HOTELRUNNER_PILOT_HR_ID"),
        hmac_key=hmac_key,
        target_guest_name=_required("HOTELRUNNER_PILOT_TARGET_GUEST_NAME"),
    )


def _record(record_property, **values: Any) -> None:
    for key, value in sorted(values.items()):
        record_property(key, value)


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


def _select_target_reservation(
    settings: ReservationPilotSettings,
    reservations: list[Any],
) -> dict[str, Any]:
    target_digest = _guest_identity_digest(settings, settings.target_guest_name)
    if target_digest is None:
        raise ReservationPilotError("BLOCKED_INVALID_ACK_TARGET")
    matches = []
    for reservation in reservations:
        if not isinstance(reservation, dict):
            raise ReservationPilotError("BLOCKED_RESERVATION_RESPONSE_INVALID")
        candidate_digest = _guest_identity_digest(settings, reservation.get("guest"))
        if candidate_digest is not None and hmac.compare_digest(candidate_digest, target_digest):
            matches.append(reservation)
    if not matches:
        raise ReservationPilotError("BLOCKED_TARGET_UNDELIVERED_RESERVATION_NOT_FOUND")
    if len(matches) > 1:
        raise ReservationPilotError("CONFLICT_MULTIPLE_TARGET_UNDELIVERED_RESERVATIONS")
    return matches[0]


async def _wait_for_target_reservation(
    provider: HotelRunnerProvider,
    settings: ReservationPilotSettings,
    *,
    wait_seconds: int,
) -> dict[str, Any]:
    if not 1 <= wait_seconds <= 180:
        raise ReservationPilotError("BLOCKED_INVALID_TARGET_WAIT_SECONDS")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_seconds
    while True:
        fetched = await provider.fetch_reservations(undelivered=True, per_page=100, page=1)
        if not fetched.success or not isinstance(fetched.data, dict):
            raise ReservationPilotError("BLOCKED_RESERVATION_READ_FAILED")
        reservations = fetched.data.get("raw_reservations")
        if not isinstance(reservations, list):
            raise ReservationPilotError("BLOCKED_RESERVATION_RESPONSE_INVALID")
        try:
            return _select_target_reservation(settings, reservations)
        except ReservationPilotError as exc:
            if str(exc) != "BLOCKED_TARGET_UNDELIVERED_RESERVATION_NOT_FOUND":
                raise

        remaining = deadline - loop.time()
        if remaining <= 0:
            raise ReservationPilotError("BLOCKED_TARGET_UNDELIVERED_RESERVATION_NOT_FOUND")
        await _sleep(min(_TARGET_POLL_INTERVAL_SECONDS, remaining))


def _verify_history_pms_number(
    reservations: list[Any],
    message_uid: str,
    pms_number: str,
) -> None:
    matches = [item for item in reservations if isinstance(item, dict) and isinstance(item.get("message_uid"), str) and hmac.compare_digest(item["message_uid"], message_uid)]
    if len(matches) != 1:
        raise ReservationPilotError("BLOCKED_POST_ACK_HISTORY_MATCH_INVALID")
    provider_pms_number = str(matches[0].get("pms_number") or "").strip()
    if not provider_pms_number or not hmac.compare_digest(provider_pms_number, pms_number):
        raise ReservationPilotError("BLOCKED_POST_ACK_PMS_NUMBER_MISMATCH")


async def test_hotelrunner_single_reservation_ack(record_property):
    """Durable PMS import first, then exactly one provider ACK and GET-only readback."""
    try:
        settings = _load_ack_settings()
        provider = HotelRunnerProvider(
            token=settings.token,
            hr_id=settings.hr_id,
            connection_id=f"pilot:{settings.correlation_label}",
            base_url=settings.base_url,
            max_retries=0,
        )
        guard = AckPilotHttpGuard(provider)
        try:
            connection = await provider.test_connection()
            if not connection.success:
                raise ReservationPilotError("BLOCKED_READONLY_CREDENTIAL_CHECK_FAILED")

            wait_seconds_raw = _required("HOTELRUNNER_PILOT_TARGET_WAIT_SECONDS")
            if not wait_seconds_raw.isdecimal():
                raise ReservationPilotError("BLOCKED_INVALID_TARGET_WAIT_SECONDS")
            raw = await _wait_for_target_reservation(
                provider,
                settings,
                wait_seconds=int(wait_seconds_raw),
            )
            message_uid = str(raw.get("message_uid") or "").strip()
            if not message_uid:
                raise ReservationPilotError("BLOCKED_RESERVATION_MESSAGE_UID_MISSING")

            _, booking = await _import_durably(settings, raw)
            pms_number = str(booking.get("id") or "").strip()
            if not pms_number:
                raise ReservationPilotError("BLOCKED_DURABLE_PMS_READBACK_FAILED")
            if guard.write_count != 0:
                raise ReservationPilotError("FAIL_PROVIDER_WRITE_BEFORE_DURABLE_PMS")

            ack = await provider.confirm_delivery(message_uid=message_uid, pms_number=pms_number)
            if guard.write_count != 1:
                raise ReservationPilotError("BLOCKED_ACK_WRITE_COUNT_MISMATCH")
            if not ack.success:
                raise ReservationPilotError("BLOCKED_RESERVATION_ACK_FAILED_OR_AMBIGUOUS")
            if ack.metadata.get("provider_status_class") != "SUCCESS":
                raise ReservationPilotError("BLOCKED_RESERVATION_ACK_STATUS_INVALID")
            if ack.metadata.get("retry_count") != 0:
                raise ReservationPilotError("BLOCKED_RESERVATION_ACK_RETRY_DETECTED")

            # GET-only readback. Never retry the ACK mutation.
            post = await provider.fetch_reservations(undelivered=True, per_page=100, page=1)
            if not post.success or not isinstance(post.data, dict):
                raise ReservationPilotError("BLOCKED_POST_ACK_READBACK_FAILED")
            post_reservations = post.data.get("raw_reservations")
            if not isinstance(post_reservations, list):
                raise ReservationPilotError("BLOCKED_POST_ACK_RESPONSE_INVALID")
            if any(str(item.get("message_uid") or "") == message_uid for item in post_reservations if isinstance(item, dict)):
                raise ReservationPilotError("BLOCKED_ACK_NOT_DURABLE_ON_PROVIDER_READBACK")

            history = await provider.fetch_reservations(
                undelivered=False,
                per_page=100,
                page=None,
            )
            if not history.success or not isinstance(history.data, dict):
                raise ReservationPilotError("BLOCKED_POST_ACK_HISTORY_READ_FAILED")
            history_reservations = history.data.get("reservations")
            if not isinstance(history_reservations, list):
                raise ReservationPilotError("BLOCKED_POST_ACK_HISTORY_RESPONSE_INVALID")
            _verify_history_pms_number(history_reservations, message_uid, pms_number)

            _record(
                record_property,
                ack_durable=True,
                durable_pms_booking=True,
                exact_head_match=True,
                get_count=guard.get_count,
                match_count_class="ONE",
                operation="reservation_ack",
                pms_booking_count=1,
                post_ack_target_absent=True,
                provider_pms_number_match=True,
                provider_status_class="SUCCESS",
                retry_count=0,
                provider_write_count=guard.write_count,
                result="PASS",
                write_http_status=guard.write_http_status or "NOT_RECORDED",
            )
            assert guard.write_count == 1
        finally:
            guard.restore()
            await provider._client.close()
    except ReservationPilotError as exc:
        pytest.fail(str(exc), pytrace=False)
