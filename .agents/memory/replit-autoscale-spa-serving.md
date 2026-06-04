---
name: Replit autoscale combined backend+SPA serving traps
description: Why a published autoscale app serves health JSON instead of the SPA at "/", and the two independent root causes (gitignored build dropped from the runtime image + explicit "/" route shadowing the SPA handler).
---

# Replit autoscale: backend-serves-SPA returns health JSON not the app

When one FastAPI service serves both the API and the built frontend on a single
autoscale URL, the published site can show only `{"status":"ok",...}` at `/`
while the build clearly succeeded. There are **two independent causes** — fixing
one without the other still leaves the root broken.

## Cause 1 — gitignored build output is dropped from the runtime image
The deploy build step runs `vite build` and produces the bundle (you can confirm
in `getDeploymentBuild(...).logs` — look for `✓ built in ...` and `build/...`
file listing). But Replit autoscale packaging ("Created Repl layer" in the build
log) **excludes gitignored paths**. If the build output dir is gitignored, it is
built and then dropped before runtime, so the backend never finds it.

**Diagnose:** build log shows the bundle built, yet a freshly-booted runtime
container still serves the JSON fallback. `git check-ignore -v <build_dir>` shows
the offending rule.

**Fix:** un-ignore the build output dir so it ships (e.g. remove `/build` from
`frontend/.gitignore`). Accepted tradeoff: build artifacts get tracked. Outputting
to a non-ignored dir works too, but anything you want in the autoscale image must
NOT be gitignored.

## Cause 2 — an explicit `GET "/"` route shadows the SPA fallback
A common pattern serves the SPA via a `@app.exception_handler(404)` that returns
`index.html` for non-API paths. But an explicit `@app.get("/")` health-probe route
(added so the autoscale `/` probe gets a cheap 200 during warm-up) **always handles
`/` and never 404s**, so the SPA handler never fires at root — users hitting `/`
get health JSON even when the build is present.

**Fix:** make the root route serve `index.html` when the build exists, and fall
back to health JSON only when absent. The HTML response is still a 200, so the
autoscale probe at `/` keeps passing; the warm-up middleware must keep allowing
`/`. Define the `frontend_build` path once and reuse it in both the root route and
the SPA block.

**Why:** the probe-200 requirement and the SPA-at-root requirement both target
`/`; serving `index.html` satisfies both. A stale "/ is intentionally not
registered" comment can hide that an explicit `/` route was later added.

## How to apply
- Verify the live root with `curl -w "%{content_type}"`: `text/html` = SPA served,
  `application/json` = still broken.
- After fixing code/gitignore, the user must **re-publish** — autoscale rebuilds
  and repackages; the agent cannot trigger it.
