---
name: SPA stale-chunk MIME error + autoscale cold-start login 503
description: Two durable deploy-time failure modes of a backend-served SPA + mobile client on Replit autoscale, and the heuristics that fix them.
---

# "'text/html' is not a valid JavaScript MIME type" after a redeploy

A lazy JS/CSS chunk request got an HTML body. Two compounding root causes,
both fixable as heuristics:

1. **A cacheable index.html outlives a redeploy.** If `index.html` is served
   cacheable, a browser keeps the OLD index, which references hashed chunk
   filenames that the new build deleted. **Heuristic:** serve index.html
   `no-store` from EVERY surface that emits it (root + SPA fallback); keep only
   the content-hashed asset mounts immutably cacheable.
2. **A SPA catch-all that serves index.html for ANY unmatched path** returns
   HTML (200) for a missing chunk, so the module loader throws the MIME error
   instead of seeing a clean 404. **Heuristic:** in the catch-all, a path WITH a
   file extension must get a real 404; only extension-less paths fall through to
   index.html for client routing.

**Why it matters:** the MIME error is misleading (looks like a bundler bug); the
real cause is cache + wrong 404 shape. After the fix, already-open browsers need
ONE hard refresh to drop the cached old index; then it self-heals.

# Mobile login timeout on the deployed app is NOT always CORS

Replit autoscale scales to zero. A freshly-hit cold instance answers `/api/*`
with a warm-up `503` (body `{"status":"starting"}`, Retry-After) until the
deferred bootstrap marks routes ready (~30-60s). A client that doesn't retry
`503` fails the first login → a Playwright `waitForURL` times out for all roles.

**Heuristics:**
- Make the mobile client retry the warm-up `503` — but gate the retry to the
  warm-up body SIGNATURE, not all `503`s, so a genuine handler-level `503` is
  never replayed (duplicate side effects for POST/PATCH/DELETE). Warm-up 503 is
  produced before any handler, so replaying it is side-effect-free.
- Make any retry backoff abort-aware (race the sleep against the AbortSignal) so
  a cancelled/unmounted request terminates immediately.
- A 30s `waitForURL` can still lose to a 60s cold start, so ALSO pre-warm the
  backend in CI (poll `/api/health` until 200 before the suite). Client retry
  covers real users; CI pre-warm guarantees the test starts warm.

# Client self-heal closes the open-tab-across-deploy gap

The server fix (no-store index + 404 for missing chunks) still leaves ONE gap:
a tab that was ALREADY OPEN across a redeploy holds the old in-memory index.html,
requests a now-deleted chunk, gets the clean 404, and its lazy dynamic import
rejects → "Importing a module script failed" / "Failed to fetch dynamically
imported module" → app stuck until a MANUAL refresh.

**Heuristic:** add an inline `index.html` handler (registered before the module
entry, and before lazy Sentry) that on `vite:preloadError` + `error` +
`unhandledrejection` matching the chunk-error message classes reloads the page
ONCE to pull the fresh index + new chunk names.

**Loop safety is the trap, not the reload.** A naive cooldown is NOT one-shot.
Use a real one-shot latch with THREE backends so a genuinely broken deploy can
never infinite-loop: in-memory (`window.__syroceChunkReloaded`), sessionStorage
(`syroce_chunk_reload_done`), AND a URL marker (`?_chunkreload=1`) for the
storage-denied branch (use `location.replace` so the post-reload load sees the
latch with no storage). If the same error recurs after the one reload, the latch
short-circuits → no second reload → the error is allowed to surface.

**Sentry beforeSend must be conditional, not global.** Dropping the chunk-error
classes unconditionally MASKS a genuinely broken deploy (same message). Gate the
drop on a heal-in-progress flag (`window.__syroceChunkHealing`, set only on the
first heal path right before reload). A recurrence after reload does NOT set the
flag → it reports. Match specific message classes, never a broad substring.

# The window-event self-heal MISSES render-path chunk errors

The `window` `error`/`unhandledrejection`/`vite:preloadError` listeners only see
chunk failures that bubble to the global scope. A `React.lazy` import that
rejects DURING render (failed load OR resolved-but-invalid module with no
`default` export) is caught by the in-app `ErrorBoundary` and rethrown inside
React's render cycle — it NEVER fires those window events, so the self-heal never
runs and `ErrorBoundary.componentDidCatch` pages Sentry directly (heal flag
false). This is the COMMON path: mobile taps, deep links, and post-login route
loads all go through render, not hover-preload. React.lazy also CACHES the
rejection, so the fallback's "Retry" rethrows forever.

**Heuristic:** expose the SAME one-shot latch from index.html
(`window.__syroceChunkReloadOnce` returning true=healing/false=latch-spent, plus
`window.__syroceIsChunkError`) and call it FIRST in `componentDidCatch`; if it
heals, `return` before `captureException`. One shared latch keeps the "reload
once, then surface" guarantee across both the window-event and render paths — a
broken deploy still pages after the single reload is spent.

**Treat "module resolved but invalid" as a chunk-error class too.** A stale
deploy can serve a chunk as index.html; the dynamic import RESOLVES but the
module lacks `.default`, and React.lazy throws an opaque
`_result.default is undefined` the matchers don't recognize. Normalize it at the
single lazy chokepoint (`lazyWithPreload`): `guardModule` throws a sentinel
(`"Dynamically imported module is invalid"`) added to every CHUNK_ERR list, so it
heals/drops exactly like a fetch-level chunk error.
