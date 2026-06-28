"""
Channel Manager — Provider Failover
Circuit breaker + retry/backoff for OTA provider communication.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failures exceeded threshold, blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


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
        self.last_failure_time: float | None = None
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

    # ── Local (in-process) primitives ────────────────────────────────
    # These are the original synchronous breaker mechanics. They remain the
    # fast-path + safe fallback whenever the shared Redis store is disabled
    # or a single Redis op fails. The async wrappers below prefer the shared
    # store and only call these when Redis is not in play.

    def _local_try_acquire(self) -> bool:
        if not self.is_available:
            return False
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1
        return True

    def _local_record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                logger.info(f"Circuit {self.provider}: HALF_OPEN → CLOSED (recovered)")
        else:
            self.failure_count = max(0, self.failure_count - 1)

    def _local_record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit {self.provider}: HALF_OPEN → OPEN (still failing)")
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit {self.provider}: CLOSED → OPEN (threshold breached)")

    def _apply_shared_state(self, state: str) -> None:
        """Mirror the authoritative Redis state into the local field so the
        observability surfaces (get_status / get_state_counts) on this worker
        reflect the shared view. Counts stay authoritative in Redis; we only
        sync the state enum here (best-effort, never raises)."""
        try:
            self.state = CircuitState(state)
        except (ValueError, TypeError):
            pass

    # ── Distributed (Redis-shared) admission/accounting ───────────────
    # When the shared store is enabled, admission and accounting are atomic
    # across the whole fleet (one OPEN trip fail-fasts every worker; the
    # fleet-wide HALF_OPEN probe budget is enforced in a single Lua call).
    # Any Redis error transparently degrades to the in-process primitives.

    async def try_acquire(self) -> bool:
        """Atomic admission. Reserves a HALF_OPEN slot when applicable.

        Distributed: the slot reservation happens in Redis so concurrent
        workers cannot collectively exceed ``half_open_max_calls``.
        Local fallback: GIL-atomic between two cooperative awaits (there is
        no async yield inside ``_local_try_acquire``).
        """
        from infra.circuit_breaker_store import circuit_breaker_store

        if circuit_breaker_store.enabled:
            try:
                state, admitted = await circuit_breaker_store.try_acquire(
                    self.provider,
                    self.recovery_timeout,
                    self.half_open_max_calls,
                )
                self._apply_shared_state(state)
                return admitted
            except Exception as e:
                logger.debug(f"CB store try_acquire fallback for {self.provider}: {e}")
        return self._local_try_acquire()

    async def record_success(self):
        from infra.circuit_breaker_store import circuit_breaker_store

        if circuit_breaker_store.enabled:
            try:
                state = await circuit_breaker_store.record_success(
                    self.provider,
                    self.half_open_max_calls,
                )
                self._apply_shared_state(state)
                return
            except Exception as e:
                logger.debug(f"CB store record_success fallback for {self.provider}: {e}")
        self._local_record_success()

    async def record_failure(self):
        from infra.circuit_breaker_store import circuit_breaker_store

        if circuit_breaker_store.enabled:
            try:
                state = await circuit_breaker_store.record_failure(
                    self.provider,
                    self.failure_threshold,
                )
                self._apply_shared_state(state)
                return
            except Exception as e:
                logger.debug(f"CB store record_failure fallback for {self.provider}: {e}")
        self._local_record_failure()

    def get_status(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "last_failure": datetime.fromtimestamp(self.last_failure_time, tz=UTC).isoformat() if self.last_failure_time else None,
        }


class ProviderFailover:
    """Manages circuit breakers and retry logic for all OTA providers."""

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}
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
    ) -> dict[str, Any]:
        """Execute an operation against a provider with circuit breaker and retry logic."""
        breaker = self.get_breaker(provider)

        # Atomic admission via try_acquire — combines is_available check with
        # HALF_OPEN slot reservation in a single non-yielding call so that
        # concurrent execute_with_failover() invocations cannot exceed
        # half_open_max_calls (regression guard, same fix as direct provider
        # wrappers in HR/Exely push paths).
        if not await breaker.try_acquire():
            return {
                "status": "circuit_open",
                "provider": provider,
                "message": f"Circuit breaker open for {provider}. Will retry after recovery timeout.",
                "circuit_state": breaker.get_status(),
            }

        last_error = None
        for attempt in range(self._retry_config["max_retries"]):
            try:
                # Subsequent retry attempts within this admission already hold
                # a HALF_OPEN slot from the initial try_acquire() — do NOT
                # double-increment half_open_calls here.
                result = await operation(*args, **kwargs)
                await breaker.record_success()
                return {
                    "status": "success",
                    "provider": provider,
                    "attempt": attempt + 1,
                    "result": result,
                }

            except Exception as e:
                last_error = e
                await breaker.record_failure()
                logger.warning(f"Provider {provider} attempt {attempt + 1} failed: {e}")

                if not breaker.is_available:
                    break

                delay = min(
                    self._retry_config["base_delay"] * (self._retry_config["backoff_factor"] ** attempt),
                    self._retry_config["max_delay"],
                )
                if self._retry_config["jitter"]:
                    import random

                    delay *= 0.5 + random.random()

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

    def _status_from_shared(self, key: str, shared: dict | None) -> dict:
        """Build a get_status()-shaped dict from a shared Redis hash, falling
        back to the local breaker's view (or a default CLOSED) when the key
        has no shared state. Used by the *_shared observability readers so
        they report the fleet-wide view, not just this worker's."""
        local = self._breakers.get(key)
        failure_threshold = local.failure_threshold if local else 5
        recovery_timeout = local.recovery_timeout if local else 60
        if not shared:
            if local:
                return local.get_status()
            return {
                "provider": key,
                "state": CircuitState.CLOSED.value,
                "failure_count": 0,
                "failure_threshold": failure_threshold,
                "recovery_timeout": recovery_timeout,
                "last_failure": None,
            }
        state = shared.get("state", CircuitState.CLOSED.value)
        try:
            failure_count = int(shared.get("failure_count", 0) or 0)
        except (TypeError, ValueError):
            failure_count = 0
        last_failure = None
        lft = shared.get("last_failure_time")
        if lft:
            try:
                last_failure = datetime.fromtimestamp(float(lft), tz=UTC).isoformat()
            except (TypeError, ValueError, OSError):
                last_failure = None
        return {
            "provider": key,
            "state": state,
            "failure_count": failure_count,
            "failure_threshold": failure_threshold,
            "recovery_timeout": recovery_timeout,
            "last_failure": last_failure,
        }

    async def get_all_status_shared(self) -> list:
        """Fleet-wide breaker status. Reads shared Redis state when enabled
        (union of Redis keys + locally-known breakers), else falls back to
        the in-process snapshot. Best-effort — any Redis error degrades to
        ``get_all_status()``."""
        from infra.circuit_breaker_store import circuit_breaker_store

        if circuit_breaker_store.enabled:
            try:
                states = await circuit_breaker_store.get_all_states()
                keys = set(states.keys()) | set(self._breakers.keys())
                return [self._status_from_shared(k, states.get(k)) for k in sorted(keys)]
            except Exception as e:
                logger.debug(f"CB store get_all_status_shared fallback: {e}")
        return self.get_all_status()

    async def get_state_counts_shared(self) -> dict[str, int]:
        """Like get_state_counts() but over the fleet-wide shared view."""
        statuses = await self.get_all_status_shared()
        states = [s.get("state") for s in statuses]
        return {
            "total": len(states),
            "open": sum(1 for s in states if s == "open"),
            "half_open": sum(1 for s in states if s == "half_open"),
            "closed": sum(1 for s in states if s == "closed"),
        }

    async def get_status_shared(self, provider: str) -> dict:
        """Fleet-wide status for a single breaker (shared Redis when enabled,
        else this worker's local view)."""
        from infra.circuit_breaker_store import circuit_breaker_store

        if circuit_breaker_store.enabled:
            try:
                shared = await circuit_breaker_store.get_state(provider)
                return self._status_from_shared(provider, shared)
            except Exception as e:
                logger.debug(f"CB store get_status_shared fallback for {provider}: {e}")
        return self.get_breaker(provider).get_status()

    def get_state_counts(self) -> dict[str, int]:
        """Public, ops-friendly count of breakers grouped by state.

        Used by `infra/cm_observability_check.get_circuit_breaker_status`
        so that observability code never has to touch the private
        ``_breakers`` mapping (forward-compat: future thread-safe wrapper
        or LRU eviction can override this method without breaking
        readiness/alerting consumers).

        Returns dict with keys: ``total``, ``open``, ``half_open``,
        ``closed``. Counts are point-in-time snapshots — no locking.
        """
        breakers = list(self._breakers.values())

        def _state_str(b) -> str:
            s = getattr(b, "state", None)
            return getattr(s, "value", s) if s is not None else "unknown"

        states = [_state_str(b) for b in breakers]
        return {
            "total": len(breakers),
            "open": sum(1 for s in states if s == "open"),
            "half_open": sum(1 for s in states if s == "half_open"),
            "closed": sum(1 for s in states if s == "closed"),
        }

    def reset_breaker(self, provider: str):
        breaker = self.get_breaker(provider)
        breaker.state = CircuitState.CLOSED
        breaker.failure_count = 0
        breaker.success_count = 0
        breaker.half_open_calls = 0
        logger.info(f"Circuit breaker for {provider} manually reset")

    async def reset_breaker_shared(self, provider: str):
        """Manual reset that clears BOTH this worker's local breaker and the
        shared Redis state so an operator-triggered reset takes effect across
        the whole fleet (not just the pod that served the request)."""
        self.reset_breaker(provider)
        from infra.circuit_breaker_store import circuit_breaker_store

        if circuit_breaker_store.enabled:
            try:
                await circuit_breaker_store.reset(provider)
            except Exception as e:
                logger.debug(f"CB store reset fallback for {provider}: {e}")


# Singleton
provider_failover = ProviderFailover()
