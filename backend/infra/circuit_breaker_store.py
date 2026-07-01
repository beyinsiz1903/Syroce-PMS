"""
Circuit Breaker Store — cross-instance shared state for the OTA provider
circuit breakers in ``domains.channel_manager.provider_failover``.

Why
---
The in-process ``CircuitBreaker`` is correct only on the worker that saw
the failures: a parallel worker keeps hammering an already-OPEN upstream
because its local breaker is still CLOSED. This store keeps the breaker
state (``state`` / ``failure_count`` / ``last_failure_time`` + the
HALF_OPEN admission counter) in Redis so the whole fleet shares one view:

  * One worker tripping a connection to OPEN immediately fail-fasts the
    same connection on every other worker (admission reads Redis).
  * Recovery is coordinated: HALF_OPEN admission is reserved atomically in
    Redis (Lua), so the *whole fleet* sends at most ``half_open_max_calls``
    probes — not that many per worker — and a recovering upstream is not
    re-drowned.

Design constraints (mirrors the existing ``auth_cache_pubsub`` /
``distributed_lock`` patterns — no new parallel Redis client):
  * **Per-connection isolation preserved** — the breaker key
    (``hotelrunner:{connection_id}`` / ``exely:{connection_id}``) is reused
    verbatim, namespaced under ``cb:``. Connection_id already appears in the
    in-process key; no credentials/PII are ever written to Redis values.
  * **Safe fallback** — if Redis is unavailable (``set_redis`` never called)
    or any single op raises, the caller transparently falls back to the
    in-process breaker. CM push flows keep working, single-worker correct.
  * **Atomicity via Lua** — admission, failure and success are single
    round-trip Lua scripts that use the Redis server clock (``TIME``) so
    pods with skewed clocks still agree on recovery timing.

Keys self-expire (``_STATE_TTL_MS``) so a connection removed forever does
not leave a stale OPEN key behind; the TTL is refreshed on every write.
"""

import logging
from typing import Any

logger = logging.getLogger("infra.circuit_breaker_store")

_KEY_PREFIX = "cb:"
# Abandoned breaker keys self-expire after 24h (refreshed on every write).
_STATE_TTL_MS = 24 * 60 * 60 * 1000

# ── Atomic admission ──────────────────────────────────────────────────
# Returns {state, admitted} where admitted is 1 (call allowed) or 0
# (fail-fast). Reserves a HALF_OPEN slot atomically so the fleet-wide
# probe count never exceeds half_open_max_calls.
_ACQUIRE_LUA = """
local key = KEYS[1]
local recovery_timeout = tonumber(ARGV[1])
local half_open_max = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local t = redis.call('TIME')
local now = tonumber(t[1])
local state = redis.call('HGET', key, 'state')
if (not state) or state == 'closed' then
  return {'closed', 1}
end
if state == 'open' then
  local lft = tonumber(redis.call('HGET', key, 'last_failure_time') or '0')
  if lft > 0 and (now - lft) >= recovery_timeout then
    redis.call('HSET', key, 'state', 'half_open', 'half_open_calls', 1, 'success_count', 0)
    redis.call('PEXPIRE', key, ttl)
    return {'half_open', 1}
  end
  return {'open', 0}
end
if state == 'half_open' then
  local hoc = tonumber(redis.call('HGET', key, 'half_open_calls') or '0')
  if hoc < half_open_max then
    redis.call('HINCRBY', key, 'half_open_calls', 1)
    redis.call('PEXPIRE', key, ttl)
    return {'half_open', 1}
  end
  return {'half_open', 0}
end
return {'closed', 1}
"""

# ── Atomic failure record ─────────────────────────────────────────────
# A failure in HALF_OPEN re-opens immediately; in CLOSED it increments the
# counter and opens once failure_threshold is breached. Returns new state.
_RECORD_FAILURE_LUA = """
local key = KEYS[1]
local failure_threshold = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local t = redis.call('TIME')
local now = tonumber(t[1])
local state = redis.call('HGET', key, 'state')
if not state then state = 'closed' end
redis.call('HSET', key, 'last_failure_time', now)
if state == 'half_open' then
  redis.call('HSET', key, 'state', 'open')
  redis.call('PEXPIRE', key, ttl)
  return 'open'
end
local fc = redis.call('HINCRBY', key, 'failure_count', 1)
redis.call('PEXPIRE', key, ttl)
if fc >= failure_threshold then
  redis.call('HSET', key, 'state', 'open')
  return 'open'
end
return state
"""

# ── Atomic success record ─────────────────────────────────────────────
# In HALF_OPEN, half_open_max consecutive successes close the breaker; in
# CLOSED it bleeds the failure counter down. Returns new state.
_RECORD_SUCCESS_LUA = """
local key = KEYS[1]
local half_open_max = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local state = redis.call('HGET', key, 'state')
if not state then state = 'closed' end
if state == 'half_open' then
  local sc = redis.call('HINCRBY', key, 'success_count', 1)
  redis.call('PEXPIRE', key, ttl)
  if sc >= half_open_max then
    redis.call('HSET', key, 'state', 'closed', 'failure_count', 0, 'success_count', 0, 'half_open_calls', 0)
    return 'closed'
  end
  return 'half_open'
end
local fc = tonumber(redis.call('HGET', key, 'failure_count') or '0')
if fc > 0 then
  redis.call('HINCRBY', key, 'failure_count', -1)
end
redis.call('PEXPIRE', key, ttl)
return state
"""


class CircuitBreakerStore:
    """Singleton bridge between the in-process breakers and Redis.

    ``enabled`` is False until ``set_redis`` wires a client at bootstrap;
    while disabled every method raises ``CircuitBreakerStoreDisabled`` and
    the breaker silently uses its in-process fast-path.
    """

    def __init__(self):
        self._redis = None
        self._metrics = {
            "acquire_admitted": 0,
            "acquire_rejected": 0,
            "failures_recorded": 0,
            "successes_recorded": 0,
            "errors": 0,
            "last_error": None,
        }

    @property
    def enabled(self) -> bool:
        return self._redis is not None

    def set_redis(self, client) -> None:
        """Wire (or clear) the shared Redis client. Idempotent."""
        self._redis = client
        if client is not None:
            logger.info("Circuit breaker store: Redis-backed shared state enabled")

    def _k(self, key: str) -> str:
        return f"{_KEY_PREFIX}{key}"

    def _note_error(self, e: Exception) -> None:
        self._metrics["errors"] += 1
        self._metrics["last_error"] = f"{type(e).__name__}: {str(e)[:160]}"

    async def try_acquire(self, key: str, recovery_timeout: int, half_open_max: int) -> tuple[str, bool]:
        """Atomically decide admission for ``key``. Returns (state, admitted)."""
        res = await self._redis.eval(
            _ACQUIRE_LUA,
            1,
            self._k(key),
            recovery_timeout,
            half_open_max,
            _STATE_TTL_MS,
        )
        state = res[0]
        if isinstance(state, bytes):
            state = state.decode("utf-8", "replace")
        admitted = bool(int(res[1]))
        if admitted:
            self._metrics["acquire_admitted"] += 1
        else:
            self._metrics["acquire_rejected"] += 1
        return state, admitted

    async def record_failure(self, key: str, failure_threshold: int) -> str:
        state = await self._redis.eval(
            _RECORD_FAILURE_LUA,
            1,
            self._k(key),
            failure_threshold,
            _STATE_TTL_MS,
        )
        if isinstance(state, bytes):
            state = state.decode("utf-8", "replace")
        self._metrics["failures_recorded"] += 1
        return state

    async def record_success(self, key: str, half_open_max: int) -> str:
        state = await self._redis.eval(
            _RECORD_SUCCESS_LUA,
            1,
            self._k(key),
            half_open_max,
            _STATE_TTL_MS,
        )
        if isinstance(state, bytes):
            state = state.decode("utf-8", "replace")
        self._metrics["successes_recorded"] += 1
        return state

    async def get_state(self, key: str) -> dict[str, Any] | None:
        """Read the shared hash for one breaker (None if never written)."""
        h = await self._redis.hgetall(self._k(key))
        return _decode_hash(h) if h else None

    async def reset(self, key: str) -> None:
        await self._redis.delete(self._k(key))

    async def get_all_states(self) -> dict[str, dict[str, Any]]:
        """SCAN every ``cb:*`` key and return {breaker_key: hash}.

        Best-effort: the caller falls back to local state on any error
        (cluster SCAN quirks etc.). Used only by observability surfaces.
        """
        out: dict[str, dict[str, Any]] = {}
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor=cursor, match=f"{_KEY_PREFIX}*", count=200)
            for k in keys:
                kk = k.decode("utf-8", "replace") if isinstance(k, bytes) else k
                h = await self._redis.hgetall(kk)
                if h:
                    out[kk[len(_KEY_PREFIX) :]] = _decode_hash(h)
            if cursor == 0:
                break
        return out

    def get_metrics(self) -> dict[str, Any]:
        return {**self._metrics, "enabled": self.enabled}


def _decode_hash(h: dict) -> dict[str, Any]:
    """Normalise a (possibly bytes-keyed) Redis hash to str→str."""
    out: dict[str, Any] = {}
    for k, v in h.items():
        kk = k.decode("utf-8", "replace") if isinstance(k, bytes) else k
        vv = v.decode("utf-8", "replace") if isinstance(v, bytes) else v
        out[kk] = vv
    return out


# Singleton
circuit_breaker_store = CircuitBreakerStore()
