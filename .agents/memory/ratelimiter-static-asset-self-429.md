---
name: Rate limiter must exempt static SPA assets
description: Why the API rate limiter must only govern /api,/graphql,/ws — throttling static chunks self-429s a code-split SPA
---

# Rate limiter must exempt static SPA serving

The backend serves the React SPA build AND the API from one FastAPI app. The
`EnhancedRateLimitMiddleware` (in `backend/apm_middleware.py`) is an ASGI
limiter that wrapped EVERY path. Static JS/CSS chunks carry no `Authorization`
header, so they fall into the `anonymous` bucket (60/min in prod).

**Rule:** the limiter must rate-limit ONLY the dynamic API surface
(`/api`, `/graphql`, `/ws`); all other paths are static SPA serving and must
bypass.

**Why:** this app is heavily code-split — a single page load fetches dozens of
hashed `/js/*.js` chunks. With the limiter active on static paths, one normal
page load exhausts the shared anonymous 60/min bucket mid-load and the backend
429s the remaining chunks. The SPA then can't finish booting and the user
can't even reach the login form — it *looks* like "login is broken / rate
limited" even though `POST /api/auth/login` itself returns 200. Confirmed via
deployment logs: login 200, then a burst of `GET /js/*.js → 429`.

**How to apply:** keep the bypass in `__call__` right after the whitelist
skip. Do NOT "fix" this by raising the anonymous limit (that weakens real DoS
protection on /api) or by lowering auth throttles. The static-vs-dynamic split
mirrors the warm-up gate in `backend/app.py`. Regression test:
`backend/tests/test_rate_limiter_static_bypass.py`.

**Watch-out:** any future *dynamic/sensitive* route added OUTSIDE `/api`
becomes unthrottled by default under this rule — keep sensitive endpoints
under `/api`.

**Deploy note:** middleware change only takes effect in production after a
republish.
