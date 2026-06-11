---
name: Mobile vs web+backend deploy host mapping (corrected)
description: Two replit.app hosts with confusingly similar names. -1 = VM backend (web+API); -syroce = static mobile bundle. Mobile config/smoke/stress must target the -1 backend host. (Older revs had this mapping BACKWARDS.)
---

Syroce runs as two SEPARATE Replit deploys with confusingly similar hostnames.
**Verified live 2026-06-11 (do not invert):**

- `emergent-yeni-uygulama-1.replit.app` — the **web app + live FastAPI backend**
  (serves React `frontend/build` AND `/api`). `/api/health/` → `200 hotel_pms`.
  This is the slot the AGENT's repl deploys to (Reserved VM). See
  deploy-build-wrong-artifact for the full topology + drift trap.
- `emergent-yeni-uygulama-1-syroce.replit.app` — the Expo **mobile** web static
  bundle (`mobile/build-web.sh` → `mobile/dist`). NO backend; `/api/*` → `404`
  (react-native-web SPA shell / 404.html). A SEPARATE "copy" Replit project.

**Diagnostic signature (which host am I hitting?):** live GET `/api/health/`
→ `200 application/json {"service":"hotel_pms"}` = the **-1 backend**;
→ `404 text/html` react-native-web shell = the **-syroce mobile** host. Probe
read-only before assuming the backend is down — a clean stable 404 (not
502/connection-refused) is a live but API-less host, i.e. a misroute.

**Rule:** anything the mobile bundle needs from the backend must point at the
**-1 backend host**, never the -syroce mobile host:
- `mobile/build-web.sh`: `EXPO_PUBLIC_API_URL` / `EXPO_PUBLIC_QUICKID_URL` defaults
  (baked at build time).
- `.github/workflows/mobile-web-smoke.yml`: `api_url` default (pre-warm).
- **Stress CI `E2E_BASE_URL`** (GH Actions secret; `playwright.stress.config.js`
  global-setup warmup + login) MUST be the **-1 backend** host. Wrong host →
  warmup `/health` 404 ×60 ("gave up after 60 attempts") → login 404 → entire
  stress suite dies in global-setup. That is the misroute, NOT a backend outage
  or spec regression.

**Copy-repl secrets gap:** the -syroce mobile repl (and any git-copied backend
deploy) does NOT inherit secrets from git. A fresh copy boots on an EMPTY local
Mongo → every real login 401 even though infra is green (health 200, CORS ok,
bogus login = clean 401). Minimum login secrets on a copied BACKEND deploy:
`MONGO_ATLAS_URI`, `CM_MASTER_KEY_CURRENT` + `CM_KEY_VERSION` (EXACT — email
lookup is a `_hash_email` blind-index HMAC of this key; wrong key → lookup miss →
401), `JWT_SECRET`. Fix is operator-side Secrets on the copy repl, then Redeploy.

**CORS:** mobile is cross-origin to the backend, so the mobile origin
(`https://emergent-yeni-uygulama-1-syroce.replit.app`) MUST be in the backend's
`_always_allowed` (explicit single host, never `*.replit.app` regex). Verify live:
OPTIONS preflight returns `Access-Control-Allow-Origin` for the mobile origin.

**Intermittent CORS in CI vs correct live preflight = cold-start transient:** a
mobile smoke step failing once with "No 'Access-Control-Allow-Origin'" but passing
on re-run, while a live OPTIONS preflight returns the header consistently, is the
backend cold-starting (inner 503/5xx escapes WITHOUT CORS headers → browser
reports a CORS block). Allowlist is fine — re-run; do NOT loosen the smoke's
zero-console-error gate.

**Deploy-config drift → "Could not find public directory":** if the agent-repl's
`[deployment]` drifts off `vm` (e.g. to a static/`gce` variant with `publicDir`
dropped), a static publish fails with "Could not find public directory". Fix is
to restore the VM config (deploy-build-wrong-artifact), not to re-add a static
publicDir — this slot is the backend.
