---
name: Rate-limit must run before auth/token verification on public endpoints
description: Why a public endpoint's throttle never trips under an invalid-credential burst, and the doctrine-safe fix.
---

# Rate-limit ordering on public endpoints

On a public endpoint, run the per-IP (or per-resource+IP) rate-limit check
BEFORE token/credential verification. If verification runs first, an
invalid-token / wrong-password burst is rejected (403/401) and short-circuits
*before* the rate-limit counter ever increments — so the throttle never trips
and a DoS-sentinel burst probe observes "no 429" no matter how large the burst.

**Why:** the counter only counts requests that reach it. Auth-rejection paths
that precede it are invisible to the limiter. Observed on the Room QR public
submit (`room_qr_requests.public_submit_request`): `_verify_token` (garbage
token → 403) ran before `_rl_check`, so a 60-request garbage burst produced 60×
403 and 0× 429.

**How to apply:** reorder so the limiter runs first, keyed by data available
pre-auth (path params + client IP). This does NOT weaken auth — the token is
still verified immediately after and an invalid token still yields 403/401; it
only bounds repeated abuse against the verify path. Legit callers (valid
credential, under the cap) are unaffected. Keep the limiter fail-open on cache
outage so a cache hiccup never 503s the public surface. Verify live: a burst of
N > cap from one IP must yield (cap × auth-reject-code) + (N−cap × 429), 5xx=0,
and no DB writes (both reject paths must precede any insert).
