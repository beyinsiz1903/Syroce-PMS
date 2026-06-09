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

**Why:** the mobile static host has no API, so pointing mobile config at itself
silently breaks login + smoke even though a healthy backend exists elsewhere.

**CORS:** mobile is cross-origin to the backend, so the mobile origin
(`https://emergent-yeni-uygulama-1.replit.app`) MUST be in `backend/server.py`
`_always_allowed` (explicit single host, per the Bug AL note — never `*.replit.app`
regex). The backend's own -syroce origin being listed does NOT cover the mobile
host. Verify live: OPTIONS preflight must return `Access-Control-Allow-Origin`
for the mobile origin. The CORS fix only takes effect when the -syroce backend
deploy runs the updated code (or has `CORS_ORIGINS` env including the mobile host).
