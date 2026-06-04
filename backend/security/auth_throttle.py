"""
Bug AT/AU/AV/AX fix — Auth-endpoint sliding-window throttle.

Pre-existing `security.rate_limiter.tenant_rate_limiter` was wired into a
runtime-status service but NEVER applied to authentication endpoints. As a
result `/api/auth/login`, `/api/auth/forgot-password`,
`/api/auth/reset-password-by-token` and `/api/auth/2fa/verify` accepted
unbounded request volume per IP and per account, enabling:
  - Online password brute-force against any account (Bug AT)
  - Email-bomb / Resend cost amplification on a target inbox (Bug AU)
  - Lack of account lockout on repeated wrong passwords (Bug AV)
  - Reset-token brute-force (Bug AX)

This module provides a small in-memory sliding-window throttle plus a
`client_ip` resolver that honours the Replit edge proxy (`X-Forwarded-For`).

Caveats (acknowledged):
  * In-memory: per-uvicorn-worker. Sufficient for single-worker dev/Replit
    deployment; for multi-worker prod, swap to Redis-backed implementation.
  * Sliding window uses a deque per key — O(N) per check where N == max.
    Throttle thresholds are small (≤30) so cost is negligible.
"""
from __future__ import annotations

import asyncio
import logging
import os
import unicodedata
from collections import deque
from datetime import datetime, timedelta

from fastapi import HTTPException, Request

# CI 2026-05-28 NO-GO P0 RCA — 98C D (TWOFA brute-force) ve 98D B (vendor per-IP)
# AYNI senaryo ile başarısız oldu (17×401 / 21×401, hiç 429). İkisi de
# `always_on=True` Mongo-backed throttle. Bu sistemik bir backend
# kullanılabilirlik sorununa işaret eder: `_check_mongo` sessiz hata ile
# fall-through olup per-container in-memory yedeğine düşüyor → Replit
# autoscale (deploymentTarget=autoscale) altında her container kendi
# sayacını tutuyor → cap asla tetiklenmiyor. Tanılayıcı için structured
# logger eklendi — production loglarında root cause'u görmek için her
# bypass'ı kaydeder.
logger = logging.getLogger(__name__)

# When True, trust the rightmost X-Forwarded-For hop (Replit edge proxy
# appends the real peer IP at the END of the chain). When False, ignore XFF
# entirely and use the raw socket peer (safe for non-proxied environments
# where any XFF must be assumed attacker-controlled).
# Default True because production runs behind Replit's mTLS edge.
TRUST_PROXY = os.getenv("TRUST_PROXY", "1") == "1"


# ── Redis-backed sliding window state (shared across replicas/workers) ──
#
# F8AH P0 fix — original SlidingWindowThrottle held counters in a process-local
# `dict[str, deque]`. In a multi-replica/multi-worker deployment (Replit
# autoscale, gunicorn workers, etc.) each process sees only a fraction of
# requests, so a 17-burst attack against /api/auth/2fa/verify distributed
# across N replicas can hit ~ceil(17/N) per replica — never tripping the
# 15/60s threshold. Stress spec 98C-twofa-totp-lifecycle.spec.js D) exposed
# this: 17/17 returned 401 (no 429). Fix: back the window with a Redis
# ZSET (score=now_ms, member=unique_token); ZREMRANGEBYSCORE evicts expired
# entries, ZCARD is the authoritative count across all replicas. In-memory
# state remains as a fail-open fallback when Redis is unreachable so the
# auth surface never goes 503 because of cache outage.
_REDIS_CLIENT = None
_REDIS_INIT_LOCK = asyncio.Lock()
_REDIS_NEXT_RETRY_AT = 0.0  # monotonic seconds; 0 = retry immediately
_REDIS_RETRY_BACKOFF_SECONDS = 30.0  # re-attempt after transient failures


# ── MongoDB-backed sliding window (cross-instance shared state) ──────────
#
# F8AH P0 follow-up — the Redis path is per-instance under Replit autoscale
# (each container runs its own `localhost:6380` redis-server, so two
# instances mean two independent throttle counters and a 17-burst attack
# distributed across them only hits each one with ~9 requests, never
# tripping the 15-cap). The Lua atomic fix is correct *within* one
# instance, but the state itself is not shared.
#
# For `always_on` security-critical throttles (TWOFA_VERIFY_IP,
# SENSITIVE_AUTH_USER, VERIFY_CODE_EMAIL, RESET_CODE_*) we instead back the
# window with MongoDB Atlas, which is already a single shared cluster
# across every deployment instance. The extra ~5-15ms per auth-verify
# check is acceptable; the protection it provides (cross-instance
# brute-force rate limit) is mandatory and cannot be delivered by any
# per-process or per-container backend.
_MONGO_THROTTLE_INDEX_READY = False
_MONGO_THROTTLE_INDEX_LOCK = asyncio.Lock()


async def _ensure_mongo_throttle_indexes() -> bool:
    """Idempotently provision the `throttle_hits` collection indexes.

    Returns True on success / already-present, False on hard failure so
    the caller can fail-CLOSED rather than silently degrade to a path
    that has no cross-instance enforcement.
    """
    global _MONGO_THROTTLE_INDEX_READY
    if _MONGO_THROTTLE_INDEX_READY:
        return True
    async with _MONGO_THROTTLE_INDEX_LOCK:
        if _MONGO_THROTTLE_INDEX_READY:
            return True
        try:
            # `throttle_hits` is system-scoped (keyed by IP / user id, not
            # by tenant_id), so we use `_raw_db` to bypass the tenant
            # proxy which would otherwise raise without a request context.
            from core.database import _raw_db as _db
            # (key, score) compound — supports the sliding-window count
            # query `{key: rkey, score: {$gt: cutoff}}` and the
            # find-oldest sort used for retry-after computation.
            await _db.throttle_hits.create_index(
                [("key", 1), ("score", 1)],
                name="ix_throttle_hits_key_score",
            )
            # TTL index on `expires_at` — Mongo auto-evicts rows past
            # window. expireAfterSeconds=0 means "expire at the exact
            # datetime stored in the field".
            await _db.throttle_hits.create_index(
                "expires_at",
                expireAfterSeconds=0,
                name="ttl_throttle_hits_expires",
            )
            _MONGO_THROTTLE_INDEX_READY = True
            return True
        except Exception:
            # Verify whether equivalent indexes already exist under
            # different names before declaring failure.
            try:
                from core.database import _raw_db as _db
                idx = await _db.throttle_hits.index_information()
                key_score_seen = False
                ttl_seen = False
                for _name, spec in idx.items():
                    keys = spec.get("key") or []
                    if (
                        len(keys) == 2
                        and keys[0][0] == "key"
                        and keys[1][0] == "score"
                    ):
                        key_score_seen = True
                    if (
                        len(keys) == 1
                        and keys[0][0] == "expires_at"
                        and spec.get("expireAfterSeconds") == 0
                    ):
                        ttl_seen = True
                if key_score_seen and ttl_seen:
                    _MONGO_THROTTLE_INDEX_READY = True
                    return True
            except Exception:
                pass
            return False


def _invalidate_redis() -> None:
    """Drop the cached client and arm the reconnect backoff.

    Called when a Redis operation throws against a previously-good client
    (network drop, server restart, etc.). Without this, `_get_redis()`
    would keep returning the dead handle for the lifetime of the process
    and every throttle check would silently fall through to per-process
    in-memory state — reintroducing multi-replica dilution.
    """
    global _REDIS_CLIENT, _REDIS_NEXT_RETRY_AT
    import time as _time
    _REDIS_CLIENT = None
    _REDIS_NEXT_RETRY_AT = _time.monotonic() + _REDIS_RETRY_BACKOFF_SECONDS


async def _get_redis():
    """Return a shared async-redis client, or None if unavailable.

    Lazy + retry-capable. On init/ping failure we record a re-try timestamp
    (30s backoff) instead of permanently flipping a done-flag; this avoids
    the architect-flagged "permanent downgrade" pitfall where a one-shot
    Redis hiccup at first request would lock the process into per-process
    in-memory throttling for its entire lifetime (= re-introducing the
    multi-replica dilution we just fixed). Concurrent callers race on
    `_REDIS_INIT_LOCK` so only one connection attempt is in-flight at a
    time.
    """
    global _REDIS_CLIENT, _REDIS_NEXT_RETRY_AT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    import time as _time
    now = _time.monotonic()
    if now < _REDIS_NEXT_RETRY_AT:
        return None
    async with _REDIS_INIT_LOCK:
        if _REDIS_CLIENT is not None:
            return _REDIS_CLIENT
        now = _time.monotonic()
        if now < _REDIS_NEXT_RETRY_AT:
            return None
        import os as _os
        try:
            from redis import asyncio as aioredis  # type: ignore
            url = _os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            client = aioredis.from_url(
                url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=2,
            )
            await client.ping()
            _REDIS_CLIENT = client
            _REDIS_NEXT_RETRY_AT = 0.0
        except Exception:
            _REDIS_CLIENT = None
            _REDIS_NEXT_RETRY_AT = _time.monotonic() + _REDIS_RETRY_BACKOFF_SECONDS
    return _REDIS_CLIENT


# Atomic sliding-window claim Lua script. Encapsulates trim + count + add
# in a single Redis-side operation so concurrent requests cannot both
# observe `count < max` at the boundary and exceed the cap. The undo-on-
# overlimit pattern from the original non-tx pipeline is replaced by a
# conditional ZADD that never adds when over budget — strictly atomic.
#
# KEYS[1] = redis key
# ARGV[1] = now_ms (claim timestamp)
# ARGV[2] = cutoff_ms (window expiry boundary)
# ARGV[3] = max_requests
# ARGV[4] = ttl_seconds (key expiry; window + slack)
# ARGV[5] = unique member identifier
# RETURN  = {allowed (1|0), retry_after_ms (0 when allowed)}
_SLIDING_WINDOW_LUA = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[2])
local count = redis.call('ZCARD', KEYS[1])
if count >= tonumber(ARGV[3]) then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  local oldest_score = 0
  if oldest[2] then oldest_score = tonumber(oldest[2]) end
  local retry_after_ms = (oldest_score + (tonumber(ARGV[1]) - tonumber(ARGV[2]))) - tonumber(ARGV[1])
  if retry_after_ms < 1 then retry_after_ms = 1 end
  return {0, retry_after_ms}
end
redis.call('ZADD', KEYS[1], tonumber(ARGV[1]), ARGV[5])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[4]))
return {1, 0}
"""

_SLIDING_WINDOW_SHA: str | None = None
_SLIDING_WINDOW_SHA_LOCK = asyncio.Lock()


async def _get_sliding_window_sha(rc) -> str | None:
    global _SLIDING_WINDOW_SHA
    if _SLIDING_WINDOW_SHA is not None:
        return _SLIDING_WINDOW_SHA
    async with _SLIDING_WINDOW_SHA_LOCK:
        if _SLIDING_WINDOW_SHA is not None:
            return _SLIDING_WINDOW_SHA
        try:
            sha = await rc.script_load(_SLIDING_WINDOW_LUA)
            _SLIDING_WINDOW_SHA = sha
            return sha
        except Exception:
            return None


class SlidingWindowThrottle:
    """Per-key sliding window: at most `max_requests` per `window_seconds`.

    Uses Redis ZSET when available (shared across replicas/workers); falls
    back to in-memory `deque` per process when Redis is unreachable. The
    fallback is intentionally fail-OPEN with respect to cross-process
    coordination — a Redis outage degrades the per-IP cap to per-process
    semantics, but never converts a legitimate request into a 503.
    """

    _instance_counter = 0

    def __init__(self, max_requests: int, window_seconds: int, *, always_on: bool = False, name: str | None = None):
        self.max = max_requests
        self.window = timedelta(seconds=window_seconds)
        self._hits: dict[str, deque[datetime]] = {}
        self._lock = asyncio.Lock()
        # F8AG P0 fix — when True, this throttle ignores DISABLE_AUTH_THROTTLE
        # regardless of APP_ENV. Used for brute-force-critical surfaces
        # (TOTP verify) where the dev escape hatch would otherwise mask the
        # absence of throttling in stress runs AND production smoke tests.
        self.always_on = always_on
        # Stable identifier for the Redis key namespace. We can't rely on
        # variable-name reflection so callers may pass `name=` explicitly;
        # otherwise we synthesise a deterministic id from (max, window).
        # Two throttles with identical (max, window) sharing a namespace is
        # fine — keys also include the per-request identity (ip / user / …).
        SlidingWindowThrottle._instance_counter += 1
        self.name = name or f"swt:{max_requests}x{window_seconds}:{SlidingWindowThrottle._instance_counter}"

    def _rkey(self, key: str) -> str:
        return f"throttle:{self.name}:{key}"

    async def _check_redis(self, rc, key: str) -> tuple[bool, int]:
        """Atomic sliding-window claim via server-side Lua.

        Architect-flagged race fix: the original non-tx pipeline left a
        check-then-claim window where two concurrent requests could each
        observe `count < max` and both succeed at the cap boundary. The
        Lua script collapses trim/count/add into a single atomic Redis
        operation, eliminating that window entirely.
        """
        import time as _time
        import uuid as _uuid
        rkey = self._rkey(key)
        now_ms = int(_time.time() * 1000)
        window_ms = int(self.window.total_seconds() * 1000)
        cutoff_ms = now_ms - window_ms
        ttl_s = int(self.window.total_seconds()) + 1
        member = f"{now_ms}:{_uuid.uuid4().hex[:10]}"
        sha = await _get_sliding_window_sha(rc)
        if sha is None:
            # Fallback: EVAL each call. Slower but functionally identical
            # and still atomic on the Redis side.
            try:
                result = await rc.eval(
                    _SLIDING_WINDOW_LUA, 1, rkey,
                    str(now_ms), str(cutoff_ms), str(self.max), str(ttl_s), member,
                )
            except Exception:
                raise
        else:
            try:
                result = await rc.evalsha(
                    sha, 1, rkey,
                    str(now_ms), str(cutoff_ms), str(self.max), str(ttl_s), member,
                )
            except Exception as exc:
                # NOSCRIPT (script flushed) → reload and retry once.
                if 'NOSCRIPT' in str(exc).upper():
                    global _SLIDING_WINDOW_SHA
                    _SLIDING_WINDOW_SHA = None
                    sha2 = await _get_sliding_window_sha(rc)
                    if sha2:
                        result = await rc.evalsha(
                            sha2, 1, rkey,
                            str(now_ms), str(cutoff_ms), str(self.max), str(ttl_s), member,
                        )
                    else:
                        result = await rc.eval(
                            _SLIDING_WINDOW_LUA, 1, rkey,
                            str(now_ms), str(cutoff_ms), str(self.max), str(ttl_s), member,
                        )
                else:
                    raise
        allowed = int(result[0]) == 1
        if allowed:
            return True, 0
        retry_after_ms = int(result[1] or 0)
        retry_after_s = max(1, (retry_after_ms + 999) // 1000)
        return False, retry_after_s

    async def _check_mongo(self, key: str) -> tuple[bool, int]:
        """Cross-instance sliding window backed by MongoDB Atlas.

        Used for `always_on` security-critical throttles where the
        per-instance local Redis cannot enforce a shared cap. Uses an
        insert-first, count-second, compensating-delete pattern so no
        transaction is required:

          1. Insert our hit doc unconditionally.
          2. Count hits in window for this key — includes our own.
          3. If count > max → delete our hit, return (False, retry).
          4. Else → return (True, 0).

        Under concurrent burst at the cap boundary, several callers may
        each insert + observe count > max + each delete their own. The
        net effect is fail-CLOSED (zero pass-through during the burst,
        slightly stricter than ideal) and never lets more than `max`
        slip through the window.
        """
        import time as _time
        import uuid as _uuid

        from core.database import _raw_db as _db
        rkey = self._rkey(key)
        now_ms = float(_time.time() * 1000)
        window_ms = float(self.window.total_seconds() * 1000)
        cutoff_ms = now_ms - window_ms
        expires_at = datetime.utcfromtimestamp(
            (now_ms + window_ms + 5000) / 1000.0
        )
        doc_id = f"{int(now_ms)}:{_uuid.uuid4().hex[:12]}"
        await _db.throttle_hits.insert_one({
            "_id": doc_id,
            "key": rkey,
            "score": now_ms,
            "expires_at": expires_at,
        })
        count = await _db.throttle_hits.count_documents({
            "key": rkey,
            "score": {"$gt": cutoff_ms},
        })
        if count > self.max:
            # Over budget — compensate our insert and report retry.
            try:
                await _db.throttle_hits.delete_one({"_id": doc_id})
            except Exception:
                pass
            oldest = await _db.throttle_hits.find_one(
                {"key": rkey, "score": {"$gt": cutoff_ms}},
                sort=[("score", 1)],
                projection={"score": 1},
            )
            if oldest:
                retry_ms = oldest["score"] + window_ms - now_ms
            else:
                retry_ms = window_ms
            retry_s = max(1, int((retry_ms + 999) // 1000))
            return False, retry_s
        return True, 0

    async def check(self, key: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds). Records the hit when allowed."""
        # F8AH P0 follow-up — security-critical (`always_on`) throttles MUST
        # use the cross-instance Mongo backend. The local Redis path is
        # per-deployment-instance under Replit autoscale, so a multi-
        # instance fan-out dilutes the cap. Mongo Atlas is shared and
        # the only backend that gives the production guarantee these
        # throttles are documented to provide.
        if self.always_on:
            try:
                if await _ensure_mongo_throttle_indexes():
                    return await self._check_mongo(key)
                else:
                    # CI 2026-05-28 NO-GO P0 — sessiz fall-through bug'ı.
                    # `always_on` throttle Mongo backend'i çağıramazsa per-
                    # container yedeğe düşer; autoscale altında bu dilution
                    # demektir (cap=15 ama 3 container = effective 45).
                    # Production'da Sentry yakalasın diye ERROR seviyesi.
                    logger.error(
                        "throttle_mongo_backend_unavailable",
                        extra={"throttle_name": self.name, "key_prefix": key.split(":")[0] if ":" in key else "?"},
                    )
            except Exception as exc:
                # Mongo hiccup — fall through to Redis/in-memory below
                # so the auth surface stays available. The throttle is
                # weaker for the duration of the outage but never blocks
                # legitimate traffic with a 503. Structured log so Sentry
                # ve drill RCA için root cause görünür olur (önceden bare
                # `except: pass` idi, 98C D / 98D B drill bypass'ında bug
                # tamamen gizli kaldı).
                logger.error(
                    "throttle_mongo_check_failed",
                    extra={
                        "throttle_name": self.name,
                        "exc_type": type(exc).__name__,
                        "exc_msg": str(exc)[:200],
                    },
                    exc_info=False,
                )
        rc = await _get_redis()
        if rc is not None:
            try:
                return await self._check_redis(rc, key)
            except Exception as exc:
                # Redis hiccup → fall through to in-memory (per-process) path
                # so the auth surface stays available. We accept that the cap
                # temporarily becomes per-process during the outage; this
                # matches the pre-F8AH behaviour and is fail-OPEN by design.
                # Architect-flagged: a dying connection would otherwise cause
                # `_REDIS_CLIENT` to keep returning the dead handle forever.
                # Clear the cache + arm the backoff timer so `_get_redis()`
                # attempts reconnection on the next call after the window.
                logger.warning(
                    "throttle_redis_check_failed",
                    extra={
                        "throttle_name": self.name,
                        "exc_type": type(exc).__name__,
                        "exc_msg": str(exc)[:200],
                    },
                )
                _invalidate_redis()
        async with self._lock:
            now = datetime.utcnow()
            cutoff = now - self.window
            dq = self._hits.setdefault(key, deque())
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self.max:
                retry_after = int((dq[0] + self.window - now).total_seconds()) + 1
                return False, max(1, retry_after)
            dq.append(now)
            # Lightweight GC to keep map bounded under spray attacks.
            if len(self._hits) > 10_000:
                self._hits = {k: v for k, v in self._hits.items() if v and v[-1] > cutoff}
            return True, 0

    async def reset(self, key: str) -> None:
        rkey = self._rkey(key)
        # always_on security-critical throttles record their hits in the
        # shared Mongo `throttle_hits` collection (see check/_check_mongo),
        # NOT in Redis or the per-process deque. The success-path drain MUST
        # clear that backend too — otherwise reset() is a silent no-op
        # against the real counter store and a legitimate user who mistyped
        # before authenticating stays one wrong attempt away from a 429
        # lockout for the rest of the window (the (cap+1)th attempt trips
        # immediately because the pre-success failures were never cleared).
        # Mirror check()'s backend selection so the drain reaches wherever
        # the hits actually live. Best-effort + structured log: a Mongo
        # hiccup must never make a successful auth raise.
        if self.always_on:
            try:
                from core.database import _raw_db as _db
                await _db.throttle_hits.delete_many({"key": rkey})
            except Exception as exc:
                logger.error(
                    "throttle_mongo_reset_failed",
                    extra={
                        "throttle_name": self.name,
                        "exc_type": type(exc).__name__,
                        "exc_msg": str(exc)[:200],
                    },
                    exc_info=False,
                )
        rc = await _get_redis()
        if rc is not None:
            try:
                await rc.delete(rkey)
            except Exception:
                # Same invalidation policy as check(): a dead client must
                # be cleared so the next call attempts reconnection rather
                # than retrying against the broken handle indefinitely.
                _invalidate_redis()
        async with self._lock:
            self._hits.pop(key, None)


def client_ip(request: Request) -> str:
    """Resolve client IP, honouring the Replit edge proxy.

    Architect-flagged bypass risk (v38): naively trusting the FIRST hop of
    `X-Forwarded-For` lets a malicious client send `X-Forwarded-For: 1.2.3.4`
    and have the throttle key it. The Replit edge proxy APPENDS the real
    peer IP at the END of the chain, so the rightmost hop is the only entry
    that originated inside the trust boundary. We use that.

    If no XFF is present (direct loopback dev / non-proxied path), fall back
    to the raw socket peer.
    """
    if TRUST_PROXY:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                return parts[-1]  # rightmost = trusted edge-appended peer
    return request.client.host if request.client else "unknown"


def normalize_identity(value: str | None) -> str:
    """Canonical form for account-identity throttle keys.

    Architect-flagged bypass risk (v38): `lower()` alone lets attackers
    evade per-account lockout via `"alice "`, `" alice"`, `"ALICE"` or
    Unicode look-alikes (`"alıce"`, `"Ａｌｉｃｅ"`). We apply
    `strip + NFKC + casefold` so visually-equivalent identifiers map to
    the same throttle bucket.
    """
    if not value:
        return ""
    return unicodedata.normalize("NFKC", value).strip().casefold()


# ── Throttle policies (conservative, can be tuned per tenant tier later) ──
# WATCH E#11 (Run #204 rate_limit_boundary P2 "no 429 observed on auth_login
# burst") — LOGIN_IP/LOGIN_ACCOUNT were the LAST brute-force-critical login
# surfaces still on the non-always_on (Redis→in-memory) backend while every
# peer (AGENCY_LOGIN_*, VENDOR_LOGIN_*, CASHIER_*, TWOFA_*, RESET_CODE_*) had
# already been moved to always_on=True (Mongo-backed, cross-instance) by the
# F8AH P0 / Task-55 waves. Under Replit autoscale (deploymentTarget=autoscale)
# the per-instance Redis (localhost) / per-process in-memory deque only ever
# saw a fraction of a fan-out burst, so a 60-request wrong-credential spray
# distributed across N instances hit each counter with ~60/N < cap(20) and
# NEVER tripped the 429 — exactly the systemic dilution documented at the top
# of this module for the 98C-D / 98D-B drills. Promoting these two to
# always_on routes them through the shared Mongo `throttle_hits` window so the
# cap is enforced once across all instances. This does NOT weaken auth: the
# login router keeps its verify-first → drain-on-success → record-on-fail
# ordering (Task-137), so wrong creds still 401, correct creds never accumulate
# a hit, and a legitimate user who mistyped is still drained on success. Stable
# name= so the Mongo/Redis key namespace can't drift with instance ordering.
LOGIN_IP = SlidingWindowThrottle(
    max_requests=20, window_seconds=60, always_on=True, name="login_ip"
)
LOGIN_ACCOUNT = SlidingWindowThrottle(
    max_requests=10, window_seconds=300, always_on=True, name="login_account"
)
FORGOT_PW_EMAIL = SlidingWindowThrottle(max_requests=3, window_seconds=600)
FORGOT_PW_IP = SlidingWindowThrottle(max_requests=10, window_seconds=600)
RESET_TOKEN_IP = SlidingWindowThrottle(max_requests=10, window_seconds=60)
TWOFA_VERIFY_IP = SlidingWindowThrottle(max_requests=15, window_seconds=60, always_on=True)
# F8AH P0 follow-up — per-IP throttle is bypassed by rotating-egress
# attackers (CDN, mobile carrier NAT, GitHub Actions runners, Tor exits).
# A per-user-id throttle (keyed by the JWT-trusted `user_id` claim inside
# the challenge_token) survives IP rotation because the attacker can't
# change WHICH ACCOUNT they're attacking without obtaining a fresh
# challenge for that account — and challenges are single-use, so the
# rate is bounded by login → challenge → verify per account anyway.
# This is the real-world brute-force protection layer; IP throttle is
# kept as defense-in-depth against garbage / pre-decode flooding.
TWOFA_VERIFY_USER = SlidingWindowThrottle(max_requests=15, window_seconds=60, always_on=True)

# v48 (Bug CE) — sensitive authenticated password/2FA endpoints. These routes
# verify the caller's CURRENT password (or current TOTP) but, being
# authenticated, were skipped by the v38 unauthenticated-throttle wave. A
# stolen access_token (XSS, public terminal, etc.) could therefore brute-force
# the password through `/auth/change-password` at bcrypt-throttled speed only,
# completely bypassing `LOGIN_ACCOUNT` lockout. Same exposure on
# `/2fa/disable` (password verify) and `/2fa/regenerate-backup-codes` (TOTP
# replay surface). Per-user-id sliding window: a few attempts per 15 min is
# plenty for a legitimate user yet kills credential dictionary attacks.
SENSITIVE_AUTH_USER = SlidingWindowThrottle(max_requests=5, window_seconds=900, always_on=True)

# v54 (Bug CO) — `/auth/register`, `/auth/register-guest`,
# `/auth/request-verification` previously had ZERO throttle, enabling:
#   - unbounded tenant creation (Mongo storage abuse, hotel_id namespace
#     exhaustion via `_generate_unique_hotel_id` collision pressure),
#   - email enumeration (existing → 400 "already registered", new → 200
#     + token; attacker walks a candidate list to harvest user inventory),
#   - email-bomb / Resend cost amplification (each request-verification
#     fires a real outbound mail to attacker-supplied address).
# REGISTER_IP caps per-IP creation rate (5 / 10 min; legitimate signup is
# a once-per-life event). REGISTER_EMAIL caps per-email rate (1 / 10 min;
# bucketed by NFKC casefold so look-alike bypass blocked).
REGISTER_IP = SlidingWindowThrottle(max_requests=5, window_seconds=600)
REGISTER_EMAIL = SlidingWindowThrottle(max_requests=1, window_seconds=600)

# v54 (Bug CO) — `/auth/verify-email` accepts a 6-digit code with NO
# attempt counter and NO per-email throttle. 1M code space + ~1000 req/s
# = ~17min full sweep per pending verification window (15 min). Combined
# with attempt-counter enforcement on the verification_codes doc itself,
# this 5-attempts-per-15-min throttle pushes effective brute-force to
# centuries.
VERIFY_CODE_EMAIL = SlidingWindowThrottle(max_requests=5, window_seconds=900, always_on=True)

# Task-170 (Bug AY) — `/auth/reset-password` (code-based legacy path) had NO
# throttle, making the 6-digit numeric code (900 000 possibilities) trivially
# brute-forceable within the 30-minute expiry window via online spraying.
# Two sliding-window layers here plus a per-record attempt counter enforced
# inside the router (max 5 wrong guesses → record invalidated) combine to
# make full-space enumeration infeasible even across distributed attackers:
#   - RESET_CODE_IP:    10 attempts / 60 s  — kills per-IP parallel spray.
#   - RESET_CODE_EMAIL: 10 attempts / 30 min — matches the code expiry window,
#                       caps total guesses per issued code to ≤10 across all IPs.
RESET_CODE_IP = SlidingWindowThrottle(max_requests=10, window_seconds=60, always_on=True)
RESET_CODE_EMAIL = SlidingWindowThrottle(max_requests=10, window_seconds=1800, always_on=True)

# Task-51 — `/api/cashier/handover-shift` accepts (target_email, target_password)
# and bcrypt-verifies the password before transferring the open cashier shift.
# Without a throttle this is a financial PIN-equivalent gate that an attacker
# holding a stolen staff access_token can brute-force at bcrypt-throttled
# speed against any peer staff account in the same tenant — completely
# bypassing the login-side `LOGIN_ACCOUNT` lockout (which only counts
# `/api/auth/login` attempts). The F9C mobile-cashier stress spec (test L)
# probes this surface and expects 429 by the 7th wrong-credential attempt.
#
# Per-user-id layer: JWT-trusted `current_user.id` of the operator initiating
#   handover (IP-rotation immune; the attacker can't change which session is
#   driving the brute-force without re-stealing the access_token).
# Per-IP layer: defense-in-depth against credential-spraying tooling that
#   could share a stolen token across many peer accounts in parallel.
# always_on=True so the dev escape hatch (DISABLE_AUTH_THROTTLE) cannot mask
# the protection in stress runs or production smoke tests.
CASHIER_HANDOVER_USER = SlidingWindowThrottle(
    max_requests=6, window_seconds=900, always_on=True, name="cashier_handover_user"
)
CASHIER_HANDOVER_IP = SlidingWindowThrottle(
    max_requests=6, window_seconds=900, always_on=True, name="cashier_handover_ip"
)

# Task-120 — `/api/cashier/peer-verify` is the mobile cashier PIN re-auth gate
# (front-desk terminals every shift). Same financial-PIN-equivalent exposure as
# the handover gate: an unattended terminal with a stolen access_token can be
# brute-forced one tap at a time without any back-off. Wires the same Mongo-
# backed sliding-window pattern as CASHIER_HANDOVER_* so the protection is
# cross-instance and survives multi-replica fan-out.
#
# Cap is 10 (vs handover's 6) because the peer-verify gate is the routine
# every-shift PIN screen where legitimate operators occasionally mistype a
# digit, while handover is rarer/more deliberate. The 11th wrong attempt in
# the window returns 429 — matches the regression probe in spec 98 test L.
# always_on=True so DISABLE_AUTH_THROTTLE cannot mask the protection in
# stress runs or production smoke tests.
CASHIER_PEER_VERIFY_USER = SlidingWindowThrottle(
    max_requests=10, window_seconds=900, always_on=True, name="cashier_peer_verify_user"
)
CASHIER_PEER_VERIFY_IP = SlidingWindowThrottle(
    max_requests=10, window_seconds=900, always_on=True, name="cashier_peer_verify_ip"
)

# Task-55 — peer login surfaces (`/api/agency-portal/auth/login`,
# `/api/supplies-market/vendor/login`) verify a staff/vendor password with
# bcrypt but were never wired to LOGIN_IP/LOGIN_ACCOUNT. That left two
# brute-force gaps with identical shape to the main login:
#
#   * agency_login accepts super_admin AND agency_admin/agency_agent
#     credentials (see agency_portal.py:507-514). An attacker can
#     dictionary-attack ANY staff account (incl. super-admin) through
#     this endpoint at bcrypt-throttled speed, bypassing the
#     LOGIN_ACCOUNT counter entirely.
#   * vendor_login is unauth but unbounded, enabling vendor-account
#     credential spraying.
#
# Per-IP layer: kills naive single-attacker parallel spray.
# Per-account layer (NFKC casefold-bucketed email): survives IP rotation
#   and caps total guesses against a given account across all sources.
# always_on=True so DISABLE_AUTH_THROTTLE cannot mask the protection in
# stress/pen runs or production smoke tests (matches the task-51 +
# SENSITIVE_AUTH_USER doctrine).
AGENCY_LOGIN_IP = SlidingWindowThrottle(
    max_requests=20, window_seconds=60, always_on=True, name="agency_login_ip"
)
AGENCY_LOGIN_ACCOUNT = SlidingWindowThrottle(
    max_requests=10, window_seconds=300, always_on=True, name="agency_login_account"
)
VENDOR_LOGIN_IP = SlidingWindowThrottle(
    max_requests=20, window_seconds=60, always_on=True, name="vendor_login_ip"
)
VENDOR_LOGIN_ACCOUNT = SlidingWindowThrottle(
    max_requests=10, window_seconds=300, always_on=True, name="vendor_login_account"
)


async def enforce(throttle: SlidingWindowThrottle, key: str, label: str = "istek") -> None:
    """Raise 429 with a Turkish, non-technical message and Retry-After header.

    DEV/TEST ESCAPE HATCH: When `DISABLE_AUTH_THROTTLE=1` is set the throttle is
    skipped entirely. This is **off by default** so production deployments stay
    protected; the local dev start.sh enables it so per-class pytest fixtures
    that re-login many times don't cascade-fail with 429.

    Hard production guard: even if `DISABLE_AUTH_THROTTLE=1` somehow leaks into
    a production env, it is IGNORED unless `APP_ENV` / `ENVIRONMENT` is dev/test.
    """
    import os as _os
    # F8AG P0 fix — `always_on` throttles (e.g. TWOFA_VERIFY_IP) are never
    # bypassed by the dev escape hatch. Brute-force-critical surfaces must
    # keep their rate limit in every environment so stress/penetration
    # tests measure the real production guarantee.
    if not getattr(throttle, "always_on", False) and _os.environ.get("DISABLE_AUTH_THROTTLE") == "1":
        env = (_os.environ.get("APP_ENV") or _os.environ.get("ENVIRONMENT") or "development").lower()
        if env in ("development", "dev", "test", "testing", "local"):
            return
    ok, retry_after = await throttle.check(key)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail=f"Çok fazla {label}. Lütfen {retry_after} saniye sonra tekrar deneyin.",
            headers={"Retry-After": str(retry_after)},
        )
