---
name: Mobile (Expo Web) login waitForURL timeout = CORS preflight, not auth/UI
description: A browser-based mobile e2e login that times out on waitForURL is often a cross-origin CORS preflight rejection, not a broken login form or AuthGate.
---

# Mobile login waitForURL timeout = cross-origin CORS preflight reject

The Expo Web mobile app and the API backend are deployed as **two separate
replit.app subdomains** under the same project (e.g. app at
`<name>-syroce.replit.app`, API baked into the bundle via
`EXPO_PUBLIC_API_URL` pointing at `<name>.replit.app`). So every mobile API
call is **cross-origin** and gated by the backend's CORS allowlist.

**Symptom that misleads:** F10A mobile smoke fails with
`page.waitForURL: Timeout 30000ms exceeded` right after submitting the login
form — looks like a broken login form, AuthGate redirect, or testid drift.

**Real cause:** the browser's CORS **preflight** (OPTIONS) is rejected, so the
login POST never fires, no token, no redirect, waitForURL hangs.

**How to diagnose (read-only, no creds needed):**
- `curl -X POST <api>/api/auth/login -d '{bad creds}'` → if it returns proper
  401 JSON, the backend is healthy (not the problem).
- `curl -X OPTIONS <api>/api/auth/login -H "Origin: <mobile-origin>" -H
  "Access-Control-Request-Method: POST"` → Starlette returns **HTTP 400**
  with NO `access-control-allow-origin` header when the origin is disallowed
  (it still echoes allow-methods/headers/credentials/max-age, which is what
  fools you into thinking CORS is fine). Missing `allow-origin` = disallowed.

**Fix:** add the single explicit mobile prod origin to the backend CORS
allowlist (`_always_allowed` in `backend/server.py`) — NOT a wildcard
(`*.replit.app` regex is banned by the Bug AL hardening note: an attacker can
register evil.replit.app and ride credentials=true). Production hosts must be
enumerated explicitly via `_always_allowed` or the `CORS_ORIGINS` env.

**Why prefer CORS_ORIGINS long-term:** replit deploy hostnames can rotate;
hardcoding a deploy URL in source goes stale silently. Keep the explicit host
for immediate reliability but make `CORS_ORIGINS` the canonical mutable source.

**Verify:** restart backend, loopback `curl -X OPTIONS http://localhost:8000/...`
with the mobile Origin must return **200 + access-control-allow-origin: <origin>**.
The `8000-<domain>` public proxy may be unmapped in a dev session (returns the
"Run this app" placeholder) — use loopback for proof.

**Takes effect in prod only after the BACKEND deployment is REDEPLOYED**
(CORS middleware config is read at process start). The mobile smoke runs
against the live backend, so it keeps failing until that redeploy.
