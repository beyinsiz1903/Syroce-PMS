---
name: CORS must be the outermost middleware
description: A rate-limit 429 (or any inner short-circuit) reaches a cross-origin client as a status-0 network failure unless CORS wraps it.
---

When a browser client and the API are on different origins, an inner-middleware
short-circuit response (rate-limit 429, upload-guard 413, etc.) that is emitted
WITHOUT `Access-Control-Allow-Origin` is blocked by the browser and surfaces to
the app as a network failure (fetch status 0 / "cannot reach server"), NOT as a
readable 429. This silently cascades e2e matrices and confuses real users.

**Why:** Starlette/FastAPI wraps middleware in REVERSE registration order — the
LAST `add_middleware` call is the OUTERMOST layer. If the rate limiter is
registered after CORS, its raw 429 escapes outside the CORS layer and loses the
header. As a bonus, CORS-outermost also answers `OPTIONS` preflights before they
reach the rate limiter, so preflights stop burning the auth bucket.

**How to apply:**
- Register `CORSMiddleware` LAST so it is outermost; it then decorates every
  inner response (429/413/500) with the CORS headers.
- This does NOT change the relative order of the inner layers (rate-limit vs
  entitlement vs upload-guard), so there is no DoS/ordering regression and no
  auth/origin posture change — keep the origin allowlist + credentials flags
  exactly as they were.
- Behavioral proof (429 actually carrying CORS headers) is only observable from
  a real cross-origin client / CI run; offline you can only confirm the
  registration order and a clean boot.
