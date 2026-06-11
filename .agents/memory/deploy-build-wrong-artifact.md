---
name: Two-repl deploy topology — agent's repl = VM backend (-1 host), copy repl = mobile static (-syroce host)
description: This GitHub repo deploys from TWO Replit repls sharing one origin. The agent's repl owns the -1 slot = Reserved VM serving FastAPI backend + React SPA. A SEPARATE copy repl owns the -syroce slot = static Expo mobile. GitHub merges drift the agent-repl's [deployment] block to mobile/static — re-assert vm.
---

This repo (`github.com/beyinsiz1903/emergent-yeni-uygulama`, branch `main`) is
deployed from **two separate Replit repls** that share the same GitHub origin.
Anchor on the HOSTNAME, never on "this/other repl" (that label kept getting
inverted in older notes and caused a near-miss that would have flipped the
backend to mobile/static):

- **`https://emergent-yeni-uygulama-1.replit.app`** — **Reserved VM**, serves the
  FastAPI backend **and** the React SPA (`frontend/build`, via FastAPI
  `FRONTEND_BUILD_DIR`). `/api/health/` → `200 {"service":"hotel_pms"}`. This is
  the only live backend. **The agent's working repl OWNS this slot** — confirmed
  2026-06-11 by `getDeploymentInfo()` (primaryUrl = this `-1` URL, type `vm`,
  healthy) AND by the operator ("bu deployment = Ana PMS backend; mobil ayrı
  kopya repl'de"). So `deployConfig` here MUST be `vm`, NOT static/mobile.
- **`https://emergent-yeni-uygulama-1-syroce.replit.app`** — **static**, serves the
  Expo **mobile** web bundle only (`mobile/build-web.sh` → `mobile/dist`). No
  backend; `/api/*` 404s (react-native-web `<!DOCTYPE html>` 404.html). A SEPARATE
  "copy" Replit project owns this slot — the operator manages mobile from there.

**Correct VM config for the agent's repl (.replit `[deployment]`):**
`deploymentTarget="vm"`,
`build=["bash","-c","cd frontend && yarn install --frozen-lockfile && yarn build"]`,
`run=["bash","-c","PYTHON_BIN=/home/runner/workspace/.venv/bin/python exec bash backend/start.sh"]`,
no `publicDir`. `yarn build` passes (~1m40s); VM has the disk for it (autoscale
SIGKILLed on the heavy ML install — see syroce-deploy-target-vm).

**The drift trap (why this keeps breaking):** GitHub merges/syncs from the
mobile-dev/copy repl drag the `.replit` `[deployment]` block along, silently
flipping the agent-repl's slot to the mobile/static config
(`deploymentTarget="static"`, `build=["bash","mobile/build-web.sh"]`,
`publicDir="mobile/dist"`). The LIVE deploy keeps serving the last good VM build,
so nothing looks broken until the next republish — which would then publish the
mobile bundle onto the backend slot and break login/API.
**How to apply:** after every GitHub sync, re-check `.replit` `[deployment]`; if
it shows static/`mobile/build-web.sh`/`mobile/dist`, restore the VM config above
(use git history — the block just before the drift commit is the known-good VM
config). Verify with `getDeploymentInfo()` (type should be `vm`, primaryUrl the
`-1` host) and `curl .../api/health/` → `hotel_pms`.

**Mobile-side note (the -syroce copy repl only):** the mobile bundle bakes
`EXPO_PUBLIC_API_URL`/`EXPO_PUBLIC_QUICKID_URL` at BUILD time; they MUST point at
the `-1` backend host, never at the mobile host itself (self-pointing → every
`/api/*` 404s → login `request_failed`). The backend already allows the mobile
origin in CORS (explicit single host, not `*.replit.app`).
