"""
Channel Manager — Provider Failover
Circuit breaker + retry/backoff for OTA provider communication.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failures exceeded threshold, blocking requests
    HALF_OPEN = "half_open" # Testing if service recovered


class CircuitBreaker:
    """Per-provider circuit breaker with configurable thresholds."""

    def __init__(
        self,
        provider: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
    ):
        self.provider = provider
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_calls = 0

    @property
    def is_available(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self.last_failure_time and (time.time() - self.last_failure_time) >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info(f"Circuit {self.provider}: OPEN → HALF_OPEN")
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.half_open_max_calls
        return False

    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                logger.info(f"Circuit {self.provider}: HALF_OPEN → CLOSED (recovered)")
        else:
            self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit {self.provider}: HALF_OPEN → OPEN (still failing)")
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit {self.provider}: CLOSED → OPEN (threshold breached)")

    def get_status(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "last_failure": datetime.fromtimestamp(self.last_failure_time, tz=timezone.utc).isoformat() if self.last_failure_time else None,
        }


class ProviderFailover:
    """Manages circuit breakers and retry logic for all OTA providers."""

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._retry_config = {
            "max_retries": 3,
            "base_delay": 1.0,
            "max_delay": 30.0,
            "backoff_factor": 2.0,
            "jitter": True,
        }

    def get_breaker(self, provider: str) -> CircuitBreaker:
        if provider not in self._breakers:
            self._breakers[provider] = CircuitBreaker(provider)
        return self._breakers[provider]

    async def execute_with_failover(
        self,
        provider: str,
        operation: Callable[..., Awaitable],
        *args,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute an operation against a provider with circuit breaker and retry logic."""
        breaker = self.get_breaker(provider)

        if not breaker.is_available:
            return {
                "status": "circuit_open",
                "provider": provider,
                "message": f"Circuit breaker open for {provider}. Will retry after recovery timeout.",
                "circuit_state": breaker.get_status(),
            }

        last_error = None
        for attempt in range(self._retry_config["max_retries"]):
            try:
                if breaker.state == CircuitState.HALF_OPEN:
                    breaker.half_open_calls += 1

                result = await operation(*args, **kwargs)
                breaker.record_success()
                return {
                    "status": "success",
                    "provider": provider,
                    "attempt": attempt + 1,
                    "result": result,
                }

            except Exception as e:
                last_error = e
                breaker.record_failure()
                logger.warning(f"Provider {provider} attempt {attempt + 1} failed: {e}")

                if not breaker.is_available:
                    break

                delay = min(
                    self._retry_config["base_delay"] * (self._retry_config["backoff_factor"] ** attempt),
                    self._retry_config["max_delay"],
                )
                if self._retry_config["jitter"]:
                    import random
                    delay *= (0.5 + random.random())

                await asyncio.sleep(delay)

        return {
            "status": "failed",
            "provider": provider,
            "attempts": self._retry_config["max_retries"],
            "error": str(last_error),
            "circuit_state": breaker.get_status(),
        }

    def get_all_status(self) -> list:
        return [b.get_status() for b in self._breakers.values()]

    def reset_breaker(self, provider: str):
        breaker = self.get_breaker(provider)
        breaker.state = CircuitState.CLOSED
        breaker.failure_count = 0
        breaker.success_count = 0
        logger.info(f"Circuit breaker for {provider} manually reset")


# Singleton
provider_failover = ProviderFailover()
