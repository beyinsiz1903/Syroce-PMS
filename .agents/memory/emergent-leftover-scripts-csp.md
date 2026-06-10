---
name: Emergent-platform leftover scripts trip CSP and leak PII
description: Emergent-migrated apps carry index.html injections (emergent-main.js, rrweb, PostHog) that violate the backend CSP and record guest PII; remove them, don't allowlist; keep Sentry working via CSP.
---

Apps migrated off the Emergent platform (e.g. repo named like `emergent-*`) ship
three leftover `<script>` injections in `frontend/index.html` that are NOT
referenced anywhere in `frontend/src`:

- `assets.emergent.sh/scripts/emergent-main.js` — a remote loader (arbitrary
  third-party code execution under the SPA's `script-src`).
- two rrweb session recorders (`unpkg.com/rrweb` + a `*.cloudfront.net`
  rrweb-recorder), usually with a comment "added for the testing, do not remove".
- an inline PostHog snippet (`us.i.posthog.com`, hardcoded `phc_` public key).

Symptoms: the deployed app's console fills with CSP violations ("violates
script-src/connect-src", "Creating a worker from blob: violates ...") because the
backend CSP doesn't allow these origins.

**Fix: REMOVE them from `frontend/index.html`, do NOT allowlist them in the CSP.**
For a PII/KVKK-sensitive PMS, third-party session recording + analytics
auto-capture of guest interactions is a privacy/compliance liability, and the app
doesn't use them (grep `posthog|rrweb|emergent` in `frontend/src` = 0). Then
rebuild `frontend/build` (it's the committed artifact the backend serves).

**Sentry is different — it IS a real, configured feature** (`frontend/src/index.jsx`
inits Sentry + `replayIntegration`). Keep it and fix the CSP so it works:
- `connect-src` needs `https://*.sentry.io` (the wildcard matches the regional
  ingest host `o<id>.ingest.<region>.sentry.io` — CSP `*.` matches one or more
  subdomain labels).
- add `worker-src 'self' blob:` — Sentry's replay/compression worker is created
  from a `blob:` URL; with no `worker-src` it falls back to `script-src` (no
  `blob:`) and is blocked. The SDK itself is bundled (served from `'self'`), so no
  `script-src` change is needed.

**Where the served CSP lives:** `backend/infra/security_headers.py`
`SecurityHeadersMiddleware` DEFAULT CSP — it is registered in
`backend/bootstrap/middleware_registry.py` with NO kwargs, so the default string
is what the SPA gets. The separate `DOC_CSP` is path-scoped to
`/api/docs|redoc|openapi.json` only; don't edit it for SPA issues. CORS is
unrelated and lives in `backend/server.py` — don't touch it here.

**Why:** removing unused trackers beats allowlisting them (smaller attack surface
+ no guest-PII egress), while error monitoring you deliberately configured must be
explicitly permitted by CSP or it silently breaks in production. Pre-existing
`script-src 'unsafe-inline' 'unsafe-eval'` and `connect-src ws: wss:` remain and
predate this; tightening them needs a nonce/hash strategy (separate work).
