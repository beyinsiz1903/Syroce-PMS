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
import os
import unicodedata
from collections import deque
from datetime import datetime, timedelta

from fastapi import HTTPException, Request

# When True, trust the rightmost X-Forwarded-For hop (Replit edge proxy
# appends the real peer IP at the END of the chain). When False, ignore XFF
# entirely and use the raw socket peer (safe for non-proxied environments
# where any XFF must be assumed attacker-controlled).
# Default True because production runs behind Replit's mTLS edge.
TRUST_PROXY = os.getenv("TRUST_PROXY", "1") == "1"


class SlidingWindowThrottle:
    """Per-key sliding window: at most `max_requests` per `window_seconds`."""

    def __init__(self, max_requests: int, window_seconds: int, *, always_on: bool = False):
        self.max = max_requests
        self.window = timedelta(seconds=window_seconds)
        self._hits: dict[str, deque[datetime]] = {}
        self._lock = asyncio.Lock()
        # F8AG P0 fix — when True, this throttle ignores DISABLE_AUTH_THROTTLE
        # regardless of APP_ENV. Used for brute-force-critical surfaces
        # (TOTP verify) where the dev escape hatch would otherwise mask the
        # absence of throttling in stress runs AND production smoke tests.
        self.always_on = always_on

    async def check(self, key: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds). Records the hit when allowed."""
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
LOGIN_IP = SlidingWindowThrottle(max_requests=20, window_seconds=60)
LOGIN_ACCOUNT = SlidingWindowThrottle(max_requests=10, window_seconds=300)
FORGOT_PW_EMAIL = SlidingWindowThrottle(max_requests=3, window_seconds=600)
FORGOT_PW_IP = SlidingWindowThrottle(max_requests=10, window_seconds=600)
RESET_TOKEN_IP = SlidingWindowThrottle(max_requests=10, window_seconds=60)
TWOFA_VERIFY_IP = SlidingWindowThrottle(max_requests=15, window_seconds=60, always_on=True)

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
