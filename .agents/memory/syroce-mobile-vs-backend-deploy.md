---
name: Syroce mobile vs web+backend deploy split
description: Two separate replit.app deploys (mobile static vs web+backend); mobile config must target the backend host, not itself.
---

Syroce runs as two SEPARATE Replit deploys with confusingly similar hostnames:

- `emergent-yeni-uygulama-1.replit.app` — the Expo **mobile** web static bundle
  (built by `mobile/build-web.sh` -> `mobile/dist`). NO backend here; `/api/*` 404s.
- `emergent-yeni-uygulama-1-syroce.replit.app` — the **web app + live FastAPI
  backend** (serves the React frontend AND `/api`). `/api/health/` -> 200,
  `/quickid/health` -> 200. Note `/api/health` (no trailing slash) 307-redirects.

The operator deploys/uses each from a different Replit project ("copy replit" =
the -syroce one). The web login is the rich `frontend/AuthPage.jsx` (Otel/Misafir,
blue circle logo); the mobile login is the simple `mobile/app/(auth)/login.tsx`.
Don't conflate a screenshot of one with the other.

**Rule:** anything the mobile bundle needs from the backend must point at the
**-syroce backend host**, never the mobile host:
- `mobile/build-web.sh`: `EXPO_PUBLIC_API_URL` / `EXPO_PUBLIC_QUICKID_URL` defaults.
- `.github/workflows/mobile-web-smoke.yml`: `api_url` default (pre-warm). A
  mobile-host default makes the pre-warm `/api/health` 404 — that exact misroute
  was the original "smoke 404" bug, NOT a missing backend.
- **Stress CI `E2E_BASE_URL`** (GitHub Actions secret; consumed by
  `playwright.stress.config.js` global-setup warmup + login). MUST be the
  -syroce backend host. If set to the mobile `-1` host the warmup hits `/health`
  → 404 for all 60 attempts ("gave up after 60 attempts") then login fails 404,
  and the ENTIRE stress suite dies in global-setup. That is the misroute, NOT a
  backend outage or a spec regression — the backend can be fully green elsewhere.

**Why:** the mobile static host has no API, so pointing mobile config at itself
silently breaks login + smoke even though a healthy backend exists elsewhere.

**Diagnostic signature (which host am I actually hitting?):** live GET `/health`
→ `200 application/json {"status":"healthy"}` = the -syroce backend; →
`404 text/html` SPA shell (`<!DOCTYPE html> <html lang="en"> <head> <meta
charset=…`) = the mobile static `-1` host (no API, serves its 404.html). Probe
BOTH hosts read-only before assuming the backend is down — a clean stable 404
(not 502/connection-refused) means a live but API-less host, i.e. a misroute.

**Copy-repl secrets gap (git-copied backend deploy):** the -syroce backend lives
in a SEPARATE Replit project that was created by git-copying. Secrets are NOT in
git, so a fresh copy boots its deploy on an EMPTY local Mongo and EVERY real login
returns 401 even though infra is fully green (health 200, CORS preflight passes,
bogus login = clean 401, no 500/timeout). Diagnose by logging the SAME real account
on the dev backend (this repl, Atlas) vs the -syroce deploy: dev 200+token but
deploy 401 PROVES the deploy is not on Atlas. Fix is operator-side on the COPY
repl's Secrets, then **Redeploy** (secret change needs a redeploy to take effect).
Minimum for login: `MONGO_ATLAS_URI` (real users), `CM_MASTER_KEY_CURRENT`
+ `CM_KEY_VERSION` (EXACT — email login lookup is a `_hash_email` blind-index HMAC
derived from this key; a wrong/dev-fallback key makes lookup miss => 401 even with
Mongo connected), and `JWT_SECRET`. DB_NAME not needed (start.sh defaults to
`syroce-pms` on Atlas). A mobile-smoke run with all `login -> group root` =
`waitForURL` timeouts is this same 401 (no redirect), not a UI bug.

**This repl's deploy slot IS the mobile static (`-1`) host** (operator-confirmed):
`.replit` [deployment] = `deploymentTarget="static"`, `build=["bash","mobile/build-web.sh"]`,
`publicDir="mobile/dist"`. The production PMS web+backend is a SEPARATE Replit project
(the `-syroce` one) — so `deployConfig` static HERE is correct and does NOT clobber the
PMS. (The older blanket "never deployConfig in the main repl" warning in
`mobile/build-web.sh` / expo memory assumed this repl held the PMS slot; for this `-1`
repl it does not.)

**Deploy-config drift → "Could not find public directory":** the [deployment] section
can silently drift off static (e.g. to `deploymentTarget="gce"` with the `publicDir`
line dropped). Publishing then fails with **"Could not find public directory"** because
a static publish needs `publicDir` and there's none (and `mobile/dist` is gitignored/empty
in the tree). Fix = `deployConfig({deploymentTarget:"static", build:["bash","mobile/build-web.sh"],
publicDir:"mobile/dist"})`. The leftover `run` line is harmless (static ignores `run`).
A static publish runs `build` first, then serves `publicDir`, so the empty tracked
`mobile/dist` is fine — the deploy builder regenerates it.

**CORS:** mobile is cross-origin to the backend, so the mobile origin
(`https://emergent-yeni-uygulama-1.replit.app`) MUST be in `backend/server.py`
`_always_allowed` (explicit single host, per the Bug AL note — never `*.replit.app`
regex). The backend's own -syroce origin being listed does NOT cover the mobile
host. Verify live: OPTIONS preflight must return `Access-Control-Allow-Origin`
for the mobile origin. The CORS fix only takes effect when the -syroce backend
deploy runs the updated code (or has `CORS_ORIGINS` env including the mobile host).

**Intermittent CORS in CI vs correct live preflight = cold-start transient:** a
mobile smoke step that FAILS once with "No 'Access-Control-Allow-Origin'" on an
`/api/*` fetch but PASSES on another run (Playwright "flaky"), while a live OPTIONS
preflight to the same path returns 200 + the header consistently, is NOT a code/CORS
gap. It is the autoscale -syroce deploy cold-starting during the CI window: an inner
503/5xx (warm-up) escapes WITHOUT CORS headers, so the browser reports it as a CORS
block. The allowlist is already correct — re-run (or keep the backend warm), do NOT
loosen the smoke's zero-console-error gate to swallow CORS errors (that hides real
cross-origin breakage).
