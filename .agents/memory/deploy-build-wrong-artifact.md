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

**Fix:** point the deployment build at the frontend the backend actually serves:
`cd frontend && yarn install --frozen-lockfile && yarn build` (vite build, ~12s).
Change it via the deployment skill's `deployConfig()` — direct `.replit` edits are
blocked. Keep target `vm` and the existing `backend/start.sh` run command.

**Why:** the served build and the build step must match. Building an unrelated
(and flaky) target wastes the deploy and can fail the publish even though the app
itself is fine. `frontend/build` is committed (~414 files), so the run command can
serve it regardless, but the build step should regenerate the same artifact.

**How to apply:** if a publish-build fails, check that the `[deployment].build`
command produces the artifact the run command serves. For this repo that is the
React `frontend/` vite build, never the mobile expo export.
