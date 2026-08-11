"""Controlled single-write HotelRunner reservation ACK pilot.

The pilot requires exactly one undelivered reservation, creates and verifies a durable
local PMS booking first, then performs exactly one HotelRunner ACK mutation. Any
ambiguous/failing ACK is never retried automatically.
"""

from __future__ import annotations

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
        f"{run_id}:{approved_head}:reservation_ack".encode(),
        hashlib.sha256,
    ).hexdigest()[:12]

    return ReservationPilotSettings(
        operation="reservation_ack",
        base_url=base_url,
        approved_head=approved_head,
        correlation_label=correlation_label,
        tenant_id=f"hotelrunner-ack-pilot-{correlation_label}",
        token=_required("HOTELRUNNER_PILOT_TOKEN"),
        hr_id=_required("HOTELRUNNER_PILOT_HR_ID"),
    )


def _record(record_property, **values: Any) -> None:
    for key, value in sorted(values.items()):
        record_property(key, value)


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

            fetched = await provider.fetch_reservations(undelivered=True, per_page=2, page=1)
            if not fetched.success or not isinstance(fetched.data, dict):
                raise ReservationPilotError("BLOCKED_RESERVATION_READ_FAILED")
            reservations = fetched.data.get("raw_reservations")
            if not isinstance(reservations, list):
                raise ReservationPilotError("BLOCKED_RESERVATION_RESPONSE_INVALID")
            if len(reservations) != 1:
                if not reservations:
                    raise ReservationPilotError("BLOCKED_NO_UNDELIVERED_RESERVATION")
                raise ReservationPilotError("BLOCKED_MULTIPLE_UNDELIVERED_RESERVATIONS")

            raw = reservations[0]
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

            # GET-only readback. Never retry the ACK mutation.
            post = await provider.fetch_reservations(undelivered=True, per_page=2, page=1)
            if not post.success or not isinstance(post.data, dict):
                raise ReservationPilotError("BLOCKED_POST_ACK_READBACK_FAILED")
            post_reservations = post.data.get("raw_reservations")
            if not isinstance(post_reservations, list):
                raise ReservationPilotError("BLOCKED_POST_ACK_RESPONSE_INVALID")
            if any(str(item.get("message_uid") or "") == message_uid for item in post_reservations if isinstance(item, dict)):
                raise ReservationPilotError("BLOCKED_ACK_NOT_DURABLE_ON_PROVIDER_READBACK")

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
