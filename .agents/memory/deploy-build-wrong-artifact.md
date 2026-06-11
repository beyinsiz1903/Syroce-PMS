---
name: Two-repl deploy topology (this repl = MOBILE static, other = VM backend/web)
description: This GitHub repo is deployed from TWO Replit repls. THIS repl is the static Expo mobile bundle; the OTHER repl is the VM that serves React web + FastAPI backend. Getting the deployment target wrong here breaks login.
---

This repo (`github.com/beyinsiz1903/emergent-yeni-uygulama`, branch `main`) is
deployed from **two separate Replit repls** that share the same GitHub origin.

- **OTHER repl — VM — `https://emergent-yeni-uygulama-1.replit.app`**
  Serves the React web app **and** the FastAPI backend. `/api/health/` returns
  `{"status":"healthy","service":"hotel_pms"}`. This is the only live backend.
- **THIS repl — static — `https://emergent-yeni-uygulama-1-syroce.replit.app`**
  Serves the **Expo mobile web bundle only** (`mobile/build-web.sh` → `mobile/dist`).
  No backend runs here. Deployment config: `deploymentTarget="static"`,
  `build=["bash","mobile/build-web.sh"]`, `publicDir="mobile/dist"`.

**Operator intent (authoritative):** THIS repl must stay the MOBILE static app.
Do NOT set it to `vm` — VM makes it serve the web site, which is the OTHER repl's
job ("vm olursa web sitesine yönlendirir ... diğer replit sayfam zaten vm"). An
earlier VM change here was wrong and was reverted.

**The login `request_failed` trap:** `mobile/build-web.sh` defaults
`EXPO_PUBLIC_API_URL` (and `EXPO_PUBLIC_QUICKID_URL`) to `...-syroce.replit.app`
— i.e. the mobile app points at ITSELF, which has no backend, so every `/api/*`
call 404s and login shows `request_failed`. EXPO_PUBLIC_* vars are baked into the
static bundle at BUILD time, so they must be set before the deploy build runs.
**Fix:** set `EXPO_PUBLIC_API_URL` + `EXPO_PUBLIC_QUICKID_URL` =
`https://emergent-yeni-uygulama-1.replit.app` in THIS repl's **production** env
(`setEnvVars(..., environment:"production")`), which overrides the script's
self-pointing default. Prefer the production env var over editing the script's
default, because the operator also pushes `mobile/build-web.sh` from a mobile-dev
repl and a GitHub merge can revert an in-file edit; the repl-scoped env var is not
in the shared code.

**CORS is already fine:** the VM backend allows the mobile origin — a preflight to
`-1/api/auth/login` with `Origin: https://...-syroce.replit.app` returns
`access-control-allow-origin: https://...-syroce.replit.app` + `allow-credentials:true`.
No cross-repl CORS change is needed (don't go chasing it).

**How to apply:** if THIS repl's published site shows `request_failed` on login or
serves a `react-native-web` bundle whose `/api/*` 404s, do NOT flip it to VM.
Confirm `deploymentTarget="static"` + `publicDir="mobile/dist"`, confirm THIS repl's
production `EXPO_PUBLIC_API_URL` points at the OTHER repl's VM URL, then have the
user republish. `curl https://emergent-yeni-uygulama-1.replit.app/api/health/`
should be the healthy `hotel_pms` backend; `-syroce` is mobile-only. Re-verify the
deployment target after every GitHub sync from the mobile-dev repl — merges drag
the `.replit` deployment block along.

**Note (for the OTHER/VM repl only):** there, build must be the React vite build
(`cd frontend && yarn build`, serves `frontend/build` via FastAPI `FRONTEND_BUILD_DIR`),
never `mobile/build-web.sh`. That rule is about the VM repl, not this one.
