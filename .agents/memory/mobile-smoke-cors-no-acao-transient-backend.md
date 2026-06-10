---
name: Mobile smoke "No ACAO" = transient backend-unreachable, not a CORS/code bug
description: How to triage a mobile-smoke guest CORS "No Access-Control-Allow-Origin" failure before assuming a backend 500 or CORS misconfig.
---

A mobile-smoke `consoleErrors` failure of the form
`blocked by CORS policy: No 'Access-Control-Allow-Origin' header` (+ `net::ERR_FAILED`)
against the deployed backend is almost always a **transient backend-unreachable
window** (the Replit edge proxy returns a CORS-less 5xx while the VM is
restarting / being republished / crash-looping), NOT a handler 500 and NOT a
CORS-config bug.

**Why this is the default conclusion:**
- CORSMiddleware is the OUTERMOST middleware (registered LAST in `server.py`),
  so it wraps every inner layer. A handler 500, a rate-limit 429, an
  entitlement reject, even the readiness/warm-up 503 gate (`_n_gate` in
  `app.py`, added via `@app.middleware("http")` so it is the INNERMOST user
  middleware) all pass back OUT through CORS → they DO carry ACAO. The only
  thing that can answer a request without ACAO is something OUTSIDE the FastAPI
  app entirely = the platform edge proxy when the backend process is down.
- A handler 500 reaches the browser as a readable 500 WITH ACAO (not a CORS
  error). So "browser reports CORS error" ⇒ the response never went through the
  app at all.

**How to apply (triage order, before touching code):**
1. Live-probe the deployed backend read-only with an `Origin` header:
   OPTIONS preflight + the failing POST/GET. If they return 2xx/401 WITH ACAO
   now, the endpoint and CORS are healthy → the CI error was transient.
   (Header check must be case-insensitive: `getheaders()` preserves original
   case, so match `k.lower()=="access-control-allow-origin"`.)
2. Check whether MULTIPLE distinct endpoints failed no-ACAO in the SAME test
   (e.g. refresh-token AND guest/bookings, including its preflight). Backend-wide
   simultaneous no-ACAO = process unreachable, not an endpoint bug.
3. Check flakiness: if a sibling test passed on retry, it's a blip.
4. Recommend re-running the CI. If it recurs CONSISTENTLY on the same portion,
   THEN it's backend instability (crash/OOM/health-check restart) worth deep
   deploy-log investigation — not a CORS or refresh-token code change.

**Trap that wasted a prior session:** the symptom was misdiagnosed as a "TRUE
500 from refresh-token's unprotected `audit_logs.insert_one`" (by analogy to
login's `_safe_audit`). A local guest repro (register-guest → refresh-token)
returned 200, and a live prod repro returned 200+ACAO — the endpoint was never
500-ing. Wrapping the audit write would have been a no-op "fix". Verify the
hypothesis with a real repro / live probe FIRST.

Aside (by-design, not the bug): `/api/guest/bookings` returns 401
"Authentication failed" WITH ACAO for a fresh self-registered guest
(tenant_id=None, no linked booking). That 401 is a normal HTTP response, not a
console error, so it does not fail the render-only smoke.
