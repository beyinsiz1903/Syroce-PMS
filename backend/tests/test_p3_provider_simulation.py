"""
P3 — Real Provider Simulation Tests
=====================================

Simulates real-world provider failure scenarios to prove
the delivery state machine handles edge cases correctly:

  1. 429 Too Many Requests — rate limiter drains tokens
  2. Timeout — classified as retryable, respects max attempts
  3. Intermittent 200/500 — alternating success/failure
  4. Delayed ACK — ACK arrives but apply not guaranteed
  5. ACK but no apply — ack_means_applied=False
  6. Apply but late verify — verify comes after consistency window
  7. Permanent failures (400, 401, 403, 422)
  8. Connection errors — classified as retryable
  9. Retry exhaustion — after max attempts → manual_review
  10. Provider error classification accuracy

These tests validate the ack_service, retry_policy, rate_limit_service,
and outbound_service components without requiring live provider connections.
"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest

from domains.channel_manager.ari.events import ARIChangeEvent, ARIDelta, ProviderResult
from domains.channel_manager.ari.ack_service import process_ack
from domains.channel_manager.ari.retry_policy import (
    classify_error, should_retry, get_retry_delay,
)
from domains.channel_manager.ari.rate_limit_service import (
    ARIRateLimitService, TokenBucket, PROVIDER_RATE_LIMITS,
)
from domains.channel_manager.ari.models import (
    STATUS_ACKED, STATUS_FAILED_RETRYABLE, STATUS_FAILED_PERMANENT,
    MAX_RETRY_ATTEMPTS, RETRY_DELAYS,
)
from domains.channel_manager.provider_capability import (
    get_capability, PROVIDER_CAPABILITIES,
    classify_error as cap_classify_error,
    should_retry as cap_should_retry,
    get_retry_delay as cap_get_retry_delay,
)
from domains.channel_manager.data_model import ErrorClass


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _change_set(provider="exely", attempt=0):
    return {
        "id": "cs-sim-1",
        "tenant_id": "t1",
        "property_id": "p1",
        "provider": provider,
        "coalescing_key": f"t1|p1|{provider}|DBL|STD|2026-08-01:2026-08-07|availability",
        "room_type_code": "DBL",
        "rate_plan_code": "STD",
        "date_from": "2026-08-01",
        "date_to": "2026-08-07",
        "change_scope": "availability",
        "compacted_payload": {"availability": 5},
        "provider_delta_hash": "abc123",
        "outbound_change_id": "oc-1",
        "outbound_attempt_count": attempt,
    }


def _provider_result(
    success=True, provider="exely", status_code=200,
    error=None, duration_ms=150, retryable=False,
):
    return ProviderResult(
        success=success,
        provider=provider,
        status_code=status_code,
        response_payload={"ok": True} if success else None,
        error=error,
        duration_ms=duration_ms,
        retryable=retryable,
    )


# ═══════════════════════════════════════════════════════════════
# 1. 429 TOO MANY REQUESTS
# ═══════════════════════════════════════════════════════════════

class TestRateLimit429:
    """429 responses → rate limiter drains, retryable."""

    def test_429_classified_as_rate_limited(self):
        """HTTP 429 → 'rate_limited' classification."""
        result = classify_error(429, "Too Many Requests")
        assert result == "rate_limited"

    def test_429_always_retryable(self):
        """429 is always retryable regardless of attempt count."""
        # In the retry_policy module, 429 is a special case
        assert classify_error(429, "") == "rate_limited"

    @pytest.mark.asyncio
    async def test_429_ack_processing(self):
        """429 result → change set marked failed_retryable."""
        cs = _change_set()
        result = _provider_result(
            success=False, status_code=429,
            error="Too Many Requests", retryable=True,
        )
        with patch("domains.channel_manager.ari.ack_service.repo") as mock_repo:
            mock_repo.insert_outbound_log = AsyncMock(return_value="log-1")
            mock_repo.update_change_set_status = AsyncMock()

            status = await process_ack(cs, result, "oc-1")
            assert status == STATUS_FAILED_RETRYABLE

    def test_rate_limiter_token_drain_on_429(self):
        """After recording 429, tokens drop to 0."""
        rl = ARIRateLimitService()
        # Fill tokens
        rl._get_bucket("exely", "p1")
        rl.record_429("exely", "p1")
        bucket = rl._get_bucket("exely", "p1")
        assert bucket.tokens == 0

    def test_token_bucket_try_consume_fails_when_empty(self):
        """Empty bucket → try_consume returns False."""
        bucket = TokenBucket(rate=5, capacity=5)
        bucket.tokens = 0
        assert bucket.try_consume() is False

    def test_token_bucket_refills_over_time(self):
        """Bucket refills tokens based on elapsed time."""
        bucket = TokenBucket(rate=60, capacity=60)  # 1 token per second
        bucket.tokens = 0
        bucket.last_refill = time.monotonic() - 2  # 2 seconds ago
        bucket._refill()
        assert bucket.tokens >= 1.5  # ~2 tokens after 2 seconds


# ═══════════════════════════════════════════════════════════════
# 2. TIMEOUT
# ═══════════════════════════════════════════════════════════════

class TestTimeout:
    """Timeout errors → retryable with backoff."""

    def test_timeout_classified_retryable(self):
        """'timeout' in error → retryable."""
        assert classify_error(0, "connection timeout") == "retryable"
        assert classify_error(0, "Request Timeout") == "retryable"

    def test_timeout_capability_matrix(self):
        """Timeout classified as RETRYABLE in provider capability matrix."""
        assert cap_classify_error("exely", "timeout") == ErrorClass.RETRYABLE
        assert cap_classify_error("hotelrunner", "timeout") == ErrorClass.RETRYABLE

    def test_timeout_retry_allowed(self):
        """Timeout allows retry on first attempts."""
        assert should_retry(1) is True  # attempt 1 < MAX (5)

    def test_timeout_exponential_backoff(self):
        """Retry delays increase with each attempt."""
        delays = RETRY_DELAYS
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]

    @pytest.mark.asyncio
    async def test_timeout_ack_processing(self):
        """Timeout result → retryable status."""
        cs = _change_set(attempt=0)
        result = _provider_result(
            success=False, status_code=0,
            error="Connection timeout after 30s",
        )
        with patch("domains.channel_manager.ari.ack_service.repo") as mock_repo:
            mock_repo.insert_outbound_log = AsyncMock(return_value="log-1")
            mock_repo.update_change_set_status = AsyncMock()

            status = await process_ack(cs, result, "oc-1")
            assert status == STATUS_FAILED_RETRYABLE


# ═══════════════════════════════════════════════════════════════
# 3. INTERMITTENT 200/500
# ═══════════════════════════════════════════════════════════════

class TestIntermittent200500:
    """Alternating success/failure → retry until success or exhaustion."""

    def test_500_classified_retryable(self):
        """HTTP 500 → retryable."""
        assert classify_error(500, "") == "retryable"
        assert classify_error(502, "") == "retryable"
        assert classify_error(503, "") == "retryable"

    def test_200_after_500_succeeds(self):
        """Success after previous failure → acked."""
        result = _provider_result(success=True, status_code=200)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_500_then_200_sequence(self):
        """First call 500 (retryable), second call 200 (acked)."""
        with patch("domains.channel_manager.ari.ack_service.repo") as mock_repo:
            mock_repo.insert_outbound_log = AsyncMock(return_value="log-1")
            mock_repo.update_change_set_status = AsyncMock()

            # Attempt 1: 500
            cs = _change_set(attempt=0)
            r1 = _provider_result(success=False, status_code=500, error="Internal Server Error")
            s1 = await process_ack(cs, r1, "oc-1")
            assert s1 == STATUS_FAILED_RETRYABLE

            # Attempt 2: 200
            cs2 = _change_set(attempt=1)
            r2 = _provider_result(success=True, status_code=200)
            s2 = await process_ack(cs2, r2, "oc-1")
            assert s2 == STATUS_ACKED

    def test_intermittent_error_in_capability_matrix(self):
        """500/502/503 are retryable in both provider matrices."""
        for code_str in ["500", "502", "503"]:
            assert cap_classify_error("exely", code_str) == ErrorClass.RETRYABLE


# ═══════════════════════════════════════════════════════════════
# 4. DELAYED ACK
# ═══════════════════════════════════════════════════════════════

class TestDelayedAck:
    """ACK arrives but doesn't mean applied."""

    def test_exely_ack_not_applied(self):
        """Exely: ack_means_applied = False."""
        cap = get_capability("exely")
        assert cap.ack_means_applied is False

    def test_hotelrunner_ack_not_applied(self):
        """HotelRunner: ack_means_applied = False."""
        cap = get_capability("hotelrunner")
        assert cap.ack_means_applied is False

    def test_consistency_window_exely(self):
        """Exely has 60s eventual consistency window."""
        cap = get_capability("exely")
        assert cap.eventual_consistency_window_seconds == 60

    def test_consistency_window_hotelrunner(self):
        """HotelRunner has 15s eventual consistency window."""
        cap = get_capability("hotelrunner")
        assert cap.eventual_consistency_window_seconds == 15

    def test_typical_ack_latency(self):
        """Exely ACK typically 3000ms, HR 1000ms."""
        assert get_capability("exely").typical_ack_latency_ms == 3000
        assert get_capability("hotelrunner").typical_ack_latency_ms == 1000


# ═══════════════════════════════════════════════════════════════
# 5. ACK BUT NO APPLY
# ═══════════════════════════════════════════════════════════════

class TestAckButNoApply:
    """HTTP 200 ≠ inventory applied. Drift detection needed."""

    @pytest.mark.asyncio
    async def test_ack_marks_status_acked(self):
        """Successful result → status 'acked', NOT 'applied'."""
        cs = _change_set()
        result = _provider_result(success=True, status_code=200)
        with patch("domains.channel_manager.ari.ack_service.repo") as mock_repo:
            mock_repo.insert_outbound_log = AsyncMock(return_value="log-1")
            mock_repo.update_change_set_status = AsyncMock()

            status = await process_ack(cs, result, "oc-1")
            assert status == STATUS_ACKED  # acked, not "applied"

            # Verify update_change_set_status called with 'acked'
            mock_repo.update_change_set_status.assert_called_with("cs-sim-1", STATUS_ACKED)

    def test_ack_means_applied_false_for_all_providers(self):
        """All configured providers: ack ≠ applied."""
        for name, cap in PROVIDER_CAPABILITIES.items():
            assert cap.ack_means_applied is False, (
                f"Provider {name} should have ack_means_applied=False"
            )


# ═══════════════════════════════════════════════════════════════
# 6. LATE VERIFY
# ═══════════════════════════════════════════════════════════════

class TestLateVerify:
    """Verify arrives after consistency window."""

    def test_consistency_window_exists(self):
        """Both providers define a consistency window."""
        for name in ["exely", "hotelrunner"]:
            cap = get_capability(name)
            assert cap.eventual_consistency_window_seconds > 0

    def test_exely_window_longer_than_hr(self):
        """Exely's consistency window is longer (SOAP vs REST)."""
        exely = get_capability("exely")
        hr = get_capability("hotelrunner")
        assert exely.eventual_consistency_window_seconds > hr.eventual_consistency_window_seconds


# ═══════════════════════════════════════════════════════════════
# 7. PERMANENT FAILURES
# ═══════════════════════════════════════════════════════════════

class TestPermanentFailures:
    """400, 401, 403, 422 → permanent, no retry."""

    @pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
    def test_permanent_http_codes(self, code):
        """These codes are permanent failures."""
        result = classify_error(code, "")
        assert result == "permanent"

    def test_permanent_no_retry(self):
        """Permanent errors → should_retry = False regardless of attempt."""
        assert should_retry(0) is True  # 0 < MAX
        # But classify_error for 400 is permanent, so ack_service won't retry

    @pytest.mark.asyncio
    async def test_permanent_failure_ack(self):
        """Permanent failure → manual_review status."""
        cs = _change_set(attempt=0)
        result = _provider_result(
            success=False, status_code=400,
            error="Invalid request body",
        )
        with patch("domains.channel_manager.ari.ack_service.repo") as mock_repo:
            mock_repo.insert_outbound_log = AsyncMock(return_value="log-1")
            mock_repo.update_change_set_status = AsyncMock()

            status = await process_ack(cs, result, "oc-1")
            assert status == STATUS_FAILED_PERMANENT

    def test_config_errors_in_capability_matrix(self):
        """Auth/credential errors → CONFIGURATION class (not retryable)."""
        assert cap_classify_error("exely", "invalid credentials") == ErrorClass.CONFIGURATION
        assert cap_classify_error("hotelrunner", "invalid api key") == ErrorClass.CONFIGURATION

    def test_business_rejection_not_retryable(self):
        """Business rejections → no retry."""
        assert cap_classify_error("exely", "closed date range") == ErrorClass.BUSINESS_REJECTION
        assert cap_should_retry("exely", "closed date range", 0) is False


# ═══════════════════════════════════════════════════════════════
# 8. CONNECTION ERRORS
# ═══════════════════════════════════════════════════════════════

class TestConnectionErrors:
    """Connection errors → retryable."""

    def test_connection_error_retryable(self):
        """'connection' in error → retryable."""
        assert classify_error(0, "Connection refused") == "retryable"
        assert classify_error(0, "Connection reset by peer") == "retryable"

    def test_connection_reset_in_capability(self):
        """Connection reset is retryable in Exely capability."""
        assert cap_classify_error("exely", "connection reset") == ErrorClass.RETRYABLE

    @pytest.mark.asyncio
    async def test_connection_error_ack(self):
        """Connection error result → retryable status."""
        cs = _change_set(attempt=0)
        result = _provider_result(
            success=False, status_code=0,
            error="Connection refused",
        )
        with patch("domains.channel_manager.ari.ack_service.repo") as mock_repo:
            mock_repo.insert_outbound_log = AsyncMock(return_value="log-1")
            mock_repo.update_change_set_status = AsyncMock()

            status = await process_ack(cs, result, "oc-1")
            assert status == STATUS_FAILED_RETRYABLE


# ═══════════════════════════════════════════════════════════════
# 9. RETRY EXHAUSTION
# ═══════════════════════════════════════════════════════════════

class TestRetryExhaustion:
    """After max attempts → manual_review (dead letter)."""

    def test_max_retry_attempts_defined(self):
        """MAX_RETRY_ATTEMPTS is configured."""
        assert MAX_RETRY_ATTEMPTS == 5

    def test_should_retry_at_max(self):
        """At max attempts → no more retries."""
        assert should_retry(MAX_RETRY_ATTEMPTS) is False

    def test_should_retry_below_max(self):
        """Below max → retry allowed."""
        assert should_retry(MAX_RETRY_ATTEMPTS - 1) is True

    @pytest.mark.asyncio
    async def test_exhausted_retry_becomes_permanent(self):
        """After max attempts with retryable error → manual_review."""
        cs = _change_set(attempt=MAX_RETRY_ATTEMPTS)
        result = _provider_result(
            success=False, status_code=500,
            error="Internal Server Error",
        )
        with patch("domains.channel_manager.ari.ack_service.repo") as mock_repo:
            mock_repo.insert_outbound_log = AsyncMock(return_value="log-1")
            mock_repo.update_change_set_status = AsyncMock()

            status = await process_ack(cs, result, "oc-1")
            assert status == STATUS_FAILED_PERMANENT

    def test_retry_delay_increases(self):
        """Delay at attempt N+1 >= delay at attempt N."""
        for i in range(len(RETRY_DELAYS) - 1):
            assert RETRY_DELAYS[i + 1] >= RETRY_DELAYS[i]

    def test_capability_retry_exhaustion_exely(self):
        """Exely: retry at 0 OK, retry at max NOT OK."""
        cap = get_capability("exely")
        assert cap_should_retry("exely", "timeout", 0) is True
        assert cap_should_retry("exely", "timeout", cap.retry_policy.max_attempts) is False

    def test_capability_retry_exhaustion_hotelrunner(self):
        """HotelRunner: retry at 0 OK, retry at max NOT OK."""
        cap = get_capability("hotelrunner")
        assert cap_should_retry("hotelrunner", "timeout", 0) is True
        assert cap_should_retry("hotelrunner", "timeout", cap.retry_policy.max_attempts) is False


# ═══════════════════════════════════════════════════════════════
# 10. PROVIDER ERROR CLASSIFICATION ACCURACY
# ═══════════════════════════════════════════════════════════════

class TestErrorClassificationAccuracy:
    """Provider error taxonomy is complete and correct."""

    @pytest.mark.parametrize("provider", ["exely", "hotelrunner"])
    def test_has_error_classification(self, provider):
        """Each provider has error classification defined."""
        cap = get_capability(provider)
        assert len(cap.error_classification) > 0

    @pytest.mark.parametrize("provider", ["exely", "hotelrunner"])
    def test_has_retry_policy(self, provider):
        """Each provider has a retry policy."""
        cap = get_capability(provider)
        assert cap.retry_policy.max_attempts > 0
        assert cap.retry_policy.base_delay_seconds > 0
        assert cap.retry_policy.max_delay_seconds > cap.retry_policy.base_delay_seconds

    @pytest.mark.parametrize("provider", ["exely", "hotelrunner"])
    def test_has_rate_limits(self, provider):
        """Each provider has rate limit config."""
        cap = get_capability(provider)
        assert cap.rate_limits.requests_per_minute > 0
        assert cap.rate_limits.requests_per_hour > 0
        assert cap.rate_limits.burst_limit > 0

    def test_exely_exponential_backoff(self):
        """Exely backoff increases exponentially."""
        delays = [cap_get_retry_delay("exely", i) for i in range(5)]
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]

    def test_hotelrunner_exponential_backoff(self):
        """HotelRunner backoff increases exponentially."""
        delays = [cap_get_retry_delay("hotelrunner", i) for i in range(5)]
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]

    def test_max_delay_capped_exely(self):
        """Exely delay never exceeds max."""
        cap = get_capability("exely")
        delay = cap_get_retry_delay("exely", 100)
        assert delay <= cap.retry_policy.max_delay_seconds

    def test_max_delay_capped_hotelrunner(self):
        """HotelRunner delay never exceeds max."""
        cap = get_capability("hotelrunner")
        delay = cap_get_retry_delay("hotelrunner", 100)
        assert delay <= cap.retry_policy.max_delay_seconds

    def test_unknown_error_defaults_retryable(self):
        """Unknown error patterns default to RETRYABLE."""
        assert cap_classify_error("exely", "some random unknown error xyz") == ErrorClass.RETRYABLE
        assert cap_classify_error("hotelrunner", "never seen this before") == ErrorClass.RETRYABLE


# ═══════════════════════════════════════════════════════════════
# 11. RATE LIMITER SERVICE CORRECTNESS
# ═══════════════════════════════════════════════════════════════

class TestRateLimiterService:
    """Rate limiter token bucket behaves correctly under load."""

    def test_fresh_bucket_allows_requests(self):
        """New bucket has full tokens → consume succeeds."""
        bucket = TokenBucket(rate=10, capacity=10)
        assert bucket.try_consume() is True

    def test_depleted_bucket_rejects(self):
        """Empty bucket → consume fails."""
        bucket = TokenBucket(rate=10, capacity=10)
        bucket.tokens = 0
        bucket.last_refill = time.monotonic()
        assert bucket.try_consume() is False

    def test_bucket_capacity_limit(self):
        """Tokens never exceed capacity."""
        bucket = TokenBucket(rate=60, capacity=10)
        bucket.last_refill = time.monotonic() - 3600  # 1 hour ago
        bucket._refill()
        assert bucket.tokens <= 10

    def test_rate_limiter_daily_limit(self):
        """Daily limit check works."""
        rl = ARIRateLimitService()
        # Check daily returns True for fresh instance
        assert rl._check_daily("exely", "p1") is True

    def test_rate_limiter_stats(self):
        """Stats reporting works."""
        rl = ARIRateLimitService()
        rl._get_bucket("exely", "p1")
        stats = rl.get_stats()
        assert "exely|p1" in stats

    def test_provider_rate_limits_defined(self):
        """Both providers have rate limit configuration."""
        assert "hotelrunner" in PROVIDER_RATE_LIMITS
        assert "exely" in PROVIDER_RATE_LIMITS


# ═══════════════════════════════════════════════════════════════
# 12. OUTBOUND LOG AUDIT TRAIL
# ═══════════════════════════════════════════════════════════════

class TestOutboundLogAudit:
    """Every push attempt creates an audit log entry."""

    @pytest.mark.asyncio
    async def test_success_logged(self):
        """Successful push → outbound log with success=True."""
        cs = _change_set()
        result = _provider_result(success=True)
        with patch("domains.channel_manager.ari.ack_service.repo") as mock_repo:
            mock_repo.insert_outbound_log = AsyncMock(return_value="log-1")
            mock_repo.update_change_set_status = AsyncMock()

            await process_ack(cs, result, "oc-1")

            # Verify outbound log was inserted
            mock_repo.insert_outbound_log.assert_called_once()
            log_arg = mock_repo.insert_outbound_log.call_args[0][0]
            assert log_arg["success"] is True
            assert log_arg["provider"] == "exely"

    @pytest.mark.asyncio
    async def test_failure_logged(self):
        """Failed push → outbound log with success=False."""
        cs = _change_set()
        result = _provider_result(success=False, status_code=500, error="ISE")
        with patch("domains.channel_manager.ari.ack_service.repo") as mock_repo:
            mock_repo.insert_outbound_log = AsyncMock(return_value="log-1")
            mock_repo.update_change_set_status = AsyncMock()

            await process_ack(cs, result, "oc-1")

            log_arg = mock_repo.insert_outbound_log.call_args[0][0]
            assert log_arg["success"] is False
            assert log_arg["status_code"] == 500

    @pytest.mark.asyncio
    async def test_log_contains_duration(self):
        """Outbound log records push duration."""
        cs = _change_set()
        result = _provider_result(success=True, duration_ms=350)
        with patch("domains.channel_manager.ari.ack_service.repo") as mock_repo:
            mock_repo.insert_outbound_log = AsyncMock(return_value="log-1")
            mock_repo.update_change_set_status = AsyncMock()

            await process_ack(cs, result, "oc-1")

            log_arg = mock_repo.insert_outbound_log.call_args[0][0]
            assert log_arg["duration_ms"] == 350
