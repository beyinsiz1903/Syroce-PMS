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

## Cause 3 — the warm-up 503 gate blocks the SPA's static bundles
Separate from Causes 1/2 (which serve health JSON at `/`), this one serves
`index.html` at `/` fine (200) but the page is a **blank white screen** because
the referenced `/js/*` and `/assets/*` bundles return **503
`{"status":"starting","detail":"Server is warming up"}`** with `Retry-After`.

The warm-up middleware (`_warmup_gate`) sheds all traffic while
`app.state.routes_ready=False`, allowing only `/health*`, `/favicon.ico`, and
exactly `/`. With `DEFER_STARTUP_BOOTSTRAP=1`, `routes_ready` flips True only
after **ALL** startup callbacks finish — including cache warming of every
booking + scheduler boot. On a cold start that heavy bootstrap can take many
minutes, so the SPA's JS/CSS stay 503 the whole time and the app never boots.

**Diagnose:** `curl /` is 200 HTML but `curl /js/<bundle>.js` and
`curl /assets/<file>.css` are `503 application/json` with body
`{"status":"starting",...}`; deployment logs show bootstrap still running
(cache_warmer / schedulers) long after `Application startup complete`.

**Fix:** add the eager static mounts' prefixes (`/js/`, `/assets/`, `/logos/`)
to the gate allow-list. They are public files with no DB/worker dependency, so
serving them during warm-up lets the SPA shell boot and render a loading/login
state. `/api`, `/ws`, `/graphql` stay gated (503, fail-closed) so no data is
served before readiness. Deep links (non-`/` HTML routes) still 503 during
warm-up — acceptable tradeoff; primary entry is `/`. Regression:
`backend/tests/test_warmup_gate_static_assets.py`.
**Why:** gating static bundles makes EVERY cold start a white screen for the
full (long) warm-up window; only dynamic/data routes need the readiness gate.

## Cause 4 — specific SPA chunks 502 "deployment could not be reached"
Distinct from Cause 3 (503 warm-up JSON). Here `/`, `/api/health`, the CSS, and
SOME `/js/*.js` return 200 (uvicorn alive), genuinely-missing files return a
clean app `404 application/json`, but the SPA entry chunk + most `/js/*.js`
return **502 `text/plain` "The deployment could not be reached"** (the Replit
edge, NOT the app). It is **deterministic per path and query-invariant**
(`?cb=1..N` all 502) — so it is NOT a content/size/timeout issue and NOT a
build-hash mismatch (a hash mismatch gives app 404, not edge 502).

**Diagnose:** the 35-byte `text/plain` "deployment could not be reached" body
== edge can't reach the instance for that request. Per-path-deterministic 200
vs 502 + clean 404 for nonexistent == multiple instances behind path-sticky
edge routing where some instances are unhealthy/crashed; each chunk URL hashes
to a good (200) or dead (502) instance. The repo build can be complete and
tracked and it still happens.

**Fix:** NOT a code change. Re-publish; for a stateful web+backend (local
Mongo/Redis + in-process workers) deploy on a **single-instance Reserved VM**
so there is no broken-instance-routing surface (see syroce-deploy-target-vm).
**Watch the config trap:** one repo, two deployments (mobile static vs
web+backend) share ONE `.replit [deployment]` block; `getDeploymentInfo()` only
reports the currently-configured one. If `.replit` is set to the static/mobile
deploy, a plain Publish re-pushes mobile and does NOT touch the broken
web+backend host — swap the block to the VM+backend config first.

**Follow-up (broken images, not white screen):** allow-listing only `/js`,
`/assets`, `/logos` is too narrow — the SPA boots but its logo and hero render
broken. The landing logo is a **root-level** file (`/syroce-logo.svg`) and the
hero lives under a **different prefix** (`/landing/hero-hotel*.webp|png`), so
both still 503 during warm-up. Widen the allow-list to the `/landing/` prefix
AND any **root-level static extension** (`.svg/.png/.webp/.css/.woff/...` via a
`_WARMUP_STATIC_EXT` set), gated behind an explicit `not (/api|/graphql|/ws)`
check so the extension rule can never open a dynamic surface (e.g.
`/api/x.json` stays 503). Lock both invariants with tests (static assets
non-503, dynamic-prefix+static-ext stays 503).
