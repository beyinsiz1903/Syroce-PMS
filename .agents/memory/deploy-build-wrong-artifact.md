---
name: Main-app deploy build pointed at the wrong artifact
description: The gce/VM deployment build was set to the Expo mobile export instead of the React frontend it actually serves, causing publish-build failures.
---

The main-app deployment (Reserved VM / gce, run = `backend/start.sh`) serves the
committed React `frontend/build` (FastAPI `app.py` -> `FRONTEND_BUILD_DIR`,
default `frontend/build`). It does NOT serve `mobile/dist`.

The deployment `build` command had been set to `bash mobile/build-web.sh`, which
runs `npx expo export -p web` into `mobile/dist`. That script's own header says
it is for a SEPARATE static repl, not the main app. Symptoms: deployment build
fails to publish (expo export is heavy/flaky), while the artifact it produces is
irrelevant to what the backend serves.

**Fix (preferred):** make the deployment `build` a NO-OP and let `backend/start.sh`
serve the committed `frontend/build`. `frontend/.gitignore` documents that the build
output is tracked on purpose so deploy packaging ships it WITHOUT a deploy-time
build. A deploy-time `yarn install && yarn build` re-introduces the heavy/flaky
install step for zero benefit (and on autoscale gets SIGKILLed / dropped). Set it
via `deployConfig()` (direct `.replit` edits are blocked); keep target `vm` and the
existing `backend/start.sh` run command.

**Stale-build trap (must do before publish):** the committed `frontend/build` can
lag `frontend/src` by a commit or two (e.g. a merge changes index.html /
ErrorBoundary / lazyWithPreload chunk-load resilience but nobody re-ran the build).
A no-op deploy build then ships a stale SPA. Before telling Murat to publish, run
`cd frontend && yarn build` (~10s, node_modules already present) and let the
task-end auto-commit capture it. Verify: `frontend/build` has ZERO `localhost:8000`
(that string is the MOBILE `client.ts` fallback, never in a React build) and `/`
serves the React "Smart reload guard" shell with NO `expo-reset` marker.

**Why live can still serve mobile after the fix:** `primaryUrl` keeps serving the
last SUCCESSFUL build, so a string of failed/old publishes (flaky mobile build) can
leave a stale mobile artifact live even though the current config is correct. The
fix only takes effect when Murat republishes; a browser hard-refresh may be needed
for the cached `index.html`.

**How to apply:** if the deploy shows the wrong app or a publish-build fails, check
`[deployment].build` is NOT `mobile/build-web.sh`; set it no-op, rebuild
`frontend/build`, then republish. The backend serves the React `frontend/` vite
build, never the mobile expo export.
