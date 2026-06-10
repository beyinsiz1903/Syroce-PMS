---
name: Static assets drain the rate-limit budget
description: Why a published SPA can 429 on "/" — a global limiter counting static-asset requests against the per-IP anonymous bucket — and how to exempt them safely.
---

# Static assets must be exempt from the global rate limiter

**Symptom:** the published backend serves the SPA but `GET /` returns HTTP 429
(`{"detail":"Rate limit exceeded...","limit":60,"remaining":0,"retry_after":60}`),
so the React app never boots. Looks like an auth/DoS limit but it is the static
shell being throttled.

**Root cause:** the global `EnhancedRateLimitMiddleware` is registered OUTERMOST
(before static serving), so it counts EVERY request — including the public static
SPA assets (index.html shell + hashed JS/CSS chunks + images/fonts) — against the
per-IP `anonymous` bucket. In production that bucket is small (60/min). A single
SPA page load fetches the shell plus ~35 hashed static files, so one load + one
refresh exhausts the per-IP budget and 429s persistently.

**Why it hides locally:** dev/test env (`REPL_ID` / `REPLIT_DEV_DOMAIN` / `CI`)
forces `is_test_env=True` → all buckets become 10000/min, so the static flood
never trips the limit. Only the production profile (`REPLIT_DEPLOYMENT=1`,
no test markers) exposes it.

**Fix:** exempt static serving BEFORE the limit check. Gate on `not _is_dynamic`
first (path does NOT start with `/api`, `/graphql`, `/ws`) so a dynamic endpoint
can never slip through, THEN bypass if path is `/` or starts with a static prefix
(`/js/`, `/assets/`, `/logos/`, `/landing/`) or its extension is in a static set
(mirror app.py's warm-up static-extension split). Leave `/api`/`/graphql`/`/ws`
and the auth (15/min) + anonymous-API (60/min) buckets untouched.

**How to apply:**
- Order matters: the dynamic-prefix check MUST come first, or `/api/x.json` would
  wrongly match the extension exemption and lose throttling.
- Do NOT exempt extension-less SPA deep-link routes — keep those counted (cheap
  but conservative for DoS).
- Keep the static-extension set in sync with the server's warm-up static split;
  if a dynamic route is ever mounted OUTSIDE `/api`/`/graphql`/`/ws` with a
  static-looking extension it would be unthrottled — re-audit then.
- Verify with the PROD profile, not locally: a unit test must clear the test-env
  vars and set `REPLIT_DEPLOYMENT=1`, assert `anonymous == (60,60)`, drive 200
  requests per static path (all 200) and assert anonymous `/api/*` still 429s
  after 60 from the SAME client IP (proves static consumed zero budget).

**Related:** CORS-must-be-outermost (cors-outermost-429-headers.md),
deployed-js-502-blank-stale-image.md (other "published SPA blank/broken" causes).
A published code fix here requires a REPUBLISH; the live deploy keeps old code.
