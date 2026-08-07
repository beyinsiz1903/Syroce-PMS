from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from domains.channel_manager.providers.exely.client import ExelySoapTransport, parse_retry_after
from domains.channel_manager.providers.exely.errors import ExelyRateLimitError, ExelyTemporaryError
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.provider_quota import (
    CHANGES_PER_DAY,
    CHANGES_PER_HOUR,
    CHANGES_PER_SECOND,
    CHANGES_PER_THREE_MINUTES,
    READ_REQUESTS_PER_HOUR,
    TOTAL_REQUESTS_PER_HOUR,
    ExelyProviderQuota,
    QuotaDecision,
)
from domains.channel_manager.providers.exely.response_parser import (
    AUTH_FAILED,
    MALFORMED,
    RATE_LIMITED,
    REJECTED,
    WARNING_SUCCESS,
    parse_ari_update_rs,
    parse_hotel_avail_rs,
    parse_read_rs,
)
from domains.channel_manager.providers.exely.retry import ExelyRetryPolicy


def _soap(body: str) -> bytes:
    return (f'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ota="http://www.opentravel.org/OTA/2003/05"><soap:Body>{body}</soap:Body></soap:Envelope>').encode()


class _FakeRedis:
    def __init__(self, result=None):
        self.result = result or [1, 0, 0]
        self.eval_calls = []
        self.set_calls = []

    async def eval(self, *args):
        self.eval_calls.append(args)
        return self.result

    async def set(self, *args, **kwargs):
        self.set_calls.append((args, kwargs))


class _QuotaGuard:
    def __init__(self, decision=QuotaDecision(True, "QUOTA_RESERVED")):
        self.decision = decision
        self.calls = []
        self.cooldowns = []

    async def reserve(self, *, operation, change_count=0):
        self.calls.append((operation, change_count))
        return self.decision

    async def record_cooldown(self, seconds):
        self.cooldowns.append(seconds)


def _budget_keys(eval_call):
    key_count = int(eval_call[1])
    return eval_call[3 : 2 + key_count]


def test_official_pmsconnect_quota_limits_are_encoded():
    assert TOTAL_REQUESTS_PER_HOUR == 650
    assert READ_REQUESTS_PER_HOUR == 30
    assert CHANGES_PER_SECOND == 1460
    assert CHANGES_PER_THREE_MINUTES == 4380
    assert CHANGES_PER_HOUR == 13140
    assert CHANGES_PER_DAY == 43800


@pytest.mark.asyncio
async def test_reservation_read_and_ari_share_tenant_property_total_budget():
    redis = _FakeRedis()
    quota = ExelyProviderQuota("tenant-a", "property-a", redis_client=redis)

    assert (await quota.reserve(operation="reservation_read")).allowed is True
    assert (await quota.reserve(operation="ari_mutation", change_count=2)).allowed is True

    first_keys = _budget_keys(redis.eval_calls[0])
    second_keys = _budget_keys(redis.eval_calls[1])
    assert first_keys[1] == second_keys[1]
    assert ":total:" in first_keys[1]
    assert first_keys[0] != second_keys[0]
    assert any(":read:" in key for key in first_keys if isinstance(key, str))
    assert any(":changes:" in key for key in second_keys if isinstance(key, str))


@pytest.mark.asyncio
async def test_quota_scope_is_tenant_and_property_specific():
    redis = _FakeRedis()
    first = ExelyProviderQuota("tenant-a", "property-a", redis_client=redis)
    second = ExelyProviderQuota("tenant-b", "property-a", redis_client=redis)
    third = ExelyProviderQuota("tenant-a", "property-b", redis_client=redis)
    await first.reserve(operation="reservation_read")
    await second.reserve(operation="reservation_read")
    await third.reserve(operation="reservation_read")
    first_total_key = _budget_keys(redis.eval_calls[0])[1]
    assert first_total_key != _budget_keys(redis.eval_calls[1])[1]
    assert first_total_key != _budget_keys(redis.eval_calls[2])[1]


@pytest.mark.asyncio
async def test_quota_backend_failure_is_fail_closed(monkeypatch):
    async def unavailable():
        return None

    monkeypatch.setattr(
        "domains.channel_manager.providers.exely.provider_quota._shared_redis_client",
        unavailable,
    )
    decision = await ExelyProviderQuota("tenant-a", "property-a").reserve(operation="reservation_read")
    assert decision == QuotaDecision(False, "QUOTA_BACKEND_UNAVAILABLE")


@pytest.mark.asyncio
async def test_local_quota_denial_blocks_ari_before_provider_write():
    quota = _QuotaGuard(QuotaDecision(False, "PROVIDER_QUOTA_EXCEEDED", 45))
    provider = ExelyProvider(username="u", password="p", hotel_code="H", quota_guard=quota)
    provider._transport.send_soap = AsyncMock()

    result = await provider.push_ari_operation(
        operation="availability",
        room_type_code="R",
        rate_plan_code="P",
        start_date="2026-08-01",
        end_date="2026-08-03",
        value=2,
    )

    assert result.success is False
    assert result.error_type == RATE_LIMITED
    assert result.metadata["provider_write_count"] == 0
    assert quota.calls == [("ari_mutation", 3)]
    provider._transport.send_soap.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_retries_transient_but_mutation_never_retries():
    policy = ExelyRetryPolicy(max_retries=2, base_delay=0, jitter=0)
    read_call = AsyncMock(side_effect=[ExelyTemporaryError(), b"ok"])
    assert await policy.execute_read(read_call) == b"ok"
    assert read_call.await_count == 2

    mutation_call = AsyncMock(side_effect=ExelyTemporaryError())
    with pytest.raises(ExelyTemporaryError):
        await policy.execute_mutation(mutation_call)
    assert mutation_call.await_count == 1


@pytest.mark.asyncio
async def test_local_quota_denial_is_not_retried_even_for_read():
    policy = ExelyRetryPolicy(max_retries=3, base_delay=0, jitter=0)
    call = AsyncMock(side_effect=ExelyRateLimitError(source="local_quota"))
    with pytest.raises(ExelyRateLimitError):
        await policy.execute_read(call)
    assert call.await_count == 1


def test_retry_after_is_bounded_and_malformed_is_fail_safe():
    now = datetime(2026, 8, 7, tzinfo=UTC)
    assert parse_retry_after("17", now=now) == 17
    assert parse_retry_after("not-a-date", now=now) == 60
    assert parse_retry_after("999999", now=now) == 3600
    assert parse_retry_after(format_datetime(now + timedelta(seconds=90)), now=now) == 90


def test_http_429_uses_safe_retry_after_parser():
    response = httpx.Response(429, headers={"Retry-After": "invalid"})
    with pytest.raises(ExelyRateLimitError) as exc_info:
        ExelySoapTransport._raise_for_http_status(response, 1, "safe-correlation")
    assert exc_info.value.retry_after_seconds == 60


@pytest.mark.parametrize("code", ["-100", "-101", "-102", "-103", "-104", "-105"])
def test_official_provider_limit_codes_are_rate_limited(code):
    result = parse_ari_update_rs(_soap(f'<ota:OTA_HotelAvailNotifRS><ota:Errors><ota:Error Code="{code}"/></ota:Errors></ota:OTA_HotelAvailNotifRS>'))
    assert result["success"] is False
    assert result["result_class"] == RATE_LIMITED
    assert result["provider_codes"] == [code]
    assert result["retry_after_seconds"] >= 1


def test_provider_auth_code_is_typed_without_description():
    result = parse_read_rs(_soap('<ota:OTA_ResRetrieveRS><ota:Errors><ota:Error Code="175">sensitive text</ota:Error></ota:Errors></ota:OTA_ResRetrieveRS>'))
    assert result["success"] is False
    assert result["result_class"] == AUTH_FAILED
    assert result["provider_codes"] == ["175"]
    assert "sensitive text" not in str(result)


def test_explicit_success_and_warning_are_typed():
    result = parse_hotel_avail_rs(
        _soap('<ota:OTA_HotelAvailRS><ota:Success/><ota:Warnings><ota:Warning Code="438"/></ota:Warnings><ota:RoomStay><ota:RoomType RoomTypeCode="R"/></ota:RoomStay></ota:OTA_HotelAvailRS>')
    )
    assert result["success"] is True
    assert result["result_class"] == WARNING_SUCCESS
    assert result["warning_codes"] == ["438"]


def test_missing_explicit_success_is_malformed_not_success():
    result = parse_read_rs(_soap("<ota:OTA_ResRetrieveRS/>"))
    assert result["success"] is False
    assert result["result_class"] == MALFORMED
    assert result["count"] == 0


def test_non_limit_provider_error_is_definitive_rejection():
    result = parse_ari_update_rs(_soap('<ota:OTA_HotelAvailNotifRS><ota:Errors><ota:Error Code="15"/></ota:Errors></ota:OTA_HotelAvailNotifRS>'))
    assert result["success"] is False
    assert result["result_class"] == REJECTED
